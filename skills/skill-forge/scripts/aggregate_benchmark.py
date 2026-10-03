# Derived from Anthropic skill-creator (Apache-2.0); modified for OMP.
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Aggregate canonical iteration runs without inventing missing measurements."""

import argparse
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

METRICS = {"pass_rate": 2, "time_seconds": 1, "tokens": 0, "cost_usd": 4}


def load_json(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def calculate_stats(values):
    values = [v for v in values if v is not None]
    n = len(values)
    if not n:
        return dict(mean=None, stddev=0, min=None, max=None, n=0)
    mean = sum(values) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1)) if n > 1 else 0
    return dict(
        mean=round(mean, 4),
        stddev=round(sd, 4),
        min=round(min(values), 4),
        max=round(max(values), 4),
        n=n,
    )


def generate_benchmark(root, skill_name="", skill_path="", primary="with_skill", baseline=None):
    runs, models, warnings = [], set(), []
    for directory in sorted(root.glob("eval-*/*/run-*")):
        if not directory.is_dir():
            continue
        metadata = load_json(directory.parent.parent / "eval_metadata.json", {})
        run = load_json(directory / "run.json", {})
        timing = load_json(directory / "timing.json", {})
        grading = load_json(directory / "grading.json", {})
        summary = grading.get("summary", {})
        run_id = directory.relative_to(root).as_posix()
        notes = []
        if not grading:
            notes.append("Ungraded run")
        if run.get("outcome") != "completed":
            notes.append(
                f"Excluded from summary statistics — outcome: {run.get('outcome', 'unknown')}"
            )
        contaminated = directory.parent.name == "without_skill" and bool(
            run.get("contamination", {}).get("read_skill")
        )
        if contaminated:
            notes.append(
                "WARNING: CONTAMINATED BASELINE — read the skill; retained in statistics, not a clean control"
            )
        warnings.extend(f"{run_id}: {note}" for note in notes)
        for values in grading.get("user_notes_summary", {}).values():
            if isinstance(values, list):
                notes.extend(values)
        calls = timing.get("tool_calls")
        result = {key: summary.get(key) for key in ("pass_rate", "passed", "failed", "total")}
        result.update(
            time_seconds=timing.get("total_duration_seconds"),
            tokens=timing.get("total_tokens"),
            cost_usd=timing.get("cost_usd"),
            tool_calls=sum(calls.values()) if isinstance(calls, dict) else None,
            errors=timing.get("tool_errors"),
            outcome=run.get("outcome"),
        )
        runs.append(
            dict(
                run_id=run_id,
                eval_id=metadata.get("eval_id", run.get("eval_id")),
                eval_name=metadata.get("eval_name", run.get("eval_name")),
                configuration=directory.parent.name,
                run_number=int(directory.name.removeprefix("run-")),
                result=result,
                expectations=grading.get("expectations", []),
                notes=notes,
            )
        )
        runs[-1]["contaminated"] = contaminated
        if run.get("model_resolved"):
            models.add(run["model_resolved"])
        skill_name = skill_name or run.get("skill_name", "")
        skill_path = skill_path or run.get("skill_path") or ""
    configs = sorted({r["configuration"] for r in runs})
    baseline = baseline or ("old_skill" if "old_skill" in configs else "without_skill")
    summaries = {
        c: {
            m: calculate_stats(
                [
                    r["result"][m]
                    for r in runs
                    if r["configuration"] == c and r["result"]["outcome"] == "completed"
                ]
            )
            for m in METRICS
        }
        for c in configs
    }
    delta = {}
    for metric, digits in METRICS.items():
        a = summaries.get(primary, {}).get(metric, {}).get("mean")
        b = summaries.get(baseline, {}).get(metric, {}).get("mean")
        delta[metric] = None if a is None or b is None else f"{a - b:+.{digits}f}"
    summaries["delta"] = delta
    # Replicates are counted per eval/config, not the total number of evals.
    counts = {}
    for r in runs:
        key = (r["eval_id"], r["configuration"])
        counts[key] = counts.get(key, 0) + 1
    iteration = (
        int(root.name.removeprefix("iteration-"))
        if root.name.removeprefix("iteration-").isdigit()
        else None
    )
    benchmark = dict(
        metadata=dict(
            skill_name=skill_name,
            skill_path=skill_path,
            iteration=iteration,
            timestamp=datetime.now(timezone.utc).isoformat(),
            evals_run=sorted({r["eval_id"] for r in runs if r["eval_id"] is not None}),
            runs_per_configuration=max(counts.values(), default=0),
            primary=primary,
            baseline=baseline,
            models=sorted(models),
        ),
        runs=runs,
        run_summary=summaries,
        notes=[],
    )
    benchmark["metadata"]["excluded_runs"] = [
        r["run_id"] for r in runs if r["result"]["outcome"] != "completed"
    ]
    return benchmark, warnings


def markdown(benchmark, warnings):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = [
        "<!-- Derived from Anthropic skill-creator (Apache-2.0); modified for OMP. -->",
        "# Benchmark",
        "",
        "| Configuration | Pass rate | Time (s) | Tokens | Cost (USD) |",
        "|---|---:|---:|---:|---:|",
    ]
    for config, metrics in benchmark["run_summary"].items():
        cells = []
        for metric in METRICS:
            stat = metrics[metric]
            cells.append(
                ("—" if stat is None else stat)
                if config == "delta"
                else (
                    "—"
                    if stat["mean"] is None
                    else f"{stat['mean']} ± {stat['stddev']} (n={stat['n']})"
                )
            )
        lines.append("| " + " | ".join(map(cell, [config, *cells])) + " |")
    lines.extend(
        [
            "",
            "Delta = primary − baseline: "
            + cell(benchmark["metadata"]["primary"])
            + " − "
            + cell(benchmark["metadata"]["baseline"]),
            "",
            "## Per-eval runs",
            "",
            "| Run | Eval | Pass rate | Time (s) | Tokens | Cost (USD) | Outcome |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for run in benchmark["runs"]:
        lines.append(
            "| "
            + " | ".join(
                cell(v) if v is not None else "—"
                for v in [
                    run["run_id"],
                    run["eval_name"],
                    *[run["result"][m] for m in METRICS],
                    run["result"]["outcome"],
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Warnings",
            *["- " + cell(w) for w in warnings],
            "",
            "## Notes",
            *["- " + cell(n) for n in benchmark["notes"]],
            "",
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iteration", type=Path)
    parser.add_argument("--skill-name", default="")
    parser.add_argument("--skill-path", default="")
    parser.add_argument("--primary", default="with_skill")
    parser.add_argument("--baseline")
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    try:
        root = args.iteration.resolve()
        if not root.is_dir():
            raise ValueError(f"Iteration does not exist: {root}")
        output = args.output.resolve() if args.output else root / "benchmark.json"
        benchmark, warnings = generate_benchmark(
            root,
            args.skill_name,
            str(Path(args.skill_path).resolve()) if args.skill_path else "",
            args.primary,
            args.baseline,
        )
        benchmark["notes"] = load_json(output, {}).get("notes", [])
        atomic_write(
            output, json.dumps(benchmark, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        )
        atomic_write(output.with_suffix(".md"), markdown(benchmark, warnings))
        for warning in warnings:
            print(f"Warning: {warning}", file=sys.stderr)
    except (OSError, ValueError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
