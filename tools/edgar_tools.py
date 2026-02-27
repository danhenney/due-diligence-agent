"""SEC EDGAR tools via edgartools."""
from __future__ import annotations

import json
from typing import Any

import edgar

from config import EDGAR_USER_AGENT

# Set user agent once at import time
edgar.set_identity(EDGAR_USER_AGENT)


def get_sec_filings(ticker: str, form_type: str = "10-K", count: int = 3) -> list[dict[str, Any]]:
    """Retrieve recent SEC filings for a ticker.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL").
        form_type: SEC form type — "10-K", "10-Q", "8-K", etc.
        count: Number of most-recent filings to return.

    Returns:
        List of dicts with keys: form, filed, period, description, text_excerpt.
    """
    try:
        company = edgar.Company(ticker)
        filings = company.get_filings(form=form_type).latest(count)
        results = []
        for filing in filings:
            try:
                doc = filing.obj()
                # Grab a text excerpt (first 3000 chars of the primary document)
                text = ""
                try:
                    text = filing.text()[:3000]
                except Exception:
                    pass
                results.append({
                    "form": filing.form,
                    "filed": str(filing.filing_date),
                    "period": str(getattr(filing, "period_of_report", "")),
                    "accession": filing.accession_no,
                    "url": filing.filing_index_url,
                    "text_excerpt": text,
                })
            except Exception as e:
                results.append({
                    "form": form_type,
                    "error": str(e),
                })
        return results
    except Exception as e:
        return [{"error": f"Could not retrieve filings for {ticker}: {e}"}]


def get_company_facts(ticker: str) -> dict[str, Any]:
    """Retrieve key financial facts / metadata for a ticker via EDGAR.

    Returns a dict with company info and available financial concepts.
    """
    try:
        company = edgar.Company(ticker)
        facts: dict[str, Any] = {
            "name": company.name,
            "cik": company.cik,
            "ticker": ticker,
            "sic": getattr(company, "sic", None),
            "sic_description": getattr(company, "sic_description", None),
            "category": getattr(company, "category", None),
            "state_of_incorporation": getattr(company, "state_of_incorporation", None),
            "fiscal_year_end": getattr(company, "fiscal_year_end", None),
        }
        return facts
    except Exception as e:
        return {"error": f"Could not retrieve facts for {ticker}: {e}"}


# ── Anthropic tool definitions ────────────────────────────────────────────────

GET_SEC_FILINGS_TOOL = {
    "name": "get_sec_filings",
    "description": (
        "Retrieve recent SEC filings (10-K annual reports, 10-Q quarterly reports, 8-K current reports) "
        "for a publicly traded US company using its ticker symbol."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol (e.g. 'AAPL', 'MSFT').",
            },
            "form_type": {
                "type": "string",
                "description": "SEC form type: '10-K', '10-Q', or '8-K'. Default '10-K'.",
                "enum": ["10-K", "10-Q", "8-K"],
                "default": "10-K",
            },
            "count": {
                "type": "integer",
                "description": "Number of recent filings to retrieve (default 3).",
                "default": 3,
            },
        },
        "required": ["ticker"],
    },
}

GET_COMPANY_FACTS_TOOL = {
    "name": "get_company_facts",
    "description": (
        "Retrieve basic company information and financial metadata from SEC EDGAR "
        "for a publicly traded US company."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol (e.g. 'AAPL', 'MSFT').",
            },
        },
        "required": ["ticker"],
    },
}


def execute_tool(name: str, inputs: dict) -> str:
    """Dispatch an EDGAR tool call and return JSON string result."""
    if name == "get_sec_filings":
        result = get_sec_filings(**inputs)
    elif name == "get_company_facts":
        result = get_company_facts(**inputs)
    else:
        raise ValueError(f"Unknown EDGAR tool: {name}")
    return json.dumps(result, ensure_ascii=False, default=str)
