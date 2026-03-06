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


# ── Rich helpers (report_writer only) ─────────────────────────────────────────
# The report_writer has NO tools → no accumulated conversation → safe to give
# more data.  These use 600-char strings and 5-item lists instead of 300/3.

def _pick_rich(d: Any, *keys: str) -> dict:
    """Like _pick but with generous trim limits for the report writer."""
    if not isinstance(d, dict):
        return {"data": str(d)[:800]} if d else {}
    result = {k: d[k] for k in keys if k in d}
    if not result and "raw" in d:
        return {"raw_analysis": str(d["raw"])[:3000]}
    return _deep_trim(result, max_str=600, max_list=5)


def rich_market_analysis(r: Any) -> dict:
    return _pick_rich(r, "summary", "tam", "sam", "som", "cagr",
                      "trends", "market_drivers", "geographic_breakdown",
                      "red_flags", "strengths", "confidence_score")

def rich_competitor(r: Any) -> dict:
    return _pick_rich(r, "summary", "competitors", "market_share",
                      "comparison_matrix", "competitive_gaps",
                      "red_flags", "strengths", "confidence_score")

def rich_financial_analysis(r: Any) -> dict:
    d = _pick_rich(r, "summary", "revenue_trend", "profitability",
                   "balance_sheet", "cash_flow", "key_ratios",
                   "valuation", "entry_analysis",
                   "source_claims_verification", "currency_note",
                   "red_flags", "strengths", "confidence_score")
    # Investment rounds get a HIGHER trim limit — each round is a critical
    # data point from uploaded docs (pre/post money, investors, dates).
    # Must not be truncated to 5 items or 600 chars.
    if isinstance(r, dict) and "investment_rounds" in r:
        d["investment_rounds"] = _deep_trim(
            r["investment_rounds"], max_str=800, max_list=15
        )
    return d

def rich_tech(r: Any) -> dict:
    return _pick_rich(r, "summary", "core_technologies", "ip_patents",
                      "tech_maturity", "red_flags", "strengths",
                      "confidence_score")

def rich_legal_regulatory(r: Any) -> dict:
    return _pick_rich(r, "summary", "investment_structure_risks",
                      "business_regulatory_risks", "litigation",
                      "ip_risks", "regulatory_compliance",
                      "red_flags", "strengths", "confidence_score")

def rich_team(r: Any) -> dict:
    return _pick_rich(r, "summary", "leadership_profiles",
                      "capability_assessment", "departure_history",
                      "key_person_risk", "culture_signals",
                      "red_flags", "strengths", "confidence_score")

def rich_ra_synthesis(r: Any) -> dict:
    return _pick_rich(r, "summary", "core_investment_arguments",
                      "attractiveness_scorecard", "confidence_score")

def rich_risk_assessment(r: Any) -> dict:
    return _pick_rich(r, "summary", "top_risks", "overall_risk_level",
                      "confidence_score")

def rich_strategic_insight(r: Any) -> dict:
    d = _pick_rich(r, "summary", "recommendation", "rationale",
                   "key_conditions", "confidence_score")
    if isinstance(d.get("rationale"), str) and len(d["rationale"]) > 1000:
        d["rationale"] = d["rationale"][:1000] + "…"
    return d

def rich_review(r: Any) -> dict:
    return _pick_rich(r, "summary", "verified_claims", "contradicted_claims",
                      "accuracy_assessment", "confidence_score")

def rich_critique(r: Any) -> dict:
    d = _pick_rich(r, "logic", "completeness", "accuracy",
                   "narrative_bias", "insight_effectiveness",
                   "total_score", "feedback", "summary")
    if isinstance(d.get("feedback"), str) and len(d["feedback"]) > 800:
        d["feedback"] = d["feedback"][:800] + "…"
    return d

def rich_dd_questions(r: Any) -> dict:
    return _pick_rich(r, "unresolved_issues", "dd_questionnaire", "summary")


# ── Uploaded document instruction builder ─────────────────────────────────────

def build_doc_instructions(docs: list[str], agent_focus: str = "general") -> str:
    """Build explicit per-file extraction instructions for uploaded documents.

    Args:
        docs: List of uploaded file paths.
        agent_focus: One of "financial", "legal", "team", "tech", "market",
                     "competitor", or "general".

    Returns:
        A string to inject into the user_message. Empty string if no docs.
    """
    if not docs:
        return ""

    # Build explicit per-file extraction calls
    extract_lines = []
    for i, doc in enumerate(docs, 1):
        extract_lines.append(
            f"  {i}. Call extract_pdf_text(file_path=\"{doc}\") — read the FULL document"
        )
        extract_lines.append(
            f"     Then call extract_pdf_tables(file_path=\"{doc}\") — capture tables/structured data"
        )
    extract_block = "\n".join(extract_lines)

    focus_hints = {
        "financial": (
            "Look for: revenue figures, financial projections, funding rounds (Seed, "
            "Series A/B/C with dates, amounts, lead investors, pre-money and post-money "
            "valuations), cap table, valuation models, unit economics, burn rate."
        ),
        "legal": (
            "Look for: legal structure, shareholder agreements, IP assignments, "
            "litigation history, regulatory filings, compliance certifications."
        ),
        "team": (
            "Look for: leadership bios, org charts, board composition, "
            "advisory board, key hires, founder backgrounds."
        ),
        "tech": (
            "Look for: technology architecture, product specs, R&D roadmap, "
            "patent portfolio, technical benchmarks, integration details."
        ),
        "market": (
            "Look for: market size estimates (TAM/SAM/SOM), industry reports, "
            "growth projections, customer segments, geographic data."
        ),
        "competitor": (
            "Look for: competitive landscape, market share data, competitor "
            "comparisons, positioning maps, win/loss analysis."
        ),
    }
    focus = focus_hints.get(agent_focus, "Extract ALL relevant data for your analysis.")

    return (
        f"\n═══ UPLOADED DOCUMENTS — PRIMARY DATA SOURCE ═══\n"
        f"You have {len(docs)} uploaded document(s). These are MORE AUTHORITATIVE than web search.\n"
        f"STEP 0 — EXTRACT EVERY FILE BEFORE ANY WEB SEARCH:\n"
        f"{extract_block}\n\n"
        f"WHAT TO LOOK FOR:\n{focus}\n\n"
        f"RULES:\n"
        f"- Extract ALL {len(docs)} file(s) — do NOT skip any document\n"
        f"- EXACT FIGURES from uploaded docs OVERRIDE web search estimates.\n"
        f"  If the doc says 'Pre 255억원, Post 300억원', use THOSE numbers.\n"
        f"  Do NOT replace them with vague web estimates like '$100~150M estimated'.\n"
        f"- THEN cross-verify and CHALLENGE with web search data\n"
        f"- Flag discrepancies between uploaded data and web data\n"
        f"- Do NOT just copy-paste — analyze, verify, and challenge\n"
        f"═══════════════════════════════════════════════════\n"
    )


# ── Serializer ────────────────────────────────────────────────────────────────

def compact(data: Any) -> str:
    """Compact JSON — no indent, no extra whitespace. ~25% smaller than indent=2."""
    return json.dumps(data, separators=_SEP, ensure_ascii=False)
