# 보고서 구조 설계 (Report Structure Design)

## 목적
종합 투자 실사 보고서(인쇄 시 20~30페이지 목표)의 구조를 설계한다.
**"읽는 사람이 6개 섹션을 순서대로 읽으면 투자 판단에 필요한 모든 정보를 얻는다"**가 핵심 원칙이다.

---

## Step 1. 6-섹션 프레임워크 확인

보고서는 반드시 아래 6개 섹션을 따른다:

### 섹션 1: 시장 및 산업 개괄
- 거시 환경 및 산업 지형
- TAM/SAM/SOM (구체적 금액 포함)
- 시장 CAGR, 트렌드, 성장 동인
- 지역별 기회 분석
- 규제 환경 개요
- 참고 에이전트: market_analysis, legal_regulatory (규제 맥락)

### 섹션 2: 타겟 개요 및 사업/제품 구조
- 회사 연혁, 미션, 주요 마일스톤
- 비즈니스 모델 및 수익 구조
- 제품/서비스 포트폴리오 및 기술 스택
- 핵심 기술 및 IP 평가
- **전용 소섹션**: 경영진 프로필 (이름이 언급된 모든 인물)
- 핵심 인물 리스크, 역량 공백, 조직 문화 시그널
- 참고 에이전트: tech_analysis, team_analysis

### 섹션 3: 성과 및 운영 지표
- 매출 추이 (5개년), 성장률, 계절성
- 수익성 지표 (매출총이익률/EBITDA/순이익률)
- 재무 건전성, 현금흐름 품질
- 핵심 재무 비율 vs 업계 벤치마크
- 참고 에이전트: financial_analysis

### 섹션 4: 경쟁 구도 및 포지셔닝
- **전체** 경쟁사 매트릭스 (재무 포함, 모든 경쟁사 포함)
- 시장 점유율 분석 및 추이
- 경쟁 우위 및 모트
- 경쟁 취약점
- 참고 에이전트: competitor_analysis

### 섹션 5: 재무 현황/전망 및 가치평가
- DCF 밸류에이션 (WACC 분해, 터미널 성장률 등 가정 완전 기술)
- 시장 기반 밸류에이션 (국내 AND 해외 비교 기업)
- 외부 밸류에이션 비교 (애널리스트, 투자 라운드, 제3자)
- 적정 가치 범위 (low/mid/high) 및 재무 전망
- 참고 에이전트: financial_analysis (valuation), ra_synthesis

### 섹션 6: 리스크 및 최종 의견/제언
- 리스크 매트릭스 (법적, 사업, 재무, 기술, 운영, 평판)
- **전용 소섹션**: 법률/규제 리스크 및 소송 (모든 건 개별 기재)
- 투자 구조 리스크
- INVEST/WATCH/PASS 추천 및 근거
- 핵심 조건, 모니터링 포인트, DD 질문서
- 참고 에이전트: risk_assessment, legal_regulatory, strategic_insight, dd_questions

💡 팁: 팀, 경쟁사, 법률/규제 내용은 반드시 각각 전용 섹션을 가져야 한다 — 짧은 언급으로 병합 금지.

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
