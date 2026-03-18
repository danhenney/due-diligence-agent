"""Base agent using Anthropic Claude with tool use."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from typing import Any

import anthropic

from config import ANTHROPIC_API_KEY, MODEL_NAME, MAX_TOKENS
from tools.executor import execute_tool_call

# ── Context-window safety ─────────────────────────────────────────────────────
_MAX_CONTEXT_CHARS = 550_000  # ~160K tokens (Korean ≈ 3.5 chars/token)
_MAX_TOOL_RESULT_CHARS = 4_000  # cap each web/API tool result
_MAX_PDF_RESULT_CHARS = 20_000  # higher cap for uploaded PDF content
# PDF tools must NOT be truncated at 4K — user-uploaded docs often have
# critical data (investment rounds, valuations) deep in the document.
_PDF_TOOLS = frozenset({"extract_pdf_text", "extract_pdf_tables"})

_client: anthropic.Anthropic | None = None

# ── Per-thread token usage accumulator ───────────────────────────────────────
_tl = threading.local()


def _accum_usage(inp: int, out: int) -> None:
    _tl.input_tokens  = getattr(_tl, "input_tokens",  0) + inp
    _tl.output_tokens = getattr(_tl, "output_tokens", 0) + out


def get_and_reset_usage() -> dict:
    """Return accumulated token counts for this thread and reset to zero."""
    inp = getattr(_tl, "input_tokens",  0)
    out = getattr(_tl, "output_tokens", 0)
    _tl.input_tokens  = 0
    _tl.output_tokens = 0
    return {"input_tokens": inp, "output_tokens": out}


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _estimate_chars(system: str, messages: list[dict]) -> int:
    """Rough character count of the full prompt (system + messages)."""
    total = len(system)
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total += len(str(block.get("content", "")))
                    total += len(str(block.get("text", "")))
                    total += len(json.dumps(block.get("input", {}), ensure_ascii=False)) if "input" in block else 0
                else:
                    total += len(str(block))
    return total


def _trim_oldest_tool_results(
    messages: list[dict], system: str, protected_ids: set[str] | None = None
) -> None:
    """Trim tool result contents in-place, oldest first, until under budget.

    NEVER trims tool results whose tool_use_id is in protected_ids — these
    are PDF extractions from uploaded documents that must be preserved.
    """
    protected = protected_ids or set()
    while _estimate_chars(system, messages) > _MAX_CONTEXT_CHARS:
        trimmed_any = False
        for msg in messages:
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                # Skip protected PDF results
                if block.get("tool_use_id", "") in protected:
                    continue
                c = block.get("content", "")
                if isinstance(c, str) and len(c) > 200:
                    block["content"] = c[:200] + "\n[…truncated to fit context window]"
                    trimmed_any = True
                    break  # re-check total after each trim
            if trimmed_any:
                break
        if not trimmed_any:
            break  # nothing left to trim


def _create_with_retry(client: anthropic.Anthropic, max_retries: int = 5, **kwargs) -> Any:
    """Call messages API with streaming + exponential backoff on rate limit errors."""
    for attempt in range(max_retries + 1):
        try:
            with client.messages.stream(**kwargs) as stream:
                return stream.get_final_message()
        except anthropic.RateLimitError:
            if attempt >= max_retries:
                raise
            wait = min(60, 10 * (2 ** attempt))  # 10 20 40 60 60 …
            time.sleep(wait)


def run_agent(
    agent_type: str,
    system_prompt: str,
    user_message: str,
    tools: list[dict],
    max_iterations: int = 10,
    language: str = "English",
    max_tokens: int | None = None,
    return_raw_text: bool = False,
) -> dict[str, Any]:
    """Run an Anthropic agentic loop with tool use.

    Handles multi-turn tool calls automatically. Returns the final structured
    response parsed from the last assistant text block, or {"raw": text}.
    """
    # Only inject operational rules for agents that have tools.
    if tools:
        today = datetime.now().strftime("%B %d, %Y")
        tool_names = {t.get("name", "") for t in tools}
        has_web = "web_search" in tool_names
        has_dart = any(n.startswith("dart_") for n in tool_names)
        has_sec = "get_sec_filings" in tool_names
        has_pdf = bool(tool_names & {"extract_pdf_text", "extract_pdf_tables"})

        # Build a single consolidated injection block
        rules = [
            f"TODAY'S DATE: {today}. Training cutoff: August 2025. "
            "ALL time-sensitive figures (price, revenue, market cap, etc.) MUST come "
            "from live tool calls — never from training memory.",
        ]

        # Source hierarchy
        hierarchy_parts = []
        if has_dart:
            hierarchy_parts.append("DART (dart_finstate/dart_company) for Korean companies")
        if has_sec:
            hierarchy_parts.append("SEC 10-K/10-Q (get_sec_filings) for US companies")
        if hierarchy_parts:
            rules.append(
                "SOURCE HIERARCHY: uploaded documents (exact figures) > "
                + " / ".join(hierarchy_parts)
                + " > public data (KOSIS/KIPRIS/FRED) > yfinance > web search. "
                "Official filings always win on conflict with web data."
            )

        if has_pdf:
            rules.append(
                "UPLOADED DOCS: Exact figures from uploaded documents (valuations, rounds, "
                "financials, team bios) are authoritative — do NOT replace with vague web "
                "estimates. Use web to cross-verify, not override. "
                "For SUBJECTIVE analysis (risk, projections, strategic opinions), form your "
                "OWN independent view — do not copy-paste the document's opinions."
            )

        if has_web:
            rules.append(
                "SEARCH BUDGET & STRATEGY (B1): 4-6 searches max. "
                "Plan ALL queries BEFORE searching — write them out, then execute. "
                "Don't repeat queries with slightly different wording. "
                "Financial data → API tools FIRST (yfinance/DART/EDGAR), web search only for gaps. "
                "Korean company → Korean queries first, then English for global context."
            )

        rules.append(
            "RECENCY & FRESHNESS (B3): Prefer newest sources. "
            "Anything >6 months old → tag [STALE: YYYY-MM]. "
            "Newer source always wins over older on conflict. "
            "For each key data point, note the date in source tag."
        )
        rules.append(
            "TOOL ERRORS: If a tool returns an error, "
            + ("fall back to web_search. " if has_web else "skip that data point. ")
            + "Always complete your full analysis."
        )
        rules.append(
            "QUALITY: Cite sources for all data. Cross-verify key claims with 3+ sources. "
            "Use actual numbers, not vague summaries. Deliver investor-focused analysis."
        )
        rules.append(
            "SOURCE RELIABILITY TIERS (B2): Tag each source — "
            "[T1] Official filings, APIs (DART/SEC/yfinance/FRED), uploaded docs. "
            "[T2] Reputable media (Bloomberg, Reuters, Gartner, IDC). "
            "[T3] General news, press releases. "
            "[T4] Forums, blogs, unverified. "
            "Critical claims on T3-T4 only → tag [LOW_CONFIDENCE]. "
            "Include tier summary in output."
        )
        rules.append(
            "[DATA]/[INFERENCE]/[UNVERIFIED] LABELING: Prefix every major statement with "
            "[DATA: <specific source>] (directly from a source — tool result, document, filing), "
            "[INFERENCE] (your own analysis/interpretation), or "
            "[UNVERIFIED] (claim without verified source). "
            "This helps downstream agents distinguish verified facts from speculation. "
            "NOTE: The report writer will convert these to numbered footnotes (¹²³) with "
            "a source verification table in the appendix."
        )

        system_prompt = "\n".join(rules) + "\n\n" + system_prompt

    if language.lower() != "english":
        system_prompt += (
            f"\n\nWrite your ENTIRE response in {language}, including JSON field values."
        )
        if tools and has_web:
            system_prompt += (
                f"\nAlso search in the LOCAL LANGUAGE (e.g., Korean for Korean companies). "
                f"Local news breaks stories days before English media."
            )

    client = _get_client()
    messages: list[dict] = [{"role": "user", "content": user_message}]
    _pdf_tool_ids: set[str] = set()  # track PDF tool_use_ids for trim protection

    for _ in range(max_iterations):
        # Safety net: trim OLD tool results if context is too large.
        # This only truncates previous tool results (search data etc.),
        # never the user's initial message, agent output, or PDF results.
        _trim_oldest_tool_results(messages, system_prompt, _pdf_tool_ids)

        kwargs: dict[str, Any] = {
            "model":      MODEL_NAME,
            "max_tokens": max_tokens or MAX_TOKENS,
            "system":     system_prompt,
            "messages":   messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = _create_with_retry(client, **kwargs)

        # Accumulate token usage for this API call
        if hasattr(response, "usage") and response.usage:
            _accum_usage(response.usage.input_tokens, response.usage.output_tokens)

        tool_use_blocks = []
        text_blocks = []
        for block in response.content:
            if block.type == "tool_use":
                tool_use_blocks.append(block)
            elif block.type == "text":
                text_blocks.append(block)

        messages.append({"role": "assistant", "content": response.content})

        if tool_use_blocks:
            tool_results = []
            for tb in tool_use_blocks:
                try:
                    result = execute_tool_call(tb.name, tb.input)
                except Exception as exc:
                    result = json.dumps({"error": str(exc)})
                # Cap each tool result to prevent context blowup
                # PDF tools get a higher limit — uploaded docs have critical
                # data (investment rounds, valuations) that must not be cut
                is_pdf = tb.name in _PDF_TOOLS
                cap = _MAX_PDF_RESULT_CHARS if is_pdf else _MAX_TOOL_RESULT_CHARS
                if isinstance(result, str) and len(result) > cap:
                    result = result[:cap] + "\n[…truncated]"
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": tb.id,
                    "content":     result,
                })
                if is_pdf:
                    _pdf_tool_ids.add(tb.id)  # protect from safety-net trimming
            messages.append({"role": "user", "content": tool_results})
            continue

        final_text = "\n".join(b.text for b in text_blocks).strip()
        break
    else:
        final_text = "Agent exceeded maximum iterations without completing."

    if return_raw_text:
        return {"raw": final_text}
    return _parse_json_response(final_text)


def _parse_json_response(text: str) -> dict[str, Any]:
    """Extract the first JSON object found in text, or return {"raw": text}."""
    cleaned = text
    if "```json" in text:
        start = text.index("```json") + 7
        end   = text.find("```", start)
        if end != -1:
            cleaned = text[start:end].strip()
        else:
            cleaned = text[start:].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end   = text.find("```", start)
        if end != -1:
            cleaned = text[start:end].strip()
        else:
            cleaned = text[start:].strip()

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        brace_start = text.find("{")
        if brace_start != -1:
            depth = 0
            for i, ch in enumerate(text[brace_start:], brace_start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[brace_start: i + 1])
                        except json.JSONDecodeError:
                            break
        return {"raw": text}
