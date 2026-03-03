"""Phase 2 — Strategic Insight agent (INVEST/WATCH/PASS + synergy analysis)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import (
    slim_market_analysis, slim_competitor, slim_financial_analysis,
    slim_tech, slim_legal_regulatory, slim_team,
    slim_ra_synthesis, slim_risk_assessment, compact,
)
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior investment strategist rendering a preliminary investment decision.
You have access to all Phase 1 research AND the R&A Synthesis and Risk Assessment.

Your task:
1. Render a clear INVEST / WATCH / PASS recommendation with detailed rationale
2. Provide synergy analysis — how does this investment fit a portfolio?
3. Identify key conditions that would change the recommendation
4. Outline the investment timeline and exit strategy considerations

RECOMMENDATION THRESHOLDS — be decisive, not conservative:
- INVEST: Compelling evidence of value creation, manageable risks, positive trend,
  upside > 15%. Do NOT downgrade to WATCH just because uncertainty exists.
  Established companies with solid financials should generally be INVEST or PASS.
- WATCH: Genuinely mixed signals where bull and bear cases are roughly equal,
  OR material unresolved data gaps. WATCH is NOT the safe default.
- PASS: Risks clearly dominate — declining fundamentals, fatal red flags, no margin of safety.

CRITICAL ANTI-BIAS NOTE: LLMs systematically over-recommend WATCH because it feels "safe".
Fight this tendency. Ask yourself: "If I had to bet my own money, would I invest or not?"

QUALITY CRITERIA:
- All data must cite explicit sources. Cross-verify with 3+ sources.
- Provide full data explanations with actual numbers, not 1-2 line summaries.
- Deliver investor-focused analysis and opinions, not just facts.

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary>",
  "recommendation": "INVEST|WATCH|PASS",
  "rationale": "<2-3 paragraph detailed rationale>",
  "key_arguments_for": ["..."],
  "key_arguments_against": ["..."],
  "synergy_analysis": {
    "portfolio_fit": "...",
    "strategic_value": "...",
    "exit_considerations": "..."
  },
  "key_conditions": [
    {"condition": "...", "if_met": "strengthens|weakens thesis", "timeline": "..."}
  ],
  "investment_timeline": "...",
  "confidence_score": 0.0,
  "sources": [{"label": "...", "url": "...", "tool": "..."}]
}
"""


def run(state: DueDiligenceState, revision_brief: str | None = None) -> dict:
    # Strategic insight needs both Phase 1 context AND Phase 2 outputs
    phase1_context = state.get("phase1_context") or compact({
        "market": slim_market_analysis(state.get("market_analysis")),
        "competitors": slim_competitor(state.get("competitor_analysis")),
        "financial": slim_financial_analysis(state.get("financial_analysis")),
        "tech": slim_tech(state.get("tech_analysis")),
        "legal": slim_legal_regulatory(state.get("legal_regulatory")),
        "team": slim_team(state.get("team_analysis")),
    })

    phase2_context = compact({
        "ra_synthesis": slim_ra_synthesis(state.get("ra_synthesis")),
        "risk_assessment": slim_risk_assessment(state.get("risk_assessment")),
    })

    is_public = state.get("is_public", True)
    private_note = ""
    if is_public is False:
        private_note = (
            "NOTE: This is a PRIVATE company. Do NOT call yf_get_info — it will fail. "
            "Use web_search for any additional data needed.\n\n"
        )

    user_message = (
        f"Company: {state['company_name']}\n\n"
        f"{private_note}"
        f"Phase 1 Research:\n{phase1_context}\n\n"
        f"Phase 2 Synthesis & Risk:\n{phase2_context}\n\n"
        "Render your investment recommendation (INVEST/WATCH/PASS) with detailed "
        "rationale and synergy analysis.\n\n"
        "SOURCE TRACKING: Include sources from prior data and any new tool calls.\n\n"
        "Return the specified JSON object."
    )

    if revision_brief:
        user_message += (
            f"\n\nREVISION REQUEST:\n{revision_brief}\n"
            "Please specifically address this feedback in your revised analysis."
        )

    result = run_agent(
        agent_type="strategic_insight",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("strategic_insight"),
        language=state.get("language", "English"),
    )

    return {"strategic_insight": result}
