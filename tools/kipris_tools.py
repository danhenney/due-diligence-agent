"""KIPRIS (Korean Intellectual Property Rights Information Service) tools.

Free API key at plus.kipris.or.kr — Korean patent/utility model search.
Complements USPTO PatentsView for Korean companies' domestic IP portfolios.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any

from config import KIPRIS_API_KEY

_BASE = "http://plus.kipris.or.kr/openapi/rest/patUtiModInfoSearchSevice"


def _parse_xml_items(xml_text: str) -> list[dict]:
    """Parse KIPRIS XML response into a list of patent dicts."""
    items = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.iter("item"):
            entry = {}
            for child in item:
                entry[child.tag] = child.text
            items.append(entry)
    except ET.ParseError:
        pass
    return items


def kipris_search_patents(
    keyword: str,
    limit: int = 20,
) -> dict[str, Any]:
    """Search Korean patents and utility models by keyword via KIPRIS.

    Args:
        keyword: Search term (Korean or English), e.g. '자연어처리', 'LLM'.
        limit:   Max results to return (default 20).

    Returns patent titles, application dates, applicants, and IPC codes.
    Useful for assessing a company's Korean IP activity and technology focus.
    """
    if not KIPRIS_API_KEY:
        return {
            "error": "KIPRIS_API_KEY not configured",
            "action": (
                "Get a free API key at plus.kipris.or.kr, then add "
                "KIPRIS_API_KEY to your .env file. "
                "Alternatively, use web_search to find Korean patent information."
            ),
        }

    try:
        import requests
        resp = requests.get(
            f"{_BASE}/freeSearchInfo",
            params={
                "word": keyword,
                "patent": "true",
                "utility": "true",
                "numOfRows": limit,
                "pageNo": 1,
                "ServiceKey": KIPRIS_API_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()

        items = _parse_xml_items(resp.text)
        if not items:
            return {
                "keyword": keyword,
                "total_found": 0,
                "message": f"No Korean patents found for '{keyword}'.",
            }

        patents = []
        for item in items[:limit]:
            patents.append({
                "title": item.get("inventionTitle", ""),
                "applicant": item.get("applicantName", ""),
                "application_date": item.get("applicationDate", ""),
                "application_number": item.get("applicationNumber", ""),
                "ipc_code": item.get("ipcNumber", ""),
                "registration_status": item.get("registerStatus", ""),
            })

        return {
            "keyword": keyword,
            "total_found": len(patents),
            "patents": patents,
        }

    except Exception as exc:
        return {
            "error": str(exc),
            "action": "Use web_search to find Korean patent information instead.",
        }


def kipris_search_by_applicant(
    applicant_name: str,
    limit: int = 20,
) -> dict[str, Any]:
    """Search Korean patents by applicant (company) name.

    Args:
        applicant_name: Company name in Korean, e.g. '삼성전자', '업스테이지'.
        limit:          Max results (default 20).

    Returns the company's Korean patent portfolio — count, recent filings, tech areas.
    """
    if not KIPRIS_API_KEY:
        return {
            "error": "KIPRIS_API_KEY not configured",
            "action": "Use web_search to find Korean patent information instead.",
        }

    try:
        import requests
        resp = requests.get(
            f"{_BASE}/applicantNameSearchInfo",
            params={
                "applicant": applicant_name,
                "patent": "true",
                "numOfRows": limit,
                "pageNo": 1,
                "ServiceKey": KIPRIS_API_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()

        items = _parse_xml_items(resp.text)
        if not items:
            return {
                "applicant": applicant_name,
                "total_found": 0,
                "message": f"No Korean patents found for applicant '{applicant_name}'.",
            }

        patents = []
        ipc_counts: dict[str, int] = {}
        for item in items[:limit]:
            ipc = item.get("ipcNumber", "")[:4]  # Main IPC section
            if ipc:
                ipc_counts[ipc] = ipc_counts.get(ipc, 0) + 1
            patents.append({
                "title": item.get("inventionTitle", ""),
                "application_date": item.get("applicationDate", ""),
                "application_number": item.get("applicationNumber", ""),
                "ipc_code": item.get("ipcNumber", ""),
                "registration_status": item.get("registerStatus", ""),
            })

        return {
            "applicant": applicant_name,
            "total_found": len(patents),
            "technology_focus": dict(sorted(ipc_counts.items(), key=lambda x: -x[1])),
            "recent_patents": patents,
        }

    except Exception as exc:
        return {
            "error": str(exc),
            "action": "Use web_search to find Korean patent information instead.",
        }


# ── Anthropic tool definitions ────────────────────────────────────────────────

KIPRIS_SEARCH_PATENTS_TOOL = {
    "name": "kipris_search_patents",
    "description": (
        "Search Korean patents and utility models by keyword via KIPRIS (Korean IP office). "
        "Returns titles, applicants, application dates, IPC codes, and registration status. "
        "Use this for Korean companies' domestic patent portfolios — complements USPTO PatentsView "
        "which only covers US patents. Search in Korean for best results (e.g. '자연어처리')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "Search keyword (Korean or English), e.g. '자연어처리', 'LLM', '배터리'.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return (default 20).",
                "default": 20,
            },
        },
        "required": ["keyword"],
    },
}

KIPRIS_SEARCH_BY_APPLICANT_TOOL = {
    "name": "kipris_search_by_applicant",
    "description": (
        "Search Korean patents by applicant (company) name via KIPRIS. "
        "Returns the company's Korean patent portfolio: count, technology focus areas (IPC codes), "
        "and recent filings. Use with the Korean company name (e.g. '삼성전자', '업스테이지')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "applicant_name": {
                "type": "string",
                "description": "Company name in Korean, e.g. '삼성전자', '카카오'.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return (default 20).",
                "default": 20,
            },
        },
        "required": ["applicant_name"],
    },
}


def execute_tool(name: str, inputs: dict) -> str:
    if name == "kipris_search_patents":
        result = kipris_search_patents(**inputs)
    elif name == "kipris_search_by_applicant":
        result = kipris_search_by_applicant(**inputs)
    else:
        raise ValueError(f"Unknown KIPRIS tool: {name}")
    return json.dumps(result, ensure_ascii=False, default=str)
