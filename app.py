"""Streamlit web UI for the Due Diligence Agent."""
import json
import os
import shutil
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

REPORTS_DIR = Path("reports")
_JOBS_DIR = REPORTS_DIR / "jobs"

# Max concurrent analyses. Additional submissions wait in queue.
_ANALYSIS_SEMAPHORE = threading.Semaphore(2)

# Jobs stuck in "running" longer than this are marked as timed-out.
_STALE_JOB_TIMEOUT_SEC = 5400  # 90 minutes


# ── File-based job state (survives multi-process + navigation) ─────────────────

def _job_file(job_id: str) -> Path:
    _JOBS_DIR.mkdir(parents=True, exist_ok=True)
    return _JOBS_DIR / f"{job_id}.json"


def _read_job(job_id: str) -> dict:
    f = _job_file(job_id)
    try:
        if f.exists():
            data = json.loads(f.read_text(encoding="utf-8"))
            # Auto-expire stale "running" jobs (e.g. after a server restart mid-run)
            if data.get("status") in ("running", "queued"):
                start = data.get("start_time") or 0
                if start and time.time() - start > _STALE_JOB_TIMEOUT_SEC:
                    data["status"] = "error"
                    data["error"] = (
                        "Analysis timed out or the server was restarted mid-run. "
                        "Please submit again."
                    )
            return data
    except Exception:
        pass
    return {"status": "unknown", "progress": [], "error": None, "start_time": None}


def _update_job(job_id: str, updates: dict) -> None:
    """Merge updates into the job file using an atomic tmp→rename write."""
    f = _job_file(job_id)
    data = _read_job(job_id)
    data.update(updates)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)


# ── History ────────────────────────────────────────────────────────────────────

def _load_history() -> list[dict]:
    hist_file = REPORTS_DIR / "history.json"
    if hist_file.exists():
        try:
            return json.loads(hist_file.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_history_entry(entry: dict) -> None:
    hist_file = REPORTS_DIR / "history.json"
    history = _load_history()
    history.insert(0, entry)
    REPORTS_DIR.mkdir(exist_ok=True)
    hist_file.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Token cost tracking ────────────────────────────────────────────────────────

# claude-sonnet-4-6 pricing (USD per 1M tokens)
_PRICE_INPUT_PER_M  = 3.00
_PRICE_OUTPUT_PER_M = 15.00

# Human-readable labels for each agent key
_AGENT_LABELS_EN = {
    "financial_analyst": "Financial Analyst",
    "market_research":   "Market Research",
    "legal_risk":        "Legal Risk",
    "management_team":   "Management Team",
    "tech_product":      "Tech & Product",
    "bull_case":         "Bull Case",
    "bear_case":         "Bear Case",
    "valuation":         "Valuation",
    "red_flag":          "Red Flag Hunter",
    "fact_checker":      "Fact Checker",
    "stress_test":       "Stress Test",
    "completeness":      "Completeness",
    "final_report_agent":"Final Report",
}

_AGENT_LABELS_KO = {
    "financial_analyst": "재무 분석가",
    "market_research":   "시장 리서처",
    "legal_risk":        "법적 리스크 분석가",
    "management_team":   "경영진 분석가",
    "tech_product":      "기술·제품 분석가",
    "bull_case":         "강세 논거 분석가",
    "bear_case":         "약세 논거 분석가",
    "valuation":         "밸류에이션 분석가",
    "red_flag":          "위험 신호 탐지기",
    "fact_checker":      "팩트체커",
    "stress_test":       "스트레스 테스트 분석가",
    "completeness":      "완성도 검사기",
    "final_report_agent":"최종 보고서 에이전트",
}

# Display order
_AGENT_ORDER = list(_AGENT_LABELS_EN.keys())


def _cost_usd(inp: int, out: int) -> float:
    return inp / 1_000_000 * _PRICE_INPUT_PER_M + out / 1_000_000 * _PRICE_OUTPUT_PER_M


# ── Background worker ──────────────────────────────────────────────────────────

def _analysis_worker(job_id: str, initial_state: dict, company: str, tmp_dir: str) -> None:
    """Daemon thread — waits for a semaphore slot, then runs the full pipeline."""
    # Wait for a free slot (max 2 concurrent analyses)
    _update_job(job_id, {"status": "queued"})
    _ANALYSIS_SEMAPHORE.acquire()
    try:
        _update_job(job_id, {"status": "running", "start_time": time.time()})
        _run_pipeline(job_id, initial_state, company, tmp_dir)
    finally:
        _ANALYSIS_SEMAPHORE.release()


def _run_pipeline(job_id: str, initial_state: dict, company: str, tmp_dir: str) -> None:
    """Inner worker — runs all pipeline nodes and writes results to disk."""
    try:
        import pdf_report
        from agents.base import get_and_reset_usage
        from graph.workflow import (
            input_processor, phase1_parallel, phase1_aggregator,
            phase2_parallel, phase2_aggregator,
            fact_checker_node, stress_test_node,
            completeness_node, final_report_node,
        )

        state: dict = dict(initial_state)
        progress: list[str] = []
        token_usage: dict = {}   # agent_key -> {input_tokens, output_tokens, cost_usd}

        # Nodes that don't call the LLM (no cost to track)
        _NO_LLM_NODES = {"input_processor", "phase1_aggregator", "phase2_aggregator"}

        def _step(fn, node_name: str) -> None:
            result = fn(state)
            state.update(result)
            progress.append(node_name)

            if node_name in ("phase1_parallel", "phase2_parallel"):
                # Per-sub-agent usage is captured inside workflow.py and
                # returned in state["__agent_usage__"]
                for agent_key, usage in (state.pop("__agent_usage__", {}) or {}).items():
                    token_usage[agent_key] = {
                        "input_tokens":  usage["input_tokens"],
                        "output_tokens": usage["output_tokens"],
                        "cost_usd":      _cost_usd(usage["input_tokens"], usage["output_tokens"]),
                    }
            elif node_name not in _NO_LLM_NODES:
                # Sequential agent — usage is on this thread
                usage = get_and_reset_usage()
                # node_name for phase3/4 agents matches the agent key
                agent_key = node_name
                token_usage[agent_key] = {
                    "input_tokens":  usage["input_tokens"],
                    "output_tokens": usage["output_tokens"],
                    "cost_usd":      _cost_usd(usage["input_tokens"], usage["output_tokens"]),
                }

            _update_job(job_id, {
                "progress":    progress.copy(),
                "token_usage": token_usage.copy(),
            })

        _step(input_processor,   "input_processor")
        _step(phase1_parallel,   "phase1_parallel")
        _step(phase1_aggregator, "phase1_aggregator")
        _step(phase2_parallel,   "phase2_parallel")
        _step(phase2_aggregator, "phase2_aggregator")
        _step(fact_checker_node, "fact_checker")
        _step(stress_test_node,  "stress_test")
        _step(completeness_node, "completeness")
        _step(final_report_node, "final_report_agent")

        pdf_path = pdf_report.generate_pdf(state, job_id)

        _save_history_entry({
            "id": job_id,
            "company": company,
            "recommendation": (state.get("recommendation") or "WATCH").upper(),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "pdf_path": str(pdf_path),
        })

        _update_job(job_id, {
            "status":         "complete",
            "pdf_path":       str(pdf_path),
            "recommendation": (state.get("recommendation") or "WATCH").upper(),
            "final_report":   state.get("final_report") or "",
            "token_usage":    token_usage,
        })

    except Exception as exc:
        _update_job(job_id, {"status": "error", "error": str(exc)})

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

import streamlit as st

# Inject Streamlit Cloud secrets into os.environ so config.py's os.getenv() works.
# This is a no-op when running locally with a .env file.
try:
    for _k in ["ANTHROPIC_API_KEY", "TAVILY_API_KEY", "EDGAR_USER_AGENT"]:
        if _k in st.secrets and not os.environ.get(_k):
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass

from config import validate_config

# ── UI Translations ────────────────────────────────────────────────────────────

_UI = {
    "en": {
        "app_title":            "## 📊 Due Diligence Agent",
        "app_subtitle":         "Submit a company → 13 AI agents analyze it in 4 phases → full investment memo + PDF",
        "history_btn":          "🕐 History",
        "form_heading":         "#### Submit a Company",
        "company_label":        "Company Name",
        "company_placeholder":  "e.g. Apple, OpenAI, Stripe",
        "url_label":            "Website URL *(required — improves research quality)*",
        "url_placeholder":      "https://example.com",
        "report_lang_label":    "Report Language",
        "docs_label":           "Supporting Documents *(optional)*",
        "docs_help":            "Pitch decks, 10-Ks, annual reports, etc.",
        "cost_caption":         "Typical cost: **$1 – $5 per analysis** · 13 agents · claude-sonnet-4-6 · $3/M input · $15/M output",
        "run_btn":              "🔍  Run Due Diligence",
        "pipeline_heading":     "#### Agent Pipeline Flow",
        "pipeline_caption":     "Phases 1 & 2 run agents in parallel. Phase 3 is sequential (order matters).",
        "directory_heading":    "#### Agent Directory",
        "directory_caption":    "Click any agent to see its methodology and data sources.",
        "how_it_works":         "**How it works:**",
        "sources_label":        "**Sources:**",
        "methodology_expander": "Methodology & Sources",
        "analyzing":            "## 📊 Analyzing {}…",
        "running_caption":      "Running in the background — you can navigate away and come back at any time.",
        "api_cost":             "**API cost so far: ${cost:.4f}**  ·  {inp:,} input tokens  ·  {out:,} output tokens  ·  Pricing: $3/M input · $15/M output (claude-sonnet-4-6)",
        "queued_heading":       "## 📊 {} — Queued",
        "queued_caption":       "Two analyses are already running. Yours will start automatically when a slot opens.",
        "queued_info":          "**Your analysis is in the queue.**\n\nThe server allows 2 simultaneous analyses to avoid API rate limits. You're next in line — this page will update automatically when it starts.",
        "waiting_caption":      "Waiting… {}s in queue",
        "analysis_failed":      "**Analysis failed:** {}",
        "try_again_btn":        "← Try Again",
        "invest_desc":          "Strong investment opportunity with compelling fundamentals.",
        "watch_desc":           "Interesting opportunity — monitor for further developments.",
        "pass_desc":            "Risks outweigh opportunities at this time.",
        "download_btn":         "⬇️  Download PDF Report",
        "analyze_another_btn":  "🔄  Analyze Another Company",
        "token_expander":       "Token Usage & Cost  —  **${:.4f} total**",
        "token_caption":        "Pricing: claude-sonnet-4-6 · $3.00 / 1M input tokens · $15.00 / 1M output tokens",
        "no_report":            "No report content was generated.",
        "agent_col":            "Agent",
        "input_tokens_col":     "Input tokens",
        "output_tokens_col":    "Output tokens",
        "cost_col":             "Cost (USD)",
        "total_label":          "**TOTAL**",
        "history_title":        "## 🕐 Analysis History",
        "history_caption":      "All due diligence reports generated on this machine.",
        "back_btn":             "← Back",
        "back_running_btn":     "← Back to Running Analysis",
        "no_history":           "No analyses yet. Submit a company on the main page to get started.",
        "pdf_btn":              "⬇️ PDF",
        "pdf_unavail":          "PDF unavailable",
        "password_label":       "Password",
        "password_placeholder": "Enter password to continue",
        "unlock_btn":           "Unlock",
        "wrong_password":       "Incorrect password.",
        "lang_toggle":          "한국어",
        "step_done":            "✓",
        "step_running":         "⏳",
        "progress_text":        "**{pct}%** — step {done} of {total}  ·  elapsed {elapsed}  ·  {eta}",
        "eta_estimating":       "Estimating…",
        "eta_remaining":        "~{} remaining",
    },
    "ko": {
        "app_title":            "## 📊 실사 에이전트",
        "app_subtitle":         "기업을 입력하면 → AI 에이전트 13개가 4단계로 분석 → 투자 메모 + PDF 완성",
        "history_btn":          "🕐 분석 기록",
        "form_heading":         "#### 기업 분석 요청",
        "company_label":        "기업명",
        "company_placeholder":  "예: Apple, OpenAI, 카카오",
        "url_label":            "공식 웹사이트 *(필수 — 분석 품질 향상)*",
        "url_placeholder":      "https://example.com",
        "report_lang_label":    "보고서 언어",
        "docs_label":           "참고 문서 *(선택)*",
        "docs_help":            "사업계획서, 10-K, 연간보고서 등 PDF",
        "cost_caption":         "예상 비용: **분석당 $1 – $5** · 에이전트 13개 · claude-sonnet-4-6 · 입력 $3/M · 출력 $15/M",
        "run_btn":              "🔍  실사 분석 시작",
        "pipeline_heading":     "#### 에이전트 파이프라인",
        "pipeline_caption":     "1·2단계는 에이전트를 병렬 실행합니다. 3단계는 순차 실행입니다.",
        "directory_heading":    "#### 에이전트 목록",
        "directory_caption":    "에이전트를 클릭하면 분석 방법론과 데이터 소스를 확인할 수 있습니다.",
        "how_it_works":         "**분석 방법:**",
        "sources_label":        "**데이터 소스:**",
        "methodology_expander": "방법론 & 소스",
        "analyzing":            "## 📊 {} 분석 중…",
        "running_caption":      "백그라운드에서 실행 중 — 페이지를 벗어났다가 언제든 돌아올 수 있습니다.",
        "api_cost":             "**현재 API 비용: ${cost:.4f}**  ·  입력 토큰 {inp:,}개  ·  출력 토큰 {out:,}개  ·  가격: 입력 $3/M · 출력 $15/M",
        "queued_heading":       "## 📊 {} — 대기 중",
        "queued_caption":       "현재 2개의 분석이 실행 중입니다. 슬롯이 열리면 자동으로 시작됩니다.",
        "queued_info":          "**분석이 대기열에 있습니다.**\n\nAPI 속도 제한을 방지하기 위해 서버는 최대 2개의 동시 분석을 허용합니다. 다음 순서입니다 — 시작되면 이 페이지가 자동으로 업데이트됩니다.",
        "waiting_caption":      "대기 중… {}초 경과",
        "analysis_failed":      "**분석 실패:** {}",
        "try_again_btn":        "← 다시 시도",
        "invest_desc":          "강력한 투자 기회 — 탄탄한 펀더멘털을 보유하고 있습니다.",
        "watch_desc":           "흥미로운 기회 — 추가 동향을 모니터링하세요.",
        "pass_desc":            "현재 시점에서 리스크가 기회를 초과합니다.",
        "download_btn":         "⬇️  PDF 보고서 다운로드",
        "analyze_another_btn":  "🔄  다른 기업 분석",
        "token_expander":       "토큰 사용량 & 비용  —  **총 ${:.4f}**",
        "token_caption":        "가격: claude-sonnet-4-6 · 입력 $3.00 / 1M 토큰 · 출력 $15.00 / 1M 토큰",
        "no_report":            "생성된 보고서 내용이 없습니다.",
        "agent_col":            "에이전트",
        "input_tokens_col":     "입력 토큰",
        "output_tokens_col":    "출력 토큰",
        "cost_col":             "비용 (USD)",
        "total_label":          "**합계**",
        "history_title":        "## 🕐 분석 기록",
        "history_caption":      "이 서버에서 생성된 모든 실사 보고서",
        "back_btn":             "← 뒤로",
        "back_running_btn":     "← 진행 중인 분석으로 돌아가기",
        "no_history":           "아직 분석 내역이 없습니다. 메인 페이지에서 기업을 입력하여 시작하세요.",
        "pdf_btn":              "⬇️ PDF",
        "pdf_unavail":          "PDF 없음",
        "password_label":       "비밀번호",
        "password_placeholder": "비밀번호를 입력하세요",
        "unlock_btn":           "잠금 해제",
        "wrong_password":       "비밀번호가 올바르지 않습니다.",
        "lang_toggle":          "English",
        "step_done":            "✓",
        "step_running":         "⏳",
        "progress_text":        "**{pct}%** — {done}/{total}단계  ·  경과 {elapsed}  ·  {eta}",
        "eta_estimating":       "예상 중…",
        "eta_remaining":        "~{} 남음",
    },
}


def t(key: str, *args, **kwargs) -> str:
    """Return translated UI string for the current ui_lang session."""
    lang = st.session_state.get("ui_lang", "en")
    s = _UI.get(lang, _UI["en"]).get(key) or _UI["en"].get(key, key)
    if args:
        return s.format(*args)
    if kwargs:
        return s.format(**kwargs)
    return s


# ── Node labels (language-aware at render time) ────────────────────────────────

_NODE_LABELS_EN = {
    "input_processor":    "🔍 Processing inputs",
    "phase1_parallel":    "📊 Phase 1 — 5 research agents ran in parallel",
    "phase1_aggregator":  "✅ Phase 1 aggregated",
    "phase2_parallel":    "📈 Phase 2 — 4 analysis agents ran in parallel",
    "phase2_aggregator":  "✅ Phase 2 aggregated",
    "fact_checker":       "🔎 Fact-checking all claims",
    "stress_test":        "⚡ Stress-testing downside scenarios",
    "completeness":       "📋 Coverage & completeness review",
    "final_report_agent": "📝 Writing investment memo",
}

_NODE_LABELS_KO = {
    "input_processor":    "🔍 입력 처리 중",
    "phase1_parallel":    "📊 1단계 — 리서치 에이전트 5개 병렬 실행",
    "phase1_aggregator":  "✅ 1단계 집계 완료",
    "phase2_parallel":    "📈 2단계 — 분석 에이전트 4개 병렬 실행",
    "phase2_aggregator":  "✅ 2단계 집계 완료",
    "fact_checker":       "🔎 모든 주장 팩트체크",
    "stress_test":        "⚡ 하방 시나리오 스트레스 테스트",
    "completeness":       "📋 커버리지 & 완성도 검토",
    "final_report_agent": "📝 투자 메모 작성 중",
}

# Weighted % of total runtime each node typically consumes (must sum to 100)
NODE_WEIGHTS = {
    "input_processor":    2,
    "phase1_parallel":    35,
    "phase1_aggregator":  1,
    "phase2_parallel":    28,
    "phase2_aggregator":  1,
    "fact_checker":       12,
    "stress_test":        9,
    "completeness":       6,
    "final_report_agent": 6,
}

# ── Pipeline graphviz diagram ─────────────────────────────────────────────────
PIPELINE_GRAPH = """
digraph pipeline {
    rankdir=LR;
    node [fontname="Helvetica" fontsize=9 style="rounded,filled" shape=box margin=0.15];
    edge [arrowsize=0.6 color="#94a3b8"];

    START [label="START" shape=circle fillcolor="#6366f1" fontcolor=white
           style=filled width=0.45 height=0.45 fontsize=8];
    END   [label="END"   shape=circle fillcolor="#059669" fontcolor=white
           style=filled width=0.45 height=0.45 fontsize=8];

    inp [label="Input\nProcessor" fillcolor="#e0e7ff" color="#6366f1" fontcolor="#3730a3"];

    subgraph cluster_p1 {
        label="Phase 1  ⟵  Parallel" fontsize=9 color="#2563eb"
        fillcolor="#eff6ff" style="rounded,filled";
        fin  [label="Financial\nAnalyst"  fillcolor="#bfdbfe" color="#1d4ed8" fontcolor="#1e3a8a"];
        mkt  [label="Market\nResearch"   fillcolor="#bfdbfe" color="#1d4ed8" fontcolor="#1e3a8a"];
        leg  [label="Legal Risk"         fillcolor="#bfdbfe" color="#1d4ed8" fontcolor="#1e3a8a"];
        mgmt [label="Management\nTeam"   fillcolor="#bfdbfe" color="#1d4ed8" fontcolor="#1e3a8a"];
        tech [label="Tech &\nProduct"    fillcolor="#bfdbfe" color="#1d4ed8" fontcolor="#1e3a8a"];
    }

    agg1 [label="⬇" shape=diamond fillcolor="#dbeafe" color="#2563eb"
          width=0.3 height=0.3 fontsize=11];

    subgraph cluster_p2 {
        label="Phase 2  ⟵  Parallel" fontsize=9 color="#7c3aed"
        fillcolor="#f5f3ff" style="rounded,filled";
        bull [label="Bull Case"  fillcolor="#ddd6fe" color="#7c3aed" fontcolor="#4c1d95"];
        bear [label="Bear Case"  fillcolor="#ddd6fe" color="#7c3aed" fontcolor="#4c1d95"];
        val  [label="Valuation"  fillcolor="#ddd6fe" color="#7c3aed" fontcolor="#4c1d95"];
        red  [label="Red Flags"  fillcolor="#ddd6fe" color="#7c3aed" fontcolor="#4c1d95"];
    }

    agg2 [label="⬇" shape=diamond fillcolor="#ede9fe" color="#7c3aed"
          width=0.3 height=0.3 fontsize=11];

    subgraph cluster_p3 {
        label="Phase 3  ⟵  Sequential" fontsize=9 color="#d97706"
        fillcolor="#fffbeb" style="rounded,filled";
        fact   [label="Fact\nChecker"  fillcolor="#fde68a" color="#b45309" fontcolor="#78350f"];
        stress [label="Stress\nTest"   fillcolor="#fde68a" color="#b45309" fontcolor="#78350f"];
        comp   [label="Complete-\nness" fillcolor="#fde68a" color="#b45309" fontcolor="#78350f"];
    }

    final [label="Final\nReport" fillcolor="#d1fae5" color="#059669" fontcolor="#064e3b"];

    START -> inp;
    inp -> fin; inp -> mkt; inp -> leg; inp -> mgmt; inp -> tech;
    fin -> agg1; mkt -> agg1; leg -> agg1; mgmt -> agg1; tech -> agg1;
    agg1 -> bull; agg1 -> bear; agg1 -> val; agg1 -> red;
    bull -> agg2; bear -> agg2; val -> agg2; red -> agg2;
    agg2 -> fact;
    fact -> stress [label="  then  " fontsize=7 color="#d97706"];
    stress -> comp [label="  then  " fontsize=7 color="#d97706"];
    comp -> final;
    final -> END;
}
"""

# ── Agent directory data (English) ────────────────────────────────────────────
AGENT_PHASES = [
    {
        "label": "Phase 1 — Parallel Research",
        "color": "#1d4ed8",
        "bg": "#eff6ff",
        "description": "5 specialist agents run **simultaneously**. Each independently researches a different dimension of the company. None waits for the others.",
        "agents": [
            {
                "icon": "💰",
                "name": "Financial Analyst",
                "role": "Assesses financial health, profitability, and accounting quality.",
                "methodology": [
                    "Pulls SEC 10-K / 10-Q filings from EDGAR",
                    "Calculates key ratios: gross margin, EBITDA margin, D/E ratio, current ratio",
                    "Trends revenue, operating income, free cash flow year-over-year",
                    "Checks for revenue concentration risk and accounting red flags",
                    "Compares metrics against industry benchmarks",
                ],
                "sources": ["SEC EDGAR (10-K, 10-Q, 8-K)", "Yahoo Finance (yfinance)", "Web search", "Uploaded PDFs"],
            },
            {
                "icon": "🌍",
                "name": "Market Research",
                "role": "Estimates TAM/SAM, maps the competitive landscape, and identifies macro trends.",
                "methodology": [
                    "Estimates Total Addressable Market (TAM) and Serviceable Market (SAM)",
                    "Maps direct competitors, indirect substitutes, and market share",
                    "Identifies macro tailwinds/headwinds (regulation, demographics, tech shifts)",
                    "Evaluates company positioning and differentiation vs. rivals",
                    "Assesses barriers to entry and market defensibility",
                ],
                "sources": ["Web search", "News search", "Google Trends (pytrends)", "FRED macroeconomic data", "Industry reports"],
            },
            {
                "icon": "⚖️",
                "name": "Legal Risk Analyst",
                "role": "Surfaces litigation, regulatory exposure, IP risks, and governance issues.",
                "methodology": [
                    "Searches for active lawsuits, class actions, and settlements",
                    "Reviews regulatory compliance status and recent enforcement actions",
                    "Assesses IP portfolio strength and patent disputes",
                    "Evaluates data privacy posture (GDPR, CCPA) and ESG exposure",
                    "Flags corporate governance red flags and insider conflicts",
                ],
                "sources": ["Web search", "News search", "USPTO PatentsView (patent database)", "Uploaded PDFs (legal docs)"],
            },
            {
                "icon": "👥",
                "name": "Management Team Analyst",
                "role": "Evaluates founders, executives, board, and organizational maturity.",
                "methodology": [
                    "Reviews founder/CEO background, domain expertise, and track record",
                    "Assesses executive team completeness and prior startup experience",
                    "Evaluates board composition (independence, relevant expertise)",
                    "Identifies key-person dependency and succession risks",
                    "Surfaces culture signals and employee sentiment (Glassdoor, press)",
                ],
                "sources": ["Web search", "News search", "LinkedIn (via web)"],
            },
            {
                "icon": "🔬",
                "name": "Tech & Product Analyst",
                "role": "Evaluates product maturity, technical moat, scalability, and PMF.",
                "methodology": [
                    "Assesses product stage (MVP / growth / mature) and feature depth",
                    "Evaluates technical differentiation and defensibility (IP, data moats)",
                    "Reviews scalability architecture and infrastructure choices",
                    "Measures product-market fit signals (NPS, churn, retention)",
                    "Benchmarks engineering team size and development velocity",
                ],
                "sources": ["Web search", "News search", "GitHub API (repos, commit activity, contributors)", "Google Trends (pytrends)", "USPTO PatentsView"],
            },
        ],
    },
    {
        "label": "Phase 2 — Parallel Analysis",
        "color": "#7c3aed",
        "bg": "#f5f3ff",
        "description": "4 thesis agents run **simultaneously**, each reading all Phase 1 reports. They argue different angles to stress-test the opportunity from every direction.",
        "agents": [
            {
                "icon": "📈",
                "name": "Bull Case Analyst",
                "role": "Builds the strongest possible investment thesis and quantifies upside.",
                "methodology": [
                    "Synthesizes Phase 1 findings to construct the best-case scenario",
                    "Identifies top catalysts (product launches, market expansion, M&A)",
                    "Assigns probability weights and timelines to each catalyst",
                    "Projects revenue trajectory and valuation upside in bull scenario",
                    "Articulates competitive advantages and why the company can win",
                ],
                "sources": ["Phase 1 reports (financial, market, legal, management, tech)"],
            },
            {
                "icon": "📉",
                "name": "Bear Case Analyst",
                "role": "Constructs the strongest argument against investing and identifies fatal flaws.",
                "methodology": [
                    "Stress-tests Phase 1 findings for weaknesses and inconsistencies",
                    "Assigns realistic likelihood and severity scores to each risk",
                    "Models worst-case scenario with quantified revenue/valuation impact",
                    "Identifies structural weaknesses that competitors could exploit",
                    "Flags management and financial concerns that may be deal-breakers",
                ],
                "sources": ["Phase 1 reports (financial, market, legal, management, tech)"],
            },
            {
                "icon": "🧮",
                "name": "Valuation Analyst",
                "role": "Estimates fair value using DCF, revenue multiples, and precedent transactions.",
                "methodology": [
                    "Runs revenue/EBITDA multiple analysis vs. comparable public companies",
                    "Builds DCF model with bull/base/bear assumptions",
                    "Reviews precedent M&A transactions in the sector",
                    "Produces a fair value range (low / mid / high) with confidence intervals",
                    "Calculates implied upside/downside to current valuation",
                ],
                "sources": ["Yahoo Finance (yfinance — live multiples, analyst targets)", "Web search", "Phase 1 financial & market reports"],
            },
            {
                "icon": "🚩",
                "name": "Red Flag Hunter",
                "role": "Cross-examines all Phase 1 reports for contradictions, omissions, and fraud signals.",
                "methodology": [
                    "Compares claims across all 5 Phase 1 reports for inconsistencies",
                    "Detects classic fraud signals: revenue ≠ cash flow, customer concentration",
                    "Identifies suspicious omissions and missing critical information",
                    "Flags related-party transactions and unusual accounting treatments",
                    "Rates each flag by severity (high / medium / low) with evidence",
                ],
                "sources": ["Phase 1 reports (cross-referenced against each other)"],
            },
        ],
    },
    {
        "label": "Phase 3 — Sequential Verification",
        "color": "#b45309",
        "bg": "#fffbeb",
        "description": "3 QA agents run **one after another** — each depends on the previous one's output. Order matters: verify facts first, then stress-test, then check for gaps.",
        "agents": [
            {
                "icon": "🔎",
                "name": "Fact Checker",
                "role": "Independently verifies every material claim made in Phases 1 & 2.",
                "methodology": [
                    "Extracts all material factual claims from Phase 1 & 2 reports",
                    "Independently searches for primary sources to confirm or refute each claim",
                    "Classifies each as: VERIFIED / UNVERIFIED / CONTRADICTED / MISSING",
                    "Assigns a confidence score and cites the verification source",
                    "Outputs overall factual integrity score for the entire DD package",
                ],
                "sources": ["Web search", "News search", "Phase 1 & 2 reports"],
            },
            {
                "icon": "⚡",
                "name": "Stress Test Analyst",
                "role": "Models three downside scenarios with quantified financial impact.",
                "methodology": [
                    "**Base Stress**: Moderate deterioration (mild recession, execution miss)",
                    "**Severe Stress**: Major adverse event (big competitor, regulatory action)",
                    "**Catastrophic**: Existential risk (fraud, bankruptcy, tech disruption)",
                    "Estimates probability, revenue impact, valuation impact per scenario",
                    "Assesses recovery likelihood and investment implications for each",
                ],
                "sources": ["Phase 1-2 reports", "Bear case", "Red flags", "Fact-check output"],
            },
            {
                "icon": "📋",
                "name": "Completeness Checker",
                "role": "QA audit — identifies coverage gaps and rates decision readiness.",
                "methodology": [
                    "Scores coverage across 7 dimensions (0-1): financial, market, legal, management, tech, valuation, risk",
                    "Identifies specific gaps that could affect the investment decision",
                    "Flags information quality issues (low confidence, unverified claims)",
                    "Recommends additional diligence items with priority ranking",
                    "Issues a verdict: READY / NEEDS MORE WORK / INSUFFICIENT",
                ],
                "sources": ["All prior Phase 1, 2, and Phase 3 outputs"],
            },
        ],
    },
    {
        "label": "Phase 4 — Investment Memo",
        "color": "#059669",
        "bg": "#f0fdf4",
        "description": "One final agent reads the **entire DD package** and writes a professional investment memo with a definitive INVEST / WATCH / PASS recommendation.",
        "agents": [
            {
                "icon": "📝",
                "name": "Final Report Agent",
                "role": "Synthesizes all 12 prior agents into a structured investment memo.",
                "methodology": [
                    "Reads all Phase 1-3 outputs holistically",
                    "Weighs bull case vs. bear case vs. verified facts vs. stress scenarios",
                    "Writes a full Markdown investment memo (Executive Summary → Recommendation Rationale)",
                    "Issues **INVEST** (compelling upside, manageable risks), **WATCH** (interesting but uncertain), or **PASS** (risks outweigh opportunity)",
                    "Memo sections: Executive Summary, Thesis, Financials, Market, Management, Tech, Legal, Valuation, Stress Tests, Fact-Check, Recommendation",
                ],
                "sources": ["All 12 prior agent outputs (full DD package)"],
            },
        ],
    },
]


def _get_agent_phases(lang: str) -> list:
    """Return AGENT_PHASES with names/descriptions translated for the given language."""
    if lang == "en":
        return AGENT_PHASES

    # Korean overrides — methodology/sources stay in English (technical content)
    ko_meta = [
        {
            "label": "1단계 — 병렬 리서치",
            "description": "5개의 전문 에이전트가 **동시에** 실행됩니다. 각각 기업의 다른 차원을 독립적으로 리서치하며, 서로를 기다리지 않습니다.",
            "agents": [
                ("💰", "재무 분석가",        "재무 건전성, 수익성, 회계 품질을 평가합니다."),
                ("🌍", "시장 리서처",        "TAM/SAM 추정, 경쟁 환경 분석, 거시 트렌드 파악"),
                ("⚖️", "법적 리스크 분석가",  "소송, 규제 노출, IP 리스크, 거버넌스 문제를 분석합니다."),
                ("👥", "경영진 분석가",       "창업자, 임원진, 이사회, 조직 성숙도를 평가합니다."),
                ("🔬", "기술·제품 분석가",    "제품 성숙도, 기술 해자, 확장성, PMF를 평가합니다."),
            ],
        },
        {
            "label": "2단계 — 병렬 분석",
            "description": "4개의 투자 논거 에이전트가 **동시에** 실행됩니다. 각각 1단계 보고서를 전부 읽고 다양한 각도에서 투자 기회를 검증합니다.",
            "agents": [
                ("📈", "강세 논거 분석가",    "가장 강력한 투자 논거를 구축하고 상방 가치를 수치화합니다."),
                ("📉", "약세 논거 분석가",    "투자에 반하는 가장 강력한 주장을 구축하고 치명적 결함을 찾습니다."),
                ("🧮", "밸류에이션 분석가",   "DCF, 매출 배수, 선례 거래를 이용해 공정가치를 추정합니다."),
                ("🚩", "위험 신호 탐지기",    "1단계 보고서 전반에서 모순, 누락, 사기 신호를 교차 검토합니다."),
            ],
        },
        {
            "label": "3단계 — 순차 검증",
            "description": "3개의 QA 에이전트가 **순차적으로** 실행됩니다. 각 단계는 이전 단계 결과에 의존합니다. 순서: 팩트체크 → 스트레스 테스트 → 완성도 점검.",
            "agents": [
                ("🔎", "팩트체커",            "1·2단계의 모든 중요 주장을 독립적으로 검증합니다."),
                ("⚡", "스트레스 테스트 분석가","하방 시나리오 3가지를 정량적 재무 영향과 함께 모델링합니다."),
                ("📋", "완성도 검사기",        "QA 감사 — 커버리지 갭을 파악하고 의사결정 준비도를 평가합니다."),
            ],
        },
        {
            "label": "4단계 — 투자 메모",
            "description": "마지막 에이전트가 **전체 DD 패키지**를 읽고 INVEST / WATCH / PASS 결정을 담은 전문 투자 메모를 작성합니다.",
            "agents": [
                ("📝", "최종 보고서 에이전트", "12개 에이전트의 결과를 종합하여 구조화된 투자 메모를 작성합니다."),
            ],
        },
    ]

    result = []
    for phase_en, phase_ko in zip(AGENT_PHASES, ko_meta):
        phase_new = dict(phase_en)
        phase_new["label"]       = phase_ko["label"]
        phase_new["description"] = phase_ko["description"]
        new_agents = []
        for agent_en, (icon_ko, name_ko, role_ko) in zip(phase_en["agents"], phase_ko["agents"]):
            agent_new          = dict(agent_en)
            agent_new["icon"]  = icon_ko
            agent_new["name"]  = name_ko
            agent_new["role"]  = role_ko
            new_agents.append(agent_new)
        phase_new["agents"] = new_agents
        result.append(phase_new)
    return result


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Due Diligence Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .main .block-container { max-width: 1100px; padding-top: 1.5rem; }
  .invest-badge {
      background:#dcfce7; color:#15803d;
      padding:14px 40px; border-radius:14px;
      font-size:2.2rem; font-weight:900; letter-spacing:0.08em;
      display:inline-block; margin-bottom:6px;
  }
  .watch-badge {
      background:#fef3c7; color:#b45309;
      padding:14px 40px; border-radius:14px;
      font-size:2.2rem; font-weight:900; letter-spacing:0.08em;
      display:inline-block; margin-bottom:6px;
  }
  .pass-badge {
      background:#fee2e2; color:#b91c1c;
      padding:14px 40px; border-radius:14px;
      font-size:2.2rem; font-weight:900; letter-spacing:0.08em;
      display:inline-block; margin-bottom:6px;
  }
  .agent-card {
      background:#f8fafc; border:1px solid #e2e8f0;
      border-radius:10px; padding:14px 16px; margin-bottom:10px;
  }
  .source-tag {
      display:inline-block; background:#e0e7ff; color:#3730a3;
      border-radius:99px; padding:2px 10px; font-size:0.75rem;
      margin:2px 2px 2px 0;
  }
  .lang-toggle { font-size:0.8rem !important; padding:3px 10px !important; }
</style>
""", unsafe_allow_html=True)

# ── Password gate ─────────────────────────────────────────────────────────────
_app_password = ""
try:
    _app_password = str(st.secrets.get("APP_PASSWORD", ""))
except Exception:
    pass

if _app_password:
    if not st.session_state.get("authenticated"):
        _pw_hdr, _pw_lang = st.columns([5, 1])
        with _pw_hdr:
            st.markdown("## 📊 Due Diligence Agent")
        with _pw_lang:
            _cur_lang = st.session_state.get("ui_lang", "en")
            if st.button("한국어" if _cur_lang == "en" else "English", key="lang_btn_auth"):
                st.session_state.ui_lang = "ko" if _cur_lang == "en" else "en"
                st.rerun()
        st.divider()
        pwd = st.text_input(
            t("password_label"),
            type="password",
            placeholder=t("password_placeholder"),
        )
        if st.button(t("unlock_btn"), type="primary"):
            if pwd == _app_password:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error(t("wrong_password"))
        st.stop()

# ── API key check ─────────────────────────────────────────────────────────────
_missing = validate_config()
if _missing:
    st.error(
        f"**Missing API keys:** {', '.join(_missing)}\n\n"
        "On **Streamlit Cloud**: go to your app → ⚙️ Settings → Secrets, and paste:\n"
        "```toml\n"
        'ANTHROPIC_API_KEY = "sk-ant-..."\n'
        'TAVILY_API_KEY = "tvly-..."\n'
        "```\n"
        "Running locally? Add those same lines to a `.env` file in the project folder."
    )
    st.stop()

# ── Session state defaults ─────────────────────────────────────────────────────
for key, default in [
    ("phase", "form"),
    ("result", None),
    ("pdf_bytes", None),
    ("company", ""),
    ("job_id", None),
    ("history_pdf_cache", {}),
    ("ui_lang", "en"),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# If there's an active job still running or queued, redirect to the running screen automatically
_active_job = st.session_state.get("job_id")
if _active_job and st.session_state.phase not in ("running", "results", "history"):
    if _read_job(_active_job).get("status") in ("running", "queued"):
        st.session_state.phase = "running"


# ── Language toggle helper ─────────────────────────────────────────────────────

def _lang_toggle(key_suffix: str = ""):
    """Render a compact language toggle button."""
    lang = st.session_state.get("ui_lang", "en")
    label = "한국어" if lang == "en" else "English"
    if st.button(label, key=f"lang_btn_{key_suffix}"):
        st.session_state.ui_lang = "ko" if lang == "en" else "en"
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def render_agent_card(agent: dict):
    with st.container():
        st.markdown(
            f"<div class='agent-card'>"
            f"<b>{agent['icon']} {agent['name']}</b><br>"
            f"<span style='color:#475569;font-size:0.88rem'>{agent['role']}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        with st.expander(t("methodology_expander")):
            st.markdown(t("how_it_works"))
            for step in agent["methodology"]:
                st.markdown(f"- {step}")
            st.markdown(t("sources_label"))
            tags = "".join(
                f"<span class='source-tag'>{s}</span>" for s in agent["sources"]
            )
            st.markdown(tags, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# SCREEN 1 — FORM
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.phase == "form":

    # ── Header ────────────────────────────────────────────────────────────────
    hdr_col, lang_col, hist_col = st.columns([5, 0.7, 0.8])
    with hdr_col:
        st.markdown(t("app_title"))
        st.caption(t("app_subtitle"))
    with lang_col:
        st.markdown("")
        _lang_toggle("form")
    with hist_col:
        st.markdown("")
        if st.button(t("history_btn"), use_container_width=True):
            st.session_state.phase = "history"
            st.rerun()
    st.divider()

    # ── Two-column layout: form left, pipeline right ──────────────────────────
    col_form, col_pipeline = st.columns([1, 1.4], gap="large")

    with col_form:
        st.markdown(t("form_heading"))
        company = st.text_input(
            t("company_label"),
            placeholder=t("company_placeholder"),
        )
        url = st.text_input(
            t("url_label"),
            placeholder=t("url_placeholder"),
        )
        language = st.radio(
            t("report_lang_label"),
            options=["English", "한국어"],
            horizontal=True,
            help="Choose the language for the entire analysis and investment memo.",
        )
        uploaded_files = st.file_uploader(
            t("docs_label"),
            type=["pdf"],
            accept_multiple_files=True,
            help=t("docs_help"),
        )
        st.markdown("")
        st.caption(t("cost_caption"))
        run = st.button(
            t("run_btn"),
            type="primary",
            disabled=not ((company or "").strip() and (url or "").strip()),
            use_container_width=True,
        )

    with col_pipeline:
        st.markdown(t("pipeline_heading"))
        st.caption(t("pipeline_caption"))
        st.graphviz_chart(PIPELINE_GRAPH, use_container_width=True)

    st.divider()

    # ── Agent Directory ───────────────────────────────────────────────────────
    st.markdown(t("directory_heading"))
    st.caption(t("directory_caption"))
    st.markdown("")

    active_phases = _get_agent_phases(st.session_state.get("ui_lang", "en"))
    tabs = st.tabs([p["label"] for p in active_phases])
    for tab, phase in zip(tabs, active_phases):
        with tab:
            st.markdown(
                f"<p style='color:{phase['color']};font-size:0.9rem'>{phase['description']}</p>",
                unsafe_allow_html=True,
            )
            st.markdown("")
            n = len(phase["agents"])
            cols = st.columns(min(n, 2))
            for i, agent in enumerate(phase["agents"]):
                with cols[i % 2]:
                    render_agent_card(agent)

    # ── Analysis runner ───────────────────────────────────────────────────────
    if run and company.strip() and url.strip():
        tmp_dir = tempfile.mkdtemp()
        doc_paths: list[str] = []
        for f in (uploaded_files or []):
            dest = os.path.join(tmp_dir, f.name)
            with open(dest, "wb") as out:
                out.write(f.getbuffer())
            doc_paths.append(dest)

        job_id = str(uuid.uuid4())
        # Map display label to canonical language string
        lang_map = {"English": "English", "한국어": "Korean"}
        lang_value = lang_map.get(language, "English")

        initial_state = {
            "company_name": company.strip(),
            "company_url": url.strip(),
            "uploaded_docs": doc_paths,
            "language": lang_value,
            "financial_report": None,
            "market_report": None,
            "legal_report": None,
            "management_report": None,
            "tech_report": None,
            "bull_case": None,
            "bear_case": None,
            "valuation": None,
            "red_flags": [],
            "verification": None,
            "stress_test": None,
            "completeness": None,
            "final_report": None,
            "recommendation": None,
            "messages": [],
            "errors": [],
            "current_phase": "init",
        }

        _update_job(job_id, {
            "status": "running",
            "progress": [],
            "error": None,
            "start_time": time.time(),
        })

        t_thread = threading.Thread(
            target=_analysis_worker,
            args=(job_id, initial_state, company.strip(), tmp_dir),
            daemon=True,
        )
        t_thread.start()

        st.session_state.job_id = job_id
        st.session_state.company = company.strip()
        st.session_state.phase = "running"
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# SCREEN 2 — RUNNING (background thread progress)
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.phase == "running":
    job_id  = st.session_state.get("job_id", "")
    company = st.session_state.get("company", "")

    job = _read_job(job_id)

    if job["status"] == "complete":
        pdf_path = job.get("pdf_path", "")
        pdf_bytes = Path(pdf_path).read_bytes() if pdf_path and Path(pdf_path).exists() else b""
        st.session_state.result = {
            "final_report":   job.get("final_report", ""),
            "recommendation": job.get("recommendation", "WATCH"),
            "token_usage":    job.get("token_usage", {}),
        }
        st.session_state.pdf_bytes = pdf_bytes
        st.session_state.history_pdf_cache[job_id] = pdf_bytes
        st.session_state.phase = "results"
        st.rerun()

    elif job["status"] == "error":
        st.error(t("analysis_failed", job.get("error", "Unknown error")))
        st.session_state.job_id = None
        if st.button(t("try_again_btn")):
            st.session_state.phase = "form"
            st.rerun()

    elif job["status"] == "queued":
        # Waiting for a semaphore slot — show queue message
        _q_hdr, _q_lang = st.columns([5, 1])
        with _q_hdr:
            st.markdown(t("queued_heading", company))
            st.caption(t("queued_caption"))
        with _q_lang:
            _lang_toggle("queued")
        st.info(t("queued_info"))
        elapsed_sec = time.time() - (job.get("start_time") or time.time())
        st.caption(t("waiting_caption", int(elapsed_sec)))
        time.sleep(5)
        st.rerun()

    else:
        # Still running — show live progress and poll
        _node_labels = _NODE_LABELS_KO if st.session_state.get("ui_lang") == "ko" else _NODE_LABELS_EN

        _run_hdr, _run_lang, _run_hist = st.columns([5, 0.7, 0.8])
        with _run_hdr:
            st.markdown(t("analyzing", company))
            st.caption(t("running_caption"))
        with _run_lang:
            _lang_toggle("running")
        with _run_hist:
            st.markdown("")
            if st.button(t("history_btn"), use_container_width=True, key="hist_running"):
                st.session_state.phase = "history"
                st.rerun()

        st.divider()

        progress    = job.get("progress") or []
        start_time  = job.get("start_time") or time.time()
        elapsed_sec = time.time() - start_time

        # ── Progress calculation ───────────────────────────────────────────
        completed_weight = sum(NODE_WEIGHTS.get(n, 0) for n in progress)
        total_weight     = sum(NODE_WEIGHTS.values())
        pct = completed_weight / total_weight  # 0.0 → 1.0

        # Elapsed + estimated remaining
        def _fmt_time(seconds: float) -> str:
            seconds = int(seconds)
            if seconds < 60:
                return f"{seconds}s"
            return f"{seconds // 60}m {seconds % 60:02d}s"

        elapsed_str = _fmt_time(elapsed_sec)
        if pct > 0.02:
            est_total  = elapsed_sec / pct
            remaining  = max(0, est_total - elapsed_sec)
            eta_str    = t("eta_remaining", _fmt_time(remaining))
        else:
            eta_str = t("eta_estimating")

        # ── Progress bar + stats row ───────────────────────────────────────
        steps_done  = len(progress)
        steps_total = len(_node_labels)
        st.progress(pct, text=t(
            "progress_text",
            pct=int(pct * 100),
            done=steps_done,
            total=steps_total,
            elapsed=elapsed_str,
            eta=eta_str,
        ))

        # ── Live cost tracker ──────────────────────────────────────────────
        token_usage = job.get("token_usage") or {}
        total_cost  = sum(v.get("cost_usd", 0)       for v in token_usage.values())
        total_in    = sum(v.get("input_tokens", 0)    for v in token_usage.values())
        total_out   = sum(v.get("output_tokens", 0)   for v in token_usage.values())
        if token_usage:
            st.caption(t("api_cost", cost=total_cost, inp=total_in, out=total_out))

        st.markdown("")

        # ── Completed steps ────────────────────────────────────────────────
        for node in progress:
            label = _node_labels.get(node, node.replace("_", " ").title())
            # Show per-node cost for steps that use the LLM
            if node in ("phase1_parallel", "phase2_parallel"):
                phase_agents = (
                    ["financial_analyst","market_research","legal_risk","management_team","tech_product"]
                    if node == "phase1_parallel" else
                    ["bull_case","bear_case","valuation","red_flag"]
                )
                phase_cost = sum(token_usage.get(a, {}).get("cost_usd", 0) for a in phase_agents)
                st.write(f"✓ {label}  —  ${phase_cost:.4f}")
            elif node not in ("input_processor", "phase1_aggregator", "phase2_aggregator"):
                node_cost = token_usage.get(node, {}).get("cost_usd", 0)
                if node_cost:
                    st.write(f"✓ {_node_labels.get(node, node)}  —  ${node_cost:.4f}")
                else:
                    st.write(f"✓ {_node_labels.get(node, node)}")
            else:
                st.write(f"✓ {label}")

        # ── Current step spinner ───────────────────────────────────────────
        completed_set = set(progress)
        for node in _node_labels:
            if node not in completed_set:
                st.write(f"⏳ {_node_labels[node]}…")
                break

        # Poll every 3 seconds
        time.sleep(3)
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# SCREEN 3 — RESULTS
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.phase == "results":
    result:  dict = st.session_state.result or {}
    company: str  = st.session_state.company
    rec = (result.get("recommendation") or "WATCH").upper()

    badge_class = {
        "INVEST": "invest-badge",
        "WATCH":  "watch-badge",
        "PASS":   "pass-badge",
    }.get(rec, "watch-badge")

    rec_desc = {
        "INVEST": t("invest_desc"),
        "WATCH":  t("watch_desc"),
        "PASS":   t("pass_desc"),
    }.get(rec, "")

    _res_hdr, _res_lang = st.columns([5, 1])
    with _res_hdr:
        st.markdown(f"### {company}")
        st.markdown(f'<div class="{badge_class}">{rec}</div>', unsafe_allow_html=True)
        st.caption(rec_desc)
    with _res_lang:
        st.markdown("")
        _lang_toggle("results")
    st.divider()

    col_dl, col_reset, col_hist, _ = st.columns([1, 1, 1, 1])
    with col_dl:
        if st.session_state.pdf_bytes:
            st.download_button(
                label=t("download_btn"),
                data=st.session_state.pdf_bytes,
                file_name=f"due_diligence_{company.replace(' ', '_')}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )
    with col_reset:
        if st.button(t("analyze_another_btn"), use_container_width=True):
            st.session_state.phase    = "form"
            st.session_state.result   = None
            st.session_state.pdf_bytes = None
            st.session_state.job_id   = None
            st.rerun()
    with col_hist:
        if st.button(t("history_btn"), use_container_width=True, key="hist_results"):
            st.session_state.phase = "history"
            st.rerun()

    st.divider()

    # ── Token usage & cost breakdown ───────────────────────────────────────────
    token_usage: dict = result.get("token_usage") or {}
    if token_usage:
        total_in   = sum(v.get("input_tokens",  0) for v in token_usage.values())
        total_out  = sum(v.get("output_tokens", 0) for v in token_usage.values())
        total_cost = sum(v.get("cost_usd",      0) for v in token_usage.values())

        with st.expander(t("token_expander", total_cost), expanded=False):
            st.caption(t("token_caption"))
            st.markdown("")

            # Agent labels in the active language
            _agent_labels = _AGENT_LABELS_KO if st.session_state.get("ui_lang") == "ko" else _AGENT_LABELS_EN

            # Table rows in display order
            rows = []
            for key in _AGENT_ORDER:
                if key not in token_usage:
                    continue
                v = token_usage[key]
                rows.append({
                    t("agent_col"):         _agent_labels.get(key, key),
                    t("input_tokens_col"):  f"{v.get('input_tokens',  0):,}",
                    t("output_tokens_col"): f"{v.get('output_tokens', 0):,}",
                    t("cost_col"):          f"${v.get('cost_usd', 0):.4f}",
                })

            # Summary row
            rows.append({
                t("agent_col"):         t("total_label"),
                t("input_tokens_col"):  f"**{total_in:,}**",
                t("output_tokens_col"): f"**{total_out:,}**",
                t("cost_col"):          f"**${total_cost:.4f}**",
            })

            st.table(rows)

    st.divider()

    final_report: str = result.get("final_report") or ""
    if final_report.strip():
        st.markdown(final_report)
    else:
        st.info(t("no_report"))


# ─────────────────────────────────────────────────────────────────────────────
# SCREEN 4 — HISTORY
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.phase == "history":
    _hist_hdr, _hist_lang = st.columns([5, 1])
    with _hist_hdr:
        st.markdown(t("history_title"))
        st.caption(t("history_caption"))
    with _hist_lang:
        _lang_toggle("history")

    _back_job   = st.session_state.get("job_id")
    _back_label = t("back_btn")
    _back_phase = "form"
    if _back_job and _read_job(_back_job).get("status") in ("running", "queued"):
        _back_label = t("back_running_btn")
        _back_phase = "running"
    if st.button(_back_label):
        st.session_state.phase = _back_phase
        st.rerun()
    st.divider()

    history = _load_history()

    if not history:
        st.info(t("no_history"))
    else:
        badge_css = {
            "INVEST": ("background:#dcfce7;color:#15803d", "INVEST"),
            "WATCH":  ("background:#fef3c7;color:#b45309", "WATCH"),
            "PASS":   ("background:#fee2e2;color:#b91c1c", "PASS"),
        }
        for entry in history:
            rec    = (entry.get("recommendation") or "WATCH").upper()
            style, label = badge_css.get(rec, badge_css["WATCH"])
            badge_html = (
                f"<span style='{style};padding:3px 12px;border-radius:8px;"
                f"font-weight:700;font-size:0.85rem'>{label}</span>"
            )
            col_name, col_rec, col_date, col_dl = st.columns([2.5, 1, 1.5, 1])
            with col_name:
                st.markdown(f"**{entry.get('company', '—')}**")
            with col_rec:
                st.markdown(badge_html, unsafe_allow_html=True)
            with col_date:
                st.caption(entry.get("date", ""))
            with col_dl:
                job_id   = entry.get("id", "")
                pdf_bytes = st.session_state.history_pdf_cache.get(job_id)
                if pdf_bytes is None:
                    pdf_path = entry.get("pdf_path", "")
                    if pdf_path and Path(pdf_path).exists():
                        try:
                            pdf_bytes = Path(pdf_path).read_bytes()
                            st.session_state.history_pdf_cache[job_id] = pdf_bytes
                        except Exception:
                            pdf_bytes = None
                if pdf_bytes:
                    fname = f"dd_{entry.get('company','report').replace(' ','_')}.pdf"
                    st.download_button(
                        label=t("pdf_btn"),
                        data=pdf_bytes,
                        file_name=fname,
                        mime="application/pdf",
                        key=f"dl_{job_id}",
                        use_container_width=True,
                    )
                else:
                    st.caption(t("pdf_unavail"))
            st.divider()
