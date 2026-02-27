"""Streamlit web UI for the Due Diligence Agent."""
import os
import shutil
import tempfile
import uuid

import streamlit as st

# Inject Streamlit Cloud secrets into os.environ so config.py's os.getenv() works.
# This is a no-op when running locally with a .env file.
try:
    for _k in ["GOOGLE_API_KEY", "TAVILY_API_KEY", "EDGAR_USER_AGENT"]:
        if _k in st.secrets and not os.environ.get(_k):
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass

from config import validate_config

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
</style>
""", unsafe_allow_html=True)

# ── API key check ─────────────────────────────────────────────────────────────
_missing = validate_config()
if _missing:
    st.error(
        f"**Missing API keys:** {', '.join(_missing)}\n\n"
        "Create a `.env` file in the project folder:\n"
        "```\nGOOGLE_API_KEY=...\nTAVILY_API_KEY=...\n```\n"
        "Free Google key → https://aistudio.google.com/app/apikey"
    )
    st.stop()

# ── Session state defaults ─────────────────────────────────────────────────────
for key, default in [
    ("phase", "form"),
    ("result", None),
    ("pdf_bytes", None),
    ("company", ""),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Node display labels (used in st.status) ───────────────────────────────────
NODE_LABELS = {
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

# ── Agent directory data ──────────────────────────────────────────────────────
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
                "sources": ["SEC EDGAR (10-K, 10-Q, 8-K)", "Web search", "Uploaded PDFs"],
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
                "sources": ["Web search", "News search", "Industry reports"],
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
                "sources": ["Web search", "News search", "Uploaded PDFs (legal docs)"],
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
                "sources": ["Web search", "News search", "GitHub (via web)", "Product reviews"],
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
                "sources": ["Web search (comps, M&A data)", "Phase 1 financial & market reports"],
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
                "sources": ["Phase 1–2 reports", "Bear case", "Red flags", "Fact-check output"],
            },
            {
                "icon": "📋",
                "name": "Completeness Checker",
                "role": "QA audit — identifies coverage gaps and rates decision readiness.",
                "methodology": [
                    "Scores coverage across 7 dimensions (0–1): financial, market, legal, management, tech, valuation, risk",
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
                    "Reads all Phase 1–3 outputs holistically",
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
        with st.expander("Methodology & Sources"):
            st.markdown("**How it works:**")
            for step in agent["methodology"]:
                st.markdown(f"- {step}")
            st.markdown("**Sources:**")
            tags = "".join(
                f"<span class='source-tag'>{s}</span>" for s in agent["sources"]
            )
            st.markdown(tags, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# SCREEN 1 — FORM
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.phase == "form":

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown("## 📊 Due Diligence Agent")
    st.caption("Submit a company → 13 AI agents analyze it in 4 phases → full investment memo + PDF")
    st.divider()

    # ── Two-column layout: form left, pipeline right ──────────────────────────
    col_form, col_pipeline = st.columns([1, 1.4], gap="large")

    with col_form:
        st.markdown("#### Submit a Company")
        company = st.text_input(
            "Company Name",
            placeholder="e.g. Apple, OpenAI, Stripe",
        )
        url = st.text_input(
            "Website URL *(optional)*",
            placeholder="https://example.com",
        )
        uploaded_files = st.file_uploader(
            "Supporting Documents *(optional)*",
            type=["pdf"],
            accept_multiple_files=True,
            help="Pitch decks, 10-Ks, annual reports, etc.",
        )
        st.markdown("")
        run = st.button(
            "🔍  Run Due Diligence",
            type="primary",
            disabled=not (company or "").strip(),
            use_container_width=True,
        )

    with col_pipeline:
        st.markdown("#### Agent Pipeline Flow")
        st.caption("Phases 1 & 2 run agents in parallel. Phase 3 is sequential (order matters).")
        st.graphviz_chart(PIPELINE_GRAPH, use_container_width=True)

    st.divider()

    # ── Agent Directory ───────────────────────────────────────────────────────
    st.markdown("#### Agent Directory")
    st.caption("Click any agent to see its methodology and data sources.")
    st.markdown("")

    tabs = st.tabs([p["label"] for p in AGENT_PHASES])
    for tab, phase in zip(tabs, AGENT_PHASES):
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
    if run and company.strip():
        tmp_dir = tempfile.mkdtemp()
        doc_paths: list[str] = []
        for f in (uploaded_files or []):
            dest = os.path.join(tmp_dir, f.name)
            with open(dest, "wb") as out:
                out.write(f.getbuffer())
            doc_paths.append(dest)

        st.session_state.company = company.strip()

        from graph.workflow import build_graph
        import pdf_report

        try:
            with st.status("Running due diligence analysis…", expanded=True) as status:
                graph = build_graph(use_checkpointing=False)
                initial_state = {
                    "company_name": company.strip(),
                    "company_url": url.strip() or None,
                    "uploaded_docs": doc_paths,
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

                merged: dict = {}
                for step in graph.stream(initial_state, stream_mode="updates"):
                    for node_name, output in step.items():
                        merged.update(output)
                        label = NODE_LABELS.get(
                            node_name, node_name.replace("_", " ").title()
                        )
                        st.write(f"✓ {label}")

                status.update(label="✅ Analysis complete!", state="complete")

            job_id = str(uuid.uuid4())
            pdf_path = pdf_report.generate_pdf(merged, job_id)
            with open(pdf_path, "rb") as fh:
                pdf_bytes = fh.read()

            st.session_state.result = merged
            st.session_state.pdf_bytes = pdf_bytes
            st.session_state.phase = "results"
            st.rerun()

        except Exception as exc:
            st.error(f"**Analysis failed:** {exc}")

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
# SCREEN 2 — RESULTS
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.phase == "results":
    result: dict = st.session_state.result or {}
    company: str = st.session_state.company
    rec = (result.get("recommendation") or "WATCH").upper()

    badge_class = {
        "INVEST": "invest-badge",
        "WATCH":  "watch-badge",
        "PASS":   "pass-badge",
    }.get(rec, "watch-badge")

    rec_desc = {
        "INVEST": "Strong investment opportunity with compelling fundamentals.",
        "WATCH":  "Interesting opportunity — monitor for further developments.",
        "PASS":   "Risks outweigh opportunities at this time.",
    }.get(rec, "")

    st.markdown(f"### {company}")
    st.markdown(f'<div class="{badge_class}">{rec}</div>', unsafe_allow_html=True)
    st.caption(rec_desc)
    st.divider()

    col_dl, col_reset, _ = st.columns([1, 1, 2])
    with col_dl:
        if st.session_state.pdf_bytes:
            st.download_button(
                label="⬇️  Download PDF Report",
                data=st.session_state.pdf_bytes,
                file_name=f"due_diligence_{company.replace(' ', '_')}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )
    with col_reset:
        if st.button("🔄  Analyze Another Company", use_container_width=True):
            st.session_state.phase = "form"
            st.session_state.result = None
            st.session_state.pdf_bytes = None
            st.rerun()

    st.divider()

    final_report: str = result.get("final_report") or ""
    if final_report.strip():
        st.markdown(final_report)
    else:
        st.info("No report content was generated.")
