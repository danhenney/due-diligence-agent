"""Phase 2 — R&A Synthesis agent (core investment arguments + scorecard)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import (
    slim_market_analysis, slim_competitor, slim_financial_analysis,
    slim_tech, slim_legal_regulatory, slim_team, compact,
)
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior investment analyst synthesizing all Phase 1 research into a cohesive
investment narrative. Your task: distill 6 specialist reports into 3-5 core investment
arguments and build an attractiveness scorecard.

Focus on:
1. Core Investment Arguments (3-5) — the most compelling reasons to invest or not
   - Each argument must be supported by specific data from Phase 1 reports
   - Rank arguments by conviction level (high/medium/low)
2. Attractiveness Scorecard covering three dimensions:
   - CDD (Commercial Due Diligence): market size, growth, competitive position, customer quality
   - LDD (Legal Due Diligence): regulatory risks, litigation, IP, governance
   - FDD (Financial Due Diligence): revenue quality, profitability, cash flow, valuation
   - Score each 1-10 with specific justification
3. Key Findings Summary — most important discoveries across all reports
4. Cross-report consistency check — do the 6 reports tell a consistent story?

QUALITY CRITERIA:
- All data must cite explicit sources. Cross-verify with 3+ sources.
- Provide full data explanations with actual numbers, not 1-2 line summaries.
- Deliver investor-focused analysis and opinions, not just facts.
- If Phase 1 data has gaps, flag them explicitly.

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary>",
  "core_investment_arguments": [
    {
      "argument": "...",
      "direction": "bullish|bearish|neutral",
      "supporting_evidence": ["..."],
      "conviction": "high|medium|low"
    }
  ],
  "attractiveness_scorecard": {
    "cdd": {"score": 0, "justification": "..."},
    "ldd": {"score": 0, "justification": "..."},
    "fdd": {"score": 0, "justification": "..."},
    "total": 0
  },
  "key_findings": ["..."],
  "cross_report_consistency": {"assessment": "...", "inconsistencies": ["..."]},
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
        "Synthesize all Phase 1 findings into core investment arguments and "
        "build the CDD/LDD/FDD attractiveness scorecard.\n\n"
        "SOURCE TRACKING: Include sources from Phase 1 data and any new tool calls.\n\n"
        "Return the specified JSON object."
    )

    if revision_brief:
        user_message += (
            f"\n\nREVISION REQUEST:\n{revision_brief}\n"
            "Please specifically address this feedback in your revised analysis."
        )

    result = run_agent(
        agent_type="ra_synthesis",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("ra_synthesis"),
        language=state.get("language", "English"),
    )

    return {"ra_synthesis": result}
