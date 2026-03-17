"""Phase 1 — Legal & Regulatory agent (investment + business risks)."""
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
    preprocessed = (state.get("preprocessed_docs") or {}).get("legal_regulatory")
    is_public = state.get("is_public", True)

    doc_note = build_doc_instructions(docs, agent_focus="legal", preprocessed_md_paths=preprocessed)

    if is_public is False:
        data_instructions = (
            "PRIVATE company. Call dart_list() for Korean regulatory filings/disclosures. "
            "Use web_search for litigation and regulatory actions. "
            "Use news_search for recent legal developments.\n"
        )
    else:
        data_instructions = (
            "Call dart_list() for Korean company filings/disclosures. "
            "Use web_search for litigation history, regulatory actions, and compliance. "
            "Use news_search for recent legal developments. "
            "Search patent database for IP disputes.\n"
        )

    user_message = (
        f"Company: {company}\nURL: {url}{doc_note}\n\n"
        "Conduct a thorough legal and regulatory analysis covering both investment "
        "structure risks and business regulatory risks.\n\n"
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
        agent_type="legal_regulatory",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("legal_regulatory"),
        max_iterations=calc_max_iterations(docs),
        language=state.get("language", "English"),
    )

    return {"legal_regulatory": result}
