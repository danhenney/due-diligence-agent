"""Phase 4 — Final Report agent (investment memo generator)."""
from __future__ import annotations

import json
from datetime import date

from graph.state import DueDiligenceState
from agents.base import run_agent
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a senior investment committee analyst synthesizing a full due diligence package
into a definitive Investment Memo.

You have access to all prior analysis: Phase 1 specialist reports, Phase 2 thesis work,
Phase 3 verification and stress-testing, and completeness assessment.

Your task: write a professional-grade investment memo and render a final recommendation.

THE RECOMMENDATION MUST BE ONE OF:
- **INVEST**: Compelling opportunity with manageable risks. Proceed with conviction.
- **WATCH**: Interesting opportunity but material uncertainties remain. Monitor and revisit.
- **PASS**: Risks outweigh opportunities, or information is insufficient to justify investment.

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
    full_package = json.dumps({
        "company_name": state["company_name"],
        "company_url": state.get("company_url"),
        "financial_report": state.get("financial_report"),
        "market_report": state.get("market_report"),
        "legal_report": state.get("legal_report"),
        "management_report": state.get("management_report"),
        "tech_report": state.get("tech_report"),
        "bull_case": state.get("bull_case"),
        "bear_case": state.get("bear_case"),
        "valuation": state.get("valuation"),
        "red_flags": state.get("red_flags"),
        "verification": state.get("verification"),
        "stress_test": state.get("stress_test"),
        "completeness": state.get("completeness"),
    }, indent=2)

    today = date.today().isoformat()

    user_message = (
        f"Company: {state['company_name']}\n"
        f"Today's Date: {today}\n\n"
        f"Full Due Diligence Package:\n{full_package}\n\n"
        "Write the complete Investment Memo as specified. "
        "Conclude with the JSON recommendation block."
    )

    result = run_agent(
        agent_type="final_report",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("final_report"),
        max_iterations=5,
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
    for line in text.splitlines():
        upper = line.upper()
        if "INVEST" in upper and ("RECOMMENDATION" in upper or "**INVEST**" in upper):
            return "INVEST"
        if "WATCH" in upper and ("RECOMMENDATION" in upper or "**WATCH**" in upper):
            return "WATCH"
        if "PASS" in upper and ("RECOMMENDATION" in upper or "**PASS**" in upper):
            return "PASS"

    # Try JSON block at end
    import re
    m = re.search(r'\{"recommendation":\s*"(INVEST|WATCH|PASS)"', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    return "WATCH"  # conservative default
