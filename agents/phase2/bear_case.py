"""Phase 2 — Bear Case agent (strongest risk thesis)."""
from __future__ import annotations

import json

from graph.state import DueDiligenceState
from agents.base import run_agent
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a bearish investment analyst tasked with stress-testing a potential investment.
You have access to Phase 1 research reports on a company.
Your role: surface the most credible reasons NOT to invest, identify potential fatal flaws,
and construct the worst-case scenario with realistic probability estimates.

Be rigorous, specific, and evidence-based. Assign probabilities.

Return a JSON object with this exact structure:
{
  "bear_thesis_title": "<punchy one-liner>",
  "core_bear_thesis": "<2-3 paragraph bear thesis>",
  "key_risks": [
    {"risk": "...", "likelihood": "high|medium|low", "severity": "fatal|major|moderate", "mitigation": "..."}
  ],
  "downside_scenario": {
    "description": "...",
    "downside_triggers": ["..."],
    "potential_loss": "...",
    "probability": 0.0
  },
  "structural_weaknesses": ["<weakness1>"],
  "competitive_threats": ["<threat1>"],
  "management_concerns": ["<concern1>"],
  "financial_concerns": ["<concern1>"],
  "confidence_score": 0.0
}
"""


def run(state: DueDiligenceState) -> dict:
    phase1_context = json.dumps({
        "financial_report": state.get("financial_report"),
        "market_report": state.get("market_report"),
        "legal_report": state.get("legal_report"),
        "management_report": state.get("management_report"),
        "tech_report": state.get("tech_report"),
    }, indent=2)

    user_message = (
        f"Company: {state['company_name']}\n\n"
        f"Phase 1 Research Reports:\n{phase1_context}\n\n"
        "Based on the research above, construct the strongest possible bear case. "
        "Identify real risks that could cause this investment to fail. "
        "Return the specified JSON object."
    )

    result = run_agent(
        agent_type="bear_case",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("bear_case"),
    )

    return {"bear_case": result}
