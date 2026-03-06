"""PDF parsing tools via PyMuPDF."""
from __future__ import annotations

import json
from typing import Any

import fitz  # PyMuPDF


_MAX_TEXT_CHARS = 18_000  # keep under the 20K tool result cap in base.py


def extract_pdf_text(file_path: str, page_range: str | None = None) -> dict[str, Any]:
    """Extract text from a PDF file.

    Args:
        file_path: Path to the PDF file.
        page_range: Optional page range string like "1-5" or "3" (1-indexed).
                    If None, extracts all pages (auto-truncates with warning).

    Returns:
        Dict with keys: file, total_pages, extracted_pages, text.
        If the document is too large, includes 'warning' with instructions
        to call again with page_range for remaining pages.
    """
    try:
        doc = fitz.open(file_path)
        try:
            total_pages = len(doc)

            # Parse page range
            pages_to_extract: list[int]
            if page_range is None:
                pages_to_extract = list(range(total_pages))
            else:
                pages_to_extract = _parse_page_range(page_range, total_pages)

            texts = []
            last_extracted = 0
            total_chars = 0
            for page_num in pages_to_extract:
                if 0 <= page_num < total_pages:
                    page = doc[page_num]
                    page_text = f"[Page {page_num + 1}]\n{page.get_text()}"
                    if total_chars + len(page_text) > _MAX_TEXT_CHARS and texts:
                        # Would exceed limit — stop here and warn
                        remaining_start = page_num + 1  # 0-indexed
                        remaining_end = pages_to_extract[-1] + 1
                        return {
                            "file": file_path,
                            "total_pages": total_pages,
                            "extracted_pages": [p + 1 for p in pages_to_extract[:len(texts)]],
                            "text": "\n\n".join(texts),
                            "warning": (
                                f"DOCUMENT TOO LARGE — only extracted pages 1-{page_num}. "
                                f"Pages {remaining_start + 1}-{remaining_end} were NOT read. "
                                f"You MUST call extract_pdf_text again with "
                                f"page_range=\"{remaining_start + 1}-{remaining_end}\" "
                                f"to read the remaining pages. Do NOT skip them — they may "
                                f"contain critical data (investment rounds, valuations, etc.)."
                            ),
                        }
                    texts.append(page_text)
                    total_chars += len(page_text)
                    last_extracted = page_num

            return {
                "file": file_path,
                "total_pages": total_pages,
                "extracted_pages": [p + 1 for p in pages_to_extract],
                "text": "\n\n".join(texts),
            }
        finally:
            doc.close()
    except Exception as e:
        return {"file": file_path, "error": str(e)}


def extract_pdf_tables(file_path: str) -> dict[str, Any]:
    """Extract tables from a PDF using PyMuPDF's table finder.

    Args:
        file_path: Path to the PDF file.

    Returns:
        Dict with keys: file, total_pages, tables (list of table dicts).
        Capped at ~18K chars total to avoid blowing up tool results.
    """
    try:
        doc = fitz.open(file_path)
        try:
            total_pages = len(doc)
            all_tables = []
            total_chars = 0

            for page_num in range(total_pages):
                page = doc[page_num]
                tabs = page.find_tables()
                for i, table in enumerate(tabs.tables):
                    rows = table.extract()
                    entry = {
                        "page": page_num + 1,
                        "table_index": i,
                        "rows": rows,
                    }
                    entry_size = len(json.dumps(entry, ensure_ascii=False, default=str))
                    if total_chars + entry_size > _MAX_TEXT_CHARS and all_tables:
                        return {
                            "file": file_path,
                            "total_pages": total_pages,
                            "tables": all_tables,
                            "warning": (
                                f"Table extraction stopped at page {page_num + 1} "
                                f"due to size limit. {total_pages - page_num} pages "
                                f"not scanned for tables."
                            ),
                        }
                    all_tables.append(entry)
                    total_chars += entry_size

            return {
                "file": file_path,
                "total_pages": total_pages,
                "tables": all_tables,
            }
        finally:
            doc.close()
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
