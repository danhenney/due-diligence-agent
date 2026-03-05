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
    # Only inject live-data header and tool-fallback note for agents that
    # have tools — no-tool agents (red_flag, completeness, final_report,
    # evaluation calls) don't need these, saving ~180 tokens per call.
    if tools:
        today = datetime.now().strftime("%B %d, %Y")
        live_data_header = (
            f"TODAY'S DATE: {today}. "
            "Your training knowledge has a cutoff of August 2025. "
            "Any numerical figure that can change over time — stock price, market cap, "
            "revenue, earnings, analyst ratings, interest rates, competitor metrics — "
            "MUST be fetched via a live tool call. "
            "Never quote a financial number from training memory; always verify with a tool.\n\n"
        )
        system_prompt = live_data_header + system_prompt

        has_web_search = any(t.get("name") == "web_search" for t in tools)
        fallback_note = (
            "\n\nTOOL FALLBACK RULE: If any tool call returns an error or a response "
            "containing '\"error\"', do NOT stop. "
            + (
                "Use web_search or news_search to find the same information instead. "
                if has_web_search else
                "Skip that data point, note it as unavailable, and continue your analysis. "
            )
            + "Always complete your full analysis regardless of individual tool failures."
        )
        system_prompt = system_prompt + fallback_note

        budget_note = (
            "\n\nSEARCH BUDGET: You have a LIMITED number of web searches. "
            "Be strategic — plan your searches before calling tools. "
            "Aim for 4-6 total search calls maximum. "
            "Combine related queries into single broader searches. "
            "Do NOT search for the same topic twice with slightly different wording."
        )
        system_prompt = system_prompt + budget_note

        recency_note = (
            "\n\nRECENCY REQUIREMENT: Prioritize the MOST RECENT information. "
            f"Today is {today}. Any claim or fact older than 6 months should be "
            "verified with a fresh news_search. If you find contradictory info "
            "between an older source and a newer one, ALWAYS prefer the newer source. "
            "Stale data is worse than no data — flag anything you cannot confirm as current."
        )
        system_prompt = system_prompt + recency_note

        has_dart = any(t.get("name", "").startswith("dart_") for t in tools)
        has_sec = any(t.get("name") == "get_sec_filings" for t in tools)
        if has_dart or has_sec:
            filing_note = (
                "\n\nOFFICIAL FILINGS PRIORITY (CRITICAL): "
            )
            if has_dart:
                filing_note += (
                    "For Korean companies, DART (금융감독원 전자공시시스템) filings are the "
                    "HIGHEST-AUTHORITY source. Call dart_finstate() and dart_company() FIRST "
                    "before any web search for financial data. "
                )
            if has_sec:
                filing_note += (
                    "For US companies, SEC 10-K/10-Q filings are the HIGHEST-AUTHORITY source. "
                    "Call get_sec_filings() for official data. "
                )
            filing_note += (
                "SOURCE HIERARCHY: DART/SEC official filings > uploaded documents > "
                "yfinance live data > web search. When official filings conflict with "
                "other sources, the official filing ALWAYS wins."
            )
            system_prompt = system_prompt + filing_note

        has_pdf = any(t.get("name") in ("extract_pdf_text", "extract_pdf_tables") for t in tools)
        if has_pdf:
            doc_priority_note = (
                "\n\nUPLOADED DOCUMENT PRIORITY (CRITICAL RULE): "
                "When uploaded documents provide SPECIFIC data (exact figures, names, dates, "
                "valuations, round details, financial metrics, team bios, etc.), those figures "
                "are the AUTHORITATIVE source. Do NOT override them with vague web estimates. "
                "Example: if the uploaded doc says 'Pre-money 255억원, Post-money 300억원', "
                "use exactly those numbers — do NOT replace with 'estimated $100~150M' from web. "
                "Web search is for CHALLENGING and CROSS-VERIFYING uploaded data, not replacing it. "
                "For factual data, also cross-check against OFFICIAL FILINGS (DART for Korean "
                "companies, SEC 10-K/10-Q for US companies) when available — these are the "
                "highest-authority public sources. If official filings confirm the uploaded data, "
                "note it as double-verified. If they contradict, flag the discrepancy and prefer "
                "the official filing. If no filing is available, the uploaded doc remains primary.\n"
                "HOWEVER, for SUBJECTIVE analysis (valuations, risk assessments, projections, "
                "growth estimates, strategic opinions), you MUST form your OWN independent view. "
                "Do NOT just copy-paste the uploaded doc's opinions or projections as your own. "
                "Present the uploaded doc's claims, then provide YOUR independent assessment "
                "based on cross-verified data, and explain where and why you agree or disagree."
            )
            system_prompt = system_prompt + doc_priority_note

    if language.lower() != "english":
        system_prompt = (
            system_prompt
            + f"\n\nIMPORTANT: Write your ENTIRE response in {language}, "
            + "including all analysis text and JSON field values. Do not use English."
        )
        if tools and has_web_search:
            local_search_note = (
                f"\n\nLOCAL-LANGUAGE SEARCH: For companies based in non-English-speaking "
                f"countries, you MUST also search in the LOCAL LANGUAGE (e.g., Korean for "
                f"Korean companies, Japanese for Japanese companies). Local news outlets "
                f"report breaking developments DAYS before English media picks them up. "
                f"Use at least 1-2 of your search calls with queries in the local language "
                f"(e.g., '네이버 국가 AI 프로젝트 2025' instead of 'Naver sovereign AI project'). "
                f"Local-language results are MORE RELIABLE for local market developments."
            )
            system_prompt = system_prompt + local_search_note

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
