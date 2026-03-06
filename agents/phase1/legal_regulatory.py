"""Phase 1 — Legal & Regulatory agent (investment + business risks)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import build_doc_instructions
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior legal and regulatory analyst conducting investment due diligence.
Analyze BOTH investment structure risks AND business regulatory risks across ALL
jurisdictions and business lines the company operates in.

INVESTMENT STRUCTURE RISKS:
1. Fund carry structure and alignment of interests
2. Exit mechanism risks (IPO feasibility, M&A constraints, lock-up periods)
3. Reputation risk to the fund/investor
4. Related-party transactions and conflicts of interest
5. Corporate governance quality — board independence, audit committee, shareholder rights
6. Ownership structure — controlling shareholders, voting rights, cap table concerns

LITIGATION (CRITICAL — be thorough):
7. Active litigation: for EACH case, state parties, jurisdiction, amount at stake,
   status, likely outcome, and timeline. Do NOT summarize multiple cases into one line.
8. Historical settlements: amount paid, terms, implications for future liability
9. Class actions or regulatory enforcement actions
10. IP litigation: patent infringement claims (as plaintiff or defendant)

REGULATORY COMPLIANCE (per jurisdiction):
11. For EACH major jurisdiction the company operates in: compliance status, key regulations,
    recent inspections/audits, penalties or warnings received
12. Pending regulatory changes that could materially affect the business
13. Data privacy: GDPR, CCPA, Korea PIPA — current posture and any violations
14. Industry-specific licensing: are all permits current? Any at risk of non-renewal?
15. Anti-trust / competition law exposure

ESG & REPUTATIONAL:
16. Environmental regulatory exposure and compliance
17. ESG controversies or ratings
18. Labor law compliance (especially important for tech companies with contractors)

For Korean companies: search DART filings (dart_list) for regulatory disclosures,
audit opinions, and material event reports.

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary connecting legal/regulatory risks to investment thesis>",
  "investment_structure_risks": [
    {"risk": "...", "severity": "high|medium|low", "probability": "high|medium|low", "description": "...", "mitigation": "..."}
  ],
  "business_regulatory_risks": [
    {"risk": "...", "jurisdiction": "...", "severity": "high|medium|low", "probability": "high|medium|low", "description": "...", "mitigation": "..."}
  ],
  "litigation": [
    {"case": "...", "parties": "...", "jurisdiction": "...", "amount_at_stake": "...", "status": "active|settled|dismissed", "likely_outcome": "...", "timeline": "...", "source": "..."}
  ],
  "ip_risks": {"patent_disputes": "...", "trade_secret_risks": "...", "assessment": "..."},
  "regulatory_compliance": {
    "by_jurisdiction": [{"jurisdiction": "...", "status": "compliant|at_risk|non_compliant", "key_regulations": ["..."], "issues": "..."}],
    "upcoming_changes": [{"regulation": "...", "effective_date": "...", "impact": "high|medium|low", "description": "..."}]
  },
  "governance": {"board_independence": "...", "audit_quality": "...", "shareholder_rights": "...", "assessment": "strong|adequate|weak"},
  "esg_exposure": {"environmental": "...", "social": "...", "governance_rating": "..."},
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

    doc_note = build_doc_instructions(docs, agent_focus="legal")

    if is_public is False:
        data_instructions = (
            "PRIVATE company. Call dart_list() for Korean regulatory filings/disclosures. "
            "Use web_search for litigation and regulatory actions. "
            "Use news_search for recent legal developments.\n"
        )
    else:
        data_instructions = (
            "Call dart_list() for Korean company filings/disclosures. "
            "Use web_search for litigation history, regulatory actions, and compliance. "
            "Use news_search for recent legal developments. "
            "Search patent database for IP disputes.\n"
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
        max_iterations=15,
        language=state.get("language", "English"),
    )

    return {"legal_regulatory": result}
