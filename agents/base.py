"""Base agent using Groq (Llama 3.3 70B) with tool use and rate-limit retry."""
from __future__ import annotations

import json
import time
from typing import Any

from groq import Groq

from config import GROQ_API_KEY, MODEL_NAME, MAX_TOKENS
from tools.executor import execute_tool_call

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def _to_groq_tools(anthropic_tools: list[dict]) -> list[dict] | None:
    """Convert Anthropic tool format → Groq/OpenAI function-calling format."""
    if not anthropic_tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in anthropic_tools
    ]


def _call_with_retry(client: Groq, max_retries: int = 6, **kwargs) -> Any:
    """Call chat.completions.create with exponential backoff on 429s."""
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as exc:
            msg = str(exc)
            if "429" in msg or "rate" in msg.lower() or "quota" in msg.lower():
                wait = min(60, 5 * (2 ** attempt))  # 5 10 20 40 60 60 …
                time.sleep(wait)
            else:
                raise
    return client.chat.completions.create(**kwargs)


def run_agent(
    agent_type: str,
    system_prompt: str,
    user_message: str,
    tools: list[dict],
    max_iterations: int = 10,
) -> dict[str, Any]:
    """Run a Groq agentic loop with tool use.

    Drop-in replacement for the original Anthropic-based interface —
    all agent files remain unchanged.
    """
    client = _get_client()
    groq_tools = _to_groq_tools(tools)

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message},
    ]

    final_text = ""

    for _ in range(max_iterations):
        kwargs: dict[str, Any] = {
            "model":      MODEL_NAME,
            "max_tokens": MAX_TOKENS,
            "messages":   messages,
        }
        if groq_tools:
            kwargs["tools"]       = groq_tools
            kwargs["tool_choice"] = "auto"

        response   = _call_with_retry(client, **kwargs)
        msg        = response.choices[0].message
        tool_calls = msg.tool_calls or []
        final_text = msg.content or ""

        # Append assistant turn (Groq needs explicit dict, not the SDK object)
        messages.append({
            "role":    "assistant",
            "content": final_text,
            "tool_calls": [
                {
                    "id":   tc.id,
                    "type": "function",
                    "function": {
                        "name":      tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ] if tool_calls else [],
        })

        if not tool_calls:
            break

        # Execute every tool call and append results
        for tc in tool_calls:
            try:
                tool_input = json.loads(tc.function.arguments)
                result = execute_tool_call(tc.function.name, tool_input)
            except Exception as exc:
                result = json.dumps({"error": str(exc)})
            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      result,
            })

    return _parse_json_response(final_text)


def _parse_json_response(text: str) -> dict[str, Any]:
    """Extract the first JSON object from text, or return {"raw": text}."""
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
