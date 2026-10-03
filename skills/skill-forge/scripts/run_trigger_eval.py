# Derived from Anthropic skill-creator (Apache-2.0); modified for OMP.
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6,<7"]
# ///
"""Evaluate successful skill reads at any point before the turn completes.

Unlike upstream's first-tool rule, unrelated earlier reads do not prevent a
trigger. Timeouts and infrastructure errors are invalid runs, not negatives.
Warm trials use the real name after up to five probes, each kept alive for
--warm-wait seconds, requiring two identical non-preview hints to be ready.
Cold trials use a fresh suffixed name. Both record same-session routing hints.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

import omp_runner
from skillmd import SkillMdError, cold_preview, dump_skill_md, make_model_visible, read_skill


def load_eval_set(source: Path | str | list[dict]) -> list[dict]:
    """Validate labels and assign stable missing IDs before splitting."""
    data = json.loads(Path(source).expanduser().resolve().read_text(encoding="utf-8")) if isinstance(source, (str, Path)) else source
    if not isinstance(data, list):
        raise ValueError("eval set must be a JSON array")
    results, labels, ids = [], {}, set()
    for index, row in enumerate(data, 1):
        if not isinstance(row, dict) or not isinstance(row.get("query"), str) or not row["query"].strip() or type(row.get("should_trigger")) is not bool:
            raise ValueError(f"eval {index} needs a nonempty query and boolean should_trigger")
        ident = row.get("id", index)
        if type(ident) is not int or ident in ids:
            raise ValueError(f"eval {index} has a noninteger or duplicate id")
        ids.add(ident)
        query, label = row["query"], row["should_trigger"]
        if query in labels and labels[query] != label:
            raise ValueError("duplicate queries have conflicting should_trigger labels")
        labels[query] = label
        results.append({"id": ident, "query": query, "should_trigger": label})
    return results


def summarize(results: list[dict]) -> dict:
    return {"total": len(results), "passed": sum(r["pass"] is True for r in results),
            "failed": sum(r["pass"] is False for r in results),
            "invalid": sum(r["pass"] is None for r in results)}


def _state(session: omp_runner.RpcSession, trial_name: str, remaining) -> str:
    response = session.request({"type": "get_state"}, timeout_s=remaining())
    if response.get("success") is not True:
        raise RuntimeError("get_state failed")
    data = response.get("data", {})
    tools = data.get("dumpTools", [])
    names = [tool.get("name") if isinstance(tool, dict) else tool for tool in tools]
    prompt = data.get("systemPrompt", "")
    if isinstance(prompt, list):
        prompt = "\n".join(prompt)
    skills = omp_runner.parse_skills_block(prompt)
    if names != ["read"] or set(skills) != {trial_name}:
        raise RuntimeError("isolation: expected only the read tool and the trial skill")
    return skills[trial_name]


def _trial(doc, description: str, model: str | None, thinking: str | None,
           timeout: float, trial_name: str, query: str | None, probe_wait: float = 0,
           expected_hint: str | None = None) -> dict:
    root = Path(tempfile.mkdtemp(prefix="skill-trigger-"))
    session = None
    result = {"outcome": "error", "hint": None, "events": [], "error": None, "stats": None}
    deadline = time.monotonic() + timeout

    def remaining():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise TimeoutError("trial deadline exceeded")
        return seconds

    try:
        skill_dir = root / "skills" / trial_name
        shutil.copytree(doc.base_dir, skill_dir, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        fm = make_model_visible(doc.frontmatter)
        fm.update(name=trial_name, description=description)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(dump_skill_md(fm, doc.body), encoding="utf-8")
        cwd = root / "cwd"
        cwd.mkdir()
        overlay = omp_runner.write_overlay(root / "isolation.yml", omp_runner.isolated_overlay(
            skill_dirs=[root / "skills"], include_skills=[trial_name], keep_todo=False, retries=False))
        argv = omp_runner.base_argv(cwd=cwd, overlay=overlay, model=model, thinking=thinking,
                                   max_time_s=max(1, int(timeout)), tools=["read"], system_prompt="",
                                   mode="rpc", no_ui=True)
        session = omp_runner.RpcSession(argv, cwd=cwd, timeout_s=remaining())
        result["hint"] = _state(session, trial_name, remaining)
        if query is not None and expected_hint is not None and result["hint"] != expected_hint:
            result.update(outcome="hint_mismatch", error="rendered hint differs from the confirmed warm hint")
            return result
        if query is None:
            # Background compression must have time to write the shared cache.
            if probe_wait:
                if remaining() < probe_wait:
                    raise TimeoutError("warm-up deadline cannot accommodate warm-wait")
                time.sleep(probe_wait)
            result["outcome"] = "probe"
        else:
            events = session.prompt(query, timeout_s=remaining())
            result["events"] = events
            completion = [e for e in events if e.get("type") == "prompt_result"]
            if not completion or completion[-1].get("status") != "completed":
                raise RuntimeError("prompt failed or its completion frame is missing")
            if any(e.get("type") == "message_end" and e.get("message", {}).get("role") == "assistant"
                   and e["message"].get("stopReason") in {"error", "aborted"} for e in events):
                raise RuntimeError("assistant turn failed")
            stats = session.request({"type": "get_session_stats"}, timeout_s=remaining())
            if stats.get("success") is not True:
                raise RuntimeError("get_session_stats failed")
            result["stats"] = stats.get("data")
            reads = omp_runner.read_targets(events, skill_name=trial_name, skill_md=skill_md)
            result["outcome"] = "triggered" if any(r.get("is_error") is False for r in reads) else "not_triggered"
    except KeyboardInterrupt:
        omp_runner.terminate_all()
        raise
    except (TimeoutError, subprocess.TimeoutExpired) as exc:
        result.update(outcome="timeout", error=str(exc))
    except Exception as exc:
        result.update(outcome="error", error=str(exc))
    finally:
        try:
            if session is not None:
                code = session.close()
                if code not in (0, None) and result["outcome"] not in {"timeout", "error"}:
                    result.update(outcome="error", error=f"OMP exited with code {code}")
        except Exception as exc:
            if result["outcome"] != "timeout":
                result.update(outcome="error", error=f"OMP teardown failed: {exc}")
        finally:
            if session is not None and query is not None and not result["events"]:
                # Public RPC events exclude get_state responses; preserve measured
                # partial usage on timeouts without persisting sensitive state.
                result["events"] = list(session.events)
            shutil.rmtree(root)
    return result


def evaluate(skill_dir: Path | str, eval_set: Path | str | list[dict], description: str | None = None,
             model: str | None = None, *, thinking: str | None = "low", runs_per_query: int = 3,
             threshold: float = 0.5, concurrency: int = 2, timeout: float = 60,
             regime: str = "warm", hint_only: bool = False, verbose: bool = False,
             log_dir: Path | None = None, warm_wait: float = 10) -> dict:
    """Evaluate an opt-in clone without editing the original skill."""
    if runs_per_query < 1 or concurrency < 1 or timeout <= 0 or warm_wait < 0 or not 0 <= threshold <= 1 or regime not in {"warm", "cold"}:
        raise ValueError("invalid runs, concurrency, timeout, warm-wait, threshold, or regime")
    doc = read_skill(Path(skill_dir).expanduser().resolve())
    if not doc.name or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", doc.name) or len(doc.name) > 64:
        raise ValueError("skill must have a valid name")
    description = doc.description if description is None else description
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        raise ValueError("description must be nonempty and at most 1024 characters")
    rows = load_eval_set(eval_set)
    preview = cold_preview(description)
    probe = None
    warm_hint, warm_ready = None, False
    if regime == "warm":
        previous_hint = None
        for _ in range(5):
            probe = _trial(doc, description, model, thinking, max(timeout, warm_wait + 30),
                           doc.name, None, probe_wait=warm_wait)
            if probe["outcome"] == "probe":
                warm_hint = probe["hint"]
                if warm_hint != preview and warm_hint == previous_hint:
                    warm_ready = True
                    break
                previous_hint = warm_hint if warm_hint != preview else None
            else:
                previous_hint = None
                if verbose:
                    print(f"Warm-up: {probe['outcome']}: {probe['error']}", file=sys.stderr)
        if not warm_ready:
            print("Warning: warm routing hint did not stabilize after five probes; scoring all trials with warm_ready:false.", file=sys.stderr)
    if hint_only:
        if regime == "cold":
            name = doc.name[:55].rstrip("-") + "-" + uuid.uuid4().hex[:8]
            probe = _trial(doc, description, model, thinking, timeout, name, None)
        if probe is None or probe["outcome"] != "probe":
            raise RuntimeError(f"hint inspection failed: {probe and probe['error']}")
        return {"cold_preview": preview, "rendered_hint": probe["hint"], "warm_ready": warm_ready}

    trials = [[] for _ in rows]
    if log_dir is not None:
        log_dir = Path(log_dir).expanduser().resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
    pool = ThreadPoolExecutor(max_workers=concurrency)
    try:
        jobs = {}
        for index, row in enumerate(rows):
            for run in range(1, runs_per_query + 1):
                name = doc.name if regime == "warm" else doc.name[:55].rstrip("-") + "-" + uuid.uuid4().hex[:8]
                future = pool.submit(_trial, doc, description, model, thinking, timeout, name, row["query"],
                                     expected_hint=warm_hint if warm_ready else None)
                jobs[future] = (index, run)
        for future in as_completed(jobs):
            index, run = jobs[future]
            trial = future.result()
            trials[index].append(trial)
            if verbose:
                print(f"Query {rows[index]['id']} run {run}: {trial['outcome']}" + (f" ({trial['error']})" if trial["error"] else ""), file=sys.stderr)
            if log_dir is not None:
                # Never log the raw get_state system prompt or authentication state.
                (log_dir / f"query-{rows[index]['id']}-run-{run}.json").write_text(json.dumps(trial, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except KeyboardInterrupt:
        pool.shutdown(wait=False, cancel_futures=True)
        omp_runner.terminate_all()
        raise
    finally:
        # Killed workers unwind their trial finally blocks and remove temp roots.
        pool.shutdown(wait=True, cancel_futures=True)

    results, hints, models, usages = [], Counter(), set(), []
    for row, batch in zip(rows, trials):
        valid = sum(t["outcome"] in {"triggered", "not_triggered"} for t in batch)
        triggers = sum(t["outcome"] == "triggered" for t in batch)
        rate = triggers / valid if valid else None
        observed = sorted({t["hint"] for t in batch if t["hint"] is not None})
        hints.update(t["hint"] for t in batch if t["hint"] is not None)
        for trial in batch:
            models.update(omp_runner.resolved_models(trial["events"]))
            usage = omp_runner.usage_summary(trial["events"])
            # Session stats are measured, but message_end is the canonical usage scope.
            usages.append(usage)
        results.append({**row, "trigger_rate": rate, "triggers": triggers, "valid_runs": valid,
                        "invalid_runs": {kind: sum(t["outcome"] == kind for t in batch) for kind in ("timeout", "error", "hint_mismatch")},
                        "hints": observed, "pass": ((rate >= threshold) == row["should_trigger"]) if valid else None})
    def measured_sum(key):
        values = [u[key] for u in usages if u.get(key) is not None]
        return sum(values) if values else None
    output = {"skill_name": doc.name, "description": description, "regime": regime,
              "warm_hint": warm_hint, "warm_ready": warm_ready,
              "model_requested": model or "@default", "models_resolved": sorted(models),
              "rendered_hints": dict(hints), "results": results, "summary": summarize(results),
              "usage": {"total_tokens": measured_sum("total_tokens"), "cost_usd": measured_sum("cost_usd"),
                        "note": "excludes background description compression"}}
    if doc.user_invoked:
        output["eligibility"] = "opt-in clone (hidden flags removed)"
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", required=True, type=Path)
    parser.add_argument("--eval-set", required=True, type=Path)
    parser.add_argument("--description")
    parser.add_argument("--model")
    parser.add_argument("--thinking", default="low")
    parser.add_argument("--runs-per-query", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--regime", choices=("warm", "cold"), default="warm")
    parser.add_argument("--warm-wait", type=float, default=10, help="seconds each warm-up RPC process stays alive for background compression (default: 10)")
    parser.add_argument("--hint-only", action="store_true")
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    try:
        output = evaluate(args.skill, args.eval_set, args.description, args.model, thinking=args.thinking,
                          runs_per_query=args.runs_per_query, threshold=args.threshold,
                          concurrency=args.concurrency, timeout=args.timeout, regime=args.regime,
                          hint_only=args.hint_only, verbose=args.verbose, warm_wait=args.warm_wait)
        text = json.dumps(output, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            target = args.output.expanduser().resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return 1 if output.get("summary", {}).get("invalid") else 0
    except KeyboardInterrupt:
        omp_runner.terminate_all()
        print("Cancelled; child processes stopped and trial directories cleaned.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, SkillMdError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
