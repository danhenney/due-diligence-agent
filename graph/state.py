import operator
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages


class DueDiligenceState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────────────
    company_name: str
    company_url: str | None
    uploaded_docs: list[str]          # local file paths to PDFs

    # ── Phase 1 — parallel specialist outputs ──────────────────────────────
    financial_report: dict | None
    market_report: dict | None
    legal_report: dict | None
    management_report: dict | None
    tech_report: dict | None

    # ── Phase 2 — parallel synthesis outputs ───────────────────────────────
    bull_case: dict | None
    bear_case: dict | None
    valuation: dict | None
    red_flags: list[dict]

    # ── Phase 3 — sequential verification outputs ──────────────────────────
    verification: dict | None
    stress_test: dict | None
    completeness: dict | None

    # ── Phase 4 — final deliverable ────────────────────────────────────────
    final_report: str | None
    recommendation: str | None        # PASS / WATCH / INVEST

    # ── Shared bookkeeping ─────────────────────────────────────────────────
    messages: Annotated[list, add_messages]
    errors: Annotated[list[str], operator.add]
    current_phase: str
