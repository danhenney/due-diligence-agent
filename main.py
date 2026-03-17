"""CLI entry point for the Multi-Agent Due Diligence Tool."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from config import REPORTS_DIR, VALID_MODES, validate_config

app = typer.Typer(
    name="due-diligence",
    help="Multi-agent investment due diligence tool powered by Claude.",
    add_completion=False,
)
console = Console()

RECOMMENDATION_COLORS = {
    "INVEST": "green",
    "WATCH": "yellow",
    "PASS": "red",
}


@app.command()
def main(
    company: str = typer.Option(..., "--company", "-c", help="Company name to analyze."),
    url: str | None = typer.Option(None, "--url", "-u", help="Company website URL."),
    mode: str = typer.Option("due-diligence", "--mode", "-m", help=f"Analysis mode: {', '.join(VALID_MODES)}"),
    vs: str | None = typer.Option(None, "--vs", help="Benchmark comparison target (benchmark mode only)."),
    docs: list[str] = typer.Option(
        [], "--docs", "-d", help="Path(s) to uploaded PDF documents.", show_default=False
    ),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file path for the memo."),
    private: bool = typer.Option(False, "--private", help="Treat as a private company (skip yfinance/EDGAR)."),
    no_checkpoint: bool = typer.Option(False, "--no-checkpoint", help="Disable SQLite checkpointing."),
    thread_id: str | None = typer.Option(
        None, "--thread-id", help="Resume a prior run using its thread ID."
    ),
):
    """Run full multi-agent due diligence on a company."""
    # ── Mode validation ───────────────────────────────────────────────────
    if mode not in VALID_MODES:
        console.print(f"[red]Error:[/red] Invalid mode '{mode}'. Valid: {', '.join(VALID_MODES)}")
        raise typer.Exit(code=1)
    if mode == "benchmark" and not vs:
        console.print("[red]Error:[/red] --vs is required for benchmark mode.")
        raise typer.Exit(code=1)

    # ── Config validation ──────────────────────────────────────────────────
    missing = validate_config()
    if missing:
        console.print(
            f"[red]Error:[/red] Missing required environment variables: {', '.join(missing)}\n"
            "Copy [bold].env.example[/bold] to [bold].env[/bold] and fill in your API keys.",
            highlight=False,
        )
        raise typer.Exit(code=1)

    # ── Validate doc paths ─────────────────────────────────────────────────
    valid_docs = []
    for doc in docs:
        path = Path(doc)
        if not path.exists():
            console.print(f"[yellow]Warning:[/yellow] Document not found, skipping: {doc}")
        else:
            valid_docs.append(str(path.resolve()))

    # ── Build initial state ────────────────────────────────────────────────
    initial_state = {
        "company_name": company,
        "company_url": url,
        "uploaded_docs": valid_docs,
        "is_public": False if private else None,   # None = auto-detect
        "ticker": None,
        # Mode
        "mode": mode,
        "vs_company": vs,
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

    run_id = thread_id or str(uuid.uuid4())

    _MODE_TITLES = {
        "due-diligence": "Multi-Agent Investment Analysis",
        "industry-research": "Industry Research Analysis",
        "deep-dive": "Deep Dive Analysis",
        "benchmark": "Benchmark Comparison",
    }
    title = _MODE_TITLES.get(mode, "Analysis")
    subtitle = f"[bold]{title}:[/bold] {company}"
    if mode == "benchmark" and vs:
        subtitle += f" vs {vs}"

    console.print()
    console.print(
        Panel.fit(
            f"{subtitle}\n"
            f"[dim]Mode: {mode} | Thread ID: {run_id}[/dim]",
            title=f"[bold blue]{title}[/bold blue]",
            border_style="blue",
        )
    )
    console.print()

    # ── Import graph (deferred to avoid slow startup) ──────────────────────
    from graph.workflow import build_graph

    graph = build_graph(mode=mode, use_checkpointing=not no_checkpoint)
    config = {"configurable": {"thread_id": run_id}}

    # ── Run the graph with progress display ───────────────────────────────
    final_state = None
    phase_messages = {
        "input_processor": "Initializing analysis...",
        "phase1_parallel": "Phase 1: Running 6 research agents in parallel (Market, Competitors, Financial, Tech, Legal, Team)...",
        "phase1_aggregator": "Phase 1 complete. Aggregating context...",
        "phase2_parallel": "Phase 2: Synthesizing (R&A Synthesis + Risk Assessment in parallel)...",
        "strategic_insight": "Phase 2: Strategic Insight (rendering recommendation)...",
        "phase2_aggregator": "Phase 2 complete. Aggregating...",
        "review_agent": "Phase 3: Review Agent (verifying claims)...",
        "critique_agent": "Phase 3: Critique Agent (scoring 5 criteria)...",
        "selective_rerun": "Feedback Loop: Re-running weak agents...",
        "phase1_restart": "Feedback Loop: Full Phase 1 restart...",
        "dd_questions": "Phase 3: DD Questions (building questionnaire)...",
        "report_structure": "Phase 4: Designing report structure...",
        "report_writer": "Phase 4: Writing final report...",
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Starting...", total=None)

        try:
            for event in graph.stream(initial_state, config=config, stream_mode="updates"):
                for node_name in event:
                    msg = phase_messages.get(node_name, f"Running {node_name}...")
                    progress.update(task, description=msg)
                    # Capture latest state
                    final_state = event[node_name]

        except Exception as e:
            progress.update(task, description=f"[red]Error: {e}[/red]")
            console.print(f"\n[red]Pipeline error:[/red] {e}")
            if "--debug" in sys.argv:
                import traceback
                traceback.print_exc()
            raise typer.Exit(code=1)

    if not final_state:
        console.print("[red]No output produced.[/red]")
        raise typer.Exit(code=1)

    # ── Retrieve the final recommendation ─────────────────────────────────
    from config import MODE_REGISTRY as _MR
    has_rec = _MR.get(mode, {}).get("has_recommendation", False)
    recommendation = final_state.get("recommendation")
    final_memo = final_state.get("final_report", "")

    if has_rec and recommendation:
        rec_color = RECOMMENDATION_COLORS.get(recommendation, "white")
        console.print()
        console.print(
            Panel.fit(
                f"[bold {rec_color}]{recommendation}[/bold {rec_color}]",
                title="[bold]Final Recommendation[/bold]",
                border_style=rec_color,
            )
        )
        console.print()
    else:
        console.print()
        console.print(Panel.fit("[bold]Analysis Complete[/bold]", border_style="green"))
        console.print()

    # ── Print errors if any ────────────────────────────────────────────────
    errors = final_state.get("errors", [])
    if errors:
        console.print("[yellow]Warnings / non-fatal errors:[/yellow]")
        for err in errors:
            console.print(f"  [yellow]• {err}[/yellow]")
        console.print()

    # ── Render memo ────────────────────────────────────────────────────────
    if final_memo:
        console.print(Markdown(final_memo))

    # ── Save to file ───────────────────────────────────────────────────────
    if output:
        out_path = Path(output)
    else:
        reports_dir = Path(REPORTS_DIR)
        reports_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() else "_" for c in company)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = reports_dir / f"{safe_name}_{timestamp}.md"

    out_path.write_text(final_memo or "", encoding="utf-8")
    console.print(f"\n[green]Memo saved to:[/green] {out_path}")
    console.print(f"[dim]Thread ID (use --thread-id to resume): {run_id}[/dim]")


if __name__ == "__main__":
    app()
