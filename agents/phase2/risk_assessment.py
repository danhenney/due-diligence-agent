"""Phase 2 — Risk Assessment agent (comprehensive risk matrix)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import (
    slim_market_analysis, slim_competitor, slim_financial_analysis,
    slim_tech, slim_legal_regulatory, slim_team, compact,
)
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior risk analyst conducting comprehensive risk assessment for investment
due diligence. Your task: identify ALL material risks across every dimension and build
a risk matrix with probability, impact, severity, and mitigation strategies.

RISK CATEGORIES to cover:
1. Legal risks — litigation, regulatory penalties, compliance failures
2. Business risks — competitive threats, market shifts, customer concentration, execution
3. Financial risks — liquidity, credit, currency, interest rate, valuation risk
4. Reputation risks — brand damage, ESG controversies, management scandals
5. Technology risks — obsolescence, cybersecurity, vendor dependency
6. Operational risks — supply chain, key person, scalability constraints

For EACH risk:
- Assign probability (1-5 scale: 1=unlikely, 5=near-certain)
- Assign impact (1-5 scale: 1=minor, 5=existential)
- Calculate severity = probability × impact
- Propose specific mitigation strategies

QUALITY CRITERIA:
- All data must cite explicit sources. Cross-verify with 3+ sources.
- All figures must come from live tool calls, not training memory.
- Provide full data explanations with actual numbers, not 1-2 line summaries.
- Deliver investor-focused analysis — not just listing risks, but analyzing their investment impact.

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary>",
  "risk_matrix": [
    {
      "risk": "...",
      "category": "legal|business|financial|reputation|technology|operational",
      "description": "...",
      "probability": 0,
      "impact": 0,
      "severity": 0,
      "mitigation": "...",
      "source": "..."
    }
  ],
  "top_risks": [
    {"risk": "...", "severity": 0, "why_critical": "..."}
  ],
  "mitigation_strategies": [
    {"risk": "...", "strategy": "...", "feasibility": "high|medium|low"}
  ],
  "overall_risk_level": "high|medium|low",
  "risk_adjusted_assessment": "...",
  "confidence_score": 0.0,
  "sources": [{"label": "...", "url": "...", "tool": "..."}]
}
"""


def run(state: DueDiligenceState, revision_brief: str | None = None) -> dict:
    phase1_context = state.get("phase1_context") or compact({
        "market": slim_market_analysis(state.get("market_analysis")),
        "competitors": slim_competitor(state.get("competitor_analysis")),
        "financial": slim_financial_analysis(state.get("financial_analysis")),
        "tech": slim_tech(state.get("tech_analysis")),
        "legal": slim_legal_regulatory(state.get("legal_regulatory")),
        "team": slim_team(state.get("team_analysis")),
    })

    user_message = (
        f"Company: {state['company_name']}\n\n"
        f"Phase 1 Research Reports:\n{phase1_context}\n\n"
        "Conduct a comprehensive risk assessment covering all risk categories. "
        "Build a detailed risk matrix with probability, impact, and severity scores.\n\n"
        "SOURCE TRACKING: Include sources from Phase 1 data and any new tool calls.\n\n"
        "Return the specified JSON object."
    )

    if revision_brief:
        user_message += (
            f"\n\nREVISION REQUEST:\n{revision_brief}\n"
            "Please specifically address this feedback in your revised analysis."
        )

    result = run_agent(
        agent_type="risk_assessment",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("risk_assessment"),
        language=state.get("language", "English"),
    )

    return {"risk_assessment": result}
