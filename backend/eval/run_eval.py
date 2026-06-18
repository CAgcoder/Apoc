"""Orchestrate the fusion ablation: load -> score -> table -> report.md."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import designs, metrics


def evaluate_run(run_dir: Path | str, *, brief_slug: str) -> dict[str, dict[str, Any]]:
    """Objective four-way scores for one run. No LLM, no network."""
    contestants = designs.load_contestants(run_dir)
    return {name: metrics.objective_scores(design) for name, design in contestants.items()}


def render_report(rows: dict[str, dict[str, dict[str, Any]]], out_path: Path | str) -> None:
    """rows = {brief_slug: {contestant: {metric: value}}} -> markdown table."""
    out_path = Path(out_path)
    lines = ["# APoc Fusion Ablation — Results", ""]
    for brief, per_contestant in rows.items():
        lines.append(f"## {brief}")
        metric_names = sorted({m for s in per_contestant.values() for m in s})
        lines.append("| contestant | " + " | ".join(metric_names) + " |")
        lines.append("|" + "---|" * (len(metric_names) + 1))
        for contestant, scores in per_contestant.items():
            cells = " | ".join(str(scores.get(m, "")) for m in metric_names)
            lines.append(f"| {contestant} | {cells} |")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:  # pragma: no cover - CLI glue
    import argparse

    from app import config

    parser = argparse.ArgumentParser(description="Run the fusion ablation eval")
    parser.add_argument("--runs", nargs="+", required=True, help="run dirs (one per brief)")
    parser.add_argument("--slugs", nargs="+", required=True, help="brief slug per run dir")
    parser.add_argument("--out", default=str(Path(config.RUNS_DIR).parent / "eval" / "report.md"))
    args = parser.parse_args()

    rows = {
        slug: evaluate_run(run, brief_slug=slug)
        for run, slug in zip(args.runs, args.slugs)
    }
    render_report(rows, args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":  # pragma: no cover
    main()
