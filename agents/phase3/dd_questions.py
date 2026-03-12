"""Phase 3 — DD Questions agent (unresolved issues + questionnaire)."""
from __future__ import annotations
from pathlib import Path

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import (
    slim_market_analysis, slim_competitor, slim_financial_analysis,
    slim_tech, slim_legal_regulatory, slim_team,
    slim_ra_synthesis, slim_risk_assessment, slim_strategic_insight,
    slim_review, slim_critique, compact,
)
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = Path(__file__).with_suffix(".md").read_text(encoding="utf-8")


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
