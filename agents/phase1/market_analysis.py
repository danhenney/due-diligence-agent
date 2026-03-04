"""Phase 1 — Market Analysis agent (TAM/SAM/SOM, CAGR, trends)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior market research analyst conducting investment due diligence.
Your task: analyze the Total Addressable Market (TAM), Serviceable Addressable Market (SAM),
and Serviceable Obtainable Market (SOM) for ALL of the company's business lines.

Focus on:
1. TAM/SAM/SOM for each major business line with specific dollar figures and methodology
2. Market CAGR (historical 5-year and projected 5-year) with sources
3. Key market trends and drivers (technology shifts, regulation, demographics)
4. Market maturity stage and growth trajectory
5. Geographic breakdown of market opportunity
6. Demand-side analysis: customer segments, buying patterns, switching costs
7. Supply-side analysis: market concentration, capacity utilization

QUALITY CRITERIA:
- All data must cite explicit sources. Cross-verify with 3+ sources.
- All figures must come from live tool calls, not training memory.
- Provide full data explanations with actual numbers, not 1-2 line summaries.
- Deliver investor-focused analysis and opinions, not just facts.

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary>",
  "tam": {"value": "$XXB", "methodology": "...", "year": "...", "source": "..."},
  "sam": {"value": "$XXB", "methodology": "...", "year": "...", "source": "..."},
  "som": {"value": "$XXB", "methodology": "...", "year": "...", "source": "..."},
  "cagr": {"historical_5yr": "X%", "projected_5yr": "X%", "source": "..."},
  "trends": [
    {"trend": "...", "impact": "positive|negative|neutral", "timeline": "...", "significance": "high|medium|low"}
  ],
  "market_drivers": ["..."],
  "geographic_breakdown": [{"region": "...", "share": "X%", "growth": "..."}],
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
            "This is a PRIVATE company. Do NOT call yf_get_info — it will fail.\n"
            "Instead use web_search for market size estimates, industry reports, "
            "and competitor landscape data.\n"
        )
    else:
        data_instructions = (
            "LIVE DATA REQUIREMENT: Call yf_get_info(ticker) to get the company's "
            "current market cap and sector classification. Use web_search and news_search "
            "for market size estimates and industry reports. Use Google Trends for demand signals. "
            "Use FRED for macroeconomic context if relevant.\n"
        )

    doc_note = ""
    if docs:
        doc_note = (
            f"\nUPLOADED DOCUMENTS: {', '.join(docs)}\n"
            "These contain key data from the user. Extract relevant market data "
            "using extract_pdf_text BEFORE web search. Uploaded materials are often "
            "more informative than public sources.\n"
        )

    user_message = (
        f"Company: {company}\nURL: {url}{doc_note}\n\n"
        "Conduct a thorough market analysis covering TAM/SAM/SOM for ALL business lines.\n\n"
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
        agent_type="market_analysis",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("market_analysis"),
        language=state.get("language", "English"),
    )

    return {"market_analysis": result}
