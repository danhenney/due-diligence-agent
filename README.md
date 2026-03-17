# Due Diligence Agent

**AI 기반 모듈러 기업 분석 플랫폼** — 최대 16개 AI 에이전트가 4단계에 걸쳐 기업을 분석하고, 분석 모드에 따라 10~30+ 페이지 보고서를 자동 생성합니다.

---

## 핵심 특징

- **4가지 분석 모드** — 투자 실사, 산업 리서치, 딥다이브, 벤치마크 비교
- **MODE_REGISTRY 기반 동적 파이프라인** — 모드에 따라 에이전트 구성, 그래프 토폴로지, 피드백 루프가 자동 조정
- **교차 검증 (Cross-pollination)** — Phase 1 에이전트 간 합의/모순/갭을 자동 추출하여 Phase 2에 전달
- **자동 품질 관리** — Critique Agent가 5개 기준으로 채점, 기준 미달 시 자동 재분석
- **Human Checkpoint** — Phase 1, 2, 3 완료 후 사용자 검토/피드백/중단 선택 가능
- **3가지 실행 방식** — Streamlit Web UI, CLI, DD Local (Claude Code)

---

## 분석 모드

### 모드 비교표

| | `due-diligence` | `industry-research` | `deep-dive` | `benchmark` |
|---|---|---|---|---|
| **목적** | 투자 의사결정 지원 | 산업 구조/동향 파악 | 비투자 심층 분석 | 기업 간 비교 |
| **Phase 1 에이전트** | 6개 (전체) | 3개 | 4개 | 3개 |
| **Phase 2 종합** | R&A + Risk + Strategic | Industry Synthesis | R&A + Risk | Benchmark Synthesis |
| **피드백 루프** | O | X | O | X |
| **투자 추천** | O (INVEST/WATCH/PASS) | X | X | X |
| **보고서 섹션** | 6개 | 3개 | 4개 | 3개 |
| **예상 페이지** | 20~30p | 10~15p | 15~20p | 10~15p |
| **특수 옵션** | — | — | — | `--vs` 비교 대상 필수 |

### 모드별 에이전트 구성

```
due-diligence (투자 실사 — 풀 파이프라인)
─────────────────────────────────────────
Phase 1: market + competitor + financial + tech + legal + team (6개, 병렬)
Phase 2: ra_synthesis + risk_assessment (병렬) → strategic_insight (순차)
Phase 3: review_agent → critique_agent → [피드백 루프] → dd_questions
Phase 4: 6 section writers → report editor → PDF/PPTX/DOCX

industry-research (산업 리서치)
─────────────────────────────────────────
Phase 1: market + competitor + tech (3개, 병렬)
Phase 2: industry_synthesis
Phase 3: critique_agent (품질 검증만)
Phase 4: 3 section writers → report editor

deep-dive (비투자 심층 분석)
─────────────────────────────────────────
Phase 1: financial + tech + team + legal (4개, 병렬)
Phase 2: ra_synthesis + risk_assessment (병렬)
Phase 3: review_agent → critique_agent → [피드백 루프]
Phase 4: 4 section writers → report editor

benchmark (기업 비교)
─────────────────────────────────────────
Phase 1: competitor + financial + tech (3개, 병렬)
Phase 2: benchmark_synthesis (A사 vs B사 헤드투헤드)
Phase 3: critique_agent (품질 검증만)
Phase 4: 3 section writers → report editor
```

---

## 아키텍처

### 전체 파이프라인 흐름

```
START → input_processor (모드 검증, 기업 유형 탐지)
      ↓
Phase 1 — Research (모드별 3~6 에이전트, 병렬 실행)
  각 에이전트: 웹 검색 + 데이터 API + PDF 추출 → 구조화된 분석 결과
      ↓
Smart Aggregator — 교차 검증
  settled_claims (합의 사실) + tensions (모순점) + gaps (미답변 질문)
      ↓
  ═══ HUMAN CHECKPOINT 1 ═══
      ↓
Phase 2 — Synthesis (모드별 1~3 에이전트)
  Phase 1 결과 → 투자 논거/산업 구조/벤치마크 종합
  [due-diligence만] strategic_insight: 2~3개 투자 프레이밍 도출
      ↓
  ═══ HUMAN CHECKPOINT 2 ═══
      ↓
Phase 3 — Review & Quality Control
  review_agent: 주장 검증 (추가 검색)
  critique_agent: 5개 기준 채점 (논리/완전성/정확성/편향/통찰)
    ├─ PASS (total≥35, all≥7) → 다음 단계
    ├─ CONDITIONAL → 약한 에이전트만 재실행
    └─ FAIL → Phase 1 전체 재시작
  dd_questions: DD 질문서 생성
      ↓
  ═══ HUMAN CHECKPOINT 3 ═══
      ↓
Phase 4 — Report Generation
  report_structure → report_writer → PDF/PPTX/DOCX
      ↓
END
```

### 동적 그래프 구성 (`build_graph(mode)`)

`MODE_REGISTRY`(config.py)가 각 모드의 에이전트 구성을 정의하고, `build_graph(mode)`가 이를 읽어 LangGraph StateGraph를 동적으로 구성합니다.

```python
# config.py — 모드별 에이전트 배정
MODE_REGISTRY = {
    "due-diligence": {
        "phase1_agents": ["market_analysis", "competitor_analysis", ...],  # 6개
        "phase2_parallel": ["ra_synthesis", "risk_assessment"],
        "phase2_sequential": ["strategic_insight"],
        "phase3_agents": ["review_agent", "critique_agent", "dd_questions"],
        "has_feedback_loop": True,
        "has_recommendation": True,
    },
    "benchmark": {
        "phase1_agents": ["competitor_analysis", "financial_analysis", "tech_analysis"],
        "phase2_parallel": ["benchmark_synthesis"],
        "phase2_sequential": [],              # strategic_insight 없음
        "phase3_agents": ["critique_agent"],   # review, dd_questions 없음
        "has_feedback_loop": False,
        "has_recommendation": False,
    },
    ...
}

# workflow.py — 동적 그래프 빌드
graph = build_graph(mode="benchmark")  # 모드에 맞는 노드/엣지만 구성
```

**핵심 설계 원칙:**
- Phase 1/2 에이전트는 상태(state)에서 `mode`를 읽어 `MODE_REGISTRY`에 정의된 에이전트만 실행
- 그래프 토폴로지가 모드별로 다름 (예: benchmark는 strategic_insight 노드 자체가 없음)
- Phase 4 report_structure/report_writer는 모드에 맞는 리포트 유형과 섹션 수를 자동 적용

### 프로젝트 구조

```
due-diligence-agent/
├── config.py                    # MODE_REGISTRY, API 키, 모드 설정
├── main.py                      # CLI 엔트리포인트 (--mode, --vs)
├── server.py                    # FastAPI 서버
├── app.py                       # Streamlit 웹 UI (배포: ddagents.streamlit.app)
│
├── graph/
│   ├── state.py                 # DueDiligenceState (TypedDict)
│   └── workflow.py              # build_graph(mode) — 동적 LangGraph 구성
│
├── agents/
│   ├── base.py                  # run_agent() — Anthropic API 래퍼
│   ├── context.py               # slim_*/rich_* 컨텍스트 압축 함수
│   │
│   ├── phase1/                  # 리서치 에이전트 (각각 .py + .md 프롬프트)
│   │   ├── market_analysis      # 시장 규모, TAM/SAM/SOM, 트렌드
│   │   ├── competitor_analysis  # 경쟁사 분석, 포지셔닝, 모트
│   │   ├── financial_analysis   # 재무제표, 밸류에이션, 투자 라운드
│   │   ├── tech_analysis        # 기술 스택, 특허, GitHub
│   │   ├── legal_regulatory     # 법률, 규제, 거버넌스
│   │   └── team_analysis        # 리더십, 핵심인물 리스크
│   │
│   ├── phase2/                  # 종합 에이전트
│   │   ├── ra_synthesis         # R&A 종합 (투자 논거 + 스코어카드)
│   │   ├── risk_assessment      # 리스크 매트릭스 + 미해결 반론
│   │   ├── strategic_insight    # 투자 프레이밍 + 추천 (due-diligence only)
│   │   ├── industry_synthesis   # 산업 구조 종합 (industry-research only)
│   │   └── benchmark_synthesis  # 기업 비교 종합 (benchmark only)
│   │
│   ├── phase3/                  # 검증 에이전트
│   │   ├── review_agent         # 주장 검증 (웹 검색으로 재확인)
│   │   ├── critique_agent       # 5개 기준 품질 채점 (1~10)
│   │   └── dd_questions         # DD 질문서 생성
│   │
│   └── phase4/                  # 보고서 생성
│       ├── report_structure     # 보고서 목차 설계 (모드별 섹션 수)
│       └── report_writer        # 최종 보고서 작성 (모드별 프레이밍)
│
├── tools/
│   └── executor.py              # 에이전트별 도구 배정 + 실행 라우터
│
├── web/                         # FastAPI 프론트엔드
├── pdf_report.py                # PDF 생성 (한국어 폰트 지원)
├── pptx_report.py               # PPTX 생성
└── docx_report.py               # DOCX 생성
```

---

## 두 가지 실행 방식

| | API 버전 (Streamlit/CLI) | DD Local (`/dd-local`) |
|---|---|---|
| **비용** | 분석당 $1~5 (Anthropic API) | $0 (Claude Code 구독만) |
| **실행** | `streamlit run app.py` 또는 `python main.py` | Claude Code에서 `/dd-local 회사명` |
| **모델** | claude-sonnet-4-6 | claude-opus-4-6 (Claude Code) |
| **런타임** | ~45분~1.5시간 | ~1~2시간 |
| **필수 키** | ANTHROPIC_API_KEY + TAVILY_API_KEY | TAVILY_API_KEY만 |

---

## 설치 및 실행

### 사전 요구사항

- Python 3.10+
- Git

### API 버전 (Streamlit/CLI)

```bash
# 1. 클론
git clone https://github.com/d-biz-transformation/dd-web.git
cd dd-web

# 2. 의존성 설치
pip install -r requirements.txt

# 3. API 키 설정
cp .env.example .env
# .env 파일을 열어서 ANTHROPIC_API_KEY, TAVILY_API_KEY 입력

# 4a. Streamlit UI 실행
streamlit run app.py

# 4b. CLI 실행
python main.py --company "Apple" --url https://apple.com --mode due-diligence
```

### CLI 사용법

```bash
# 기본 투자 실사
python main.py -c "삼성전자" -u https://samsung.com

# 산업 리서치 모드
python main.py -c "AI Industry" --mode industry-research

# 딥다이브 (비투자 분석)
python main.py -c "카카오" -u https://kakaocorp.com --mode deep-dive

# 벤치마크 비교
python main.py -c "Upstage" -u https://upstage.ai --mode benchmark --vs "OpenAI"

# 비공개 기업 + 문서 첨부
python main.py -c "스타트업A" --private --docs report.pdf financials.xlsx

# 체크포인트 없이 실행
python main.py -c "Apple" -u https://apple.com --no-checkpoint
```

### Streamlit 배포

Streamlit Cloud에서 자동 배포: https://ddagents.streamlit.app/

Streamlit UI에서는 Analysis Mode 드롭다운으로 모드를 선택하고, benchmark 모드 시 Benchmark Target 입력란이 나타납니다.

---

## DD Local (Claude Code)

Claude Code 구독자를 위한 API 비용 없는 실행 방식입니다.

### 설치

```bash
# Claude Code 설치
npm install -g @anthropic-ai/claude-code

# .env에 TAVILY_API_KEY만 설정하면 사용 가능
```

### 사용법

```bash
claude

# 기본 (한국어 출력)
/dd-local 삼성전자 --url https://samsung.com

# 영어 출력
/dd-local Apple --url https://apple.com --lang English

# 문서 첨부
/dd-local 업스테이지 --url https://upstage.ai --docs report.pdf financials.xlsx
```

DD Local의 상세 문서는 [dd-local 레포](https://github.com/d-biz-transformation/dd-local)를 참조하세요.

---

## 에이전트 상세

### Phase 1 — Research (리서치)

| 에이전트 | 도구 | 분석 내용 |
|----------|------|-----------|
| market_analysis | Tavily(web+news), yfinance, Google Trends, PDF | TAM/SAM/SOM, CAGR, 성장 동인, 규제 환경 |
| competitor_analysis | Tavily(web), yfinance, PDF | 경쟁사 프로필, 시장점유율, KSF, 모트 평가 |
| financial_analysis | DART, SEC EDGAR, yfinance(info+financials+analyst), Tavily, PDF | 재무제표, 밸류에이션, 투자 라운드, DCF |
| tech_analysis | Tavily(web+news), GitHub, PatentsView, PDF | 기술 스택, 특허, R&D, 최신 제품 |
| legal_regulatory | DART, Tavily(web+news), PDF | 소송, 규제, IP, 거버넌스, ESG |
| team_analysis | Tavily(web), PDF | 리더십 프로필, 핵심인물 리스크, 조직 |

### Phase 2 — Synthesis (종합)

| 에이전트 | 모드 | 도구 | 역할 |
|----------|------|------|------|
| ra_synthesis | due-diligence, deep-dive | 없음 | 핵심 투자 논거 + CDD/LDD/FDD 스코어카드 |
| risk_assessment | due-diligence, deep-dive | Tavily(web+news) | 리스크 매트릭스 + 미해결 반론 (kill_potential) |
| strategic_insight | due-diligence only | 없음 | 2~3개 투자 프레이밍 → INVEST/WATCH/PASS |
| industry_synthesis | industry-research only | 없음 | Porter's 5 Forces, 밸류체인, 기술 트렌드 |
| benchmark_synthesis | benchmark only | 없음 | 재무/기술/시장 헤드투헤드 + 스코어카드 |

### Phase 3 — Quality Control (품질 관리)

| 에이전트 | 모드 | 도구 | 역할 |
|----------|------|------|------|
| review_agent | due-diligence, deep-dive | DART, Tavily, yfinance | 주장 검증, 반론 검색 |
| critique_agent | 전체 | 없음 | 5개 기준 채점 (logic, completeness, accuracy, narrative_bias, insight_effectiveness) |
| dd_questions | due-diligence only | 없음 | 미해결 이슈 + DD 질문서 |

### 피드백 루프 (due-diligence, deep-dive)

Critique Agent 채점 결과에 따라:
- **PASS** (total ≥ 35, 전체 ≥ 7) → Phase 4로 진행
- **CONDITIONAL** → 약한 에이전트만 재실행 후 재검토
- **FAIL** (total < 30 또는 3개 이상 < 5) → Phase 1 전체 재시작
- 최대 2회 루프 후 강제 진행 (비용 안전장치)

---

## 교차 검증 (Cross-pollination)

Phase 1 완료 후 Smart Aggregator가 6개(또는 3~4개) 에이전트 결과를 분석하여:

1. **Settled Claims** (합의 사실, 5~8개) — 여러 에이전트가 동의하는 데이터 포인트. Phase 2에서 반복하지 않음
2. **Tensions** (모순점, 3~5개) — 에이전트 간 상충하는 주장. Phase 2에서 해결 또는 설명 필요
3. **Gaps** (갭, 2~3개) — 어떤 에이전트도 답하지 못한 중요 질문. Phase 2에서 보충 시도

이 정보는 `_aggregator` 결과로 저장되어 Phase 2 모든 에이전트에 전달됩니다.

---

## API 키 가이드

| API | 용도 | 필수 여부 | 무료 여부 |
|-----|------|-----------|-----------|
| **Anthropic** | AI 에이전트 (API 버전) | API 버전 필수 | 유료 ($3/M input, $15/M output) |
| **Tavily** | 웹/뉴스 검색 | 전체 필수 | 1,000회/월 무료 |
| DART | 한국 기업 재무제표 | 선택 (한국 기업 권장) | 무료 |
| FRED | 거시경제 데이터 | 선택 | 무료 |
| GitHub | 오픈소스 리포 분석 | 선택 (60→5000 req/hr) | 무료 |
| PatentsView | 미국 특허 검색 | 선택 | 무료 |
| SEC EDGAR | 미국 상장사 공시 | 선택 (미국 기업) | 무료 |

```bash
# .env 예시
ANTHROPIC_API_KEY=sk-ant-...
TAVILY_API_KEY=tvly-...
DART_API_KEY=...          # 한국 기업 분석 시
FRED_API_KEY=...          # 거시경제 데이터
GITHUB_TOKEN=ghp_...      # GitHub API rate limit 향상
```

---

## 비용 관리

- **분석당 하드 캡**: `MAX_COST_PER_ANALYSIS = $7.00` (config.py)
- 예산 초과 시 피드백 루프 스킵, 파이프라인 조기 종료
- 일반적 비용:
  - due-diligence: $2~5
  - industry-research / benchmark: $1~2
  - deep-dive: $2~4

---

## 출력 형식

### API 버전 (Streamlit/CLI)

| 형식 | 설명 |
|------|------|
| PDF | 스타일링된 보고서 (한국어 폰트 지원) |
| PPTX | 프레젠테이션 슬라이드 |
| DOCX | 편집 가능한 Word 문서 |
| Markdown | 웹 UI 인라인 렌더링 |

### DD Local

```
dd-local-outputs/<회사명>/
  market_analysis.md         # Phase 1 에이전트 결과 (각각 .md)
  competitor_analysis.md
  financial_analysis.md
  tech_analysis.md
  legal_regulatory.md
  team_analysis.md
  _aggregator.md             # 교차 검증
  ra_synthesis.md            # Phase 2 종합
  risk_assessment.md
  strategic_insight.md
  review_agent.md            # Phase 3 검증
  critique_agent.md
  dd_questions.md
  _section_1~6.md            # Phase 4 보고서 섹션
  report.md                  # 최종 보고서 (Markdown)
  report.pdf                 # 최종 보고서 (PDF)
```

---

## 기술 스택

| 구성요소 | 기술 |
|----------|------|
| 오케스트레이션 | LangGraph (StateGraph + conditional edges) |
| LLM | Claude claude-sonnet-4-6 (API 버전) / Claude Opus 4.6 (DD Local) |
| 웹 UI | Streamlit |
| 서버 | FastAPI + SSE |
| 검색 | Tavily (web + news) |
| 재무 데이터 | yfinance, DART (OpenDartReader), SEC EDGAR |
| 기술 데이터 | GitHub API, PatentsView, Google Trends |
| 상태 관리 | SQLite checkpointing (LangGraph) |
| 스토리지 | Supabase (Streamlit Cloud 배포) |

---

## 라이선스

MIT
