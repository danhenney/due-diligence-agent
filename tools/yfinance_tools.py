"""Yahoo Finance tools via yfinance — free, no API key required."""
from __future__ import annotations

import json
import math
from typing import Any

import yfinance as yf


def _clean(val: Any) -> Any:
    """Make a value JSON-serialisable; drop NaN/Inf."""
    if val is None:
        return None
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    if hasattr(val, "item"):          # numpy scalar
        return _clean(val.item())
    if hasattr(val, "isoformat"):     # datetime / Timestamp
        return val.isoformat()[:10]
    return val


def _df_to_dict(df, keep_rows: list[str] | None = None) -> dict:
    """Convert a yfinance DataFrame to a plain dict {row: {date: value}}.

    If keep_rows is provided only those row labels are included (others
    are silently skipped when absent).
    """
    if df is None or df.empty:
        return {}
    rows = keep_rows if keep_rows else list(df.index)
    out: dict = {}
    for row in rows:
        if row not in df.index:
            continue
        series = df.loc[row]
        row_data = {}
        for col, val in series.items():
            date_str = _clean(col) or str(col)
            v = _clean(val)
            if v is not None:
                row_data[date_str] = v
        if row_data:
            out[row] = row_data
    return out


# ── Public functions ──────────────────────────────────────────────────────────

def yf_get_info(ticker: str) -> dict[str, Any]:
    """Return company overview and current valuation multiples.

    Useful for public companies. Returns empty dict for unknown tickers.
    """
    try:
        info = yf.Ticker(ticker.strip().upper()).info
    except Exception as exc:
        return {"error": str(exc)}

    if not info or info.get("quoteType") == "NONE":
        return {"error": f"No data found for ticker '{ticker}'"}

    fields = [
        # Identity
        "longName", "sector", "industry", "country", "website",
        "fullTimeEmployees", "longBusinessSummary",
        # Price & market cap
        "currentPrice", "previousClose", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
        "marketCap", "enterpriseValue",
        # Valuation multiples
        "trailingPE", "forwardPE", "priceToBook",
        "priceToSalesTrailing12Months",
        "enterpriseToRevenue", "enterpriseToEbitda",
        # Profitability
        "grossMargins", "operatingMargins", "profitMargins", "ebitdaMargins",
        # Growth
        "revenueGrowth", "earningsGrowth", "earningsQuarterlyGrowth",
        # Balance sheet snapshot
        "totalCash", "totalCashPerShare", "totalDebt", "debtToEquity",
        "currentRatio", "quickRatio", "freeCashflow",
        # Returns
        "returnOnEquity", "returnOnAssets",
        # Analyst consensus
        "targetMeanPrice", "targetHighPrice", "targetLowPrice",
        "targetMedianPrice", "recommendationKey", "numberOfAnalystOpinions",
        # Risk
        "beta", "auditRisk", "boardRisk", "compensationRisk",
        "shareHolderRightsRisk", "overallRisk",
        # Dividends
        "dividendYield", "payoutRatio",
    ]

    result = {k: _clean(info.get(k)) for k in fields if info.get(k) is not None}

    # Compute implied upside to analyst mean target
    price = result.get("currentPrice")
    target = result.get("targetMeanPrice")
    if price and target and price > 0:
        result["impliedUpsideToTarget"] = round((target - price) / price * 100, 1)

    return result


def yf_get_financials(ticker: str, period: str = "annual") -> dict[str, Any]:
    """Return structured income statement, balance sheet, and cash flow.

    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL').
        period: 'annual' (last 4 years) or 'quarterly' (last 4 quarters).
    """
    try:
        t = yf.Ticker(ticker.strip().upper())
    except Exception as exc:
        return {"error": str(exc)}

    if period == "quarterly":
        inc = t.quarterly_income_stmt
        bal = t.quarterly_balance_sheet
        cf  = t.quarterly_cashflow
    else:
        inc = t.income_stmt
        bal = t.balance_sheet
        cf  = t.cashflow

    income_rows = [
        "Total Revenue", "Cost Of Revenue", "Gross Profit",
        "Operating Income", "EBITDA", "Net Income",
        "Basic EPS", "Diluted EPS",
        "Research And Development", "Selling General And Administrative",
    ]
    balance_rows = [
        "Total Assets", "Total Liabilities Net Minority Interest",
        "Total Debt", "Long Term Debt", "Current Debt",
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
        "Stockholders Equity", "Total Equity Gross Minority Interest",
        "Current Assets", "Current Liabilities",
        "Inventory", "Accounts Receivable",
    ]
    cashflow_rows = [
        "Operating Cash Flow", "Capital Expenditure", "Free Cash Flow",
        "Issuance Of Debt", "Repayment Of Debt",
        "Repurchase Of Capital Stock", "Common Stock Dividend Paid",
        "Changes In Cash",
    ]

    return {
        "period":           period,
        "income_statement": _df_to_dict(inc, income_rows),
        "balance_sheet":    _df_to_dict(bal, balance_rows),
        "cash_flow":        _df_to_dict(cf,  cashflow_rows),
    }


def yf_get_analyst_data(ticker: str) -> dict[str, Any]:
    """Return analyst recommendations, price targets, and earnings estimates."""
    try:
        t    = yf.Ticker(ticker.strip().upper())
        info = t.info
    except Exception as exc:
        return {"error": str(exc)}

    result: dict[str, Any] = {
        "current_price":    _clean(info.get("currentPrice")),
        "target_mean":      _clean(info.get("targetMeanPrice")),
        "target_median":    _clean(info.get("targetMedianPrice")),
        "target_high":      _clean(info.get("targetHighPrice")),
        "target_low":       _clean(info.get("targetLowPrice")),
        "recommendation":   info.get("recommendationKey"),
        "num_analysts":     info.get("numberOfAnalystOpinions"),
    }

    price  = result["current_price"]
    target = result["target_mean"]
    if price and target and price > 0:
        result["upside_to_mean_target_pct"] = round((target - price) / price * 100, 1)

    # Recent ratings history (last 10 rows)
    try:
        recs = t.recommendations
        if recs is not None and not recs.empty:
            result["recent_ratings"] = [
                {k: _clean(v) for k, v in row.items()}
                for row in recs.tail(10).to_dict(orient="records")
            ]
    except Exception:
        pass

    # Earnings estimates table
    try:
        ee = t.earnings_estimate
        if ee is not None and not ee.empty:
            result["earnings_estimates"] = {
                str(idx): {
                    col: _clean(ee.loc[idx, col]) for col in ee.columns
                    if _clean(ee.loc[idx, col]) is not None
                }
                for idx in ee.index
            }
    except Exception:
        pass

    # Revenue estimates
    try:
        re = t.revenue_estimate
        if re is not None and not re.empty:
            result["revenue_estimates"] = {
                str(idx): {
                    col: _clean(re.loc[idx, col]) for col in re.columns
                    if _clean(re.loc[idx, col]) is not None
                }
                for idx in re.index
            }
    except Exception:
        pass

    return result


# ── Anthropic tool definitions ────────────────────────────────────────────────

YF_GET_INFO_TOOL = {
    "name": "yf_get_info",
    "description": (
        "Get a public company's current valuation metrics, profitability ratios, "
        "balance sheet snapshot, and analyst consensus via Yahoo Finance. "
        "Use this for any publicly traded company when you have a ticker symbol. "
        "Returns market cap, EV, P/E, EV/Revenue, EV/EBITDA, gross/operating margins, "
        "debt levels, free cash flow, analyst price targets, and more."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol, e.g. 'AAPL', 'MSFT', 'NVDA'.",
            },
        },
        "required": ["ticker"],
    },
}

YF_GET_FINANCIALS_TOOL = {
    "name": "yf_get_financials",
    "description": (
        "Get structured financial statements (income statement, balance sheet, cash flow) "
        "for a publicly traded company via Yahoo Finance. "
        "Use 'annual' for multi-year trend analysis or 'quarterly' for recent momentum. "
        "Returns revenue, gross profit, EBITDA, net income, EPS, total debt, cash, "
        "free cash flow, and more — already parsed into clean numbers."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol, e.g. 'AAPL'.",
            },
            "period": {
                "type": "string",
                "enum": ["annual", "quarterly"],
                "description": "'annual' for last 4 fiscal years (default), 'quarterly' for last 4 quarters.",
                "default": "annual",
            },
        },
        "required": ["ticker"],
    },
}

YF_GET_ANALYST_DATA_TOOL = {
    "name": "yf_get_analyst_data",
    "description": (
        "Get analyst recommendations, consensus price targets, and earnings/revenue estimates "
        "for a publicly traded company via Yahoo Finance. "
        "Returns buy/sell/hold breakdown, mean price target with implied upside, "
        "recent rating changes, and forward earnings and revenue estimates."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol, e.g. 'AAPL'.",
            },
        },
        "required": ["ticker"],
    },
}


def execute_tool(name: str, inputs: dict) -> str:
    """Dispatch a yfinance tool call and return a JSON string."""
    if name == "yf_get_info":
        result = yf_get_info(**inputs)
    elif name == "yf_get_financials":
        result = yf_get_financials(**inputs)
    elif name == "yf_get_analyst_data":
        result = yf_get_analyst_data(**inputs)
    else:
        raise ValueError(f"Unknown yfinance tool: {name}")
    return json.dumps(result, ensure_ascii=False, default=str)
