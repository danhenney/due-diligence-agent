"""Phase 3 — Fact Checker agent (cross-reference all claims)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import slim_financial, slim_market, slim_management, slim_tech, slim_bull, slim_bear, slim_red_flags, compact
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a rigorous fact-checking analyst for investment due diligence.
You have access to all Phase 1 and Phase 2 analysis reports.
Your task: independently verify the most material factual claims.

For each significant claim, determine:
- VERIFIED: independently confirmed via web/news search
- UNVERIFIED: plausible but could not confirm
- CONTRADICTED: evidence found that disputes the claim
- MISSING: claim expected but not present

Focus on the highest-stakes facts:
1. Revenue / financial figures
2. Market size claims
3. Key customer claims
4. Management background
5. Product capabilities and differentiation claims
6. Regulatory status claims

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence fact-check summary>",
  "verified_claims": [
    {"claim": "...", "source": "...", "confidence": "high|medium"}
  ],
  "unverified_claims": [
    {"claim": "...", "why_unverified": "...", "risk_if_false": "high|medium|low"}
  ],
  "contradicted_claims": [
    {"claim": "...", "contradiction": "...", "source": "...", "severity": "high|medium|low"}
  ],
  "missing_information": [
    {"expected_fact": "...", "why_important": "...", "recommended_action": "..."}
  ],
  "overall_factual_integrity": "high|medium|low",
  "confidence_score": 0.0
}
"""


def run(state: DueDiligenceState, revision_brief: str | None = None) -> dict:
    all_context = compact({
        "financial":  slim_financial(state.get("financial_report")),
        "market":     slim_market(state.get("market_report")),
        "management": slim_management(state.get("management_report")),
        "tech":       slim_tech(state.get("tech_report")),
        "bull_case":  slim_bull(state.get("bull_case")),
        "bear_case":  slim_bear(state.get("bear_case")),
        "red_flags":  slim_red_flags(state.get("red_flags")),
    })

    user_message = (
        f"Company: {state['company_name']}\n\n"
        f"All Prior Research:\n{all_context}\n\n"
        "Fact-check the most material claims from the research above.\n\n"
        "LIVE VERIFICATION REQUIREMENT: For any financial figure claimed above "
        "(market cap, revenue, stock price, valuation multiple), call yf_get_info(ticker) "
        "or yf_get_financials(ticker) to confirm the number is current and correct. "
        "Use news_search to verify any recent events, product launches, or regulatory actions. "
        "Your fact-check MUST compare claimed figures against live tool results — "
        "flag any that differ from training memory.\n\n"
        "Return the specified JSON object."
    )

    if revision_brief:
        user_message += (
            f"\n\nORCHESTRATOR REVISION REQUEST:\n{revision_brief}\n"
            "Please specifically address this feedback in your revised analysis, "
            "using your available tools to fetch any missing or stale data."
        )

    result = run_agent(
        agent_type="fact_checker",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("fact_checker"),
        language=state.get("language", "English"),
    )

    return {"verification": result}
