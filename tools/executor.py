"""Tool routing and execution for agent tool calls."""
from __future__ import annotations

from tools import tavily_tools, edgar_tools, pdf_tools

# Map tool name → executor module
_TOOL_REGISTRY: dict[str, object] = {}

for _mod in (tavily_tools, edgar_tools, pdf_tools):
    # Each module exposes an execute_tool(name, inputs) function
    _TOOL_REGISTRY[_mod.__name__.split(".")[-1]] = _mod


def get_all_tools() -> list[dict]:
    """Return all Anthropic tool definitions."""
    return [
        tavily_tools.WEB_SEARCH_TOOL,
        tavily_tools.NEWS_SEARCH_TOOL,
        edgar_tools.GET_SEC_FILINGS_TOOL,
        edgar_tools.GET_COMPANY_FACTS_TOOL,
        pdf_tools.EXTRACT_PDF_TEXT_TOOL,
        pdf_tools.EXTRACT_PDF_TABLES_TOOL,
    ]


def get_tools_for_agent(agent_type: str) -> list[dict]:
    """Return the appropriate tool subset for a given agent type."""
    tool_map = {
        # Phase 1
        "financial_analyst": [
            edgar_tools.GET_SEC_FILINGS_TOOL,
            edgar_tools.GET_COMPANY_FACTS_TOOL,
            tavily_tools.WEB_SEARCH_TOOL,
            pdf_tools.EXTRACT_PDF_TEXT_TOOL,
            pdf_tools.EXTRACT_PDF_TABLES_TOOL,
        ],
        "market_research": [
            tavily_tools.WEB_SEARCH_TOOL,
            tavily_tools.NEWS_SEARCH_TOOL,
        ],
        "legal_risk": [
            tavily_tools.WEB_SEARCH_TOOL,
            tavily_tools.NEWS_SEARCH_TOOL,
            pdf_tools.EXTRACT_PDF_TEXT_TOOL,
        ],
        "management_team": [
            tavily_tools.WEB_SEARCH_TOOL,
            tavily_tools.NEWS_SEARCH_TOOL,
        ],
        "tech_product": [
            tavily_tools.WEB_SEARCH_TOOL,
            tavily_tools.NEWS_SEARCH_TOOL,
        ],
        # Phase 2
        "bull_case": [],        # reads state only — no live tools
        "bear_case": [],
        "valuation": [
            tavily_tools.WEB_SEARCH_TOOL,
            edgar_tools.GET_SEC_FILINGS_TOOL,
        ],
        "red_flag": [],
        # Phase 3
        "fact_checker": [
            tavily_tools.WEB_SEARCH_TOOL,
            tavily_tools.NEWS_SEARCH_TOOL,
        ],
        "stress_test": [],
        "completeness": [],
        # Phase 4
        "final_report": [],
    }
    return tool_map.get(agent_type, [])


def execute_tool_call(tool_name: str, tool_input: dict) -> str:
    """Route and execute a tool call, returning the result as a string."""
    # Tavily tools
    if tool_name in ("web_search", "news_search"):
        return tavily_tools.execute_tool(tool_name, tool_input)
    # EDGAR tools
    if tool_name in ("get_sec_filings", "get_company_facts"):
        return edgar_tools.execute_tool(tool_name, tool_input)
    # PDF tools
    if tool_name in ("extract_pdf_text", "extract_pdf_tables"):
        return pdf_tools.execute_tool(tool_name, tool_input)
    raise ValueError(f"Unknown tool: {tool_name}")
