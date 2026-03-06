"""Phase 1 — Market Analysis agent (TAM/SAM/SOM, CAGR, trends)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import build_doc_instructions, calc_max_iterations
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior market research analyst conducting investment due diligence.
Analyze the market opportunity for ALL of the company's business lines separately.

MULTI-BM REQUIREMENT: If the company operates multiple business models (e.g., API platform,
on-device solutions, consulting), size EACH market independently with its own TAM/SAM/SOM.
Do NOT lump different BMs into one aggregate number.

MARKET SIZING (per BM):
1. TAM/SAM/SOM with specific dollar figures, methodology (top-down or bottom-up), and year
2. Market CAGR — historical 5-year AND projected 5-year with sources
3. Market maturity stage: emerging → growth → mature → declining

MARKET DYNAMICS:
4. Key trends with severity scoring: each trend gets impact (positive/negative/neutral),
   timeline (near-term/medium/long-term), and significance (high/medium/low)
5. Market drivers AND inhibitors — what accelerates or decelerates growth?
6. Geographic breakdown — which regions are growing fastest and why?
7. Demand-side: customer segments, buying patterns, switching costs, price sensitivity
8. Supply-side: market concentration (HHI or CR4), capacity utilization, entry barriers
9. Regulatory tailwinds/headwinds that directly affect market size

CROSS-VERIFICATION:
- Cross-check market size estimates from 2+ independent sources (e.g., Gartner vs IDC vs
  company filings). If they diverge significantly, report the range and explain why.
- Prefer reports from the last 12 months. Flag any estimate older than 2 years.

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary connecting market opportunity to investment thesis>",
  "business_lines": [
    {
      "name": "...",
      "tam": {"value": "$XXB", "methodology": "top-down|bottom-up", "year": "...", "source": "..."},
      "sam": {"value": "$XXB", "methodology": "...", "year": "...", "source": "..."},
      "som": {"value": "$XXB", "methodology": "...", "year": "...", "source": "..."},
      "cagr": {"historical_5yr": "X%", "projected_5yr": "X%", "source": "..."},
      "maturity_stage": "emerging|growth|mature|declining"
    }
  ],
  "trends": [
    {"trend": "...", "impact": "positive|negative|neutral", "timeline": "near-term|medium|long-term", "significance": "high|medium|low", "affected_bms": ["..."]}
  ],
  "market_drivers": ["..."],
  "market_inhibitors": ["..."],
  "geographic_breakdown": [{"region": "...", "share": "X%", "growth": "...", "key_driver": "..."}],
  "demand_analysis": {"customer_segments": ["..."], "switching_costs": "high|medium|low", "price_sensitivity": "..."},
  "supply_analysis": {"concentration": "...", "entry_barriers": "high|medium|low", "key_players": ["..."]},
  "regulatory_impact": {"tailwinds": ["..."], "headwinds": ["..."]},
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

    doc_note = build_doc_instructions(docs, agent_focus="market")

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
        max_iterations=calc_max_iterations(docs),
        language=state.get("language", "English"),
    )

    return {"market_analysis": result}
