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

The report MUST follow this exact 6-section framework:

1. 시장 및 산업 개괄 (Market & Industry Overview)
   - Macro environment and industry landscape
   - TAM/SAM/SOM with specific dollar figures
   - Market CAGR, trends, growth drivers
   - Geographic breakdown of opportunity
   - Regulatory environment overview
   - Source agents: market_analysis, legal_regulatory (regulatory context)

2. 타겟 개요 및 사업/제품 구조 (Target Overview & Business/Product Structure)
   - Company history, mission, and milestones
   - Business model and revenue streams
   - Product/service portfolio and technology stack
   - Core technology and IP assessment
   - DEDICATED SUBSECTION: Leadership team profiles (every person named)
   - Key person risk, capability gaps, culture signals
   - Source agents: tech_analysis, team_analysis

3. 성과 및 운영 지표 (Performance & Operating Metrics)
   - Revenue trends (5-year), growth rate, seasonality
   - Profitability metrics (gross/EBITDA/net margins)
   - Balance sheet strength, cash flow quality
   - Key financial ratios vs industry benchmarks
   - Source agents: financial_analysis

4. 경쟁 구도 및 포지셔닝 (Competitive Landscape & Positioning)
   - FULL competitor matrix with financials (every competitor listed)
   - Market share analysis and trends
   - Competitive advantages and moats
   - Competitive gaps and vulnerabilities
   - Source agents: competitor_analysis

5. 재무 현황/전망 및 가치평가 (Financial Status/Outlook & Valuation)
   - DCF valuation with FULLY REASONED assumptions (WACC breakdown, terminal growth)
   - Market-based valuation (domestic AND international comps)
   - External valuations comparison (analysts, funding rounds, third-party)
   - Fair value range (low/mid/high) and financial projections
   - Source agents: financial_analysis (valuation), ra_synthesis

6. 리스크 및 최종 의견/제언 (Risks & Final Opinion/Recommendations)
   - Risk matrix (legal, business, financial, tech, operational, reputational)
   - DEDICATED SUBSECTION: Legal/regulatory risks and litigation (every case listed)
   - Investment structure risks
   - INVEST/WATCH/PASS recommendation with rationale
   - Key conditions, watchpoints, DD questionnaire
   - Source agents: risk_assessment, legal_regulatory, strategic_insight, dd_questions

MANDATORY: Team, competitor, and legal/regulatory findings MUST each have their own
dedicated sections — do NOT merge them into brief mentions.

For each section, specify:
- Exact heading text (in the language of the report)
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
        "Design the report structure following the 6-section framework. "
        "Target 20-30 pages when printed.\n\n"
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
