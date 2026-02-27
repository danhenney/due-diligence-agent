"""Phase 3 Quality Checkpoint + Final Synthesis.

Two-pass orchestrator for the end of Phase 3:

  Pass 1 (no tools): Evaluate fact_checker and stress_test outputs.
                     Re-run weak agents (score < 0.65, max 2) with revision briefs.

  Pass 2 (with tools): Synthesize all 11 agent outputs, fill critical data gaps
                       via live tool calls, and produce a preliminary investment
                       recommendation for the Final Report agent.

Returns: revised phase-3 agent outputs (if any) + orchestrator_briefing dict.
"""
from __future__ import annotations

from agents.context import (
    slim_financial, slim_market, slim_legal, slim_management, slim_tech,
    slim_bull, slim_bear, slim_valuation, slim_red_flags,
    slim_verification, slim_stress, slim_completeness, compact,
)
from agents.orchestrator._check_base import (
    evaluate_phase, revise_agents, SYNTHESIS_SYSTEM_PROMPT,
)
from agents.base import run_agent
from tools.executor import get_tools_for_agent
from graph.state import DueDiligenceState


def _agent_map():
    from agents.phase3 import fact_checker, stress_test
    return {
        "fact_checker": (fact_checker.run, "verification"),
        "stress_test":  (stress_test.run,  "stress_test"),
        # completeness excluded — it reads all prior outputs; re-running after
        # revisions would need another full pass (handled by the synthesis step).
    }


AGENT_NAMES = ["fact_checker", "stress_test", "completeness"]


def _build_full_package(s: dict) -> str:
    return compact({
        "financial":    slim_financial(s.get("financial_report")),
        "market":       slim_market(s.get("market_report")),
        "legal":        slim_legal(s.get("legal_report")),
        "management":   slim_management(s.get("management_report")),
        "tech":         slim_tech(s.get("tech_report")),
        "bull_case":    slim_bull(s.get("bull_case")),
        "bear_case":    slim_bear(s.get("bear_case")),
        "valuation":    slim_valuation(s.get("valuation")),
        "red_flags":    slim_red_flags(s.get("red_flags")),
        "verification": slim_verification(s.get("verification")),
        "stress_test":  slim_stress(s.get("stress_test")),
        "completeness": slim_completeness(s.get("completeness")),
    })


def run(state: DueDiligenceState) -> dict:
    language = state.get("language", "English")
    working_state = dict(state)

    # ── Pass 1: Evaluate Phase 3 agents (no tools) ────────────────────────────
    p3_context = compact({
        "verification": slim_verification(state.get("verification")),
        "stress_test":  slim_stress(state.get("stress_test")),
        "completeness": slim_completeness(state.get("completeness")),
    })

    eval_result = evaluate_phase(
        state=working_state,
        agent_names=AGENT_NAMES,
        context=p3_context,
        phase_label="Phase 3 — Verification (fact checker, stress test, completeness)",
        language=language,
    )

    evaluations = eval_result.get("evaluations", [])

    # ── Revision loop ──────────────────────────────────────────────────────────
    state_updates = revise_agents(
        working_state=working_state,
        agent_map=_agent_map(),
        evaluations=evaluations,
        language=language,
    )

    # ── Pass 2: Synthesis with live tools ─────────────────────────────────────
    full_package = _build_full_package(working_state)

    revised_names = list(state_updates.keys())
    revision_note = (
        f"NOTE: The following Phase 3 agents were revised after quality review: "
        f"{', '.join(revised_names)}. Their updated outputs are reflected below.\n\n"
        if revised_names else ""
    )

    synthesis_msg = (
        f"Company: {state['company_name']}\n\n"
        f"{revision_note}"
        f"All Agent Outputs (all 11 agents, Phases 1–3):\n{full_package}\n\n"
        "As Investment Committee Director, produce the final synthesis briefing:\n"
        "1. Use your tools to fill any remaining critical data gaps "
        "(call yf_get_info for live price/market cap, news_search for recent events).\n"
        "2. Identify and resolve cross-agent inconsistencies.\n"
        "3. Highlight the most vs. least reliable findings.\n"
        "4. Render a decisive investment recommendation (INVEST / WATCH / PASS) "
        "with clear rationale. Do not default to WATCH — be specific about why.\n\n"
        "Return the specified JSON object."
    )

    synthesis_result = run_agent(
        agent_type="orchestrator",
        system_prompt=SYNTHESIS_SYSTEM_PROMPT,
        user_message=synthesis_msg,
        tools=get_tools_for_agent("orchestrator"),
        max_iterations=12,
        language=language,
    )

    # Attach evaluation metadata to the briefing
    synthesis_result["phase_quality_scores"] = {
        e["agent_name"]: {"score": e.get("score", 0.0), "key_gaps": e.get("key_gaps", [])}
        for e in evaluations
    }
    synthesis_result["agents_revised_in_phase3"] = revised_names

    state_updates["orchestrator_briefing"] = synthesis_result
    return state_updates
