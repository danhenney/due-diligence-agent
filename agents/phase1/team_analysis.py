"""Phase 1 — Team Analysis agent (leadership profiles, capability analysis)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import build_doc_instructions
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior organizational and leadership analyst conducting investment due diligence.
Evaluate the leadership team's capability to execute the company's strategy across ALL
business lines. This section directly informs key-person risk in the investment decision.

LEADERSHIP PROFILES (MANDATORY — list EVERY executive):
1. CEO/founder, C-suite, and ALL key executives — do NOT skip anyone.
   For EACH person: name, title, education, prior companies, domain expertise,
   track record (specific achievements with numbers — revenue grown, products launched,
   exits completed), tenure at company, industry experience in years.
2. Board of directors: composition, independence ratio, relevant expertise,
   any conflicts of interest, notable board members and their networks.
3. Advisory board (if any): key advisors and their strategic value.

CAPABILITY ASSESSMENT:
4. Does the team have the right skills for the NEXT growth phase?
   Map team capabilities to each business model:
   - Does BM #1 have the right technical leadership?
   - Does BM #2 have the right commercial/sales leadership?
5. Functional coverage gaps: sales, engineering, operations, finance, legal, HR.
   For each gap, assess severity (critical/moderate/minor) and whether hiring is in progress.
6. Strategic vision: is leadership aligned on direction? Any public disagreements?

KEY PERSON RISK:
7. Who are the irreplaceable people? What happens if they leave?
8. Succession planning: is there a documented plan? Who are the #2s?
9. Equity vesting schedules: are key people locked in or free to leave?

DEPARTURE HISTORY:
10. All executive departures in the last 3 years: who, when, why (voluntary vs forced),
    and what was the impact on the company.

ORGANIZATIONAL HEALTH:
11. Employee count and growth trend (YoY)
12. Employee sentiment: Glassdoor rating, Blind reviews, social media signals
13. Hiring velocity: is the company attracting top talent? Any hiring freezes?
14. Compensation competitiveness: how does pay compare to market?
15. Insider ownership: do executives have meaningful skin-in-the-game?

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary connecting team quality to investment thesis>",
  "leadership_profiles": [
    {
      "name": "...",
      "title": "...",
      "background": "...",
      "track_record": "...",
      "tenure": "...",
      "domain_expertise": "...",
      "assessment": "strong|adequate|weak",
      "assessment_reasoning": "..."
    }
  ],
  "board": {
    "members": [{"name": "...", "role": "...", "independence": "independent|non_independent", "expertise": "..."}],
    "independence_ratio": "...",
    "assessment": "strong|adequate|weak"
  },
  "capability_assessment": {
    "strategic_vision": "...",
    "execution_ability": "...",
    "functional_gaps": [{"function": "...", "severity": "critical|moderate|minor", "hiring_status": "..."}],
    "bm_coverage": [{"business_line": "...", "leadership_quality": "strong|adequate|weak", "gap": "..."}],
    "overall": "strong|adequate|weak"
  },
  "departure_history": [
    {"name": "...", "role": "...", "departure_date": "...", "reason": "voluntary|forced|retirement", "impact": "..."}
  ],
  "key_person_risk": {"level": "high|medium|low", "critical_people": ["..."], "succession_plan": "...", "mitigants": ["..."]},
  "culture_signals": {"employee_count": "...", "yoy_growth": "...", "glassdoor_rating": "...", "hiring_trend": "...", "sentiment": "..."},
  "compensation": {"insider_ownership": "...", "equity_alignment": "...", "market_competitiveness": "..."},
  "red_flags": ["..."],
  "strengths": ["..."],
  "confidence_score": 0.0,
  "sources": [{"label": "...", "url": "...", "tool": "..."}]
}
"""


def run(state: DueDiligenceState, revision_brief: str | None = None) -> dict:
    company = state["company_name"]
    url = state.get("company_url") or ""
    docs = state.get("uploaded_docs") or []
    is_public = state.get("is_public", True)

    if is_public is False:
        data_instructions = (
            "PRIVATE company — leadership info may be limited. "
            "Use web_search for leadership bios, LinkedIn profiles (via web), "
            "executive departures, and organizational news. "
            "Uploaded documents may contain team bios — extract ALL names and details.\n"
        )
    else:
        data_instructions = (
            "Use web_search for leadership bios, LinkedIn profiles (via web), "
            "executive departures, Glassdoor ratings, and organizational news. "
            "Use news_search for recent leadership changes and culture signals. "
            "Check proxy statements for compensation and insider ownership.\n"
        )

    doc_note = build_doc_instructions(docs, agent_focus="team")

    user_message = (
        f"Company: {company}\nURL: {url}{doc_note}\n\n"
        "Conduct a thorough leadership and team analysis.\n\n"
        f"{data_instructions}\n"
        "SOURCE TRACKING: For every tool call that returns a URL or source_url, "
        "include it in your sources array. Each source needs label, url, and tool name.\n\n"
        "Return your findings as the specified JSON object."
    )

    if revision_brief:
        user_message += (
            f"\n\nREVISION REQUEST:\n{revision_brief}\n"
            "Please specifically address this feedback in your revised analysis."
        )

    result = run_agent(
        agent_type="team_analysis",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("team_analysis"),
        max_iterations=15,
        language=state.get("language", "English"),
    )

    return {"team_analysis": result}
