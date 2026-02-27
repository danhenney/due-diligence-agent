"""Conditional edge logic for the LangGraph workflow."""
from __future__ import annotations

from graph.state import DueDiligenceState


def should_proceed_to_phase2(state: DueDiligenceState) -> str:
    """After phase1_aggregator, always proceed to phase 2."""
    return "phase2_aggregator_entry"


def should_proceed_to_phase3(state: DueDiligenceState) -> str:
    """After phase2_aggregator, always proceed to phase 3."""
    return "fact_checker"


def after_fact_checker(state: DueDiligenceState) -> str:
    return "stress_test"


def after_stress_test(state: DueDiligenceState) -> str:
    return "completeness"


def after_completeness(state: DueDiligenceState) -> str:
    return "final_report_agent"
