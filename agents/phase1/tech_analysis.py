"""Phase 1 — Tech Analysis agent (core tech, IP/patents, maturity)."""
from __future__ import annotations

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import build_doc_instructions, calc_max_iterations
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior technology analyst conducting investment due diligence.
Evaluate the company's technology across ALL business lines. Present findings in
investor-friendly language — translate technical concepts into business impact.

PER-BM TECH STACK:
1. For EACH business line: what technologies power it? What is the architecture?
2. Tech maturity per BM: emerging → growth → mature → declining
3. Moat assessment per BM: is the tech genuinely defensible or easily replicable?

IP & PATENTS:
4. Patent portfolio: total count, key patents, pending applications, geographic coverage
5. IP strategy assessment: offensive (licensing revenue) vs defensive (blocking competitors)
6. Trade secret risks — what is NOT patented but critical?

COMPETITIVE TECH POSITIONING:
7. Head-to-head comparison with top 3-5 competitors on: speed, accuracy, scalability,
   cost-efficiency, developer experience, ecosystem/integrations
8. Where does the target lead vs lag? Quantify where possible (e.g., "2x faster inference")

TECH RISK MATRIX:
9. For each risk, assess probability and impact:
   - Obsolescence risk: how fast is the underlying tech evolving?
   - Vendor lock-in: dependency on single cloud/infra/framework
   - Cybersecurity posture: known vulnerabilities, breach history
   - Technical debt: legacy systems, migration challenges
   - Key-person tech risk: is critical knowledge concentrated in few engineers?

R&D EFFICIENCY:
10. R&D spend (absolute and % of revenue), trend over 3 years
11. R&D efficiency: patents per $M R&D spend, products shipped per year, revenue per R&D dollar
12. Hiring trends in engineering — growing or shrinking?

LATEST PRODUCTS (CRITICAL):
13. Search for the MOST RECENT product launches, model releases, and tech announcements.
    Missing a recently launched product is a major oversight for valuation.

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence executive summary connecting tech position to investment thesis>",
  "tech_by_bm": [
    {"business_line": "...", "tech_stack": "...", "maturity": "emerging|growth|mature", "moat_strength": "high|medium|low", "moat_evidence": "..."}
  ],
  "ip_patents": {
    "total_patents": "...",
    "key_patents": ["..."],
    "pending_applications": "...",
    "geographic_coverage": "...",
    "ip_strategy": "offensive|defensive|mixed",
    "trade_secret_risks": "..."
  },
  "tech_maturity": {
    "overall_stage": "early|growth|mature|declining",
    "vs_competitors": "leading|on_par|lagging",
    "key_advantages": ["..."],
    "key_gaps": ["..."]
  },
  "competitive_comparison": [
    {"competitor": "...", "dimensions": {"speed": "...", "accuracy": "...", "scalability": "...", "cost": "..."}, "advantage": "target|competitor|neutral"}
  ],
  "tech_risks": [
    {"risk": "...", "category": "obsolescence|vendor_lock_in|cybersecurity|tech_debt|key_person", "probability": "high|medium|low", "impact": "high|medium|low", "mitigation": "..."}
  ],
  "scalability": {"assessment": "...", "constraints": ["..."], "10x_readiness": "yes|partial|no"},
  "rd_investment": {"rd_spend": "...", "percent_of_revenue": "...", "trend": "...", "efficiency_metrics": "..."},
  "latest_products": [{"product": "...", "launch_date": "...", "significance": "..."}],
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
            "This is a PRIVATE company. Use web_search and news_search for technology "
            "analysis. Search GitHub for open source repos. Search patents database.\n"
        )
    else:
        data_instructions = (
            "Use web_search for technology stack analysis and R&D spending. "
            "Search GitHub for the company's open source repos and activity. "
            "Search the patent database for IP portfolio. "
            "Use news_search for recent technology announcements.\n"
        )

    if url:
        data_instructions += (
            f"\nCRITICAL: Search the company's own website for their latest products "
            f"and models. Use web_search with queries like '{company} latest model 2026' "
            f"or '{company} new product launch'. The company URL is {url} — search for "
            f"product pages. Missing a recently launched product is a major oversight.\n"
        )

    doc_note = build_doc_instructions(docs, agent_focus="tech")

    user_message = (
        f"Company: {company}\nURL: {url}{doc_note}\n\n"
        "Conduct a thorough technology analysis of this company.\n\n"
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
        agent_type="tech_analysis",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("tech_analysis"),
        max_iterations=calc_max_iterations(docs),
        language=state.get("language", "English"),
    )

    return {"tech_analysis": result}
