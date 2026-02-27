"""PatentsView (USPTO) tools — free API key at search.patentsview.org/docs."""
from __future__ import annotations

import json
from typing import Any

import requests

from config import PATENTSVIEW_API_KEY

_BASE = "https://search.patentsview.org/api/v1"


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if PATENTSVIEW_API_KEY:
        h["X-Api-Key"] = PATENTSVIEW_API_KEY
    return h


def search_patents(
    assignee_name: str,
    year_from: int = 2015,
    limit: int = 25,
) -> dict[str, Any]:
    """Search US patents assigned to a company via the USPTO PatentsView API.

    Args:
        assignee_name: Company name as it appears on patents, e.g. 'Apple Inc.'.
        year_from:     Only return patents filed from this year onwards.
        limit:         Max patents to return (default 25).

    Returns patent count, technology categories, and recent patent titles.
    Useful for assessing IP portfolio strength and R&D focus areas.
    """
    if not PATENTSVIEW_API_KEY:
        return {
            "error": "PATENTSVIEW_API_KEY not configured",
            "action": (
                "Get a free API key at search.patentsview.org/docs, then add "
                "PATENTSVIEW_API_KEY to your environment. "
                "Alternatively, use web_search to find patent information."
            ),
        }

    try:
        payload = {
            "q": {
                "_and": [
                    {"_text_phrase": {"patent_assignees.assignee_organization": assignee_name}},
                    {"_gte": {"patent_date": f"{year_from}-01-01"}},
                ]
            },
            "f": [
                "patent_id", "patent_date", "patent_title",
                "patent_abstract", "patent_type",
                "patent_assignees.assignee_organization",
                "patent_cpcs.cpc_section_id",
                "patent_cpcs.cpc_group_id",
            ],
            "o": {"per_page": limit, "page": 1},
            "s": [{"patent_date": "desc"}],
        }

        resp = requests.post(
            f"{_BASE}/patent/",
            json=payload,
            headers=_headers(),
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()

        patents = data.get("patents") or []
        total   = data.get("total_patent_count") or len(patents)

        if not patents:
            return {
                "assignee":    assignee_name,
                "total_found": 0,
                "message":     f"No patents found for '{assignee_name}' from {year_from}. "
                               "Try the exact legal entity name as it appears on filings.",
            }

        # Summarise CPC technology sections
        cpc_counts: dict[str, int] = {}
        for p in patents:
            for cpc in (p.get("patent_cpcs") or []):
                section = cpc.get("cpc_section_id", "Unknown")
                cpc_counts[section] = cpc_counts.get(section, 0) + 1

        cpc_labels = {
            "A": "Human Necessities",
            "B": "Performing Operations / Transporting",
            "C": "Chemistry / Metallurgy",
            "D": "Textiles / Paper",
            "E": "Fixed Constructions",
            "F": "Mechanical Engineering",
            "G": "Physics / Computing",
            "H": "Electricity / Electronics",
            "Y": "New Technological Developments",
        }

        recent = []
        for p in patents[:15]:
            abstract = (p.get("patent_abstract") or "")[:200]
            recent.append({
                "id":       p.get("patent_id"),
                "date":     p.get("patent_date"),
                "title":    p.get("patent_title"),
                "abstract": abstract + ("…" if len(abstract) == 200 else ""),
                "type":     p.get("patent_type"),
            })

        return {
            "assignee":          assignee_name,
            "total_found":       total,
            "showing":           len(recent),
            "year_from":         year_from,
            "technology_focus":  {
                cpc_labels.get(k, k): v
                for k, v in sorted(cpc_counts.items(), key=lambda x: -x[1])
            },
            "recent_patents":    recent,
        }

    except requests.exceptions.Timeout:
        return {
            "error": "PatentsView API timed out",
            "action": "Use web_search to find patent information for this company instead.",
        }
    except Exception as exc:
        return {
            "error": str(exc),
            "action": "Use web_search to find patent information instead.",
        }


def get_patent_detail(patent_id: str) -> dict[str, Any]:
    """Fetch full details for a specific patent by its USPTO ID."""
    if not PATENTSVIEW_API_KEY:
        return {"error": "PATENTSVIEW_API_KEY not configured",
                "action": "Use web_search to find patent details instead."}

    try:
        payload = {
            "q": {"patent_id": patent_id},
            "f": [
                "patent_id", "patent_date", "patent_title", "patent_abstract",
                "patent_claims", "patent_assignees.assignee_organization",
                "inventors.inventor_first_name", "inventors.inventor_last_name",
                "patent_cpcs.cpc_group_id",
            ],
        }
        resp = requests.post(
            f"{_BASE}/patent/",
            json=payload,
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data  = resp.json()
        items = data.get("patents") or []
        if not items:
            return {"error": f"Patent '{patent_id}' not found"}
        p = items[0]
        inventors = [
            f"{i.get('inventor_first_name','')} {i.get('inventor_last_name','')}".strip()
            for i in (p.get("inventors") or [])
        ]
        return {
            "patent_id":  p.get("patent_id"),
            "date":       p.get("patent_date"),
            "title":      p.get("patent_title"),
            "abstract":   p.get("patent_abstract"),
            "claims":     (p.get("patent_claims") or "")[:500],
            "assignees":  [a.get("assignee_organization") for a in (p.get("patent_assignees") or [])],
            "inventors":  inventors,
        }
    except Exception as exc:
        return {"error": str(exc)}


# ── Anthropic tool definitions ────────────────────────────────────────────────

SEARCH_PATENTS_TOOL = {
    "name": "search_patents",
    "description": (
        "Search US patents assigned to a company via the USPTO PatentsView database. "
        "Returns total patent count, technology focus areas (CPC classification), "
        "and titles/abstracts of recent patents. "
        "Use this to assess the strength and breadth of a company's IP portfolio, "
        "identify their core R&D areas, and flag potential patent moats or gaps. "
        "Works best with the exact legal entity name (e.g. 'Apple Inc.' not 'Apple')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "assignee_name": {
                "type": "string",
                "description": "Company legal name on patents, e.g. 'Apple Inc.', 'NVIDIA Corporation'.",
            },
            "year_from": {
                "type": "integer",
                "description": "Only include patents from this year onwards (default 2015).",
                "default": 2015,
            },
            "limit": {
                "type": "integer",
                "description": "Max patents to retrieve (default 25).",
                "default": 25,
            },
        },
        "required": ["assignee_name"],
    },
}

GET_PATENT_DETAIL_TOOL = {
    "name": "get_patent_detail",
    "description": (
        "Fetch full details for a specific US patent by its ID (e.g. '10123456'). "
        "Returns title, abstract, claims, inventors, and assignees. "
        "Use after search_patents to deep-dive into a key patent."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "patent_id": {
                "type": "string",
                "description": "USPTO patent number, e.g. '10123456'.",
            },
        },
        "required": ["patent_id"],
    },
}


def execute_tool(name: str, inputs: dict) -> str:
    if name == "search_patents":
        result = search_patents(**inputs)
    elif name == "get_patent_detail":
        result = get_patent_detail(**inputs)
    else:
        raise ValueError(f"Unknown patents tool: {name}")
    return json.dumps(result, ensure_ascii=False, default=str)
