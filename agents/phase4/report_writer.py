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
5. STRUCTURED: Follow the 6-section report structure below
6. TABLE-DRIVEN: Use Markdown tables liberally for key comparisons — competitor matrix,
   domestic vs international comps, valuation comparison, risk matrix, investment rounds.
   Tables make the report scannable. Each major section should have at least one table.
7. DETAIL FROM AGENTS: Do NOT summarize agent findings into vague one-liners. Transfer
   the SPECIFIC details — risk severity levels AND resolution/mitigation likelihood,
   competitor financial metrics, team member track records, legal case specifics.
   If an agent provided a severity rating (high/medium/low) and a probability, include BOTH.
8. LATEST INFORMATION: Prioritize the most recent data, product launches, partnerships,
   and news. If the data mentions recent developments (new models, latest funding, recent
   acquisitions), feature them prominently — they are the most valuable signals.

THE RECOMMENDATION MUST BE ONE OF:
- **INVEST**: Compelling opportunity — strong fundamentals, manageable risks, >15% upside
- **WATCH**: Genuinely mixed signals where bull and bear are roughly equal
- **PASS**: Risks clearly dominate — declining fundamentals, fatal red flags

CRITICAL: Do NOT default to WATCH as a hedge. If the strategic insight agent recommended
INVEST or PASS, follow that unless you have specific, concrete reasons to override.

Structure the memo as Markdown:

# Due Diligence Report: [Company Name]
**Date:** [today]
**Recommendation:** [INVEST / WATCH / PASS]
**Confidence:** [High / Medium / Low]

## Executive Summary
2-3 paragraph synthesis: what the company does, investment thesis, key financials,
recommendation with confidence level.

## 1. 시장 및 산업 개괄 (Market & Industry Overview)
Market size (TAM/SAM/SOM with specific figures), CAGR, growth drivers, industry trends,
geographic breakdown, regulatory environment context.
Data: market_analysis (tam, sam, som, cagr, trends, market_drivers, geographic_breakdown)
+ legal_regulatory (regulatory_compliance).

## 2. 타겟 개요 및 사업/제품 구조 (Target Overview & Business/Product Structure)
### 2.1 사업 모델 및 제품/서비스 (Business Model & Products/Services)
Business model, revenue streams, product portfolio, technology stack, IP assessment.
Data: tech_analysis (core_technologies, ip_patents, tech_maturity).
### 2.2 경영진 및 조직 (Leadership & Organization)
MANDATORY: List EVERY person from leadership_profiles with name, title, background,
track record, and assessment. Cover capability_assessment, departure_history,
key_person_risk, culture_signals. Each leader gets their own paragraph.
Data: team_analysis — use ALL fields.

## 3. 성과 및 운영 지표 (Performance & Operating Metrics)
Revenue trends (5-year), profitability (gross/EBITDA/net margins), balance sheet
strength (cash, debt, ratios), cash flow quality (FCF, capex), key ratios vs benchmarks.
Data: financial_analysis (revenue_trend, profitability, balance_sheet, cash_flow, key_ratios).

## 4. 경쟁 구도 및 포지셔닝 (Competitive Landscape & Positioning)
MANDATORY: List EVERY competitor from the competitors array with name, type,
valuation/market cap, revenue, market share, key strengths/weaknesses, threat level.
Present as a comparison table. Include competitive_gaps, comparison_matrix, market_share.
Data: competitor_analysis — use ALL fields.

## 5. 재무 현황/전망 및 가치평가 (Financial Status/Outlook & Valuation)
### 5.1 DCF Valuation
MANDATORY: Show WACC with full reasoning — risk-free rate (source), equity risk premium
(source), beta (source/methodology), resulting WACC. Terminal growth rate with reasoning.
FCF projections with assumptions.
### 5.2 Market Comparables
MANDATORY: Include BOTH domestic and international comparable companies with specific
multiples (P/E, EV/EBITDA, P/S). Present as comparison TABLE. For each domestic comp,
state when they IPO'd/raised and justify why they are a valid comparison.
### 5.3 Investment Round History & Entry Analysis
If investment_rounds data exists: present ALL rounds as a TABLE (round, date, amount,
lead investor, implied valuation, multiple vs previous). Then analyze: what multiple vs
last round does a new investment represent? Is the entry point favorable?
### 5.4 External Valuations Comparison
MANDATORY: Compare your DCF result vs your comps result vs external analyst targets vs
last funding round valuation. Present as a comparison TABLE. Explain differences.
### 5.5 Fair Value Range & Projections
Low/mid/high fair value with implied upside/downside. Financial projections and guidance.
Data: financial_analysis (valuation, investment_rounds, entry_analysis) + ra_synthesis.

## 6. 리스크 및 최종 의견/제언 (Risks & Final Opinion/Recommendations)
### 6.1 Risk Matrix
Present ALL top_risks from risk_assessment as a TABLE with columns: Risk, Category,
Severity (high/medium/low), Probability (high/medium/low), Mitigation Strategy,
Resolution Likelihood. Include BOTH the severity AND the likelihood of resolution/mitigation
for each risk — this is critical for investment decision-making.
### 6.2 법률/규제 리스크 (Legal & Regulatory Risks)
MANDATORY: List EVERY litigation case and regulatory risk individually from
legal_regulatory. Include investment_structure_risks, business_regulatory_risks,
ip_risks. For EACH risk, state: (1) description, (2) severity, (3) probability,
(4) potential mitigation or resolution path. Do NOT summarize into one sentence.
### 6.3 Investment Recommendation
INVEST/WATCH/PASS with detailed rationale from strategic_insight.
### 6.4 Key Conditions & Watchpoints
Conditions that would change the recommendation.
### 6.5 DD Questionnaire
Unresolved questions for follow-up from dd_questions.

## Appendix
### Review Summary
Key verified, unverified, and contradicted claims from review agent.
### Critique Summary
Scores and feedback from critique agent.
### Data Sources
Numbered list of all sources used with inline citations.

═══════════════════════════════════════════════════════════════════
MANDATORY INCLUSION CHECKLIST — Before finalizing, verify ALL items:
[ ] Section 2.2: Every person from leadership_profiles is named and described
[ ] Section 4: Every competitor listed as TABLE with financials and threat level
[ ] Section 5.1: DCF WACC has explicit reasoning (risk-free rate, ERP, beta sources)
[ ] Section 5.2: Domestic comps include IPO/funding date and selection justification
[ ] Section 5.3: Investment rounds TABLE exists (if data available)
[ ] Section 5.4: Own valuation vs external valuations comparison TABLE exists
[ ] Section 6.1: Risk matrix TABLE with severity AND resolution likelihood for each risk
[ ] Section 6.2: Every litigation/regulatory risk individually described with mitigation
[ ] TABLES: At least 5 tables total across the report (comps, competitors, risks, rounds, etc.)
[ ] LATEST INFO: Most recent product launches and developments are mentioned
If ANY item is missing, go back and add it before outputting.
═══════════════════════════════════════════════════════════════════

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
