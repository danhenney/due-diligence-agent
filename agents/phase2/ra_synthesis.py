"""Phase 2 — R&A Synthesis agent (core investment arguments + scorecard)."""
from __future__ import annotations
from pathlib import Path

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import (
    slim_market_analysis, slim_competitor, slim_financial_analysis,
    slim_tech, slim_legal_regulatory, slim_team, compact,
)
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = Path(__file__).with_suffix(".md").read_text(encoding="utf-8")


def run(state: DueDiligenceState, revision_brief: str | None = None) -> dict:
    phase1_context = state.get("phase1_context") or compact({
        "market": slim_market_analysis(state.get("market_analysis")),
        "competitors": slim_competitor(state.get("competitor_analysis")),
        "financial": slim_financial_analysis(state.get("financial_analysis")),
        "tech": slim_tech(state.get("tech_analysis")),
        "legal": slim_legal_regulatory(state.get("legal_regulatory")),
        "team": slim_team(state.get("team_analysis")),
    })

    # Build cross-pollination context from Smart Aggregator
    claims = state.get("settled_claims") or []
    tensions = state.get("phase1_tensions") or []
    gaps = state.get("phase1_gaps") or []
    cross_poll = ""
    if claims:
        cross_poll += "\n=== SETTLED CLAIMS (do NOT restate — build on these) ===\n" + "\n".join(f"- {c}" for c in claims)
    if tensions:
        cross_poll += "\n\n=== TENSIONS (resolve or explain these contradictions) ===\n" + "\n".join(f"- {t}" for t in tensions)
    if gaps:
        cross_poll += "\n\n=== GAPS (fill these if possible with tool calls) ===\n" + "\n".join(f"- {g}" for g in gaps)

    user_message = (
        f"Company: {state['company_name']}\n\n"
        f"Phase 1 Research Reports:\n{phase1_context}\n\n"
        + (f"{cross_poll}\n\n" if cross_poll else "") +
        "Synthesize all Phase 1 findings into core investment arguments and "
        "build the CDD/LDD/FDD attractiveness scorecard.\n\n"
        "SOURCE TRACKING: Include sources from Phase 1 data and any new tool calls.\n\n"
        "Return the specified JSON object."
    )

    if revision_brief:
        user_message += (
            f"\n\nREVISION REQUEST:\n{revision_brief}\n"
            "Please specifically address this feedback in your revised analysis."
        )

    result = run_agent(
        agent_type="ra_synthesis",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("ra_synthesis"),
        language=state.get("language", "English"),
    )

    return {"ra_synthesis": result}
