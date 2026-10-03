# Derived from Anthropic skill-creator (Apache-2.0); modified for OMP.
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6,<7"]
# ///
"""Freeze a skill and execute paired evaluations in independent OMP processes."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import sys

import omp_runner
import skillmd


def _json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _slug(name, eval_id):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40].rstrip("-")
    return slug or f"eval-{eval_id}"


def _contained(path: Path, root: Path):
    return path == root or root in path.parents


def _load_evals(path: Path, skill_dir: Path, skill_name: str, ids: set[int] | None):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("evals"), list) or not data["evals"]:
        raise ValueError("evals.json must contain a non-empty evals array")
    if data.get("skill_name") != skill_name:
        raise ValueError(f"evals.json skill_name must be {skill_name!r}")
    seen = set()
    evals = []
    for item in data["evals"]:
        if not isinstance(item, dict):
            raise ValueError("Every eval must be an object")
        eval_id = item.get("id")
        if not isinstance(eval_id, int) or isinstance(eval_id, bool) or eval_id in seen:
            raise ValueError("Eval ids must be unique integers")
        seen.add(eval_id)
        prompt = item.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"Eval {eval_id}: prompt must be non-empty text")
        name = item.get("name", f"eval-{eval_id}")
        expected = item.get("expected_output", "")
        if not isinstance(name, str) or not isinstance(expected, str):
            raise ValueError(f"Eval {eval_id}: name and expected_output must be strings")
        assertions = item.get("assertions", item.get("expectations", []))
        files = item.get("files", [])
        if not isinstance(assertions, list) or any(not isinstance(a, str) for a in assertions):
            raise ValueError(f"Eval {eval_id}: assertions must be an array of strings")
        if not isinstance(files, list) or any(not isinstance(f, str) for f in files):
            raise ValueError(f"Eval {eval_id}: files must be an array of relative paths")
        sources = []
        for filename in files:
            relative = Path(filename)
            source = (skill_dir / relative).resolve()
            if relative.is_absolute() or ".." in relative.parts or not _contained(source, skill_dir):
                raise ValueError(f"Eval {eval_id}: input path must stay inside the skill: {filename}")
            if not source.is_file():
                raise ValueError(f"Eval {eval_id}: input file missing: {source}")
            sources.append((relative, source))
        if ids is None or eval_id in ids:
            evals.append({"eval_id": eval_id, "eval_name": name, "prompt": prompt,
                          "expected_output": expected, "files": files, "assertions": assertions,
                          "sources": sources})
    if ids is not None and ids - seen:
        raise ValueError(f"Unknown --eval-ids: {', '.join(map(str, sorted(ids - seen)))}")
    if not evals:
        raise ValueError("No evaluations selected")
    return evals


def _freeze(source: Path, destination: Path, discover: bool):
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination,
                        ignore=shutil.ignore_patterns("evals", "__pycache__", ".git", "*.pyc"))
        if discover:
            doc = skillmd.read_skill(destination)
            doc.path.write_text(skillmd.dump_skill_md(skillmd.make_model_visible(doc.frontmatter), doc.body),
                                encoding="utf-8")
    doc = skillmd.read_skill(destination)
    if discover and doc.user_invoked:
        raise ValueError(f"Existing frozen skill is user-invoked: {destination}; use a new iteration for discover mode")
    return doc


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _contamination(events, *, skill_docs, original_dirs, cwd):
    roots = list(dict.fromkeys([Path(p).resolve() for p in original_dirs]
                              + [doc.base_dir.resolve() for doc in skill_docs]))
    names = {doc.name for doc in skill_docs}
    evidence = []
    def record(path, tool, is_error):
        if not isinstance(path, str):
            return
        target = omp_runner._strip_selector(path)
        if target.startswith("skill://"):
            match = re.match(r"skill://([^/\s]+)(?:/.*)?$", target)
            matches = bool(match and match[1] in names)
        elif "://" not in target:
            candidate = Path(target).expanduser()
            candidate = (candidate if candidate.is_absolute() else cwd / candidate).resolve()
            matches = any(_contained(candidate, root) for root in roots)
        else:
            matches = False
        item = {"tool": tool, "path": path, "is_error": is_error}
        if matches and item not in evidence:
            evidence.append(item)
    for call in omp_runner.tool_calls(events):
        for value in _strings(call["args"]):
            record(value, call["name"], call["is_error"])
            # Shell/code arguments can reference a skill without a dedicated path field.
            for target in re.findall(r"skill://[^\s\"'`<>)\]}]+", value):
                record(target, call["name"], call["is_error"])
            try:
                tokens = shlex.split(value)
            except ValueError:
                tokens = []
            for token in tokens:
                token = token.strip(";,()[]")
                if token.startswith(("/", "~/", "./", "../")):
                    record(token, call["name"], call["is_error"])
            for root in roots:
                # Require a path boundary; a sibling with the same prefix is not contamination.
                pattern = re.escape(str(root)) + r"(?=$|[/\s\"'`:;,()\[\]{}])[^\s\"'`;,()\[\]{}]*"
                for match in re.finditer(pattern, value):
                    record(match[0], call["name"], call["is_error"])
    for doc in skill_docs:
        for target in omp_runner.read_targets(events, skill_name=doc.name, skill_md=doc.path):
            record(target["path"], "read", target["is_error"])
    # Resolved paths also cover relative paths and URI aliases returned by the tools.
    for event in events:
        if event.get("type") == "tool_execution_end":
            details = (event.get("result") or {}).get("details") or {}
            record(details.get("resolvedPath"), event.get("toolName"), event.get("isError"))
    return {"read_skill": bool(evidence), "evidence": evidence}


def _prepare(eval_item, configuration, replicate, *, args, iteration_dir, frozen_docs, tools):
    eval_dir = iteration_dir / f"eval-{eval_item['eval_id']}-{_slug(eval_item['eval_name'], eval_item['eval_id'])}"
    run_dir = eval_dir / configuration / f"run-{replicate}"
    inputs, outputs = run_dir / "inputs", run_dir / "outputs"
    inputs.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)
    input_paths = []
    basenames = Counter(relative.name for relative, _ in eval_item["sources"])
    for relative, source in eval_item["sources"]:
        destination = inputs / (relative if basenames[relative.name] > 1 else relative.name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        input_paths.append(str(destination))
    user_text = eval_item["prompt"] + "\n\n"
    if input_paths:
        user_text += "Input files: " + "\n".join(input_paths) + "\n"
    user_text += (f"Save the files you produce in the current directory ({outputs}). "
                  "I won't be around to answer questions, so make reasonable assumptions, "
                  "and finish with a short summary of what you produced.")
    doc = frozen_docs.get(configuration)
    if doc is not None and args.with_skill_mode == "invoke":
        prompt = omp_runner.skill_invocation_message(doc.name, doc.body, doc.base_dir, user_text)
        prompt_mode = "skill-invocation"
    else:
        prompt = user_text
        prompt_mode = "skill-discovery" if doc is not None else "plain"
    skill_dirs = [doc.base_dir.parent] if doc is not None else []
    if args.env == "isolated":
        overlay = omp_runner.isolated_overlay(skill_dirs=skill_dirs,
                                              include_skills=[doc.name] if doc is not None else None)
    else:
        overlay = omp_runner.ambient_overlay(skill_dirs=skill_dirs,
                                             ignored_skills=[args.skill_name] if doc is None else [])
    overlay_path = omp_runner.write_overlay(run_dir / "overlay.yml", overlay)
    argv = omp_runner.base_argv(cwd=outputs, overlay=overlay_path, model=args.model,
                                thinking=args.thinking, max_time_s=args.timeout, tools=tools,
                                no_skills=(doc is None and args.env == "isolated"),
                                isolated=args.env == "isolated")
    run = {"run_id": str(run_dir.relative_to(iteration_dir)), "eval_id": eval_item["eval_id"],
           "eval_name": eval_item["eval_name"], "configuration": configuration, "replicate": replicate,
           "iteration": args.iteration, "skill_name": args.skill_name,
           "skill_path": str(doc.base_dir) if doc is not None else None, "prompt_mode": prompt_mode,
           "env": args.env, "model_requested": args.model, "thinking": args.thinking}
    return {"run_dir": run_dir, "outputs": outputs, "prompt": prompt, "argv": argv, "run": run}


def _reserve(job, reserved):
    record = dict(job["run"])
    record.update({"model_resolved": None, "outcome": "running", "exit_code": None,
                   "error": None, "started_at": None, "ended_at": None, "wall_ms": None,
                   "contamination": {"read_skill": False, "evidence": []},
                   "omp_argv": job["argv"]})
    # Exclusive creation closes the race between the preflight check and execution.
    with (job["run_dir"] / "run.json").open("x", encoding="utf-8") as stream:
        job["run"] = record
        reserved.append(job)
        json.dump(record, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    (job["run_dir"] / "dry_run.json").unlink(missing_ok=True)


def _abort_pending(jobs):
    records = []
    for job in jobs:
        path = job["run_dir"] / "run.json"
        try:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                # An interrupted reservation/final write can leave incomplete JSON.
                record = dict(job["run"])
            if record.get("outcome") == "running":
                record.update({"outcome": "aborted", "error": "Evaluation interrupted",
                               "ended_at": _utc()})
                _json(path, record)
            records.append(record)
        except (OSError, ValueError) as exc:
            print(f"ERROR: Cannot record interrupted run {path}: {exc}", file=sys.stderr)
    return records


def _interrupt(signum, frame):
    raise KeyboardInterrupt


def _execute(job, args, skill_docs, original_dirs):
    started_at = _utc()
    result = omp_runner.run_print(job["prompt"], job["argv"], cwd=job["outputs"],
                                  timeout_s=args.timeout, transcript_path=job["run_dir"] / "transcript.jsonl")
    ended_at = _utc()
    models = omp_runner.resolved_models(result.events)
    calls = omp_runner.tool_calls(result.events)
    counts = {}
    for call in calls:
        name = call["name"] or "unknown"
        counts[name] = counts.get(name, 0) + 1
    timing = omp_runner.usage_summary(result.events)
    observed = any(e.get("type") == "agent_start" for e in result.events) or bool(
        omp_runner.assistant_messages(result.events))
    tool_errors = (sum(c["is_error"] is True for c in calls)
                   if observed and all(c["is_error"] is not None for c in calls) else None)
    timing.update({"duration_ms": result.wall_ms, "total_duration_seconds": result.wall_ms / 1000,
                   "tool_calls": counts if observed else None, "tool_errors": tool_errors,
                   "token_scope": "assistant message_end usage; excludes background description compression"})
    run = dict(job["run"])
    run.update({"model_resolved": models[-1] if models else None, "outcome": result.outcome,
                "exit_code": result.exit_code, "error": result.error, "started_at": started_at,
                "ended_at": ended_at, "wall_ms": result.wall_ms,
                "contamination": _contamination(result.events, skill_docs=skill_docs,
                                                original_dirs=original_dirs, cwd=job["outputs"]),
                "omp_argv": result.argv})
    run_dir = job["run_dir"]
    (run_dir / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    (run_dir / "transcript.md").write_text(omp_runner.render_transcript_md(result.events), encoding="utf-8")
    _json(run_dir / "timing.json", timing)
    _json(run_dir / "run.json", run)
    return run, timing


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", type=Path, required=True)
    parser.add_argument("--evals", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--iteration", type=_positive, required=True)
    baseline = parser.add_mutually_exclusive_group()
    baseline.add_argument("--baseline-skill", type=Path)
    baseline.add_argument("--no-baseline", action="store_true")
    parser.add_argument("--configs", help="Comma-separated with_skill,without_skill,old_skill")
    parser.add_argument("--runs", type=_positive, default=1)
    parser.add_argument("--eval-ids", help="Comma-separated integer eval ids")
    parser.add_argument("--model", default="@default")
    parser.add_argument("--thinking")
    parser.add_argument("--concurrency", type=_positive, default=3)
    parser.add_argument("--timeout", type=_positive, default=900)
    parser.add_argument("--env", choices=("isolated", "ambient"), default="isolated")
    parser.add_argument("--with-skill-mode", choices=("invoke", "discover"), default="invoke")
    parser.add_argument("--tools", help="Comma-separated OMP tool names")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Delete selected existing run directories, keeping frozen skills")
    return parser


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    reserved = []
    try:
        args.skill = args.skill.expanduser().resolve()
        source_doc = skillmd.read_skill(args.skill)
        args.skill = source_doc.base_dir.resolve()
        args.skill_name = source_doc.name
        if (not isinstance(args.skill_name, str) or not re.fullmatch(skillmd.NAME_RE, args.skill_name)
                or len(args.skill_name) > 64):
            raise ValueError("Skill must have a valid name before it can be evaluated")
        baseline_doc = None
        if args.baseline_skill is not None:
            baseline_doc = skillmd.read_skill(args.baseline_skill.expanduser().resolve())
            args.baseline_skill = baseline_doc.base_dir.resolve()
            if (not isinstance(baseline_doc.name, str) or not re.fullmatch(skillmd.NAME_RE, baseline_doc.name)
                    or len(baseline_doc.name) > 64):
                raise ValueError("Baseline skill must have a valid name")
        configs = ["with_skill"]
        if not args.no_baseline:
            configs += ["old_skill" if baseline_doc is not None else "without_skill"]
        if args.configs is not None:
            configs = [c.strip() for c in args.configs.split(",")]
        if not configs or len(set(configs)) != len(configs) or any(c not in {"with_skill", "without_skill", "old_skill"} for c in configs):
            raise ValueError("--configs must contain unique with_skill,without_skill,old_skill names")
        if "old_skill" in configs and baseline_doc is None:
            raise ValueError("old_skill requires --baseline-skill")
        if args.no_baseline and configs != ["with_skill"]:
            raise ValueError("--no-baseline permits only the with_skill configuration")
        ids = None
        if args.eval_ids is not None:
            ids = {int(value.strip()) for value in args.eval_ids.split(",")}
        tools = None if args.tools is None else [t.strip() for t in args.tools.split(",")]
        if tools is not None and any(not tool for tool in tools):
            raise ValueError("--tools must contain non-empty tool names")
        eval_path = (args.evals or args.skill / "evals" / "evals.json").expanduser().resolve()
        evals = _load_evals(eval_path, args.skill, args.skill_name, ids)
        default_state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
        workspace = (args.workspace or default_state / "skill-forge" / args.skill_name).expanduser().resolve()
        original_dirs = [args.skill] + ([args.baseline_skill] if baseline_doc is not None else [])
        if any(_contained(workspace, root) for root in original_dirs):
            raise ValueError("Workspace must be outside the candidate and baseline skill directories")
        iteration_dir = workspace / f"iteration-{args.iteration}"
        # Check every selected destination before making any destructive changes.
        run_dirs = []
        for item in evals:
            eval_dir = iteration_dir / f"eval-{item['eval_id']}-{_slug(item['eval_name'], item['eval_id'])}"
            for config in configs:
                for replicate in range(1, args.runs + 1):
                    run_dirs.append(eval_dir / config / f"run-{replicate}")
        existing = [path for path in run_dirs if (path / "run.json").exists()]
        if existing and not args.force:
            raise ValueError(f"Run directory already exists: {existing[0]}; use a new iteration or --force")
        # Frozen copies are immutable for an iteration, including forced reruns.
        candidate = _freeze(args.skill, iteration_dir / "candidate" / args.skill_name,
                            args.with_skill_mode == "discover")
        frozen_docs = {"with_skill": candidate}
        if baseline_doc is not None:
            frozen_docs["old_skill"] = _freeze(args.baseline_skill,
                                               iteration_dir / "baseline-skill" / baseline_doc.name,
                                               args.with_skill_mode == "discover")
        for path in existing:
            if path.is_symlink():
                raise ValueError(f"Refusing to delete symlinked run directory: {path}")
            shutil.rmtree(path)
        jobs = []
        for item in evals:
            eval_dir = iteration_dir / f"eval-{item['eval_id']}-{_slug(item['eval_name'], item['eval_id'])}"
            eval_dir.mkdir(parents=True, exist_ok=True)
            metadata = {k: v for k, v in item.items() if k != "sources"}
            metadata_path = eval_dir / "eval_metadata.json"
            if not metadata["assertions"] and metadata_path.exists():
                old_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                previous = old_metadata.get("assertions", [])
                if previous:
                    metadata["assertions"] = previous
            _json(metadata_path, metadata)
            for config in configs:
                for replicate in range(1, args.runs + 1):
                    jobs.append(_prepare(item, config, replicate, args=args,
                                         iteration_dir=iteration_dir, frozen_docs=frozen_docs, tools=tools))
        manifest = {"iteration": args.iteration, "skill": str(args.skill), "workspace": str(workspace),
                    "model_requested": args.model, "runs": []}
        if args.dry_run:
            first = jobs[0]
            print("argv: " + json.dumps(first["argv"], ensure_ascii=False))
            print("prompt transport: stdin")
            print("prompt:\n" + first["prompt"])
            for job in jobs:
                _json(job["run_dir"] / "dry_run.json",
                      {"run_id": job["run"]["run_id"], "prepared_at": _utc()})
            print(f"Dry run: prepared {len(jobs)} run directories; launched nothing.")
            return 0
        for job in jobs:
            _reserve(job, reserved)
        results = {}
        failures = 0
        executor = ThreadPoolExecutor(max_workers=args.concurrency)
        previous_term = signal.signal(signal.SIGTERM, _interrupt)
        try:
            futures = {executor.submit(_execute, job, args, list(frozen_docs.values()), original_dirs): job
                       for job in jobs}
            for finished, future in enumerate(as_completed(futures), 1):
                run, timing = future.result()
                results[run["run_id"]] = run
                failures += run["outcome"] != "completed"
                tokens = timing["total_tokens"]
                print(f"[{finished}/{len(jobs)}] {run['run_id']} {run['outcome']} "
                      f"{run['wall_ms'] / 1000:.1f}s {tokens if tokens is not None else 'null'} tok", flush=True)
        except KeyboardInterrupt:
            previous_int = signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            try:
                executor.shutdown(wait=False, cancel_futures=True)
                omp_runner.terminate_all()
                executor.shutdown(wait=True, cancel_futures=True)
                manifest["runs"] = _abort_pending(reserved)
                _json(iteration_dir / "runs.json", manifest)
                completed = sum(run["outcome"] == "completed" for run in manifest["runs"])
                aborted = sum(run["outcome"] == "aborted" for run in manifest["runs"])
                print(f"Interrupted: {completed}/{len(jobs)} completed; {aborted} aborted.",
                      file=sys.stderr)
                return 130
            finally:
                signal.signal(signal.SIGINT, previous_int)
        except Exception:
            executor.shutdown(wait=False, cancel_futures=True)
            omp_runner.terminate_all()
            executor.shutdown(wait=True, cancel_futures=True)
            _abort_pending(reserved)
            raise
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
            signal.signal(signal.SIGTERM, previous_term)
        manifest["runs"] = [results[job["run"]["run_id"]] for job in jobs]
        manifest_path = iteration_dir / "runs.json"
        _json(manifest_path, manifest)
        print(manifest_path)
        print(f"{len(jobs) - failures}/{len(jobs)} completed; {failures} failed.")
        return 2 if failures else 0
    except (OSError, ValueError, skillmd.SkillMdError) as exc:
        _abort_pending(reserved)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        omp_runner.terminate_all()
        _abort_pending(reserved)
        print("ERROR: Evaluation interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
