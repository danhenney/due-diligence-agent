"""Phase 1 — Financial Analysis agent (5-year financials, ratios, valuation)."""
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
    preprocessed = (state.get("preprocessed_docs") or {}).get("financial_analysis")
    is_public = state.get("is_public", True)

    doc_note = build_doc_instructions(docs, agent_focus="financial", preprocessed_md_paths=preprocessed)

    if is_public is False:
        data_instructions = (
            "PRIVATE company — do NOT call yf_get_info/yf_get_financials/get_sec_filings.\n"
            f"1. Call dart_finstate('{company}'), dart_company('{company}'), dart_list('{company}').\n"
            "2. Extract uploaded docs for projections, rounds, valuations.\n"
            "3. Fill gaps with web_search/news_search. Flag estimated vs confirmed data.\n"
        )
    else:
        data_instructions = (
            "1. DART/SEC: dart_finstate() for Korean, get_sec_filings() for US companies.\n"
            "2. MARKET: yf_get_info(ticker), yf_get_financials(ticker, 'quarterly'), "
            "yf_get_analyst_data(ticker) for live data.\n"
            "3. COMPS: yf_get_info for 3-5 comparable companies.\n"
        )

    user_message = (
        f"Company: {company}\nURL: {url}{doc_note}\n\n"
        "Conduct a thorough financial analysis AND valuation of this company.\n\n"
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
        agent_type="financial_analysis",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("financial_analysis"),
        max_iterations=calc_max_iterations(docs),
        language=state.get("language", "English"),
    )

    return {"financial_analysis": result}
