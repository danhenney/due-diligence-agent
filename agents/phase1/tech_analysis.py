"""Phase 1 — Tech Analysis agent (core tech, IP/patents, maturity)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior technology analyst conducting investment due diligence.
Your task: evaluate the company's core technology stack, intellectual property,
technical maturity relative to competitors, and present findings in investor-friendly language.

Focus on:
1. Core technology inventory — what technologies power each business line?
2. IP and patent portfolio — number of patents, key patents, pending applications
3. Technical moat assessment — how defensible is the technology?
4. Tech maturity vs. competitors — where does the company stand?
5. Scalability and architecture — can the tech scale 10x?
6. Open source footprint — GitHub activity, community engagement
7. Technical debt and risks — legacy systems, vendor lock-in
8. LATEST product launches and models — search for the most recent announcements,
   new model releases, and product updates. These are critical for valuation.
8. R&D investment levels — % of revenue, team size, hiring trends

QUALITY CRITERIA:
- All data must cite explicit sources. Cross-verify with 3+ sources.
- All figures must come from live tool calls, not training memory.
- Provide full data explanations with actual numbers, not 1-2 line summaries.
- Deliver investor-focused analysis — translate technical details into business impact.
- Use investor-friendly language, not engineering jargon.

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary>",
  "core_technologies": [
    {"technology": "...", "business_line": "...", "maturity": "emerging|growth|mature", "moat_strength": "high|medium|low"}
  ],
  "ip_patents": {
    "total_patents": "...",
    "key_patents": ["..."],
    "pending_applications": "...",
    "ip_strategy_assessment": "..."
  },
  "tech_maturity": {
    "overall_stage": "early|growth|mature|declining",
    "vs_competitors": "leading|on_par|lagging",
    "key_advantages": ["..."],
    "key_gaps": ["..."]
  },
  "competitive_comparison": [
    {"competitor": "...", "tech_comparison": "...", "advantage": "target|competitor|neutral"}
  ],
  "scalability": {"assessment": "...", "constraints": ["..."]},
  "rd_investment": {"rd_spend": "...", "percent_of_revenue": "...", "trend": "..."},
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
            "This is a PRIVATE company. Use web_search and news_search for technology "
            "analysis. Search GitHub for open source repos. Search patents database.\n"
        )
    else:
        data_instructions = (
            "Use web_search for technology stack analysis and R&D spending. "
            "Search GitHub for the company's open source repos and activity. "
            "Search the patent database for IP portfolio. "
            "Use news_search for recent technology announcements.\n"
        )

    if url:
        data_instructions += (
            f"\nCRITICAL: Search the company's own website for their latest products "
            f"and models. Use web_search with queries like '{company} latest model 2026' "
            f"or '{company} new product launch'. The company URL is {url} — search for "
            f"product pages. Missing a recently launched product is a major oversight.\n"
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
        "Conduct a thorough technology analysis of this company.\n\n"
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
        agent_type="tech_analysis",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("tech_analysis"),
        language=state.get("language", "English"),
    )

    return {"tech_analysis": result}
