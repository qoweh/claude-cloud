#!/usr/bin/env python3
"""AI 브리프·매거진 기사 제목을 자료집의 8개 부로 나눠 부록 C 색인을 만든다.

data/details.jsonl 의 toc(AI 브리프 기사 제목, 매거진 기사 제목)를 읽어
부마다 키워드 규칙으로 분류한다. 한 기사가 여러 부에 걸리면 PRIORITY 순서로
가장 구체적인 부 하나에만 넣는다(예: "에이전트 코딩 모델 출시"는 4부).

사용법:
    python3 spri/scripts/build_index.py      # spri/부록C_기사색인.md 생성
"""
import json
import re
from collections import OrderedDict, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "부록C_기사색인.md"
SINCE = "2019"  # AI 브리프 1호가 2019-11, 매거진은 2019년 이후만 싣는다

PARTS = OrderedDict([
    ("1", ("1부. 생성형 AI는 어디까지 왔나", "01_생성형AI.md",
           r"\bLLM|거대\s?언어|대규모\s?언어|대형\s?언어|초거대|생성\s?(형|AI)|generative|\bGPT|ChatGPT|챗GPT|클로드|Claude|"
           r"제미나이|Gemini|Llama|라마\s?\d|파운데이션\s?모델|기반\s?모델|foundation model|언어\s?모델|딥시크|DeepSeek|"
           r"그록|Grok|AI Index|AI 인덱스")),
    ("2", ("2부. 모델 기술과 오픈 모델 생태계", "02_모델과_오픈모델.md",
           r"오픈\s?소스|open\s?source|오픈\s?(모델|웨이트)|open[- ]weight|파인\s?튜닝|fine[- ]?tun|미세\s?조정|프롬프트|prompt|"
           r"추론\s?(모델|비용|능력|성능)|reasoning|강화\s?학습|경량화|양자화|증류|토크노믹스|토큰\s?(비용|가격)|"
           r"멀티\s?모달|multimodal|월드\s?모델|world model|피지컬\s?AI|physical AI|휴머노이드|딥러닝|머신\s?러닝|기계\s?학습|"
           r"신경망|해석\s?가능|\bsLM\b|소형\s?언어|온디바이스")),
    ("3", ("3부. RAG·검색·데이터", "03_RAG_검색_데이터.md",
           r"\bRAG\b|검색\s?증강|retrieval|임베딩|embedding|벡터|지식\s?그래프|검색|퍼플렉시티|Perplexity|추천\s?(시스템|알고리즘|서비스)|"
           r"학습\s?데이터|합성\s?데이터|데이터\s?(셋|품질|상호운용|이동권|거버넌스|경제|공유|라벨링)|dataset|빅\s?데이터|공공\s?데이터")),
    ("4", ("4부. AI 에이전트", "04_AI_에이전트.md",
           r"에이전트|에이전틱|\bagents?\b|agentic|\bMCP\b|\bA2A\b|컴퓨터\s?사용|computer use|오퍼레이터|AI\s?비서|코파일럿|copilot|"
           r"딥\s?리서치|deep research|마누스")),
    ("5", ("5부. AI를 떠받치는 인프라와 SW 스택", "05_인프라와_SW스택.md",
           r"GPU|NPU|TPU|AI\s?반도체|AI\s?칩|지능형\s?반도체|데이터\s?센터|클라우드|cloud|컴퓨팅\s?(자원|인프라|파워|센터)|"
           r"슈퍼\s?컴퓨터|고성능\s?컴퓨팅|엔비디아|NVIDIA|GTC|PyTorch|파이토치|CUDA|MLPerf|MLOps|LLMOps|전력")),
    ("6", ("6부. AI 시대의 개발자와 커리어", "06_개발자와_커리어.md",
           r"코딩|coding|개발자|developer|코드\s?생성|코덱스|Codex|깃허브|GitHub|프로그래밍|SW\s?공학|소프트웨어\s?공학|"
           r"AI\s?인재|SW\s?인재|디지털\s?인재|인재\s?양성|인력|AI\s?교육|SW\s?교육|채용|직무|일자리|고용|노동|직업|해고|감원")),
    ("7", ("7부. 책임 있는 AI 서비스 만들기: 안전·신뢰·평가·규제", "07_책임있는_AI.md",
           r"AI\s?안전|안전성|안전\s?(연구소|보고서|프레임워크|표준)|신뢰성|신뢰할 수 있는|trustworth|환각|hallucination|벤치마크|benchmark|"
           r"평가|레드\s?팀|red[- ]?team|정렬|alignment|편향|bias|공정성|설명\s?가능|XAI|워터마크|딥페이크|AI\s?위험|위험\s?관리|"
           r"AI\s?윤리|윤리|책임\s?있는|보안|탈옥|프롬프트\s?주입|"
           r"AI\s?(법|기본법|규제|거버넌스|행정명령)|EU\s?AI|AI\s?Act|인공지능\s?(법|기본법)|법안|규제|행정명령|저작권|개인정보|소송|반독점")),
    ("8", ("8부. AI 서비스와 비즈니스", "08_서비스와_비즈니스.md",
           r"AI\s?(서비스|도입|활용|전환|스타트업|비즈니스|투자|시장)|\bAX\b|인공지능\s?(전환|도입|활용)|업무\s?자동화|챗봇|chatbot|"
           r"SaaS|수익|매출|비즈니스\s?모델|투자|인수|벤처|스타트업|공공\s?부문|공공\s?행정|지방\s?행정|행정\s?(서비스|업무)")),
])
# 한 기사가 여러 부에 걸릴 때 먼저 확인할 순서: 좁고 구체적인 주제부터
PRIORITY = ["4", "3", "7", "2", "5", "6", "8", "1"]
PART_RE = {k: re.compile(v[2], re.I) for k, v in PARTS.items()}


def load_articles():
    rows = [json.loads(line) for line in (DATA / "details.jsonl").read_text().splitlines()]
    arts = []
    for d in rows:
        boards = set(d.get("boards", []))
        if not boards & {"AI-Brief", "archive", "magazine"} or d["date"] < SINCE:
            continue
        kind = "매거진" if "magazine" in boards else "AI 브리프"
        files = {a["label"]: a["file_id"] for a in d.get("attachments", [])}
        issue = d.get("title") or d.get("list_title", "")
        for title in d.get("toc", []):
            if kind == "매거진" and (title.startswith("중간-") or len(title) < 6):
                continue  # 포토에세이 등
            url = (f"https://spri.kr/download/{files[title]}" if title in files
                   else f"https://spri.kr/posts/view/{d['id']}")
            arts.append({"date": d["date"], "title": title, "kind": kind, "issue": issue, "url": url})
    return arts


def classify(title):
    for k in PRIORITY:
        if PART_RE[k].search(title):
            return k
    return None


def main():
    arts = load_articles()
    by_part = defaultdict(list)
    unmatched = 0
    for a in arts:
        k = classify(a["title"])
        if k:
            by_part[k].append(a)
        else:
            unmatched += 1

    n_brief = sum(a["kind"] == "AI 브리프" for a in arts)
    n_mag = len(arts) - n_brief
    lines = [
        "# 부록 C. AI 브리프·매거진 기사 색인",
        "",
        "[← 부록 B](부록B_행사발표자료.md) · [목차](00_목차.md)",
        "",
        f"{SINCE}년 이후 월간 AI 브리프 기사 {n_brief:,}건과 월간 SW중심사회(매거진) 기사 {n_mag:,}건의 제목을 "
        f"8개 부로 나눴다. 키워드 규칙으로 자동 분류해서 {len(arts) - unmatched:,}건이 들어갔고, "
        f"어느 부에도 걸리지 않은 {unmatched:,}건(정책 일반, 해외 동향 등)은 뺐다. "
        "한 기사는 가장 구체적인 부 하나에만 넣었다. 최신 기사부터 정렬했다.",
        "",
        "AI 브리프 기사는 그 호의 게시물 페이지로, 매거진 기사는 기사별 PDF로 연결된다. "
        "2022년 AI 브리프 10개 호는 웹페이지에 기사 목록이 없어 빠져 있다.",
        "",
        "이 파일은 `python3 spri/scripts/build_index.py`로 다시 만든다. 분류 규칙도 그 스크립트에 있다.",
        "",
        "| 부 | 기사 |",
        "|---|---:|",
    ]
    for k, (name, fname, _) in PARTS.items():
        anchor = re.sub(r"[^\w\- ]", "", name.lower()).replace(" ", "-")
        lines.append(f"| [{name}](#{anchor}) | {len(by_part[k]):,} |")

    for k, (name, fname, _) in PARTS.items():
        items = sorted(by_part[k], key=lambda a: (a["date"], a["title"]), reverse=True)
        lines += ["", f"## {name}", "", f"본문: [{fname}]({fname}) · {len(items):,}건"]
        year = None
        for a in items:
            if a["date"][:4] != year:
                year = a["date"][:4]
                lines += ["", f"### {year}", ""]
            if a["kind"] == "매거진":
                src = f"매거진 {a['date'][:7]}"
            elif "AI Brief" in a["issue"]:
                src = a["issue"]  # [AI Brief 스페셜] …, AI Brief 23호
            else:
                src = f"AI 브리프 {a['issue']}"
            lines.append(f"- {a['date']} {a['title']} · [{src}]({a['url']})")
    OUT.write_text("\n".join(lines) + "\n")
    print(f"기사 {len(arts)}건 중 {len(arts) - unmatched}건 분류 → {OUT}")
    for k, (name, _, _) in PARTS.items():
        print(f"  {name}: {len(by_part[k])}")


if __name__ == "__main__":
    main()
