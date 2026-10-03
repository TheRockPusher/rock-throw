# Derived from Anthropic skill-creator (Apache-2.0); modified for OMP.
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6,<7"]
# ///
"""Evaluate and improve routing descriptions without editing SKILL.md.

The held-out set is hidden from the improver but reused to select the best
iteration, so it is a validation set, not an unbiased final test set.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import sys

import omp_runner

from generate_report import generate_html
from improve_description import history_entry, improve
from run_trigger_eval import evaluate, load_eval_set
from skillmd import SkillMdError, read_skill


def split_eval_set(eval_set: list[dict], holdout: float, seed: int = 42) -> tuple[list[dict], list[dict]]:
    """Stratify reproducibly, preserving training examples for each class."""
    if not 0 <= holdout < 1:
        raise ValueError("holdout must be at least 0 and less than 1")
    if not eval_set:
        raise ValueError("eval set must not be empty")
    rng = random.Random(seed)
    train, test = [], []
    for label in (True, False):
        group = [row for row in eval_set if row["should_trigger"] is label]
        rng.shuffle(group)
        count = min(len(group) - 1, max(1, int(len(group) * holdout))) if holdout > 0 and len(group) >= 2 else 0
        test.extend(group[:count])
        train.extend(group[count:])
    return train, test


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _infrastructure_only(evaluation: dict) -> bool:
    summary = evaluation["summary"]
    return (summary["invalid"] == summary["total"]
            or sum(row["valid_runs"] for row in evaluation["results"]) == 0)


def run_loop(skill_dir: Path | str, eval_set: Path | str | list[dict], model: str | None = None, *,
             improver_model: str | None = None, max_iterations: int = 5, runs_per_query: int = 3,
             threshold: float = 0.5, holdout: float = 0.4, seed: int = 42,
             concurrency: int = 2, timeout: float = 60, regime: str = "warm", warm_wait: float = 10,
             results_dir: Path | str | None = None, report: str = "auto", verbose: bool = False) -> dict:
    if max_iterations < 1:
        raise ValueError("max_iterations must be positive")
    doc = read_skill(Path(skill_dir).expanduser().resolve())
    if not doc.name or not doc.description:
        raise ValueError("skill needs a name and description")
    rows = load_eval_set(eval_set)
    train_set, test_set = split_eval_set(rows, holdout, seed)
    if results_dir is None:
        state = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destination = state / "skill-forge" / doc.name / "trigger" / timestamp
    else:
        destination = Path(results_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    logs = destination / "logs"
    logs.mkdir(exist_ok=True)
    report_path = None if report == "none" else destination / "report.html" if report == "auto" else Path(report).expanduser().resolve()
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Results: {destination}\nSplit: {len(train_set)} train, {len(test_set)} validation (seed={seed}); held-out scores are reused for selection.", file=sys.stderr)
    current = doc.description
    attempts, training_history = [], []
    best = None
    stopped = "max_iterations"
    output = {}
    for iteration in range(1, max_iterations + 1):
        print(f"Iteration {iteration}/{max_iterations}", file=sys.stderr)
        if verbose:
            print(f"Description: {current}", file=sys.stderr)
        options = {"runs_per_query": runs_per_query, "threshold": threshold, "concurrency": concurrency,
                   "timeout": timeout, "regime": regime, "verbose": verbose, "warm_wait": warm_wait}
        train = evaluate(doc.base_dir, train_set, current, model, log_dir=logs / f"iteration-{iteration}" / "train", **options)
        test = evaluate(doc.base_dir, test_set, current, model, log_dir=logs / f"iteration-{iteration}" / "test", **options) if test_set else None
        _write_json(logs / f"iteration-{iteration}-train.json", train)
        if test is not None:
            _write_json(logs / f"iteration-{iteration}-test.json", test)
        hints = Counter(train["rendered_hints"])
        if test is not None:
            hints.update(test["rendered_hints"])
        eligible = not _infrastructure_only(train) and (test is None or not _infrastructure_only(test))
        mismatches = {"train": sum(row["invalid_runs"].get("hint_mismatch", 0) for row in train["results"]),
                      "test": sum(row["invalid_runs"].get("hint_mismatch", 0) for row in test["results"]) if test else 0}
        attempt = {"iteration": iteration, "description": current,
                   "train": {"summary": train["summary"], "results": train["results"],
                             "warm_ready": train["warm_ready"], "warm_hint": train["warm_hint"]},
                   "test": {"summary": test["summary"], "results": test["results"],
                            "warm_ready": test["warm_ready"], "warm_hint": test["warm_hint"]} if test else None,
                   "rendered_hints": dict(hints),
                   "warm_ready": train["warm_ready"] and (test is None or test["warm_ready"]),
                   "hint_mismatches": mismatches, "eligible": eligible}
        attempts.append(attempt)
        selection = test if test is not None else train
        if eligible:
            training_history.append(history_entry(current, train))
            if best is None or selection["summary"]["passed"] > best["selection"]["passed"]:
                best = {"attempt": attempt, "selection": selection["summary"]}
        else:
            stopped = "infrastructure_failure"
            print("Stopping: this iteration has no valid trials in a split; it is ineligible for selection or description improvement.", file=sys.stderr)
        train_summary = train["summary"]
        print(f"  Train: {train_summary['passed']}/{train_summary['total']} passed; {train_summary['failed']} failed; {train_summary['invalid']} invalid", file=sys.stderr)
        if test is not None:
            print(f"  Validation: {test['summary']['passed']}/{test['summary']['total']} passed; {test['summary']['invalid']} invalid", file=sys.stderr)
        if regime == "warm":
            print(f"  Warm ready: train={train['warm_ready']}, validation={test['warm_ready'] if test else 'not used'}; hint mismatches: train={mismatches['train']}, validation={mismatches['test']}", file=sys.stderr)
        if eligible and train_summary["passed"] == train_summary["total"]:
            stopped = "all_train_passed"
        label = "test" if test_set else "train"
        output = {"skill_name": doc.name, "original_description": doc.description,
                  "best_description": best["attempt"]["description"] if best else None,
                  "best_score": f"{best['selection']['passed']}/{best['selection']['total']} {label}" if best else None,
                  "best_iteration": best["attempt"]["iteration"] if best else None, "regime": regime,
                  "model": model or "@default", "holdout": holdout, "seed": seed,
                  "iterations": attempts, "stopped_because": stopped}
        if doc.user_invoked:
            output["eligibility"] = "opt-in clone (hidden flags removed)"
        _write_json(destination / "results.json", output)
        if report_path is not None:
            report_path.write_text(generate_html(output, skill_name=doc.name), encoding="utf-8")
        if stopped in {"all_train_passed", "infrastructure_failure"} or iteration == max_iterations:
            break
        print("  Improving from training failures only…", file=sys.stderr)
        current = improve(doc.base_dir, train, training_history[:-1], improver_model or model,
                          description=current, log_dir=logs, iteration=iteration)
    if best is None:
        print("No eligible iteration: infrastructure failure; SKILL.md unchanged. See results.json and logs.", file=sys.stderr)
    else:
        print(f"Best: {output['best_score']} (iteration {output['best_iteration']}); SKILL.md unchanged.", file=sys.stderr)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", required=True, type=Path)
    parser.add_argument("--eval-set", required=True, type=Path)
    parser.add_argument("--model")
    parser.add_argument("--improver-model")
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--runs-per-query", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--holdout", type=float, default=0.4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--regime", choices=("warm", "cold"), default="warm")
    parser.add_argument("--warm-wait", type=float, default=10, help="seconds warm-up probes stay alive for background compression")
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--report", default="auto", help="auto (results-dir/report.html), none, or an HTML path")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    try:
        output = run_loop(args.skill, args.eval_set, args.model, improver_model=args.improver_model,
                          max_iterations=args.max_iterations, runs_per_query=args.runs_per_query,
                          threshold=args.threshold, holdout=args.holdout, seed=args.seed,
                          concurrency=args.concurrency, timeout=args.timeout, regime=args.regime, warm_wait=args.warm_wait,
                          results_dir=args.results_dir, report=args.report, verbose=args.verbose)
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 2 if output["stopped_because"] == "infrastructure_failure" else 0
    except KeyboardInterrupt:
        omp_runner.terminate_all()
        print("Cancelled; child processes stopped and temporary directories cleaned.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, SkillMdError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
