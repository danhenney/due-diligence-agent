# Due Diligence Agent

## Overview
Multi-agent investment due diligence tool. 15 AI agents analyze a company across 4 phases and produce an investment memo + PDF report.

- **Stack:** LangGraph + Anthropic SDK (claude-sonnet-4-6) + Tavily + edgartools + PyMuPDF + ReportLab
- **Deployed:** Streamlit Cloud at https://ddagents.streamlit.app/
- **Repo:** https://github.com/danhenney/due-diligence-agent

## Pipeline
1. **Phase 1 — Parallel (5 agents):** Financial Analyst, Market Research, Legal Risk, Management Team, Tech & Product
2. **Phase 2 — Parallel (4 agents):** Bull Case, Bear Case, Valuation, Red Flag Hunter
3. **Phase 3 — Sequential (3 agents):** Fact Checker, Stress Test, Completeness
4. **Orchestrator quality gates** run after each phase — scores agents, revises weak ones (< 0.65)
5. **Phase 4:** Final Report Agent writes the investment memo

## Key Files
- `app.py` — Streamlit UI (form, running progress, results, history screens)
- `main.py` — CLI entry point
- `graph/workflow.py` — LangGraph pipeline orchestration
- `graph/state.py` — State schema
- `agents/base.py` — Base agent with token tracking
- `agents/context.py` — Agent definitions and prompts
- `pdf_report.py` — ReportLab PDF generation (supports Korean fonts)
- `supabase_storage.py` — Persistent storage (jobs, history, PDF uploads)
- `config.py` — API key validation
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
