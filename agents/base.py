"""Base agent using Google Gemini with tool use."""
from __future__ import annotations

import json
from typing import Any

import google.generativeai as genai
import google.generativeai.protos as protos

from config import GOOGLE_API_KEY, MODEL_NAME, MAX_TOKENS
from tools.executor import execute_tool_call

# ── Schema conversion (Anthropic format → Gemini protos) ──────────────────────

_TYPE_MAP = {
    "string":  protos.Type.STRING,
    "integer": protos.Type.INTEGER,
    "number":  protos.Type.NUMBER,
    "boolean": protos.Type.BOOLEAN,
    "array":   protos.Type.ARRAY,
    "object":  protos.Type.OBJECT,
}


def _to_schema(d: dict) -> protos.Schema:
    t = _TYPE_MAP.get(d.get("type", "string"), protos.Type.STRING)
    kw: dict[str, Any] = {"type": t}
    if d.get("description"):
        kw["description"] = d["description"]
    if t == protos.Type.OBJECT:
        props = {k: _to_schema(v) for k, v in d.get("properties", {}).items()}
        if props:
            kw["properties"] = props
        if d.get("required"):
            kw["required"] = d["required"]
    elif t == protos.Type.ARRAY and "items" in d:
        kw["items"] = _to_schema(d["items"])
    return protos.Schema(**kw)


def _to_gemini_tools(anthropic_tools: list[dict]) -> list | None:
    """Convert Anthropic tool definitions to a Gemini Tool proto."""
    if not anthropic_tools:
        return None
    fds = [
        protos.FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters=_to_schema(
                t.get("input_schema", {"type": "object", "properties": {}})
            ),
        )
        for t in anthropic_tools
    ]
    return [protos.Tool(function_declarations=fds)]


# ── Agent loop ─────────────────────────────────────────────────────────────────

def run_agent(
    agent_type: str,
    system_prompt: str,
    user_message: str,
    tools: list[dict],
    max_iterations: int = 10,
) -> dict[str, Any]:
    """Run a Gemini agentic loop with tool use.

    Mirrors the original Anthropic-based interface so all agent files
    remain unchanged.
    """
    genai.configure(api_key=GOOGLE_API_KEY)

    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=system_prompt,
        tools=_to_gemini_tools(tools),
        generation_config=genai.GenerationConfig(
            max_output_tokens=MAX_TOKENS,
        ),
    )

    chat = model.start_chat()
    response = chat.send_message(user_message)

    for _ in range(max_iterations):
        # Collect any function-call parts
        fn_calls = []
        for part in response.parts:
            try:
                if part.function_call.name:
                    fn_calls.append(part.function_call)
            except AttributeError:
                pass

        if not fn_calls:
            break

        # Execute every tool call and collect responses
        fn_parts = []
        for fc in fn_calls:
            try:
                result = execute_tool_call(fc.name, dict(fc.args))
            except Exception as exc:
                result = json.dumps({"error": str(exc)})
            fn_parts.append(
                protos.Part(
                    function_response=protos.FunctionResponse(
                        name=fc.name,
                        response={"result": result},
                    )
                )
            )

        response = chat.send_message(protos.Content(parts=fn_parts))

    # Extract final text
    text_parts = []
    for part in response.parts:
        try:
            if part.text:
                text_parts.append(part.text)
        except AttributeError:
            pass
    final_text = "".join(text_parts).strip()

    return _parse_json_response(final_text)


def _parse_json_response(text: str) -> dict[str, Any]:
    """Extract the first JSON object from text, or return {"raw": text}."""
    cleaned = text
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        cleaned = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
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
