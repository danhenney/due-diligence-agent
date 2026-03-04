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
You have access to the complete DD package AND a report structure designed by the
Report Structure agent.

Your task: write a comprehensive, insight-driven investment memo in Markdown format.
This is NOT a summary — it's the definitive document for the investment committee.
TARGET LENGTH: 20-30 pages (8,000-15,000 words). Be thorough. Each section should have
multiple paragraphs with specific data points, comparisons, and analysis — not just bullet points.

WRITING PRINCIPLES:
1. INSIGHT-DRIVEN: Not just facts — provide analysis, opinions, and investment implications
2. DATA-RICH: Include specific numbers, percentages, and figures throughout
3. BALANCED: Present both bull and bear cases fairly
4. ACTIONABLE: Every section should help the reader make a decision
5. STRUCTURED: Follow the report structure provided, using Why/What/How/Risk/Recommendations

THE RECOMMENDATION MUST BE ONE OF:
- **INVEST**: Compelling opportunity — strong fundamentals, manageable risks, >15% upside
- **WATCH**: Genuinely mixed signals where bull and bear are roughly equal
- **PASS**: Risks clearly dominate — declining fundamentals, fatal red flags

CRITICAL: Do NOT default to WATCH as a hedge. If the strategic insight agent recommended
INVEST or PASS, follow that unless you have specific, concrete reasons to override.

Structure the memo as Markdown with these sections:
# Due Diligence Report: [Company Name]
**Date:** [today]
**Recommendation:** [INVEST / WATCH / PASS]
**Confidence:** [High / Medium / Low]

## Executive Summary
2-3 paragraph synthesis: what the company does, investment thesis, key financials,
recommendation with confidence level.

## 1. Why This Company? (Investment Thesis)
Market opportunity, timing, strategic fit, core investment arguments.

## 2. Business Overview
Business model, products/services, technology, competitive positioning, team.

## 3. Financial Analysis & Valuation
Revenue, profitability, growth, cash flow, DCF, comps, fair value range.

## 4. Risk Assessment
Risk matrix, top risks, mitigation strategies, stress scenarios.

## 5. Recommendation & Next Steps
### Investment Recommendation
Detailed rationale for INVEST/WATCH/PASS.
### Key Conditions & Watchpoints
Conditions that would change the recommendation.
### DD Questionnaire
Unresolved questions for follow-up investigation.

## Appendix
### Review Summary
Key verified, unverified, and contradicted claims.
### Data Sources
Numbered list of all sources used with inline citations.

IMPORTANT: Every agent's output must be represented in the memo. Do NOT omit findings.
Use inline citations [1], [2], etc. throughout the memo body.

After the memo, output a JSON block on its own line:
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
        structure_json = compact(_deep_trim(report_structure, max_str=200, max_list=5))
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
