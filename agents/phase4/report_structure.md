# 보고서 구조 설계 (Report Structure Design)

## 목적
분석 모드에 따라 적절한 보고서 구조를 설계한다.
**"읽는 사람이 섹션을 순서대로 읽으면 판단에 필요한 모든 정보를 얻는다"**가 핵심 원칙이다.

---

## Step 1. 모드별 섹션 프레임워크

**IMPORTANT:** Analysis Mode가 user message에 전달된다. 해당 모드의 프레임워크만 사용할 것.

---

### Mode: due-diligence (6 섹션, 20~30 페이지)

#### 섹션 1: 시장 및 산업 개괄
- 거시 환경 및 산업 지형
- TAM/SAM/SOM (구체적 금액 포함)
- 시장 CAGR, 트렌드, 성장 동인
- 지역별 기회 분석, 규제 환경 개요
- 참고 에이전트: market_analysis, legal_regulatory (규제 맥락)

#### 섹션 2: 타겟 개요 및 사업/제품 구조
- 비즈니스 모델 및 수익 구조, 제품/서비스 포트폴리오 및 기술 스택, IP
- **전용 소섹션**: 경영진 프로필 (이름이 언급된 모든 인물), 핵심 인물 리스크
- 참고 에이전트: tech_analysis, team_analysis

#### 섹션 3: 성과 및 운영 지표
- 매출 추이 (5개년), 수익성 지표, 재무 건전성, 현금흐름 품질, 핵심 비율 vs 업계 벤치마크
- 참고 에이전트: financial_analysis

#### 섹션 4: 경쟁 구도 및 포지셔닝
- **전체** 경쟁사 매트릭스, 시장 점유율 분석, 경쟁 우위/모트, 경쟁 취약점
- 참고 에이전트: competitor_analysis

#### 섹션 5: 재무 현황/전망 및 가치평가
- DCF, 비교법 (국내 AND 해외), 투자 라운드, 적정 가치 범위 (low/mid/high)
- 참고 에이전트: financial_analysis (valuation), ra_synthesis

#### 섹션 6: 리스크 및 최종 의견/제언
- 리스크 매트릭스, **전용 소섹션**: 법률/규제 리스크 및 소송
- INVEST/WATCH/PASS 추천 및 근거, 조건, 모니터링 포인트, DD 질문서
- 참고 에이전트: risk_assessment, legal_regulatory, strategic_insight, dd_questions

💡 팁: 팀, 경쟁사, 법률/규제 내용은 반드시 각각 전용 섹션을 가져야 한다 — 짧은 언급으로 병합 금지.

---

### Mode: industry-research (3 섹션, 10~15 페이지)

#### 섹션 1: 시장 구조 및 규모
- TAM/SAM, CAGR, 성장 동인, 규제 환경
- 지역별 시장 세분화, 산업 밸류체인, 진입 장벽
- 참고 에이전트: market_analysis, industry_synthesis

#### 섹션 2: 경쟁 구도 및 주요 플레이어
- 주요 플레이어 프로필 (전수), 시장점유율, KSF(핵심 성공 요인)
- 포지셔닝 맵, 경쟁 강도, 신규 진입자 동향
- 참고 에이전트: competitor_analysis, industry_synthesis

#### 섹션 3: 기술 동향 및 전망
- 핵심 기술 트렌드, 기술 성숙도, 파괴적 혁신 가능성
- R&D 투자 동향, 향후 3~5년 전망
- 참고 에이전트: tech_analysis, industry_synthesis

투자 추천(INVEST/WATCH/PASS) 없음. 산업 매력도를 HIGH/MEDIUM/LOW로 평가.

---

### Mode: deep-dive (4 섹션, 15~20 페이지)

#### 섹션 1: 기업 개요 및 사업 구조
- 사업 모델, 제품 라인업, 기술 스택, IP
- 경영진 프로필 (전원), 조직 구조
- 참고 에이전트: tech_analysis, team_analysis

#### 섹션 2: 재무 분석
- 매출/수익성, 재무상태표, 현금흐름, 비율 분석, 동종업계 비교
- 참고 에이전트: financial_analysis

#### 섹션 3: 법률/규제 분석
- 소송, 규제 준수, ESG, 지배구조, 라이선스
- 참고 에이전트: legal_regulatory

#### 섹션 4: 리스크 종합 및 시사점
- 리스크 매트릭스, 주요 리스크 심층 분석, 종합 시사점
- 참고 에이전트: risk_assessment, ra_synthesis, critique_result

투자 추천 없음. 기업 실체 파악 목적.

---

### Mode: benchmark (3 섹션, 10~15 페이지)

#### 섹션 1: 경쟁 포지션 비교
- 우리 vs 경쟁사 전수 비교, KSF별 점수표 (1-10)
- 강점/약점 매트릭스, 포지셔닝 맵
- 참고 에이전트: competitor_analysis, benchmark_synthesis

#### 섹션 2: 재무 벤치마크
- 매출/수익성/성장률 비교, 비율 분석 비교, 효율성 지표 비교
- 참고 에이전트: financial_analysis, benchmark_synthesis

#### 섹션 3: 기술 역량 비교 및 전략적 시사점
- 기술 스택 비교, R&D 효율성, IP 비교
- 전략적 시사점, 액션 아이템
- 참고 에이전트: tech_analysis, benchmark_synthesis

투자 추천 없음. 경쟁 포지션을 LEADING/ON_PAR/LAGGING으로 평가.

---

## Step 2. 섹션별 상세 설계

각 섹션에 대해 아래 항목을 명시한다:
- **정확한 제목 텍스트** (보고서 언어에 맞춰)
- **참고 에이전트 데이터** — 어떤 에이전트의 데이터가 투입되는지
- **핵심 데이터 포인트** — 반드시 포함되어야 할 수치와 분석
- **목표 페이지 수**
- **내러티브 아크** — 이 섹션이 전달하는 스토리는 무엇인가?

💡 팁: 내러티브 아크는 단순 데이터 나열이 아니라, "왜 이 정보가 투자 판단에 중요한가"를 독자에게 전달하는 논리 흐름이다.

---

## Step 3. Executive Summary 및 부록 설계

- **Executive Summary**: 핵심 포인트, 추천 프리뷰, 목표 분량
- **부록**: 리뷰 요약, 비평 점수, 출처 목록 등

---

## 전체 규칙

1. 6개 섹션 프레임워크를 정확히 따를 것
2. 팀·경쟁사·법률/규제는 전용 섹션 필수
3. 각 섹션의 내러티브 아크가 다른 섹션과 연결되어야 함
4. 총 20~30 페이지 목표 — 섹션별 페이지 배분이 합계에 맞아야 함

---

## JSON Output Schema

Return a JSON object with this exact structure:
{
  "report_title": "...",
  "table_of_contents": [
    {
      "section_number": "1",
      "heading": "...",
      "subheadings": ["..."],
      "source_agents": ["..."],
      "key_data_points": ["..."],
      "target_pages": 0,
      "narrative_arc": "..."
    }
  ],
  "executive_summary_outline": {
    "key_points": ["..."],
    "recommendation_preview": "...",
    "target_length": "..."
  },
  "appendix_sections": ["..."],
  "total_target_pages": 0,
  "design_notes": "..."
}
