"""Phase 2 — Red Flag Hunter agent (cross-report inconsistency detection)."""
from __future__ import annotations

import json

from graph.state import DueDiligenceState
from agents.base import run_agent
from tools.executor import get_tools_for_agent

SYSTEM_PROMPT = """\
You are a forensic investment analyst specializing in detecting inconsistencies,
contradictions, and warning signs across due diligence reports.

Your task: cross-examine ALL Phase 1 reports and identify:
1. Internal contradictions (e.g., management claims strong growth but financials show decline)
2. Missing information that should be present (suspicious omissions)
3. Claims that don't align across reports
4. Data quality issues or unreliable sources
5. Classic fraud/manipulation signals:
   - Revenue recognized but no cash inflows
   - Customer concentration hidden across reports
   - Related-party transactions obscured
   - Aggressive accounting choices
6. Narrative inconsistencies (what the company says vs. what data shows)

Be skeptical. Surface anything that warrants deeper investigation.

Return a JSON object with this exact structure:
{
  "summary": "<2-3 sentence overview of cross-report findings>",
  "contradictions": [
    {"description": "...", "report_a": "...", "report_b": "...", "severity": "high|medium|low"}
  ],
  "suspicious_omissions": [
    {"description": "...", "expected_in": "...", "risk": "..."}
  ],
  "fraud_signals": [
    {"signal": "...", "evidence": "...", "severity": "high|medium|low"}
  ],
  "narrative_vs_data_gaps": ["<gap1>"],
  "data_quality_issues": ["<issue1>"],
  "requires_immediate_investigation": ["<item1>"],
  "overall_integrity_score": 0.0,
  "flags": []
}
"""


def run(state: DueDiligenceState) -> dict:
    all_reports = json.dumps({
        "financial_report": state.get("financial_report"),
        "market_report": state.get("market_report"),
        "legal_report": state.get("legal_report"),
        "management_report": state.get("management_report"),
        "tech_report": state.get("tech_report"),
    }, indent=2)

    user_message = (
        f"Company: {state['company_name']}\n\n"
        f"All Phase 1 Reports:\n{all_reports}\n\n"
        "Cross-examine all reports for inconsistencies, contradictions, and red flags. "
        "Be thorough and skeptical. Return the specified JSON object."
    )

    result = run_agent(
        agent_type="red_flag",
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tools=get_tools_for_agent("red_flag"),
    )

    # Build the red_flags list[dict] for state from the full report
    flags: list[dict] = []
    for item in result.get("contradictions", []):
        flags.append({"type": "contradiction", "severity": item.get("severity", "medium"), **item})
    for item in result.get("fraud_signals", []):
        flags.append({"type": "fraud_signal", "severity": item.get("severity", "high"), **item})
    for item in result.get("suspicious_omissions", []):
        flags.append({"type": "omission", "severity": "medium", **item})
    for item in result.get("requires_immediate_investigation", []):
        flags.append({"type": "investigation_needed", "description": item, "severity": "high"})

    # Also include raw report in flags for downstream reference
    flags.append({"type": "full_report", "severity": "info", "report": result})

    return {"red_flags": flags}
