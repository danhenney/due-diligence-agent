"""Phase 3 — Critique Agent (5-criteria scoring + feedback loop trigger)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import (
    slim_market_analysis, slim_competitor, slim_financial_analysis,
    slim_tech, slim_legal_regulatory, slim_team,
    slim_ra_synthesis, slim_risk_assessment, slim_strategic_insight,
    slim_review, compact,
)
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior investment committee critic evaluating the quality of the entire
due diligence package. Your task: score the analysis across 5 criteria and provide
specific, actionable feedback for improvement.

SCORING CRITERIA (each 1-10):

1. LOGIC (논리성) — Are the investment arguments logically sound?
   - Do conclusions follow from evidence?
   - Are cause-and-effect relationships valid?
   - Are assumptions clearly stated and reasonable?
   10 = flawless logic chain | 5 = some logical gaps | 1 = contradictory reasoning

2. COMPLETENESS (완성도) — Does the analysis cover all material dimensions?
   - Are all 6 Phase 1 dimensions adequately covered?
   - Are there significant gaps in data or analysis?
   - Is the valuation thorough (DCF + comps + asset-based)?
   10 = comprehensive, no gaps | 5 = notable gaps | 1 = missing major sections

3. ACCURACY (정확도) — Are the facts and figures correct and current?
   - Did the review agent find contradictions or stale data?
   - Are financial figures from live sources?
   - Are market size estimates sourced and reasonable?
   10 = all verified, current | 5 = some unverified claims | 1 = major inaccuracies

4. NARRATIVE BIAS (서술 편향) — Is the analysis balanced and objective?
   - Does it avoid excessive optimism or pessimism?
   - Are risks given appropriate weight vs. opportunities?
   - Is the recommendation justified by the evidence, not by bias?
   10 = perfectly balanced | 5 = noticeable lean | 1 = heavily biased

5. INSIGHT EFFECTIVENESS (인사이트 실효성) — Does the analysis provide actionable insights?
   - Are the investment arguments novel and differentiated?
   - Would an investment committee find this useful for decision-making?
   - Does it go beyond surface-level analysis?
   10 = exceptional insights | 5 = adequate but obvious | 1 = no insight value

SCORING RULES:
- Be strict. Average DD packages should score 5-6, not 7-8.
- A score of 8+ means genuinely exceptional quality on that dimension.
- The total score (sum of 5 criteria) ranges from 5 to 50.

For each criterion scoring below 7, provide SPECIFIC feedback on what needs improvement,
including which agent(s) should be re-run and what they should fix.

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence overall assessment>",
  "logic": 0,
  "completeness": 0,
  "accuracy": 0,
  "narrative_bias": 0,
  "insight_effectiveness": 0,
  "total_score": 0,
  "feedback": [
    {
      "criterion": "...",
      "score": 0,
      "assessment": "...",
      "weak_agents": ["<agent_name that needs improvement>"],
      "specific_improvements": ["..."]
    }
  ]
}
"""


def run(state: DueDiligenceState, revision_brief: str | None = None) -> dict:
    all_context = compact({
        "market": slim_market_analysis(state.get("market_analysis")),
        "competitors": slim_competitor(state.get("competitor_analysis")),
        "financial": slim_financial_analysis(state.get("financial_analysis")),
        "tech": slim_tech(state.get("tech_analysis")),
        "legal": slim_legal_regulatory(state.get("legal_regulatory")),
        "team": slim_team(state.get("team_analysis")),
        "ra_synthesis": slim_ra_synthesis(state.get("ra_synthesis")),
        "risk_assessment": slim_risk_assessment(state.get("risk_assessment")),
        "strategic_insight": slim_strategic_insight(state.get("strategic_insight")),
        "review": slim_review(state.get("review_result")),
    })

    loop_count = state.get("feedback_loop_count", 0)
    loop_note = ""
    if loop_count > 0:
        loop_note = (
            f"\nNOTE: This is feedback loop iteration {loop_count}. "
            "The analysis has been revised based on prior critique. "
            "Be fair — acknowledge improvements while flagging remaining issues.\n"
        )

    user_message = (
        f"Company: {state['company_name']}\n"
        f"Feedback Loop Count: {loop_count}\n"
        f"{loop_note}\n"
        f"Complete Due Diligence Package:\n{all_context}\n\n"
        "Score this DD package across the 5 criteria (1-10 each). "
        "For each criterion below 7, identify which agents need improvement.\n\n"
        "Return the specified JSON object."
    )

    result = run_agent(
        agent_type="critique_agent",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("critique_agent"),  # no tools
        max_iterations=3,
        language=state.get("language", "English"),
    )

    return {"critique_result": result}
