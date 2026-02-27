"""Phase 1 — Market Research agent."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior market research analyst conducting investment due diligence.
Your task: analyze the company's market opportunity, competitive landscape, and macro environment.

Focus on:
1. Total Addressable Market (TAM), Serviceable Addressable Market (SAM), market growth rate
2. Competitive landscape — direct competitors, indirect substitutes, market share
3. Company's competitive positioning and differentiation
4. Macro / regulatory tailwinds and headwinds
5. Industry trends (technology shifts, consolidation, disruption risks)
6. Customer segments and demand drivers
7. Barriers to entry and defensibility of market position

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary>",
  "market_size": {
    "tam": "...", "sam": "...", "growth_rate": "...",
    "confidence": "high|medium|low", "sources": ["..."]
  },
  "competitive_landscape": {
    "direct_competitors": [{"name": "...", "position": "...", "threat_level": "high|medium|low"}],
    "market_share_estimate": "...",
    "differentiation": "..."
  },
  "macro_factors": {
    "tailwinds": ["..."],
    "headwinds": ["..."],
    "regulatory_risks": ["..."]
  },
  "industry_trends": ["<trend1>", "<trend2>"],
  "barriers_to_entry": ["<barrier1>", "<barrier2>"],
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
        "Conduct thorough market research for this company. "
        "Identify the market size, key competitors, competitive positioning, "
        "and macro environment. Return your findings as the specified JSON object."
    )

    result = run_agent(
        agent_type="market_research",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("market_research"),
        language=state.get("language", "English"),
    )

    return {"market_report": result}
