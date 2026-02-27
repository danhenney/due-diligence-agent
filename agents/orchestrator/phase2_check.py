"""Phase 2 Quality Checkpoint — evaluates and optionally revises Phase 2 agents.

Runs after phase2_aggregator. Scores bull_case, bear_case, and valuation.
Re-runs any agent scoring below 0.65 (up to 3) with a targeted revision
brief before Phase 3 (fact_checker) begins.

Note: red_flag is evaluated for quality scoring but excluded from revisions
because its state key (red_flags) uses operator.add list-append semantics
in LangGraph — re-running it would duplicate the flag list.
"""
from __future__ import annotations

from agents.context import (
    slim_bull, slim_bear, slim_valuation, slim_red_flags, compact,
)
from agents.orchestrator._check_base import evaluate_phase, revise_agents
from graph.state import DueDiligenceState


def _agent_map():
    from agents.phase2 import bull_case, bear_case, valuation
    return {
        "bull_case": (bull_case.run, "bull_case"),
        "bear_case": (bear_case.run, "bear_case"),
        "valuation": (valuation.run, "valuation"),
        # red_flag intentionally excluded — see module docstring
    }


AGENT_NAMES = ["bull_case", "bear_case", "valuation", "red_flag"]


def run(state: DueDiligenceState) -> dict:
    language = state.get("language", "English")
    working_state = dict(state)

    context = compact({
        "bull_case":  slim_bull(state.get("bull_case")),
        "bear_case":  slim_bear(state.get("bear_case")),
        "valuation":  slim_valuation(state.get("valuation")),
        "red_flags":  slim_red_flags(state.get("red_flags")),
    })

    # Pass 1 — evaluate (no tools)
    eval_result = evaluate_phase(
        state=working_state,
        agent_names=AGENT_NAMES,
        context=context,
        phase_label="Phase 2 — Analysis (bull case, bear case, valuation, red flags)",
        language=language,
    )

    evaluations = eval_result.get("evaluations", [])

    # Revision loop — re-run weak agents before Phase 3 sees their outputs
    state_updates = revise_agents(
        working_state=working_state,
        agent_map=_agent_map(),
        evaluations=evaluations,
        language=language,
    )

    return state_updates
