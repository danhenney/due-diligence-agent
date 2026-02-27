"""Phase 1 — Financial Analyst agent."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior financial analyst conducting investment due diligence.
Your task: analyze the company's financial health thoroughly.

Focus on:
1. Revenue trends (growth rate, consistency, seasonality)
2. Profitability metrics (gross margin, EBITDA margin, net margin)
3. Balance sheet strength (cash position, debt levels, current ratio)
4. Cash flow quality (FCF generation, capex requirements)
5. Key financial ratios vs. industry benchmarks
6. Revenue concentration risks (customer / geographic)
7. Accounting red flags (revenue recognition, off-balance-sheet items)

Use available tools to retrieve SEC filings, financial statements, and web data.
If the company is private, rely on web research and any uploaded documents.

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary>",
  "revenue_trend": {"description": "...", "cagr_estimate": "...", "confidence": "high|medium|low"},
  "profitability": {"gross_margin": "...", "ebitda_margin": "...", "net_margin": "...", "trend": "..."},
  "balance_sheet": {"cash_position": "...", "debt_level": "...", "current_ratio": "...", "assessment": "..."},
  "cash_flow": {"fcf_status": "...", "capex_intensity": "...", "assessment": "..."},
  "key_ratios": [{"metric": "...", "value": "...", "benchmark": "...", "signal": "positive|neutral|negative"}],
  "red_flags": ["<flag1>", "<flag2>"],
  "strengths": ["<strength1>", "<strength2>"],
  "confidence_score": 0.0,
  "data_sources": ["<source1>", "<source2>"]
}
"""


def run(state: DueDiligenceState) -> dict:
    """Execute the financial analyst agent and return state update."""
    company = state["company_name"]
    url = state.get("company_url") or ""
    docs = state.get("uploaded_docs") or []

    doc_note = ""
    if docs:
        doc_note = f"\nUploaded documents available for analysis: {', '.join(docs)}"

    user_message = (
        f"Company: {company}\n"
        f"URL: {url}{doc_note}\n\n"
        "Conduct a thorough financial analysis of this company.\n\n"
        "STEP 1 — LIVE DATA (mandatory for public companies): "
        "Call yf_get_info(ticker) and yf_get_financials(ticker, 'quarterly') to retrieve "
        "today's stock price, market cap, latest quarterly financials, margins, and analyst targets. "
        "If you don't know the ticker, use web_search to find it first. "
        "ALL financial figures in your output MUST come from these live tool calls, "
        "not from training memory.\n\n"
        "STEP 2 — DEPTH: Use get_sec_filings for multi-year historical trends, "
        "web_search for private-company data, and any uploaded documents.\n\n"
        "Return your findings as the specified JSON object."
    )

    result = run_agent(
        agent_type="financial_analyst",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("financial_analyst"),
        language=state.get("language", "English"),
    )

    return {"financial_report": result}
