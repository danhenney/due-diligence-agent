"""Phase 3 — Review Agent (source verification, accuracy, consistency)."""
from __future__ import annotations
from pathlib import Path

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import (
    slim_market_analysis, slim_competitor, slim_financial_analysis,
    slim_tech, slim_legal_regulatory, slim_team,
    slim_ra_synthesis, slim_risk_assessment, slim_strategic_insight, compact,
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
    })

    is_public = state.get("is_public", True)
    if is_public is False:
        verification_instructions = (
            "PRIVATE company — do NOT call yf_get_info/yf_get_financials.\n"
            "Verify via: dart_finstate() for financials, web/news for other claims.\n"
        )
    else:
        verification_instructions = (
            "Verify via: dart_finstate() for Korean financials, yf_get_info(ticker) "
            "for market data, news_search for recent events.\n"
        )

    user_message = (
        f"Company: {state['company_name']}\n\n"
        f"All Prior Research (Phase 1 + Phase 2):\n{all_context}\n\n"
        "Review and verify the most material claims from the research above.\n\n"
        f"{verification_instructions}\n"
        "SOURCE TRACKING: For every tool call that returns a URL or source_url, "
        "include it in your sources array.\n\n"
        "Return the specified JSON object."
    )

    if revision_brief:
        user_message += (
            f"\n\nREVISION REQUEST:\n{revision_brief}\n"
            "Please specifically address this feedback."
        )

    result = run_agent(
        agent_type="review_agent",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("review_agent"),
        language=state.get("language", "English"),
    )

    return {"review_result": result}
