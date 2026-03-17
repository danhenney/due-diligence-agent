from __future__ import annotations

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

    # ── Mode ──────────────────────────────────────────────────────────────
    mode: str                          # "due-diligence" | "industry-research" | "deep-dive" | "benchmark"
    vs_company: str | None             # benchmark mode only: comparison target

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
    industry_synthesis: dict | None    # industry-research mode only
    benchmark_synthesis: dict | None   # benchmark mode only

    # ── Phase 3 — Review & Critique ───────────────────────────────────────
    review_result: dict | None
    critique_result: dict | None      # contains 5 scores + total + feedback
    dd_questions: dict | None

    # ── Phase 4 — Output ──────────────────────────────────────────────────
    report_structure: dict | None
    final_report: str | None
    recommendation: str | None        # INVEST / WATCH / PASS

    # ── Phase 5 — Codex Verification (per-phase) ─────────────────────────
    verification_phase1: dict | None   # codex check after Phase 1
    verification_phase2: dict | None   # codex check after Phase 2
    verification_phase3: dict | None   # codex check after Phase 3
    verification_result: dict | None   # codex final check after Phase 4
    codex_retry_count: int             # per-phase retry tracker (resets each phase)

    # ── Cross-pollination (Smart Aggregator output) ───────────────────────
    settled_claims: list[str] | None  # facts all Phase 1 agents agree on
    phase1_tensions: list[str] | None # contradictions between Phase 1 agents
    phase1_gaps: list[str] | None     # important questions no agent answered

    # ── Feedback loop ─────────────────────────────────────────────────────
    phase1_context: str | None        # compact Phase 1 summary, built once
    feedback_loop_count: int          # starts 0, max 2
    weak_sections: list[str]          # agent names needing re-run

    # ── Human checkpoints ────────────────────────────────────────────────
    checkpoint_feedback: str | None   # user feedback from last checkpoint
    auto_approve: bool                # True = skip human checkpoints

    # ── Shared bookkeeping ────────────────────────────────────────────────
    messages: Annotated[list, add_messages]
    errors: Annotated[list[str], operator.add]
    current_phase: str
    language: str                     # "English" | "Korean"
