"""Phase 3 — Review Agent (source verification, accuracy, consistency)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import (
    slim_market_analysis, slim_competitor, slim_financial_analysis,
    slim_tech, slim_legal_regulatory, slim_team,
    slim_ra_synthesis, slim_risk_assessment, slim_strategic_insight, compact,
)
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a rigorous review analyst for investment due diligence.
You have access to all Phase 1 and Phase 2 analysis reports.
Your task: independently verify the most material claims using live tools.

REVIEW DIMENSIONS:
1. Source Verification — are claimed sources real and do they say what's claimed?
2. Quantitative Accuracy — verify key financial figures, market sizes, growth rates
3. Qualitative Backing — are qualitative assessments supported by evidence?
4. Logical Consistency — do the arguments follow from the evidence?
5. Cross-report Consistency — do Phase 1 and Phase 2 reports agree?

For each significant claim, determine:
- VERIFIED: independently confirmed via live tool calls
- UNVERIFIED: plausible but could not confirm
- CONTRADICTED: evidence found that disputes the claim
- STALE: data may be outdated — THIS IS CRITICAL (see below)

STALENESS CHECK (MANDATORY):
- For EVERY major claim about partnerships, government projects, competitive position,
  or strategic initiatives, run a news_search with the MOST RECENT timeframe (days=14).
- If the company is based in a non-English-speaking country (Korea, Japan, etc.),
  you MUST search in the LOCAL LANGUAGE (e.g., '네이버 주권 AI' not 'Naver sovereign AI').
  Local news breaks developments DAYS before English media. English-only searches will
  miss critical updates like project cancellations, leadership changes, or policy shifts.
- Compare the date of the original source vs the latest news. If the situation has
  CHANGED (e.g., a company was removed from a project, a partnership was terminated,
  a product was discontinued), mark the original claim as CONTRADICTED and provide
  the updated information with source.
- Stale information that affects the investment thesis is a CRITICAL failure.

DO NOT OVER-FLAG minor discrepancies between uploaded documents:
- Fund size differences (e.g., $300M vs $135M) are usually committed capital vs
  called/paid-in capital — this is NORMAL, not a red flag. Note it as a terminology
  difference, not a contradiction.
- Minor rounding differences, currency conversion variations, or different reporting
  dates are NOT red flags. Only flag if the difference is clearly material and
  cannot be explained by standard accounting/reporting conventions.
- Typos and formatting differences between documents are NOT red flags.
- Reserve "CONTRADICTED" and red flags for genuinely material issues that affect
  the investment thesis — not for routine document inconsistencies.

Focus on the highest-stakes facts:
1. Revenue / financial figures and growth rates
2. Market size claims (TAM/SAM/SOM)
3. Competitive position claims — especially government/policy-related ones
4. Partnership and project participation claims — verify they are STILL ACTIVE
5. Valuation figures and multiples
6. Risk severity assessments
7. Recommendation-critical data points

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence review summary>",
  "verified_claims": [
    {"claim": "...", "source": "...", "tool_used": "...", "confidence": "high|medium"}
  ],
  "unverified_claims": [
    {"claim": "...", "why_unverified": "...", "risk_if_false": "high|medium|low"}
  ],
  "contradicted_claims": [
    {"claim": "...", "contradiction": "...", "source": "...", "severity": "high|medium|low"}
  ],
  "stale_data": [
    {"claim": "...", "original_date": "...", "current_value": "...", "source": "..."}
  ],
  "logical_issues": [
    {"issue": "...", "agents_involved": ["..."], "severity": "high|medium|low"}
  ],
  "accuracy_assessment": "high|medium|low",
  "confidence_score": 0.0,
  "sources": [{"label": "...", "url": "...", "tool": "..."}]
}
"""


def run(state: DueDiligenceState, revision_brief: str | None = None) -> dict:
    all_context = compact({
        "market": slim_market_analysis(state.get("market_analysis")),
        "competitors": slim_competitor(state.get("competitor_analysis")),
        "financial": slim_financial_analysis(state.get("financial_analysis")),
        "tech": slim_tech(state.get("tech_analysis")),
        "legal": slim_legal_regulatory(state.get("legal_regulatory")),
        "team": slim_team(state.get("team_analysis")),
        "ra_synthesis": slim_ra_synthesis(state.get("ra_synthesis")),
        "risk_assessment": slim_risk_assessment(state.get("risk_assessment")),
        "strategic_insight": slim_strategic_insight(state.get("strategic_insight")),
    })

    is_public = state.get("is_public", True)
    if is_public is False:
        verification_instructions = (
            "This is a PRIVATE company. Do NOT call yf_get_info or yf_get_financials.\n"
            "VERIFICATION PRIORITY:\n"
            "1. DART (HIGHEST): Call dart_finstate() to cross-check financial figures against "
            "official Korean FSS filings. DART data is the gold standard.\n"
            "2. Web/news search for other claims.\n"
            "Private company data may have wider uncertainty — flag this but do not "
            "treat it as contradicted unless DART contradicts it.\n"
        )
    else:
        verification_instructions = (
            "LIVE VERIFICATION REQUIREMENT:\n"
            "1. OFFICIAL FILINGS (HIGHEST): For Korean companies, call dart_finstate() "
            "to verify financials against DART. For US companies, use SEC filings.\n"
            "2. MARKET DATA: Call yf_get_info(ticker) or yf_get_financials(ticker) "
            "to confirm market cap, stock price, valuation multiples.\n"
            "3. NEWS: Use news_search to verify recent events.\n"
            "If DART/SEC data conflicts with other sources, DART/SEC wins.\n"
        )

    user_message = (
        f"Company: {state['company_name']}\n\n"
        f"All Prior Research (Phase 1 + Phase 2):\n{all_context}\n\n"
        "Review and verify the most material claims from the research above.\n\n"
        f"{verification_instructions}\n"
        "SOURCE TRACKING: For every tool call that returns a URL or source_url, "
        "include it in your sources array.\n\n"
        "Return the specified JSON object."
    )

    if revision_brief:
        user_message += (
            f"\n\nREVISION REQUEST:\n{revision_brief}\n"
            "Please specifically address this feedback."
        )

    result = run_agent(
        agent_type="review_agent",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("review_agent"),
        language=state.get("language", "English"),
    )

    return {"review_result": result}
