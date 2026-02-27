"""FRED (Federal Reserve Economic Data) tools — free API key from fred.stlouisfed.org."""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from config import FRED_API_KEY

# ── Commonly useful series for due diligence ─────────────────────────────────
SERIES_REFERENCE = {
    # Macro
    "FEDFUNDS":   "Federal Funds Rate (%)",
    "DGS10":      "10-Year Treasury Yield (%)",
    "CPIAUCSL":   "CPI Inflation (All Urban, Index)",
    "CPILFESL":   "Core CPI (ex food & energy, Index)",
    "UNRATE":     "US Unemployment Rate (%)",
    "GDP":        "Real GDP (Billions USD, SAAR)",
    "GDPC1":      "Real GDP Growth Rate (%)",
    # Credit / financial conditions
    "BAMLH0A0HYM2": "High-Yield Bond Spread (bps)",
    "DEXUSEU":    "USD/EUR Exchange Rate",
    "DEXCHUS":    "USD/CNY Exchange Rate",
    # Consumer / spending
    "RSAFS":      "Retail Sales (Millions USD)",
    "PCE":        "Personal Consumption Expenditures",
    "UMCSENT":    "University of Michigan Consumer Sentiment",
    # Tech / VC
    "NASDAQ100":  "NASDAQ 100 Index",
    "NASDAQCOM":  "NASDAQ Composite Index",
    # Real estate
    "CSUSHPISA":  "Case-Shiller Home Price Index",
    "MORTGAGE30US":"30-Year Fixed Mortgage Rate (%)",
}


def fred_get_series(
    series_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 24,
) -> dict[str, Any]:
    """Fetch an economic data series from FRED.

    Args:
        series_id: FRED series identifier, e.g. 'FEDFUNDS', 'UNRATE', 'GDP'.
        start_date: ISO date string 'YYYY-MM-DD'. Defaults to 2 years ago.
        end_date:   ISO date string 'YYYY-MM-DD'. Defaults to today.
        limit:      Max number of observations to return (default 24).

    Returns a dict with series metadata and observation values.
    """
    if not FRED_API_KEY:
        return {
            "error": "FRED_API_KEY not configured",
            "action": (
                "Use web_search to find current macroeconomic data instead. "
                "Search for the specific indicator needed (e.g. 'current US inflation rate')."
            ),
            "available_series": SERIES_REFERENCE,
        }

    if start_date is None:
        start_date = (date.today() - timedelta(days=730)).isoformat()
    if end_date is None:
        end_date = date.today().isoformat()

    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_API_KEY)

        # Get series info
        info = fred.get_series_info(series_id)
        series = fred.get_series(
            series_id,
            observation_start=start_date,
            observation_end=end_date,
        )

        if series is None or series.empty:
            return {"error": f"No data for series '{series_id}' in range {start_date}–{end_date}"}

        # Take last `limit` observations
        series = series.tail(limit).dropna()
        observations = {str(idx)[:10]: round(float(v), 4) for idx, v in series.items()}

        values = list(observations.values())
        return {
            "series_id":   series_id,
            "title":       str(info.get("title", "")),
            "units":       str(info.get("units", "")),
            "frequency":   str(info.get("frequency", "")),
            "start_date":  start_date,
            "end_date":    end_date,
            "observations": observations,
            "latest_value": values[-1]  if values else None,
            "prior_value":  values[-2]  if len(values) >= 2 else None,
            "min_in_range": min(values) if values else None,
            "max_in_range": max(values) if values else None,
        }

    except Exception as exc:
        return {
            "error": str(exc),
            "action": "Use web_search to find the macroeconomic data instead.",
        }


def fred_search_series(search_text: str, limit: int = 10) -> dict[str, Any]:
    """Search for FRED series by keyword to find relevant economic indicators."""
    if not FRED_API_KEY:
        return {
            "error": "FRED_API_KEY not configured",
            "action": "Use web_search to find economic data instead.",
            "common_series": SERIES_REFERENCE,
        }
    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_API_KEY)
        results = fred.search(search_text, limit=limit)
        if results is None or results.empty:
            return {"error": "No series found", "search": search_text}
        return {
            "search": search_text,
            "results": [
                {
                    "id":        str(row.name),
                    "title":     str(row.get("title", "")),
                    "units":     str(row.get("units", "")),
                    "frequency": str(row.get("frequency", "")),
                }
                for _, row in results.head(limit).iterrows()
            ],
        }
    except Exception as exc:
        return {"error": str(exc)}


# ── Anthropic tool definitions ────────────────────────────────────────────────

FRED_GET_SERIES_TOOL = {
    "name": "fred_get_series",
    "description": (
        "Fetch real macroeconomic data from the US Federal Reserve (FRED database). "
        "Use this to get precise, official economic indicators: interest rates, inflation, "
        "unemployment, GDP growth, consumer sentiment, credit spreads, exchange rates, and more. "
        "This gives you structured numeric data rather than news articles. "
        f"Common series IDs: {', '.join(list(SERIES_REFERENCE.keys())[:10])}."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "series_id": {
                "type": "string",
                "description": (
                    "FRED series identifier. Examples: 'FEDFUNDS' (interest rate), "
                    "'CPIAUCSL' (inflation), 'UNRATE' (unemployment), 'GDP' (GDP), "
                    "'DGS10' (10-yr Treasury yield), 'BAMLH0A0HYM2' (high-yield spread)."
                ),
            },
            "start_date": {
                "type": "string",
                "description": "Start date in YYYY-MM-DD format. Defaults to 2 years ago.",
            },
            "end_date": {
                "type": "string",
                "description": "End date in YYYY-MM-DD format. Defaults to today.",
            },
            "limit": {
                "type": "integer",
                "description": "Max observations to return (default 24).",
                "default": 24,
            },
        },
        "required": ["series_id"],
    },
}

FRED_SEARCH_SERIES_TOOL = {
    "name": "fred_search_series",
    "description": (
        "Search the FRED database for economic data series by keyword. "
        "Use this to discover the right series_id before calling fred_get_series. "
        "For example, search 'software employment' to find tech sector employment data."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "search_text": {
                "type": "string",
                "description": "Keywords to search for, e.g. 'consumer confidence', 'tech employment'.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return (default 10).",
                "default": 10,
            },
        },
        "required": ["search_text"],
    },
}


def execute_tool(name: str, inputs: dict) -> str:
    if name == "fred_get_series":
        result = fred_get_series(**inputs)
    elif name == "fred_search_series":
        result = fred_search_series(**inputs)
    else:
        raise ValueError(f"Unknown FRED tool: {name}")
    return json.dumps(result, ensure_ascii=False, default=str)
