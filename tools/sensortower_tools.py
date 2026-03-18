"""Sensor Tower app intelligence tools.

Enterprise API — requires SENSOR_TOWER_API_TOKEN in .env.
Provides app download/revenue estimates, category rankings, and app search
for mobile app companies in due diligence analysis.
"""
from __future__ import annotations

import json
from typing import Any

from config import SENSOR_TOWER_API_TOKEN

_BASE = "https://api.sensortower.com/v1"
_NO_KEY = {
    "error": "SENSOR_TOWER_API_TOKEN not configured",
    "action": (
        "Add SENSOR_TOWER_API_TOKEN to your .env file (enterprise subscription required). "
        "Alternatively, use web_search to find app download/revenue estimates."
    ),
}


def _get(path: str, params: dict | None = None, timeout: int = 20) -> dict | list:
    """Make authenticated GET request to Sensor Tower API."""
    import requests

    params = params or {}
    params["auth_token"] = SENSOR_TOWER_API_TOKEN
    resp = requests.get(f"{_BASE}/{path}", params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, payload: dict, timeout: int = 20) -> dict | list:
    """Make authenticated POST request to Sensor Tower API."""
    import requests

    payload["auth_token"] = SENSOR_TOWER_API_TOKEN
    resp = requests.post(f"{_BASE}/{path}", json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ── Tool implementations ─────────────────────────────────────────────────────


def st_search_apps(
    query: str,
    os: str = "unified",
    limit: int = 10,
) -> dict[str, Any]:
    """Search for mobile apps by name or keyword.

    Args:
        query: App name or keyword (e.g. 'Coupang', '배달의민족').
        os:    Platform — 'unified', 'ios', or 'android'.
        limit: Max results (default 10).

    Returns matching apps with IDs, names, publishers, and categories.
    """
    if not SENSOR_TOWER_API_TOKEN:
        return _NO_KEY
    try:
        data = _get(f"{os}/search_entities", {"term": query, "limit": limit, "entity_type": "app"})
        apps = []
        if isinstance(data, list):
            for app in data[:limit]:
                apps.append({
                    "app_id": app.get("app_id") or app.get("id", ""),
                    "name": app.get("name", ""),
                    "publisher": app.get("publisher_name") or app.get("publisher", ""),
                    "os": app.get("os", os),
                    "category": app.get("category", ""),
                    "icon_url": app.get("icon_url", ""),
                })
        return {"query": query, "os": os, "total_found": len(apps), "apps": apps}
    except Exception as exc:
        return {
            "error": str(exc),
            "action": "Use web_search to find app information instead.",
        }


def st_sales_estimates(
    app_ids: list[str],
    os: str = "unified",
    countries: list[str] | None = None,
    date_granularity: str = "monthly",
    start_date: str = "",
    end_date: str = "",
) -> dict[str, Any]:
    """Get download and revenue estimates for specific apps.

    Args:
        app_ids:          List of Sensor Tower app IDs.
        os:               'unified', 'ios', or 'android'.
        countries:        Country codes (e.g. ['US', 'KR']). None = worldwide.
        date_granularity: 'daily', 'weekly', or 'monthly'.
        start_date:       YYYY-MM-DD format.
        end_date:         YYYY-MM-DD format.

    Returns download counts, revenue estimates, and trends per app.
    """
    if not SENSOR_TOWER_API_TOKEN:
        return _NO_KEY
    try:
        params: dict[str, Any] = {
            "app_ids": ",".join(app_ids),
            "date_granularity": date_granularity,
        }
        if countries:
            params["countries"] = ",".join(countries)
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        data = _get(f"{os}/sales_report_estimates", params)
        return {
            "app_ids": app_ids,
            "os": os,
            "countries": countries or ["WW"],
            "granularity": date_granularity,
            "estimates": data,
        }
    except Exception as exc:
        return {
            "error": str(exc),
            "action": "Use web_search to find app download/revenue data instead.",
        }


def st_top_charts(
    category: str = "",
    os: str = "unified",
    country: str = "WW",
    chart_type: str = "free",
    limit: int = 20,
) -> dict[str, Any]:
    """Get top-ranking apps by downloads or revenue.

    Args:
        category:   App category (e.g. 'overall', 'finance', 'shopping').
        os:         'ios' or 'android' (top charts require specific OS).
        country:    ISO country code (default 'WW' for worldwide).
        chart_type: 'free', 'paid', or 'grossing'.
        limit:      Max results (default 20).

    Returns ranked list of top apps with download/revenue metrics.
    """
    if not SENSOR_TOWER_API_TOKEN:
        return _NO_KEY
    try:
        params: dict[str, Any] = {
            "country": country,
            "chart_type": chart_type,
            "limit": limit,
        }
        if category:
            params["category"] = category

        data = _get(f"{os}/ranking/top", params)
        return {
            "category": category or "overall",
            "os": os,
            "country": country,
            "chart_type": chart_type,
            "top_apps": data if isinstance(data, list) else data,
        }
    except Exception as exc:
        return {
            "error": str(exc),
            "action": "Use web_search to find app ranking data instead.",
        }


# ── Anthropic tool definitions ────────────────────────────────────────────────

ST_SEARCH_APPS_TOOL = {
    "name": "st_search_apps",
    "description": (
        "Search for mobile apps by name or keyword using Sensor Tower. "
        "Returns app IDs, names, publishers, and categories. Use this to find "
        "a company's mobile apps before fetching their download/revenue data. "
        "Example queries: 'Coupang', '카카오', 'TikTok'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "App name or keyword to search for.",
            },
            "os": {
                "type": "string",
                "enum": ["unified", "ios", "android"],
                "description": "Platform filter (default: 'unified' for both).",
                "default": "unified",
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return (default 10).",
                "default": 10,
            },
        },
        "required": ["query"],
    },
}

ST_SALES_ESTIMATES_TOOL = {
    "name": "st_sales_estimates",
    "description": (
        "Get download count and revenue estimates for specific mobile apps "
        "using Sensor Tower. Requires app IDs from st_search_apps. "
        "Returns monthly/weekly/daily download and revenue data by country. "
        "Essential for assessing mobile app companies' market traction."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "app_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of Sensor Tower app IDs (from st_search_apps results).",
            },
            "os": {
                "type": "string",
                "enum": ["unified", "ios", "android"],
                "description": "Platform (default: 'unified').",
                "default": "unified",
            },
            "countries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "ISO country codes (e.g. ['US', 'KR']). Omit for worldwide.",
            },
            "date_granularity": {
                "type": "string",
                "enum": ["daily", "weekly", "monthly"],
                "description": "Data granularity (default: 'monthly').",
                "default": "monthly",
            },
            "start_date": {
                "type": "string",
                "description": "Start date in YYYY-MM-DD format.",
            },
            "end_date": {
                "type": "string",
                "description": "End date in YYYY-MM-DD format.",
            },
        },
        "required": ["app_ids"],
    },
}

ST_TOP_CHARTS_TOOL = {
    "name": "st_top_charts",
    "description": (
        "Get top-ranking mobile apps by downloads or revenue using Sensor Tower. "
        "Useful for market analysis — understanding market leaders, competitive landscape, "
        "and category dynamics. Specify category (e.g. 'finance', 'shopping') and country."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "App category (e.g. 'overall', 'finance', 'shopping', 'social_networking').",
            },
            "os": {
                "type": "string",
                "enum": ["ios", "android"],
                "description": "Platform (required for charts — 'ios' or 'android').",
                "default": "ios",
            },
            "country": {
                "type": "string",
                "description": "ISO country code (default 'WW' for worldwide).",
                "default": "WW",
            },
            "chart_type": {
                "type": "string",
                "enum": ["free", "paid", "grossing"],
                "description": "Chart type (default 'free').",
                "default": "free",
            },
            "limit": {
                "type": "integer",
                "description": "Max results (default 20).",
                "default": 20,
            },
        },
        "required": [],
    },
}


def execute_tool(name: str, inputs: dict) -> str:
    if name == "st_search_apps":
        result = st_search_apps(**inputs)
    elif name == "st_sales_estimates":
        result = st_sales_estimates(**inputs)
    elif name == "st_top_charts":
        result = st_top_charts(**inputs)
    else:
        raise ValueError(f"Unknown Sensor Tower tool: {name}")
    return json.dumps(result, ensure_ascii=False, default=str)
