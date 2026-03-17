"""Phase 4 — Report Writer agent (final polished report).

Mode-aware: builds context only from agents that ran, adapts report framing
(investment memo vs industry report vs benchmark comparison).
"""
from __future__ import annotations
from pathlib import Path

import json
from datetime import date

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import (
    rich_market_analysis, rich_competitor, rich_financial_analysis,
    rich_tech, rich_legal_regulatory, rich_team,
    rich_ra_synthesis, rich_risk_assessment, rich_strategic_insight,
    rich_review, rich_critique, rich_dd_questions,
    rich_industry_synthesis, rich_benchmark_synthesis, compact,
    _deep_trim,
)
from tools.executor import get_tools_for_agent
from config import MODE_REGISTRY

SYSTEM_PROMPT = Path(__file__).with_suffix(".md").read_text(encoding="utf-8")

# Maps agent/state key → rich function
_RICH_MAP = {
    "market_analysis": ("market", rich_market_analysis),
    "competitor_analysis": ("competitors", rich_competitor),
    "financial_analysis": ("financial", rich_financial_analysis),
    "tech_analysis": ("tech", rich_tech),
    "legal_regulatory": ("legal", rich_legal_regulatory),
    "team_analysis": ("team", rich_team),
    "ra_synthesis": ("ra_synthesis", rich_ra_synthesis),
    "risk_assessment": ("risk_assessment", rich_risk_assessment),
    "strategic_insight": ("strategic_insight", rich_strategic_insight),
    "review_result": ("review", rich_review),
    "critique_result": ("critique", rich_critique),
    "dd_questions": ("dd_questions", rich_dd_questions),
    "industry_synthesis": ("industry_synthesis", rich_industry_synthesis),
    "benchmark_synthesis": ("benchmark_synthesis", rich_benchmark_synthesis),
}

_REPORT_TYPES = {
    "due-diligence": "Due Diligence Report",
    "industry-research": "Industry Research Report",
    "deep-dive": "Deep Dive Analysis Report",
    "benchmark": "Benchmark Comparison Report",
    "custom": "Custom Analysis Report",
}

_MODE_INSTRUCTIONS = {
    "due-diligence": (
        "Write the complete Due Diligence Report as specified. Be thorough and detailed — "
        "include all specific numbers, data points, and evidence from the agent reports. "
        "Each section should have substantive depth, not just summaries. "
        "Follow the report structure provided. "
        "Conclude with the JSON recommendation block."
    ),
    "industry-research": (
        "Write the complete Industry Research Report. Focus on industry structure, dynamics, "
        "and strategic opportunities — NOT investment recommendations. "
        "Include all specific market data, competitive dynamics, and technology trends. "
        "Follow the report structure provided."
    ),
    "deep-dive": (
        "Write the complete Deep Dive Analysis Report. Provide comprehensive technical, "
        "financial, and operational analysis. Do NOT include investment recommendations. "
        "Include all specific numbers and evidence from the agent reports. "
        "Follow the report structure provided."
    ),
    "benchmark": (
        "Write the complete Benchmark Comparison Report. Focus on objective, data-driven "
        "comparison between the two companies across all dimensions. "
        "Use comparison tables extensively. Do NOT include investment recommendations. "
        "Follow the report structure provided."
    ),
    "custom": (
        "Write the complete analysis report based on the available agent outputs. "
        "Be thorough and detailed — include all specific numbers and evidence. "
        "Adapt the report structure to the agents that were included in this run. "
        "Follow the report structure provided."
    ),
}


def _build_mode_context(state: DueDiligenceState) -> dict:
    """Build rich context dict from agents that ran for the current mode."""
    mode = state.get("mode", "due-diligence")
    cfg = MODE_REGISTRY[mode]

    ctx = {}
    # Phase 1 agents
    for agent_name in cfg["phase1_agents"]:
        if agent_name in _RICH_MAP:
            key, fn = _RICH_MAP[agent_name]
            ctx[key] = fn(state.get(agent_name))

    # Phase 2 agents
    for agent_name in cfg["phase2_parallel"] + cfg.get("phase2_sequential", []):
        if agent_name in _RICH_MAP:
            key, fn = _RICH_MAP[agent_name]
            ctx[key] = fn(state.get(agent_name))

    # Phase 3 agents
    phase3_state_keys = {
        "review_agent": "review_result",
        "critique_agent": "critique_result",
        "dd_questions": "dd_questions",
    }
    for agent_name in cfg["phase3_agents"]:
        state_key = phase3_state_keys.get(agent_name, agent_name)
        if state_key in _RICH_MAP:
            key, fn = _RICH_MAP[state_key]
            ctx[key] = fn(state.get(state_key))

    return ctx


def _collect_all_sources(state: DueDiligenceState) -> list[dict]:
    """Deduplicate sources by URL from all agent reports."""
    mode = state.get("mode", "due-diligence")
    cfg = MODE_REGISTRY[mode]

    # Collect from all agents that ran
    report_keys = list(cfg["phase1_agents"])
    report_keys += cfg["phase2_parallel"] + cfg.get("phase2_sequential", [])
    # Add phase 3 state keys
    phase3_state_keys = {
        "review_agent": "review_result",
        "critique_agent": "critique_result",
        "dd_questions": "dd_questions",
    }
    for agent_name in cfg["phase3_agents"]:
        report_keys.append(phase3_state_keys.get(agent_name, agent_name))

    seen_urls: set[str] = set()
    all_sources: list[dict] = []
    for key in report_keys:
        report = state.get(key)
        if not isinstance(report, dict):
            continue
        for src in report.get("sources", []):
            if not isinstance(src, dict):
                continue
            url = src.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_sources.append({"label": src.get("label", ""), "url": url})
    return all_sources


def run(state: DueDiligenceState) -> dict:
    mode = state.get("mode", "due-diligence")
    cfg = MODE_REGISTRY[mode]
    # For thread-safe custom keys like "custom-abc123", look up "custom" fallback
    lookup_mode = "custom" if mode.startswith("custom") else mode
    report_type = _REPORT_TYPES.get(lookup_mode, "Analysis Report")

    full_package = compact(_build_mode_context(state))

    report_structure = state.get("report_structure") or {}
    if report_structure:
        structure_json = compact(_deep_trim(report_structure, max_str=400, max_list=8))
    else:
        structure_json = "No structure provided."

    today = date.today().isoformat()

    # Aggregated sources (cap at 20)
    all_sources = _collect_all_sources(state)[:20]
    sources_section = ""
    if all_sources:
        source_lines = "\n".join(
            f"[{i+1}] {s['label']} — {s['url']}" for i, s in enumerate(all_sources)
        )
        sources_section = (
            f"\nAGGREGATED SOURCES (use these for the Data Sources appendix "
            f"and inline [N] citations):\n{source_lines}\n\n"
        )

    is_public = state.get("is_public", True)
    private_disclaimer = ""
    if is_public is False:
        private_disclaimer = (
            "PRIVATE COMPANY DISCLAIMER: Include a disclaimer at the top of the memo "
            "stating: 'Note: This analysis covers a private company. Data is sourced from "
            "publicly available information and uploaded documents rather than audited SEC "
            "filings. Financial figures may be estimated.'\n\n"
        )

    # Benchmark mode: include vs_company context
    benchmark_note = ""
    if mode == "benchmark":
        vs = state.get("vs_company") or "industry average"
        benchmark_note = f"Benchmark Target: {vs}\n\n"

    write_instructions = _MODE_INSTRUCTIONS.get(lookup_mode, _MODE_INSTRUCTIONS["custom"])

    user_message = (
        f"Company: {state['company_name']}\n"
        f"Analysis Mode: {mode}\n"
        f"Report Type: {report_type}\n"
        f"Today's Date: {today}\n\n"
        f"{benchmark_note}"
        f"{private_disclaimer}"
        f"Report Structure:\n{structure_json}\n\n"
        f"{sources_section}"
        f"Full Analysis Package:\n{full_package}\n\n"
        f"{write_instructions}"
    )

    result = run_agent(
        agent_type="report_writer",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("report_writer"),  # no tools
        max_iterations=5,
        max_tokens=32000,
        language=state.get("language", "English"),
        return_raw_text=True,  # Don't parse as JSON — output is markdown
    )

    memo_text = result.get("raw", "")

    output: dict = {
        "final_report": memo_text,
        "current_phase": "complete",
    }

    # Only extract recommendation for modes that have one
    if cfg.get("has_recommendation"):
        output["recommendation"] = _extract_recommendation(memo_text)

    return output


def _extract_recommendation(text: str) -> str:
    """Pull INVEST / WATCH / PASS from the memo text."""
    import re

    m = re.search(r'\{"recommendation":\s*"(INVEST|WATCH|PASS)"', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    m = re.search(r'\*\*Recommendation:\*\*\s*(INVEST|WATCH|PASS)', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    m = re.search(r'###\s+.*?(INVEST|WATCH|PASS)', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    m = re.search(r'[Rr]ecommendation.{0,100}(INVEST|WATCH|PASS)', text)
    if m:
        return m.group(1).upper()

    return "WATCH"
