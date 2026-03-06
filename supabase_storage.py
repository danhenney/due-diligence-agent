"""Supabase-backed storage for job state, history, and PDF reports.

Drop-in replacement for the old file-based helpers in app.py.
Requires SUPABASE_URL and SUPABASE_SERVICE_KEY in environment or Streamlit secrets.
"""
from __future__ import annotations

import json
import os
import time
import logging

_client = None

_STALE_JOB_TIMEOUT_SEC = 5400  # 90 minutes


def _get_client():
    """Lazy-init singleton Supabase client (service-role key)."""
    global _client
    if _client is not None:
        return _client

    import streamlit as st
    from supabase import create_client

    # Try Streamlit secrets first, then env vars
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    try:
        if not url:
            url = str(st.secrets.get("SUPABASE_URL", ""))
        if not key:
            key = str(st.secrets.get("SUPABASE_SERVICE_KEY", ""))
    except Exception:
        pass

    if not url or not key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_KEY. "
            "Add them to .env or Streamlit secrets."
        )

    _client = create_client(url, key)
    return _client


# ── Job state ────────────────────────────────────────────────────────────────

_JOB_DEFAULTS = {
    "status": "unknown",
    "progress": [],
    "error": None,
    "start_time": None,
    "pdf_path": None,
    "recommendation": None,
    "final_report": None,
    "token_usage": {},
}


def read_job(job_id: str) -> dict:
    """Read job state from the jobs table. Auto-expires stale running jobs."""
    try:
        sb = _get_client()
        resp = sb.table("jobs").select("*").eq("id", job_id).maybe_single().execute()
        if resp.data:
            data = resp.data
            # JSONB columns come back as dicts/lists already from supabase-py
            if isinstance(data.get("progress"), str):
                data["progress"] = json.loads(data["progress"])
            if isinstance(data.get("token_usage"), str):
                data["token_usage"] = json.loads(data["token_usage"])
            if isinstance(data.get("agent_outputs"), str):
                data["agent_outputs"] = json.loads(data["agent_outputs"])

            # Auto-expire stale jobs
            if data.get("status") in ("running", "queued"):
                start = data.get("start_time") or 0
                if start and time.time() - start > _STALE_JOB_TIMEOUT_SEC:
                    data["status"] = "error"
                    data["error"] = (
                        "Analysis timed out or the server was restarted mid-run. "
                        "Please submit again."
                    )
            return data
    except Exception as exc:
        logging.warning("read_job failed for job: %s", exc)
    return dict(_JOB_DEFAULTS)


_JOBS_KNOWN_COLUMNS = {
    "id", "status", "progress", "error", "start_time", "pdf_path",
    "recommendation", "final_report", "token_usage", "company",
    "pptx_path", "docx_path", "agent_outputs",
}


def update_job(job_id: str, updates: dict) -> None:
    """Upsert job state into the jobs table."""
    sb = _get_client()
    row = {"id": job_id}
    row.update(updates)

    # Ensure JSONB fields are serialized properly
    for key in ("progress", "token_usage", "agent_outputs"):
        if key in row and not isinstance(row[key], str):
            row[key] = json.dumps(row[key], ensure_ascii=False)

    try:
        sb.table("jobs").upsert(row, on_conflict="id").execute()
    except Exception as first_err:
        err_msg = str(first_err).lower()
        # Only strip columns if the error is column-related (schema mismatch)
        if "column" in err_msg or "schema" in err_msg or "could not find" in err_msg:
            optional_cols = ["agent_outputs", "docx_path", "pptx_path", "company"]
            for col in optional_cols:
                row.pop(col, None)
            try:
                sb.table("jobs").upsert(row, on_conflict="id").execute()
                return
            except Exception:
                pass
        # For any other error (network, etc.), re-raise so caller knows
        raise


def load_queue() -> list[dict]:
    """Load all running/queued jobs (global queue visible to all users)."""
    try:
        sb = _get_client()
        # Try with company column; fall back without it if column doesn't exist yet
        try:
            resp = (
                sb.table("jobs")
                .select("id, company, status, progress, start_time, token_usage")
                .in_("status", ["running", "queued"])
                .order("start_time", desc=False)
                .execute()
            )
        except Exception:
            resp = (
                sb.table("jobs")
                .select("id, status, progress, start_time, token_usage")
                .in_("status", ["running", "queued"])
                .order("start_time", desc=False)
                .execute()
            )
        rows = resp.data or []
        for row in rows:
            if isinstance(row.get("progress"), str):
                row["progress"] = json.loads(row["progress"])
            if isinstance(row.get("token_usage"), str):
                row["token_usage"] = json.loads(row["token_usage"])
        return rows
    except Exception:
        return []


def cleanup_stale_jobs() -> int:
    """Cancel all running/queued jobs (used on app startup after reboot)."""
    try:
        sb = _get_client()
        resp = (
            sb.table("jobs")
            .select("id")
            .in_("status", ["running", "queued"])
            .execute()
        )
        rows = resp.data or []
        for row in rows:
            sb.table("jobs").update({"status": "cancelled"}).eq("id", row["id"]).execute()
        return len(rows)
    except Exception:
        return 0


# ── History ──────────────────────────────────────────────────────────────────

def load_history() -> list[dict]:
    """Load all history entries, newest first."""
    try:
        sb = _get_client()
        resp = (
            sb.table("history")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return resp.data or []
    except Exception:
        return []


def save_history_entry(entry: dict) -> None:
    """Insert a new history entry."""
    sb = _get_client()
    sb.table("history").upsert(entry, on_conflict="id").execute()


# ── File storage ─────────────────────────────────────────────────────────────

_MIME_TYPES = {
    ".pdf":  "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def upload_file(job_id: str, local_path: str, folder: str = "pdfs") -> str:
    """Upload a file to Supabase Storage and return the storage path."""
    sb = _get_client()
    ext = os.path.splitext(local_path)[1].lower()
    storage_path = f"{folder}/{job_id}{ext}"
    content_type = _MIME_TYPES.get(ext, "application/octet-stream")

    with open(local_path, "rb") as f:
        file_bytes = f.read()

    sb.storage.from_("reports").upload(
        storage_path,
        file_bytes,
        file_options={"content-type": content_type, "upsert": "true"},
    )
    return storage_path


def upload_pdf(job_id: str, local_path: str) -> str:
    """Upload a PDF to Supabase Storage and return the storage path."""
    return upload_file(job_id, local_path, folder="pdfs")


def download_file(storage_path: str) -> bytes | None:
    """Download file bytes from Supabase Storage. Returns None on failure."""
    try:
        sb = _get_client()
        data = sb.storage.from_("reports").download(storage_path)
        return data
    except Exception:
        return None


def download_pdf(storage_path: str) -> bytes | None:
    """Download PDF bytes from Supabase Storage. Returns None on failure."""
    return download_file(storage_path)
