"""Phase 1 — Competitor Analysis agent (competitor ID, comparison matrix)."""
from __future__ import annotations
from pathlib import Path

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import build_doc_instructions, calc_max_iterations
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = Path(__file__).with_suffix(".md").read_text(encoding="utf-8")


def run(state: DueDiligenceState, revision_brief: str | None = None) -> dict:
    company = state["company_name"]
    url = state.get("company_url") or ""
    docs = state.get("uploaded_docs") or []
    preprocessed = (state.get("preprocessed_docs") or {}).get("competitor_analysis")
    is_public = state.get("is_public", True)

    if is_public is False:
        data_instructions = (
            "This is a PRIVATE company. Use web_search and news_search to identify "
            "competitors and their financial metrics. For public competitors, you CAN "
            "call yf_get_info to get their market cap and financials.\n"
        )
    else:
        data_instructions = (
            "LIVE DATA REQUIREMENT: Call yf_get_info(ticker) for both the target company "
            "and its public competitors to get current market caps and key metrics. "
            "Use web_search for competitive landscape reports and market share data. "
            "Use Google Trends to compare brand interest levels.\n"
        )

    doc_note = build_doc_instructions(docs, agent_focus="competitor", preprocessed_md_paths=preprocessed)

    user_message = (
        f"Company: {company}\nURL: {url}{doc_note}\n\n"
        "Identify and analyze ALL significant competitors across every business line. "
        "Build a comprehensive comparison matrix.\n\n"
        f"{data_instructions}\n"
        "SOURCE TRACKING: For every tool call that returns a URL or source_url, "
        "include it in your sources array. Each source needs label, url, and tool name.\n\n"
        "Return your findings as the specified JSON object."
    )

    if revision_brief:
        user_message += (
            f"\n\nREVISION REQUEST:\n{revision_brief}\n"
            "Please specifically address this feedback in your revised analysis."
        )

    result = run_agent(
        agent_type="competitor_analysis",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("competitor_analysis"),
        max_iterations=calc_max_iterations(docs),
        language=state.get("language", "English"),
    )

    return {"competitor_analysis": result}
