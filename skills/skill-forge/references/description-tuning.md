<!-- Derived from Anthropic skill-creator (Apache-2.0); modified for OMP. -->
# Description tuning for OMP

## Contents

1. [When tuning applies](#when-tuning-applies)
2. [What the model actually sees](#what-the-model-actually-sees)
3. [Write for the rendered hint](#write-for-the-rendered-hint)
4. [Generate realistic trigger queries](#generate-realistic-trigger-queries)
5. [Review the query set with the user](#review-the-query-set-with-the-user)
6. [Inspect and evaluate a description](#inspect-and-evaluate-a-description)
7. [Run the optimization loop](#run-the-optimization-loop)
8. [Read results honestly](#read-results-honestly)
9. [Apply the chosen result](#apply-the-chosen-result)
10. [Cost and scope](#cost-and-scope)

Path notation is inherited from SKILL.md: `<skill-dir>` is this skill's resolved absolute directory; `<target-skill>` is the skill being tuned; `<workspace>` is its persistent external workspace; `<session-model>` is the current session model selector from the system prompt. External programs need filesystem paths, not internal URIs.

## When tuning applies

Description tuning measures autonomous selection of **model-invocable skills**. For a user-invoked skill (`disable-model-invocation: true` or `hide: true`), instead review the short human-facing summary and test explicit invocation. Hidden skills are absent from the model's routing list, but remain readable via `skill://` and explicitly invocable through `/skill:`. Hiding is not access control.

If the user explicitly wants to explore making a user-only skill model-invocable, the trigger scripts use a labelled **opt-in clone** with hidden flags removed. Report that this tests hypothetical eligibility, not the source's installed policy. Do not silently remove the source's hidden flags or propose autonomous use merely because a trigger experiment scores well. This skill itself is user-invoked by design.

Content quality should already be in reasonable shape. Triggering and useful execution are different questions: a correctly selected but poorly written skill still fails the user. Use `references/evaluation.md` for paired task-quality evaluation.

## What the model actually sees

In OMP 18.5.x the system prompt's skills list contains an eligible skill's **name plus rendered routing hint**, not necessarily its full authored description. After selection, a successful `read` of `skill://<name>` (or the resolved SKILL.md) loads the full instructions.

### Cold preview

OMP normalizes whitespace. If the description fits in 100 characters, it displays that text. Otherwise it considers the first 99 characters:

- Prefer the first sentence ending with `.`, `!`, or `?` followed by whitespace/end, if that sentence is at least 40 characters long.
- Otherwise cut at the last word boundary (or use the slice if no space exists), then append `…`.

Later paragraphs or trigger branches may never reach a cold-session model. A long description is not a longer cold routing hint.

### Warm compression and cache

Native background `smol` compression produces a single-line hint capped at **12 words and 160 characters**. It can paraphrase the source and introduce or omit distinctions; do not assume it merely truncates sentence two. The cache key hashes the compression prompt, skill name, and full authored description. Changing the name or description changes the key.

Each session freezes its hint at rendering time. A background completion updates the shared cache for **later sessions**, not the current one. Background compression is model work and is excluded from normal run-summary usage/cost. A config overlay is not a promise that no runtime cache writes occur.

The trigger evaluator starts a fresh headless OMP RPC process for every trial, inspects `get_state` before the query, validates that only the candidate skill and `read` tool are exposed, and records the actual rendered hint from that same session. This makes the measured hint observable instead of inferring it from the authored description or startup timing.

### Warm versus cold regimes

- `--regime warm` (default) uses the real skill name and runs up to five fresh `get_state` probes, keeping each process alive for `--warm-wait` seconds (default 10) so background compression can finish. Two consecutive identical non-preview hints establish readiness: `warm_ready: true` and `warm_hint` identify the observed stable hint. When ready, scoring trials whose actual hint differs from `warm_hint` are excluded as `invalid_runs.hint_mismatch`. If `warm_ready: false`, trials were scored under mixed/unknown hints: report that explicitly and do not call the experiment warm. Compression identical to the preview cannot establish non-preview readiness.
- `--regime cold` gives every trial a unique `<name>-<8 hex>` name, changing the key so the cold preview is expected. It measures first-install-like routing with an altered name; record and disclose that alteration. New keys can also start additional background compression work.

Do not combine warm and cold results into one trigger rate. Compare descriptions in the same regime and inspect hint distributions for mixed rendering within a claimed warm experiment.

## Write for the rendered hint

For a model-invocable skill:

- Write a crisp, self-contained first sentence within 100 characters. If a longer description is needed, a first sentence of at least 40 characters can survive the sentence-preference rule.
- Use third-person, task-specific wording: what this skill does and when it is appropriate. Describe intent categories, not a pile of test-query keywords.
- Distinguish meaningful trigger branches and nearby tasks that should use another workflow. Include an exclusion when it clarifies a genuine boundary, not to memorize every negative query.
- Keep richer details in the body/references; do not assume a long trigger list reaches the model or survives compression.
- Avoid keyword stuffing, overly broad claims, and descriptions that overfit a handful of examples. Keep the authored description non-empty, at most 1024 characters, and without angle brackets.

Read `references/writing-skills.md` for frontmatter syntax, invocation policy, and the rest of the authoring guidance. Human-facing descriptions for user-invoked skills need a clear summary, not autonomous trigger optimization.

## Generate realistic trigger queries

Create roughly 20 queries: **8–10 should-trigger and 8–10 should-not-trigger**. Save them in the target's `evals/trigger-evals.json`. Read `references/schemas.md` before writing this file:

```json
[
  {"id": 1, "query": "A concrete user request that benefits from this skill", "should_trigger": true},
  {"id": 2, "query": "A plausible adjacent request needing a different workflow", "should_trigger": false}
]
```

IDs are optional on input (the scripts assign stable 1-based IDs if absent), but explicit unique IDs make review easier. Duplicate queries with conflicting labels are rejected. Keep all copies of a query in one partition; do not disguise duplicates as independent validation examples.

The queries must be realistic and something a user would actually type. Not abstract requests, but requests that are concrete and specific and have a good amount of detail: file paths, personal context about the user's job or situation, column names and values, company names, URLs, a little backstory. Some might be lowercase or contain abbreviations, typos, or casual speech. Use a mix of lengths and focus on edge cases rather than making everything clear-cut. Use synthetic/non-sensitive details for fixtures and personal context.

Bad: “Format this data”, “Extract text from PDF”, “Create a chart”.

Good: “ok so my boss just sent me this xlsx file (its in my downloads, called something like 'Q4 sales final FINAL v2.xlsx') and she wants me to add a column that shows the profit margin as a percentage. The revenue is in column C and costs are in column D i think”.

For the **should-trigger** queries (8–10), think about coverage. You want different phrasings of the same intent — some formal, some casual. Include cases where the user doesn't explicitly name the skill or file type but clearly needs it. Throw in uncommon use cases and cases where this skill competes with another but should win.

For the **should-not-trigger** queries (8–10), the most valuable ones are near-misses — queries that share keywords or concepts with the skill but actually need something different. Think adjacent domains, ambiguous phrasing where a naive keyword match would trigger but shouldn't, and cases touching on something the skill does in a context where another tool is more appropriate.

The key thing to avoid: don't make should-not-trigger queries obviously irrelevant. “Write a fibonacci function” as a negative test for a PDF skill is too easy — it doesn't test anything. The negative cases should be genuinely tricky.

Use substantive tasks where consulting the skill would plausibly be useful. Do not tell the model to invoke the target skill, mention `skill://`, or expose the desired labels in the query: that would be explicit selection, not autonomous routing. Do not assume every simple request must trigger or that every complex request will. Make the labels reflect intended use, not a platform-specific claim about model tendencies.

## Review the query set with the user

This step matters — bad eval queries lead to bad descriptions. Let the user correct unrealistic wording, boundaries, and labels before optimization.

Either show/edit the JSON directly or use the trigger viewer (which loads `assets/trigger_review.html`):

```sh
uv run <skill-dir>/scripts/generate_review.py --trigger-evals <target-skill>/evals/trigger-evals.json --skill-name <skill-name> --description "<current-description>" --host 127.0.0.1 --port 3117
```

Run it as a named `bash` service such as `name: "skill-trig-<slug>"`, where `<slug>` is the first 20 characters of the skill name, keeping the label within OMP's 48-character limit. Use `ready: {port: 3117}` and **no `async` or command timeout**. Shell-quote the actual description correctly. Do not run this alongside an evaluation viewer already using that port; stop your owned service first or choose a distinct port/readiness/tunnel. The trigger viewer's default port is 3118 if `--port` is omitted.

Give the user the tunnel instruction `ssh -L 3117:127.0.0.1:3117 <user>@<host>`, then open http://localhost:3117. The live viewer saves the query set back to the given JSON file. Read that file after the user finishes.

For static review:

```sh
uv run <skill-dir>/scripts/generate_review.py --trigger-evals <target-skill>/evals/trigger-evals.json --skill-name <skill-name> --description "<current-description>" --static <workspace>/trigger-review.html
```

Have the user copy/open the HTML locally and return its exported eval-set JSON; use that exact reviewed file. Do not assume a remote user's Downloads folder is available on the host. Stop the owned live service with `write proc://skill-trig-<slug>/kill`, omitting `content` and using the exact same service label.

Use `ask` only when genuinely needed for structured choices such as whether an ambiguous near-miss belongs in scope. Never ask the user for information obtainable from the skill or repository. Timeout/cancelled choices are not affirmative review.

## Inspect and evaluate a description

Inspect the authored description's cold preview and an observed rendered hint before spending on a loop:

```sh
uv run <skill-dir>/scripts/run_trigger_eval.py --skill <target-skill> --eval-set <target-skill>/evals/trigger-evals.json --model <session-model> --regime warm --hint-only
```

An alternative description can be tested without modifying SKILL.md:

```sh
uv run <skill-dir>/scripts/run_trigger_eval.py --skill <target-skill> --eval-set <target-skill>/evals/trigger-evals.json --description "<candidate-description>" --model <session-model> --thinking low --runs-per-query 3 --threshold 0.5 --concurrency 2 --timeout 60 --regime warm -o <workspace>/trigger-results.json
```

The evaluator uses a temporary copy containing the actual skill body and bundled resources, removes hidden flags from the clone where needed, and deletes the temporary root afterward. Fresh RPC trials expose only `read`, disable other skill discovery, retries, and model fallback, and verify isolation before scoring. This is a routing experiment, not complete task execution with the normal tool set.

A trigger means a **successful read of the candidate instruction document at any point in the completed query turn**, via its exact URI or resolved SKILL.md path. Merely mentioning the skill, attempting a failed read, or reading a reference instead of the instruction document is not a successful trigger. This deliberately does not require the skill read to be the first tool call.

## Run the optimization loop

Tell the user you'll run the loop in the background. Use their session model selector for routing tests, not an unannounced cheaper model:

```sh
uv run <skill-dir>/scripts/run_loop.py --skill <target-skill> --eval-set <target-skill>/evals/trigger-evals.json --model <session-model> --max-iterations 5 --runs-per-query 3 --threshold 0.5 --holdout 0.4 --seed 42 --concurrency 2 --timeout 60 --regime warm --results-dir <workspace>/trigger/<UTC-timestamp> --report auto --verbose
```

Launch this finite command with `bash`, `async: true`, and `timeout: 0`, like paired evals in `references/evaluation.md`. OMP clamps nonzero outer timeouts to 3600 seconds; the script enforces its own per-trial `--timeout`. Background results auto-deliver; do not poll or periodically read progress logs. Continue useful work; use `wait` only when blocked. A named service is for viewers, not this finite loop.

Controls:

| Flag | Meaning |
| --- | --- |
| `--max-iterations 5` | Upper bound; loop may stop earlier when all train queries pass. |
| `--runs-per-query 3` | Repeat each query; higher counts reduce instability but cost more. |
| `--threshold 0.5` | Trigger-rate threshold for classifying positive versus negative. |
| `--holdout 0.4` | Stratified validation fraction; keep both classes represented where possible. |
| `--seed 42` | Reproducible split seed. |
| `--concurrency 2` | Bound parallel trial subprocesses. |
| `--timeout 60` | Seconds per trial. |
| `--regime warm` / `cold` | Cache regime; do not mix them in one comparison. |
| `--warm-wait 10` | Keep each of up to five warm-up probe processes alive this many seconds for native compression; readiness still requires two identical non-preview hints. |
| `--improver-model <selector>` | Optional different rewrite model; disclose it. Routing still uses `--model`. |
| `--results-dir <path>` | Keep each tuning experiment's results/report/logs together. |
| `--report auto` / `none` / `<path>` | Generate the normal report, skip it, or write at a chosen path. |
| `--verbose` | Retain useful progress and diagnostics. |

The loop splits queries into stratified train/validation partitions (default 60%/40%). Each iteration evaluates both, then asks a tools-disabled model to rewrite using **train failures only** and prior train history. Validation queries are hidden from that improver. It stops when all train queries pass or the iteration cap is reached, then chooses the description with the best validation passed count; ties prefer the earlier iteration. With `--holdout 0`, selection uses train performance and has no held-out evidence. The loop **never modifies SKILL.md**.

For a deliberate one-shot rewrite rather than the full loop:

```sh
uv run <skill-dir>/scripts/improve_description.py --skill <target-skill> --eval-results <workspace>/trigger-results.json --model <session-model> -o <workspace>/description-proposal.json
```

Only give the rewriter training results; do not feed validation queries/results back into its prompt. Optional `--history <history.json>` retains prior attempts and `--log-dir <path>` retains rewrite logs. The returned proposal is not evidence until independently evaluated.

To regenerate a saved loop report:

```sh
uv run <skill-dir>/scripts/generate_report.py <workspace>/trigger/<UTC-timestamp>/results.json -o <workspace>/trigger/<UTC-timestamp>/report.html --skill-name <skill-name>
```

The report is a file, not an automatically opened browser. Tell the user how to copy/open it.

## Read results honestly

Read `results.json`, the report, and necessary logs after completion. See `references/schemas.md` for exact contracts. Keep the following distinctions visible:

- Authored `description` versus the actual `rendered_hints` observed in each regime; examine a hint distribution rather than assuming one stable compressed phrase.
- Requested versus resolved models; unavailable models and provider errors are failures, not alternate-model evaluations.
- Positive misses versus negative false triggers; both matter. Good overall counts can hide a broken branch or permissive negatives.
- Per-query `triggers`, `valid_runs`, `trigger_rate`, `invalid_runs`, and `pass`. The pass rule is `(trigger_rate >= threshold) == should_trigger`, computed **only over valid runs**. With no valid runs, `pass` is `null` and the query is invalid, not a passed negative.
- Timeout/error trials and, when warm readiness was established, trials with a different hint (`invalid_runs.hint_mismatch`) are excluded from trigger-rate denominators. Keep invalid counts visible; a small surviving valid subset is weaker evidence, not improved reliability. The loop records per-iteration `warm_ready` and `hint_mismatches`; if readiness is false, describe mixed/unknown hints rather than a warm experiment.
- Hidden-source experiments carry the label `eligibility: "opt-in clone (hidden flags removed)"`. They do not prove installed hidden skills route autonomously.
- `stopped_because: all_train_passed` is not proof validation passed. Inspect train and validation separately and state the remaining errors.
- If no iteration had valid trials, the loop stops with `stopped_because: "infrastructure_failure"`, exits 2, and returns `best_description: null`. Inspect logs and fix the infrastructure; do not apply a description from that failed experiment.

The output calls the held-out partition `test` and may print `best_score` like “7/8 test.” Statistically, it is a **validation/model-selection set**, not an untouched final test: every iteration is scored on it and the best description is chosen by that score. Hiding it from the improver reduces direct leakage, but repeated selection still adapts to it. Do not report its selected score as unbiased generalization. If the user needs stronger evidence, reserve a separate fresh final set and evaluate the fixed chosen description once, without choosing another description on that score.

## Apply the chosen result

Only apply a non-null `best_description` from an experiment with valid trials. Show the current authored description and selected text side by side, the chosen iteration, regime, validation score, invalid counts, warm readiness/hint mismatches, and any eligibility change. Apply the selected text with `edit` only when appropriate to the user's requested tuning; do not copy the rendered compressed hint into the frontmatter merely because it was shown in a report. Preserve the skill name, body, and invocation policy.

Validate the model-invocable target:

```sh
uv run <skill-dir>/scripts/validate_skill.py <target-skill> --policy model
```

For a hypothetical clone experiment where the source remains user-invoked, validate the source with `--policy user` instead and say autonomous eligibility was not applied. If the experiment suggests a policy change, let the user explicitly choose it rather than silently changing it.

Inspect the chosen description's actual hint with the earlier `--hint-only` command after applying it. Validation enforces authored metadata, not routing success. Record the before/after and the limits of the evidence; then return to task-quality checks if the skill body or intended scope also changed.

## Cost and scope

Three trials for ~20 queries across train/validation and up to five iterations can mean many foreground model calls, plus rewrite and warm-up work. Start with a reviewed, meaningful set, bounded concurrency, and a small iteration cap. A cheaper model is acceptable for labelled smoke runs, never as an undisclosed substitute in final user-model routing comparisons.

Usage reports exclude **background description compression**; warm-up and rewriting are additional work, not free query samples. The paired executor metric `token_scope` is `assistant message_end usage; excludes background description compression`; trigger reports carry the corresponding exclusion note. Do not add cache-read tokens again to totals or claim a report contains every auxiliary cost.

Fresh processes and verified routing overlays isolate conversation/discovery state, not files, network, credentials, or native caches. Use safe queries, never print secrets or raw ambient prompts, and retain infrastructure failures so the optimization cannot reward broken execution as a negative result.
