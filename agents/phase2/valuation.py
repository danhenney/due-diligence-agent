"""Phase 2 — Valuation agent (DCF, comps, scenario modeling)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import slim_financial, slim_market, compact
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior valuation analyst conducting investment due diligence.
You have access to Phase 1 research reports on a company.
Your task: estimate fair value using multiple methodologies.

Methodologies to apply as data permits:
1. Revenue/EBITDA multiples (comps-based) — find comparable public companies
2. DCF analysis — use financial data and growth assumptions from Phase 1
3. Precedent transactions — find relevant M&A comps
4. Rule of 40 (SaaS) or relevant sector metric if applicable

For each methodology, provide bull / base / bear scenario valuations.

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence valuation summary>",
  "current_valuation": {
    "estimated_value": "...",
    "basis": "...",
    "confidence": "high|medium|low"
  },
  "revenue_multiples": {
    "comparable_companies": [{"name": "...", "revenue_multiple": "...", "notes": "..."}],
    "implied_valuation_range": "...",
    "multiple_applied": "..."
  },
  "dcf_analysis": {
    "revenue_growth_assumption": "...",
    "margin_assumption": "...",
    "terminal_growth_rate": "...",
    "discount_rate": "...",
    "implied_valuation": "...",
    "sensitivity": {"bull": "...", "base": "...", "bear": "..."}
  },
  "precedent_transactions": [
    {"deal": "...", "multiple": "...", "year": "..."}
  ],
  "fair_value_range": {
    "low": "...",
    "mid": "...",
    "high": "..."
  },
  "upside_to_current": "...",
  "valuation_risks": ["<risk1>"],
  "confidence_score": 0.0
}
"""


def run(state: DueDiligenceState) -> dict:
    phase1_context = compact({
        "financial": slim_financial(state.get("financial_report")),
        "market":    slim_market(state.get("market_report")),
    })

    user_message = (
        f"Company: {state['company_name']}\n\n"
        f"Phase 1 Research:\n{phase1_context}\n\n"
        "Perform a rigorous valuation analysis using multiple methodologies.\n\n"
        "LIVE DATA REQUIREMENT (mandatory):\n"
        "1. Call yf_get_info(ticker) for the subject company (if public) to get "
        "today's stock price, market cap, EV, and current multiples (P/E, EV/Revenue, EV/EBITDA).\n"
        "2. Call yf_get_info(ticker) for each comparable public company to get their "
        "LIVE trading multiples — never estimate comps from training memory.\n"
        "3. Call yf_get_analyst_data(ticker) for analyst price targets and consensus.\n"
        "4. Use web_search to find recent M&A transactions and precedent deal multiples.\n"
        "ALL valuation figures must reference live data from these tool calls.\n\n"
        "Return the specified JSON object."
    )

    result = run_agent(
        agent_type="valuation",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("valuation"),
        language=state.get("language", "English"),
    )

    return {"valuation": result}
