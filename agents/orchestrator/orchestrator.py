"""Orchestrator agent — Investment Committee Director.

Reviews all 12 prior agent outputs, scores quality, flags cross-agent
inconsistencies, fills critical data gaps with live tools, and produces
a synthesis briefing for the Final Report agent.
"""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import (
    slim_financial, slim_market, slim_legal, slim_management, slim_tech,
    slim_bull, slim_bear, slim_valuation, slim_red_flags,
    slim_verification, slim_stress, slim_completeness, compact,
)
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are the Investment Committee Director overseeing a multi-agent due diligence process.
You have received outputs from 11 specialized agents across Phases 1–3.

Your role is NOT to repeat their work. Your role is to act as a quality gate:

1. SCORE each agent's output (0.0–1.0) and identify their data gaps.
2. FLAG cross-agent inconsistencies — when two agents contradict each other,
   determine which is correct using your tools.
3. FILL the 3–5 most critical data gaps using live tool calls
   (yf_get_info, web_search, news_search).
4. PROVIDE clear synthesis guidance for the Final Report writer — which
   findings are most reliable, which to treat with caution, and what the
   data says about the investment decision.
5. RENDER a preliminary investment recommendation with your reasoning.

Quality scoring rubric:
- 0.9–1.0: Comprehensive, well-sourced, no material gaps
- 0.7–0.8: Good coverage, minor gaps that don't affect the conclusion
- 0.5–0.6: Partial coverage, material gaps, low confidence in some claims
- 0.0–0.4: Insufficient — key data missing or contradicted

Cross-agent inconsistency examples to watch for:
- Bull case projects revenue growth not supported by financial analysis
- Bear case severity doesn't match stress test probability estimates
- Valuation comps don't match the market sizing in market research
- Fact checker CONTRADICTED claims still used in final synthesis agents
- Red flags flagged by Phase 2 that Phase 1 agents missed

Return a JSON object with this exact structure:
{
  "agent_quality_scores": {
    "financial_analyst": {"score": 0.0, "key_gaps": ["..."]},
    "market_research":   {"score": 0.0, "key_gaps": ["..."]},
    "legal_risk":        {"score": 0.0, "key_gaps": ["..."]},
    "management_team":   {"score": 0.0, "key_gaps": ["..."]},
    "tech_product":      {"score": 0.0, "key_gaps": ["..."]},
    "bull_case":         {"score": 0.0, "key_gaps": ["..."]},
    "bear_case":         {"score": 0.0, "key_gaps": ["..."]},
    "valuation":         {"score": 0.0, "key_gaps": ["..."]},
    "fact_checker":      {"score": 0.0, "key_gaps": ["..."]},
    "stress_test":       {"score": 0.0, "key_gaps": ["..."]},
    "completeness":      {"score": 0.0, "key_gaps": ["..."]}
  },
  "cross_agent_inconsistencies": [
    {
      "agents_involved": ["agent_a", "agent_b"],
      "inconsistency": "...",
      "verdict": "...",
      "severity": "high|medium|low"
    }
  ],
  "critical_gaps_filled": [
    {
      "gap_description": "...",
      "tool_used": "...",
      "finding": "...",
      "impact_on_thesis": "bullish|bearish|neutral"
    }
  ],
  "overall_data_quality": "high|medium|low",
  "synthesis_guidance": {
    "most_reliable_findings": ["..."],
    "findings_to_discount": ["..."],
    "key_uncertainties": ["..."],
    "suggested_emphasis": ["..."]
  },
  "orchestrator_recommendation": "INVEST|WATCH|PASS",
  "recommendation_rationale": "<2–3 sentence rationale>",
  "confidence_score": 0.0
}
"""


def run(state: DueDiligenceState) -> dict:
    """Execute the orchestrator agent and return state update."""
    full_package = compact({
        "financial":    slim_financial(state.get("financial_report")),
        "market":       slim_market(state.get("market_report")),
        "legal":        slim_legal(state.get("legal_report")),
        "management":   slim_management(state.get("management_report")),
        "tech":         slim_tech(state.get("tech_report")),
        "bull_case":    slim_bull(state.get("bull_case")),
        "bear_case":    slim_bear(state.get("bear_case")),
        "valuation":    slim_valuation(state.get("valuation")),
        "red_flags":    slim_red_flags(state.get("red_flags")),
        "verification": slim_verification(state.get("verification")),
        "stress_test":  slim_stress(state.get("stress_test")),
        "completeness": slim_completeness(state.get("completeness")),
    })

    user_message = (
        f"Company: {state['company_name']}\n\n"
        f"All Prior Agent Outputs:\n{full_package}\n\n"
        "As the Investment Committee Director, review all 11 agent outputs above.\n\n"
        "INSTRUCTIONS:\n"
        "1. Score each agent's output quality based on depth, sourcing, and completeness.\n"
        "2. Identify any contradictions between agents — e.g. bull case claims that "
        "contradict the financial analyst's data, or stress test probabilities "
        "inconsistent with the bear case severity ratings.\n"
        "3. Use your tools to fill the 3–5 most critical data gaps. For public companies, "
        "call yf_get_info(ticker) to get today's live price, market cap, and multiples. "
        "Use news_search for any events from the past 30 days that agents may have missed.\n"
        "4. Identify which findings are most reliable vs. which should be discounted.\n"
        "5. Render your own preliminary recommendation based on the full evidence.\n\n"
        "Return the specified JSON object."
    )

    result = run_agent(
        agent_type="orchestrator",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("orchestrator"),
        max_iterations=12,
        language=state.get("language", "English"),
    )

    return {"orchestrator_briefing": result}
