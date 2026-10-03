# Derived from Anthropic skill-creator (Apache-2.0); modified for OMP.
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Render a self-contained OMP description-tuning report with train/test columns."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import sys


def _escape(value) -> str:
    return html.escape("—" if value is None else str(value), quote=True)


def _score(split: dict | None) -> str:
    if split is None:
        return "—"
    summary = split.get("summary", {})
    return (f"{_escape(summary.get('passed'))}/{_escape(summary.get('total'))} passed"
            f"<br><small>{_escape(summary.get('failed'))} failed; {_escape(summary.get('invalid'))} invalid</small>")


def _result(row: dict | None) -> str:
    if row is None:
        return "—"
    passed = row.get("pass")
    state = "pass" if passed is True else "fail" if passed is False else "invalid"
    caption = "PASS" if passed is True else "FAIL" if passed is False else "INVALID"
    errors = row.get("invalid_runs", {})
    return (f'<strong class="{_escape(state)}">{_escape(caption)}</strong>'
            f"<br><small>{_escape(row.get('triggers'))}/{_escape(row.get('valid_runs'))} successful reads"
            f"<br>{_escape(errors.get('timeout', 0))} timeout; {_escape(errors.get('error', 0))} error"
            f"<br>{_escape(errors.get('hint_mismatch', 0))} hint mismatch</small>")


def _warm_status(attempt: dict, regime: str) -> str:
    if regime != "warm":
        return "Not applicable (cold)"
    parts = [f"<strong>Ready: {_escape(attempt.get('warm_ready'))}</strong>"]
    for split in ("train", "test"):
        evaluation = attempt.get(split)
        if evaluation is None:
            continue
        mismatches = attempt.get("hint_mismatches", {}).get(split, 0)
        parts.append(f"<p>{_escape(split.title())}: ready={_escape(evaluation.get('warm_ready'))}; "
                     f"{_escape(mismatches)} hint mismatches<br>"
                     f"<span class=\"hint\">{_escape(evaluation.get('warm_hint'))}</span></p>")
    return "".join(parts)


def generate_html(data: dict, *, skill_name: str = "") -> str:
    """Return offline HTML. All data-derived strings pass through html.escape."""
    iterations = data.get("iterations", [])
    title = (skill_name or data.get("skill_name", "")) + " — OMP skill description tuning"
    parts = ["""<!-- Derived from Anthropic skill-creator (Apache-2.0); modified for OMP. -->
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>""", _escape(title), """</title><style>
:root { color-scheme: light dark; }
body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem; line-height: 1.5; }
h1, h2 { line-height: 1.2; }
.summary, .note { padding: 1rem; border: 1px solid #8886; border-radius: .5rem; margin: 1rem 0; }
.note { border-left: 4px solid #5286bd; }
.description, .hint { white-space: pre-wrap; overflow-wrap: anywhere; }
.table { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; }
th, td { padding: .7rem; border: 1px solid #8886; vertical-align: top; }
th { text-align: left; background: #8882; }
th.query { min-width: 15rem; }
td.description { min-width: 20rem; }
.test { background: #5286bd15; }
.best { outline: 2px solid #398457; outline-offset: -2px; }
.pass { color: #398457; } .fail { color: #c34b4b; } .invalid { color: #987121; }
small { opacity: .8; } ul { padding-left: 1.2rem; } details { margin: 1rem 0; }
</style></head><body><h1>""", _escape(title), "</h1>"]
    parts.append('<div class="note">The model sees the skill name and rendered routing hint, not the full authored description. A trigger is a successful skill read at any point before the turn completes (different from upstream’s first-tool rule). Infrastructure failures are invalid runs, never non-triggers. The held-out set is hidden from the improver but reused for best-iteration selection: it is a validation set, not an unbiased final test.</div>')
    parts.append('<section class="summary"><h2>Summary</h2>')
    for label, key in (("Regime", "regime"), ("Requested model", "model"), ("Holdout", "holdout"),
                       ("Split seed", "seed"), ("Best score", "best_score"), ("Best iteration", "best_iteration"),
                       ("Stopped because", "stopped_because"), ("Eligibility", "eligibility")):
        if key in data:
            parts.append(f"<p><strong>{_escape(label)}:</strong> {_escape(data[key])}</p>")
    parts.append(f'<h3>Original description</h3><p class="description">{_escape(data.get("original_description"))}</p>')
    parts.append(f'<h3>Best description</h3><p class="description">{_escape(data.get("best_description"))}</p></section>')
    if not iterations:
        parts.append("<p>No evaluated iterations are available.</p></body></html>\n")
        return "".join(parts)

    queries = []
    seen = set()
    for attempt in iterations:
        for split in ("train", "test"):
            for row in (attempt.get(split) or {}).get("results", []):
                key = (split, row.get("id"), row.get("query"))
                if key not in seen:
                    seen.add(key)
                    queries.append((split, row))
    parts.append('<h2>Iterations</h2><div class="table"><table><thead><tr><th>Iteration</th><th>Authored description</th><th>Train score</th><th class="test">Test / validation score</th><th>Observed rendered hints</th><th>Warm readiness / hint mismatches</th>')
    for split, row in queries:
        label = "Should trigger" if row.get("should_trigger") is True else "Should not trigger"
        parts.append(f'<th class="query {_escape(split)}">{_escape(split.title())}<br><small>{_escape(label)}</small><p>{_escape(row.get("query"))}</p></th>')
    parts.append("</tr></thead><tbody>")
    for attempt in iterations:
        css = "best" if attempt.get("iteration") == data.get("best_iteration") else ""
        parts.append(f'<tr class="{_escape(css)}"><td>{_escape(attempt.get("iteration"))}</td><td class="description">{_escape(attempt.get("description"))}</td>')
        parts.append(f'<td>{_score(attempt.get("train"))}</td><td class="test">{_score(attempt.get("test"))}</td>')
        hints = attempt.get("rendered_hints", {})
        hint_html = "<ul>" + "".join(f'<li><span class="hint">{_escape(hint)}</span> <small>({_escape(count)} trials)</small></li>' for hint, count in hints.items()) + "</ul>" if hints else "No hint recorded"
        parts.append(f"<td>{hint_html}</td>")
        parts.append(f"<td>{_warm_status(attempt, data.get('regime', ''))}</td>")
        lookup = {(split, row.get("id"), row.get("query")): row for split in ("train", "test")
                  for row in (attempt.get(split) or {}).get("results", [])}
        for split, row in queries:
            parts.append(f'<td class="{_escape(split)}">{_result(lookup.get((split, row.get("id"), row.get("query"))))}</td>')
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    parts.append('<p><small>Background native description compression is excluded from normal run usage. Cold trials use a unique suffixed skill name; warm trials use the real name after up to five probes kept alive for background compression. Warm readiness requires two consecutive identical non-preview hints. When ready, mismatched hints are excluded as invalid runs; otherwise all trials are scored with a warning. Rendered hints are captured from the same session that answers each query.</small></p></body></html>\n')
    return "".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", help="run_loop results.json, or - for stdin")
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--skill-name", default="")
    args = parser.parse_args()
    try:
        source = sys.stdin.read() if args.results == "-" else Path(args.results).expanduser().resolve().read_text(encoding="utf-8")
        data = json.loads(source)
        if not isinstance(data, dict):
            raise ValueError("results must be a JSON object")
        report = generate_html(data, skill_name=args.skill_name)
        if args.output:
            path = args.output.expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(report, encoding="utf-8")
        else:
            print(report, end="")
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
