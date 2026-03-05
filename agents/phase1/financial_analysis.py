"""Phase 1 — Financial Analysis agent (5-year financials, ratios, valuation)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import build_doc_instructions
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
- INVESTMENT ROUNDS (CRITICAL — often in uploaded documents):
  UPLOADED DOCUMENTS frequently contain detailed funding history with pre-money and
  post-money valuations, lead investors, and round sizes. This is the MOST RELIABLE
  source for round data. Extract EVERY round from the uploaded docs FIRST, then
  supplement with web search.
  For EACH round, you MUST output: round name, date, amount raised, lead investor(s),
  pre-money valuation, post-money valuation, and multiple vs previous round.
  Do NOT skip any round. Do NOT summarize multiple rounds into one line.
  Then ANALYZE:
  (1) What is the valuation trajectory across rounds? (growth multiple between rounds)
  (2) At what multiple vs the last round would a new investment be priced?
  (3) Is the deal structure favorable for our entry point?
  (4) Who are the existing investors and what does their involvement signal?

CURRENCY HANDLING:
- If uploaded documents contain BOTH KRW and USD figures, cross-check them.
  Derive the implied exchange rate (e.g., revenue 270억원 and $17.8M → rate = 1,516 KRW/USD).
  State which currency you use as primary and the exchange rate applied.
- Always present key figures in BOTH currencies when the company operates cross-border.

FINANCIAL RATIO CALCULATION:
- When uploaded documents provide raw financial data (revenue, COGS, operating income,
  net income, etc.), CALCULATE ratios yourself: operating margin, net margin, EBITDA margin,
  revenue growth rate, etc. Do NOT just report what the document says — compute and verify.

UPLOADED DOCUMENT SOURCE TYPE:
- If the uploaded document appears to be from a broker, investment bank, or fund manager
  (fundraising materials, pitch deck, IM), flag this in your summary. Their projections
  and valuations may be optimistic. Extract ALL their claims (revenue projections, TAM,
  valuation, round details including pre-money and post-money) but flag them as
  "source claims" that need independent verification.

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
  "source_claims_verification": {
    "source_type": "broker|fund|company|public",
    "key_claims": [{"claim": "...", "our_verification": "confirmed|disputed|unverifiable", "details": "..."}],
    "optimism_bias_assessment": "..."
  },
  "currency_note": {"primary_currency": "...", "exchange_rate_used": "...", "cross_check": "..."},
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

    doc_note = build_doc_instructions(docs, agent_focus="financial")

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
