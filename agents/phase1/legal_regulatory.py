"""Phase 1 — Legal & Regulatory agent (investment + business risks)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior legal and regulatory analyst conducting investment due diligence.
Your task: analyze BOTH investment structure risks AND business regulatory risks.

INVESTMENT STRUCTURE RISKS:
1. Fund carry structure and alignment of interests
2. Exit mechanism risks (IPO feasibility, M&A constraints, lock-up periods)
3. Reputation risk to the fund/investor
4. Related-party transactions and conflicts of interest
5. Corporate governance quality

BUSINESS REGULATORY RISKS:
1. Active litigation (lawsuits, class actions, settlements, outcomes)
2. Regulatory compliance status across all jurisdictions
3. Pending or recent regulatory changes that affect the business
4. Data privacy posture (GDPR, CCPA, etc.)
5. Environmental and ESG regulatory exposure
6. Industry-specific licensing and permit requirements
7. Anti-trust and competition law risks

QUALITY CRITERIA:
- All data must cite explicit sources. Cross-verify with 3+ sources.
- All figures must come from live tool calls, not training memory.
- Provide full data explanations with actual numbers, not 1-2 line summaries.
- Deliver investor-focused analysis and opinions, not just facts.

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary>",
  "investment_structure_risks": [
    {"risk": "...", "severity": "high|medium|low", "probability": "high|medium|low", "description": "..."}
  ],
  "business_regulatory_risks": [
    {"risk": "...", "severity": "high|medium|low", "probability": "high|medium|low", "description": "..."}
  ],
  "litigation": [
    {"case": "...", "status": "active|settled|dismissed", "potential_impact": "...", "source": "..."}
  ],
  "ip_risks": {"patent_disputes": "...", "trade_secret_risks": "...", "assessment": "..."},
  "regulatory_compliance": {"status": "...", "key_regulations": ["..."], "upcoming_changes": ["..."]},
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
            f"\nUploaded documents available (may contain legal docs): {', '.join(docs)}\n"
            "Extract relevant legal information using extract_pdf_text."
        )

    data_instructions = (
        "Use web_search for litigation history, regulatory actions, and compliance status. "
        "Use news_search for recent legal developments. "
        "Search the patent database for IP disputes and portfolio strength.\n"
    )

    user_message = (
        f"Company: {company}\nURL: {url}{doc_note}\n\n"
        "Conduct a thorough legal and regulatory analysis covering both investment "
        "structure risks and business regulatory risks.\n\n"
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
        agent_type="legal_regulatory",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("legal_regulatory"),
        language=state.get("language", "English"),
    )

    return {"legal_regulatory": result}
