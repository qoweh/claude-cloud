#!/usr/bin/env python3
"""SPRi 게시물의 PDF 첨부를 받아 텍스트로 바꾸고, 그 전문에서 키워드를 찾는다.

웹 본문은 요약만 있거나 앞부분만 저장되므로(details.jsonl 은 3,000자까지),
보고서 안쪽 장(章)에서 다루는 주제는 PDF 전문을 봐야 찾을 수 있다.
PDF 와 텍스트는 spri/cache/ 에 두고 커밋하지 않는다.

사용법:
    pip install pypdf cffi
    python3 spri/scripts/pdf_text.py fetch --since 2023 --boards data_all,AI-Brief --workers 3
    python3 spri/scripts/pdf_text.py search "RAG|검색\\s?증강" --context 1
    python3 spri/scripts/pdf_text.py search "에이전트|agent" --min 5

fetch 는 게시물마다 첫 번째 PDF 첨부('PDF 다운로드' 버튼 우선)만 받는다.
search 는 게시물별 일치 수를 세고, 일치 수 순으로 앞뒤 문맥을 보여 준다.
"""
import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = ROOT / "cache" / "pdf_text"
BASE = "https://spri.kr/"
UA = "Mozilla/5.0 (compatible; study-crawler; personal learning use)"

_local = threading.local()


def get_session():
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers["User-Agent"] = UA
    return _local.session


def load_details():
    rows = {}
    for line in (DATA / "details.jsonl").read_text().splitlines():
        d = json.loads(line)
        rows[d["id"]] = d
    return rows


def pick_pdf(d):
    """'PDF 다운로드' 버튼 첨부를 먼저, 없으면 첫 첨부."""
    atts = d.get("attachments", [])
    for a in atts:
        if a["label"] in ("PDF 다운로드", "다운받기"):
            return a
    return atts[0] if atts else None


def pdf_to_text(content):
    from io import BytesIO
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(content))
    pages = []
    for i, page in enumerate(reader.pages, 1):
        try:
            t = page.extract_text() or ""
        except Exception as e:  # 깨진 페이지는 건너뛴다
            t = f"[page {i} 추출 실패: {type(e).__name__}]"
        pages.append(f"\n\n=== page {i} ===\n{t}")
    return "".join(pages), len(reader.pages)


def fetch_one(d, delay):
    out = CACHE / f"{d['id']}.txt"
    if out.exists():
        return d["id"], "cached", 0
    att = pick_pdf(d)
    if not att:
        return d["id"], "no-attachment", 0
    time.sleep(delay)
    for attempt in range(5):
        try:
            r = get_session().get(BASE + f"download/{att['file_id']}", timeout=120)
            r.raise_for_status()
            break
        except requests.RequestException as e:
            if attempt == 4:
                return d["id"], f"download-failed {type(e).__name__}", 0
            time.sleep(min(2 ** attempt, 20))
    if not r.content.startswith(b"%PDF"):
        return d["id"], "not-pdf", 0
    try:
        text, n = pdf_to_text(r.content)
    except Exception as e:
        return d["id"], f"parse-failed {type(e).__name__}", 0
    header = f"# {d['id']} {d['date']} {d.get('title') or d.get('list_title')}\n# file {att['file_id']} {n} pages\n"
    out.write_text(header + text)
    return d["id"], "ok", n


def cmd_fetch(args):
    CACHE.mkdir(parents=True, exist_ok=True)
    rows = load_details()
    boards = set(args.boards.split(","))
    todo = [d for d in rows.values()
            if d["date"] >= args.since and boards & set(d.get("boards", []))
            and not any(b.startswith(("notice",)) for b in d.get("boards", []))]
    todo.sort(key=lambda d: d["date"], reverse=True)
    print(f"대상 {len(todo)}건 → {CACHE}")
    stats = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(fetch_one, d, args.delay) for d in todo]
        for i, fut in enumerate(as_completed(futs), 1):
            pid, status, n = fut.result()
            key = status.split()[0]
            stats[key] = stats.get(key, 0) + 1
            if key not in ("ok", "cached"):
                print(f"  ! {pid} {status}", file=sys.stderr)
            if i % 25 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} {stats}")


def cmd_search(args):
    rows = load_details()
    rx = re.compile(args.pattern, re.I)
    hits = []
    for f in sorted(CACHE.glob("*.txt")):
        text = f.read_text()
        found = [m for m in rx.finditer(text)]
        if len(found) >= args.min:
            hits.append((len(found), f.stem, text, found))
    hits.sort(key=lambda h: -h[0])
    print(f"'{args.pattern}': {len(hits)}건 (PDF {len(list(CACHE.glob('*.txt')))}개 중)")
    for n, pid, text, found in hits[:args.limit]:
        d = rows.get(pid, {})
        print(f"\n{n:4d}  {d.get('date', '')} [{d.get('category', '')}] {d.get('title') or d.get('list_title', '')}  "
              f"https://spri.kr/posts/view/{pid}")
        terms = {}
        for m in found:
            terms[m.group(0)] = terms.get(m.group(0), 0) + 1
        print("      " + ", ".join(f"{k}×{v}" for k, v in sorted(terms.items(), key=lambda x: -x[1])[:8]))
        for m in found[:args.context]:
            s = re.sub(r"\s+", " ", text[max(0, m.start() - 80):m.end() + 80])
            print(f"      … {s} …")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--since", default="2023")
    f.add_argument("--boards", default="data_all,AI-Brief")
    f.add_argument("--workers", type=int, default=3)
    f.add_argument("--delay", type=float, default=0.7)
    s = sub.add_parser("search")
    s.add_argument("pattern")
    s.add_argument("--min", type=int, default=1, help="게시물당 최소 일치 수")
    s.add_argument("--limit", type=int, default=40)
    s.add_argument("--context", type=int, default=2, help="보여 줄 문맥 수")
    args = ap.parse_args()
    {"fetch": cmd_fetch, "search": cmd_search}[args.cmd](args)


if __name__ == "__main__":
    main()
