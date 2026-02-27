"""PDF parsing tools via PyMuPDF."""
from __future__ import annotations

import json
from typing import Any

import fitz  # PyMuPDF


def extract_pdf_text(file_path: str, page_range: str | None = None) -> dict[str, Any]:
    """Extract text from a PDF file.

    Args:
        file_path: Path to the PDF file.
        page_range: Optional page range string like "1-5" or "3" (1-indexed).
                    If None, extracts all pages.

    Returns:
        Dict with keys: file, total_pages, extracted_pages, text.
    """
    try:
        doc = fitz.open(file_path)
        total_pages = len(doc)

        # Parse page range
        pages_to_extract: list[int]
        if page_range is None:
            pages_to_extract = list(range(total_pages))
        else:
            pages_to_extract = _parse_page_range(page_range, total_pages)

        texts = []
        for page_num in pages_to_extract:
            if 0 <= page_num < total_pages:
                page = doc[page_num]
                texts.append(f"[Page {page_num + 1}]\n{page.get_text()}")

        doc.close()
        return {
            "file": file_path,
            "total_pages": total_pages,
            "extracted_pages": [p + 1 for p in pages_to_extract],
            "text": "\n\n".join(texts),
        }
    except Exception as e:
        return {"file": file_path, "error": str(e)}


def extract_pdf_tables(file_path: str) -> dict[str, Any]:
    """Extract tables from a PDF using PyMuPDF's table finder.

    Args:
        file_path: Path to the PDF file.

    Returns:
        Dict with keys: file, total_pages, tables (list of table dicts).
    """
    try:
        doc = fitz.open(file_path)
        all_tables = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            tabs = page.find_tables()
            for i, table in enumerate(tabs.tables):
                rows = table.extract()
                all_tables.append({
                    "page": page_num + 1,
                    "table_index": i,
                    "rows": rows,
                })

        doc.close()
        return {
            "file": file_path,
            "total_pages": len(doc) if not doc.is_closed else "?",
            "tables": all_tables,
        }
    except Exception as e:
        return {"file": file_path, "error": str(e)}


def _parse_page_range(page_range: str, total_pages: int) -> list[int]:
    """Parse a page range string into a list of 0-indexed page numbers."""
    pages = []
    for part in page_range.split(","):
        part = part.strip()
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            start = max(1, int(start_str.strip())) - 1
            end = min(total_pages, int(end_str.strip())) - 1
            pages.extend(range(start, end + 1))
        else:
            page = int(part) - 1
            if 0 <= page < total_pages:
                pages.append(page)
    return sorted(set(pages))


# ── Anthropic tool definitions ────────────────────────────────────────────────

EXTRACT_PDF_TEXT_TOOL = {
    "name": "extract_pdf_text",
    "description": (
        "Extract text content from a PDF document (e.g., pitch deck, financial report, legal filing). "
        "Optionally specify a page range to limit extraction."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute or relative path to the PDF file.",
            },
            "page_range": {
                "type": "string",
                "description": (
                    "Optional page range (1-indexed). Examples: '1-5', '3', '1-3,7-9'. "
                    "Omit to extract all pages."
                ),
            },
        },
        "required": ["file_path"],
    },
}

EXTRACT_PDF_TABLES_TOOL = {
    "name": "extract_pdf_tables",
    "description": (
        "Extract all tables from a PDF document. "
        "Useful for financial statements, comparison tables, and structured data."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute or relative path to the PDF file.",
            },
        },
        "required": ["file_path"],
    },
}


def execute_tool(name: str, inputs: dict) -> str:
    """Dispatch a PDF tool call and return JSON string result."""
    if name == "extract_pdf_text":
        result = extract_pdf_text(**inputs)
    elif name == "extract_pdf_tables":
        result = extract_pdf_tables(**inputs)
    else:
        raise ValueError(f"Unknown PDF tool: {name}")
    return json.dumps(result, ensure_ascii=False, default=str)
