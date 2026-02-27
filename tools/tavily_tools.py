"""Tavily-based web and news search tools."""
from __future__ import annotations

import json
from typing import Any

from tavily import TavilyClient

from config import TAVILY_API_KEY

_client: TavilyClient | None = None


def _get_client() -> TavilyClient:
    global _client
    if _client is None:
        if not TAVILY_API_KEY:
            raise RuntimeError("TAVILY_API_KEY is not set. Add it to your .env file.")
        _client = TavilyClient(api_key=TAVILY_API_KEY)
    return _client


def web_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """General web search via Tavily.

    Returns a list of result dicts with keys: title, url, content, score.
    """
    client = _get_client()
    response = client.search(
        query=query,
        search_depth="advanced",
        max_results=max_results,
        include_answer=True,
    )
    results = []
    if response.get("answer"):
        results.append({"type": "answer", "content": response["answer"]})
    for r in response.get("results", []):
        results.append({
            "type": "result",
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
            "score": r.get("score", 0.0),
        })
    return results


def news_search(query: str, max_results: int = 5, days: int = 30) -> list[dict[str, Any]]:
    """Recent news search via Tavily (finance / business focused).

    Args:
        query: Search query string.
        max_results: Number of results to return.
        days: Look back this many days.

    Returns a list of result dicts with keys: title, url, content, published_date, score.
    """
    client = _get_client()
    response = client.search(
        query=query,
        search_depth="advanced",
        topic="news",
        days=days,
        max_results=max_results,
        include_answer=True,
    )
    results = []
    if response.get("answer"):
        results.append({"type": "answer", "content": response["answer"]})
    for r in response.get("results", []):
        results.append({
            "type": "result",
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
            "published_date": r.get("published_date", ""),
            "score": r.get("score", 0.0),
        })
    return results


# ── Anthropic tool definitions ────────────────────────────────────────────────

WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": (
        "Search the web for information about a company, market, technology, or any topic "
        "relevant to investment due diligence. Returns titles, URLs, and excerpts."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default 5).",
                "default": 5,
            },
        },
        "required": ["query"],
    },
}

NEWS_SEARCH_TOOL = {
    "name": "news_search",
    "description": (
        "Search for recent news articles about a company or topic. "
        "Useful for finding recent financials, leadership changes, lawsuits, or product launches."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The news search query.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of articles to return (default 5).",
                "default": 5,
            },
            "days": {
                "type": "integer",
                "description": "Look back this many days (default 30).",
                "default": 30,
            },
        },
        "required": ["query"],
    },
}


def execute_tool(name: str, inputs: dict) -> str:
    """Dispatch a Tavily tool call and return JSON string result."""
    if name == "web_search":
        result = web_search(**inputs)
    elif name == "news_search":
        result = news_search(**inputs)
    else:
        raise ValueError(f"Unknown Tavily tool: {name}")
    return json.dumps(result, ensure_ascii=False)
