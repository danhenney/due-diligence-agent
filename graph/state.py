import operator
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages


class DueDiligenceState(TypedDict):
    # ── Input ─────────────────────────────────────────────────────────────
    company_name: str
    company_url: str | None
    uploaded_docs: list[str]          # local file paths to PDFs
    is_public: bool | None            # True = public, False = private, None = unknown
    ticker: str | None                # resolved ticker symbol (public companies only)

    # ── Phase 1 — Research & Analysis (6 parallel agents) ─────────────────
    market_analysis: dict | None
    competitor_analysis: dict | None
    financial_analysis: dict | None
    tech_analysis: dict | None
    legal_regulatory: dict | None
    team_analysis: dict | None

    # ── Phase 2 — Synthesis ───────────────────────────────────────────────
    ra_synthesis: dict | None
    risk_assessment: dict | None
    strategic_insight: dict | None

    # ── Phase 3 — Review & Critique ───────────────────────────────────────
    review_result: dict | None
    critique_result: dict | None      # contains 5 scores + total + feedback
    dd_questions: dict | None

    # ── Phase 4 — Output ──────────────────────────────────────────────────
    report_structure: dict | None
    final_report: str | None
    recommendation: str | None        # INVEST / WATCH / PASS

    # ── Feedback loop ─────────────────────────────────────────────────────
    phase1_context: str | None        # compact Phase 1 summary, built once
    feedback_loop_count: int          # starts 0, max 2
    weak_sections: list[str]          # agent names needing re-run

    # ── Shared bookkeeping ────────────────────────────────────────────────
    messages: Annotated[list, add_messages]
    errors: Annotated[list[str], operator.add]
    current_phase: str
    language: str                     # "English" | "Korean"
