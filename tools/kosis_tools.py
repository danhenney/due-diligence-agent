"""KOSIS (Korean Statistical Information Service) tools.

Free API key at kosis.kr/openapi — Korean national statistics (산업, GDP, 인구, 경제).
Provides official Korean government statistics for market sizing and macro analysis.
"""
from __future__ import annotations

import json
from typing import Any

from config import KOSIS_API_KEY

_BASE = "https://kosis.kr/openapi"


def kosis_get_statistics(
    table_id: str,
    org_id: str = "101",
    start_year: str = "2020",
    end_year: str = "2025",
) -> dict[str, Any]:
    """Fetch statistical data from a specific KOSIS table.

    Args:
        table_id:   KOSIS table ID (found via kosis_search_tables).
        org_id:     Organization ID (default '101' = Statistics Korea).
        start_year: Start year for data range.
        end_year:   End year for data range.

    Returns structured statistical data with time series.
    Useful for Korean market TAM/SAM sizing with official government data.
    """
    if not KOSIS_API_KEY:
        return {
            "error": "KOSIS_API_KEY not configured",
            "action": (
                "Get a free API key at kosis.kr/openapi, then add "
                "KOSIS_API_KEY to your .env file. "
                "Alternatively, use web_search to find Korean economic statistics."
            ),
        }

    try:
        import requests
        resp = requests.get(
            f"{_BASE}/Param/statisticsParameterData.do",
            params={
                "method": "getList",
                "apiKey": KOSIS_API_KEY,
                "itmId": "ALL",
                "objL1": "ALL",
                "objL2": "",
                "objL3": "",
                "objL4": "",
                "objL5": "",
                "objL6": "",
                "objL7": "",
                "objL8": "",
                "format": "json",
                "jsonVD": "Y",
                "prdSe": "Y",
                "startPrdDe": start_year,
                "endPrdDe": end_year,
                "orgId": org_id,
                "tblId": table_id,
            },
            timeout=15,
        )
        resp.raise_for_status()

        try:
            data = resp.json()
        except ValueError:
            return {"error": "Invalid response from KOSIS", "raw": resp.text[:2000]}

        if isinstance(data, list):
            # Summarise: group by item name, show time series
            summary: dict[str, list] = {}
            for row in data[:200]:  # Cap at 200 rows
                item_name = row.get("ITM_NM", "Unknown")
                period = row.get("PRD_DE", "")
                value = row.get("DT", "")
                unit = row.get("UNIT_NM", "")
                if item_name not in summary:
                    summary[item_name] = []
                summary[item_name].append({
                    "period": period,
                    "value": value,
                    "unit": unit,
                })

            return {
                "table_id": table_id,
                "org_id": org_id,
                "period": f"{start_year}-{end_year}",
                "items": {k: v for k, v in list(summary.items())[:20]},
                "total_rows": len(data),
            }
        else:
            return {"table_id": table_id, "data": data}

    except Exception as exc:
        return {
            "error": str(exc),
            "action": "Use web_search to find Korean economic statistics instead.",
        }


def kosis_search_tables(
    keyword: str,
    limit: int = 10,
) -> dict[str, Any]:
    """Search KOSIS for statistical tables by keyword.

    Args:
        keyword: Search term in Korean, e.g. 'AI 산업', '소프트웨어', 'GDP'.
        limit:   Max results (default 10).

    Returns matching table IDs and names. Use the table_id with kosis_get_statistics
    to fetch the actual data.
    """
    if not KOSIS_API_KEY:
        return {
            "error": "KOSIS_API_KEY not configured",
            "action": "Use web_search to find Korean statistics instead.",
        }

    try:
        import requests
        resp = requests.get(
            f"{_BASE}/statisticsList.do",
            params={
                "method": "getList",
                "apiKey": KOSIS_API_KEY,
                "vwCd": "MT_ZTITLE",
                "searchKwd": keyword,
                "format": "json",
                "jsonVD": "Y",
            },
            timeout=15,
        )
        resp.raise_for_status()

        try:
            data = resp.json()
        except ValueError:
            return {"error": "Invalid response", "raw": resp.text[:2000]}

        if isinstance(data, list):
            tables = []
            for row in data[:limit]:
                tables.append({
                    "table_id": row.get("TBL_ID", ""),
                    "table_name": row.get("TBL_NM", ""),
                    "org_name": row.get("ORG_NM", ""),
                    "period": row.get("PRD_DE", ""),
                })
            return {
                "keyword": keyword,
                "total_found": len(data),
                "tables": tables,
            }
        else:
            return {"keyword": keyword, "data": data}

    except Exception as exc:
        return {
            "error": str(exc),
            "action": "Use web_search to find Korean statistics instead.",
        }


# ── Anthropic tool definitions ────────────────────────────────────────────────

KOSIS_GET_STATISTICS_TOOL = {
    "name": "kosis_get_statistics",
    "description": (
        "Fetch official Korean government statistics from KOSIS (Statistics Korea). "
        "Returns time-series data from a specific statistical table. "
        "Use after kosis_search_tables to find the right table_id. "
        "Provides authoritative Korean market data for TAM/SAM sizing, "
        "industry production/shipment, GDP composition, and demographic data."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "table_id": {
                "type": "string",
                "description": "KOSIS table ID (from kosis_search_tables result).",
            },
            "org_id": {
                "type": "string",
                "description": "Organization ID (default '101' = Statistics Korea).",
                "default": "101",
            },
            "start_year": {
                "type": "string",
                "description": "Start year, e.g. '2020'.",
                "default": "2020",
            },
            "end_year": {
                "type": "string",
                "description": "End year, e.g. '2025'.",
                "default": "2025",
            },
        },
        "required": ["table_id"],
    },
}

KOSIS_SEARCH_TABLES_TOOL = {
    "name": "kosis_search_tables",
    "description": (
        "Search KOSIS (Korean national statistics) for statistical tables by keyword. "
        "Returns table IDs and names that match the search term. "
        "Use this first to discover the right table, then call kosis_get_statistics "
        "with the table_id to fetch actual data. "
        "Search in Korean for best results (e.g. 'AI 산업', '소프트웨어 생산')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "Search keyword in Korean, e.g. 'AI 산업', '소프트웨어', '반도체'.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results (default 10).",
                "default": 10,
            },
        },
        "required": ["keyword"],
    },
}


def execute_tool(name: str, inputs: dict) -> str:
    if name == "kosis_get_statistics":
        result = kosis_get_statistics(**inputs)
    elif name == "kosis_search_tables":
        result = kosis_search_tables(**inputs)
    else:
        raise ValueError(f"Unknown KOSIS tool: {name}")
    return json.dumps(result, ensure_ascii=False, default=str)
