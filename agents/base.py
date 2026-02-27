"""Base agent using Anthropic Claude with tool use."""
from __future__ import annotations

import json
import time
from typing import Any

import anthropic

from config import ANTHROPIC_API_KEY, MODEL_NAME, MAX_TOKENS
from tools.executor import execute_tool_call

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _create_with_retry(client: anthropic.Anthropic, max_retries: int = 5, **kwargs) -> Any:
    """Call messages.create with exponential backoff on rate limit errors."""
    for attempt in range(max_retries):
        try:
            return client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            wait = min(60, 10 * (2 ** attempt))  # 10 20 40 60 60 …
            time.sleep(wait)
    return client.messages.create(**kwargs)  # final attempt, let it raise


def run_agent(
    agent_type: str,
    system_prompt: str,
    user_message: str,
    tools: list[dict],
    max_iterations: int = 10,
    language: str = "English",
) -> dict[str, Any]:
    """Run an Anthropic agentic loop with tool use.

    Handles multi-turn tool calls automatically. Returns the final structured
    response parsed from the last assistant text block, or {"raw": text}.
    """
    if language.lower() != "english":
        system_prompt = (
            system_prompt
            + f"\n\nIMPORTANT: Write your ENTIRE response in {language}, "
            + "including all analysis text and JSON field values. Do not use English."
        )

    client = _get_client()
    messages: list[dict] = [{"role": "user", "content": user_message}]

    for _ in range(max_iterations):
        kwargs: dict[str, Any] = {
            "model":      MODEL_NAME,
            "max_tokens": MAX_TOKENS,
            "system":     system_prompt,
            "messages":   messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = _create_with_retry(client, **kwargs)

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
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": tb.id,
                    "content":     result,
                })
            messages.append({"role": "user", "content": tool_results})
            continue

        final_text = "\n".join(b.text for b in text_blocks).strip()
        break
    else:
        final_text = "Agent exceeded maximum iterations without completing."

    return _parse_json_response(final_text)


def _parse_json_response(text: str) -> dict[str, Any]:
    """Extract the first JSON object found in text, or return {"raw": text}."""
    cleaned = text
    if "```json" in text:
        start   = text.index("```json") + 7
        end     = text.index("```", start)
        cleaned = text[start:end].strip()
    elif "```" in text:
        start   = text.index("```") + 3
        end     = text.index("```", start)
        cleaned = text[start:end].strip()

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
