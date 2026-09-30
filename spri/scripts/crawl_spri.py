#!/usr/bin/env python3
"""SPRi(소프트웨어정책연구소, https://spri.kr) 전체 게시물 크롤러.

두 단계로 수집한다.
  1) 목록: 게시판마다 모든 페이지를 넘기며 제목·날짜·분류·저자·태그 등을 모은다.
  2) 상세(--details): 게시물마다 상세 페이지를 열어 정확한 날짜, 저자 소속,
     본문 요약, 목차(AI 브리프·매거진 기사 제목), 첨부파일 목록을 모은다.
     중간에 끊겨도 다시 실행하면 이미 받은 글은 건너뛴다.

사용법:
    python3 spri/scripts/crawl_spri.py                  # 목록만 전체 수집
    python3 spri/scripts/crawl_spri.py --details        # 목록 + 상세 전체 수집
    python3 spri/scripts/crawl_spri.py --max-pages 2    # 게시판당 2페이지만 (테스트)
    python3 spri/scripts/crawl_spri.py --details-only   # 이미 받은 목록으로 상세만

결과 (spri/data/):
    boards.json     게시판 목록과 게시판별 페이지·게시물 수
    posts.json      게시판별 게시물 목록
    posts.csv       게시물 한 건당 한 줄 (여러 게시판에 있는 글은 합쳐서)
    details.jsonl   게시물 상세 (한 줄에 한 건)
    details.csv     상세 중 요약·목차·첨부를 펼친 표
"""
import argparse
import csv
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://spri.kr/"
OUT_DIR = Path(__file__).resolve().parent.parent / "data"
UA = "Mozilla/5.0 (compatible; study-crawler; personal learning use)"
PAGE_PARAMS = ("data_page", "page")
FILE_DOWN = re.compile(r"file_down\(\s*'\s*(\d+)\s*'\s*\)")  # file_down(' 23065') 처럼 공백이 낀 글도 있다

# (key, 이름, URL). 메인 메뉴·목록 페이지에서 확인한 게시판이다.
# data_all 은 연구자료 전체이고 board_type 별 게시판은 그 부분집합이다.
# 메뉴에서 새로 찾은 게시판은 실행할 때 뒤에 더해진다.
BOARDS = [
    ("data_all", "연구자료 전체", "posts?code=data_all"),
    ("data_all|research", "연구보고서", "posts?code=data_all&board_type=research"),
    ("data_all|issue_reports", "이슈리포트", "posts?code=data_all&board_type=issue_reports"),
    ("data_all|column", "SPRi칼럼", "posts?code=data_all&board_type=column"),
    ("data_all|industry_trend", "산업/정책 동향", "posts?code=data_all&board_type=industry_trend"),
    ("data_all|ai_brief", "기타자료", "posts?code=data_all&board_type=ai_brief"),
    ("magazine", "SW중심사회 (월간 매거진)", "posts?code=magazine"),
    ("AI-Brief", "AI 브리프", "posts?code=AI-Brief"),
    ("annual_reports", "산업연간보고서", "posts?code=annual_reports"),
    ("sw_reports", "승인통계보고서", "posts?code=sw_reports"),
    ("archive", "이전 간행물", "posts?code=archive"),
    ("conference|flg1", "전체행사", "posts?code=conference&flg=1"),
    ("conference", "컨퍼런스", "posts?code=conference"),
    ("forum", "포럼", "posts?code=forum"),
    ("speech", "세미나", "posts?code=speech"),
    ("notice", "공지사항", "posts?code=notice"),
]
# 메뉴에는 있지만 게시물 목록이 아닌 안내 페이지라 건너뛴다
SKIP_BOARDS = {"open_release"}

_local = threading.local()


def get_session():
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers["User-Agent"] = UA
    return _local.session


def fetch(url, delay, tries=5):
    """HTML을 받아 온다. 404는 바로 포기하고, 연결 오류는 간격을 늘려 재시도한다."""
    time.sleep(delay)
    for attempt in range(tries):
        try:
            r = get_session().get(url, timeout=40)
            if r.status_code == 404:
                print(f"  ! 404 {url}", file=sys.stderr)
                return None
            r.raise_for_status()
            return r.content
        except requests.RequestException as e:
            print(f"  ! {url} ({type(e).__name__}), 재시도 {attempt + 1}/{tries}", file=sys.stderr)
            time.sleep(min(2 ** attempt, 20))
    return None


def soup_of(html):
    return BeautifulSoup(html, "lxml")


def text_of(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""


def board_key(url):
    q = parse_qs(urlparse(url).query)
    key = q.get("code", [""])[0]
    if q.get("board_type", [""])[0]:
        key += "|" + q["board_type"][0]
    if q.get("flg", [""])[0] == "1":
        key += "|flg1"
    return key


def post_id(url):
    m = re.search(r"/posts/view/(\d+)", url)
    return m.group(1) if m else None


def with_page(url, param, n):
    p = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(p.query, keep_blank_values=True).items()}
    q[param] = str(n)
    return p._replace(query=urlencode(q)).geturl()


# ---------- 날짜 ----------

DATE_FULL = re.compile(r"(20\d{2}|19\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})")
DATE_MONTH = re.compile(r"(20\d{2}|19\d{2})\s*년\s*(\d{1,2})\s*월")


def parse_date(s):
    m = DATE_FULL.search(s or "")
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = DATE_MONTH.search(s or "")
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    return ""


# ---------- 게시판 찾기 ----------

def discover_boards(delay):
    boards = OrderedDict((k, {"name": n, "url": urljoin(BASE, u)}) for k, n, u in BOARDS)
    html = fetch(BASE, delay)
    if not html:
        return boards
    for a in soup_of(html).find_all("a", href=True):
        u = urljoin(BASE, a["href"])
        p = urlparse(u)
        if not (p.netloc.endswith("spri.kr") and p.path.rstrip("/") == "/posts" and "code=" in p.query):
            continue
        k = board_key(u)
        if k not in boards and k not in SKIP_BOARDS:
            boards[k] = {"name": text_of(a).lstrip("- ").strip() or k, "url": u}
            print(f"  새 게시판 발견: {k} {u}")
    return boards


# ---------- 목록 ----------

def pagination(soup):
    """페이지 파라미터 이름과 마지막 페이지 번호를 구한다."""
    param, last = None, 1
    for a in soup.select(".pagination a[href]"):
        q = parse_qs(urlparse(a["href"]).query)
        for k in PAGE_PARAMS:
            v = q.get(k, [""])[0]
            if v.isdigit():
                param = param or k
                last = max(last, int(v))
    return param, last


def parse_item(li, page_url):
    """목록의 게시물 한 건(li)을 읽는다. 게시판마다 모양이 달라서 있는 것만 채운다."""
    ids = OrderedDict()
    for a in li.find_all("a", href=True):
        pid = post_id(a["href"])
        if pid:
            ids.setdefault(pid, urljoin(page_url, a["href"]))
    if not ids:
        return None
    pid, url = next(iter(ids.items()))

    title_el = li.select_one(".title a") or li.select_one(".title")
    title = text_of(title_el)
    img = li.find("img", alt=True)
    data_el = li.select_one(".text_box .data")
    if not title and img and img["alt"].strip() and img["alt"].strip() != "이미지":
        title = img["alt"].strip()
    if not title and data_el:
        title = text_of(data_el).replace("날짜", "").strip()

    # 날짜: '날짜' 라벨 옆, 없으면 매거진처럼 '2026년09월호' 형식
    date = ""
    for hide in li.select(".hide"):
        if hide.get_text(strip=True) == "날짜":
            date = parse_date(text_of(hide.parent))
            break
    if not date and data_el:
        date = parse_date(text_of(data_el))
    if not date:
        date = parse_date(title)

    views = ""
    for hide in li.select(".hide"):
        if hide.get_text(strip=True) == "조회수":
            views = re.sub(r"[^\d]", "", text_of(hide.parent))
            break

    mark = li.select(".mark_list_area .list")
    category, number = "", ""
    if mark:
        c1 = mark[0].select_one(".bg_c1")
        c2 = mark[0].select_one(".bg_c2")
        category = text_of(c1)
        number = text_of(c2)

    authors = list(OrderedDict.fromkeys(text_of(a) for a in li.select('a[href*="s_authors="]')))
    tags = list(OrderedDict.fromkeys(text_of(a) for a in li.select('a[href*="s_tags="]')))
    summary = text_of(li.select_one(".info_list")) or text_of(li.select_one(".text"))
    files = FILE_DOWN.findall(str(li))

    return {
        "id": pid, "title": title, "date": date, "category": category, "number": number,
        "authors": authors, "tags": tags, "views": views, "summary": summary[:500],
        "file_ids": files, "url": url,
    }


def parse_list_page(soup, page_url):
    posts = OrderedDict()
    for box in soup.select(".com_list_box"):
        ul = box.find("ul", recursive=False) or box.find("ul")
        items = ul.find_all("li", recursive=False) if ul else []
        for li in items:
            p = parse_item(li, page_url)
            if p and p["id"] not in posts:
                posts[p["id"]] = p
    return posts


def crawl_board(key, info, delay, max_pages):
    print(f"[게시판] {key} ({info['name']}) {info['url']}")
    html = fetch(info["url"], delay)
    if not html:
        info.update(pages=0, count=0)
        return []
    soup = soup_of(html)
    param, last = pagination(soup)
    all_posts = parse_list_page(soup, info["url"])
    print(f"  page 1/{last}: {len(all_posts)}건 (파라미터 {param})")

    n = 2
    while param and n <= min(last, max_pages):
        page_url = with_page(info["url"], param, n)
        html = fetch(page_url, delay)
        if html is None:
            print(f"  ! page {n} 실패, 건너뜀", file=sys.stderr)
            n += 1
            continue
        soup = soup_of(html)
        new = parse_list_page(soup, page_url)
        added = [pid for pid in new if pid not in all_posts]
        for pid in added:
            all_posts[pid] = new[pid]
        # 페이지 번호가 10개씩만 보이는 게시판도 있으니 마지막 번호를 계속 갱신한다
        _, seen_last = pagination(soup)
        last = max(last, seen_last)
        print(f"  page {n}/{last}: +{len(added)} (누적 {len(all_posts)})")
        if not new:
            break
        n += 1

    info.update(pages=min(last, max_pages), count=len(all_posts), page_param=param)
    return list(all_posts.values())


def merge_posts(result):
    """게시판별 목록을 게시물 하나당 한 줄로 합친다. 빈 값은 다른 게시판 값으로 채운다."""
    merged = OrderedDict()
    for key, b in result.items():
        for p in b["posts"]:
            m = merged.get(p["id"])
            if m is None:
                m = dict(p, boards=[])
                merged[p["id"]] = m
            else:
                for f in ("title", "date", "category", "number", "views", "summary"):
                    if not m[f] or (f == "date" and len(p[f]) > len(m[f])):
                        m[f] = p[f] or m[f]
                for f in ("authors", "tags", "file_ids"):
                    m[f] = list(OrderedDict.fromkeys(m[f] + p[f]))
            m["boards"].append(key)
    return merged


def load_details():
    path = OUT_DIR / "details.jsonl"
    rows = OrderedDict()
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            rows[d["id"]] = d
    return rows


def write_lists(boards, result, details=None):
    (OUT_DIR / "boards.json").write_text(json.dumps(boards, ensure_ascii=False, indent=2))
    (OUT_DIR / "posts.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    merged = merge_posts(result)
    # 목록에 날짜·저자·번호가 없거나 덜 자세하면 상세에서 채운다
    for pid, d in (details or {}).items():
        p = merged.get(pid)
        if not p:
            continue
        if len(d.get("date", "")) > len(p["date"]):
            p["date"] = d["date"]
        if not p["authors"] and d.get("authors"):
            p["authors"] = [a["name"] for a in d["authors"]]
        p["number"] = p["number"] or d.get("number", "")
        if not p["file_ids"]:
            p["file_ids"] = [a["file_id"] for a in d.get("attachments", [])]
    with open(OUT_DIR / "posts.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "date", "category", "number", "title", "authors", "tags",
                    "views", "boards", "file_ids", "url", "summary"])
        for p in sorted(merged.values(), key=lambda x: (x["date"], int(x["id"])), reverse=True):
            w.writerow([p["id"], p["date"], p["category"], p["number"], p["title"],
                        "; ".join(p["authors"]), "; ".join(p["tags"]), p["views"],
                        "; ".join(p["boards"]), "; ".join(p["file_ids"]), p["url"], p["summary"]])
    return merged


# ---------- 상세 ----------

NOISE = ("공유 열기", "글자크기", "PDF 다운로드", "HTML 보기", "e-book 보기", "목록")


def parse_detail(html, url):
    soup = soup_of(html)
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    d = {"id": post_id(url), "url": url}

    # 머리: 번호 / 제목 / 저자(소속) / 날짜 / 조회수
    top = soup.select_one(".title_area")
    box = top.parent if top else soup
    d["number"] = text_of(top.select_one(".bg_c2")) if top else ""
    d["title"] = text_of(top.select_one(".title")) if top else ""
    d["authors"] = []
    for li in box.select(".info_list_area li"):
        a = li.find("a")
        name = text_of(a) if a else ""
        whole = text_of(li)
        position = whole[len(name):].strip() if name and whole.startswith(name) else whole
        d["authors"].append({"name": name or whole, "position": position if name else ""})
    date, views = "", ""
    for hide in box.select(".hide") or soup.select(".hide"):
        label = hide.get_text(strip=True)
        if label == "날짜" and not date:
            date = parse_date(text_of(hide.parent))
        elif label == "조회수" and not views:
            views = re.sub(r"[^\d]", "", text_of(hide.parent))
    d["date"], d["views"] = date, views

    # 본문: 메뉴/푸터를 뺀 텍스트에서 '글자크기 작게' 뒤부터 '목록' 앞까지
    body = soup.body or soup
    lines = [l.strip().strip("\u200b").strip() for l in body.get_text("\n").split("\n")]
    lines = [l for l in lines if l]
    try:
        start = max(i for i, l in enumerate(lines) if l == "글자크기 작게") + 1
    except ValueError:
        start = 0
    try:
        end = start + lines[start:].index("목록")
    except ValueError:
        end = len(lines)
    content = [l for l in lines[start:end] if l not in NOISE]

    # 목차: AI 브리프의 '▹ 기사 제목', 매거진의 다운로드 링크 제목
    toc = [l.lstrip("▹▸•·- ").strip() for l in content if l.startswith(("▹", "▸"))]
    attachments = []
    seen = set()
    for a in soup.find_all(["a", "button"]):
        fid = None
        m = re.search(r"/download/(\d+)", a.get("href", "") + " " + a.get("data-down", ""))
        if m:
            fid = m.group(1)
        m = FILE_DOWN.search(a.get("onclick", ""))
        if m:
            fid = m.group(1)
        if fid and fid not in seen:
            seen.add(fid)
            label = text_of(a)
            attachments.append({"file_id": fid, "label": label,
                                "url": urljoin(BASE, f"download/{fid}")})
    for m in re.finditer(r"\[download id=(\d+)\]", " ".join(content)):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            attachments.append({"file_id": m.group(1), "label": "",
                                "url": urljoin(BASE, f"download/{m.group(1)}")})
    if not toc:
        toc = [a["label"] for a in attachments if a["label"] and a["label"] not in ("PDF 다운로드", "다운받기")]

    tags = [text_of(a) for a in soup.select('a[href*="s_tags="]')]
    text = "\n".join(content)
    d.update(tags=list(OrderedDict.fromkeys(tags)), toc=toc, attachments=attachments,
             text=text[:3000], text_length=len(text))
    return d


def fetch_detail(p, delay):
    url = urljoin(BASE, f"posts/view/{p['id']}?" + urlparse(p["url"]).query)
    html = fetch(url, delay)
    if not html:
        return None
    d = parse_detail(html, url)
    d["list_title"], d["category"], d["boards"] = p["title"], p["category"], p["boards"]
    d["date"] = d["date"] or p["date"]
    return d


def crawl_details(merged, delay, limit, workers=1, refetch_empty=False):
    """상세를 받아 details.jsonl 에 이어 쓴다. 같은 글이 여러 줄이면 마지막 줄을 쓴다."""
    path = OUT_DIR / "details.jsonl"
    done = {pid for pid, d in load_details().items()
            if not (refetch_empty and not d.get("attachments"))}
    todo = [p for p in merged.values() if p["id"] not in done]
    if limit:
        todo = todo[:limit]
    print(f"[상세] 받을 글 {len(todo)}건 (이미 받은 글 {len(done)}건, 동시 {workers}개)")
    with open(path, "a", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_detail, p, delay): p for p in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            p, d = futures[fut], fut.result()
            if d:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
                f.flush()
            if i % 25 == 0 or i == len(todo):
                title = (d or {}).get("title") or p["title"]
                print(f"  {i}/{len(todo)} {p['id']} {(d or {}).get('date', '실패')} {title[:40]}")


def write_details_csv():
    rows = load_details()
    with open(OUT_DIR / "details.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "date", "category", "number", "title", "authors", "tags",
                    "toc", "attachments", "views", "boards", "url", "text_head"])
        for d in sorted(rows.values(), key=lambda x: (x["date"], int(x["id"])), reverse=True):
            w.writerow([
                d["id"], d["date"], d.get("category", ""), d.get("number", ""),
                d.get("title") or d.get("list_title", ""),
                "; ".join(f"{a['name']}({a['position']})" if a["position"] else a["name"]
                          for a in d["authors"]),
                "; ".join(d["tags"]), " | ".join(d["toc"]),
                "; ".join(f"{a['file_id']}:{a['label']}" for a in d["attachments"]),
                d.get("views", ""), "; ".join(d.get("boards", [])), d["url"], d["text"][:800],
            ])
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=0.7, help="요청 간 대기(초)")
    ap.add_argument("--max-pages", type=int, default=1000, help="게시판당 최대 페이지")
    ap.add_argument("--details", action="store_true", help="목록 뒤에 상세 페이지도 수집")
    ap.add_argument("--details-only", action="store_true", help="저장된 목록으로 상세만 수집")
    ap.add_argument("--details-limit", type=int, default=0, help="상세를 이만큼만 (테스트)")
    ap.add_argument("--workers", type=int, default=1, help="상세를 동시에 받을 개수")
    ap.add_argument("--refetch-empty", action="store_true", help="첨부가 비어 있는 상세를 다시 받기")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.details_only:
        boards = json.loads((OUT_DIR / "boards.json").read_text())
        result = json.loads((OUT_DIR / "posts.json").read_text())
        merged = merge_posts(result)
    else:
        boards = discover_boards(args.delay)
        print(f"게시판 {len(boards)}개")
        result = OrderedDict()
        for key, info in boards.items():
            posts = crawl_board(key, info, args.delay, args.max_pages)
            result[key] = {"name": info["name"], "url": info["url"], "posts": posts}
            write_lists(boards, result)
        merged = write_lists(boards, result)
        total = sum(len(b["posts"]) for b in result.values())
        print(f"목록 완료: 게시판 {len(result)}개, 게시판별 합계 {total}건, 중복 제거 {len(merged)}건")

    if args.details or args.details_only:
        crawl_details(merged, args.delay, args.details_limit, args.workers, args.refetch_empty)
        n = write_details_csv()
        write_lists(boards, result, load_details())
        print(f"상세 완료: {n}건 → {OUT_DIR / 'details.csv'}")


if __name__ == "__main__":
    main()
