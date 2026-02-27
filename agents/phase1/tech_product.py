"""Phase 1 — Technology & Product agent."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior technology and product analyst conducting investment due diligence.
Your task: evaluate the company's product maturity, technical moat, and scalability.

Focus on:
1. Core product/service description and value proposition
2. Product maturity stage (MVP, early traction, growth, mature)
3. Technical differentiation and moat (proprietary tech, patents, data advantages)
4. Scalability of technology stack (architecture, infrastructure)
5. Product-market fit signals (NPS, retention, usage metrics)
6. Development velocity and engineering team quality
7. Technical debt and security posture
8. Integration ecosystem and platform stickiness
9. AI/ML usage (if applicable) — competitive advantage or table-stakes?

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary>",
  "product_overview": {
    "core_product": "...",
    "value_proposition": "...",
    "maturity_stage": "mvp|early_traction|growth|mature"
  },
  "technical_moat": {
    "differentiators": ["..."],
    "moat_strength": "strong|moderate|weak",
    "sustainability": "..."
  },
  "scalability": {
    "architecture_quality": "...",
    "known_limitations": ["..."],
    "scalability_rating": "high|medium|low"
  },
  "product_market_fit": {
    "signals": ["..."],
    "pmf_strength": "strong|emerging|weak|unknown"
  },
  "engineering_team": {
    "size_estimate": "...",
    "quality_signals": ["..."]
  },
  "technical_risks": ["<risk1>"],
  "red_flags": ["<flag1>"],
  "strengths": ["<strength1>"],
  "confidence_score": 0.0,
  "data_sources": ["<source1>"]
}
"""


def run(state: DueDiligenceState) -> dict:
    company = state["company_name"]
    url = state.get("company_url") or ""

    user_message = (
        f"Company: {company}\n"
        f"URL: {url}\n\n"
        "Conduct a thorough technology and product assessment. "
        "Evaluate product maturity, technical differentiation, scalability, "
        "and product-market fit signals. "
        "Return your findings as the specified JSON object."
    )

    result = run_agent(
        agent_type="tech_product",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("tech_product"),
    )

    return {"tech_report": result}
