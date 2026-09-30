#!/usr/bin/env python3
"""SPRi(소프트웨어정책연구소, https://spri.kr) 전체 게시물 목록 크롤러.

1단계(목록 수집)만 한다: 게시판을 모두 찾고, 페이지를 넘기며 게시물의
제목·날짜·링크를 모은다. 본문과 PDF 내용 분석은 목차 승인 뒤 2단계에서 한다.

사용법:
    python3 spri/scripts/crawl_spri.py            # 전체 수집
    python3 spri/scripts/crawl_spri.py --max-pages 3   # 게시판당 3페이지만 (테스트)

결과:
    spri/data/boards.json   발견한 게시판 목록
    spri/data/posts.json    게시물 목록 (게시판별)
    spri/data/posts.csv     같은 내용의 CSV
"""
import argparse
import csv
import json
import re
import sys
import time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://spri.kr/"
OUT_DIR = Path(__file__).resolve().parent.parent / "data"
UA = "Mozilla/5.0 (compatible; study-crawler; personal learning use)"
DATE_RE = re.compile(r"(20\d{2})[.\-/]\s?(\d{1,2})[.\-/]\s?(\d{1,2})")
PAGE_PARAMS = ("page", "data_page", "pageIndex", "p")

# 검색으로 확인된 게시판. 메인 메뉴에서 찾은 게시판이 여기에 더해진다.
SEED_BOARDS = [
    "https://spri.kr/posts?code=magazine",
    "https://spri.kr/posts?code=AI-Brief",
    "https://spri.kr/posts?code=data_all",
    "https://spri.kr/posts?code=data_all&board_type=research",
    "https://spri.kr/posts?code=data_all&board_type=issue_reports",
    "https://spri.kr/posts?code=data_all&board_type=advice",
    "https://spri.kr/posts?code=data_all&board_type=ai_brief",
]

session = requests.Session()
session.headers["User-Agent"] = UA


def fetch(url, delay):
    time.sleep(delay)
    for attempt in range(3):
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or r.encoding
            return r.text
        except requests.RequestException as e:
            print(f"  ! {url} ({e}), 재시도 {attempt + 1}/3", file=sys.stderr)
            time.sleep(2 ** attempt)
    return None


def board_key(url):
    """게시판을 구분하는 키: code + board_type (페이지 파라미터 제외)."""
    q = parse_qs(urlparse(url).query)
    code = q.get("code", [""])[0]
    btype = q.get("board_type", [""])[0]
    return f"{code}|{btype}" if btype else code


def is_board_url(url):
    p = urlparse(url)
    return p.netloc.endswith("spri.kr") and p.path.rstrip("/") == "/posts" and "code=" in p.query


def is_post_url(url):
    p = urlparse(url)
    return p.netloc.endswith("spri.kr") and (
        re.match(r"^/posts/view/\d+", p.path) or re.match(r"^/post/\d+", p.path)
    )


def post_id(url):
    m = re.search(r"/posts?/(?:view/)?(\d+)", urlparse(url).path)
    return m.group(1) if m else url


def page_num(url):
    q = parse_qs(urlparse(url).query)
    for k in PAGE_PARAMS:
        if k in q and q[k][0].isdigit():
            return int(q[k][0])
    return 1


def discover_boards(delay):
    boards = OrderedDict()
    for u in SEED_BOARDS:
        boards.setdefault(board_key(u), {"url": u, "name": ""})
    html = fetch(BASE, delay)
    if html:
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            u = urljoin(BASE, a["href"])
            if is_board_url(u):
                k = board_key(u)
                name = a.get_text(" ", strip=True)
                if k not in boards:
                    boards[k] = {"url": u, "name": name}
                elif name and not boards[k]["name"]:
                    boards[k]["name"] = name
    return boards


def title_of(soup, fallback=""):
    t = soup.find("title")
    t = t.get_text(strip=True) if t else fallback
    return t.split(":", 1)[-1].strip() if ":" in t else t


def extract_posts(soup, page_url):
    posts = OrderedDict()
    for a in soup.find_all("a", href=True):
        u = urljoin(page_url, a["href"])
        if not is_post_url(u):
            continue
        title = a.get_text(" ", strip=True)
        # 날짜·분류는 보통 같은 목록 항목(li/tr/div) 안에 있다
        container = a.find_parent(["li", "tr", "article"]) or a.parent
        ctx = container.get_text(" ", strip=True) if container else ""
        m = DATE_RE.search(ctx)
        date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""
        pid = post_id(u)
        prev = posts.get(pid)
        # 같은 글에 링크가 여러 개면(썸네일+제목) 가장 긴 텍스트를 제목으로
        if prev is None or len(title) > len(prev["title"]):
            posts[pid] = {"id": pid, "title": title, "date": date, "url": u, "context": ctx[:300]}
    return posts


def pagination_links(soup, page_url, key):
    links = set()
    for a in soup.find_all("a", href=True):
        u = urljoin(page_url, a["href"])
        if is_board_url(u) and board_key(u) == key and page_num(u) > 1:
            links.add(u)
    return links


def with_page(url, param, n):
    p = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(p.query).items()}
    q[param] = str(n)
    return p._replace(query=urlencode(q)).geturl()


def crawl_board(key, info, delay, max_pages):
    print(f"[게시판] {key} {info['url']}")
    all_posts = OrderedDict()
    seen_pages, queue = set(), [info["url"]]
    first_html = None
    while queue and len(seen_pages) < max_pages:
        u = queue.pop(0)
        if u in seen_pages:
            continue
        seen_pages.add(u)
        html = fetch(u, delay)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        if first_html is None:
            first_html = soup
            if not info["name"]:
                info["name"] = title_of(soup)
        new = extract_posts(soup, u)
        for pid, p in new.items():
            all_posts.setdefault(pid, p)
        for link in sorted(pagination_links(soup, u, key), key=page_num):
            if link not in seen_pages:
                queue.append(link)
        print(f"  page {page_num(u)}: +{len(new)} (누적 {len(all_posts)})")

    # 페이지 링크가 JS로만 되어 있으면 파라미터를 직접 올려 본다
    if len(seen_pages) == 1 and all_posts:
        for param in PAGE_PARAMS:
            before = len(all_posts)
            n = 2
            while n <= max_pages:
                html = fetch(with_page(info["url"], param, n), delay)
                if not html:
                    break
                new = extract_posts(BeautifulSoup(html, "lxml"), info["url"])
                added = [pid for pid in new if pid not in all_posts]
                if not added:
                    break
                for pid in added:
                    all_posts[pid] = new[pid]
                print(f"  {param}={n}: +{len(added)} (누적 {len(all_posts)})")
                n += 1
            if len(all_posts) > before:
                break
    return list(all_posts.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=0.7, help="요청 간 대기(초)")
    ap.add_argument("--max-pages", type=int, default=500, help="게시판당 최대 페이지")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    boards = discover_boards(args.delay)
    (OUT_DIR / "boards.json").write_text(json.dumps(boards, ensure_ascii=False, indent=2))
    print(f"게시판 {len(boards)}개 발견")

    result = OrderedDict()
    for key, info in boards.items():
        result[key] = {"name": info["name"], "url": info["url"],
                       "posts": crawl_board(key, info, args.delay, args.max_pages)}
        (OUT_DIR / "posts.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))

    with open(OUT_DIR / "posts.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["board", "board_name", "id", "date", "title", "url"])
        for key, b in result.items():
            for p in b["posts"]:
                w.writerow([key, b["name"], p["id"], p["date"], p["title"], p["url"]])
    total = sum(len(b["posts"]) for b in result.values())
    print(f"완료: 게시판 {len(result)}개, 게시물 {total}건 → {OUT_DIR}")


if __name__ == "__main__":
    main()
