<!-- Derived from Anthropic skill-creator (Apache-2.0); modified for OMP. -->
# Evaluating and improving skills

## Contents

1. [Plan the experiment](#plan-the-experiment)
2. [Workspace and snapshots](#workspace-and-snapshots)
3. [Launch paired runs](#launch-paired-runs)
4. [Draft assertions while runs execute](#draft-assertions-while-runs-execute)
5. [Grade actual artifacts](#grade-actual-artifacts)
6. [Aggregate and analyze](#aggregate-and-analyze)
7. [Human review](#human-review)
8. [Iterate](#iterate)
9. [Blind comparison](#blind-comparison)
10. [Metrics, honesty, and cost control](#metrics-honesty-and-cost-control)

This is a continuous procedure: launch → draft assertions → grade → aggregate/analyze → show the user → read feedback → revise. Do not stop after dispatching runs or replace human review with your own judgment. Use the OMP tools advertised in the live session.

Path notation is inherited from SKILL.md: `<skill-dir>` is the resolved absolute directory of this skill; `<target-skill>` is the skill under evaluation; `<workspace>` is persistent experiment storage; `<session-model>` is the current session's model selector from the system prompt. Resolve internal URIs before invoking external programs.

## Plan the experiment

Come up with 2–3 realistic test prompts — the kind of thing a real user would actually say. Share them with the user: “Here are a few test cases I'd like to try. Do these look right, or do you want to add more?” Then run them.

Use organic requests with the necessary context, file names, formats, and constraints. Do not inject “evaluation,” arm names, success assertions, or instructions to inspect the skill into the user prompt. The runner adds matching input/output instructions to both arms; the actual skill context differs by arm. A prompt that tells the baseline how the skill works defeats the comparison.

Save prompts to the target's `evals/evals.json`; read `references/schemas.md` for the exact fields. Give each eval a unique integer `id` and meaningful `name`, a `prompt`, and human-readable `expected_output`. `files` are optional paths relative to the target skill, e.g. `evals/files/contacts.csv`; use non-sensitive, representative fixtures. Include cases covering ordinary use and important edge cases, not only perfect inputs. The runner copies fixtures into each run's `inputs/` and gives the executor absolute paths.

Start without assertions unless they already exist. Subjective skills can have no formal assertions and still receive useful human review. Do not manufacture a pass rate from a subjective preference or from an ungraded run.

Choose and label the question:

- **New skill:** `with_skill` versus `without_skill` measures improvement over ordinary behavior.
- **Existing skill:** `with_skill` versus frozen `old_skill` measures the change relative to a named version.
- **Explicit-invocation simulation** (default): evaluates following an invoked skill. Print-mode OMP does not expand `/skill:` commands, so the runner reproduces the user-invocation body injection instead. This is not a trigger/discovery metric.
- **Discovery mode:** a model-visible frozen copy is discoverable; the executor receives a plain request and may or may not read it. This measures selection plus execution. For a hidden source skill, label the eligibility change as an opt-in experiment, not installed-policy behavior.

Autonomous trigger-only testing is a different experiment; read `references/description-tuning.md` for that procedure.

## Workspace and snapshots

The default is `${XDG_STATE_HOME:-$HOME/.local/state}/skill-forge/<skill-name>/`. Use `--workspace` to override it, but keep the workspace outside repositories and skills roots so artifacts don't become authored content or additional discovered skills.

For improve mode, **before editing**, create the snapshot parent and copy the original once:

```sh
mkdir -p <workspace>/skill-snapshot
cp -r <target-skill> <workspace>/skill-snapshot/<skill-name>
```

Treat that snapshot as immutable; do not copy over an existing snapshot. If comparing against the previous iteration rather than the original, create a separate snapshot and name that decision in the review. If edits have already happened without a snapshot, reconstruct the real prior version from available source history; do not mislabel the edited version as the original.

The runner creates the per-iteration layout:

```text
<workspace>/
  skill-snapshot/<skill-name>/
  iteration-N/
    candidate/<skill-name>/
    baseline-skill/<skill-name>/       # only with --baseline-skill
    runs.json
    eval-<id>-<slug>/
      eval_metadata.json
      with_skill/run-1/
        inputs/
        outputs/
        transcript.jsonl
        transcript.md
        stderr.txt
        run.json
        timing.json
        grading.json                 # grader writes later
      without_skill/run-1/            # or old_skill/run-1/
    benchmark.json
    benchmark.md
    feedback.json
    review.html                      # optional static export
    blind/                           # optional comparison
```

`<slug>` comes from `name`, is lowercase hyphenated and at most 40 characters; fallback is `eval-<id>`. Configurations each have `run-1`, `run-2`, etc. A stable run ID is `eval-1-messy-contacts/with_skill/run-1`, not an invented flattened name. The candidate and baseline copies are frozen for that iteration. Do not alter them or reuse the iteration to hide prior results. Existing run directories are refused by default; `--force` deletes those run directories, so use a new iteration for normal revision.

## Launch paired runs

For a new skill:

```sh
uv run <skill-dir>/scripts/run_evals.py --skill <target-skill> --workspace <workspace> --iteration 1 --model <session-model> --runs 1 --concurrency 3 --timeout 900 --env isolated --with-skill-mode invoke
```

For an existing skill, the same command adds:

```sh
uv run <skill-dir>/scripts/run_evals.py --skill <target-skill> --workspace <workspace> --iteration 1 --baseline-skill <workspace>/skill-snapshot/<skill-name> --model <session-model> --runs 1 --concurrency 3 --timeout 900 --env isolated --with-skill-mode invoke
```

Default configurations are `with_skill,without_skill`, or `with_skill,old_skill` when a baseline snapshot is given. `--no-baseline` is a deliberate single-arm run, not a paired benchmark. Optional controls:

| Flag | Use |
| --- | --- |
| `--evals <path>` | Override the target's default `evals/evals.json`. |
| `--configs with_skill,without_skill` | Select arms explicitly; use `old_skill` with a snapshot. |
| `--runs 3` | Replicates per eval/configuration; one run is only a first look. |
| `--eval-ids 1,3` | Run selected evals for focused iteration; disclose the subset. |
| `--thinking <level>` | Hold supported effort constant across arms. |
| `--concurrency 3` | Bound concurrent OMP subprocesses. |
| `--timeout 900` | Per-run timeout in seconds. |
| `--env isolated` | Suppress ordinary skill/context discovery, extensions, rules, memory, and auxiliary policies through the runner's overlay. |
| `--env ambient` | Keep normal environment influences; label the comparison ambient and inspect contamination. |
| `--with-skill-mode invoke` | Reproduce explicit skill invocation (default). |
| `--with-skill-mode discover` | Make the frozen candidate model-visible and send a plain request. |
| `--tools <csv>` | Restrict executor tools consistently; do not cripple only one arm. |
| `--dry-run` | Create metadata and print the first run's exact argv/prompt without model execution. |

Launch **both arms in one call** with finite-job `bash` background dispatch:

```json
{
  "i": "Running paired skill evaluations",
  "command": "uv run <skill-dir>/scripts/run_evals.py --skill <target-skill> --workspace <workspace> --iteration 1 --model <session-model> --runs 1 --concurrency 3 --timeout 900 --env isolated --with-skill-mode invoke",
  "async": true,
  "timeout": 0
}
```

Substitute real absolute paths and quote shell arguments as needed. Set the outer finite-job `timeout: 0`: OMP clamps nonzero outer timeouts to 3600 seconds, while the script enforces its own per-run `--timeout`. Do not give this finite run a named-service readiness contract. Background results auto-deliver; keep working on assertions and do not poll the job, repeatedly read logs, or sleep-loop. Use `wait` only when all other useful work is blocked.

The script records one progress line per completed run and finally writes `runs.json`. Exit 0 means all completed; exit 2 means some failed, with artifacts still retained. Read the manifest and failed runs' `stderr.txt`, `run.json`, and transcripts before interpreting output. It is discovery/context isolation, **not OS containment**: accessible files, credentials, network services, and runtime caches remain real. Use safe fixtures and account for side effects.

## Draft assertions while runs execute

Don't just wait. Draft quantitative assertions and explain them to the user. If assertions already exist, review and explain what they check.

Good assertions are objectively verifiable and have descriptive names — they should read clearly in the benchmark viewer so someone glancing at the results immediately understands what each one checks. Subjective skills (writing style, design quality) are better evaluated qualitatively — don't force assertions onto things that need human judgment.

Update `assertions` in the target's eval set and in each iteration's `eval_metadata.json` once the runner has created it. Keep the rubric the same across both arms. The runner preserves an existing metadata file's non-empty assertions when the eval set has none, but never rely on old iteration metadata carrying over to a new directory.

Explain what the user will see: qualitative artifacts, evidence-backed formal grades where applicable, and a benchmark of measured time, tokens, and cost.

## Grade actual artifacts

After runs complete, inspect `outcome` and contamination before grading. Grade completed runs with one fresh tool-capable `task` child per run; bundle independent graders in a single `tasks` array. Failed runs are infrastructure outcomes, not completed quality samples. Read `roles/grader.md` and `references/schemas.md` first.

For assertions that can be checked programmatically, write and run a deterministic checker rather than eyeballing the artifact. Put experiment-specific checkers/evidence in the workspace, not in this installed skill; reuse them across arms and iterations. Use `uv` for Python dependencies/interpreters. Have the grader inspect the check and actual evidence, not just an unsupported “passed” summary. Bundle a helper into the target skill only if the workflow itself repeatedly needs it, not to memorize eval answers.

Below is a complete `task` call with one illustrative item. Replace `<run-dir>` with the real absolute run path and `<metadata>` with its eval's metadata path. Add an item for **every completed run**, with unique names and the same strict schema. Omit `agent` for the generic role-following worker; these bundled role documents are instructions, not globally registered agent types. Optional `model` belongs on each item.

```json
{
  "i": "Grading completed evaluation runs",
  "context": "Evaluate only each assigned run. Read the role, metadata, transcript and actual output artifacts. Use deterministic checks where possible. Do not inspect sibling outputs or modify the skill, metadata, or timing. Do not run repository builds, tests, linters, or formatters. Write grading.json and yield exactly the same object; evidence must support every pass.",
  "tasks": [
    {
      "name": "GradeWithSkillE1R1",
      "task": "Read <skill-dir>/roles/grader.md. Grade <run-dir> using <metadata>: inspect outputs/, transcript.md, run.json and timing.json. Write <run-dir>/grading.json and yield the same grading object. Treat unverifiable assertions as failed with an explanation; flag weak assertions in eval_feedback. Do not invent execution metrics.",
      "solutionSpace": "The assertions and artifacts are fixed; evidence-based grading and assertion critique require judgment.",
      "schemaMode": "strict",
      "outputSchema": {
        "type": "object",
        "properties": {
          "expectations": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {"text": {"type": "string"}, "passed": {"type": "boolean"}, "evidence": {"type": "string"}},
              "required": ["text", "passed", "evidence"],
              "additionalProperties": false
            }
          },
          "summary": {
            "type": "object",
            "properties": {"passed": {"type": "integer"}, "failed": {"type": "integer"}, "total": {"type": "integer"}, "pass_rate": {"type": "number"}},
            "required": ["passed", "failed", "total", "pass_rate"],
            "additionalProperties": false
          },
          "claims": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {"claim": {"type": "string"}, "type": {"type": "string", "enum": ["factual", "process", "quality"]}, "verified": {"type": "boolean"}, "evidence": {"type": "string"}},
              "required": ["claim", "type", "verified", "evidence"],
              "additionalProperties": false
            }
          },
          "eval_feedback": {
            "type": "object",
            "properties": {
              "suggestions": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {"assertion": {"type": "string"}, "reason": {"type": "string"}},
                  "required": ["reason"],
                  "additionalProperties": false
                }
              },
              "overall": {"type": "string"}
            },
            "required": ["suggestions", "overall"],
            "additionalProperties": false
          },
          "user_notes_summary": {
            "type": "object",
            "properties": {
              "uncertainties": {"type": "array", "items": {"type": "string"}},
              "needs_review": {"type": "array", "items": {"type": "string"}},
              "workarounds": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["uncertainties", "needs_review", "workarounds"],
            "additionalProperties": false
          }
        },
        "required": ["expectations", "summary"],
        "additionalProperties": false
      }
    }
  ]
}
```

Results auto-deliver. Read `agent://<id>` to retrieve structured grading results and check schema/error status; a JSON sidecar can exist even after validation failure, so presence alone is not success. The grader also writes the run's `grading.json`. Fix a failed grading dispatch rather than synthesizing a pass. Viewer fields are exactly `expectations[].text`, `passed`, and `evidence`, with `summary` — not renamed variants.

## Aggregate and analyze

```sh
uv run <skill-dir>/scripts/aggregate_benchmark.py <workspace>/iteration-1 --skill-name <skill-name> --skill-path <target-skill>
```

This writes `benchmark.json` and `benchmark.md`. Primary defaults to `with_skill`; baseline is `old_skill` if present, otherwise `without_skill`. Optional `--primary`, `--baseline`, and `-o` set those deliberately. Missing grades stay nullable; measured timing is read independently of grading. Runs whose outcome is not `completed` stay in `runs[]` but are excluded from all `run_summary` statistics, listed in `metadata.excluded_runs`, and warned about. Contaminated `without_skill` runs stay in statistics with `contaminated: true` and prominent warnings; do not draw clean-control conclusions from them.

Dispatch a fresh analyst `task` that reads `roles/analyzer.md` in **benchmark mode**, `benchmark.json`, metadata, and necessary run evidence. Use per-item `schemaMode: "strict"` and this exact benchmark-notes schema from `references/schemas.md`:

```json
{"type":"object","properties":{"notes":{"type":"array","items":{"type":"string"}}},"required":["notes"],"additionalProperties":false}
```

Ask for patterns aggregate means hide: non-discriminating assertions, high variance, uneven eval coverage, time/token tradeoffs, and limits of the evidence. This mode returns observations, **not improvement recommendations**. Read the structured result with `read agent://<id>`, then use `edit` or `eval` to merge the returned notes into `benchmark.json`'s existing top-level `notes` array, preserving all other fields and prior notes. The aggregator preserves notes on subsequent runs.

## Human review

Use `scripts/generate_review.py`, not custom replacement HTML. It uses `assets/viewer.html` to show Outputs (prompt, artifacts, transcript, formal grades, previous output/feedback) and Benchmark (summary, per-eval results, notes).

Launch a **named bash service**, not a detached shell background process:

```json
{
  "i": "Serving skill evaluation review",
  "command": "uv run <skill-dir>/scripts/generate_review.py <workspace>/iteration-1 --skill-name <skill-name> --benchmark <workspace>/iteration-1/benchmark.json --host 127.0.0.1 --port 3117",
  "name": "skill-review-<slug>-1",
  "ready": {"port": 3117}
}
```

The general pattern is `name: "skill-review-<slug>-<N>"`, where `<slug>` is the first 20 characters of the skill name; keep the full label within OMP's 48-character service-name limit. Substitute real values and reuse the exact label when stopping it. Do **not** combine a named service with `async: true` or a command timeout. Readiness has its own timeout. Bind to loopback. For iteration 2+, add `--previous <workspace>/iteration-(N-1)`. A busy port is a real error; do not kill its listener. Choose another port explicitly and adjust readiness/URL/tunnel together if needed.

Tell the user: “The review is available at http://localhost:3117. Outputs lets you inspect each result and leave feedback; Benchmark shows the comparison. When you're done, submit the reviews and tell me.” Never claim the server opened their browser.

For a user on another computer, always include:

```sh
ssh -L 3117:127.0.0.1:3117 <user>@<host>
```

Then open http://localhost:3117 on that computer, with the SSH tunnel running. The service is intentionally not publicly exposed.

If serving or tunnelling is impractical, generate a self-contained static file:

```sh
uv run <skill-dir>/scripts/generate_review.py <workspace>/iteration-1 --skill-name <skill-name> --benchmark <workspace>/iteration-1/benchmark.json --static <workspace>/iteration-1/review.html
```

Have the user copy the HTML to their computer and open it locally. Static feedback is downloaded, not posted to the host. Ask them to return that exact `feedback.json`, then place it in the iteration directory; do not guess that the remote user's Downloads folder is the agent's filesystem. Some very large artifacts are omitted with a note; direct the user to inspect those files separately.

For a tiny evaluation where the viewer genuinely adds little, present the prompt and artifacts in conversation and ask for concrete feedback. If structured choices are useful and `ask` is available, use unique question IDs with object options such as Accept/Revise and permit notes. Check cancellation and `timedOut`; a default chosen on timeout is not human approval. Persist explicit reviews in the `feedback.json` contract from `references/schemas.md`.

After the user says they're done, read `feedback.json`. Each review is keyed by stable `run_id`. `status: complete` means submitted, not necessarily all inspected. `visited: false` plus empty feedback is **not reviewed**. Empty feedback from a visited output is no recorded complaint, not proof of excellence; prioritize concrete issues and clarify omissions only when they matter.

Stop your viewer when finished:

```json
{"i":"Stopping owned review service","path":"proc://skill-review-<slug>-1/kill"}
```

This is a `write` call with `content` omitted, not a shell command. Use the exact owned service name. Do not stop unrelated processes.

## Iterate

Generalize from feedback, keep the prompt lean, explain why, and bundle repeated workflow helpers — see SKILL.md's improvement guidance. Read transcripts as well as outputs; don't optimize only the handful of familiar examples.

Apply improvements and validate. Use a fresh `iteration-<N+1>` and rerun paired cases. A new skill keeps the no-skill baseline. For an existing skill, make explicit whether comparison is against the original immutable snapshot or a frozen previous version. Launch review with `--previous` pointing to the prior iteration, read new feedback, improve again, repeat.

Stop when the user is satisfied, all relevant results were explicitly reviewed with no remaining issues, or changes no longer produce meaningful progress. Expand the eval set to check generalization rather than reporting a small hand-tuned set as broad reliability.

## Blind comparison

For a more rigorous output-quality comparison, randomize neutral A/B artifacts:

```sh
uv run <skill-dir>/scripts/prepare_blind.py <workspace>/iteration-1 --eval eval-1-messy-contacts --a with_skill --b without_skill --run 1 --seed 42
```

For improvement mode use `--b old_skill`. The script copies outputs to `blind/<eval-dir>/A/` and `B/`, with an unblinding key at `blind/<eval-dir>.key.json` outside those directories. It does not redact artifact contents: inspect whether outputs themselves reveal identity, and disclose compromised blinding rather than claiming it is perfect.

Read `roles/comparator.md` and its strict output schema in `references/schemas.md`. Dispatch comparator items in a `task` batch, each with `schemaMode: "strict"` and the comparator's per-item `outputSchema`. Provide only the original prompt, optional assertions, neutral A/B paths, and role instructions. Explicitly prohibit reading key files or siblings. Do not pass skills, transcripts, arm-marked metadata, or source output paths. Record the comparator's structured result via `read agent://<id>`; TIE is a valid result.

Only after comparison, unblind. Dispatch a post-hoc analyst `task` using `roles/analyzer.md`, its exact strict per-item schema, the comparator result, key, both transcripts, and available skill versions. This works for new-skill `with_skill` versus `without_skill` comparisons too: pass null for the no-skill side's skill path, and its instruction-following fields are null, marked “not applicable.” Analyze why the winner won, distinguish evidence from inference, and seek generalizable changes. For multiple independent comparisons/analyses, batch items within each wave; analysis depends on the comparison and must not run before it.

## Metrics, honesty, and cost control

- `run.json` records requested/resolved model, configuration, prompt mode, environment, outcome, and `contamination.read_skill` with evidence. A baseline reading any candidate/original skill material is contaminated. Contaminated `without_skill` runs remain in benchmark statistics, with `contaminated: true` and prominent warnings; make no clean-control conclusions from those arms.
- Runs with outcome other than `completed` (timeout, error, or aborted) remain in benchmark `runs[]` with available timing/outcomes, but are excluded from **all** `run_summary` statistics. Their IDs appear in `metadata.excluded_runs` and they produce warnings. Do not turn a failed run into a clean negative, zero-token success, or silent disappearance.
- `timing.json` is measured, never estimated. Tokens sum assistant `message_end` usage, not repeated event envelopes or output characters. `total_tokens` already includes cache reads; do not add them again. Missing values stay `null`.
- Wall duration measures the subprocess; model time sums assistant message durations. They are different. Timeouts may have partial artifacts; these are not completed deliverables.
- `token_scope` is `assistant message_end usage; excludes background description compression`. Grader, comparator, analyst, and viewer overhead are not executor metrics. Native compression may update shared caches and incur additional unreported cost even with isolated overlays.
- Means/stddev describe observed samples; repeated runs and per-eval patterns matter. Keep the primary-minus-baseline delta's direction explicit. A one-run comparison is exploratory, not a variance estimate.
- Control spend with `--runs`, `--eval-ids`, `--concurrency`, and bounded timeouts. A cheaper `--model` can be used for labelled smoke runs, never substituted for the user's model in final comparisons. Keep models/effort equal across arms and inspect resolved identities; do not silently fall back when a requested model is unavailable.
