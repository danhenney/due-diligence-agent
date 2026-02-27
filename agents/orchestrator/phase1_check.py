"""Phase 1 Quality Checkpoint — evaluates and optionally revises Phase 1 agents.

Runs after phase1_aggregator. Scores financial_analyst, market_research,
legal_risk, management_team, and tech_product. Re-runs any agent scoring
below 0.65 (up to 3) with a targeted revision brief before Phase 2 begins.
"""
from __future__ import annotations

from agents.context import (
    slim_financial, slim_market, slim_legal, slim_management, slim_tech, compact,
)
from agents.orchestrator._check_base import evaluate_phase, revise_agents
from graph.state import DueDiligenceState


def _agent_map():
    from agents.phase1 import (
        financial_analyst, market_research, legal_risk, management_team, tech_product,
    )
    return {
        "financial_analyst": (financial_analyst.run, "financial_report"),
        "market_research":   (market_research.run,   "market_report"),
        "legal_risk":        (legal_risk.run,         "legal_report"),
        "management_team":   (management_team.run,    "management_report"),
        "tech_product":      (tech_product.run,       "tech_report"),
    }


AGENT_NAMES = [
    "financial_analyst", "market_research", "legal_risk",
    "management_team", "tech_product",
]


def run(state: DueDiligenceState) -> dict:
    language = state.get("language", "English")
    working_state = dict(state)

    context = compact({
        "financial":  slim_financial(state.get("financial_report")),
        "market":     slim_market(state.get("market_report")),
        "legal":      slim_legal(state.get("legal_report")),
        "management": slim_management(state.get("management_report")),
        "tech":       slim_tech(state.get("tech_report")),
    })

    # Pass 1 — evaluate (no tools)
    eval_result = evaluate_phase(
        state=working_state,
        agent_names=AGENT_NAMES,
        context=context,
        phase_label="Phase 1 — Research (financial, market, legal, management, tech)",
        language=language,
    )

    evaluations = eval_result.get("evaluations", [])

    # Revision loop — re-run weak agents before Phase 2 sees their outputs
    state_updates = revise_agents(
        working_state=working_state,
        agent_map=_agent_map(),
        evaluations=evaluations,
        language=language,
    )

    return state_updates  # may be empty dict if all agents passed
