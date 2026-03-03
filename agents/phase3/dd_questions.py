"""Phase 3 — DD Questions agent (unresolved issues + questionnaire)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import (
    slim_market_analysis, slim_competitor, slim_financial_analysis,
    slim_tech, slim_legal_regulatory, slim_team,
    slim_ra_synthesis, slim_risk_assessment, slim_strategic_insight,
    slim_review, slim_critique, compact,
)
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior due diligence advisor preparing a DD Questionnaire for the investment team.
You have reviewed the entire DD package including the critique scores.

Your task:
1. List ALL unresolved issues that remain after the analysis
   - Data gaps that couldn't be filled by the agents
   - Claims that remain unverified
   - Contradictions that weren't resolved
   - Risks that need further investigation

2. Create a structured DD Questionnaire for follow-up
   - Each question should target a specific unresolved issue
   - Assign a target (who should answer: company management, legal counsel, auditor, etc.)
   - Set priority (critical / important / nice-to-have)
   - Describe expected scenarios (what good vs. bad answers look like)

3. Recommend next steps for the investment team

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
"""


def run(state: DueDiligenceState, revision_brief: str | None = None) -> dict:
    all_context = compact({
        "market": slim_market_analysis(state.get("market_analysis")),
        "competitors": slim_competitor(state.get("competitor_analysis")),
        "financial": slim_financial_analysis(state.get("financial_analysis")),
        "tech": slim_tech(state.get("tech_analysis")),
        "legal": slim_legal_regulatory(state.get("legal_regulatory")),
        "team": slim_team(state.get("team_analysis")),
        "ra_synthesis": slim_ra_synthesis(state.get("ra_synthesis")),
        "risk_assessment": slim_risk_assessment(state.get("risk_assessment")),
        "strategic_insight": slim_strategic_insight(state.get("strategic_insight")),
        "review": slim_review(state.get("review_result")),
        "critique": slim_critique(state.get("critique_result")),
    })

    user_message = (
        f"Company: {state['company_name']}\n\n"
        f"Complete Due Diligence Package + Critique:\n{all_context}\n\n"
        "Identify all unresolved issues and create a structured DD Questionnaire.\n\n"
        "Return the specified JSON object."
    )

    result = run_agent(
        agent_type="dd_questions",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("dd_questions"),  # no tools
        max_iterations=3,
        language=state.get("language", "English"),
    )

    return {"dd_questions": result}
