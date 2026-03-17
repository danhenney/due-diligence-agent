"""Phase 1 — Team Analysis agent (leadership profiles, capability analysis)."""
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
    preprocessed = (state.get("preprocessed_docs") or {}).get("team_analysis")
    is_public = state.get("is_public", True)

    if is_public is False:
        data_instructions = (
            "PRIVATE company — leadership info may be limited. "
            "Use web_search for leadership bios, LinkedIn profiles (via web), "
            "executive departures, and organizational news. "
            "Uploaded documents may contain team bios — extract ALL names and details.\n"
        )
    else:
        data_instructions = (
            "Use web_search for leadership bios, LinkedIn profiles (via web), "
            "executive departures, Glassdoor ratings, and organizational news. "
            "Use news_search for recent leadership changes and culture signals. "
            "Check proxy statements for compensation and insider ownership.\n"
        )

    doc_note = build_doc_instructions(docs, agent_focus="team", preprocessed_md_paths=preprocessed)

    user_message = (
        f"Company: {company}\nURL: {url}{doc_note}\n\n"
        "Conduct a thorough leadership and team analysis.\n\n"
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
        agent_type="team_analysis",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("team_analysis"),
        max_iterations=calc_max_iterations(docs),
        language=state.get("language", "English"),
    )

    return {"team_analysis": result}
