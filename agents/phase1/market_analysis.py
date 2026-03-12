"""Phase 1 — Market Analysis agent (TAM/SAM/SOM, CAGR, trends)."""
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
    is_public = state.get("is_public", True)

    if is_public is False:
        data_instructions = (
            "This is a PRIVATE company. Do NOT call yf_get_info — it will fail.\n"
            "Instead use web_search for market size estimates, industry reports, "
            "and competitor landscape data.\n"
        )
    else:
        data_instructions = (
            "LIVE DATA REQUIREMENT: Call yf_get_info(ticker) to get the company's "
            "current market cap and sector classification. Use web_search and news_search "
            "for market size estimates and industry reports. Use Google Trends for demand signals. "
            "Use FRED for macroeconomic context if relevant.\n"
        )

    doc_note = build_doc_instructions(docs, agent_focus="market")

    user_message = (
        f"Company: {company}\nURL: {url}{doc_note}\n\n"
        "Conduct a thorough market analysis covering TAM/SAM/SOM for ALL business lines.\n\n"
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
        agent_type="market_analysis",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("market_analysis"),
        max_iterations=calc_max_iterations(docs),
        language=state.get("language", "English"),
    )

    return {"market_analysis": result}
