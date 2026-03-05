"""Phase 1 — Financial Analysis agent (5-year financials, ratios, valuation)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior financial analyst conducting investment due diligence.
Your task: analyze the company's financial health thoroughly AND perform a
comprehensive valuation analysis.

FINANCIAL ANALYSIS — Focus on:
1. Revenue trends (5-year history, growth rate, consistency, seasonality)
2. Profitability metrics (gross margin, EBITDA margin, net margin, trends)
3. Balance sheet strength (cash position, debt levels, current ratio, D/E)
4. Cash flow quality (FCF generation, capex requirements, working capital)
5. Key financial ratios vs. industry benchmarks
6. Revenue concentration risks (customer / geographic / product)
7. Accounting red flags (revenue recognition, off-balance-sheet items)

VALUATION ANALYSIS — Must include:
1. DCF valuation (with explicit assumptions: WACC, terminal growth, FCF projections)
2. Market-based valuation (P/E, EV/EBITDA, P/S vs. domestic AND international comps)
3. Asset-based valuation (if applicable: NAV, book value)
4. Fair value range (low / mid / high) with methodology
5. Implied upside/downside to current price

CRITICAL VALUATION REQUIREMENTS:
- DCF ASSUMPTIONS REASONING: For EVERY assumption (WACC, risk-free rate, equity risk
  premium, beta, terminal growth rate), explain the SOURCE and REASONING. Do NOT just
  state "WACC = 10%". Example: "risk-free rate 4.3% (10Y UST yield), equity risk premium
  5.5% (Damodaran country ERP), beta 1.2 (regression vs KOSPI), WACC = 11.2%".
- DOMESTIC COMPS: If the company operates primarily in Korea/Asia, you MUST search for
  and include domestic comparable companies. For EACH domestic comp, state:
  (1) when they IPO'd or last raised funding, (2) their current valuation/multiples.
  FILTERING CRITERIA: Only use comps that are RECENT and RELEVANT — exclude companies
  whose IPO or last funding was 5+ years ago unless their current multiples are still
  meaningful. Justify WHY each comp was selected or excluded.
- EXTERNAL VALUATIONS: Search for external valuation references — analyst price targets,
  last funding round valuation, third-party estimates. Present a comparison: your DCF
  result vs your comps result vs external analyst consensus vs last funding round.
  Explain where your valuation differs and WHY.
- FINANCIAL PROJECTIONS: Search for the company's forward guidance, sell-side consensus
  estimates, and recently announced products/models that may impact future revenue.
  Include the LATEST product launches, partnerships, and business developments.
- INVESTMENT ROUNDS: For private or recently-IPO companies, search for ALL funding
  rounds (Series A/B/C, etc.) with: dates, amounts, lead investors, implied valuations,
  and key terms if available. Then ANALYZE:
  (1) What is the valuation trajectory across rounds? (growth multiple between rounds)
  (2) At what multiple vs the last round would a new investment be priced?
  (3) Is the deal structure favorable for our entry point?
  (4) Who are the existing investors and what does their involvement signal?

QUALITY CRITERIA:
- All data must cite explicit sources. Cross-verify with 3+ sources.
- All figures must come from live tool calls, not training memory.
- Provide full data explanations with actual numbers, not 1-2 line summaries.
- Deliver investor-focused analysis and opinions, not just facts.

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary>",
  "revenue_trend": {"description": "...", "five_year_data": "...", "cagr": "...", "confidence": "high|medium|low"},
  "profitability": {"gross_margin": "...", "ebitda_margin": "...", "net_margin": "...", "trend": "..."},
  "balance_sheet": {"cash_position": "...", "debt_level": "...", "current_ratio": "...", "de_ratio": "...", "assessment": "..."},
  "cash_flow": {"fcf_status": "...", "capex_intensity": "...", "working_capital_trend": "...", "assessment": "..."},
  "key_ratios": [{"metric": "...", "value": "...", "benchmark": "...", "signal": "positive|neutral|negative"}],
  "valuation": {
    "dcf": {"fair_value": "...", "wacc": "...", "wacc_reasoning": "...", "terminal_growth": "...", "terminal_growth_reasoning": "...", "methodology": "..."},
    "market_comps": {"pe_ratio": "...", "ev_ebitda": "...", "ps_ratio": "...", "peer_comparison": "...", "domestic_comps": [{"name": "...", "metric": "...", "value": "..."}]},
    "external_valuations": {"analyst_targets": "...", "last_funding_round": "...", "third_party_estimates": "...", "comparison_summary": "..."},
    "investment_rounds": [{"round": "...", "date": "...", "amount": "...", "lead_investor": "...", "implied_valuation": "...", "multiple_vs_previous": "..."}],
    "entry_analysis": {"current_vs_last_round_multiple": "...", "deal_structure_assessment": "...", "investor_signal": "..."},
    "asset_based": "...",
    "fair_value_range": {"low": "...", "mid": "...", "high": "..."},
    "upside_downside": "..."
  },
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

    doc_note = ""
    if docs:
        doc_note = (
            f"\nUPLOADED DOCUMENTS (PRIMARY DATA SOURCE): {', '.join(docs)}\n"
            "STEP 0 — EXTRACT UPLOADED DATA FIRST: Call extract_pdf_text on each document "
            "BEFORE any web search. These documents are provided by the user and contain "
            "the most authoritative financial data (revenue, projections, valuations, etc.).\n"
            "USE THESE NUMBERS AS YOUR BASE — they take priority over web search results.\n"
            "THEN cross-verify and CHALLENGE these numbers with web search data:\n"
            "- Do external sources confirm the revenue/growth figures?\n"
            "- Are the projections realistic compared to industry benchmarks?\n"
            "- Where do the uploaded numbers differ from public data? Flag discrepancies.\n"
            "Do NOT just copy-paste from the documents — analyze, verify, and challenge.\n"
        )

    if is_public is False:
        data_instructions = (
            "This is a PRIVATE company. Do NOT call yf_get_info, yf_get_financials, "
            "yf_get_analyst_data, or get_sec_filings — they will fail.\n"
            "Instead:\n"
            "- Use web_search for '{company} revenue', '{company} funding round', "
            "'{company} valuation', '{company} financials'\n"
            "- Prioritize any uploaded documents as primary financial data source\n"
            "- Use news_search for recent financial news\n"
            "- Flag explicitly where data is estimated vs. confirmed\n"
            "- For valuation, use latest funding round as anchor and compare to peers\n"
        )
    else:
        data_instructions = (
            "STEP 1 — LIVE DATA (mandatory for public companies): "
            "Call yf_get_info(ticker) and yf_get_financials(ticker, 'quarterly') to retrieve "
            "today's stock price, market cap, latest quarterly financials, margins, and analyst targets. "
            "Also call yf_get_analyst_data(ticker) for consensus estimates and price targets. "
            "If you don't know the ticker, use web_search to find it first. "
            "ALL financial figures in your output MUST come from these live tool calls.\n\n"
            "STEP 2 — DEPTH: Use get_sec_filings for multi-year historical trends, "
            "web_search for additional data, and any uploaded documents.\n\n"
            "STEP 3 — COMPS: Call yf_get_info for 3-5 comparable companies to build "
            "the market-based valuation with actual current multiples.\n"
        )

    user_message = (
        f"Company: {company}\nURL: {url}{doc_note}\n\n"
        "Conduct a thorough financial analysis AND valuation of this company.\n\n"
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
        agent_type="financial_analysis",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("financial_analysis"),
        language=state.get("language", "English"),
    )

    return {"financial_analysis": result}
