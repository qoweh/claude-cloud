# SPRi(소프트웨어정책연구소) 자료 정리

[spri.kr](https://spri.kr/)에 올라온 간행물과 연구자료 중에서 **RAG, AI 에이전트 등 AI 서비스 개발을 공부하는 SW 전공자**에게 도움이 될 자료를 골라 정리하는 디렉토리다.

## 진행 단계

1. **목록 수집**: 전체 게시판과 게시물 목록(제목, 날짜, 링크)을 크롤링한다. `scripts/crawl_spri.py` → `data/`
2. **대목차 승인**: 수집한 목록을 대목차로 나눠 `00_목차_초안.md`에 정리하고 확인을 받는다.
3. **정리**: 승인된 목차대로 자료별 요약과 추천 이유를 쓴다.

## 크롤러 실행

```bash
pip install requests beautifulsoup4 lxml
python3 spri/scripts/crawl_spri.py                # 전체 수집
python3 spri/scripts/crawl_spri.py --max-pages 2  # 게시판당 2페이지만 (테스트)
```

## 지금까지 확인된 게시판

| 게시판 | URL |
|---|---|
| 매거진 | https://spri.kr/posts?code=magazine |
| AI 브리프 | https://spri.kr/posts?code=AI-Brief |
| 연구자료 전체 | https://spri.kr/posts?code=data_all |
| 연구보고서 | https://spri.kr/posts?code=data_all&board_type=research |
| 이슈리포트 | https://spri.kr/posts?code=data_all&board_type=issue_reports |
| 자문 (board_type=advice) | https://spri.kr/posts?code=data_all&board_type=advice |
