# DD 질문서 작성 (DD Questionnaire)

## 목적
전체 DD 패키지와 비평 점수를 검토한 후, **미해결 이슈를 체계적으로 정리**하고 투자팀을 위한 **구조화된 DD 질문서**를 작성한다.

---

## Step 1. 미해결 이슈 목록화

분석 완료 후에도 남아 있는 모든 미해결 이슈를 식별한다:
- 에이전트가 채울 수 없었던 **데이터 공백**
- 여전히 **미검증 상태**인 주장
- 해소되지 않은 **모순**
- 추가 조사가 필요한 **리스크**

각 이슈에 대해 기록:
- 카테고리 (financial / market / legal / tech / team / strategic)
- 심각도 (critical / important / minor)
- 현재 파악된 내용 (what_we_know)
- 파악되지 않은 내용 (what_we_dont_know)

💡 팁: 비평 에이전트에서 7점 미만을 받은 기준과 리뷰 에이전트의 UNVERIFIED·CONTRADICTED 항목이 미해결 이슈의 주요 원천이다.

---

## Step 2. 구조화된 DD 질문서 작성

각 미해결 이슈에 대응하는 후속 질문을 설계한다:
- **질문**: 구체적이고 명확하게 — 하나의 이슈에 하나의 질문
- **대상**: 누가 답변해야 하는가 (경영진 / 법률 자문 / 감사인 / 기술팀 / 산업 전문가)
- **우선순위**: critical / important / nice_to_have
- **맥락**: 왜 이 질문이 중요한지 배경 설명
- **시나리오**: 좋은 답변 vs 나쁜 답변이 각각 어떤 모습인지 기술

💡 팁: 좋은 DD 질문은 "예/아니오"로 끝나지 않는다. 구체적 수치, 일정, 근거를 요구하는 질문이 투자 판단에 실질적으로 도움된다.

---

## Step 3. 후속 조치 제안

투자팀을 위한 다음 단계를 우선순위와 일정과 함께 제안한다:
- 즉시 확인 필요 사항 (1주 이내)
- 심화 조사 항목 (1개월 이내)
- 장기 모니터링 항목

---

## 전체 규칙

1. 모든 미해결 이슈를 빠짐없이 목록화 — 누락이 곧 리스크
2. 질문은 구체적이고 실행 가능해야 함 — 막연한 "더 알아봐 주세요" 금지
3. 좋은 답변/나쁜 답변 시나리오를 반드시 포함하여 투자팀이 답변을 즉시 평가 가능하게 함
4. 우선순위는 투자 논거에 미치는 영향도 기준으로 설정

---

## JSON Output Schema

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence overview of outstanding issues>",
  "unresolved_issues": [
    {
      "issue": "...",
      "category": "financial|market|legal|tech|team|strategic",
      "severity": "critical|important|minor",
      "what_we_know": "...",
      "what_we_dont_know": "..."
    }
  ],
  "dd_questionnaire": [
    {
      "question": "...",
      "target": "management|legal_counsel|auditor|technical_team|industry_expert",
      "priority": "critical|important|nice_to_have",
      "context": "...",
      "good_answer_scenario": "...",
      "bad_answer_scenario": "...",
      "related_issue": "..."
    }
  ],
  "next_steps": [
    {"action": "...", "priority": "...", "timeline": "..."}
  ]
}
