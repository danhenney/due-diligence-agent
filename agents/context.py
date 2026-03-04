"""Compact context builders — reduce token usage across all agents.

Design principle: MAX_TOKENS stays high (16000) so individual agents
(especially Korean) never get truncated.  These slim_* functions then
aggressively compress each agent's output so the COMBINED context for
downstream agents (review, report_writer) stays well under 200K tokens.

Token budget:  ~60K for all agent outputs combined → ~4-5K per agent.
"""
from __future__ import annotations

import json
from typing import Any

_SEP = (",", ":")  # no-whitespace JSON separators

# ── Core helpers ─────────────────────────────────────────────────────────────

def _deep_trim(obj: Any, max_str: int = 300, max_list: int = 3) -> Any:
    """Recursively trim all strings and lists in a nested structure."""
    if isinstance(obj, str):
        return obj[:max_str] + "…" if len(obj) > max_str else obj
    if isinstance(obj, list):
        return [_deep_trim(item, max_str, max_list) for item in obj[:max_list]]
    if isinstance(obj, dict):
        return {k: _deep_trim(v, max_str, max_list) for k, v in obj.items()}
    return obj


def _pick(d: Any, *keys: str) -> dict:
    """Return only the specified keys from a report dict, deep-trimmed."""
    if not isinstance(d, dict):
        return {"data": str(d)[:500]} if d else {}
    result = {k: d[k] for k in keys if k in d}
    # Preserve raw text if no structured keys matched (agent didn't return JSON)
    if not result and "raw" in d:
        return {"raw_analysis": str(d["raw"])[:1500]}
    return _deep_trim(result)


def slim_sources(sources: Any, max_sources: int = 3) -> list[dict]:
    """Keep at most max_sources, retaining only label + url."""
    if not isinstance(sources, list):
        return []
    out = []
    for s in sources:
        if not isinstance(s, dict) or not s.get("url"):
            continue
        out.append({"label": s.get("label", "")[:80], "url": s["url"]})
        if len(out) >= max_sources:
            break
    return out


# ── Phase 1 slim helpers ─────────────────────────────────────────────────────
# Each Phase 1 agent can output up to 16K tokens.  We keep only the summary
# (capped at 800 chars) plus 2-3 key structured fields.  Sources are stripped
# here — report_writer collects them separately via _collect_all_sources().

def slim_market_analysis(r: Any) -> dict:
    d = _pick(r, "summary", "tam", "cagr",
              "red_flags", "strengths", "confidence_score")
    if "summary" in d:
        d["summary"] = _deep_trim(d["summary"], max_str=800)
    return d

def slim_competitor(r: Any) -> dict:
    d = _pick(r, "summary", "competitors",
              "red_flags", "strengths", "confidence_score")
    return d

def slim_financial_analysis(r: Any) -> dict:
    d = _pick(r, "summary", "revenue_trend", "profitability",
              "red_flags", "strengths", "confidence_score")
    return d

def slim_tech(r: Any) -> dict:
    d = _pick(r, "summary", "core_technologies",
              "red_flags", "strengths", "confidence_score")
    return d

def slim_legal_regulatory(r: Any) -> dict:
    d = _pick(r, "summary", "red_flags", "strengths", "confidence_score")
    return d

def slim_team(r: Any) -> dict:
    d = _pick(r, "summary", "key_person_risk",
              "red_flags", "strengths", "confidence_score")
    return d


# ── Phase 2 slim helpers ─────────────────────────────────────────────────────

def slim_ra_synthesis(r: Any) -> dict:
    d = _pick(r, "summary", "core_investment_arguments", "confidence_score")
    return d

def slim_risk_assessment(r: Any) -> dict:
    d = _pick(r, "summary", "top_risks", "overall_risk_level",
              "confidence_score")
    return d

def slim_strategic_insight(r: Any) -> dict:
    d = _pick(r, "summary", "recommendation", "rationale",
              "key_conditions", "confidence_score")
    if isinstance(d.get("rationale"), str) and len(d["rationale"]) > 600:
        d["rationale"] = d["rationale"][:600] + "…"
    return d


# ── Phase 3 slim helpers ─────────────────────────────────────────────────────

def slim_review(r: Any) -> dict:
    d = _pick(r, "summary", "verified_claims", "contradicted_claims",
              "confidence_score")
    return d

def slim_critique(r: Any) -> dict:
    d = _pick(r, "logic", "completeness", "accuracy",
              "narrative_bias", "insight_effectiveness",
              "total_score", "feedback", "summary")
    # feedback can be very long — cap it
    if isinstance(d.get("feedback"), str) and len(d["feedback"]) > 500:
        d["feedback"] = d["feedback"][:500] + "…"
    return d

def slim_dd_questions(r: Any) -> dict:
    d = _pick(r, "unresolved_issues", "dd_questionnaire", "summary")
    return d


# ── Serializer ────────────────────────────────────────────────────────────────

def compact(data: Any) -> str:
    """Compact JSON — no indent, no extra whitespace. ~25% smaller than indent=2."""
    return json.dumps(data, separators=_SEP, ensure_ascii=False)
