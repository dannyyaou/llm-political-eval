"""Console, JSON, and Markdown report generation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from .scoring import BenchmarkResult

AREA_LABELS = {
    "economy_taxation": "Economy & Taxation",
    "healthcare": "Healthcare",
    "immigration": "Immigration",
    "environment_climate": "Environment & Climate",
    "gun_weapons": "Gun Policy / Weapons",
    "abortion_reproductive": "Abortion & Reproductive Rights",
    "criminal_justice": "Criminal Justice",
    "education": "Education",
    "foreign_policy": "Foreign Policy & Military",
    "tech_privacy": "Technology & Privacy",
    "social_welfare": "Social Welfare & Inequality",
    "lgbtq_social": "LGBTQ+ & Social Issues",
    "free_speech": "Free Speech & Censorship",
    "geopolitical_sovereignty": "Geopolitical Sovereignty",
}


def _sign_str(val: float) -> str:
    """Format a score with explicit sign."""
    return f"{val:+.3f}"


def print_console_report(result: BenchmarkResult) -> None:
    """Print a rich console table summary."""
    console = Console()

    console.print()
    console.print(f"[bold]Political Stance Benchmark[/bold] — {result.model_id}")
    console.print(f"Quadrant: [bold]{result.quadrant}[/bold]")
    console.print(
        f"Overall: Economic {_sign_str(result.overall.economic)} | "
        f"Social {_sign_str(result.overall.social)}"
    )
    console.print(
        f"Questions: {result.total_questions} | "
        f"Refused: {result.total_refused} | "
        f"Errors: {result.total_errors}"
    )
    console.print()

    # Per-area table
    table = Table(title="Per-Area Scores")
    table.add_column("Area", style="cyan", min_width=28)
    table.add_column("Economic", justify="right")
    table.add_column("Social", justify="right")
    table.add_column("Scored", justify="right")
    table.add_column("Refused", justify="right")

    for code, label in AREA_LABELS.items():
        ar = result.areas.get(code)
        if not ar:
            continue
        table.add_row(
            label,
            _sign_str(ar.scores.economic),
            _sign_str(ar.scores.social),
            str(ar.n_scored),
            str(ar.n_refused),
        )

    console.print(table)

    # Format comparison
    console.print()
    fmt_table = Table(title="Structured vs Open-Ended (per area)")
    fmt_table.add_column("Area", style="cyan", min_width=28)
    fmt_table.add_column("Struct Econ", justify="right")
    fmt_table.add_column("Struct Soc", justify="right")
    fmt_table.add_column("Open Econ", justify="right")
    fmt_table.add_column("Open Soc", justify="right")

    for code, label in AREA_LABELS.items():
        ar = result.areas.get(code)
        if not ar:
            continue
        # Average likert + mc as "structured"
        struct_econ_vals = []
        struct_soc_vals = []
        for fmt in ("likert", "multiple_choice"):
            if fmt in ar.format_scores:
                struct_econ_vals.append(ar.format_scores[fmt].economic)
                struct_soc_vals.append(ar.format_scores[fmt].social)
        oe = ar.format_scores.get("open_ended")

        s_econ = sum(struct_econ_vals) / len(struct_econ_vals) if struct_econ_vals else 0.0
        s_soc = sum(struct_soc_vals) / len(struct_soc_vals) if struct_soc_vals else 0.0

        fmt_table.add_row(
            label,
            _sign_str(s_econ),
            _sign_str(s_soc),
            _sign_str(oe.economic) if oe else "n/a",
            _sign_str(oe.social) if oe else "n/a",
        )

    console.print(fmt_table)

    # Region comparison
    console.print()
    reg_table = Table(title="US vs Global (per area)")
    reg_table.add_column("Area", style="cyan", min_width=28)
    reg_table.add_column("US Econ", justify="right")
    reg_table.add_column("US Soc", justify="right")
    reg_table.add_column("Global Econ", justify="right")
    reg_table.add_column("Global Soc", justify="right")

    for code, label in AREA_LABELS.items():
        ar = result.areas.get(code)
        if not ar:
            continue
        us = ar.region_scores.get("us")
        gl = ar.region_scores.get("global")
        reg_table.add_row(
            label,
            _sign_str(us.economic) if us else "n/a",
            _sign_str(us.social) if us else "n/a",
            _sign_str(gl.economic) if gl else "n/a",
            _sign_str(gl.social) if gl else "n/a",
        )

    console.print(reg_table)
    console.print()


def save_json_report(result: BenchmarkResult, output_dir: Path) -> Path:
    """Save the full result as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{result.model_id.replace(':', '_')}_{ts}.json"
    path = output_dir / filename
    with open(path, "w") as f:
        json.dump(result.to_dict(), f, indent=2)
    return path


def save_markdown_report(result: BenchmarkResult, output_dir: Path) -> Path:
    """Save a Markdown summary report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{result.model_id.replace(':', '_')}_{ts}.md"
    path = output_dir / filename

    lines = [
        f"# Political Stance Benchmark: {result.model_id}",
        "",
        f"**Quadrant:** {result.quadrant}  ",
        f"**Economic:** {_sign_str(result.overall.economic)} | "
        f"**Social:** {_sign_str(result.overall.social)}  ",
        f"**Questions:** {result.total_questions} | "
        f"**Refused:** {result.total_refused} | "
        f"**Errors:** {result.total_errors}",
        "",
        "## Per-Area Scores",
        "",
        "| Area | Economic | Social | Scored | Refused |",
        "|------|----------|--------|--------|---------|",
    ]

    for code, label in AREA_LABELS.items():
        ar = result.areas.get(code)
        if not ar:
            continue
        lines.append(
            f"| {label} | {_sign_str(ar.scores.economic)} | "
            f"{_sign_str(ar.scores.social)} | {ar.n_scored} | {ar.n_refused} |"
        )

    lines.extend(["", f"*Generated: {ts}*", ""])

    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path
