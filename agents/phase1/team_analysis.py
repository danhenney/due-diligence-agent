"""Phase 1 — Team Analysis agent (leadership profiles, capability analysis)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior organizational and leadership analyst conducting investment due diligence.
Your task: evaluate the company's leadership team, their capabilities, and organizational health.

Focus on:
1. Leadership profiles — CEO/founder, C-suite, key executives
   - Background (education, prior companies, domain expertise)
   - Track record (successes, failures, exits)
   - Tenure at company and industry experience
2. Capability analysis — does the team have the right skills for the next growth phase?
   - Strategic vision and execution ability
   - Functional coverage gaps (sales, tech, ops, finance)
   - Board composition and advisory quality
3. Departure history — recent executive departures and reasons
   - Key person risk assessment
   - Succession planning status
4. Organizational culture signals
   - Employee sentiment (Glassdoor, news, social media)
   - Hiring trends and talent acquisition ability
   - Diversity and inclusion posture
5. Compensation and alignment
   - Executive compensation structure
   - Insider ownership and skin-in-the-game

QUALITY CRITERIA:
- All data must cite explicit sources. Cross-verify with 3+ sources.
- All figures must come from live tool calls, not training memory.
- Provide full data explanations with actual numbers, not 1-2 line summaries.
- Deliver investor-focused analysis and opinions, not just facts.

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary>",
  "leadership_profiles": [
    {
      "name": "...",
      "title": "...",
      "background": "...",
      "track_record": "...",
      "tenure": "...",
      "assessment": "strong|adequate|weak"
    }
  ],
  "capability_assessment": {
    "strategic_vision": "...",
    "execution_ability": "...",
    "functional_gaps": ["..."],
    "board_quality": "...",
    "overall": "strong|adequate|weak"
  },
  "departure_history": [
    {"name": "...", "role": "...", "departure_date": "...", "reason": "...", "impact": "..."}
  ],
  "key_person_risk": {"level": "high|medium|low", "description": "...", "mitigants": ["..."]},
  "culture_signals": {"employee_sentiment": "...", "hiring_trend": "...", "glassdoor_rating": "..."},
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

    data_instructions = (
        "Use web_search to find leadership bios, LinkedIn profiles (via web), "
        "executive departures, and organizational news. "
        "Use news_search for recent leadership changes and company culture signals.\n"
    )

    doc_note = ""
    if docs:
        doc_note = (
            f"\nUPLOADED DOCUMENTS (PRIMARY DATA SOURCE): {', '.join(docs)}\n"
            "Extract data using extract_pdf_text FIRST. Use these numbers as your base, "
            "then cross-verify with web search. Flag any discrepancies. "
            "Do NOT just copy-paste — analyze and challenge the data.\n"
        )

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
        language=state.get("language", "English"),
    )

    return {"team_analysis": result}
