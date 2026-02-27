"""LangGraph StateGraph construction for the due diligence pipeline."""
from __future__ import annotations

import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from graph.state import DueDiligenceState
from config import CHECKPOINT_DB_PATH

# ── Import all agents ─────────────────────────────────────────────────────────
from agents.phase1 import (
    financial_analyst,
    market_research,
    legal_risk,
    management_team,
    tech_product,
)
from agents.phase2 import bull_case, bear_case, valuation, red_flag
from agents.phase3 import fact_checker, stress_test, completeness
from agents.orchestrator import orchestrator
from agents.phase4 import final_report
from agents.base import get_and_reset_usage


def _run_agent_with_usage(fn, state: Any) -> tuple[dict, dict]:
    """Run an agent function and return (result, token_usage) tuple.

    Captures the thread-local usage counter so parallel phases can collect
    per-sub-agent token counts from their worker threads.
    """
    result = fn(state)
    usage = get_and_reset_usage()
    return result, usage


# ── Node implementations ──────────────────────────────────────────────────────

def input_processor(state: DueDiligenceState) -> dict:
    """Validate inputs and set initial phase marker."""
    errors = []
    if not state.get("company_name", "").strip():
        errors.append("company_name is required but was not provided.")
    return {
        "current_phase": "phase1",
        "errors": errors,
        "red_flags": [],
    }


def phase1_parallel(state: DueDiligenceState) -> dict:
    """Run all 5 Phase 1 agents concurrently using ThreadPoolExecutor."""
    agent_names = [
        "financial_analyst", "market_research", "legal_risk",
        "management_team", "tech_product",
    ]
    agent_fns = [
        financial_analyst.run,
        market_research.run,
        legal_risk.run,
        management_team.run,
        tech_product.run,
    ]

    merged: dict[str, Any] = {"current_phase": "phase1_done"}
    errors = []
    agent_usage: dict[str, dict] = {}

    # Stagger starts by 3 s to avoid all 5 agents hitting the API simultaneously
    # and triggering rate-limit backoffs that stack.
    future_to_name: dict = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for i, (fn, name) in enumerate(zip(agent_fns, agent_names)):
            if i > 0:
                _time.sleep(3)
            future_to_name[executor.submit(_run_agent_with_usage, fn, state)] = name

        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                result, usage = future.result()
                merged.update(result)
                agent_usage[name] = usage
            except Exception as exc:
                errors.append(f"{name} failed: {exc}")

    merged["__agent_usage__"] = agent_usage
    if errors:
        merged["errors"] = errors

    return merged


def phase1_aggregator(state: DueDiligenceState) -> dict:
    """Lightweight aggregator after phase 1 — just marks phase transition."""
    return {"current_phase": "phase2"}


def phase2_parallel(state: DueDiligenceState) -> dict:
    """Run all 4 Phase 2 agents concurrently using ThreadPoolExecutor."""
    agent_names = ["bull_case", "bear_case", "valuation", "red_flag"]
    agent_fns = [bull_case.run, bear_case.run, valuation.run, red_flag.run]

    merged: dict[str, Any] = {"current_phase": "phase2_done"}
    errors = []
    all_red_flags: list[dict] = list(state.get("red_flags") or [])
    agent_usage: dict[str, dict] = {}

    future_to_name: dict = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        for i, (fn, name) in enumerate(zip(agent_fns, agent_names)):
            if i > 0:
                _time.sleep(3)
            future_to_name[executor.submit(_run_agent_with_usage, fn, state)] = name

        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                result, usage = future.result()
                if "red_flags" in result:
                    all_red_flags.extend(result.pop("red_flags", []))
                merged.update(result)
                agent_usage[name] = usage
            except Exception as exc:
                errors.append(f"{name} failed: {exc}")

    merged["red_flags"] = all_red_flags
    merged["__agent_usage__"] = agent_usage
    if errors:
        merged["errors"] = errors

    return merged


def phase2_aggregator(state: DueDiligenceState) -> dict:
    return {"current_phase": "phase3"}


def fact_checker_node(state: DueDiligenceState) -> dict:
    return fact_checker.run(state)


def stress_test_node(state: DueDiligenceState) -> dict:
    return stress_test.run(state)


def completeness_node(state: DueDiligenceState) -> dict:
    return completeness.run(state)


def orchestrator_node(state: DueDiligenceState) -> dict:
    return orchestrator.run(state)


def final_report_node(state: DueDiligenceState) -> dict:
    return final_report.run(state)


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph(use_checkpointing: bool = True):
    """Build and compile the LangGraph StateGraph.

    Args:
        use_checkpointing: If True, attach a SQLite checkpointer for resumability.

    Returns:
        Compiled LangGraph app.
    """
    builder = StateGraph(DueDiligenceState)

    # Register nodes
    builder.add_node("input_processor", input_processor)
    builder.add_node("phase1_parallel", phase1_parallel)
    builder.add_node("phase1_aggregator", phase1_aggregator)
    builder.add_node("phase2_parallel", phase2_parallel)
    builder.add_node("phase2_aggregator", phase2_aggregator)
    builder.add_node("fact_checker", fact_checker_node)
    builder.add_node("stress_test", stress_test_node)
    builder.add_node("completeness", completeness_node)
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("final_report_agent", final_report_node)

    # Wire edges
    builder.add_edge(START, "input_processor")
    builder.add_edge("input_processor", "phase1_parallel")
    builder.add_edge("phase1_parallel", "phase1_aggregator")
    builder.add_edge("phase1_aggregator", "phase2_parallel")
    builder.add_edge("phase2_parallel", "phase2_aggregator")
    builder.add_edge("phase2_aggregator", "fact_checker")
    builder.add_edge("fact_checker", "stress_test")
    builder.add_edge("stress_test", "completeness")
    builder.add_edge("completeness", "orchestrator")
    builder.add_edge("orchestrator", "final_report_agent")
    builder.add_edge("final_report_agent", END)

    if use_checkpointing:
        checkpointer = SqliteSaver.from_conn_string(CHECKPOINT_DB_PATH)
        return builder.compile(checkpointer=checkpointer)
    else:
        return builder.compile()
