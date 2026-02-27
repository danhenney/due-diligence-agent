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

from config import REPORTS_DIR, validate_config

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
    docs: list[str] = typer.Option(
        [], "--docs", "-d", help="Path(s) to uploaded PDF documents.", show_default=False
    ),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file path for the memo."),
    no_checkpoint: bool = typer.Option(False, "--no-checkpoint", help="Disable SQLite checkpointing."),
    thread_id: str | None = typer.Option(
        None, "--thread-id", help="Resume a prior run using its thread ID."
    ),
):
    """Run full multi-agent due diligence on a company."""
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

    run_id = thread_id or str(uuid.uuid4())

    console.print()
    console.print(
        Panel.fit(
            f"[bold]Due Diligence:[/bold] {company}\n"
            f"[dim]Thread ID: {run_id}[/dim]",
            title="[bold blue]Multi-Agent Investment Analysis[/bold blue]",
            border_style="blue",
        )
    )
    console.print()

    # ── Import graph (deferred to avoid slow startup) ──────────────────────
    from graph.workflow import build_graph

    graph = build_graph(use_checkpointing=not no_checkpoint)
    config = {"configurable": {"thread_id": run_id}}

    # ── Run the graph with progress display ───────────────────────────────
    final_state = None
    phase_messages = {
        "input_processor": "Initializing analysis...",
        "phase1_parallel": "Phase 1: Running specialist agents in parallel (Financial, Market, Legal, Management, Tech)...",
        "phase1_aggregator": "Phase 1 complete. Aggregating...",
        "phase2_parallel": "Phase 2: Building thesis (Bull Case, Bear Case, Valuation, Red Flags)...",
        "phase2_aggregator": "Phase 2 complete. Aggregating...",
        "fact_checker": "Phase 3: Fact-checking all claims...",
        "stress_test": "Phase 3: Running stress tests...",
        "completeness": "Phase 3: Checking completeness...",
        "final_report_agent": "Phase 4: Generating Investment Memo...",
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
    recommendation = final_state.get("recommendation", "WATCH")
    rec_color = RECOMMENDATION_COLORS.get(recommendation, "white")
    final_memo = final_state.get("final_report", "")

    console.print()
    console.print(
        Panel.fit(
            f"[bold {rec_color}]{recommendation}[/bold {rec_color}]",
            title="[bold]Final Recommendation[/bold]",
            border_style=rec_color,
        )
    )
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
