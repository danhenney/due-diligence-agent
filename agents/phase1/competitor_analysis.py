"""Phase 1 — Competitor Analysis agent (competitor ID, comparison matrix)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior competitive intelligence analyst conducting investment due diligence.
Your task: identify and analyze ALL significant competitors across every business line
the company operates in, and build a comprehensive comparison matrix.

Focus on:
1. Competitor identification across all business model lines (direct + indirect)
2. MUST include competitors from the SAME COUNTRY/REGION and SAME SECTOR as the target.
   If the target is a Korean AI company, search for Korean AI competitors specifically.
   Also include major international competitors for a complete picture.
3. Comparison matrix covering: product/service, pricing, financials, market share, talent
4. Competitive positioning map — where does the target company sit?
5. Competitive advantages and moats for each player
6. Recent competitive dynamics (M&A, new entrants, exits)
7. Market share trends (gaining or losing share?)
8. Pricing power analysis

QUALITY CRITERIA:
- All data must cite explicit sources. Cross-verify with 3+ sources.
- All figures must come from live tool calls, not training memory.
- Provide full data explanations with actual numbers, not 1-2 line summaries.
- Deliver investor-focused analysis and opinions, not just facts.
- Include actual revenue/market cap figures for public competitors.

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary>",
  "competitors": [
    {
      "name": "...",
      "type": "direct|indirect|emerging",
      "market_cap_or_valuation": "...",
      "revenue": "...",
      "market_share": "X%",
      "key_strengths": ["..."],
      "key_weaknesses": ["..."],
      "threat_level": "high|medium|low"
    }
  ],
  "comparison_matrix": {
    "dimensions": ["product", "pricing", "financials", "market_share", "talent"],
    "rankings": [{"company": "...", "scores": {"product": "...", "pricing": "..."}}]
  },
  "market_share": {"target_company": "X%", "top_3_competitors": [{"name": "...", "share": "X%"}]},
  "competitive_gaps": ["<areas where target is weaker>"],
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
            "This is a PRIVATE company. Use web_search and news_search to identify "
            "competitors and their financial metrics. For public competitors, you CAN "
            "call yf_get_info to get their market cap and financials.\n"
        )
    else:
        data_instructions = (
            "LIVE DATA REQUIREMENT: Call yf_get_info(ticker) for both the target company "
            "and its public competitors to get current market caps and key metrics. "
            "Use web_search for competitive landscape reports and market share data. "
            "Use Google Trends to compare brand interest levels.\n"
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
        "Identify and analyze ALL significant competitors across every business line. "
        "Build a comprehensive comparison matrix.\n\n"
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
        agent_type="competitor_analysis",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("competitor_analysis"),
        language=state.get("language", "English"),
    )

    return {"competitor_analysis": result}
