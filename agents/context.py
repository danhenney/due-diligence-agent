"""Compact context builders — reduce token usage across all agents."""
from __future__ import annotations

import json
from typing import Any

_SEP = (",", ":")  # no-whitespace JSON separators


def _pick(d: Any, *keys: str) -> dict:
    """Return only the specified keys from a report dict."""
    if not isinstance(d, dict):
        return {"data": str(d)[:500]} if d else {}
    result = {k: d[k] for k in keys if k in d}
    # Preserve raw text if no structured keys matched (agent didn't return JSON)
    if not result and "raw" in d:
        return {"raw_analysis": str(d["raw"])[:2000]}
    return result


def slim_sources(sources: Any, max_sources: int = 10) -> list[dict]:
    """Keep at most max_sources, retaining only label + url."""
    if not isinstance(sources, list):
        return []
    out = []
    for s in sources:
        if not isinstance(s, dict) or not s.get("url"):
            continue
        out.append({"label": s.get("label", ""), "url": s["url"]})
        if len(out) >= max_sources:
            break
    return out


# ── Phase 1 slim helpers ─────────────────────────────────────────────────────

def slim_market_analysis(r: Any) -> dict:
    d = _pick(r, "summary", "tam", "sam", "som", "cagr", "trends",
              "market_drivers", "red_flags", "strengths", "confidence_score", "sources")
    if "sources" in d:
        d["sources"] = slim_sources(d["sources"])
    return d

def slim_competitor(r: Any) -> dict:
    d = _pick(r, "summary", "competitors", "comparison_matrix",
              "market_share", "competitive_gaps", "red_flags", "strengths",
              "confidence_score", "sources")
    if "sources" in d:
        d["sources"] = slim_sources(d["sources"])
    return d

def slim_financial_analysis(r: Any) -> dict:
    d = _pick(r, "summary", "revenue_trend", "profitability", "balance_sheet",
              "cash_flow", "key_ratios", "valuation", "red_flags", "strengths",
              "confidence_score", "sources")
    if "sources" in d:
        d["sources"] = slim_sources(d["sources"])
    return d

def slim_tech(r: Any) -> dict:
    d = _pick(r, "summary", "core_technologies", "ip_patents",
              "tech_maturity", "competitive_comparison", "red_flags", "strengths",
              "confidence_score", "sources")
    if "sources" in d:
        d["sources"] = slim_sources(d["sources"])
    return d

def slim_legal_regulatory(r: Any) -> dict:
    d = _pick(r, "summary", "investment_structure_risks", "business_regulatory_risks",
              "litigation", "ip_risks", "red_flags", "strengths",
              "confidence_score", "sources")
    if "sources" in d:
        d["sources"] = slim_sources(d["sources"])
    return d

def slim_team(r: Any) -> dict:
    d = _pick(r, "summary", "leadership_profiles", "capability_assessment",
              "departure_history", "key_person_risk", "red_flags", "strengths",
              "confidence_score", "sources")
    if "sources" in d:
        d["sources"] = slim_sources(d["sources"])
    return d


# ── Phase 2 slim helpers ─────────────────────────────────────────────────────

def slim_ra_synthesis(r: Any) -> dict:
    d = _pick(r, "summary", "core_investment_arguments", "attractiveness_scorecard",
              "key_findings", "confidence_score", "sources")
    if "sources" in d:
        d["sources"] = slim_sources(d["sources"])
    return d

def slim_risk_assessment(r: Any) -> dict:
    d = _pick(r, "summary", "risk_matrix", "top_risks",
              "mitigation_strategies", "overall_risk_level",
              "confidence_score", "sources")
    if "sources" in d:
        d["sources"] = slim_sources(d["sources"])
    return d

def slim_strategic_insight(r: Any) -> dict:
    d = _pick(r, "summary", "recommendation", "rationale",
              "synergy_analysis", "key_conditions", "confidence_score", "sources")
    if "sources" in d:
        d["sources"] = slim_sources(d["sources"])
    return d


# ── Phase 3 slim helpers ─────────────────────────────────────────────────────

def slim_review(r: Any) -> dict:
    d = _pick(r, "summary", "verified_claims", "unverified_claims",
              "contradicted_claims", "accuracy_assessment",
              "confidence_score", "sources")
    if "sources" in d:
        d["sources"] = slim_sources(d["sources"])
    return d

def slim_critique(r: Any) -> dict:
    return _pick(r, "logic", "completeness", "accuracy",
                 "narrative_bias", "insight_effectiveness",
                 "total_score", "feedback", "summary")

def slim_dd_questions(r: Any) -> dict:
    return _pick(r, "unresolved_issues", "dd_questionnaire", "summary")


# ── Serializer ────────────────────────────────────────────────────────────────

def compact(data: Any) -> str:
    """Compact JSON — no indent, no extra whitespace. ~25% smaller than indent=2."""
    return json.dumps(data, separators=_SEP)
