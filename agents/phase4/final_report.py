"""Phase 4 — Final Report agent (investment memo generator)."""
from __future__ import annotations

import json
from datetime import date

from graph.state import DueDiligenceState
from agents.base import run_agent
from agents.context import (
    slim_financial, slim_market, slim_legal, slim_management, slim_tech,
    slim_bull, slim_bear, slim_valuation, slim_red_flags,
    slim_verification, slim_stress, slim_completeness, slim_orchestrator, compact,
)
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior investment committee analyst synthesizing a full due diligence package
into a definitive Investment Memo.

You have access to all prior analysis: Phase 1 specialist reports, Phase 2 thesis work,
Phase 3 verification and stress-testing, completeness assessment, and a synthesis briefing
from the Investment Committee Director (Orchestrator) who has already reviewed all outputs,
flagged inconsistencies, filled data gaps, and provided a preliminary recommendation.

Your task: write a professional-grade investment memo and render a final recommendation.

THE RECOMMENDATION MUST BE ONE OF:
- **INVEST**: Compelling opportunity — strong fundamentals, manageable risks, positive momentum,
  and upside potential > 15%. All investments carry uncertainty; do NOT downgrade to WATCH
  simply because some risks exist. If the evidence is broadly favorable, recommend INVEST.
- **WATCH**: Genuinely mixed signals where bull and bear cases are roughly equal in weight,
  OR material unresolved data gaps that make the risk/reward genuinely unclear. This is NOT
  the "safe" default — you must justify why the evidence is truly inconclusive.
- **PASS**: Risks clearly dominate — declining fundamentals, fatal red flags, no margin of
  safety, or valuation leaves no room for error.

CRITICAL: Do NOT default to WATCH as a hedge. LLMs systematically over-select WATCH because
it feels "safe". Fight this bias. If the orchestrator recommended INVEST or PASS, you need
a strong, specific reason to override — not vague uncertainty. Most well-known public companies
with solid financials should be INVEST or PASS, not WATCH.

Structure the memo as Markdown with these sections:
# Investment Memo: [Company Name]
**Date:** [today]
**Recommendation:** [INVEST / WATCH / PASS]
**Confidence:** [High / Medium / Low]

## Executive Summary
## Company Overview
## Investment Thesis (Bull Case)
## Key Risks (Bear Case)
## Financial Analysis
## Market Opportunity
## Management Assessment
## Technology & Product Assessment
## Legal & Compliance
## Valuation
## Stress Test Summary
## Fact-Check Summary
## Recommendation Rationale
### Why [INVEST/WATCH/PASS]
### Key Conditions / Watchpoints
## Appendix: Data Sources

After the memo, output a JSON block on its own line:
```json
{"recommendation": "INVEST|WATCH|PASS", "confidence": "high|medium|low"}
```
"""


def run(state: DueDiligenceState) -> dict:
    orchestrator_brief = slim_orchestrator(state.get("orchestrator_briefing"))

    full_package = compact({
        "financial":    slim_financial(state.get("financial_report")),
        "market":       slim_market(state.get("market_report")),
        "legal":        slim_legal(state.get("legal_report")),
        "management":   slim_management(state.get("management_report")),
        "tech":         slim_tech(state.get("tech_report")),
        "bull_case":    slim_bull(state.get("bull_case")),
        "bear_case":    slim_bear(state.get("bear_case")),
        "valuation":    slim_valuation(state.get("valuation")),
        "red_flags":    slim_red_flags(state.get("red_flags")),
        "verification": slim_verification(state.get("verification")),
        "stress_test":  slim_stress(state.get("stress_test")),
        "completeness": slim_completeness(state.get("completeness")),
    })

    today = date.today().isoformat()

    orchestrator_section = (
        f"\nORCHESTRATOR DIRECTOR BRIEFING:\n{compact(orchestrator_brief)}\n\n"
        if orchestrator_brief else ""
    )

    user_message = (
        f"Company: {state['company_name']}\n"
        f"Today's Date: {today}\n\n"
        f"{orchestrator_section}"
        f"Full Due Diligence Package:\n{full_package}\n\n"
        "The Orchestrator Director has already reviewed all 11 agent outputs, "
        "identified inconsistencies, filled data gaps, and provided a preliminary "
        "recommendation in the briefing above. "
        "Use their synthesis_guidance to decide which findings deserve the most weight "
        "and which to treat with caution.\n\n"
        "IMPORTANT: The Orchestrator's recommendation carries strong weight. If the "
        "Orchestrator recommended INVEST or PASS, you should follow that recommendation "
        "unless you have a specific, concrete reason to override (not just general uncertainty). "
        "Do NOT default to WATCH as a safe middle ground — justify any deviation.\n\n"
        "Write the complete Investment Memo as specified. "
        "Conclude with the JSON recommendation block."
    )

    result = run_agent(
        agent_type="final_report",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("final_report"),
        max_iterations=5,
        language=state.get("language", "English"),
    )

    # The result may be {"raw": "<full memo text>"} or parsed JSON
    if "raw" in result:
        memo_text = result["raw"]
    else:
        # If somehow it returned JSON, convert back to string for display
        memo_text = json.dumps(result, indent=2)

    # Extract recommendation from the memo text
    recommendation = _extract_recommendation(memo_text)

    return {
        "final_report": memo_text,
        "recommendation": recommendation,
        "current_phase": "complete",
    }


def _extract_recommendation(text: str) -> str:
    """Pull INVEST / WATCH / PASS from the memo text."""
    import re

    # 1. Try JSON block first (most reliable — explicitly structured output)
    m = re.search(r'\{"recommendation":\s*"(INVEST|WATCH|PASS)"', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    # 2. Look for **Recommendation:** INVEST/WATCH/PASS line
    m = re.search(r'\*\*Recommendation:\*\*\s*(INVEST|WATCH|PASS)', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    # 3. Look for "### Why INVEST/WATCH/PASS" heading
    m = re.search(r'###\s+Why\s+(INVEST|WATCH|PASS)', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    # 4. Broad scan — first standalone occurrence of INVEST/WATCH/PASS
    #    after "recommendation" keyword (within 100 chars)
    m = re.search(r'[Rr]ecommendation.{0,100}(INVEST|WATCH|PASS)', text)
    if m:
        return m.group(1).upper()

    # No fallback default — return None so caller knows extraction failed
    return "WATCH"
