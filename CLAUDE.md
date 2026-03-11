# Due Diligence Agent

## Overview
Multi-agent investment due diligence tool. 14 AI agents analyze a company across 4 phases with a feedback loop, producing an investment memo + PDF + PPTX report.

- **Stack:** LangGraph + Anthropic SDK (claude-sonnet-4-6) + Tavily + edgartools + PyMuPDF + ReportLab + python-pptx
- **Deployed:** Streamlit Cloud at https://ddagents.streamlit.app/
- **Repo:** https://github.com/danhenney/ddagent

## Pipeline
1. **Phase 1 — Parallel (6 agents):** Market Analysis, Competitor Analysis, Financial Analysis, Tech Analysis, Legal & Regulatory, Team Analysis
2. **Phase 2 — Synthesis:** R&A Synthesis + Risk Assessment (parallel), then Strategic Insight (sequential, renders INVEST/WATCH/PASS)
3. **Phase 3 — Review & Critique:** Review Agent → Critique Agent (scores 5 criteria 1-10) → DD Questions
   - **Feedback Loop:** Critique agent triggers selective re-run or full Phase 1 restart if quality insufficient (max 2 loops)
   - Pass: total >= 35 AND all criteria >= 7
   - Conditional: selective re-run of weak agents
   - Fail: full Phase 1 restart
4. **Phase 4 — Report:** Report Structure (designs Why/What/How/Risk/Recommendations framework) → Report Writer (final memo)

## Key Files
- `app.py` — Streamlit UI (form, running progress, results, history screens)
- `main.py` — CLI entry point
- `graph/workflow.py` — LangGraph pipeline orchestration with feedback loop
- `graph/state.py` — State schema (DueDiligenceState)
- `agents/base.py` — Base agent with token tracking
- `agents/context.py` — Compact context builders (slim_* functions)
- `pdf_report.py` — ReportLab PDF generation (supports Korean fonts)
- `pptx_report.py` — python-pptx slide deck generation
- `supabase_storage.py` — Persistent storage (jobs, history, PDF uploads)
- `config.py` — API key validation
- `tools/executor.py` — Tool routing and caching
- `tools/` — Tavily, EDGAR, yfinance, PyTrends, FRED, GitHub, patents, PDF reader

## Storage (Supabase)
All persistent state uses Supabase (PostgreSQL + Storage):
- `jobs` table — in-progress and completed analysis state
- `history` table — list of past analyses
- `reports` storage bucket — PDF files at `pdfs/{job_id}.pdf`
- Credentials: `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` in env or Streamlit secrets

## Running Locally
```bash
python main.py --company "Apple" --url https://apple.com
# or Streamlit UI:
streamlit run app.py
```

## Workflow
- Always push changes to GitHub so Streamlit Cloud auto-deploys
- API keys in `.env` locally, Streamlit secrets in production
- Max 2 concurrent analyses (semaphore in app.py)
- Korean language support for both UI and PDF reports
- Recommendation: INVEST / WATCH / PASS (anti-bias: does NOT default to WATCH)
