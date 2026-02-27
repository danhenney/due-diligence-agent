"""Shared evaluation + revision logic for per-phase orchestrator checkpoints."""
from __future__ import annotations

import logging
from typing import Any, Callable

from agents.base import run_agent
from tools.executor import get_tools_for_agent

log = logging.getLogger(__name__)

# ── Evaluation prompt (no tools) ──────────────────────────────────────────────

EVAL_SYSTEM_PROMPT = """\
You are the Investment Committee Director running a quality checkpoint on agent outputs.

Score each agent's output on a 0.0–1.0 scale:
- 0.9–1.0: Comprehensive, live-data figures confirmed, fully sourced, no material gaps
- 0.7–0.8: Good coverage, minor gaps that don't affect the conclusion
- 0.5–0.65: Material gaps — key figures missing, data may be stale, weak support
- Below 0.5: Insufficient — major analysis missing, contradictions, or clearly wrong data

IMPORTANT: Be strict. Agents that cite round, unsourced numbers without evidence of a
live tool call (e.g. "market cap ~$2T" with no source) should score below 0.65.

For every agent scoring below 0.65, set needs_revision=true and write a revision_brief
with at least 3 specific, actionable bullet points:
- Exactly which tool to call (e.g. "Call yf_get_info('NVDA') for today's price/market cap")
- Exactly which data point is missing (e.g. "Revenue CAGR is unquantified")
- Exactly which claim needs verification (e.g. "TAM of $50B is unsourced — run web_search")

Return a JSON object with this exact structure:
{
  "evaluations": [
    {
      "agent_name": "...",
      "score": 0.0,
      "key_gaps": ["..."],
      "needs_revision": false,
      "revision_brief": null
    }
  ],
  "overall_quality": "high|medium|low",
  "check_summary": "<1–2 sentence summary of this phase's quality>"
}
"""

# ── Synthesis prompt (with tools) — used only by phase3_check ─────────────────

SYNTHESIS_SYSTEM_PROMPT = """\
You are the Investment Committee Director providing a final synthesis briefing
for the Investment Memo writer.

You have reviewed and potentially revised all 11 specialist agent outputs.
Your tasks:
1. Use live tools (yf_get_info, web_search, news_search) to fill any remaining
   critical data gaps that the agents left unresolved.
2. Identify cross-agent findings that are most vs. least reliable.
3. Resolve any contradictions between agents (e.g. bull case revenue not matching
   financial analyst data; stress test probabilities inconsistent with bear case).
4. Render a clear, decisive investment recommendation.

RECOMMENDATION THRESHOLDS — be decisive, not conservative:
- INVEST: Compelling evidence of value creation, manageable risks, positive trend,
  upside > 15%. Do NOT downgrade to WATCH just because uncertainty exists —
  all investments carry uncertainty. Established companies with solid financials,
  growing revenue, and no fatal red flags should generally be INVEST.
- WATCH: Genuinely mixed signals where bull and bear cases are roughly equal,
  OR material unresolved data gaps that make risk/reward genuinely unclear.
  WATCH is NOT the safe default — you must have specific reasons why the evidence
  is truly inconclusive. If you can articulate a clear bull or bear thesis, it's
  probably INVEST or PASS, not WATCH.
- PASS: Risks clearly dominate — declining fundamentals, fatal red flags, no margin
  of safety, or valuation leaves no room for error.

CRITICAL ANTI-BIAS NOTE: LLMs systematically over-recommend WATCH because it feels
"safe" and avoids committing. Fight this tendency. Ask yourself: "If I had to bet my
own money, would I invest or not?" If the answer is clearly yes or no, do not hedge
with WATCH.

Return a JSON object with this exact structure:
{
  "critical_gaps_filled": [
    {
      "gap_description": "...",
      "tool_used": "...",
      "finding": "...",
      "impact_on_thesis": "bullish|bearish|neutral"
    }
  ],
  "cross_agent_inconsistencies": [
    {
      "agents_involved": ["agent_a", "agent_b"],
      "inconsistency": "...",
      "verdict": "...",
      "severity": "high|medium|low"
    }
  ],
  "overall_data_quality": "high|medium|low",
  "synthesis_guidance": {
    "most_reliable_findings": ["..."],
    "findings_to_discount": ["..."],
    "key_uncertainties": ["..."],
    "suggested_emphasis": ["..."]
  },
  "orchestrator_recommendation": "INVEST|WATCH|PASS",
  "recommendation_rationale": "<2–3 sentence rationale — be specific and decisive>",
  "confidence_score": 0.0
}
"""


# ── Core helpers ───────────────────────────────────────────────────────────────

def evaluate_phase(
    state: dict,
    agent_names: list[str],
    context: str,
    phase_label: str,
    language: str = "English",
) -> dict:
    """Call LLM (no tools) to score agents and generate revision briefs."""
    user_msg = (
        f"Company: {state.get('company_name', '')}\n\n"
        f"Phase being evaluated: {phase_label}\n"
        f"Agents: {', '.join(agent_names)}\n\n"
        f"Agent outputs:\n{context}\n\n"
        "Evaluate each agent strictly. For any agent scoring below 0.65, set "
        "needs_revision=true and write a revision_brief with at least 3 specific "
        "bullet points. Return the specified JSON object."
    )
    return run_agent(
        agent_type="orchestrator",
        system_prompt=EVAL_SYSTEM_PROMPT,
        user_message=user_msg,
        tools=[],           # no tools — pure evaluation
        max_iterations=3,
        language=language,
    )


def revise_agents(
    working_state: dict,
    agent_map: dict[str, tuple[Callable, str]],
    evaluations: list[dict],
    language: str = "English",
) -> dict[str, Any]:
    """Re-run agents that need revision. Returns merged state updates."""
    to_revise = [
        e for e in evaluations
        if e.get("needs_revision") and e.get("score", 1.0) < 0.65
        and e.get("agent_name") in agent_map
    ]
    to_revise.sort(key=lambda e: e.get("score", 1.0))   # worst first
    to_revise = to_revise[:3]                            # cap at 3 per phase

    state_updates: dict[str, Any] = {}
    for ev in to_revise:
        agent_name = ev["agent_name"]
        brief = ev.get("revision_brief") or ""
        if not brief:
            continue
        run_fn, _ = agent_map[agent_name]
        log.info(
            "Orchestrator check: revising %s (score=%.2f)", agent_name, ev.get("score", 0)
        )
        try:
            result = run_fn(working_state, revision_brief=brief)
            working_state.update(result)
            state_updates.update(result)
        except Exception as exc:
            log.warning("Orchestrator check: revision of %s failed: %s", agent_name, exc)

    return state_updates
