"""DART (Korean FSS electronic disclosure) tools via OpenDartReader."""
from __future__ import annotations

import json
import os
from typing import Any


def _get_reader():
    """Lazy-init OpenDartReader with API key."""
    api_key = os.getenv("DART_API_KEY", "")
    if not api_key:
        raise RuntimeError("DART_API_KEY not set — cannot access DART filings.")
    import OpenDartReader as odr
    return odr.OpenDartReader(api_key)


def dart_finstate(company: str, year: int | None = None, consolidated: bool = True) -> dict[str, Any]:
    """Retrieve financial statements for a Korean company from DART.

    Args:
        company: Company name (e.g. '업스테이지') or stock code (e.g. '462870').
        year: Fiscal year. Defaults to the most recent available year.
        consolidated: If True, try consolidated (연결) statements first, then standalone.
    """
    try:
        dart = _get_reader()
        from datetime import datetime
        if year is None:
            year = datetime.now().year - 1  # most recent full fiscal year

        # Try consolidated (연결) first, then standalone (별도)
        df = None
        basis = "consolidated"
        if consolidated:
            try:
                df = dart.finstate(company, year, reprt_code='11011')  # annual consolidated
            except Exception:
                pass
        if df is None or (hasattr(df, "empty") and df.empty):
            df = dart.finstate(company, year)
            basis = "standalone"
        if df is None or (hasattr(df, "empty") and df.empty):
            # Try previous year as fallback
            df = dart.finstate(company, year - 1)
            if df is None or (hasattr(df, "empty") and df.empty):
                return {"error": f"No financial statements found for '{company}' on DART."}
            year = year - 1

        # Convert DataFrame to list of dicts
        records = df.to_dict("records") if hasattr(df, "to_dict") else []
        # Keep only the most useful columns
        slim = []
        for row in records:
            slim.append({
                k: v for k, v in row.items()
                if v is not None and str(v).strip() not in ("", "nan", "None")
            })

        return {
            "company": company,
            "year": year,
            "basis": basis,  # "consolidated" or "standalone"
            "source": "DART (금융감독원 전자공시시스템)",
            "statement_count": len(slim),
            "statements": slim[:50],  # cap to avoid huge payloads
        }
    except RuntimeError:
        raise  # re-raise missing API key
    except Exception as e:
        return {"error": f"DART finstate lookup failed for '{company}': {e}"}


def dart_company(company: str) -> dict[str, Any]:
    """Retrieve company info from DART (registration details, industry, etc.).

    Args:
        company: Company name or stock code.
    """
    try:
        dart = _get_reader()
        info = dart.company(company)
        if info is None or (hasattr(info, "empty") and info.empty):
            return {"error": f"No company info found for '{company}' on DART."}

        if hasattr(info, "to_dict"):
            data = info.to_dict()
        elif isinstance(info, dict):
            data = info
        else:
            data = {"raw": str(info)}

        data["source"] = "DART (금융감독원 전자공시시스템)"
        return data
    except RuntimeError:
        raise
    except Exception as e:
        return {"error": f"DART company lookup failed for '{company}': {e}"}


def dart_list(company: str, kind: str = "A", count: int = 10) -> dict[str, Any]:
    """Retrieve recent disclosure filings for a Korean company from DART.

    Args:
        company: Company name or stock code.
        kind: Filing type — 'A' (periodic reports), 'B' (major reports),
              'C' (special disclosures), 'D' (other). Default 'A'.
        count: Max number of filings to return.
    """
    try:
        dart = _get_reader()
        df = dart.list(company, kind=kind)
        if df is None or (hasattr(df, "empty") and df.empty):
            return {"error": f"No DART filings found for '{company}'."}

        records = df.head(count).to_dict("records") if hasattr(df, "to_dict") else []
        slim = []
        for row in records:
            slim.append({
                k: v for k, v in row.items()
                if v is not None and str(v).strip() not in ("", "nan", "None")
            })

        return {
            "company": company,
            "filing_type": kind,
            "source": "DART (금융감독원 전자공시시스템)",
            "count": len(slim),
            "filings": slim,
        }
    except RuntimeError:
        raise
    except Exception as e:
        return {"error": f"DART filing list failed for '{company}': {e}"}


# ── Anthropic tool definitions ────────────────────────────────────────────────

DART_FINSTATE_TOOL = {
    "name": "dart_finstate",
    "description": (
        "Retrieve official financial statements (income statement, balance sheet, "
        "cash flow) for a Korean company from DART (금융감독원 전자공시시스템). "
        "Returns consolidated (연결) statements by default, falls back to standalone. "
        "This is the HIGHEST-AUTHORITY source for Korean company financials."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "company": {
                "type": "string",
                "description": "Korean company name (e.g. '업스테이지', '삼성전자') or stock code (e.g. '005930').",
            },
            "year": {
                "type": "integer",
                "description": "Fiscal year. Omit for most recent available year.",
            },
        },
        "required": ["company"],
    },
}

DART_COMPANY_TOOL = {
    "name": "dart_company",
    "description": (
        "Retrieve official company registration info from DART — industry code, "
        "CEO name, address, establishment date, fiscal year end. "
        "Highest-authority source for Korean company metadata."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "company": {
                "type": "string",
                "description": "Korean company name or stock code.",
            },
        },
        "required": ["company"],
    },
}

DART_LIST_TOOL = {
    "name": "dart_list",
    "description": (
        "Retrieve recent disclosure filings list from DART for a Korean company. "
        "Shows periodic reports (annual/quarterly), major event reports, etc."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "company": {
                "type": "string",
                "description": "Korean company name or stock code.",
            },
            "kind": {
                "type": "string",
                "description": "Filing type: 'A' (periodic), 'B' (major), 'C' (special), 'D' (other). Default 'A'.",
                "enum": ["A", "B", "C", "D"],
                "default": "A",
            },
            "count": {
                "type": "integer",
                "description": "Max filings to return (default 10).",
                "default": 10,
            },
        },
        "required": ["company"],
    },
}


def execute_tool(name: str, inputs: dict) -> str:
    """Dispatch a DART tool call and return JSON string result."""
    if name == "dart_finstate":
        result = dart_finstate(**inputs)
    elif name == "dart_company":
        result = dart_company(**inputs)
    elif name == "dart_list":
        result = dart_list(**inputs)
    else:
        raise ValueError(f"Unknown DART tool: {name}")
    return json.dumps(result, ensure_ascii=False, default=str)
