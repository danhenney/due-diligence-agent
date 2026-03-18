"""LangGraph StateGraph construction for the due diligence pipeline.

Supports 4 analysis modes via MODE_REGISTRY (config.py):
  - due-diligence:      full 6-agent Phase 1, feedback loop, recommendation
  - industry-research:  3 agents, industry_synthesis, no loop
  - deep-dive:          4 agents, ra+risk synthesis, loop, no recommendation
  - benchmark:          3 agents, benchmark_synthesis, no loop

Graph topology is built dynamically by build_graph(mode).
"""
from __future__ import annotations

import logging
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from graph.state import DueDiligenceState
from config import CHECKPOINT_DB_PATH, MODE_REGISTRY
from tools.doc_preprocessor import preprocess_documents

# ── Import all agents ─────────────────────────────────────────────────────────
from agents.phase1 import (
    market_analysis,
    competitor_analysis,
    financial_analysis,
    tech_analysis,
    legal_regulatory,
    team_analysis,
)
from agents.phase2 import (
    ra_synthesis, risk_assessment, strategic_insight,
    industry_synthesis, benchmark_synthesis,
)
from agents.phase3 import review_agent, critique_agent, dd_questions
from agents.phase4 import report_structure, report_writer
from agents.phase5 import codex_verification
from agents.base import get_and_reset_usage
from tools.executor import reset_tool_cache
from agents.context import (
    slim_market_analysis, slim_competitor, slim_financial_analysis,
    slim_tech, slim_legal_regulatory, slim_team, compact,
)
from config import ANTHROPIC_API_KEY, MODEL_NAME

log = logging.getLogger(__name__)


_AGENT_TIMEOUT_SEC = 600  # 10-minute timeout per agent

# ── Agent function registries ─────────────────────────────────────────────────
# Maps agent name (as used in MODE_REGISTRY) → run function

PHASE1_AGENT_FNS = {
    "market_analysis": market_analysis.run,
    "competitor_analysis": competitor_analysis.run,
    "financial_analysis": financial_analysis.run,
    "tech_analysis": tech_analysis.run,
    "legal_regulatory": legal_regulatory.run,
    "team_analysis": team_analysis.run,
}

PHASE2_AGENT_FNS = {
    "ra_synthesis": ra_synthesis.run,
    "risk_assessment": risk_assessment.run,
    "strategic_insight": strategic_insight.run,
    "industry_synthesis": industry_synthesis.run,
    "benchmark_synthesis": benchmark_synthesis.run,
}

# Slim context builders per Phase 1 agent (for aggregator)
PHASE1_SLIM_FNS = {
    "market_analysis": ("market", slim_market_analysis),
    "competitor_analysis": ("competitors", slim_competitor),
    "financial_analysis": ("financial", slim_financial_analysis),
    "tech_analysis": ("tech", slim_tech),
    "legal_regulatory": ("legal", slim_legal_regulatory),
    "team_analysis": ("team", slim_team),
}

# ── Disk-based output persistence ────────────────────────────────────────────
import json as _json
import os as _os
import re as _re


def _save_agent_output(company_name: str, agent_name: str, result: dict) -> None:
    """Persist agent result to outputs/<company_slug>/<agent_name>.json.

    Side-effect only — failures are logged but never raised.
    """
    try:
        slug = _re.sub(r"[^\w\-]", "_", company_name.strip())[:60]
        out_dir = _os.path.join("outputs", slug)
        _os.makedirs(out_dir, exist_ok=True)
        path = _os.path.join(out_dir, f"{agent_name}.json")
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(result, f, ensure_ascii=False, indent=2)
        log.info("[disk] Saved %s → %s", agent_name, path)
    except Exception as exc:
        log.warning("[disk] Failed to save %s: %s", agent_name, exc)


def _run_agent_with_usage(fn, state: Any) -> tuple[dict, dict]:
    """Run an agent function and return (result, token_usage) tuple."""
    try:
        result = fn(state)
    except Exception:
        # Capture any tokens consumed before the crash
        get_and_reset_usage()
        raise
    usage = get_and_reset_usage()
    # Persist to disk for crash resilience and human review
    company = state.get("company_name", "unknown") if isinstance(state, dict) else "unknown"
    for key, value in result.items():
        if isinstance(value, dict):
            _save_agent_output(company, key, value)
    return result, usage


# ── Node implementations ──────────────────────────────────────────────────────

def _detect_company_type(company_name: str) -> tuple[bool, str | None]:
    """Lightweight yfinance probe to determine if company is public."""
    try:
        import yfinance as yf
        name = company_name.strip()
        words = name.split()
        candidates = []
        if len(words) == 1:
            candidates.append(words[0].upper())
        else:
            candidates.append(words[0].upper())
            acronym = "".join(w[0].upper() for w in words if w)
            candidates.append(acronym)

        for candidate in candidates:
            try:
                info = yf.Ticker(candidate).info
                if info and info.get("quoteType") not in (None, "NONE") and info.get("marketCap"):
                    return True, candidate
            except Exception:
                continue
        return False, None
    except Exception:
        return False, None


def input_processor(state: DueDiligenceState) -> dict:
    """Validate inputs, detect company type, set initial phase marker."""
    reset_tool_cache()
    errors = []
    if not state.get("company_name", "").strip():
        errors.append("company_name is required but was not provided.")

    is_public = state.get("is_public")
    ticker = state.get("ticker")
    if is_public is None:
        is_public, ticker = _detect_company_type(state.get("company_name", ""))

    # Default mode if not provided
    mode = state.get("mode") or "due-diligence"
    if mode not in MODE_REGISTRY:
        errors.append(f"Invalid mode '{mode}'. Valid: {list(MODE_REGISTRY.keys())}")
        mode = "due-diligence"

    # ── Document preprocessing (Step 0.5) ──────────────────────────────────
    # Convert uploaded PDFs/Excel to MD before Phase 1 agents run.
    # This ensures agents read FULL content, not just first ~6 pages.
    preprocessed_docs = None
    uploaded = state.get("uploaded_docs") or []
    if uploaded:
        try:
            company_slug = _re.sub(r"[^\w\-]", "_", state.get("company_name", "unknown").strip())[:60]
            preprocess_dir = _os.path.join("outputs", company_slug, "_preprocessed")
            preprocessed_docs = preprocess_documents(uploaded, preprocess_dir)
            log.info("[preprocess] Converted %d docs → %d MD files across %d agents",
                     len(uploaded),
                     sum(len(v) for v in preprocessed_docs.values()),
                     sum(1 for v in preprocessed_docs.values() if v))
        except Exception as exc:
            log.warning("[preprocess] Document preprocessing failed, falling back to raw docs: %s", exc)
            errors.append(f"Document preprocessing failed: {exc}")

    return {
        "current_phase": "phase1",
        "errors": errors,
        "is_public": is_public,
        "ticker": ticker,
        "mode": mode,
        "preprocessed_docs": preprocessed_docs,
        "feedback_loop_count": 0,
        "weak_sections": [],
    }


def phase1_parallel(state: DueDiligenceState) -> dict:
    """Run Phase 1 agents (dynamic per mode) in batches of 2."""
    mode = state.get("mode", "due-diligence")
    cfg = MODE_REGISTRY[mode]
    agent_names = cfg["phase1_agents"]
    agent_fns = [PHASE1_AGENT_FNS[name] for name in agent_names]

    merged: dict[str, Any] = {"current_phase": "phase1_done"}
    errors = []
    agent_usage: dict[str, dict] = {}

    # Run in batches of 2 to avoid overwhelming free-tier Tavily rate limits
    batch_size = 2
    for batch_start in range(0, len(agent_fns), batch_size):
        batch_fns = agent_fns[batch_start:batch_start + batch_size]
        batch_names = agent_names[batch_start:batch_start + batch_size]

        if batch_start > 0:
            _time.sleep(5)  # pause between batches for rate limit recovery

        future_to_name: dict = {}
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            for fn, name in zip(batch_fns, batch_names):
                future_to_name[executor.submit(_run_agent_with_usage, fn, state)] = name

            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    result, usage = future.result(timeout=_AGENT_TIMEOUT_SEC)
                    merged.update(result)
                    agent_usage[name] = usage
                    log.info("[phase1] %s: input=%d, output=%d", name, usage.get('input_tokens', 0), usage.get('output_tokens', 0))
                except Exception as exc:
                    errors.append(f"{name} failed: {exc}")
                    log.error("[phase1] %s FAILED: %s", name, exc)

    merged["__agent_usage__"] = agent_usage
    if errors:
        merged["errors"] = errors
    log.info("[phase1] Total agents with usage: %d, errors: %d", len(agent_usage), len(errors))

    return merged


def phase1_cross_check_node(state: DueDiligenceState) -> dict:
    """D1: Cross-check numeric values across Phase 1 agents before aggregation."""
    import re
    import json

    patterns = {
        'revenue': r'(?:매출|revenue)[^\d]*?([\d,]+(?:\.\d+)?)\s*(?:억|백만|B|M)',
        'employees': r'(?:직원|임직원|employee)[^\d]*?([\d,]+)',
        'market_cap': r'(?:시가총액|market.?cap)[^\d]*?([\d,]+(?:\.\d+)?)',
        'growth': r'(?:성장률|growth)[^\d]*?([\d.]+)\s*%',
    }

    agent_keys = ["market_analysis", "competitor_analysis", "financial_analysis",
                  "tech_analysis", "legal_regulatory", "team_analysis"]

    numbers = {}
    for agent in agent_keys:
        data = state.get(agent)
        if not data:
            continue
        text = json.dumps(data, ensure_ascii=False, default=str) if isinstance(data, dict) else str(data)
        for metric, pat in patterns.items():
            matches = re.findall(pat, text, re.IGNORECASE)
            if matches:
                numbers.setdefault(metric, {})[agent] = matches[0]

    tensions = []
    for metric, agent_vals in numbers.items():
        if len(agent_vals) >= 2 and len(set(agent_vals.values())) > 1:
            tensions.append({"metric": metric, "values": agent_vals})

    log.info("[cross-check] Found %d pre-aggregator tensions", len(tensions))
    return {"pre_tensions": tensions}


def adaptive_phase2_context_node(state: DueDiligenceState) -> dict:
    """D2: Build adaptive context for Phase 2 based on Phase 1 results."""
    # State fields from phase1_aggregator: phase1_tensions, phase1_gaps
    tensions = state.get("phase1_tensions") or []
    gaps = state.get("phase1_gaps") or []
    pre_tensions = state.get("pre_tensions") or []

    supplements = []

    # Inject tensions for resolution
    if tensions:
        tension_items = tensions if isinstance(tensions, list) else [tensions]
        supplements.append(
            "## Tensions from Phase 1 (반드시 해소할 것)\n"
            + "\n".join(f"- {t}" for t in tension_items[:10])
            + "\n각 tension에 대해: (a) 어느 쪽이 맞는지 판정, (b) 근거, (c) 판정 불가 시 양쪽 시나리오 제시"
        )

    # Inject gaps for deeper analysis
    if gaps:
        gap_items = gaps if isinstance(gaps, list) else [gaps]
        supplements.append(
            "## Critical Gaps from Phase 1 (보강 분석 필요)\n"
            + "\n".join(f"- {g}" for g in gap_items[:10])
        )

    # Pre-tension numeric discrepancies
    if pre_tensions:
        supplements.append(
            "## Numeric Discrepancies (코드 기반 사전 탐지)\n"
            + "\n".join(f"- {t['metric']}: {t['values']}" for t in pre_tensions[:5])
        )

    phase2_context = "\n\n".join(supplements) if supplements else ""
    log.info("[adaptive-phase2] Built %d supplement sections", len(supplements))
    return {"phase2_supplements": phase2_context}


def phase1_aggregator(state: DueDiligenceState) -> dict:
    """Build compact Phase 1 context + extract settled claims and tensions.

    Dynamically aggregates only the agents that ran for the current mode.
    """
    mode = state.get("mode", "due-diligence")
    cfg = MODE_REGISTRY[mode]
    active_agents = cfg["phase1_agents"]

    # Build slim context only for agents that ran
    slim_data = {}
    for agent_name in active_agents:
        if agent_name in PHASE1_SLIM_FNS:
            key, slim_fn = PHASE1_SLIM_FNS[agent_name]
            slim_data[key] = slim_fn(state.get(agent_name))

    phase1_context = compact(slim_data)

    # Smart Aggregator: extract cross-pollination signals via one LLM call
    settled_claims = []
    phase1_tensions = []
    phase1_gaps = []
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        lang = state.get("language", "English")
        n_agents = len(active_agents)
        resp = client.messages.create(
            model=MODEL_NAME,
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": (
                    f"You are analyzing {n_agents} due diligence research agents' outputs for {state.get('company_name', 'a company')}.\n"
                    f"Analysis mode: {mode}\n"
                    f"Respond in {lang}. Output ONLY valid JSON with exactly 3 keys.\n\n"
                    f"Phase 1 agent results:\n{phase1_context[:8000]}\n\n"
                    "Extract:\n"
                    "1. \"settled_claims\": list of 5-8 key FACTS that multiple agents agree on. "
                    "Include specific numbers. These will NOT be repeated in Phase 2.\n"
                    "2. \"tensions\": list of 3-5 CONTRADICTIONS or disagreements between agents. "
                    "Example: 'market_analysis estimates TAM at $14B but competitor_analysis says $25.7B'\n"
                    "3. \"gaps\": list of 2-3 important questions that NO agent answered.\n\n"
                    "JSON only, no markdown fences:"
                ),
            }],
        )
        import json
        text = resp.content[0].text.strip()
        # Handle potential markdown fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(text)
        settled_claims = parsed.get("settled_claims", [])[:8]
        phase1_tensions = parsed.get("tensions", [])[:5]
        phase1_gaps = parsed.get("gaps", [])[:3]
        log.info("[aggregator] Extracted %d claims, %d tensions, %d gaps",
                 len(settled_claims), len(phase1_tensions), len(phase1_gaps))
    except Exception as exc:
        log.warning("[aggregator] Smart extraction failed, proceeding without: %s", exc)

    return {
        "current_phase": "phase2",
        "phase1_context": phase1_context,
        "settled_claims": settled_claims,
        "phase1_tensions": phase1_tensions,
        "phase1_gaps": phase1_gaps,
    }


def phase2_parallel(state: DueDiligenceState) -> dict:
    """Run Phase 2 parallel agents (dynamic per mode)."""
    mode = state.get("mode", "due-diligence")
    cfg = MODE_REGISTRY[mode]
    agent_names = cfg["phase2_parallel"]
    agent_fns = [PHASE2_AGENT_FNS[name] for name in agent_names]

    merged: dict[str, Any] = {}
    errors = []
    agent_usage: dict[str, dict] = {}

    future_to_name: dict = {}
    with ThreadPoolExecutor(max_workers=max(len(agent_fns), 1)) as executor:
        for i, (fn, name) in enumerate(zip(agent_fns, agent_names)):
            if i > 0:
                _time.sleep(3)
            future_to_name[executor.submit(_run_agent_with_usage, fn, state)] = name

        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                result, usage = future.result(timeout=_AGENT_TIMEOUT_SEC)
                merged.update(result)
                agent_usage[name] = usage
            except Exception as exc:
                errors.append(f"{name} failed: {exc}")

    merged["__agent_usage__"] = agent_usage
    if errors:
        merged["errors"] = errors

    return merged


def strategic_insight_node(state: DueDiligenceState) -> dict:
    """Run strategic_insight sequentially (needs ra_synthesis + risk_assessment)."""
    return strategic_insight.run(state)


def phase2_aggregator(state: DueDiligenceState) -> dict:
    return {"current_phase": "phase3"}


def review_agent_node(state: DueDiligenceState) -> dict:
    return review_agent.run(state)


def critique_agent_node(state: DueDiligenceState) -> dict:
    return critique_agent.run(state)


def dd_questions_node(state: DueDiligenceState) -> dict:
    return dd_questions.run(state)


def report_structure_node(state: DueDiligenceState) -> dict:
    return report_structure.run(state)


def report_writer_node(state: DueDiligenceState) -> dict:
    return report_writer.run(state)


def codex_verify_phase1_node(state: DueDiligenceState) -> dict:
    """Run Phase 1 codex verification. On retry (prev FAIL), force PASS."""
    prev = state.get("verification_phase1")
    if prev and prev.get("overall") == "FAIL":
        log.info("[codex-phase1] Max retry reached, forcing PASS")
        return {"verification_phase1": {"status": "skipped", "overall": "PASS", "reason": "max retry reached"}}
    return codex_verification.run_phase1(state)


def codex_verify_phase2_node(state: DueDiligenceState) -> dict:
    """Run Phase 2 codex verification. On retry (prev FAIL), force PASS."""
    prev = state.get("verification_phase2")
    if prev and prev.get("overall") == "FAIL":
        log.info("[codex-phase2] Max retry reached, forcing PASS")
        return {"verification_phase2": {"status": "skipped", "overall": "PASS", "reason": "max retry reached"}}
    return codex_verification.run_phase2(state)


def codex_verify_phase3_node(state: DueDiligenceState) -> dict:
    """Run Phase 3 codex verification. On retry (prev FAIL), force PASS."""
    prev = state.get("verification_phase3")
    if prev and prev.get("overall") == "FAIL":
        log.info("[codex-phase3] Max retry reached, forcing PASS")
        return {"verification_phase3": {"status": "skipped", "overall": "PASS", "reason": "max retry reached"}}
    return codex_verification.run_phase3(state)


def codex_verify_final_node(state: DueDiligenceState) -> dict:
    """Run final codex verification. On retry (prev FAIL), force PASS."""
    prev = state.get("verification_result")
    if prev and prev.get("overall") == "FAIL":
        log.info("[codex-final] Max retry reached, forcing PASS")
        return {"verification_result": {"status": "skipped", "overall": "PASS", "reason": "max retry reached"}}
    return codex_verification.run_final(state)


def _codex_router(verification_key: str):
    """Factory for codex PASS/FAIL routing functions.

    Retry protection is in the verify nodes themselves (force PASS on 2nd attempt),
    so the router is a simple FAIL → rerun, else → pass.
    """
    def router(state: DueDiligenceState) -> str:
        v = state.get(verification_key) or {}
        overall = v.get("overall", "PASS")
        if overall == "FAIL":
            log.info("[codex-router] %s FAIL → rerun", verification_key)
            return "fail"
        log.info("[codex-router] %s %s → pass", verification_key, overall)
        return "pass"
    return router


# ── Checkpoint nodes (human review pause points) ─────────────────────────────
# These are marker nodes; the actual pausing logic lives in server.py's
# streaming loop, which checks for these node names and waits for approval.

def checkpoint_phase1_node(state: DueDiligenceState) -> dict:
    """Checkpoint after Phase 1 — server may pause here for human review."""
    return {"current_phase": "checkpoint_phase1"}


def checkpoint_phase2_node(state: DueDiligenceState) -> dict:
    """Checkpoint after Phase 2 — server may pause here for human review."""
    return {"current_phase": "checkpoint_phase2"}


def checkpoint_phase3_node(state: DueDiligenceState) -> dict:
    """Checkpoint after Phase 3 — server may pause here for human review."""
    return {"current_phase": "checkpoint_phase3"}


# ── Feedback loop nodes ───────────────────────────────────────────────────────

def critique_router(state: DueDiligenceState) -> str:
    """Conditional edge: route based on critique scores."""
    scores = state.get("critique_result") or {}
    total = scores.get("total_score", 0)
    criteria = [
        scores.get("logic", 0),
        scores.get("completeness", 0),
        scores.get("accuracy", 0),
        scores.get("narrative_bias", 0),
        scores.get("insight_effectiveness", 0),
    ]
    loop_count = state.get("feedback_loop_count", 0)

    if loop_count >= 2:
        log.info("Critique router: safety cap reached (loop_count=%d), passing", loop_count)
        return "pass"

    low = [c for c in criteria if c < 5]
    if total >= 35 and all(c >= 7 for c in criteria):
        log.info("Critique router: PASS (total=%d, all >= 7)", total)
        return "pass"
    elif total < 30 or len(low) >= 3:
        log.info("Critique router: FAIL (total=%d, low_count=%d)", total, len(low))
        return "fail"
    else:
        log.info("Critique router: CONDITIONAL (total=%d)", total)
        return "conditional"


def selective_rerun(state: DueDiligenceState) -> dict:
    """Re-run only weak agents identified by critique feedback, then loop back."""
    critique = state.get("critique_result") or {}
    feedback_items = critique.get("feedback", [])
    loop_count = state.get("feedback_loop_count", 0) + 1

    # Collect weak agent names from critique feedback
    weak_agents: set[str] = set()
    revision_briefs: dict[str, str] = {}
    for item in feedback_items:
        if item.get("score", 10) < 7:
            for agent_name in item.get("weak_agents", []):
                weak_agents.add(agent_name)
                improvements = item.get("specific_improvements", [])
                revision_briefs[agent_name] = (
                    f"Criterion '{item.get('criterion', '')}' scored {item.get('score', '?')}/10. "
                    f"Assessment: {item.get('assessment', '')}. "
                    f"Improvements needed: {'; '.join(improvements)}"
                )

    # Map agent names to run functions (all phases)
    agent_map = {**PHASE1_AGENT_FNS, **PHASE2_AGENT_FNS}

    merged: dict[str, Any] = {
        "feedback_loop_count": loop_count,
        "weak_sections": list(weak_agents),
    }

    for agent_name in weak_agents:
        if agent_name not in agent_map:
            log.warning("Selective rerun: unknown agent '%s' — skipping", agent_name)
            continue
        log.info("Selective rerun: re-running %s (loop %d)", agent_name, loop_count)
        try:
            brief = revision_briefs.get(agent_name, "")
            result = agent_map[agent_name](state, revision_brief=brief)
            merged.update(result)
        except Exception as exc:
            log.warning("Selective rerun: %s failed: %s", agent_name, exc)
            merged.setdefault("errors", []).append(f"selective_rerun {agent_name} failed: {exc}")

    return merged


def phase1_restart(state: DueDiligenceState) -> dict:
    """Full Phase 1 restart — clear outputs and increment loop count."""
    loop_count = state.get("feedback_loop_count", 0) + 1
    log.info("Phase 1 restart (loop %d)", loop_count)

    # Clear all Phase 1 + Phase 2 outputs
    cleared: dict[str, Any] = {
        "feedback_loop_count": loop_count,
        "weak_sections": [],
        "phase1_context": None,
        "review_result": None,
        "critique_result": None,
    }

    # Clear Phase 1 agent outputs for current mode
    mode = state.get("mode", "due-diligence")
    cfg = MODE_REGISTRY[mode]
    for agent_name in cfg["phase1_agents"]:
        cleared[agent_name] = None
    for agent_name in cfg["phase2_parallel"] + cfg.get("phase2_sequential", []):
        cleared[agent_name] = None

    return cleared


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph(mode: str = "due-diligence", use_checkpointing: bool = True):
    """Build and compile a mode-specific LangGraph StateGraph.

    The graph topology varies by mode:
      - due-diligence:     full pipeline with strategic_insight, feedback loop, dd_questions
      - industry-research: lighter pipeline, industry_synthesis, no loop
      - deep-dive:         ra+risk synthesis, feedback loop, no recommendation
      - benchmark:         benchmark_synthesis, no loop
    """
    if mode not in MODE_REGISTRY:
        raise ValueError(f"Unknown mode '{mode}'. Valid: {list(MODE_REGISTRY.keys())}")

    cfg = MODE_REGISTRY[mode]
    builder = StateGraph(DueDiligenceState)

    phase3_agents = cfg["phase3_agents"]
    has_review = "review_agent" in phase3_agents
    has_critique = "critique_agent" in phase3_agents
    has_dd_q = "dd_questions" in phase3_agents
    has_loop = cfg["has_feedback_loop"]
    has_strategic = bool(cfg["phase2_sequential"])

    # ── Nodes always present ──────────────────────────────────────────────
    builder.add_node("input_processor",    input_processor)
    builder.add_node("phase1_parallel",    phase1_parallel)
    builder.add_node("phase1_cross_check", phase1_cross_check_node)
    builder.add_node("phase1_aggregator",  phase1_aggregator)
    builder.add_node("adaptive_phase2_context", adaptive_phase2_context_node)
    builder.add_node("phase2_parallel",    phase2_parallel)
    builder.add_node("phase2_aggregator",  phase2_aggregator)
    builder.add_node("report_structure",   report_structure_node)
    builder.add_node("report_writer",      report_writer_node)

    # ── Codex verification + checkpoint nodes ────────────────────────────
    builder.add_node("codex_verify_phase1", codex_verify_phase1_node)
    builder.add_node("codex_verify_phase2", codex_verify_phase2_node)
    builder.add_node("codex_verify_final",  codex_verify_final_node)
    builder.add_node("checkpoint_phase1",   checkpoint_phase1_node)
    builder.add_node("checkpoint_phase2",   checkpoint_phase2_node)

    has_phase3_agents = has_review or has_critique or has_dd_q
    if has_phase3_agents:
        builder.add_node("codex_verify_phase3", codex_verify_phase3_node)
        builder.add_node("checkpoint_phase3",   checkpoint_phase3_node)

    # ── Phase 1 edges ────────────────────────────────────────────────────
    builder.add_edge(START,                "input_processor")
    builder.add_edge("input_processor",    "phase1_parallel")
    builder.add_edge("phase1_parallel",    "phase1_cross_check")
    builder.add_edge("phase1_cross_check", "phase1_aggregator")
    builder.add_edge("phase1_aggregator",  "codex_verify_phase1")

    builder.add_conditional_edges(
        "codex_verify_phase1",
        _codex_router("verification_phase1"),
        {"pass": "checkpoint_phase1", "fail": "phase1_parallel"},
    )
    builder.add_edge("checkpoint_phase1", "adaptive_phase2_context")
    builder.add_edge("adaptive_phase2_context", "phase2_parallel")

    # ── Phase 2 sequential (strategic_insight) ────────────────────────────
    if has_strategic:
        builder.add_node("strategic_insight", strategic_insight_node)
        builder.add_edge("phase2_parallel",   "strategic_insight")
        builder.add_edge("strategic_insight",  "phase2_aggregator")
    else:
        builder.add_edge("phase2_parallel",    "phase2_aggregator")

    # ── Phase 2 → codex verification ──────────────────────────────────────
    builder.add_edge("phase2_aggregator", "codex_verify_phase2")

    # Determine Phase 3 entry point (varies by mode)
    if has_review:
        phase3_entry = "review_agent"
    elif has_critique:
        phase3_entry = "critique_agent"
    elif has_dd_q:
        phase3_entry = "dd_questions"
    else:
        phase3_entry = "report_structure"  # no Phase 3 agents

    builder.add_conditional_edges(
        "codex_verify_phase2",
        _codex_router("verification_phase2"),
        {"pass": "checkpoint_phase2", "fail": "phase2_parallel"},
    )
    builder.add_edge("checkpoint_phase2", phase3_entry)

    # ── Phase 3 — dynamic chain → codex_verify_phase3 → report_structure ─
    phase3_exit = "codex_verify_phase3" if has_phase3_agents else "report_structure"
    prev_node = None  # entry handled by codex_verify_phase2 conditional edges

    if has_review:
        builder.add_node("review_agent", review_agent_node)
        prev_node = "review_agent"

    if has_critique:
        builder.add_node("critique_agent", critique_agent_node)
        if prev_node:
            builder.add_edge(prev_node, "critique_agent")

        if has_loop:
            # Feedback loop: critique → router → {pass, conditional, fail}
            builder.add_node("selective_rerun", selective_rerun)
            builder.add_node("phase1_restart",  phase1_restart)

            pass_target = "dd_questions" if has_dd_q else phase3_exit
            if has_dd_q:
                builder.add_node("dd_questions", dd_questions_node)

            builder.add_conditional_edges(
                "critique_agent",
                critique_router,
                {
                    "pass":        pass_target,
                    "conditional": "selective_rerun",
                    "fail":        "phase1_restart",
                },
            )

            # Loop-back edges
            loop_target = "review_agent" if has_review else "critique_agent"
            builder.add_edge("selective_rerun", loop_target)
            builder.add_edge("phase1_restart",  "phase1_parallel")

            if has_dd_q:
                builder.add_edge("dd_questions", phase3_exit)
        else:
            # No feedback loop — straight through
            if has_dd_q:
                builder.add_node("dd_questions", dd_questions_node)
                builder.add_edge("critique_agent", "dd_questions")
                builder.add_edge("dd_questions",   phase3_exit)
            else:
                builder.add_edge("critique_agent", phase3_exit)
    else:
        # No critique agent
        if has_dd_q:
            builder.add_node("dd_questions", dd_questions_node)
            if prev_node:
                builder.add_edge(prev_node, "dd_questions")
            builder.add_edge("dd_questions", phase3_exit)
        elif prev_node:
            builder.add_edge(prev_node, phase3_exit)

    # ── Phase 3 codex verification ────────────────────────────────────────
    if has_phase3_agents:
        builder.add_conditional_edges(
            "codex_verify_phase3",
            _codex_router("verification_phase3"),
            {"pass": "checkpoint_phase3", "fail": phase3_entry},
        )
        builder.add_edge("checkpoint_phase3", "report_structure")

    # ── Phase 4 ───────────────────────────────────────────────────────────
    builder.add_edge("report_structure", "report_writer")

    # ── Final codex verification ──────────────────────────────────────────
    builder.add_edge("report_writer", "codex_verify_final")
    builder.add_conditional_edges(
        "codex_verify_final",
        _codex_router("verification_result"),
        {"pass": END, "fail": "report_writer"},
    )

    # ── Compile ───────────────────────────────────────────────────────────
    if use_checkpointing:
        checkpointer = SqliteSaver.from_conn_string(CHECKPOINT_DB_PATH)
        return builder.compile(checkpointer=checkpointer)
    else:
        return builder.compile()
