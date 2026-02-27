"""Phase 1 — Legal Risk agent."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior legal and compliance analyst conducting investment due diligence.
Your task: identify and assess all material legal, regulatory, and compliance risks.

Focus on:
1. Active and pending litigation (lawsuits, arbitrations, regulatory investigations)
2. Regulatory compliance posture (industry-specific regulations, recent violations)
3. Intellectual property (patents, trademarks, trade secrets, IP disputes)
4. Data privacy and cybersecurity compliance (GDPR, CCPA, breaches)
5. Environmental, social, and governance (ESG) legal exposure
6. Contractual obligations and risks (key customer/supplier contracts, change-of-control clauses)
7. Corporate governance (board composition, related-party transactions, insider dealings)

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary>",
  "litigation": {
    "active_cases": [{"description": "...", "exposure": "...", "status": "...", "severity": "high|medium|low"}],
    "overall_litigation_risk": "high|medium|low"
  },
  "regulatory": {
    "compliance_status": "...",
    "recent_actions": ["..."],
    "upcoming_regulatory_changes": ["..."],
    "risk_level": "high|medium|low"
  },
  "intellectual_property": {
    "ip_portfolio": "...",
    "ip_disputes": ["..."],
    "protection_quality": "strong|adequate|weak"
  },
  "data_privacy": {
    "compliance_frameworks": ["..."],
    "known_breaches": ["..."],
    "risk_level": "high|medium|low"
  },
  "governance_flags": ["<flag1>"],
  "red_flags": ["<critical_flag1>"],
  "strengths": ["<strength1>"],
  "confidence_score": 0.0,
  "data_sources": ["<source1>"]
}
"""


def run(state: DueDiligenceState) -> dict:
    company = state["company_name"]
    url = state.get("company_url") or ""
    docs = state.get("uploaded_docs") or []

    doc_note = f"\nUploaded documents: {', '.join(docs)}" if docs else ""

    user_message = (
        f"Company: {company}\n"
        f"URL: {url}{doc_note}\n\n"
        "Conduct a thorough legal and regulatory risk assessment for this company. "
        "Search for litigation, regulatory actions, IP issues, and governance concerns. "
        "Return your findings as the specified JSON object."
    )

    result = run_agent(
        agent_type="legal_risk",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("legal_risk"),
        language=state.get("language", "English"),
    )

    return {"legal_report": result}
