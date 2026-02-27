"""Phase 3 — Stress Test agent (downside scenario analysis)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import slim_financial, slim_bear, slim_valuation, slim_verification, slim_red_flags, compact
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a risk analyst specializing in stress-testing investment theses.
You have access to all prior due diligence analysis including bear case and red flags.
Your task: model concrete downside scenarios and quantify their impact.

Construct 3 stress scenarios:
1. **Base Stress**: Moderate deterioration (recession, execution miss)
2. **Severe Stress**: Significant adverse events (major competitor, regulatory action)
3. **Catastrophic**: Existential risk scenario (technology disruption, fraud, bankruptcy)

For each scenario, estimate probability, financial impact, and investment implications.

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence stress test summary>",
  "scenarios": [
    {
      "name": "Base Stress",
      "description": "...",
      "triggers": ["..."],
      "probability": 0.0,
      "revenue_impact": "...",
      "valuation_impact": "...",
      "recovery_likelihood": "high|medium|low|none",
      "investment_implication": "..."
    },
    {
      "name": "Severe Stress",
      "description": "...",
      "triggers": ["..."],
      "probability": 0.0,
      "revenue_impact": "...",
      "valuation_impact": "...",
      "recovery_likelihood": "high|medium|low|none",
      "investment_implication": "..."
    },
    {
      "name": "Catastrophic",
      "description": "...",
      "triggers": ["..."],
      "probability": 0.0,
      "revenue_impact": "...",
      "valuation_impact": "...",
      "recovery_likelihood": "none",
      "investment_implication": "..."
    }
  ],
  "key_vulnerabilities": ["<vulnerability1>"],
  "risk_mitigants": ["<mitigant1>"],
  "expected_loss_estimate": "...",
  "stress_test_conclusion": "pass|watch|fail",
  "confidence_score": 0.0
}
"""


def run(state: DueDiligenceState) -> dict:
    context = compact({
        "financial":   slim_financial(state.get("financial_report")),
        "bear_case":   slim_bear(state.get("bear_case")),
        "red_flags":   slim_red_flags(state.get("red_flags")),
        "valuation":   slim_valuation(state.get("valuation")),
        "verification":slim_verification(state.get("verification")),
    })

    user_message = (
        f"Company: {state['company_name']}\n\n"
        f"Prior Analysis:\n{context}\n\n"
        "Conduct a rigorous stress test. Model three downside scenarios with quantified impact.\n\n"
        "LIVE DATA REQUIREMENT: Use web_search and news_search to check for any recent "
        "negative developments, competitive threats, or macro changes that affect your scenarios. "
        "Valuation impact figures (e.g. '−40% to stock price') must be anchored to the "
        "current stock price or market cap confirmed in prior analysis — not training memory.\n\n"
        "Return the specified JSON object."
    )

    result = run_agent(
        agent_type="stress_test",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("stress_test"),
        language=state.get("language", "English"),
    )

    return {"stress_test": result}
