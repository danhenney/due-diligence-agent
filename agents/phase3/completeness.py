"""Phase 3 — Completeness Check agent (coverage gap checker)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import (
    slim_financial, slim_market, slim_legal, slim_management, slim_tech,
    slim_bull, slim_bear, slim_valuation, slim_red_flags,
    slim_verification, slim_stress, compact,
)
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


def run(state: DueDiligenceState, revision_brief: str | None = None) -> dict:
    full_context = compact({
        "financial":   slim_financial(state.get("financial_report")),
        "market":      slim_market(state.get("market_report")),
        "legal":       slim_legal(state.get("legal_report")),
        "management":  slim_management(state.get("management_report")),
        "tech":        slim_tech(state.get("tech_report")),
        "bull_case":   slim_bull(state.get("bull_case")),
        "bear_case":   slim_bear(state.get("bear_case")),
        "valuation":   slim_valuation(state.get("valuation")),
        "red_flags":   slim_red_flags(state.get("red_flags")),
        "verification":slim_verification(state.get("verification")),
        "stress_test": slim_stress(state.get("stress_test")),
    })

    user_message = (
        f"Company: {state['company_name']}\n\n"
        f"Full Due Diligence Package:\n{full_context}\n\n"
        "Assess the completeness of this due diligence. Identify gaps and determine "
        "readiness for a final recommendation. Return the specified JSON object."
    )

    if revision_brief:
        user_message += (
            f"\n\nORCHESTRATOR REVISION REQUEST:\n{revision_brief}\n"
            "Please specifically address this feedback in your revised analysis, "
            "using your available tools to fetch any missing or stale data."
        )

    result = run_agent(
        agent_type="completeness",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("completeness"),
        language=state.get("language", "English"),
    )

    return {"completeness": result}
