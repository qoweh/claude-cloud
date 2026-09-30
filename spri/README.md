# SPRi(소프트웨어정책연구소) 자료 정리

[spri.kr](https://spri.kr/)에 올라온 간행물과 연구자료 가운데 **RAG, AI 에이전트 등 AI 서비스 개발을 공부하는 SW 전공자**에게 도움이 될 자료를 골라 정리한 디렉토리다.

**읽기는 [00_목차.md](00_목차.md)에서 시작한다.**

## 구성

| 파일 | 내용 |
|---|---|
| [00_목차.md](00_목차.md) | 전체 목차, 먼저 알아둘 점, 목적별로 골라 읽는 경로, 먼저 읽을 10편 |
| [01_생성형AI.md](01_생성형AI.md) ~ [08_서비스와_비즈니스.md](08_서비스와_비즈니스.md) | 본문 8개 부. 자료마다 3줄 요약, 추천 이유, 같이 볼 기사 |
| [부록A_기초자료.md](부록A_기초자료.md) | 2015~2021년 자료 중 지금도 쓸 만한 기초 자료 |
| [부록B_행사발표자료.md](부록B_행사발표자료.md) | 발표 슬라이드가 있는 2023년 이후 행사 |
| [부록C_기사색인.md](부록C_기사색인.md) | AI 브리프·매거진 기사를 부별로 나눈 색인 (스크립트로 생성) |
| `data/` | 수집한 전체 게시물 데이터 |
| `scripts/` | 수집·검색·색인 스크립트 |

## 데이터 (`data/`)

2026-09-30에 게시판 17개의 게시물 2,358건 전체를 수집했다.

| 파일 | 내용 |
|---|---|
| `boards.json` | 게시판 목록, 게시판별 페이지 수와 게시물 수 |
| `posts.json` | 게시판별 게시물 목록 (제목, 날짜, 분류, 보고서 번호, 저자, 태그, 조회수, 첨부 번호) |
| `posts.csv` | 게시물 한 건당 한 줄. 여러 게시판에 실린 글은 합치고 `boards` 열에 모두 적었다. 엑셀로 열어 보기 좋다 |
| `details.jsonl` | 게시물 상세 한 줄에 한 건: 정확한 날짜, 저자와 소속, 본문 앞 3,000자, 목차(AI 브리프·매거진 기사 제목), 첨부파일 |

첨부파일은 `https://spri.kr/download/<file_id>`로 받을 수 있다.

## 스크립트 (`scripts/`)

```bash
pip install requests beautifulsoup4 lxml

# 1. 전체 수집 (목록 약 20분 + 상세 약 25분)
python3 spri/scripts/crawl_spri.py --details --workers 3
python3 spri/scripts/crawl_spri.py --details-only --workers 3        # 끊긴 곳부터 상세만 이어받기
python3 spri/scripts/crawl_spri.py --max-pages 2 --details --details-limit 10   # 테스트

# 2. PDF 전문 검색 (PDF와 텍스트는 spri/cache/에 저장, 커밋하지 않음)
pip install pypdf cffi
python3 spri/scripts/pdf_text.py fetch --since 2023 --boards data_all,AI-Brief --workers 3
python3 spri/scripts/pdf_text.py fetch --ids 21804 --files 23864      # 특정 게시물, 매거진 기사별 PDF
python3 spri/scripts/pdf_text.py search "(?-i:RAG)|검색\s?증강" --context 2

# 3. 부록 C 기사 색인 다시 만들기
python3 spri/scripts/build_index.py
```

- `crawl_spri.py`는 요청 사이에 0.7초씩 쉬고(`--delay`), 상세는 `--workers`만큼 동시에 받는다. spri.kr이 가끔 연결을 끊지만 재시도로 처리된다.
- `pdf_text.py`는 각 게시물의 대표 PDF를 받아 텍스트로 바꾼다. 웹 본문은 요약만 있어서, 보고서 안쪽 장·절에 있는 주제(예: RAG)는 PDF 전문을 검색해야 찾을 수 있다. 시스템의 `cryptography` 패키지가 깨져 pypdf가 안 뜨면 `cffi`를 설치하면 된다.
- `build_index.py`에 부록 C의 부별 분류 규칙(키워드 정규식)이 있다.

## 게시판

`data_all`(연구자료 전체)은 아래 분류 5개와 산업연간보고서를 합친 것이다. `data_all&flg=1`은 여기에 매거진·AI 브리프·이전 간행물까지 더한 목록이다.

| 키 | 게시판 | 건수 | 비고 |
|---|---|---:|---|
| `data_all` | 연구자료 전체 | 1,339 | |
| `data_all\|research` | 연구보고서 | 194 | 번호 RE- |
| `data_all\|issue_reports` | 이슈리포트 | 235 | 번호 IS- |
| `data_all\|column` | SPRi칼럼 | 317 | |
| `data_all\|industry_trend` | 산업/정책 동향 | 481 | |
| `data_all\|ai_brief` | 기타자료 | 103 | AI 브리프 특집, 학술논문, 연구용역 등 |
| `data_all\|flg1` | 연구 (간행물 포함) | 1,582 | |
| `magazine` | 월간 SW중심사회 | 147 | 상세에 호별 기사 제목과 기사별 PDF |
| `AI-Brief` | 월간 AI 브리프 | 67 | 상세에 호별 기사 목차 |
| `annual_reports` | 산업연간보고서 | 9 | |
| `sw_reports` | 승인통계보고서 | 34 | 실태조사 등 |
| `archive` | 이전 간행물 | 29 | 옛 AI Brief 1~29호 (2019~2021) |
| `conference\|flg1` | 전체행사 | 284 | 컨퍼런스+포럼+세미나 |
| `conference` | 컨퍼런스 | 60 | |
| `forum` | 포럼 | 83 | 상세에 발표자료 |
| `speech` | 세미나 | 141 | |
| `notice` | 공지사항 | 458 | |

수집하지 않은 곳: `open_release`(정보공개)는 게시물이 없는 안내 페이지이고, `/pages/media`(미디어)는 외부 언론 보도 모음이다.

## 크롤러가 처리하는 사이트 구조

- 목록은 `.com_list_box` 안의 `li`만 읽는다. 모든 페이지 하단의 "개인정보처리방침" 링크(게시물 23713)가 게시물처럼 보이기 때문이다.
- 간행물 게시판은 제목이 표지 이미지의 `alt`에 있고, 날짜는 `2026년09월호`처럼 월까지만 있다. 정확한 날짜는 상세에서 채운다.
- 페이지 파라미터는 게시판마다 `data_page` 또는 `page`이다. 첫 페이지의 페이지 링크에서 이름과 마지막 번호를 읽는다.
- 첨부는 `file_down('번호')`, `/download/번호` 링크, `data-down` 속성(포럼 발표자료) 세 가지 형태로 나온다. `file_down(' 23065')`처럼 번호 앞에 공백이 있는 글도 있다.
- AI 브리프 목차는 2024년 이후 `▹ 기사`, 2023년과 옛 AI Brief는 `ㅇ 기사` 형식이다. 스페셜 호는 `1. 장 제목`만 있고, 2022년 호는 웹페이지에 섹션 이름만 있어 기사 목록이 없다.
- 매거진 옛 호는 `칼럼 / COLUMN / 기사 제목…`처럼 섹션 라벨 사이에 기사 제목이 있다.
- 2020년 무렵 매거진에서 옮겨 온 산업/정책 동향 글 일부는 본문이 이미지라 웹 본문이 "월간SW중심사회" 한 줄뿐이다. 내용은 첨부 PDF에 있다.
