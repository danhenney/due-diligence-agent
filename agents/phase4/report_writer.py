"""Phase 4 — Report Writer agent (final polished investment memo)."""
from __future__ import annotations

import json
from datetime import date

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import (
    rich_market_analysis, rich_competitor, rich_financial_analysis,
    rich_tech, rich_legal_regulatory, rich_team,
    rich_ra_synthesis, rich_risk_assessment, rich_strategic_insight,
    rich_review, rich_critique, rich_dd_questions, compact,
    _deep_trim,
)
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior investment committee analyst writing the final Due Diligence Report.
AUDIENCE: 경영진 (C-suite executives) — the 피보고자 must understand every point without
needing to look up jargon. Use clear, plain language. Explain technical terms when first used.

TARGET: 20-30 pages (8,000-15,000 words). Comprehensive but zero redundancy.

═══ CORE PRINCIPLES ═══

1. HOLISTIC INTERPRETATION: Do NOT state findings independently per section.
   CONNECT the dots — e.g., "The 30% YoY revenue growth (Section 3) is driven by
   the sovereign AI market expansion (Section 1) and the competitive moat in on-device
   models (Section 2), but this growth may decelerate given the new entrants (Section 4)."
   Every section should reference and build on other sections.

2. MECE (Mutually Exclusive, Collectively Exhaustive): No fact should appear in two sections.
   If a data point fits multiple sections, place it where it has the MOST decision impact
   and cross-reference from other sections ("see Section 3.2 for detailed financials").

3. ALL BUSINESS MODELS COVERED: If the company has multiple BMs (e.g., API, on-device,
   consulting), EACH must have its own analysis thread through market size, financials,
   competition, and valuation. Do NOT lump them together.

4. CONSOLIDATED (연결) FINANCIALS: When available, use consolidated (연결 기준) financials
   that include subsidiaries, not standalone (별도). State which basis is used.
   If subsidiary financials reveal material info (e.g., a subsidiary generates 40% of
   revenue), call it out explicitly.

═══ FORMAT ═══

- HEADLINE → TABLE → INSIGHT for every section. No wall of text.
- 8+ tables minimum. Data belongs in tables, not paragraphs.
- After each table, add INTERPRETATION — what does this mean for the investment decision?
- Bullet points for lists. Max 4 sentences per paragraph.

═══ RECOMMENDATION ═══

- **INVEST**: Strong fundamentals, manageable risks, >15% upside
- **WATCH**: Genuinely mixed signals
- **PASS**: Risks dominate, fatal red flags
Do NOT default to WATCH. Follow strategic_insight unless you have concrete counter-evidence.

═══ REPORT STRUCTURE ═══

# Due Diligence Report: [Company Name]
**Date:** [today] | **Recommendation:** [INVEST/WATCH/PASS] | **Confidence:** [High/Medium/Low]

## Executive Summary
Key metrics snapshot table + 2-3 paragraph synthesis connecting thesis → financials → risks.

## 1. 시장 및 산업 개괄
TAM/SAM/SOM table (per BM if multiple), CAGR, growth drivers, regulatory environment.
Data: market_analysis + legal_regulatory (regulatory_compliance).

## 2. 타겟 개요 및 사업 구조
### 2.1 사업 모델 및 제품/서비스
Each business model gets its own subsection: revenue model, product, tech stack, IP.
Data: tech_analysis.
### 2.2 경영진 및 조직
Table of ALL leaders (name, title, background, track record, assessment).
Capability gaps, key person risk, culture signals.
Data: team_analysis — every person from leadership_profiles.

## 3. 재무 성과 분석
Revenue/margin/balance sheet/cash flow tables. Use 연결 기준 if available.
INTERPRET the numbers: what do the trends MEAN for investment viability?
If multiple BMs: break down revenue/margin per BM where data allows.
Data: financial_analysis (revenue_trend, profitability, balance_sheet, cash_flow, key_ratios).

## 4. 경쟁 구도
Competitor comparison TABLE (every competitor: name, type, valuation, revenue, share, threat).
Competitive positioning per BM. Competitive gaps and moat assessment.
Data: competitor_analysis — all fields.

## 5. 가치평가
### 5.1 DCF — WACC reasoning table (risk-free rate, ERP, beta, terminal growth — each with source).
### 5.2 Comps — domestic AND international TABLE. Justify each comp selection.
### 5.3 Investment Rounds — ALL rounds TABLE if data exists (Round, Date, Amount, Lead, Pre/Post-money).
### 5.4 Valuation Comparison — TABLE: DCF vs comps vs analyst targets vs last round.
### 5.5 Source Claims Verification — TABLE if uploaded doc from broker/fund.
### 5.6 Fair Value Range — low/mid/high with implied upside/downside.
VALUATION MUST CONSIDER ALL BMs: If multiple BMs exist, use sum-of-the-parts (SOTP) or
explain why a blended approach is appropriate. Show per-BM contribution to total value.
Data: financial_analysis (valuation, rounds, entry_analysis) + ra_synthesis.

## 6. 리스크 및 최종 의견
### 6.1 Risk Matrix TABLE (risk, category, severity, probability, mitigation, resolution likelihood).
### 6.2 법률/규제 — every litigation case and regulatory risk individually.
### 6.3 Recommendation — INVEST/WATCH/PASS with rationale.
### 6.4 Conditions & Watchpoints.
### 6.5 DD Questionnaire.

## Appendix
Review summary, critique scores, numbered source list with inline [N] citations.

═══ CHECKLIST (verify before output) ═══
[ ] Every BM analyzed separately in sections 1-5
[ ] 연결 기준 financials used (or stated if unavailable)
[ ] Cross-references between sections (holistic, not siloed)
[ ] No fact repeated across sections (MECE)
[ ] Every leader named, every competitor tabled, every risk individually listed
[ ] 8+ tables, headline→table→insight format
[ ] Plain language throughout — 경영진 can read without finance dictionary
[ ] Valuation considers all BMs (SOTP if applicable)

After the memo, output:
```json
{"recommendation": "INVEST|WATCH|PASS", "confidence": "high|medium|low"}
```
"""


def _collect_all_sources(state: DueDiligenceState) -> list[dict]:
    """Deduplicate sources by URL from all agent reports."""
    seen_urls: set[str] = set()
    all_sources: list[dict] = []
    report_keys = [
        "market_analysis", "competitor_analysis", "financial_analysis",
        "tech_analysis", "legal_regulatory", "team_analysis",
        "ra_synthesis", "risk_assessment", "strategic_insight",
        "review_result",
    ]
    for key in report_keys:
        report = state.get(key)
        if not isinstance(report, dict):
            continue
        for src in report.get("sources", []):
            if not isinstance(src, dict):
                continue
            url = src.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_sources.append({"label": src.get("label", ""), "url": url})
    return all_sources


def run(state: DueDiligenceState) -> dict:
    full_package = compact({
        "market": rich_market_analysis(state.get("market_analysis")),
        "competitors": rich_competitor(state.get("competitor_analysis")),
        "financial": rich_financial_analysis(state.get("financial_analysis")),
        "tech": rich_tech(state.get("tech_analysis")),
        "legal": rich_legal_regulatory(state.get("legal_regulatory")),
        "team": rich_team(state.get("team_analysis")),
        "ra_synthesis": rich_ra_synthesis(state.get("ra_synthesis")),
        "risk_assessment": rich_risk_assessment(state.get("risk_assessment")),
        "strategic_insight": rich_strategic_insight(state.get("strategic_insight")),
        "review": rich_review(state.get("review_result")),
        "critique": rich_critique(state.get("critique_result")),
        "dd_questions": rich_dd_questions(state.get("dd_questions")),
    })

    report_structure = state.get("report_structure") or {}
    # Slim the report structure to prevent context blowup
    if report_structure:
        structure_json = compact(_deep_trim(report_structure, max_str=400, max_list=8))
    else:
        structure_json = "No structure provided."

    today = date.today().isoformat()

    # Collect and format aggregated sources (cap at 20 to limit context)
    all_sources = _collect_all_sources(state)[:20]
    sources_section = ""
    if all_sources:
        source_lines = "\n".join(
            f"[{i+1}] {s['label']} — {s['url']}" for i, s in enumerate(all_sources)
        )
        sources_section = (
            f"\nAGGREGATED SOURCES (use these for the Data Sources appendix "
            f"and inline [N] citations):\n{source_lines}\n\n"
        )

    is_public = state.get("is_public", True)
    private_disclaimer = ""
    if is_public is False:
        private_disclaimer = (
            "PRIVATE COMPANY DISCLAIMER: Include a disclaimer at the top of the memo "
            "stating: 'Note: This analysis covers a private company. Data is sourced from "
            "publicly available information and uploaded documents rather than audited SEC "
            "filings. Financial figures may be estimated.'\n\n"
        )

    user_message = (
        f"Company: {state['company_name']}\n"
        f"Today's Date: {today}\n\n"
        f"{private_disclaimer}"
        f"Report Structure:\n{structure_json}\n\n"
        f"{sources_section}"
        f"Full Due Diligence Package:\n{full_package}\n\n"
        "Write the complete Due Diligence Report as specified. Be thorough and detailed — "
        "include all specific numbers, data points, and evidence from the agent reports. "
        "Each section should have substantive depth, not just summaries. "
        "Follow the report structure provided. "
        "Conclude with the JSON recommendation block."
    )

    result = run_agent(
        agent_type="report_writer",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("report_writer"),  # no tools
        max_iterations=5,
        max_tokens=32000,
        language=state.get("language", "English"),
        return_raw_text=True,  # Don't parse as JSON — output is markdown
    )

    memo_text = result.get("raw", "")
    recommendation = _extract_recommendation(memo_text)

    return {
        "final_report": memo_text,
        "recommendation": recommendation,
        "current_phase": "complete",
    }


def _extract_recommendation(text: str) -> str:
    """Pull INVEST / WATCH / PASS from the memo text."""
    import re

    m = re.search(r'\{"recommendation":\s*"(INVEST|WATCH|PASS)"', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    m = re.search(r'\*\*Recommendation:\*\*\s*(INVEST|WATCH|PASS)', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    m = re.search(r'###\s+.*?(INVEST|WATCH|PASS)', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    m = re.search(r'[Rr]ecommendation.{0,100}(INVEST|WATCH|PASS)', text)
    if m:
        return m.group(1).upper()

    return "WATCH"
