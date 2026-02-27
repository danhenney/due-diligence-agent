"""Phase 1 — Management Team agent."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior talent and organizational analyst conducting investment due diligence.
Your task: assess the quality and completeness of the management team and organizational structure.

Focus on:
1. Founder/CEO background, track record, and domain expertise
2. Key executive team (CFO, CTO, COO) — experience and prior outcomes
3. Board composition — independence, expertise, investor representation
4. Team completeness — critical gaps in leadership
5. Employee count, growth trajectory, Glassdoor/LinkedIn signals
6. Founder equity retention and key-person dependency risk
7. Culture and execution signals (press, customer reviews, employee reviews)
8. Advisor and investor quality

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary>",
  "founders": [
    {"name": "...", "role": "...", "background": "...", "prior_exits": "...", "assessment": "strong|adequate|weak"}
  ],
  "executive_team": [
    {"name": "...", "role": "...", "background": "...", "notable_experience": "..."}
  ],
  "board": {
    "composition": "...",
    "notable_members": ["..."],
    "independence_quality": "strong|adequate|weak"
  },
  "team_gaps": ["<gap1>"],
  "key_person_risk": "high|medium|low",
  "culture_signals": {"positive": ["..."], "negative": ["..."]},
  "organizational_maturity": "early|scaling|mature",
  "red_flags": ["<flag1>"],
  "strengths": ["<strength1>"],
  "confidence_score": 0.0,
  "data_sources": ["<source1>"]
}
"""


def run(state: DueDiligenceState, revision_brief: str | None = None) -> dict:
    company = state["company_name"]
    url = state.get("company_url") or ""

    user_message = (
        f"Company: {company}\n"
        f"URL: {url}\n\n"
        "Assess the management team, founders, board, and organizational structure. "
        "Search for leadership backgrounds, track records, and culture signals. "
        "Return your findings as the specified JSON object."
    )

    if revision_brief:
        user_message += (
            f"\n\nORCHESTRATOR REVISION REQUEST:\n{revision_brief}\n"
            "Please specifically address this feedback in your revised analysis, "
            "using your available tools to fetch any missing or stale data."
        )

    result = run_agent(
        agent_type="management_team",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("management_team"),
        language=state.get("language", "English"),
    )

    return {"management_report": result}
