"""Phase 2 — Bull Case agent (strongest investment thesis)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import slim_financial, slim_market, slim_legal, slim_management, slim_tech, compact
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a bullish investment analyst crafting the strongest possible investment thesis.
You have access to Phase 1 research reports on a company.
Your role: synthesize the most compelling reasons TO invest, quantify the upside,
and construct a credible path to exceptional returns.

Be rigorous — cherry-picking only. Cite evidence. Assign probability weights.

Return a JSON object with this exact structure:
{
  "thesis_title": "<punchy one-liner>",
  "core_thesis": "<2-3 paragraph investment thesis>",
  "key_catalysts": [
    {"catalyst": "...", "timeline": "...", "impact": "...", "probability": 0.0}
  ],
  "upside_scenario": {
    "description": "...",
    "revenue_projection": "...",
    "valuation_upside": "...",
    "return_potential": "..."
  },
  "competitive_advantages": ["<advantage1>", "<advantage2>"],
  "market_timing": "...",
  "why_now": "...",
  "confidence_score": 0.0
}
"""


def run(state: DueDiligenceState) -> dict:
    phase1_context = compact({
        "financial": slim_financial(state.get("financial_report")),
        "market":    slim_market(state.get("market_report")),
        "legal":     slim_legal(state.get("legal_report")),
        "management":slim_management(state.get("management_report")),
        "tech":      slim_tech(state.get("tech_report")),
    })

    user_message = (
        f"Company: {state['company_name']}\n\n"
        f"Phase 1 Research Reports:\n{phase1_context}\n\n"
        "Based on the research above, construct the strongest possible bull case "
        "investment thesis. Return the specified JSON object."
    )

    result = run_agent(
        agent_type="bull_case",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("bull_case"),
        language=state.get("language", "English"),
    )

    return {"bull_case": result}
