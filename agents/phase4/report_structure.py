"""Phase 4 — Report Structure agent (design TOC + draft structure).

Mode-aware: builds context only from agents that ran for the current mode.
"""
from __future__ import annotations
from pathlib import Path

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import (
    slim_market_analysis, slim_competitor, slim_financial_analysis,
    slim_tech, slim_legal_regulatory, slim_team,
    slim_ra_synthesis, slim_risk_assessment, slim_strategic_insight,
    slim_review, slim_critique, slim_dd_questions,
    slim_industry_synthesis, slim_benchmark_synthesis, compact,
)
from tools.executor import get_tools_for_agent
from config import MODE_REGISTRY

SYSTEM_PROMPT = Path(__file__).with_suffix(".md").read_text(encoding="utf-8")

# Maps agent/state key → slim function
_SLIM_MAP = {
    "market_analysis": ("market", slim_market_analysis),
    "competitor_analysis": ("competitors", slim_competitor),
    "financial_analysis": ("financial", slim_financial_analysis),
    "tech_analysis": ("tech", slim_tech),
    "legal_regulatory": ("legal", slim_legal_regulatory),
    "team_analysis": ("team", slim_team),
    "ra_synthesis": ("ra_synthesis", slim_ra_synthesis),
    "risk_assessment": ("risk_assessment", slim_risk_assessment),
    "strategic_insight": ("strategic_insight", slim_strategic_insight),
    "review_result": ("review", slim_review),
    "critique_result": ("critique", slim_critique),
    "dd_questions": ("dd_questions", slim_dd_questions),
    "industry_synthesis": ("industry_synthesis", slim_industry_synthesis),
    "benchmark_synthesis": ("benchmark_synthesis", slim_benchmark_synthesis),
}

# Report type descriptions per mode
_REPORT_TYPES = {
    "due-diligence": ("Due Diligence Report", 6, "20-30 pages"),
    "industry-research": ("Industry Research Report", 3, "10-15 pages"),
    "deep-dive": ("Deep Dive Analysis Report", 4, "15-20 pages"),
    "benchmark": ("Benchmark Comparison Report", 3, "10-15 pages"),
}


def _build_mode_context(state: DueDiligenceState) -> dict:
    """Build slim context dict from agents that ran for the current mode."""
    mode = state.get("mode", "due-diligence")
    cfg = MODE_REGISTRY[mode]

    ctx = {}
    # Phase 1 agents
    for agent_name in cfg["phase1_agents"]:
        if agent_name in _SLIM_MAP:
            key, fn = _SLIM_MAP[agent_name]
            ctx[key] = fn(state.get(agent_name))

    # Phase 2 agents
    for agent_name in cfg["phase2_parallel"] + cfg.get("phase2_sequential", []):
        if agent_name in _SLIM_MAP:
            key, fn = _SLIM_MAP[agent_name]
            ctx[key] = fn(state.get(agent_name))

    # Phase 3 agents
    phase3_state_keys = {
        "review_agent": "review_result",
        "critique_agent": "critique_result",
        "dd_questions": "dd_questions",
    }
    for agent_name in cfg["phase3_agents"]:
        state_key = phase3_state_keys.get(agent_name, agent_name)
        if state_key in _SLIM_MAP:
            key, fn = _SLIM_MAP[state_key]
            ctx[key] = fn(state.get(state_key))

    return ctx


def run(state: DueDiligenceState) -> dict:
    mode = state.get("mode", "due-diligence")
    cfg = MODE_REGISTRY[mode]
    report_type, n_sections, page_target = _REPORT_TYPES.get(
        mode, ("Analysis Report", cfg["phase4_sections"], "15-20 pages")
    )

    all_context = compact(_build_mode_context(state))

    recommendation = "N/A"
    if cfg.get("has_recommendation"):
        si = state.get("strategic_insight")
        if isinstance(si, dict):
            recommendation = si.get("recommendation", "UNKNOWN")

    user_message = (
        f"Company: {state['company_name']}\n"
        f"Analysis Mode: {mode}\n"
        f"Report Type: {report_type}\n"
        f"Preliminary Recommendation: {recommendation}\n\n"
        f"Analysis Package:\n{all_context}\n\n"
        f"Design the report structure for a {report_type} with {n_sections} sections. "
        f"Target {page_target} when printed.\n\n"
        "Return the specified JSON object."
    )

    result = run_agent(
        agent_type="report_structure",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("report_structure"),  # no tools
        max_iterations=3,
        language=state.get("language", "English"),
    )

    return {"report_structure": result}
