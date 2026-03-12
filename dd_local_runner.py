#!/usr/bin/env python3
"""DD Local Runner -Zero-cost 14-agent due diligence via Claude Code CLI.

Each agent runs as an independent `claude -p` call. No context window limits.
Results persist to disk -reruns skip completed agents automatically.

Usage:
    python dd_local_runner.py "Upstage" --url https://upstage.ai --lang Korean --docs a.pdf c.pdf
    python dd_local_runner.py "Apple" --url https://apple.com --batch-size 6
"""
from __future__ import annotations

import argparse
import concurrent.futures
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows (prevents cp949 encoding errors)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Config ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
OUTPUT_BASE = ROOT / "dd-local-outputs"
AGENT_TIMEOUT = 1200  # 20 min per agent
DEFAULT_BATCH = 3     # Phase 1 parallel agents

AGENT_PY: dict[str, Path] = {
    "market_analysis":     ROOT / "agents/phase1/market_analysis.py",
    "competitor_analysis": ROOT / "agents/phase1/competitor_analysis.py",
    "financial_analysis":  ROOT / "agents/phase1/financial_analysis.py",
    "tech_analysis":       ROOT / "agents/phase1/tech_analysis.py",
    "legal_regulatory":    ROOT / "agents/phase1/legal_regulatory.py",
    "team_analysis":       ROOT / "agents/phase1/team_analysis.py",
    "ra_synthesis":        ROOT / "agents/phase2/ra_synthesis.py",
    "risk_assessment":     ROOT / "agents/phase2/risk_assessment.py",
    "strategic_insight":   ROOT / "agents/phase2/strategic_insight.py",
    "review_agent":        ROOT / "agents/phase3/review_agent.py",
    "critique_agent":      ROOT / "agents/phase3/critique_agent.py",
    "dd_questions":        ROOT / "agents/phase3/dd_questions.py",
    "report_structure":    ROOT / "agents/phase4/report_structure.py",
    "report_writer":       ROOT / "agents/phase4/report_writer.py",
}

# Agents that need web search + bash (rest get Write/Read/Bash only)
SEARCH_AGENTS = {
    "market_analysis", "competitor_analysis", "financial_analysis",
    "tech_analysis", "legal_regulatory", "team_analysis",
    "risk_assessment", "review_agent",
}


def log(msg: str) -> None:
    try:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
    except UnicodeEncodeError:
        print(f"[{time.strftime('%H:%M:%S')}] {msg.encode('utf-8', errors='replace').decode('utf-8')}", flush=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_system_prompt(agent_name: str) -> str:
    """Load system prompt from the agent's .md file."""
    md_path = AGENT_PY[agent_name].with_suffix(".md")
    if not md_path.exists():
        raise ValueError(f"No system prompt file: {md_path}")
    return md_path.read_text(encoding="utf-8").strip()


def run_claude(prompt: str, agent_name: str, timeout: int = AGENT_TIMEOUT) -> str:
    """Run claude CLI in print mode. Returns stdout."""
    tools = (
        ["WebSearch", "Bash", "Write", "Read"]
        if agent_name in SEARCH_AGENTS
        else ["Write", "Read", "Bash"]
    )
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("CLAUDECODE", None)  # allow nested claude calls
    # Windows needs .cmd extension for npm-installed CLIs
    claude_cmd = "claude.cmd" if sys.platform == "win32" else "claude"
    cmd = [
        claude_cmd, "-p",
        "--no-session-persistence",
        "--allowedTools", ",".join(tools),
    ]
    try:
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", cwd=str(ROOT), env=env,
        )
        if proc.returncode != 0:
            log(f"    warn: {agent_name} exit={proc.returncode}")
            if proc.stderr:
                log(f"    stderr: {proc.stderr[:300]}")
        return proc.stdout
    except subprocess.TimeoutExpired:
        log(f"    timeout: {agent_name} exceeded {timeout}s")
        return ""
    except Exception as e:
        log(f"    error: {agent_name}: {e}")
        return ""


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError, OSError):
        return {}


def detect_public(company: str) -> dict:
    """Check if company is publicly traded via yfinance."""
    script = f"""import yfinance as yf, json
try:
    t = yf.Ticker('{company}')
    info = t.info
    if info.get('marketCap'):
        print(json.dumps({{'is_public': True, 'ticker': '{company}'}}))
    else:
        print(json.dumps({{'is_public': False, 'ticker': None}}))
except:
    print(json.dumps({{'is_public': False, 'ticker': None}}))"""
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        r = subprocess.run(
            ["python", "-c", script],
            capture_output=True, text=True, timeout=30, encoding="utf-8", env=env,
        )
        return json.loads(r.stdout.strip())
    except Exception:
        return {"is_public": False, "ticker": None}


def compact_output(data: dict, max_chars: int = 1500) -> str:
    """Compact an agent output for phase-to-phase handoff."""
    parts = []
    for key in ("summary", "red_flags", "strengths", "confidence_score"):
        if key in data:
            val = data[key]
            if isinstance(val, list):
                val = val[:5]
            parts.append(f"{key}: {val}")
    return "\n".join(parts)[:max_chars]


# ── Prompt building blocks ────────────────────────────────────────────────────

def _lang(lang: str) -> str:
    if lang.lower() == "english":
        return ""
    return f"\nWrite your ENTIRE response in {lang}. Also search in {lang}."


def _docs(docs: list[str]) -> str:
    if not docs:
        return ""
    lines = ["\n## Documents (AUTHORITATIVE -exact figures override web estimates)"]
    for d in docs:
        lines.append(
            f'Read via Bash: `python -c "import fitz; doc=fitz.open(\'{d}\'); '
            f'[print(doc[i].get_text()[:3000]) for i in range(min(len(doc),6))]"`'
        )
    return "\n".join(lines)


def _tools(agent: str, company: str, is_public: bool) -> str:
    """Per-agent tool instructions matching executor.py."""
    b = []
    if agent in SEARCH_AGENTS:
        b.append(
            "Tavily (via Bash, higher quality than WebSearch):\n"
            '`python -c "from tavily import TavilyClient;import os,json;'
            "c=TavilyClient(api_key=os.environ['TAVILY_API_KEY']);"
            "print(json.dumps(c.search('QUERY',search_depth='advanced',max_results=5,"
            'include_answer=True),ensure_ascii=False))"`\n'
            "For news: add topic='news', days=14.\n"
            "Also use WebSearch (free, built-in) for quick lookups."
        )
    if agent in ("market_analysis", "competitor_analysis", "review_agent"):
        b.append(
            'yfinance (public comps): `python -c "import yfinance as yf,json;'
            "t=yf.Ticker('TICKER');print(json.dumps({k:str(v) for k,v in t.info.items()}))\"`"
        )
    if agent == "financial_analysis":
        if is_public:
            b.append(
                'yfinance: `python -c "import yfinance as yf,json;t=yf.Ticker(\'TICKER\');'
                'print(t.financials.to_json())"`\n'
                'Balance sheet: `python -c "import yfinance as yf;t=yf.Ticker(\'TICKER\');'
                'print(t.balance_sheet.to_json())"`'
            )
        else:
            b.append(f"PRIVATE company -no yfinance for {company}. Use DART + docs + web.")
        b.append(
            f'DART: `python -c "import OpenDartReader,json,os;'
            f"d=OpenDartReader(os.environ.get('DART_API_KEY',''));"
            f"print(d.finstate('{company}',2024).to_json(force_ascii=False))\"`"
        )
        b.append(
            'SEC EDGAR: `python -c "from edgar import Company;'
            "c=Company('NAME');print(c.get_filings(form='10-K').latest(1))\"`"
        )
    if agent == "legal_regulatory":
        b.append(
            f'DART filings: `python -c "import OpenDartReader,json,os;'
            f"d=OpenDartReader(os.environ.get('DART_API_KEY',''));"
            f"print(d.list('{company}',kind='A'))\"`"
        )
    if agent == "tech_analysis":
        b.append(
            f'GitHub: `python -c "import requests,json;'
            f"r=requests.get('https://api.github.com/search/repositories?q={company}');"
            f'print(json.dumps(r.json(),indent=2))"`\n'
            f'Patents: `python -c "import requests,json;'
            f"r=requests.post('https://api.patentsview.org/patents/query',"
            f"json={{'q':{{'_text_any':{{'patent_abstract':'{company}'}}}},"
            f"'f':['patent_number','patent_title','patent_date'],'o':{{'per_page':10}}}});"
            f'print(json.dumps(r.json(),indent=2))"`'
        )
    if agent in ("market_analysis", "tech_analysis"):
        b.append(
            'Google Trends: `python -c "from pytrends.request import TrendReq;'
            "pt=TrendReq();pt.build_payload(['KEYWORD']);print(pt.interest_over_time().to_json())\"`"
        )
    return "\n".join(b) if b else "WebSearch and Bash available."


QUALITY_RULES = """## Research Quality Rules (MANDATORY)
1. SEARCH BUDGET: 4-6 calls max (WebSearch + Tavily combined). Plan before searching.
2. CROSS-VERIFY: Key claims need 3+ independent sources. 1 source = low confidence.
3. [DATA]/[INFERENCE]: Prefix every major statement. [DATA]=from source. [INFERENCE]=your analysis.
4. RECENCY: Prefer newest. >6mo = re-verify. Newer wins on conflict.
5. Use actual numbers, not vague summaries."""


# ── Phase prompt builders ─────────────────────────────────────────────────────

def prompt_phase1(agent: str, info: dict, docs: list[str]) -> str:
    sp = extract_system_prompt(agent)
    out = info["output_dir"] / f"{agent}.json"
    return f"""## Role
{sp}

## Company
- Name: {info['name']}
- URL: {info.get('url', 'N/A')}
- Public: {info['is_public']} | Ticker: {info.get('ticker', 'None')}

## Tools
{_tools(agent, info['name'], info['is_public'])}
{_docs(docs)}
{QUALITY_RULES}

## Output
Write your complete JSON to: {out}
Use the Write tool. Include ALL fields from the schema above.
{_lang(info['lang'])}"""


def prompt_aggregator(phase1_outputs: dict, output_path: Path, lang: str) -> str:
    summaries = []
    for name, data in phase1_outputs.items():
        summaries.append(f"### {name}\n{compact_output(data, 1200)}")
    ctx = "\n\n".join(summaries)
    return f"""Analyze these 6 due diligence reports and extract cross-pollination signals.

{ctx}

Output JSON with EXACTLY this structure:
{{
  "phase1_context": "<compact 2-3 paragraph summary>",
  "settled_claims": ["<5-8 facts MULTIPLE agents agree on, with numbers>"],
  "tensions": ["<3-5 CONTRADICTIONS between agents, specific>"],
  "gaps": ["<2-3 important unanswered questions>"]
}}

Write to: {output_path}
{_lang(lang)}"""


def prompt_phase2(agent: str, info: dict, phase1_ctx: str, agg: dict,
                  docs: list[str], extra: str = "") -> str:
    sp = extract_system_prompt(agent)
    out = info["output_dir"] / f"{agent}.json"

    claims = "\n".join(f"- {c}" for c in agg.get("settled_claims", []))
    tensions = "\n".join(f"- {t}" for t in agg.get("tensions", []))
    gaps = "\n".join(f"- {g}" for g in agg.get("gaps", []))

    additional = ""
    if agent == "risk_assessment":
        additional = "\nMUST output `unresolved_objections`: 2-3 hardest kill-criteria, each with `kill_potential`: high/medium/low."
    elif agent == "strategic_insight":
        additional = "\nMUST output `framings`: 2-3 distinct investment scenarios. Pick strongest, name runners-up."

    return f"""## Role
{sp}

## Company: {info['name']}

## Phase 1 Summary
{phase1_ctx[:6000]}

## Cross-Pollination
=== SETTLED CLAIMS (build on these) ===
{claims}
=== TENSIONS (resolve these) ===
{tensions}
=== GAPS (fill if possible) ===
{gaps}
{additional}

## Tools
{_tools(agent, info['name'], info['is_public'])}
{_docs(docs) if agent == 'risk_assessment' else ''}
{extra}

## Output
Write JSON to: {out}
{_lang(info['lang'])}"""


def prompt_phase3(agent: str, info: dict, all_outputs: dict) -> str:
    sp = extract_system_prompt(agent)
    out = info["output_dir"] / f"{agent}.json"

    ctx_parts = [f"### {n}\n{compact_output(d, 800)}" for n, d in all_outputs.items()]
    ctx = "\n\n".join(ctx_parts)[:8000]

    extra = ""
    if agent == "review_agent":
        extra = "\nREALITY CHECK: If narrative is heavily bullish/bearish, search for CONTRADICTING data."
    elif agent == "critique_agent":
        extra = "\nScore 5 criteria 1-10: logic, completeness, accuracy, narrative_bias, insight_effectiveness."

    return f"""## Role
{sp}

## Company: {info['name']}

## All Prior Analysis
{ctx}
{extra}

## Tools
{_tools(agent, info['name'], info['is_public'])}

## Output
Write JSON to: {out}
{_lang(info['lang'])}"""


def prompt_phase4(agent: str, info: dict, all_outputs: dict) -> str:
    sp = extract_system_prompt(agent)
    is_writer = agent == "report_writer"
    out = info["output_dir"] / ("report.md" if is_writer else f"{agent}.json")

    keys = ["strategic_insight", "risk_assessment", "ra_synthesis",
            "review_agent", "dd_questions", "critique_agent"]
    if is_writer:
        keys.append("report_structure")

    ctx_parts = []
    for k in keys:
        if k in all_outputs:
            ctx_parts.append(f"### {k}\n{json.dumps(all_outputs[k], ensure_ascii=False, indent=2)[:2500]}")
    ctx = "\n\n".join(ctx_parts)[:8000]

    return f"""## Role
{sp}

## Company: {info['name']}

## Analysis Context
{ctx}

## Output
Write to: {out}
{_lang(info['lang'])}"""


# ── Execution ─────────────────────────────────────────────────────────────────

def run_agent(name: str, prompt: str, output_dir: Path) -> dict:
    """Run one agent. Skip if output file already exists (resume)."""
    out_file = output_dir / f"{name}.json"
    if out_file.exists() and out_file.stat().st_size > 10:
        log(f"  >> {name} -cached, skipping")
        return load_json(out_file)

    log(f"  >> {name} -starting...")
    t0 = time.time()
    run_claude(prompt, name)
    dt = time.time() - t0

    result = load_json(out_file)
    status = "done" if result else "NO OUTPUT"
    log(f"  << {name} -{status} ({dt:.0f}s)")
    return result


def run_batch(pairs: list[tuple[str, str]], output_dir: Path) -> dict:
    """Run agents in parallel."""
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(pairs)) as pool:
        futs = {pool.submit(run_agent, n, p, output_dir): n for n, p in pairs}
        for f in concurrent.futures.as_completed(futs):
            name = futs[f]
            try:
                results[name] = f.result()
            except Exception as e:
                log(f"  !! {name} exception: {e}")
                results[name] = {}
    return results


# ── Phase runners ─────────────────────────────────────────────────────────────

def phase1(info: dict, docs: list[str], batch_size: int) -> dict:
    log("=" * 60)
    log("PHASE 1: Research (6 agents)")
    log("=" * 60)
    agents = ["market_analysis", "competitor_analysis", "financial_analysis",
              "tech_analysis", "legal_regulatory", "team_analysis"]
    all_results = {}
    for i in range(0, len(agents), batch_size):
        batch = agents[i:i + batch_size]
        log(f"  Batch {i // batch_size + 1}: {', '.join(batch)}")
        pairs = [(n, prompt_phase1(n, info, docs)) for n in batch]
        all_results.update(run_batch(pairs, info["output_dir"]))
    return all_results


def aggregator(info: dict, p1: dict) -> dict:
    log("=" * 60)
    log("AGGREGATOR: Cross-Pollination")
    log("=" * 60)
    out_file = info["output_dir"] / "_aggregator.json"
    if out_file.exists() and out_file.stat().st_size > 10:
        log("  >> cached, skipping")
        return load_json(out_file)

    prompt = prompt_aggregator(p1, out_file, info["lang"])
    run_claude(prompt, "ra_synthesis")  # no search needed
    result = load_json(out_file)
    if result:
        log(f"  << done: {len(result.get('settled_claims', []))} claims, "
            f"{len(result.get('tensions', []))} tensions, {len(result.get('gaps', []))} gaps")
    else:
        log("  !! no output -using empty aggregator")
        result = {"phase1_context": "", "settled_claims": [], "tensions": [], "gaps": []}
    return result


def phase2(info: dict, phase1_ctx: str, agg: dict, docs: list[str]) -> dict:
    log("=" * 60)
    log("PHASE 2: Synthesis (3 agents)")
    log("=" * 60)
    results = {}

    # Parallel: ra_synthesis + risk_assessment
    pairs = [
        ("ra_synthesis", prompt_phase2("ra_synthesis", info, phase1_ctx, agg, docs)),
        ("risk_assessment", prompt_phase2("risk_assessment", info, phase1_ctx, agg, docs)),
    ]
    results.update(run_batch(pairs, info["output_dir"]))

    # Sequential: strategic_insight (needs ra + risk)
    ra = json.dumps(results.get("ra_synthesis", {}), ensure_ascii=False, indent=2)[:3000]
    risk = json.dumps(results.get("risk_assessment", {}), ensure_ascii=False, indent=2)[:3000]
    extra = f"\n## R&A Synthesis Output\n{ra}\n\n## Risk Assessment Output\n{risk}"
    prompt = prompt_phase2("strategic_insight", info, phase1_ctx, agg, docs, extra)
    results["strategic_insight"] = run_agent("strategic_insight", prompt, info["output_dir"])

    return results


def phase3(info: dict, all_out: dict) -> dict:
    log("=" * 60)
    log("PHASE 3: Review & Quality (3 agents)")
    log("=" * 60)
    results = {}

    # review_agent
    prompt = prompt_phase3("review_agent", info, all_out)
    results["review_agent"] = run_agent("review_agent", prompt, info["output_dir"])
    all_out["review_agent"] = results["review_agent"]

    # critique_agent
    prompt = prompt_phase3("critique_agent", info, all_out)
    results["critique_agent"] = run_agent("critique_agent", prompt, info["output_dir"])

    # Feedback loop check
    critique = results["critique_agent"]
    scores = critique.get("scores", critique.get("criteria_scores", {}))
    if isinstance(scores, dict) and scores:
        total = sum(v for v in scores.values() if isinstance(v, (int, float)))
        min_s = min(v for v in scores.values() if isinstance(v, (int, float)))
        if total >= 35 and min_s >= 7:
            log(f"  Critique PASS (total={total}, min={min_s})")
        elif min_s < 5 or total < 25:
            log(f"  Critique FAIL (total={total}, min={min_s}) -skipping restart for now")
        else:
            log(f"  Critique CONDITIONAL (total={total}, min={min_s})")
    else:
        log("  Critique scores not parseable -proceeding")

    # dd_questions
    all_out["critique_agent"] = results["critique_agent"]
    prompt = prompt_phase3("dd_questions", info, all_out)
    results["dd_questions"] = run_agent("dd_questions", prompt, info["output_dir"])

    return results


def phase4(info: dict, all_out: dict) -> dict:
    log("=" * 60)
    log("PHASE 4: Report Generation (2 agents)")
    log("=" * 60)
    results = {}

    # report_structure
    prompt = prompt_phase4("report_structure", info, all_out)
    results["report_structure"] = run_agent("report_structure", prompt, info["output_dir"])
    all_out["report_structure"] = results["report_structure"]

    # report_writer (output is .md not .json)
    report_file = info["output_dir"] / "report.md"
    if report_file.exists() and report_file.stat().st_size > 100:
        log("  >> report_writer -cached, skipping")
        results["report_writer"] = {"status": "cached"}
    else:
        log("  >> report_writer -starting...")
        t0 = time.time()
        prompt = prompt_phase4("report_writer", info, all_out)
        run_claude(prompt, "report_writer")
        dt = time.time() - t0
        if report_file.exists():
            log(f"  << report_writer -done ({dt:.0f}s)")
            results["report_writer"] = {"status": "done"}
        else:
            log(f"  !! report_writer -no output ({dt:.0f}s)")

    return results


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="DD Local Runner -14-agent due diligence pipeline via Claude Code CLI"
    )
    parser.add_argument("company", help="Company name")
    parser.add_argument("--url", default="", help="Company website URL")
    parser.add_argument("--lang", default="English", help="Output language (Korean, English, etc.)")
    parser.add_argument("--docs", nargs="*", default=[], help="PDF document paths for analysis")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH,
                        help=f"Phase 1 parallel batch size (default {DEFAULT_BATCH}, max 6)")
    parser.add_argument("--force", action="store_true",
                        help="Force re-run all agents (delete existing outputs)")
    args = parser.parse_args()

    # Setup output directory
    slug = re.sub(r"[^\w\-]", "_", args.company)
    output_dir = OUTPUT_BASE / slug
    if args.force and output_dir.exists():
        import shutil
        shutil.rmtree(output_dir)
        log(f"Cleared {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Verify docs
    docs: list[str] = []
    for d in args.docs:
        p = Path(d).resolve()
        if p.exists():
            docs.append(str(p))
        else:
            log(f"WARNING: doc not found: {d}")

    # Detect public/private
    log(f"Company: {args.company}")
    log("Detecting public/private...")
    pub = detect_public(args.company)
    log(f"  is_public={pub['is_public']}, ticker={pub.get('ticker')}")

    info = {
        "name": args.company,
        "url": args.url,
        "lang": args.lang,
        "is_public": pub["is_public"],
        "ticker": pub.get("ticker"),
        "output_dir": output_dir,
    }

    t_start = time.time()

    # ── Phase 1 ───────────────────────────────────────────────────────────
    p1 = phase1(info, docs, args.batch_size)

    # ── Aggregator ────────────────────────────────────────────────────────
    agg = aggregator(info, p1)
    phase1_ctx = agg.get("phase1_context", "")

    # ── Phase 2 ───────────────────────────────────────────────────────────
    p2 = phase2(info, phase1_ctx, agg, docs)
    all_outputs = {**p1, **p2}

    # ── Phase 3 ───────────────────────────────────────────────────────────
    p3 = phase3(info, all_outputs)
    all_outputs.update(p3)

    # ── Phase 4 ───────────────────────────────────────────────────────────
    phase4(info, all_outputs)

    # ── Summary ───────────────────────────────────────────────────────────
    elapsed = time.time() - t_start
    log("")
    log("=" * 60)
    log(f"COMPLETE -{elapsed / 60:.1f} minutes")
    log(f"Output directory: {output_dir}")

    si = all_outputs.get("strategic_insight", {})
    log(f"Recommendation: {si.get('recommendation', si.get('investment_recommendation', 'N/A'))}")
    log(f"Confidence: {si.get('confidence_score', 'N/A')}")

    log("\nFiles:")
    for f in sorted(output_dir.iterdir()):
        log(f"  {f.name:30s} {f.stat().st_size:>8,} bytes")

    report = output_dir / "report.md"
    if report.exists():
        log(f"\n{'=' * 60}")
        log("REPORT (first 3000 chars):")
        log("=" * 60)
        print(report.read_text(encoding="utf-8")[:3000])


if __name__ == "__main__":
    main()
