# SPRi(소프트웨어정책연구소) 자료 정리

[spri.kr](https://spri.kr/)에 올라온 간행물과 연구자료 중에서 **RAG, AI 에이전트 등 AI 서비스 개발을 공부하는 SW 전공자**에게 도움이 될 자료를 골라 정리하는 디렉토리다.

## 진행 단계

1. **수집**: 전체 게시판의 게시물 목록과 상세(날짜, 저자, 요약, 목차, 첨부)를 크롤링한다. `scripts/crawl_spri.py` → `data/`
2. **대목차 승인**: 수집한 자료를 주제별로 나눠 [`00_목차_초안.md`](00_목차_초안.md)에 정리하고 확인을 받는다. `scripts/find_topics.py`로 주제 후보를 뽑는다.
3. **정리**: 승인된 목차대로 자료별 요약과 추천 이유를 쓴다.

## 실행

```bash
pip install requests beautifulsoup4 lxml
python3 spri/scripts/crawl_spri.py --details --workers 3   # 목록 + 상세 전체 수집 (약 45분)
python3 spri/scripts/crawl_spri.py                 # 목록만 (약 20분)
python3 spri/scripts/crawl_spri.py --details-only --workers 3                  # 저장된 목록으로 상세만 (끊긴 곳부터 이어받음)
python3 spri/scripts/crawl_spri.py --details-only --workers 3 --refetch-empty  # 첨부가 빈 상세만 다시 받기
python3 spri/scripts/crawl_spri.py --max-pages 2 --details --details-limit 10   # 테스트
python3 spri/scripts/find_topics.py                # 주제별 후보 뽑기
```

요청 사이에 0.7초씩 쉰다(`--delay`). 상세는 `--workers`만큼 동시에 받는다(3이면 분당 약 100건). spri.kr이 가끔 연결을 끊지만 재시도로 처리된다.

## 데이터 파일 (`data/`)

| 파일 | 내용 |
|---|---|
| `boards.json` | 게시판 목록, 게시판별 페이지 수와 게시물 수 |
| `posts.json` | 게시판별 게시물 목록 (제목, 날짜, 분류, 보고서 번호, 저자, 태그, 조회수, 첨부 번호) |
| `posts.csv` | 게시물 한 건당 한 줄. 여러 게시판에 실린 글은 합치고 `boards` 열에 모두 적는다 |
| `details.jsonl` | 게시물 상세 한 줄에 한 건: 정확한 날짜, 저자와 소속, 본문 앞 3,000자, 목차, 첨부파일 |
| `details.csv` | 상세를 표로 펼친 것 |
| `topic_candidates.csv` | 주제 키워드가 걸린 글과 점수 |
| `topic_summary.md` | 주제별 건수, 상위 글, 주제에 걸린 AI 브리프·매거진 기사 |

첨부파일은 `https://spri.kr/download/<file_id>`로 받을 수 있다.

## 게시판

`data_all`(연구자료 전체)은 아래 분류 5개와 산업연간보고서를 합친 것이다. `data_all&flg=1`은 여기에 매거진·AI 브리프·이전 간행물까지 더한 목록이다.

| 키 | 게시판 | URL | 비고 |
|---|---|---|---|
| `data_all` | 연구자료 전체 | https://spri.kr/posts?code=data_all | |
| `data_all\|research` | 연구보고서 | https://spri.kr/posts?code=data_all&board_type=research | 번호 RE- |
| `data_all\|issue_reports` | 이슈리포트 | https://spri.kr/posts?code=data_all&board_type=issue_reports | 번호 IS- |
| `data_all\|column` | SPRi칼럼 | https://spri.kr/posts?code=data_all&board_type=column | |
| `data_all\|industry_trend` | 산업/정책 동향 | https://spri.kr/posts?code=data_all&board_type=industry_trend | |
| `data_all\|ai_brief` | 기타자료 | https://spri.kr/posts?code=data_all&board_type=ai_brief | AI 브리프 특집, 학술논문 등 |
| `data_all\|flg1` | 연구 (간행물 포함) | https://spri.kr/posts?code=data_all&flg=1 | |
| `magazine` | SW중심사회 (월간) | https://spri.kr/posts?code=magazine | 상세에 호별 기사 제목과 기사별 PDF |
| `AI-Brief` | AI 브리프 (월간) | https://spri.kr/posts?code=AI-Brief | 상세에 호별 기사 목차 |
| `annual_reports` | 산업연간보고서 | https://spri.kr/posts?code=annual_reports | |
| `sw_reports` | 승인통계보고서 | https://spri.kr/posts?code=sw_reports | 실태조사 등 |
| `archive` | 이전 간행물 | https://spri.kr/posts?code=archive | 옛 AI Brief 등 |
| `conference\|flg1` | 전체행사 | https://spri.kr/posts?code=conference&flg=1 | 컨퍼런스+포럼+세미나 |
| `conference` | 컨퍼런스 | https://spri.kr/posts?code=conference | |
| `forum` | 포럼 | https://spri.kr/posts?code=forum | 상세에 발표자료 |
| `speech` | 세미나 | https://spri.kr/posts?code=speech | |
| `notice` | 공지사항 | https://spri.kr/posts?code=notice | |

제외한 곳: `open_release`(정보공개)는 게시물이 없는 안내 페이지이고, `/pages/media`(미디어)는 외부 언론 보도 모음이라 수집하지 않는다. 예전 README에 있던 `board_type=advice`는 사이트에 없는 값이라 연구자료 전체가 그대로 나왔다.

## 크롤러가 처리하는 사이트 구조

- 목록은 `.com_list_box` 안의 `li`만 읽는다. 모든 페이지 하단의 "개인정보처리방침" 링크(게시물 23713)가 게시물처럼 보이기 때문이다.
- 간행물 게시판은 제목이 표지 이미지의 `alt`에 있고, 날짜는 `2026년09월호`처럼 월까지만 있다. 정확한 날짜는 상세에서 채운다.
- 페이지 파라미터는 게시판마다 `data_page` 또는 `page`이다. 첫 페이지의 페이지 링크에서 이름과 마지막 번호를 읽는다.
- 첨부는 `file_down('번호')`, `/download/번호` 링크, `data-down` 속성(포럼 발표자료) 세 가지 형태로 나온다. `file_down(' 23065')`처럼 번호 앞에 공백이 있는 글도 있다.
- 2020년 무렵 월간 SW중심사회에서 옮겨 온 산업/정책 동향 글 일부는 본문이 이미지라 본문 텍스트가 "월간SW중심사회" 한 줄뿐이다. 내용은 첨부 PDF에 있다.
