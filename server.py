"""FastAPI server for the Due Diligence Agent web UI."""
from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
import uuid
import webbrowser
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

import pdf_report
from config import validate_config, register_custom_mode, unregister_custom_mode
from graph.workflow import build_graph

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="Due Diligence Agent")

WEB_DIR = Path(__file__).parent / "web"
UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)

# In-memory job store: job_id → {status, queue, recommendation, pdf_path, error}
_jobs: dict[str, dict[str, Any]] = {}

# ── Serve frontend ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index = WEB_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return HTMLResponse(content=index.read_text(encoding="utf-8"))


# ── Job lifecycle ─────────────────────────────────────────────────────────────

def _run_analysis(job_id: str, company: str, url: str, doc_paths: list[str],
                   mode: str = "due-diligence", vs_company: str | None = None):
    """Background thread: runs the graph and posts SSE events to the queue."""
    job = _jobs[job_id]
    q: queue.Queue = job["queue"]
    # Track custom mode key for cleanup
    custom_mode_key: str | None = job.get("custom_mode_key")

    try:
        graph = build_graph(mode=mode, use_checkpointing=False)
        initial_state = {
            "company_name": company,
            "company_url": url or None,
            "uploaded_docs": doc_paths,
            "is_public": None,
            "ticker": None,
            "mode": mode,
            "vs_company": vs_company,
            # Phase 1
            "market_analysis": None,
            "competitor_analysis": None,
            "financial_analysis": None,
            "tech_analysis": None,
            "legal_regulatory": None,
            "team_analysis": None,
            # Phase 2
            "ra_synthesis": None,
            "risk_assessment": None,
            "strategic_insight": None,
            "industry_synthesis": None,
            "benchmark_synthesis": None,
            # Phase 3
            "review_result": None,
            "critique_result": None,
            "dd_questions": None,
            # Phase 4
            "report_structure": None,
            "final_report": None,
            "recommendation": None,
            # Cross-pollination
            "settled_claims": None,
            "phase1_tensions": None,
            "phase1_gaps": None,
            # Feedback loop
            "phase1_context": None,
            "feedback_loop_count": 0,
            "weak_sections": [],
            # Bookkeeping
            "messages": [],
            "errors": [],
            "current_phase": "init",
            "language": "English",
        }

        merged: dict[str, Any] = {}

        for step in graph.stream(initial_state, stream_mode="updates"):
            for node_name, node_output in step.items():
                merged.update(node_output)
                q.put({
                    "type": "node_complete",
                    "node": node_name,
                    "current_phase": merged.get("current_phase", ""),
                })

        # Generate PDF
        recommendation = merged.get("recommendation") or "WATCH"
        pdf_path = pdf_report.generate_pdf(merged, job_id)

        job["status"] = "complete"
        job["recommendation"] = recommendation
        job["pdf_path"] = pdf_path

        q.put({"type": "complete", "recommendation": recommendation})

    except Exception as exc:
        job["status"] = "error"
        job["error"] = str(exc)
        q.put({"type": "error", "message": str(exc)})

    finally:
        # Sentinel to close SSE stream
        q.put(None)
        # Clean up custom mode registration
        if custom_mode_key:
            unregister_custom_mode(custom_mode_key)
        # Clean up uploaded files
        for p in doc_paths:
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass


# ── API endpoints ─────────────────────────────────────────────────────────────

@app.post("/api/analyze")
async def analyze(
    company: str = Form(...),
    url: str = Form(""),
    mode: str = Form("due-diligence"),
    vs_company: str = Form(""),
    agents: str = Form(""),
    feedback_loop: bool = Form(False),
    recommendation: bool = Form(False),
    files: list[UploadFile] = File(default=[]),
):
    """Accept form submission, save uploads, spawn background thread."""
    # Save uploaded PDFs
    job_id = str(uuid.uuid4())
    job_upload_dir = UPLOADS_DIR / job_id
    job_upload_dir.mkdir(parents=True, exist_ok=True)

    doc_paths: list[str] = []
    for f in files:
        if f.filename:
            dest = job_upload_dir / f.filename
            content = await f.read()
            dest.write_bytes(content)
            doc_paths.append(str(dest))

    # ── Custom mode registration ──────────────────────────────────────────
    custom_mode_key: str | None = None
    if agents:
        from config import VALID_PHASE1_AGENTS, VALID_PHASE2_AGENTS, VALID_PHASE3_AGENTS
        agent_list = [a.strip() for a in agents.split(",") if a.strip()]
        p1 = [a for a in agent_list if a in VALID_PHASE1_AGENTS]
        p2 = [a for a in agent_list if a in VALID_PHASE2_AGENTS and a != "strategic_insight"]
        p2_seq = [a for a in agent_list if a == "strategic_insight"]
        p3 = [a for a in agent_list if a in VALID_PHASE3_AGENTS]
        if not p3:
            p3 = ["critique_agent"]

        custom_mode_key = f"custom-{job_id}"
        try:
            register_custom_mode(
                phase1=p1, phase2_parallel=p2, phase2_sequential=p2_seq,
                phase3=p3, feedback_loop=feedback_loop,
                recommendation=recommendation, mode_key=custom_mode_key,
            )
            mode = custom_mode_key
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    # Validate mode
    from config import VALID_MODES, MODE_REGISTRY
    if mode not in VALID_MODES and mode not in MODE_REGISTRY:
        mode = "due-diligence"

    # Register job
    _jobs[job_id] = {
        "status": "running",
        "queue": queue.Queue(),
        "recommendation": None,
        "pdf_path": None,
        "error": None,
        "custom_mode_key": custom_mode_key,
    }

    # Spawn background thread
    t = threading.Thread(
        target=_run_analysis,
        args=(job_id, company, url, doc_paths, mode, vs_company or None),
        daemon=True,
    )
    t.start()

    return JSONResponse({"job_id": job_id})


@app.get("/api/stream/{job_id}")
async def stream_events(job_id: str, request: Request):
    """SSE endpoint that relays events from the job queue."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    q: queue.Queue = job["queue"]

    async def event_generator():
        loop = asyncio.get_event_loop()
        while True:
            if await request.is_disconnected():
                break
            try:
                # Non-blocking get with 0.1 s timeout via executor
                event = await loop.run_in_executor(None, _queue_get_timeout, q, 0.1)
            except _QueueTimeout:
                # Send a keepalive comment so the connection stays open
                yield ": keepalive\n\n"
                continue

            if event is None:
                # Sentinel — stream finished
                yield "data: null\n\n"
                break

            yield f"data: {json.dumps(event)}\n\n"

            if event.get("type") in ("complete", "error"):
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


class _QueueTimeout(Exception):
    pass


def _queue_get_timeout(q: queue.Queue, timeout: float) -> Any:
    """Blocking get with timeout; raises _QueueTimeout on timeout."""
    try:
        return q.get(timeout=timeout)
    except queue.Empty:
        raise _QueueTimeout()


@app.get("/api/status/{job_id}")
async def job_status(job_id: str):
    """Polling fallback for clients that don't support SSE."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _jobs[job_id]
    return JSONResponse({
        "status": job["status"],
        "recommendation": job["recommendation"],
        "has_report": job["pdf_path"] is not None,
        "error": job["error"],
    })


@app.get("/api/report/{job_id}")
async def download_report(job_id: str):
    """Return the generated PDF as a file download."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _jobs[job_id]
    if not job["pdf_path"]:
        raise HTTPException(status_code=404, detail="Report not ready yet")
    pdf_path = Path(job["pdf_path"])
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"due_diligence_{job_id[:8]}.pdf",
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Validate environment before starting
    missing = validate_config()
    if missing:
        print(f"[ERROR] Missing environment variables: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in the required keys.")
        raise SystemExit(1)

    # Open browser after a short delay
    def _open_browser():
        time.sleep(1.5)
        webbrowser.open("http://localhost:8000")

    threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
