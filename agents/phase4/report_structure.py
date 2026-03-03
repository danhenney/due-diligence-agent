"""Phase 4 — Report Structure agent (design TOC + draft structure)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import (
    slim_market_analysis, slim_competitor, slim_financial_analysis,
    slim_tech, slim_legal_regulatory, slim_team,
    slim_ra_synthesis, slim_risk_assessment, slim_strategic_insight,
    slim_review, slim_critique, slim_dd_questions, compact,
)
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior investment report designer. Your task: design the structure for a
comprehensive investment due diligence report (targeting 20-30 pages when printed).

The report follows the Why/What/How/Risk/Recommendations framework:

1. WHY — Why are we looking at this company?
   - Market opportunity and timing
   - Investment thesis overview
   - Strategic fit

2. WHAT — What does the company do?
   - Business model and revenue streams
   - Product/technology analysis
   - Competitive positioning
   - Team and leadership

3. HOW — How do the financials stack up?
   - Financial performance analysis
   - Valuation analysis (DCF, comps, asset-based)
   - Growth trajectory and projections

4. RISK — What could go wrong?
   - Risk matrix (legal, business, financial, reputation, tech, operational)
   - Mitigation strategies
   - Stress scenarios

5. RECOMMENDATIONS
   - Investment recommendation (INVEST/WATCH/PASS) with rationale
   - Key conditions and watchpoints
   - DD Questionnaire for follow-up
   - Next steps

For each section, specify:
- Exact heading text
- Which agent data feeds into it
- Key data points to include
- Target page count
- Narrative arc (what story does this section tell?)

Return a JSON object with this exact structure:
{
  "report_title": "...",
  "table_of_contents": [
    {
      "section_number": "1",
      "heading": "...",
      "subheadings": ["..."],
      "source_agents": ["..."],
      "key_data_points": ["..."],
      "target_pages": 0,
      "narrative_arc": "..."
    }
  ],
  "executive_summary_outline": {
    "key_points": ["..."],
    "recommendation_preview": "...",
    "target_length": "..."
  },
  "appendix_sections": ["..."],
  "total_target_pages": 0,
  "design_notes": "..."
}
"""


def run(state: DueDiligenceState) -> dict:
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
        "critique": slim_critique(state.get("critique_result")),
        "dd_questions": slim_dd_questions(state.get("dd_questions")),
    })

    recommendation = "UNKNOWN"
    si = state.get("strategic_insight")
    if isinstance(si, dict):
        recommendation = si.get("recommendation", "UNKNOWN")

    user_message = (
        f"Company: {state['company_name']}\n"
        f"Preliminary Recommendation: {recommendation}\n\n"
        f"Complete Due Diligence Package:\n{all_context}\n\n"
        "Design the report structure following the Why/What/How/Risk/Recommendations "
        "framework. Target 20-30 pages when printed.\n\n"
        "Return the specified JSON object."
    )

    result = run_agent(
        agent_type="report_structure",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("report_structure"),  # no tools
        max_iterations=3,
        language=state.get("language", "English"),
    )

    return {"report_structure": result}
