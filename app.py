"""Streamlit web UI for the Due Diligence Agent."""
import os
import shutil
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from supabase_storage import (
    read_job,
    update_job,
    load_history,
    load_queue,
    save_history_entry,
    upload_pdf,
    upload_file,
    download_pdf,
    download_file,
)

# Max concurrent analyses. Additional submissions wait in queue.
_ANALYSIS_SEMAPHORE = threading.Semaphore(2)


# ── Token cost tracking ────────────────────────────────────────────────────────

# claude-sonnet-4-6 pricing (USD per 1M tokens)
_PRICE_INPUT_PER_M  = 3.00
_PRICE_OUTPUT_PER_M = 15.00

# Human-readable labels for each agent key
_AGENT_LABELS_EN = {
    "market_analysis":     "Market Analysis",
    "competitor_analysis": "Competitor Analysis",
    "financial_analysis":  "Financial Analysis",
    "tech_analysis":       "Tech Analysis",
    "legal_regulatory":    "Legal & Regulatory",
    "team_analysis":       "Team Analysis",
    "ra_synthesis":        "R&A Synthesis",
    "risk_assessment":     "Risk Assessment",
    "strategic_insight":   "Strategic Insight",
    "review_agent":        "Review Agent",
    "critique_agent":      "Critique Agent",
    "selective_rerun":     "Selective Re-run",
    "phase1_restart":      "Phase 1 Restart",
    "dd_questions":        "DD Questions",
    "report_structure":    "Report Structure",
    "report_writer":       "Report Writer",
}

_AGENT_LABELS_KO = {
    "market_analysis":     "시장 분석",
    "competitor_analysis": "경쟁사 분석",
    "financial_analysis":  "재무 분석",
    "tech_analysis":       "기술 분석",
    "legal_regulatory":    "법률·규제 분석",
    "team_analysis":       "팀 분석",
    "ra_synthesis":        "R&A 종합",
    "risk_assessment":     "리스크 평가",
    "strategic_insight":   "전략적 인사이트",
    "review_agent":        "검토 에이전트",
    "critique_agent":      "비평 에이전트",
    "selective_rerun":     "선택적 재실행",
    "phase1_restart":      "1단계 재시작",
    "dd_questions":        "DD 질문서",
    "report_structure":    "보고서 구조",
    "report_writer":       "보고서 작성자",
}

# Display order
_AGENT_ORDER = list(_AGENT_LABELS_EN.keys())

# Keys to collect from pipeline state as agent outputs
_AGENT_OUTPUT_KEYS = [
    "market_analysis", "competitor_analysis", "financial_analysis",
    "tech_analysis", "legal_regulatory", "team_analysis",
    "ra_synthesis", "risk_assessment", "strategic_insight",
    "review_result", "critique_result", "dd_questions",
    "report_structure",
]

# Phase-grouped layout for rendering agent outputs
_AGENT_OUTPUT_PHASES = [
    {
        "heading_en": "Phase 1: Research & Analysis",
        "heading_ko": "1단계: 리서치 & 분석",
        "keys": [
            ("market_analysis",     "🔍"),
            ("competitor_analysis", "🏢"),
            ("financial_analysis",  "💰"),
            ("tech_analysis",       "🔧"),
            ("legal_regulatory",    "⚖️"),
            ("team_analysis",       "👥"),
        ],
    },
    {
        "heading_en": "Phase 2: Synthesis",
        "heading_ko": "2단계: 종합",
        "keys": [
            ("ra_synthesis",     "📈"),
            ("risk_assessment",  "⚠️"),
            ("strategic_insight","🎯"),
        ],
    },
    {
        "heading_en": "Phase 3: Review & Critique",
        "heading_ko": "3단계: 검토 & 비평",
        "keys": [
            ("review_result",  "✅"),
            ("critique_result","📝"),
            ("dd_questions",   "❓"),
        ],
    },
    {
        "heading_en": "Phase 4: Report",
        "heading_ko": "4단계: 보고서",
        "keys": [
            ("report_structure", "📋"),
        ],
    },
]


def _cost_usd(inp: int, out: int) -> float:
    return inp / 1_000_000 * _PRICE_INPUT_PER_M + out / 1_000_000 * _PRICE_OUTPUT_PER_M


# ── Background worker ──────────────────────────────────────────────────────────

def _analysis_worker(job_id: str, initial_state: dict, company: str, tmp_dir: str) -> None:
    """Daemon thread — waits for a semaphore slot, then runs the full pipeline."""
    # Wait for a free slot (max 2 concurrent analyses)
    update_job(job_id, {"status": "queued"})
    _ANALYSIS_SEMAPHORE.acquire()
    try:
        update_job(job_id, {"status": "running", "start_time": time.time()})
        _run_pipeline(job_id, initial_state, company, tmp_dir)
    finally:
        _ANALYSIS_SEMAPHORE.release()


def _run_pipeline(job_id: str, initial_state: dict, company: str, tmp_dir: str) -> None:
    """Inner worker — runs the full pipeline with feedback loop support."""
    try:
        import pdf_report
        import pptx_report
        from agents.base import get_and_reset_usage
        from config import MAX_COST_PER_ANALYSIS
        from graph.workflow import (
            input_processor, phase1_parallel, phase1_aggregator,
            phase2_parallel, strategic_insight_node, phase2_aggregator,
            review_agent_node, critique_agent_node, critique_router,
            selective_rerun, phase1_restart,
            dd_questions_node, report_structure_node, report_writer_node,
        )

        state: dict = dict(initial_state)
        progress: list[str] = []
        token_usage: dict = {}

        _NO_LLM_NODES = {"input_processor", "phase1_aggregator", "phase2_aggregator",
                         "phase1_restart"}

        def _total_cost() -> float:
            return sum(v.get("cost_usd", 0) for v in token_usage.values())

        def _over_budget() -> bool:
            return _total_cost() > MAX_COST_PER_ANALYSIS

        def _step(fn, node_name: str) -> None:
            result = fn(state)
            state.update(result)
            progress.append(node_name)

            if node_name in ("phase1_parallel", "phase2_parallel"):
                for agent_key, usage in (state.pop("__agent_usage__", {}) or {}).items():
                    token_usage[agent_key] = {
                        "input_tokens":  usage["input_tokens"],
                        "output_tokens": usage["output_tokens"],
                        "cost_usd":      _cost_usd(usage["input_tokens"], usage["output_tokens"]),
                    }
            elif node_name not in _NO_LLM_NODES:
                usage = get_and_reset_usage()
                token_usage[node_name] = {
                    "input_tokens":  usage["input_tokens"],
                    "output_tokens": usage["output_tokens"],
                    "cost_usd":      _cost_usd(usage["input_tokens"], usage["output_tokens"]),
                }

            update_job(job_id, {
                "progress":    progress.copy(),
                "token_usage": token_usage.copy(),
            })

        # Main pipeline
        _step(input_processor,        "input_processor")
        _step(phase1_parallel,        "phase1_parallel")
        _step(phase1_aggregator,      "phase1_aggregator")
        _step(phase2_parallel,        "phase2_parallel")
        _step(strategic_insight_node, "strategic_insight")
        _step(phase2_aggregator,      "phase2_aggregator")

        # Phase 3 — review + critique, with at most 1 rerun
        _step(review_agent_node,   "review_agent")
        _step(critique_agent_node, "critique_agent")

        route = critique_router(state)
        progress.append(f"critique_router:{route}")
        update_job(job_id, {"progress": progress.copy()})

        if route != "pass" and not _over_budget():
            if route == "conditional":
                _step(selective_rerun, "selective_rerun")
            elif route == "fail":
                _step(phase1_restart, "phase1_restart")
                _step(phase1_parallel, "phase1_parallel")
                _step(phase1_aggregator, "phase1_aggregator")
                _step(phase2_parallel, "phase2_parallel")
                _step(strategic_insight_node, "strategic_insight")
                _step(phase2_aggregator, "phase2_aggregator")

            # Second review after rerun — always proceed regardless of score
            _step(review_agent_node,   "review_agent")
            _step(critique_agent_node, "critique_agent")
            route2 = critique_router(state)
            progress.append(f"critique_router:{route2}")
            update_job(job_id, {"progress": progress.copy()})

        # Forward path
        _step(dd_questions_node,      "dd_questions")
        _step(report_structure_node,  "report_structure")
        _step(report_writer_node,     "report_writer")

        # Generate PDF
        pdf_path = pdf_report.generate_pdf(state, job_id, output_dir=tmp_dir)
        pdf_storage = upload_pdf(job_id, pdf_path)

        # Generate PPTX + upload to Supabase
        pptx_storage = None
        try:
            pptx_path = pptx_report.generate_pptx(state, job_id, output_dir=tmp_dir)
            pptx_storage = upload_file(job_id, pptx_path, folder="pptx")
        except Exception:
            pass

        # Generate DOCX + upload to Supabase
        docx_storage = None
        try:
            import docx_report
            docx_path = docx_report.generate_docx(state, job_id, output_dir=tmp_dir)
            docx_storage = upload_file(job_id, docx_path, folder="docx")
        except Exception:
            pass

        save_history_entry({
            "id": job_id,
            "company": company,
            "recommendation": (state.get("recommendation") or "WATCH").upper(),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "pdf_path": pdf_storage,
        })

        # Mark job complete first (critical — must not fail)
        job_update = {
            "status":         "complete",
            "pdf_path":       pdf_storage,
            "recommendation": (state.get("recommendation") or "WATCH").upper(),
            "final_report":   state.get("final_report") or "",
            "token_usage":    token_usage,
        }
        if pptx_storage:
            job_update["pptx_path"] = pptx_storage
        if docx_storage:
            job_update["docx_path"] = docx_storage
        update_job(job_id, job_update)

        # Persist agent outputs separately (best-effort — large payload)
        try:
            agent_outputs = {}
            for key in _AGENT_OUTPUT_KEYS:
                val = state.get(key)
                if val is not None:
                    agent_outputs[key] = val
            if agent_outputs:
                update_job(job_id, {"agent_outputs": agent_outputs})
        except Exception:
            pass  # Don't let agent_outputs failure break the completed job

    except Exception as exc:
        update_job(job_id, {"status": "error", "error": str(exc)})

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

import streamlit as st

# Inject Streamlit Cloud secrets into os.environ so config.py's os.getenv() works.
# This is a no-op when running locally with a .env file.
try:
    for _k in ["ANTHROPIC_API_KEY", "TAVILY_API_KEY", "EDGAR_USER_AGENT",
                "SUPABASE_URL", "SUPABASE_SERVICE_KEY"]:
        if _k in st.secrets and not os.environ.get(_k):
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass

from config import validate_config

# ── UI Translations ────────────────────────────────────────────────────────────

_UI = {
    "en": {
        "app_title":            "## 📊 Due Diligence Agent",
        "app_subtitle":         "Submit a company → 15 AI agents analyze it in 4 phases → full investment memo + PDF",
        "history_btn":          "🕐 History",
        "form_heading":         "#### Submit a Company",
        "company_label":        "Company Name",
        "company_placeholder":  "e.g. Apple, OpenAI, Stripe",
        "url_label":            "Website URL *(required — improves research quality)*",
        "url_placeholder":      "https://example.com",
        "report_lang_label":    "Report Language",
        "docs_label":           "Supporting Documents *(optional)*",
        "docs_help":            "Pitch decks, 10-Ks, annual reports, etc.",
        "cost_caption":         "Typical cost: **$1 – $5 per analysis** · 15 agents · claude-sonnet-4-6 · $3/M input · $15/M output",
        "run_btn":              "🔍  Run Due Diligence",
        "pipeline_heading":     "#### Agent Pipeline Flow",
        "pipeline_caption":     "Orchestrator reviews each phase — scores agents, revises weak ones (red dashed), then passes to the next phase.",
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
        "history_caption":      "All due diligence reports generated so far.",
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
        "queue_heading":        "#### Active Analyses",
        "queue_empty":          "No analyses running.",
        "queue_status_running": "Running",
        "queue_status_queued":  "Queued",
        "queue_view_btn":       "View",
        "queue_progress":       "{}%",
        "queue_eta":            "~{} left",
        "queue_started":        "Started {}s ago",
        "back_to_form_btn":     "← Back to Form",
        "job_picker_label":     "Switch analysis:",
        "agent_outputs_heading":"📊 Agent Outputs",
        "no_agent_outputs":     "No individual agent outputs available for this analysis.",
        "view_details_btn":     "📄 Details",
    },
    "ko": {
        "app_title":            "## 📊 실사 에이전트",
        "app_subtitle":         "기업을 입력하면 → AI 에이전트 15개가 4단계로 분석 → 투자 메모 + PDF 완성",
        "history_btn":          "🕐 분석 기록",
        "form_heading":         "#### 기업 분석 요청",
        "company_label":        "기업명",
        "company_placeholder":  "예: Apple, OpenAI, 카카오",
        "url_label":            "공식 웹사이트 *(필수 — 분석 품질 향상)*",
        "url_placeholder":      "https://example.com",
        "report_lang_label":    "보고서 언어",
        "docs_label":           "참고 문서 *(선택)*",
        "docs_help":            "사업계획서, 10-K, 연간보고서 등 PDF",
        "cost_caption":         "예상 비용: **분석당 $1 – $5** · 에이전트 15개 · claude-sonnet-4-6 · 입력 $3/M · 출력 $15/M",
        "run_btn":              "🔍  실사 분석 시작",
        "pipeline_heading":     "#### 에이전트 파이프라인",
        "pipeline_caption":     "오케스트레이터가 각 단계를 검토 — 에이전트 점수 평가, 약한 에이전트 재실행(빨간 점선), 통과 후 다음 단계로 진행.",
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
        "history_caption":      "지금까지 생성된 모든 실사 보고서",
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
        "queue_heading":        "#### 진행 중인 분석",
        "queue_empty":          "진행 중인 분석이 없습니다.",
        "queue_status_running": "실행 중",
        "queue_status_queued":  "대기 중",
        "queue_view_btn":       "보기",
        "queue_progress":       "{}%",
        "queue_eta":            "~{} 남음",
        "queue_started":        "{}초 전 시작",
        "back_to_form_btn":     "← 입력 폼으로",
        "job_picker_label":     "분석 전환:",
        "agent_outputs_heading":"📊 에이전트 출력",
        "no_agent_outputs":     "이 분석에 대한 개별 에이전트 출력이 없습니다.",
        "view_details_btn":     "📄 상세",
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
    "phase1_parallel":    "📊 Phase 1 — 6 research agents in parallel",
    "phase1_aggregator":  "✅ Phase 1 aggregated",
    "phase2_parallel":    "📈 Phase 2 — R&A Synthesis + Risk Assessment in parallel",
    "strategic_insight":  "🎯 Strategic Insight",
    "phase2_aggregator":  "✅ Phase 2 aggregated",
    "review_agent":       "🔎 Review Agent — verifying claims",
    "critique_agent":     "📋 Critique Agent — scoring quality",
    "selective_rerun":    "🔄 Selective re-run of weak agents",
    "phase1_restart":     "🔄 Full Phase 1 restart",
    "dd_questions":       "❓ DD Questions",
    "report_structure":   "📐 Report Structure",
    "report_writer":      "📝 Writing investment memo",
}

_NODE_LABELS_KO = {
    "input_processor":    "🔍 입력 처리 중",
    "phase1_parallel":    "📊 1단계 — 리서치 에이전트 6개 병렬 실행",
    "phase1_aggregator":  "✅ 1단계 집계 완료",
    "phase2_parallel":    "📈 2단계 — R&A 종합 + 리스크 평가 병렬 실행",
    "strategic_insight":  "🎯 전략적 인사이트",
    "phase2_aggregator":  "✅ 2단계 집계 완료",
    "review_agent":       "🔎 검토 에이전트 — 주장 검증",
    "critique_agent":     "📋 비평 에이전트 — 품질 채점",
    "selective_rerun":    "🔄 약한 에이전트 선택적 재실행",
    "phase1_restart":     "🔄 1단계 전체 재시작",
    "dd_questions":       "❓ DD 질문서",
    "report_structure":   "📐 보고서 구조",
    "report_writer":      "📝 투자 메모 작성 중",
}

# Weighted % of total runtime each node typically consumes (must sum to 100)
NODE_WEIGHTS = {
    "input_processor":    2,
    "phase1_parallel":    36,
    "phase1_aggregator":  1,
    "phase2_parallel":    14,
    "strategic_insight":  8,
    "phase2_aggregator":  1,
    "review_agent":       10,
    "critique_agent":     4,
    "selective_rerun":    6,
    "phase1_restart":     1,
    "dd_questions":       4,
    "report_structure":   4,
    "report_writer":      9,
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
        label="Phase 1  —  Parallel (6 agents)" fontsize=9 color="#2563eb"
        fillcolor="#eff6ff" style="rounded,filled";
        mkt  [label="Market\nAnalysis"   fillcolor="#bfdbfe" color="#1d4ed8" fontcolor="#1e3a8a"];
        comp [label="Competitor\nAnalysis" fillcolor="#bfdbfe" color="#1d4ed8" fontcolor="#1e3a8a"];
        fin  [label="Financial\nAnalysis"  fillcolor="#bfdbfe" color="#1d4ed8" fontcolor="#1e3a8a"];
        tec  [label="Tech\nAnalysis"      fillcolor="#bfdbfe" color="#1d4ed8" fontcolor="#1e3a8a"];
        leg  [label="Legal &\nRegulatory" fillcolor="#bfdbfe" color="#1d4ed8" fontcolor="#1e3a8a"];
        team [label="Team\nAnalysis"      fillcolor="#bfdbfe" color="#1d4ed8" fontcolor="#1e3a8a"];
    }

    subgraph cluster_p2 {
        label="Phase 2  —  Synthesis" fontsize=9 color="#7c3aed"
        fillcolor="#f5f3ff" style="rounded,filled";
        ras  [label="R&A\nSynthesis" fillcolor="#ddd6fe" color="#7c3aed" fontcolor="#4c1d95"];
        risk [label="Risk\nAssessment" fillcolor="#ddd6fe" color="#7c3aed" fontcolor="#4c1d95"];
        si   [label="Strategic\nInsight" fillcolor="#ddd6fe" color="#7c3aed" fontcolor="#4c1d95"];
    }

    subgraph cluster_p3 {
        label="Phase 3  —  Review & Critique" fontsize=9 color="#d97706"
        fillcolor="#fffbeb" style="rounded,filled";
        rev  [label="Review\nAgent"    fillcolor="#fde68a" color="#b45309" fontcolor="#78350f"];
        crit [label="Critique\nAgent"  fillcolor="#fde68a" color="#b45309" fontcolor="#78350f"];
        ddq  [label="DD\nQuestions"    fillcolor="#fde68a" color="#b45309" fontcolor="#78350f"];
    }

    router [label="Critique\nRouter" fillcolor="#a7f3d0" color="#059669" fontcolor="#064e3b"
            shape=diamond fontsize=8];

    subgraph cluster_p4 {
        label="Phase 4  —  Report" fontsize=9 color="#1e40af"
        fillcolor="#eff6ff" style="rounded,filled";
        rstr [label="Report\nStructure" fillcolor="#bfdbfe" color="#1d4ed8" fontcolor="#1e3a8a"];
        rwrt [label="Report\nWriter"    fillcolor="#bfdbfe" color="#1d4ed8" fontcolor="#1e3a8a"];
    }

    START -> inp;
    inp -> mkt; inp -> comp; inp -> fin; inp -> tec; inp -> leg; inp -> team;
    mkt -> ras; comp -> ras; fin -> ras; tec -> ras; leg -> ras; team -> ras;
    mkt -> risk; comp -> risk; fin -> risk; tec -> risk; leg -> risk; team -> risk;
    ras -> si; risk -> si;
    si -> rev;
    rev -> crit;
    crit -> router;
    router -> ddq [label=" pass " fontsize=7 color="#059669"];
    ddq -> rstr;
    rstr -> rwrt;
    rwrt -> END;

    // Feedback loop edges (dashed)
    edge [style=dashed color="#dc2626" arrowsize=0.5];
    router -> rev  [label="conditional\n(selective rerun)" fontsize=6 color="#dc2626"];
    router -> mkt  [label="fail\n(full restart)" fontsize=6 color="#dc2626"];
}
"""

# ── Agent directory data (English) ────────────────────────────────────────────
AGENT_PHASES = [
    {
        "label": "Phase 1 — Parallel Research",
        "color": "#1d4ed8",
        "bg": "#eff6ff",
        "description": "6 specialist agents run **simultaneously**. Each independently researches a different dimension of the company.",
        "agents": [
            {
                "icon": "🌍",
                "name": "Market Analysis",
                "role": "TAM/SAM/SOM for ALL markets, CAGR, trends, and market drivers.",
                "methodology": [
                    "Estimates TAM/SAM/SOM for each business line with specific dollar figures",
                    "Calculates historical and projected 5-year CAGR",
                    "Maps key market trends, drivers, and geographic breakdown",
                    "Identifies macro tailwinds/headwinds and demand-side dynamics",
                    "Cross-verifies all figures with 3+ sources",
                ],
                "sources": ["Web search", "News search", "Yahoo Finance", "Google Trends", "FRED macroeconomic data"],
            },
            {
                "icon": "🏢",
                "name": "Competitor Analysis",
                "role": "Competitor ID across all business lines, comparison matrix.",
                "methodology": [
                    "Identifies direct and indirect competitors across all business lines",
                    "Builds comparison matrix (product, pricing, financials, market share, talent)",
                    "Analyzes market share trends and competitive positioning",
                    "Assesses competitive gaps and pricing power dynamics",
                    "Includes actual revenue/market cap for public competitors",
                ],
                "sources": ["Web search", "News search", "Yahoo Finance", "Google Trends"],
            },
            {
                "icon": "💰",
                "name": "Financial Analysis",
                "role": "5-year financials, ratios, cash flow + DCF/Market-based/Asset-based valuation.",
                "methodology": [
                    "Pulls live financial data: revenue, margins, balance sheet, cash flow",
                    "Performs DCF with explicit WACC and terminal growth assumptions",
                    "Runs market-based valuation (P/E, EV/EBITDA, P/S) with domestic + international comps",
                    "Calculates fair value range (low/mid/high) with methodology",
                    "Flags accounting red flags and revenue concentration risks",
                ],
                "sources": ["Yahoo Finance (yfinance)", "SEC EDGAR (10-K, 10-Q)", "Web search", "Uploaded PDFs"],
            },
            {
                "icon": "🔬",
                "name": "Tech Analysis",
                "role": "Core tech inventory, IP/patents, tech maturity vs. competitors.",
                "methodology": [
                    "Inventories core technologies powering each business line",
                    "Assesses IP and patent portfolio (count, key patents, pending)",
                    "Evaluates tech maturity and moat strength vs. competitors",
                    "Reviews R&D investment levels and engineering capacity",
                    "Translates technical details into investor-friendly language",
                ],
                "sources": ["Web search", "News search", "GitHub API", "USPTO PatentsView"],
            },
            {
                "icon": "⚖️",
                "name": "Legal & Regulatory",
                "role": "Investment structure risks + business regulatory risks.",
                "methodology": [
                    "Evaluates investment structure risks (fund carry, exit, reputation)",
                    "Reviews business regulatory compliance across jurisdictions",
                    "Searches for active litigation, settlements, and enforcement actions",
                    "Assesses IP risks, data privacy posture, and ESG exposure",
                    "Flags corporate governance issues and related-party transactions",
                ],
                "sources": ["Web search", "News search", "USPTO PatentsView", "Uploaded PDFs"],
            },
            {
                "icon": "👥",
                "name": "Team Analysis",
                "role": "Leadership profiles, capability analysis, departure history.",
                "methodology": [
                    "Profiles CEO/founder, C-suite, and key executives",
                    "Assesses team capabilities vs. next growth phase requirements",
                    "Reviews departure history and succession planning",
                    "Evaluates board composition and advisory quality",
                    "Surfaces culture signals from Glassdoor, press, and social media",
                ],
                "sources": ["Web search", "News search", "LinkedIn (via web)"],
            },
        ],
    },
    {
        "label": "Phase 2 — Synthesis",
        "color": "#7c3aed",
        "bg": "#f5f3ff",
        "description": "R&A Synthesis + Risk Assessment run **in parallel**, then Strategic Insight runs **sequentially** (needs both).",
        "agents": [
            {
                "icon": "📊",
                "name": "R&A Synthesis",
                "role": "Synthesizes Phase 1 into 3-5 core investment arguments + CDD/LDD/FDD scorecard.",
                "methodology": [
                    "Distills 6 reports into 3-5 core investment arguments ranked by conviction",
                    "Builds attractiveness scorecard: CDD, LDD, FDD (each 1-10)",
                    "Checks cross-report consistency and flags contradictions",
                    "Identifies key findings and information gaps",
                ],
                "sources": ["All Phase 1 reports", "Web search", "Yahoo Finance"],
            },
            {
                "icon": "⚠️",
                "name": "Risk Assessment",
                "role": "ALL risks with probability/impact/severity matrix + mitigation strategies.",
                "methodology": [
                    "Identifies risks across 6 categories: legal, business, financial, reputation, tech, operational",
                    "Scores each risk: probability (1-5) × impact (1-5) = severity",
                    "Proposes specific mitigation strategies with feasibility rating",
                    "Determines overall risk level and risk-adjusted assessment",
                ],
                "sources": ["All Phase 1 reports", "Web search", "News search"],
            },
            {
                "icon": "🎯",
                "name": "Strategic Insight",
                "role": "INVEST/WATCH/PASS decision + detailed rationale + synergy analysis.",
                "methodology": [
                    "Renders preliminary investment recommendation with detailed rationale",
                    "Analyzes portfolio fit and strategic synergies",
                    "Identifies key conditions that would change the recommendation",
                    "Outlines investment timeline and exit strategy considerations",
                    "Anti-bias: does NOT default to WATCH — decisive recommendation required",
                ],
                "sources": ["All Phase 1 + Phase 2 reports", "Web search", "Yahoo Finance"],
            },
        ],
    },
    {
        "label": "Phase 3 — Review & Critique",
        "color": "#b45309",
        "bg": "#fffbeb",
        "description": "Sequential: **Review** (verify claims) → **Critique** (score 5 criteria) → **DD Questions**. The Critique agent triggers a **feedback loop** if quality is insufficient (max 2 iterations).",
        "agents": [
            {
                "icon": "🔎",
                "name": "Review Agent",
                "role": "Source verification, quantitative accuracy, logical consistency.",
                "methodology": [
                    "Verifies material claims using live tool calls",
                    "Checks quantitative accuracy of financial figures and market sizes",
                    "Assesses qualitative backing and logical consistency",
                    "Identifies stale data and cross-report inconsistencies",
                    "Classifies claims as VERIFIED / UNVERIFIED / CONTRADICTED / STALE",
                ],
                "sources": ["Web search", "News search", "Yahoo Finance"],
            },
            {
                "icon": "📋",
                "name": "Critique Agent",
                "role": "Scores 5 criteria (1-10): Logic, Completeness, Accuracy, Narrative Bias, Insight Effectiveness.",
                "methodology": [
                    "Scores Logic (1-10): Are investment arguments logically sound?",
                    "Scores Completeness (1-10): Does the analysis cover all material dimensions?",
                    "Scores Accuracy (1-10): Are facts and figures correct and current?",
                    "Scores Narrative Bias (1-10): Is the analysis balanced and objective?",
                    "Scores Insight Effectiveness (1-10): Does it provide actionable insights?",
                    "Total >= 35 AND all >= 7: PASS | < 30 or 3+ items < 5: FAIL | Otherwise: CONDITIONAL (selective rerun)",
                ],
                "sources": ["All prior agent outputs (no tools — pure evaluation)"],
            },
            {
                "icon": "❓",
                "name": "DD Questions",
                "role": "Unresolved issues list + structured DD Questionnaire.",
                "methodology": [
                    "Lists all unresolved issues remaining after analysis",
                    "Creates structured DD Questionnaire with target, priority, and expected scenarios",
                    "Recommends next steps for the investment team",
                    "Only runs after critique passes quality threshold",
                ],
                "sources": ["All prior agent outputs (no tools)"],
            },
        ],
    },
    {
        "label": "Phase 4 — Report",
        "color": "#1e40af",
        "bg": "#eff6ff",
        "description": "**Report Structure** designs the Why/What/How/Risk/Recommendations framework, then **Report Writer** produces the final polished memo.",
        "agents": [
            {
                "icon": "📐",
                "name": "Report Structure",
                "role": "Designs Why/What/How/Risk/Recommendations TOC with 20-30 page target.",
                "methodology": [
                    "Designs report following Why/What/How/Risk/Recommendations framework",
                    "Specifies data sources and key data points for each section",
                    "Sets target page counts and narrative arcs",
                    "Outlines executive summary and appendix sections",
                ],
                "sources": ["All prior agent outputs (no tools)"],
            },
            {
                "icon": "📝",
                "name": "Report Writer",
                "role": "Writes insight-driven final report with INVEST/WATCH/PASS recommendation.",
                "methodology": [
                    "Follows report structure to write comprehensive Markdown memo",
                    "Includes specific numbers, data points, and inline source citations",
                    "Balances bull and bear cases with evidence-based reasoning",
                    "Renders final INVEST/WATCH/PASS recommendation with confidence level",
                    "Includes DD Questionnaire and next steps",
                ],
                "sources": ["All prior agent outputs + Report Structure"],
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
            "description": "6개의 전문 에이전트가 **동시에** 실행됩니다. 각각 기업의 다른 차원을 독립적으로 리서치합니다.",
            "agents": [
                ("🌍", "시장 분석",          "TAM/SAM/SOM, CAGR, 시장 트렌드를 분석합니다."),
                ("🏢", "경쟁사 분석",        "모든 사업 라인의 경쟁사를 파악하고 비교 매트릭스를 구축합니다."),
                ("💰", "재무 분석",          "5년 재무제표, 비율, 현금흐름 + DCF/시장기반/자산기반 밸류에이션"),
                ("🔬", "기술 분석",          "핵심 기술, IP/특허, 기술 성숙도를 경쟁사와 비교 분석합니다."),
                ("⚖️", "법률·규제 분석",     "투자 구조 리스크 + 비즈니스 규제 리스크를 분석합니다."),
                ("👥", "팀 분석",            "리더십 프로필, 역량 분석, 이탈 이력을 평가합니다."),
            ],
        },
        {
            "label": "2단계 — 종합",
            "description": "R&A 종합 + 리스크 평가가 **병렬**로 실행되고, 전략적 인사이트가 **순차적**으로 실행됩니다.",
            "agents": [
                ("📊", "R&A 종합",           "1단계를 3-5개 핵심 투자 논거 + CDD/LDD/FDD 스코어카드로 종합합니다."),
                ("⚠️", "리스크 평가",         "모든 리스크를 확률/영향/심각도 매트릭스로 분석합니다."),
                ("🎯", "전략적 인사이트",     "INVEST/WATCH/PASS 결정 + 상세 근거 + 시너지 분석"),
            ],
        },
        {
            "label": "3단계 — 검토 & 비평",
            "description": "순차: **검토** (주장 검증) → **비평** (5개 기준 채점) → **DD 질문서**. 비평 에이전트가 품질 미달 시 **피드백 루프**를 실행합니다 (최대 2회).",
            "agents": [
                ("🔎", "검토 에이전트",       "출처 검증, 정량적 정확도, 논리적 일관성을 확인합니다."),
                ("📋", "비평 에이전트",       "5개 기준 채점(1-10): 논리, 완성도, 정확도, 서술 편향, 인사이트 실효성"),
                ("❓", "DD 질문서",           "미해결 이슈 목록 + 구조화된 DD 질문서를 작성합니다."),
            ],
        },
        {
            "label": "4단계 — 보고서",
            "description": "**보고서 구조** 에이전트가 Why/What/How/Risk/Recommendations 프레임워크를 설계하고, **보고서 작성자**가 최종 메모를 작성합니다.",
            "agents": [
                ("📐", "보고서 구조",        "Why/What/How/Risk/Recommendations TOC를 설계합니다."),
                ("📝", "보고서 작성자",       "인사이트 중심의 최종 보고서를 작성합니다."),
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
    ("active_jobs", []),        # list of job_id strings submitted by this user
    ("results", {}),            # {job_id: {result, pdf_bytes}}
    ("viewing_job", None),      # which job the running/results screen is showing
    ("company", ""),
    ("history_pdf_cache", {}),
    ("history_detail_job", None),
    ("ui_lang", "ko"),
]:
    if key not in st.session_state:
        st.session_state[key] = default


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


def _render_nested_dict(d: dict, indent: int = 0) -> None:
    """Render a nested dict as readable markdown paragraphs."""
    prefix = "  " * indent
    for k, v in d.items():
        label = k.replace("_", " ").title()
        if isinstance(v, dict):
            st.markdown(f"{prefix}**{label}:**")
            _render_nested_dict(v, indent + 1)
        elif isinstance(v, list):
            st.markdown(f"{prefix}**{label}:**")
            for item in v:
                if isinstance(item, dict):
                    parts = [f"{ik.replace('_', ' ').title()}: {iv}" for ik, iv in item.items() if iv]
                    st.markdown(f"{prefix}- {' — '.join(parts)}")
                else:
                    st.markdown(f"{prefix}- {item}")
        elif v is not None and v != "":
            st.markdown(f"{prefix}**{label}:** {v}")


def _render_agent_detail(key: str, data) -> None:
    """Render a single agent's output as readable formatted content."""
    # Safety: parse JSON string if Supabase returned it as string
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, ValueError):
            st.markdown(data)
            return
    if not isinstance(data, dict):
        st.json(data)
        return

    # Check for failed agent
    raw = data.get("raw", "") or data.get("raw_analysis", "")
    if "exceeded maximum iterations" in str(raw):
        st.warning("This agent did not complete its analysis.")
        return
    if raw and not any(k for k in data if k not in ("raw", "raw_analysis")):
        st.markdown(raw)
        return

    # Summary always first
    if "summary" in data:
        st.markdown(f"**Summary:** {data['summary']}")
        st.divider()

    # ── Critique agent: show scores prominently ──
    if key == "critique_result":
        score_keys = ["logic", "completeness", "accuracy", "narrative_bias", "insight_effectiveness"]
        score_labels = {
            "logic": "Logic", "completeness": "Completeness", "accuracy": "Accuracy",
            "narrative_bias": "Narrative Bias", "insight_effectiveness": "Insight Effectiveness",
        }
        cols = st.columns(len(score_keys))
        for col, sk in zip(cols, score_keys):
            val = data.get(sk, "?")
            col.metric(score_labels.get(sk, sk), f"{val}/10")
        total = data.get("total_score", "?")
        st.metric("Total Score", f"{total}/50")
        for fb in data.get("feedback", []):
            with st.expander(f"{fb.get('criterion', '?')} — {fb.get('score', '?')}/10"):
                st.markdown(f"**Assessment:** {fb.get('assessment', 'N/A')}")
                if fb.get("weak_agents"):
                    st.markdown(f"**Weak agents:** {', '.join(fb['weak_agents'])}")
                for imp in fb.get("specific_improvements", []):
                    st.markdown(f"- {imp}")
        return

    # ── Strategic insight: recommendation badge ──
    if key == "strategic_insight":
        rec = data.get("recommendation", "")
        if rec:
            color = {"INVEST": "green", "WATCH": "orange", "PASS": "red"}.get(rec, "gray")
            st.markdown(f"### :{color}[{rec}]")
        if data.get("rationale"):
            st.markdown(data["rationale"])
        for section_key, section_label in [("key_arguments_for", "Arguments For"), ("key_arguments_against", "Arguments Against")]:
            items = data.get(section_key, [])
            if items:
                st.markdown(f"**{section_label}:**")
                for item in items:
                    st.markdown(f"- {item}")
        if data.get("key_conditions"):
            st.markdown("**Key Conditions:**")
            for cond in data["key_conditions"]:
                st.markdown(f"- {cond.get('condition', cond) if isinstance(cond, dict) else cond}")
        return

    # ── Risk assessment: risk matrix table ──
    if key == "risk_assessment" and data.get("risk_matrix"):
        level = data.get("overall_risk_level", "")
        if level:
            color = {"high": "red", "medium": "orange", "low": "green"}.get(level.lower(), "gray")
            st.markdown(f"**Overall Risk Level:** :{color}[{level.upper()}]")
        rows = []
        for r in data["risk_matrix"]:
            if isinstance(r, dict):
                rows.append({
                    "Risk": r.get("risk", ""),
                    "Category": r.get("category", ""),
                    "Probability": r.get("probability", ""),
                    "Impact": r.get("impact", ""),
                    "Severity": r.get("severity", ""),
                })
        if rows:
            st.dataframe(rows, use_container_width=True)
        for tr in data.get("top_risks", []):
            if isinstance(tr, dict):
                st.markdown(f"- **{tr.get('risk', '')}** (severity {tr.get('severity', '?')}): {tr.get('why_critical', '')}")
        return

    # ── DD questions: questionnaire ──
    if key == "dd_questions":
        for issue in data.get("unresolved_issues", []):
            if isinstance(issue, dict):
                sev = issue.get("severity", "")
                st.markdown(f"- **[{sev.upper()}]** {issue.get('issue', '')}")
        if data.get("dd_questionnaire"):
            st.markdown("**Due Diligence Questions:**")
            for i, q in enumerate(data["dd_questionnaire"], 1):
                if isinstance(q, dict):
                    pri = q.get("priority", "")
                    st.markdown(f"{i}. **[{pri}]** {q.get('question', '')}")
                    if q.get("context"):
                        st.caption(f"   Context: {q['context']}")
        return

    # ── Generic renderer for other agents ──
    red_flags = data.get("red_flags", [])
    strengths = data.get("strengths", [])

    if strengths:
        st.markdown("**Strengths:**")
        for s in strengths:
            st.markdown(f"- :green[{s}]")

    if red_flags:
        st.markdown("**Red Flags:**")
        for r in red_flags:
            st.markdown(f"- :red[{r}]")

    confidence = data.get("confidence_score")
    if confidence is not None:
        st.metric("Confidence", f"{confidence:.0%}" if isinstance(confidence, (int, float)) else str(confidence))

    skip_keys = {"summary", "red_flags", "strengths", "confidence_score", "sources", "raw", "raw_analysis"}
    for field_key, field_val in data.items():
        if field_key in skip_keys:
            continue
        nice_label = field_key.replace("_", " ").title()

        if isinstance(field_val, str):
            st.markdown(f"**{nice_label}:** {field_val}")

        elif isinstance(field_val, list) and field_val:
            # List of dicts → render as table if uniform keys, else as cards
            if isinstance(field_val[0], dict):
                # Try table: all items share same keys
                all_keys = list(field_val[0].keys())
                uniform = all(set(item.keys()) == set(all_keys) for item in field_val if isinstance(item, dict))
                if uniform and len(all_keys) <= 8:
                    st.markdown(f"**{nice_label}:**")
                    table_data = []
                    for item in field_val:
                        row = {}
                        for k in all_keys:
                            v = item.get(k, "")
                            row[k.replace("_", " ").title()] = str(v) if not isinstance(v, str) else v
                        table_data.append(row)
                    st.dataframe(table_data, use_container_width=True, hide_index=True)
                else:
                    # Non-uniform dicts → render as readable cards
                    st.markdown(f"**{nice_label}:**")
                    for item in field_val:
                        if isinstance(item, dict):
                            # Use first string value as card title
                            title_val = ""
                            for v in item.values():
                                if isinstance(v, str) and len(v) < 100:
                                    title_val = v
                                    break
                            if title_val:
                                st.markdown(f"**{title_val}**")
                            for k, v in item.items():
                                if v and str(v) != title_val:
                                    st.markdown(f"- {k.replace('_', ' ').title()}: {v}")
                            st.markdown("")
            else:
                # List of strings
                st.markdown(f"**{nice_label}:**")
                for item in field_val:
                    st.markdown(f"- {item}")

        elif isinstance(field_val, dict) and field_val:
            st.markdown(f"**{nice_label}:**")
            _render_nested_dict(field_val)

    # Sources at bottom
    sources = data.get("sources", [])
    if sources:
        with st.expander("Sources"):
            for src in sources:
                if isinstance(src, dict):
                    label = src.get("label", src.get("url", ""))
                    url = src.get("url", "")
                    tool = src.get("tool", "")
                    st.markdown(f"- [{label}]({url}) ({tool})" if url else f"- {label} ({tool})")
                else:
                    st.markdown(f"- {src}")


def _render_agent_outputs(agent_outputs, lang: str = "en") -> None:
    """Render phase-grouped expanders for each agent's output in readable format."""
    if isinstance(agent_outputs, str):
        try:
            agent_outputs = json.loads(agent_outputs)
        except (json.JSONDecodeError, ValueError):
            pass
    if not agent_outputs or not isinstance(agent_outputs, dict):
        st.info(t("no_agent_outputs"))
        return

    labels = _AGENT_LABELS_KO if lang == "ko" else _AGENT_LABELS_EN

    for phase in _AGENT_OUTPUT_PHASES:
        heading = phase["heading_ko"] if lang == "ko" else phase["heading_en"]
        phase_keys_with_data = [
            (key, icon) for key, icon in phase["keys"] if key in agent_outputs
        ]
        if not phase_keys_with_data:
            continue

        st.markdown(f"**{heading}**")
        for key, icon in phase_keys_with_data:
            label = labels.get(key, key.replace("_", " ").title())
            with st.expander(f"{icon} {label}"):
                _render_agent_detail(key, agent_outputs[key])
        st.markdown("")


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
            options=["한국어", "English"],
            horizontal=True,
            help="Choose the language for the entire analysis and investment memo.",
        )
        company_type = st.radio(
            "Company type",
            options=["Auto-detect", "Public", "Private"],
            horizontal=True,
            help="Auto-detect probes Yahoo Finance. Choose Private to skip stock/SEC data lookups.",
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

    # ── Global Queue ──────────────────────────────────────────────────────────
    queue_items = load_queue()
    if queue_items:
        st.divider()
        st.markdown(t("queue_heading"))
        for qi in queue_items:
            qi_progress = qi.get("progress") or []
            qi_start = qi.get("start_time") or time.time()
            qi_elapsed = time.time() - qi_start

            completed_w = sum(NODE_WEIGHTS.get(n, 0) for n in set(qi_progress))
            total_w = sum(NODE_WEIGHTS.values())
            qi_pct = min(int(completed_w / total_w * 100), 100) if total_w else 0

            # ETA
            frac = completed_w / total_w if total_w else 0
            if frac > 0.02:
                est_total = qi_elapsed / frac
                remaining = max(0, est_total - qi_elapsed)
                rem_s = int(remaining)
                eta_label = t("queue_eta", f"{rem_s // 60}m {rem_s % 60:02d}s" if rem_s >= 60 else f"{rem_s}s")
            else:
                eta_label = ""

            qi_status = t("queue_status_running") if qi.get("status") == "running" else t("queue_status_queued")
            qi_company = qi.get("company") or qi.get("id", "")[:8]

            c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1.2, 0.8])
            with c1:
                st.markdown(f"**{qi_company}**")
            with c2:
                st.caption(qi_status)
            with c3:
                st.caption(t("queue_progress", qi_pct))
            with c4:
                st.caption(eta_label)
            with c5:
                qi_id = qi.get("id", "")
                if qi_id in st.session_state.active_jobs:
                    if st.button(t("queue_view_btn"), key=f"qv_{qi_id}"):
                        st.session_state.viewing_job = qi_id
                        # Look up company for this job
                        st.session_state.company = qi_company
                        st.session_state.phase = "running"
                        st.rerun()

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

        # Map company type selector to is_public value
        _ct_map = {"Auto-detect": None, "Public": True, "Private": False}
        is_public_value = _ct_map.get(company_type)

        initial_state = {
            "company_name": company.strip(),
            "company_url": url.strip(),
            "uploaded_docs": doc_paths,
            "is_public": is_public_value,
            "ticker": None,
            "language": lang_value,
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
            # Phase 3
            "review_result": None,
            "critique_result": None,
            "dd_questions": None,
            # Phase 4
            "report_structure": None,
            "final_report": None,
            "recommendation": None,
            # Feedback loop
            "phase1_context": None,
            "feedback_loop_count": 0,
            "weak_sections": [],
            # Bookkeeping
            "messages": [],
            "errors": [],
            "current_phase": "init",
        }

        update_job(job_id, {
            "status": "running",
            "progress": [],
            "error": None,
            "start_time": time.time(),
            "company": company.strip(),
        })

        t_thread = threading.Thread(
            target=_analysis_worker,
            args=(job_id, initial_state, company.strip(), tmp_dir),
            daemon=True,
        )
        t_thread.start()

        st.session_state.active_jobs.append(job_id)
        st.session_state.viewing_job = job_id
        st.session_state.company = company.strip()
        st.session_state.phase = "running"
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# SCREEN 2 — RUNNING (background thread progress)
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.phase == "running":
    job_id  = st.session_state.get("viewing_job", "")
    company = st.session_state.get("company", "")

    # ── Job picker (if user has multiple active jobs) ──────────────────────
    active_jobs = st.session_state.active_jobs
    if len(active_jobs) > 1:
        # Build label → job_id mapping
        _picker_labels = {}
        for _jid in active_jobs:
            _jdata = read_job(_jid)
            _jcompany = _jdata.get("company") or _jid[:8]
            _jstatus = _jdata.get("status", "unknown")
            _picker_labels[f"{_jcompany} ({_jstatus})"] = _jid
        _current_label = next(
            (lbl for lbl, jid in _picker_labels.items() if jid == job_id),
            list(_picker_labels.keys())[0] if _picker_labels else "",
        )
        _selected_label = st.selectbox(
            t("job_picker_label"),
            options=list(_picker_labels.keys()),
            index=list(_picker_labels.keys()).index(_current_label) if _current_label in _picker_labels else 0,
            key="job_picker",
        )
        _selected_jid = _picker_labels[_selected_label]
        if _selected_jid != job_id:
            st.session_state.viewing_job = _selected_jid
            _sel_data = read_job(_selected_jid)
            st.session_state.company = _sel_data.get("company") or ""
            st.rerun()

    if not job_id:
        st.session_state.phase = "form"
        st.rerun()

    job = read_job(job_id)

    if job["status"] == "complete":
        storage_path = job.get("pdf_path", "")
        pdf_bytes = download_pdf(storage_path) if storage_path else b""
        if not pdf_bytes:
            pdf_bytes = b""
        st.session_state.results[job_id] = {
            "result": {
                "final_report":   job.get("final_report", ""),
                "recommendation": job.get("recommendation", "WATCH"),
                "token_usage":    job.get("token_usage", {}),
            },
            "pdf_bytes": pdf_bytes,
            "pptx_path": job.get("pptx_path", ""),
            "docx_path": job.get("docx_path", ""),
            "company": job.get("company") or company,
            "agent_outputs": job.get("agent_outputs") or {},
        }
        st.session_state.history_pdf_cache[job_id] = pdf_bytes
        st.session_state.phase = "results"
        st.rerun()

    elif job["status"] == "error":
        st.error(t("analysis_failed", job.get("error", "Unknown error")))
        # Remove failed job from active list
        if job_id in st.session_state.active_jobs:
            st.session_state.active_jobs.remove(job_id)
        if st.button(t("try_again_btn")):
            st.session_state.viewing_job = None
            st.session_state.phase = "form"
            st.rerun()

    elif job["status"] == "queued":
        # Waiting for a semaphore slot — show queue message
        _q_hdr, _q_lang, _q_back = st.columns([4, 0.7, 1])
        with _q_hdr:
            st.markdown(t("queued_heading", company))
            st.caption(t("queued_caption"))
        with _q_lang:
            _lang_toggle("queued")
        with _q_back:
            st.markdown("")
            if st.button(t("back_to_form_btn"), key="back_form_queued"):
                st.session_state.phase = "form"
                st.rerun()
        st.info(t("queued_info"))
        elapsed_sec = time.time() - (job.get("start_time") or time.time())
        st.caption(t("waiting_caption", int(elapsed_sec)))
        time.sleep(5)
        st.rerun()

    else:
        # Still running — show live progress and poll
        _node_labels = _NODE_LABELS_KO if st.session_state.get("ui_lang") == "ko" else _NODE_LABELS_EN

        _run_hdr, _run_lang, _run_back, _run_hist = st.columns([4, 0.7, 1, 0.8])
        with _run_hdr:
            st.markdown(t("analyzing", company))
            st.caption(t("running_caption"))
        with _run_lang:
            _lang_toggle("running")
        with _run_back:
            st.markdown("")
            if st.button(t("back_to_form_btn"), key="back_form_running"):
                st.session_state.phase = "form"
                st.rerun()
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
        # Use set so feedback-loop reruns don't double-count weights
        unique_nodes = set(progress)
        completed_weight = sum(NODE_WEIGHTS.get(n, 0) for n in unique_nodes)
        total_weight     = sum(NODE_WEIGHTS.values())
        pct = min(completed_weight / total_weight, 1.0)  # cap at 100%

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
        _PHASE1_AGENTS = [
            "market_analysis", "competitor_analysis", "financial_analysis",
            "tech_analysis", "legal_regulatory", "team_analysis",
        ]
        _PHASE2_AGENTS = ["ra_synthesis", "risk_assessment"]

        for node in progress:
            # Skip non-node entries (critique_router:pass, budget_cap:*, etc.)
            if ":" in node:
                route_label = node.split(":", 1)[1]
                st.write(f"↳ {route_label}")
                continue

            label = _node_labels.get(node, node.replace("_", " ").title())
            # Show per-phase cost for parallel steps
            if node == "phase1_parallel":
                phase_cost = sum(token_usage.get(a, {}).get("cost_usd", 0) for a in _PHASE1_AGENTS)
                st.write(f"✓ {label}  —  ${phase_cost:.4f}")
            elif node == "phase2_parallel":
                phase_cost = sum(token_usage.get(a, {}).get("cost_usd", 0) for a in _PHASE2_AGENTS)
                st.write(f"✓ {label}  —  ${phase_cost:.4f}")
            elif node not in ("input_processor", "phase1_aggregator", "phase2_aggregator", "phase1_restart"):
                node_cost = token_usage.get(node, {}).get("cost_usd", 0)
                if node_cost:
                    st.write(f"✓ {label}  —  ${node_cost:.4f}")
                else:
                    st.write(f"✓ {label}")
            else:
                st.write(f"✓ {label}")

        # ── Current step spinner ───────────────────────────────────────────
        # Map: after this node completes, what runs next?
        _NEXT_STEP = {
            "input_processor":    "phase1_parallel",
            "phase1_parallel":    "phase1_aggregator",
            "phase1_aggregator":  "phase2_parallel",
            "phase2_parallel":    "strategic_insight",
            "strategic_insight":  "phase2_aggregator",
            "phase2_aggregator":  "review_agent",
            "review_agent":       "critique_agent",
            "critique_agent":     "dd_questions",       # default if pass
            "selective_rerun":    "review_agent",       # second review
            "phase1_restart":     "phase1_parallel",    # full restart
            "dd_questions":       "report_structure",
            "report_structure":   "report_writer",
        }
        last_real = ""
        for n in reversed(progress):
            if ":" not in n:  # skip critique_router:conditional etc
                last_real = n
                break
        next_node = _NEXT_STEP.get(last_real, "")
        if next_node and next_node in _node_labels:
            st.write(f"⏳ {_node_labels[next_node]}…")
        elif last_real == "report_writer":
            st.write("⏳ Generating documents…")
        else:
            st.write("⏳ Processing…")

        # Poll every 3 seconds
        time.sleep(3)
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# SCREEN 3 — RESULTS
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.phase == "results":
    _viewing = st.session_state.viewing_job or ""
    _job_data = st.session_state.results.get(_viewing, {})
    result:  dict = _job_data.get("result") or {}
    _pdf_bytes_result: bytes = _job_data.get("pdf_bytes") or b""
    company: str  = _job_data.get("company") or st.session_state.company
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

    _cname = company.replace(" ", "_")
    col_dl, col_pptx, col_docx, col_reset, col_hist = st.columns([1, 1, 1, 1, 1])
    with col_dl:
        if _pdf_bytes_result:
            st.download_button(
                label="⬇️ PDF",
                data=_pdf_bytes_result,
                file_name=f"due_diligence_{_cname}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )
    with col_pptx:
        _pptx_storage = _job_data.get("pptx_path") or ""
        if _pptx_storage:
            _pptx_bytes = download_file(_pptx_storage)
            if _pptx_bytes:
                st.download_button(
                    label="⬇️ PPTX",
                    data=_pptx_bytes,
                    file_name=f"due_diligence_{_cname}.pptx",
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    use_container_width=True,
                )
    with col_docx:
        _docx_storage = _job_data.get("docx_path") or ""
        if _docx_storage:
            _docx_bytes = download_file(_docx_storage)
            if _docx_bytes:
                st.download_button(
                    label="⬇️ DOCX",
                    data=_docx_bytes,
                    file_name=f"due_diligence_{_cname}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )
    with col_reset:
        if st.button(t("analyze_another_btn"), use_container_width=True):
            if _viewing in st.session_state.active_jobs:
                st.session_state.active_jobs.remove(_viewing)
            st.session_state.viewing_job = None
            st.session_state.phase = "form"
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

    # ── Agent Outputs ─────────────────────────────────────────────────────────
    _ao = _job_data.get("agent_outputs") or {}
    if _ao:
        st.divider()
        st.markdown(f"### {t('agent_outputs_heading')}")
        _render_agent_outputs(_ao, st.session_state.get("ui_lang", "en"))


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

    # Check if any active job is still running
    _back_label = t("back_btn")
    _back_phase = "form"
    _viewing = st.session_state.get("viewing_job")
    if _viewing and _viewing in st.session_state.active_jobs:
        _vj = read_job(_viewing)
        if _vj.get("status") in ("running", "queued"):
            _back_label = t("back_running_btn")
            _back_phase = "running"
    if st.button(_back_label):
        st.session_state.phase = _back_phase
        st.rerun()
    st.divider()

    history = load_history()

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
            col_name, col_rec, col_date, col_dl, col_view = st.columns([2.5, 1, 1.5, 0.8, 0.8])
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
                    storage_path = entry.get("pdf_path", "")
                    if storage_path:
                        try:
                            pdf_bytes = download_pdf(storage_path)
                            if pdf_bytes:
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
            with col_view:
                if st.button(t("view_details_btn"), key=f"view_{job_id}", use_container_width=True):
                    # Load full job from Supabase and navigate to results screen
                    _hist_job = read_job(job_id)
                    _hist_pdf = pdf_bytes or b""
                    st.session_state.results[job_id] = {
                        "result": {
                            "final_report":   _hist_job.get("final_report", ""),
                            "recommendation": _hist_job.get("recommendation", "WATCH"),
                            "token_usage":    _hist_job.get("token_usage", {}),
                        },
                        "pdf_bytes": _hist_pdf,
                        "pptx_path": _hist_job.get("pptx_path", ""),
                        "docx_path": _hist_job.get("docx_path", ""),
                        "company": _hist_job.get("company") or entry.get("company", ""),
                        "agent_outputs": _hist_job.get("agent_outputs") or {},
                    }
                    st.session_state.viewing_job = job_id
                    st.session_state.phase = "results"
                    st.rerun()
            st.divider()
