"""Tool routing and execution for agent tool calls."""
from __future__ import annotations

import json as _json
import threading

from tools import tavily_tools, edgar_tools, dart_tools, pdf_tools, yfinance_tools
from tools import pytrends_tools, fred_tools, github_tools, patents_tools
from tools import kipris_tools, kosis_tools

# ── Per-run tool result cache ────────────────────────────────────────────────
# Keyed on (tool_name, frozen_input). Shared across threads within a single
# analysis run. Call reset_tool_cache() at the start of each pipeline run.
_cache_lock = threading.Lock()
_tool_cache: dict[tuple, str] = {}


def reset_tool_cache() -> None:
    """Clear the tool result cache. Call at pipeline start."""
    global _tool_cache
    with _cache_lock:
        _tool_cache = {}


def _cache_key(tool_name: str, tool_input: dict) -> tuple:
    """Build a hashable cache key from tool name + input."""
    frozen = _json.dumps(tool_input, sort_keys=True, default=str)
    return (tool_name, frozen)


def get_all_tools() -> list[dict]:
    """Return all Anthropic tool definitions."""
    return [
        tavily_tools.WEB_SEARCH_TOOL,
        tavily_tools.NEWS_SEARCH_TOOL,
        edgar_tools.GET_SEC_FILINGS_TOOL,
        edgar_tools.GET_COMPANY_FACTS_TOOL,
        pdf_tools.EXTRACT_PDF_TEXT_TOOL,
        pdf_tools.EXTRACT_PDF_TABLES_TOOL,
        yfinance_tools.YF_GET_INFO_TOOL,
        yfinance_tools.YF_GET_FINANCIALS_TOOL,
        yfinance_tools.YF_GET_ANALYST_DATA_TOOL,
    ]


def get_tools_for_agent(agent_type: str) -> list[dict]:
    """Return the appropriate tool subset for a given agent type."""
    tool_map = {
        # Phase 1 — Research & Analysis (6 parallel)
        "market_analysis": [
            tavily_tools.WEB_SEARCH_TOOL,
            tavily_tools.NEWS_SEARCH_TOOL,
            yfinance_tools.YF_GET_INFO_TOOL,
            pytrends_tools.GOOGLE_TRENDS_INTEREST_TOOL,
            pytrends_tools.GOOGLE_TRENDS_RELATED_TOOL,
            kosis_tools.KOSIS_SEARCH_TABLES_TOOL,
            kosis_tools.KOSIS_GET_STATISTICS_TOOL,
            pdf_tools.EXTRACT_PDF_TEXT_TOOL,
            pdf_tools.EXTRACT_PDF_TABLES_TOOL,
        ],
        "competitor_analysis": [
            tavily_tools.WEB_SEARCH_TOOL,
            yfinance_tools.YF_GET_INFO_TOOL,
            pdf_tools.EXTRACT_PDF_TEXT_TOOL,
            pdf_tools.EXTRACT_PDF_TABLES_TOOL,
        ],
        "financial_analysis": [
            dart_tools.DART_FINSTATE_TOOL,
            dart_tools.DART_COMPANY_TOOL,
            dart_tools.DART_LIST_TOOL,
            yfinance_tools.YF_GET_INFO_TOOL,
            yfinance_tools.YF_GET_FINANCIALS_TOOL,
            yfinance_tools.YF_GET_ANALYST_DATA_TOOL,
            edgar_tools.GET_SEC_FILINGS_TOOL,
            edgar_tools.GET_COMPANY_FACTS_TOOL,
            tavily_tools.WEB_SEARCH_TOOL,
            pdf_tools.EXTRACT_PDF_TEXT_TOOL,
            pdf_tools.EXTRACT_PDF_TABLES_TOOL,
        ],
        "tech_analysis": [
            tavily_tools.WEB_SEARCH_TOOL,
            github_tools.GITHUB_SEARCH_REPOS_TOOL,
            github_tools.GITHUB_REPO_STATS_TOOL,
            patents_tools.SEARCH_PATENTS_TOOL,
            kipris_tools.KIPRIS_SEARCH_PATENTS_TOOL,
            kipris_tools.KIPRIS_SEARCH_BY_APPLICANT_TOOL,
            pdf_tools.EXTRACT_PDF_TEXT_TOOL,
            pdf_tools.EXTRACT_PDF_TABLES_TOOL,
        ],
        "legal_regulatory": [
            dart_tools.DART_LIST_TOOL,
            tavily_tools.WEB_SEARCH_TOOL,
            tavily_tools.NEWS_SEARCH_TOOL,
            patents_tools.PATENT_SEARCH_TOOL,
            kipris_tools.KIPRIS_SEARCH_PATENTS_TOOL,
            kipris_tools.KIPRIS_SEARCH_BY_APPLICANT_TOOL,
            pdf_tools.EXTRACT_PDF_TEXT_TOOL,
            pdf_tools.EXTRACT_PDF_TABLES_TOOL,
        ],
        "team_analysis": [
            tavily_tools.WEB_SEARCH_TOOL,
            pdf_tools.EXTRACT_PDF_TEXT_TOOL,
            pdf_tools.EXTRACT_PDF_TABLES_TOOL,
        ],
        # Phase 2 — Synthesis (no tools, work from Phase 1 data)
        "ra_synthesis": [],
        "risk_assessment": [
            tavily_tools.WEB_SEARCH_TOOL,
            tavily_tools.NEWS_SEARCH_TOOL,
        ],
        "strategic_insight": [],
        "industry_synthesis": [],
        "benchmark_synthesis": [],
        # Phase 3 — Review & Critique
        "review_agent": [
            dart_tools.DART_FINSTATE_TOOL,
            tavily_tools.WEB_SEARCH_TOOL,
            yfinance_tools.YF_GET_INFO_TOOL,
        ],
        "critique_agent": [],
        "dd_questions": [],
        # Phase 4 — Output
        "report_structure": [],
        "report_writer": [],
    }
    return tool_map.get(agent_type, [])


def execute_tool_call(tool_name: str, tool_input: dict) -> str:
    """Route and execute a tool call, returning the result as a string.

    Results are cached per-run so duplicate calls (e.g. yf_get_info("AAPL")
    from multiple agents) return instantly without re-calling the API.

    Never raises — on any failure returns a structured JSON error so the
    agent can fall back to web_search instead of crashing.
    """
    key = _cache_key(tool_name, tool_input)
    with _cache_lock:
        if key in _tool_cache:
            return _tool_cache[key]

    try:
        result = _dispatch_tool(tool_name, tool_input)
    except Exception as exc:
        return _tool_error(tool_name, str(exc), _fallback_for(tool_name))

    with _cache_lock:
        _tool_cache[key] = result
    return result


_TOOL_DISPATCH: dict[str, object] = {
    "web_search":              tavily_tools,
    "news_search":             tavily_tools,
    "get_sec_filings":         edgar_tools,
    "get_company_facts":       edgar_tools,
    "dart_finstate":           dart_tools,
    "dart_company":            dart_tools,
    "dart_list":               dart_tools,
    "extract_pdf_text":        pdf_tools,
    "extract_pdf_tables":      pdf_tools,
    "yf_get_info":             yfinance_tools,
    "yf_get_financials":       yfinance_tools,
    "yf_get_analyst_data":     yfinance_tools,
    "google_trends_interest":  pytrends_tools,
    "google_trends_related":   pytrends_tools,
    "fred_get_series":         fred_tools,
    "fred_search_series":      fred_tools,
    "github_search_repos":     github_tools,
    "github_repo_stats":       github_tools,
    "search_patents":          patents_tools,
    "get_patent_detail":       patents_tools,
    "kipris_search_patents":       kipris_tools,
    "kipris_search_by_applicant":  kipris_tools,
    "kosis_get_statistics":        kosis_tools,
    "kosis_search_tables":         kosis_tools,
}


def _dispatch_tool(tool_name: str, tool_input: dict) -> str:
    """Route a tool call to the correct executor module."""
    module = _TOOL_DISPATCH.get(tool_name)
    if module is None:
        return _tool_error(tool_name, f"Unknown tool '{tool_name}'", "web_search")
    return module.execute_tool(tool_name, tool_input)


def _fallback_for(tool_name: str) -> str:
    """Return the recommended fallback tool name for a given tool."""
    _fallbacks = {
        "dart_finstate":             "web_search",
        "dart_company":             "web_search",
        "dart_list":                "web_search",
        "get_sec_filings":          "web_search",
        "get_company_facts":        "web_search",
        "yf_get_info":              "web_search",
        "yf_get_financials":        "web_search",
        "yf_get_analyst_data":      "web_search",
        "extract_pdf_text":         "web_search",
        "extract_pdf_tables":       "web_search",
        "news_search":              "web_search",
        "google_trends_interest":   "web_search",
        "google_trends_related":    "web_search",
        "fred_get_series":          "web_search",
        "fred_search_series":       "web_search",
        "github_search_repos":      "web_search",
        "github_repo_stats":        "web_search",
        "search_patents":           "web_search",
        "get_patent_detail":        "web_search",
        "kipris_search_patents":        "web_search",
        "kipris_search_by_applicant":   "web_search",
        "kosis_get_statistics":         "web_search",
        "kosis_search_tables":          "web_search",
    }
    return _fallbacks.get(tool_name, "web_search")


def _tool_error(tool_name: str, message: str, fallback: str) -> str:
    """Return a structured JSON error that guides the agent to a fallback."""
    import json
    return json.dumps({
        "error": "tool_unavailable",
        "tool": tool_name,
        "message": message,
        "action": f"Use '{fallback}' to find the same information instead.",
    })
