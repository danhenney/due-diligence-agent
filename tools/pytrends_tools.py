"""Google Trends tools via pytrends — free, no API key required."""
from __future__ import annotations

import json
import time
from typing import Any


def _client():
    from pytrends.request import TrendReq
    # Note: do NOT pass retries/backoff_factor — causes urllib3 compat errors
    return TrendReq(hl="en-US", tz=0, timeout=(10, 30))


def google_trends_interest(
    keywords: list[str],
    timeframe: str = "today 5-y",
    geo: str = "",
) -> dict[str, Any]:
    """Return Google search-interest time series for up to 5 keywords.

    Args:
        keywords: List of search terms to compare (max 5).
        timeframe: Date range string — e.g. 'today 5-y', 'today 12-m',
                   'today 3-m', '2020-01-01 2024-12-31'.
        geo: Two-letter country code for regional data ('' = worldwide).

    Returns a dict with weekly/monthly interest scores (0-100) per keyword.
    """
    kws = [k.strip() for k in keywords[:5] if k.strip()]
    if not kws:
        return {"error": "No keywords provided"}

    try:
        pt = _client()
        pt.build_payload(kws, timeframe=timeframe, geo=geo)
        df = pt.interest_over_time()

        if df is None or df.empty:
            return {"error": "No trend data returned — keyword may be too obscure"}

        result: dict[str, Any] = {"timeframe": timeframe, "geo": geo or "worldwide"}
        for kw in kws:
            if kw in df.columns:
                series = {
                    str(ts)[:10]: int(v)
                    for ts, v in df[kw].items()
                    if not hasattr(v, "__float__") or v == v  # skip NaN
                }
                # Summarise: last value, peak, average
                values = list(series.values())
                result[kw] = {
                    "weekly_interest": series,
                    "current":  values[-1]  if values else None,
                    "peak":     max(values) if values else None,
                    "average":  round(sum(values) / len(values), 1) if values else None,
                    "trend":    "rising"  if len(values) >= 4 and values[-1] > values[-4] else
                                "falling" if len(values) >= 4 and values[-1] < values[-4] else
                                "stable",
                }
        return result

    except Exception as exc:
        return {"error": f"Google Trends request failed: {exc}",
                "action": "Use web_search to find market trend information instead."}


def google_trends_related(keyword: str) -> dict[str, Any]:
    """Return top and rising related search queries for a keyword.

    Useful for understanding what topics users associate with a company/product.
    """
    try:
        pt = _client()
        pt.build_payload([keyword], timeframe="today 12-m")
        related = pt.related_queries()
        out: dict[str, Any] = {"keyword": keyword}
        data = related.get(keyword, {})
        for key in ("top", "rising"):
            df = data.get(key)
            if df is not None and not df.empty:
                out[key] = df.head(10).to_dict(orient="records")
        return out
    except Exception as exc:
        return {"error": f"Google Trends related queries failed: {exc}"}


# ── Anthropic tool definitions ────────────────────────────────────────────────

GOOGLE_TRENDS_INTEREST_TOOL = {
    "name": "google_trends_interest",
    "description": (
        "Get Google search-interest trend data (0-100 score) for a company name, "
        "product, or market keyword over time. Use this to assess brand momentum, "
        "product adoption curves, and competitive search share. "
        "Compare the company against competitors by passing multiple keywords. "
        "Scores are relative: 100 = peak interest in the period."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "1-5 search terms to compare, e.g. ['Stripe', 'Square', 'PayPal'].",
            },
            "timeframe": {
                "type": "string",
                "description": (
                    "Date range: 'today 5-y' (5 years), 'today 12-m' (1 year), "
                    "'today 3-m' (3 months). Default 'today 5-y'."
                ),
                "default": "today 5-y",
            },
            "geo": {
                "type": "string",
                "description": "Two-letter country code for regional data, e.g. 'US'. Leave empty for worldwide.",
                "default": "",
            },
        },
        "required": ["keywords"],
    },
}

GOOGLE_TRENDS_RELATED_TOOL = {
    "name": "google_trends_related",
    "description": (
        "Get top and rising related search queries for a company or product name. "
        "Reveals what topics users associate with the brand, useful for understanding "
        "market perception, use cases, and competitor associations."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "A single company or product name to analyse.",
            },
        },
        "required": ["keyword"],
    },
}


def execute_tool(name: str, inputs: dict) -> str:
    if name == "google_trends_interest":
        result = google_trends_interest(**inputs)
    elif name == "google_trends_related":
        result = google_trends_related(**inputs)
    else:
        raise ValueError(f"Unknown pytrends tool: {name}")
    return json.dumps(result, ensure_ascii=False, default=str)
