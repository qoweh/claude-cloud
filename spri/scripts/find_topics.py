#!/usr/bin/env python3
"""수집한 SPRi 자료에서 AI 서비스 개발 공부에 관련된 글을 주제별로 골라낸다.

crawl_spri.py 결과(data/posts.json, data/details.jsonl)를 읽어
제목·태그·목차(AI 브리프 기사 제목, 매거진 기사 제목)·본문 앞부분에서
주제 키워드를 찾고 점수를 매긴다. 제목·태그·목차에서 찾으면 3점, 본문에서 찾으면 1점.

사용법:
    python3 spri/scripts/find_topics.py

결과 (spri/data/):
    topic_candidates.csv   주제에 걸린 글 목록 (점수 높은 순)
    topic_summary.md       주제별 건수와 상위 글, AI 브리프에서 걸린 기사 제목
"""
import csv
import json
import re
from collections import OrderedDict, defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# 주제 → 정규식(대소문자 무시). 넓게 잡고 점수로 거른다.
TOPICS = OrderedDict([
    ("LLM·생성형 AI", r"\bLLM|거대\s?언어|대규모\s?언어|대형\s?언어|초거대|생성\s?(형|AI)|generative|\bGPT|ChatGPT|챗GPT|클로드|Claude|제미나이|Gemini|Llama|파운데이션\s?모델|기반\s?모델|foundation model|\bsLM\b|소형\s?언어|언어\s?모델|딥시크|DeepSeek|트랜스포머|transformer"),
    ("AI 에이전트", r"에이전트|에이전틱|\bagents?\b|agentic|\bMCP\b|컴퓨터\s?사용|computer use|오퍼레이터|AI\s?비서|코파일럿|copilot"),
    ("RAG·검색·지식", r"\bRAG\b|검색\s?증강|retrieval|벡터\s?(DB|데이터베이스|검색)|임베딩|embedding|지식\s?그래프|knowledge graph|검색\s?(엔진|알고리즘|서비스)|AI\s?검색|추천\s?(시스템|알고리즘|서비스)"),
    ("모델 기술(학습·추론·멀티모달)", r"파인\s?튜닝|fine[- ]?tun|미세\s?조정|프롬프트|prompt|추론\s?(모델|비용|능력|성능)|reasoning|강화\s?학습|RLHF|경량화|양자화|distill|증류|토큰\s?(비용|단가|수|가격)|토크노믹스|컨텍스트\s?(윈도|창|길이)|context window|멀티\s?모달|multimodal|월드\s?모델|world model|피지컬\s?AI|physical AI|딥러닝|deep learning|기계\s?학습|머신\s?러닝|machine learning|신경망|알고리즘 분석"),
    ("오픈소스·오픈 모델", r"오픈\s?소스|open\s?source|공개\s?SW|오픈\s?(모델|웨이트)|open[- ]weight|깃허브|GitHub|라이선스"),
    ("AI 인프라·SW 스택", r"GPU|NPU|TPU|AI\s?반도체|지능형\s?반도체|데이터\s?센터|클라우드|cloud|컴퓨팅\s?(자원|인프라|파워)|고성능\s?컴퓨팅|PyTorch|파이토치|JAX|CUDA|쿠다|MLPerf|엔비디아|NVIDIA|MLOps|LLMOps"),
    ("데이터", r"학습\s?데이터|합성\s?데이터|데이터\s?(셋|구축|품질|상호운용|이동권|거버넌스|경제|댐|라벨링|레이블링)|dataset|synthetic data|공공\s?데이터|빅\s?데이터"),
    ("개발자·개발 방식", r"코딩|coding|개발자|developer|바이브\s?코딩|vibe coding|코드\s?생성|code generation|AI\s?개발\s?도구|코딩\s?에이전트|\bAPI\b|SW\s?공학|소프트웨어\s?공학|DevOps|애자일|agile|컨테이너|마이크로\s?서비스|테스트\s?자동|시큐어\s?코딩|규모\s?산정|프로그래밍"),
    ("AI 신뢰·안전·평가", r"AI\s?안전|안전성|신뢰성|신뢰할 수 있는|trustworth|환각|hallucination|벤치마크|benchmark|성능\s?(측정|평가)|평가\s?(체계|지표|방법)|레드\s?팀|red[- ]?team|alignment|편향|bias|공정성|설명\s?가능|XAI|워터마크|딥페이크|AI\s?위험|AI\s?윤리|책임\s?있는 AI"),
    ("AI 서비스·비즈니스", r"AI\s?(서비스|도입|활용|전환|스타트업|비즈니스|기업)|\bAX\b|인공지능\s?(전환|도입|활용)|업무\s?자동화|챗봇|chatbot|SaaS|수익\s?모델|비즈니스\s?모델"),
    ("정책·규제", r"AI\s?(법|기본법|규제|거버넌스|행정명령)|EU\s?AI|AI\s?Act|인공지능\s?(법|기본법)|저작권|개인정보|AI\s?정책"),
    ("인재·커리어", r"AI\s?인재|SW\s?인재|디지털\s?인재|인재\s?양성|AI\s?교육|SW\s?교육|코딩\s?교육|채용|직무|일자리|고용|커리어"),
])
TOPIC_RE = {k: re.compile(v, re.I) for k, v in TOPICS.items()}


def load():
    posts = OrderedDict()
    for key, b in json.loads((DATA / "posts.json").read_text()).items():
        for p in b["posts"]:
            m = posts.setdefault(p["id"], dict(p, boards=[]))
            m["boards"].append(key)
            if len(p.get("date", "")) > len(m.get("date", "")):
                m["date"] = p["date"]
    details = {}
    path = DATA / "details.jsonl"
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            details[d["id"]] = d
    return posts, details


def main():
    posts, details = load()
    rows = []
    brief_hits = defaultdict(list)  # 주제 → [(날짜, 호, 기사 제목)]
    for pid, p in posts.items():
        d = details.get(pid, {})
        title = d.get("title") or p["title"]
        strong = " ".join([title, " ".join(p.get("tags", [])), " ".join(d.get("tags", [])),
                           " ".join(d.get("toc", []))])
        weak = d.get("text", "") + " " + p.get("summary", "")
        scores, hits = {}, {}
        for topic, rx in TOPIC_RE.items():
            s_hits = set(m.group(0) for m in rx.finditer(strong))
            w_hits = set(m.group(0) for m in rx.finditer(weak))
            score = 3 * len(rx.findall(strong)) + len(rx.findall(weak))
            if score:
                scores[topic] = score
                hits[topic] = sorted(s_hits | w_hits, key=str.lower)[:6]
        # AI 브리프·매거진은 목차의 기사 제목 단위로도 본다
        for item in d.get("toc", []):
            for topic, rx in TOPIC_RE.items():
                if rx.search(item):
                    brief_hits[topic].append((d.get("date") or p["date"], title, item, pid))
        if not scores:
            continue
        date = d.get("date") or p["date"]
        rows.append({
            "id": pid, "date": date, "category": p.get("category") or d.get("category", ""),
            "boards": "; ".join(p["boards"]), "title": title, "total": sum(scores.values()),
            "topics": "; ".join(f"{k}({v})" for k, v in sorted(scores.items(), key=lambda x: -x[1])),
            "main_topic": max(scores, key=scores.get),
            "keywords": "; ".join(f"{k}: {', '.join(v)}" for k, v in hits.items()),
            "url": f"https://spri.kr/posts/view/{pid}",
        })
    rows.sort(key=lambda r: r["date"], reverse=True)
    rows.sort(key=lambda r: r["total"], reverse=True)

    with open(DATA / "topic_candidates.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["id"])
        w.writeheader()
        w.writerows(rows)

    by_topic = defaultdict(list)
    for r in rows:
        for part in r["topics"].split("; "):
            t, s = part.rsplit("(", 1)
            by_topic[t].append((int(s.rstrip(")")), r))

    out = ["# SPRi 자료 주제별 후보", "",
           f"게시물 {len(posts)}건 중 상세 {len(details)}건을 읽어 주제 키워드가 걸린 글 {len(rows)}건을 골랐다.",
           "점수: 제목·태그·목차에서 찾으면 3점, 본문 앞부분에서 찾으면 1점. 전체 목록은 `topic_candidates.csv`.", "",
           "| 주제 | 걸린 글 | 제목·태그·목차에서 걸린 글 | AI 브리프·매거진 기사 |", "|---|---:|---:|---:|"]
    for t in TOPICS:
        items = by_topic.get(t, [])
        strong_n = sum(1 for s, r in items if s >= 3)
        out.append(f"| {t} | {len(items)} | {strong_n} | {len(brief_hits.get(t, []))} |")
    for t in TOPICS:
        items = sorted(by_topic.get(t, []), key=lambda x: x[1]["date"], reverse=True)
        items.sort(key=lambda x: x[0], reverse=True)
        if not items:
            continue
        out += ["", f"## {t}", "", "### 점수 상위 글", ""]
        for s, r in items[:25]:
            out.append(f"- [{r['title']}]({r['url']}) — {r['date']}, {r['category'] or r['boards']}, 점수 {s}")
        arts = sorted(brief_hits.get(t, []), reverse=True)
        if arts:
            out += ["", f"### AI 브리프·매거진 기사 ({len(arts)}건 중 최근 30건)", ""]
            for date, issue, item, pid in arts[:30]:
                out.append(f"- {item} — [{issue}](https://spri.kr/posts/view/{pid}), {date}")
    (DATA / "topic_summary.md").write_text("\n".join(out) + "\n")
    print(f"후보 {len(rows)}건 → {DATA / 'topic_candidates.csv'}, {DATA / 'topic_summary.md'}")


if __name__ == "__main__":
    main()
