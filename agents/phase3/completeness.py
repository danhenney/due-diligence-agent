"""Phase 3 — Completeness Check agent (coverage gap checker)."""
from __future__ import annotations

import json

from graph.state import DueDiligenceState
from agents.base import run_agent
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior due diligence quality assurance analyst.
You have access to ALL prior analysis from all phases.
Your task: assess the completeness and quality of the entire due diligence process,
identify coverage gaps, and determine if there is sufficient information to make
a final investment recommendation.

Evaluate completeness across:
1. Financial analysis — are key metrics covered?
2. Market analysis — is the opportunity well-defined?
3. Legal/compliance — are all material risks surfaced?
4. Management — is the team adequately assessed?
5. Technology — is the product/tech sufficiently understood?
6. Valuation — is the price/value assessment sound?
7. Risk — are all major risks identified and stress-tested?

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence completeness summary>",
  "coverage_scores": {
    "financial": 0.0,
    "market": 0.0,
    "legal": 0.0,
    "management": 0.0,
    "technology": 0.0,
    "valuation": 0.0,
    "risk": 0.0
  },
  "coverage_gaps": [
    {"area": "...", "gap": "...", "impact_on_decision": "high|medium|low"}
  ],
  "information_quality_issues": ["<issue1>"],
  "additional_diligence_recommended": [
    {"item": "...", "priority": "critical|high|medium|low", "rationale": "..."}
  ],
  "decision_readiness": "ready|needs_more_work|insufficient",
  "overall_completeness_score": 0.0,
  "confidence_in_recommendation": "high|medium|low"
}
"""


def run(state: DueDiligenceState) -> dict:
    full_context = json.dumps({
        "company_name": state["company_name"],
        "financial_report": state.get("financial_report"),
        "market_report": state.get("market_report"),
        "legal_report": state.get("legal_report"),
        "management_report": state.get("management_report"),
        "tech_report": state.get("tech_report"),
        "bull_case": state.get("bull_case"),
        "bear_case": state.get("bear_case"),
        "valuation": state.get("valuation"),
        "red_flags": state.get("red_flags"),
        "verification": state.get("verification"),
        "stress_test": state.get("stress_test"),
    }, indent=2)

    user_message = (
        f"Company: {state['company_name']}\n\n"
        f"Full Due Diligence Package:\n{full_context}\n\n"
        "Assess the completeness of this due diligence. Identify gaps and determine "
        "readiness for a final recommendation. Return the specified JSON object."
    )

    result = run_agent(
        agent_type="completeness",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("completeness"),
    )

    return {"completeness": result}
