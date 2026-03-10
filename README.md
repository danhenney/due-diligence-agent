# Due Diligence Agent

14개 AI 에이전트가 4단계에 걸쳐 기업을 분석하고, 30+ 페이지 투자 실사 보고서를 자동 생성합니다.

## 두 가지 실행 방식

| | API 버전 (Streamlit/CLI) | DD Local (`/dd-local`) |
|---|---|---|
| **비용** | 분석당 $1~5 (Anthropic API) | $0 (Claude Code 구독만) |
| **실행** | `streamlit run app.py` 또는 `python main.py` | Claude Code에서 `/dd-local 회사명` |
| **모델** | claude-sonnet-4-6 | claude-opus-4-6 (Claude Code) |
| **런타임** | ~45분~1.5시간 | ~1~2시간 |
| **필수 키** | ANTHROPIC_API_KEY + TAVILY_API_KEY | TAVILY_API_KEY만 |

---

## DD Local 설치 및 사용법

### 사전 요구사항

- [Claude Code](https://claude.ai/code) 구독 및 설치 (`npm install -g @anthropic-ai/claude-code`)
- Python 3.10+
- Git

### 설치

```bash
# 1. 레포 클론
git clone https://github.com/danhenney/due-diligence-agent.git
cd due-diligence-agent

# 2. API 키 설정
cp .env.example .env
# .env 파일을 열어서 TAVILY_API_KEY 입력 (필수)
# DART_API_KEY 입력 (한국 기업 분석 시 권장)

# 3. 설치 스크립트 실행
bash install-dd-local.sh
```

### 사용법

```bash
# Claude Code 실행
claude

# 기본 사용 (한국어 출력)
/dd-local 삼성전자 --url https://samsung.com

# 영어 출력
/dd-local Apple --url https://apple.com --lang English

# 문서 첨부 (PDF, Excel 지원)
/dd-local 업스테이지 --url https://upstage.ai --docs report.pdf financials.xlsx

# 여러 문서 첨부
/dd-local 카카오 --docs ir_deck.pdf audit_report.pdf projections.xlsx
```

### 출력 파일

분석 완료 후 `dd-local-outputs/<회사명>/` 디렉토리에 생성:

```
dd-local-outputs/Samsung/
  market_analysis.json     # 시장 분석
  competitor_analysis.json # 경쟁사 분석
  financial_analysis.json  # 재무 분석
  tech_analysis.json       # 기술 분석
  legal_regulatory.json    # 법률/규제 분석
  team_analysis.json       # 팀 분석
  _aggregator.json         # 교차 검증 (settled_claims, tensions, gaps)
  ra_synthesis.json        # R&A 종합
  risk_assessment.json     # 리스크 평가
  strategic_insight.json   # 전략적 통찰 + 투자 프레이밍
  review_agent.json        # 리뷰
  critique_agent.json      # 품질 평가 (5개 기준 1-10점)
  dd_questions.json        # DD 질문지
  _section_1~6.md          # 보고서 섹션
  report.md                # 최종 보고서 (Markdown)
  report.pdf               # 최종 보고서 (PDF, 한국어 폰트 지원)
```

### 업데이트

```bash
cd due-diligence-agent
git pull
bash install-dd-local.sh   # 스킬 파일 재복사
```

### SKILL.md 수정

로컬에서 `skills/dd-local/SKILL.md`를 수정한 후 설치 스크립트를 재실행하면 반영됩니다:

```bash
# 수정 후
bash install-dd-local.sh
```

---

## API 버전 (Streamlit/CLI)

### 로컬 실행

```bash
pip install -r requirements.txt
cp .env.example .env
# .env에 ANTHROPIC_API_KEY, TAVILY_API_KEY 입력

# Streamlit UI
streamlit run app.py

# CLI
python main.py --company "Apple" --url https://apple.com
```

### 배포

Streamlit Cloud에서 자동 배포: https://ddagents.streamlit.app/

---

## 파이프라인 구조

```
Phase 1 (6 agents, 병렬):
  market_analysis, competitor_analysis, financial_analysis
  tech_analysis, legal_regulatory, team_analysis
      ↓
  Smart Aggregator (교차 검증)
      ↓
Phase 2 (3 agents):
  ra_synthesis + risk_assessment (병렬) → strategic_insight (순차)
      ↓
Phase 3 (품질 관리):
  review_agent → critique_agent + dd_questions (병렬)
  ※ 품질 미달 시 자동 재실행 (피드백 루프)
      ↓
Phase 4 (보고서):
  6 section_writers (병렬) → report_editor → PDF
```

## API 키 가이드

| API | 용도 | 필수 여부 | 무료 여부 |
|-----|------|-----------|-----------|
| Tavily | 웹/뉴스 검색 | DD Local 필수 | 1000회/월 무료 |
| Anthropic | AI 에이전트 | API 버전 필수 | 유료 |
| DART | 한국 기업 재무제표 | 선택 (한국 기업 권장) | 무료 |
| FRED | 거시경제 데이터 | 선택 | 무료 |
| GitHub | 리포 분석 | 선택 | 무료 |

## 라이선스

MIT
