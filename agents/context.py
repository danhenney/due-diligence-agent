"""Compact context builders — reduce token usage across all agents."""
from __future__ import annotations

import json
from typing import Any

_SEP = (",", ":")  # no-whitespace JSON separators


def _pick(d: Any, *keys: str) -> dict:
    """Return only the specified keys from a report dict."""
    if not isinstance(d, dict):
        return {"data": str(d)[:500]} if d else {}
    return {k: d[k] for k in keys if k in d}


# ── Phase 1 slim helpers ───────────────────────────────────────────────────────

def slim_financial(r: Any) -> dict:
    return _pick(r, "summary", "revenue_trend", "profitability",
                 "key_ratios", "red_flags", "strengths", "confidence_score")

def slim_market(r: Any) -> dict:
    return _pick(r, "summary", "market_size", "competitive_landscape",
                 "barriers_to_entry", "red_flags", "strengths", "confidence_score")

def slim_legal(r: Any) -> dict:
    return _pick(r, "summary", "litigation", "regulatory",
                 "red_flags", "strengths", "confidence_score")

def slim_management(r: Any) -> dict:
    return _pick(r, "summary", "founders", "key_person_risk",
                 "team_gaps", "red_flags", "strengths", "confidence_score")

def slim_tech(r: Any) -> dict:
    return _pick(r, "summary", "technical_moat", "product_market_fit",
                 "technical_risks", "red_flags", "strengths", "confidence_score")


def slim_red_flags(flags: Any) -> list:
    """Keep first 10 non-full_report flags; only type/severity/description."""
    if not isinstance(flags, list):
        return []
    out = []
    for f in flags:
        if not isinstance(f, dict) or f.get("type") == "full_report":
            continue
        out.append({k: f[k] for k in ("type", "severity", "description") if k in f})
        if len(out) >= 10:
            break
    return out


# ── Phase 2 slim helpers ───────────────────────────────────────────────────────

def slim_bull(r: Any) -> dict:
    return _pick(r, "thesis_title", "core_thesis", "key_catalysts",
                 "upside_scenario", "confidence_score")

def slim_bear(r: Any) -> dict:
    return _pick(r, "bear_thesis_title", "core_bear_thesis", "key_risks",
                 "downside_scenario", "confidence_score")

def slim_valuation(r: Any) -> dict:
    return _pick(r, "summary", "fair_value_range", "upside_to_current",
                 "valuation_risks", "confidence_score")


# ── Phase 3 slim helpers ───────────────────────────────────────────────────────

def slim_verification(r: Any) -> dict:
    return _pick(r, "summary", "contradicted_claims", "unverified_claims",
                 "overall_factual_integrity", "confidence_score")

def slim_stress(r: Any) -> dict:
    return _pick(r, "summary", "scenarios", "stress_test_conclusion",
                 "key_vulnerabilities", "confidence_score")

def slim_completeness(r: Any) -> dict:
    return _pick(r, "summary", "coverage_scores", "coverage_gaps",
                 "decision_readiness", "overall_completeness_score")


# ── Orchestrator slim helper ───────────────────────────────────────────────────

def slim_orchestrator(r: Any) -> dict:
    return _pick(r, "cross_agent_inconsistencies", "critical_gaps_filled",
                 "overall_data_quality", "synthesis_guidance",
                 "orchestrator_recommendation", "recommendation_rationale",
                 "confidence_score")


# ── Serializer ─────────────────────────────────────────────────────────────────

def compact(data: Any) -> str:
    """Compact JSON — no indent, no extra whitespace. ~25% smaller than indent=2."""
    return json.dumps(data, separators=_SEP)
