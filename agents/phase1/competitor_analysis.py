"""Phase 1 — Competitor Analysis agent (competitor ID, comparison matrix)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import build_doc_instructions, calc_max_iterations
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior competitive intelligence analyst conducting investment due diligence.
Identify and analyze ALL significant competitors across EVERY business line the company
operates in. Build a comprehensive comparison matrix per BM.

COMPETITOR IDENTIFICATION:
1. Per-BM mapping: For EACH business model, identify direct, indirect, and emerging competitors.
   Do NOT mix competitors from different BMs into one undifferentiated list.
2. MUST include DOMESTIC competitors (same country/region, same sector). If the target is a
   Korean AI company, search specifically for Korean AI competitors. Then add major
   international competitors for context.
3. For each competitor: name, type (direct/indirect/emerging), revenue, valuation/market cap,
   market share, funding stage (if private), latest funding round date and amount.

COMPARISON MATRIX:
4. Multi-dimensional comparison: product quality, pricing/unit economics, financials,
   market share, talent/team, technology, go-to-market strategy, customer base.
5. For each dimension, rank all players (target + competitors) with specific evidence.
6. Identify the target's MOAT — what is genuinely defensible vs easily replicable?

COMPETITIVE DYNAMICS:
7. Market share trends — who is gaining/losing and why?
8. Recent moves: M&A, partnerships, new entrants, product launches, exits
9. Pricing pressure analysis — are margins compressing industry-wide?
10. Customer win/loss patterns — who is the target losing deals to and why?

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary connecting competitive position to investment thesis>",
  "competitors_by_bm": [
    {
      "business_line": "...",
      "competitors": [
        {
          "name": "...",
          "type": "direct|indirect|emerging",
          "country": "...",
          "market_cap_or_valuation": "...",
          "revenue": "...",
          "market_share": "X%",
          "funding_stage": "...",
          "key_strengths": ["..."],
          "key_weaknesses": ["..."],
          "threat_level": "high|medium|low"
        }
      ]
    }
  ],
  "comparison_matrix": {
    "dimensions": ["product", "pricing", "unit_economics", "financials", "market_share", "talent", "technology", "gtm_strategy"],
    "rankings": [{"company": "...", "scores": {"product": "...", "pricing": "...", "technology": "..."}}]
  },
  "moat_assessment": {"moat_type": "...", "durability": "high|medium|low", "evidence": "..."},
  "market_share": {"target_company": "X%", "trend": "gaining|stable|losing", "top_competitors": [{"name": "...", "share": "X%", "trend": "..."}]},
  "competitive_dynamics": {"recent_moves": ["..."], "pricing_pressure": "...", "win_loss_patterns": "..."},
  "competitive_gaps": ["..."],
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

    doc_note = build_doc_instructions(docs, agent_focus="competitor")

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
        max_iterations=calc_max_iterations(docs),
        language=state.get("language", "English"),
    )

    return {"competitor_analysis": result}
