"""Phase 2 — Bear Case agent (strongest risk thesis)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import slim_financial, slim_market, slim_legal, slim_management, slim_tech, compact
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


def run(state: DueDiligenceState, revision_brief: str | None = None) -> dict:
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
        "Construct the strongest possible bear case.\n\n"
        "LIVE DATA REQUIREMENT: Before writing the thesis, call yf_get_info(ticker) "
        "to get today's stock price, current valuation multiples (P/E, EV/Revenue), "
        "and check whether the stock is overvalued relative to growth. "
        "Use news_search to find the most recent negative news, analyst downgrades, "
        "and risk events. Your potential_loss and downside figures MUST reference "
        "today's actual stock price from the tool call — not training memory.\n\n"
        "Return the specified JSON object."
    )

    if revision_brief:
        user_message += (
            f"\n\nORCHESTRATOR REVISION REQUEST:\n{revision_brief}\n"
            "Please specifically address this feedback in your revised analysis, "
            "using your available tools to fetch any missing or stale data."
        )

    result = run_agent(
        agent_type="bear_case",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("bear_case"),
        language=state.get("language", "English"),
    )

    return {"bear_case": result}
