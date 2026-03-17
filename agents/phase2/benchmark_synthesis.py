"""Phase 2 — Benchmark Synthesis agent (benchmark mode)."""
from __future__ import annotations
from pathlib import Path

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import (
    slim_competitor, slim_financial_analysis, slim_tech, compact,
)
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = Path(__file__).with_suffix(".md").read_text(encoding="utf-8")


def run(state: DueDiligenceState, revision_brief: str | None = None) -> dict:
    phase1_context = state.get("phase1_context") or compact({
        "competitors": slim_competitor(state.get("competitor_analysis")),
        "financial": slim_financial_analysis(state.get("financial_analysis")),
        "tech": slim_tech(state.get("tech_analysis")),
    })

    # Cross-pollination from aggregator
    claims = state.get("settled_claims") or []
    tensions = state.get("phase1_tensions") or []
    gaps = state.get("phase1_gaps") or []
    cross_poll = ""
    if claims:
        cross_poll += "\n=== SETTLED CLAIMS (do NOT restate — build on these) ===\n" + "\n".join(f"- {c}" for c in claims)
    if tensions:
        cross_poll += "\n\n=== TENSIONS (resolve or explain these contradictions) ===\n" + "\n".join(f"- {t}" for t in tensions)
    if gaps:
        cross_poll += "\n\n=== GAPS (fill these if possible) ===\n" + "\n".join(f"- {g}" for g in gaps)

    vs_company = state.get("vs_company") or "industry average"

    user_message = (
        f"Company: {state['company_name']}\n"
        f"Benchmark Target: {vs_company}\n\n"
        f"Phase 1 Research Reports:\n{phase1_context}\n\n"
        + (f"{cross_poll}\n\n" if cross_poll else "") +
        f"Create a comprehensive benchmark comparison between {state['company_name']} and {vs_company}.\n"
        "Compare across financial performance, technology, market position, and operational efficiency.\n\n"
        "SOURCE TRACKING: Include sources from Phase 1 data.\n\n"
        "Return the specified JSON object."
    )

    if revision_brief:
        user_message += (
            f"\n\nREVISION REQUEST:\n{revision_brief}\n"
            "Please specifically address this feedback in your revised analysis."
        )

    result = run_agent(
        agent_type="benchmark_synthesis",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("benchmark_synthesis"),
        language=state.get("language", "English"),
    )

    return {"benchmark_synthesis": result}
