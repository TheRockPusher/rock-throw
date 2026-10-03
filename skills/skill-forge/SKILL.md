---
name: skill-forge
description: "Create, improve, and evaluate OMP skills: draft SKILL.md, run paired with/without-skill evals, review results, tune descriptions."
disable-model-invocation: true
---

# Skill Forge

A skill for creating new OMP skills and iteratively improving them. It is an OMP-native port of Anthropic's `skill-creator`, renamed so the two are never confused.

Invoke with `/skill:skill-forge <request>`. The appended `User:` text is the user's request. Define `<skill-dir>` once as the absolute directory in the invocation's `[Skill directory: …]` line; if absent, resolve it with `realpath skill://skill-forge`. Resolve this skill's bundled paths against that directory. External programs cannot open internal URIs: give `uv` the resolved filesystem path, never a `skill://` URI.

At a high level, the process goes like this:

- Decide what you want the skill to do and roughly how it should do it.
- Write a draft of the skill.
- Create a few realistic test prompts and run paired with-skill and baseline trials.
- Help the user evaluate the results both qualitatively and quantitatively.
- Rewrite the skill based on feedback and meaningful benchmark findings.
- Repeat until satisfied; expand the test set to check generalization.

Your job is to figure out where the user is in this process and help them progress. Maybe they want a new skill; maybe they already have a draft and can go straight to evaluation. They may want just evaluation, or description tuning. Always be flexible: if they say “I don't need a bunch of evaluations, just vibe with me,” do that instead. Description tuning is a separate, optional stage for model-invocable skills only.

Use the available OMP tools and their live schemas. Optional `ask`, `todo`, or `eval` facilities may be disabled; do not claim they ran. Report a missing required facility instead of silently substituting a different model or runtime.

## Communicating with the user

People have a wide range of familiarity with coding jargon. Pay attention to context cues to understand how to phrase your communication:

- “Evaluation” and “benchmark” are borderline, but OK.
- For “JSON” and “assertion,” look for serious cues that the user knows what those mean before using them without explaining them.

It's OK to briefly explain terms if you're in doubt. An assertion is simply a specific, checkable statement about a successful result.

## Creating a skill

### Capture intent

Start by understanding the user's intent. The current conversation might already contain a workflow the user wants to capture (e.g., “turn this into a skill”). If so, extract answers from the conversation history first — the tools used, the sequence of steps, corrections the user made, input/output formats observed. The user may need to fill the gaps, and should confirm before proceeding to the next step.

1. What should this skill enable the agent to do?
2. When should it be used? What user phrases or contexts matter?
3. What's the expected output format?
4. Should we set up test cases to verify it works? Skills with objectively verifiable outputs (file transforms, data extraction, code generation, fixed workflow steps) benefit from test cases. Skills with subjective outputs (writing style, art) often don't need them. Suggest the appropriate default, but let the user decide.
5. **Invocation policy:** default to user-invoked (`disable-model-invocation: true`) in this repository unless the user wants autonomous use. User-invoked descriptions are human-facing summaries; model-invocable descriptions are routing hints. Hiding is not access control: explicit invocation and reads remain possible.
6. **Is a skill the right surface?** Read `references/omp-capabilities.md` before choosing a skill over a rule, tool, extension, agent, or MCP integration. A skill teaches a reusable procedure; it does not enforce runtime policy.

### Interview and research

Proactively ask questions about edge cases, input/output formats, example files, success criteria, and dependencies. Wait to write test prompts until you've got this part ironed out.

Check available research tools and MCPs. If useful for searching docs, finding similar skills, or looking up best practices, research independent questions in parallel with a `task` batch of `scout` agents after scoping the work; otherwise research inline. Come prepared with context to reduce burden on the user. Use `ask` only for genuinely needed structured choices, not information available from files or tools; ordinary conversation is fine for open-ended discussion.

### Where the skill lives

If the current working directory is a skills/plugin repository (`package.json` has an `omp` entry or there are existing `skills/*/SKILL.md` files), use its `skills/` root. Otherwise ask the user to choose project-local `.omp/skills/` or personal `~/.omp/agent/skills/`. Keep one skill directory directly under the chosen root, with `name` matching that directory.

For an existing skill, preserve its name. If installed read-only, edit a writable copy and integrate it into the intended root when finished. Before editing in improve mode, take the persistent snapshot described in `references/evaluation.md`.

### Write SKILL.md

Read `references/writing-skills.md` before authoring, and `assets/skill-template.md` when starting a new skill. Based on the interview, fill in:

- **name:** the skill identifier, lowercase letters/digits with single hyphen separators.
- **description:** what it does; for model-invocable skills, also the precise contexts in which it should be selected. Read `references/description-tuning.md` for OMP's preview/compression limits. Do not put crucial routing information only in the body.
- **compatibility:** required tools or dependencies, if needed.
- **body:** instructions, examples, output formats, and clear pointers saying when to read supporting files.

A skill has required YAML frontmatter and Markdown instructions in SKILL.md, plus optional bundled resources: executable `scripts/`, on-demand `references/`, and output resources in `assets/`. Metadata advertises eligible skills; the body loads when invoked or read; resources load as needed. OMP may display only a short rendered description hint, not the whole authored description.

Keep the body lean (under 500 lines is a useful general target). Move detail to one-hop references with clear read conditions; give long references a contents list. For multiple domains or frameworks, organize by variant so the agent reads only the relevant material.

Prefer imperative instructions. Define output formats explicitly and include useful input/output examples. Try to explain why things are important instead of piling on rigid directives. Make the skill general, not super-narrow to specific examples. Write a draft, then look at it with fresh eyes and improve it.

**Principle of lack of surprise:** Skills must not contain malware, exploit code, or any content that could compromise system security. A skill's contents should not surprise the user in their intent if described. Don't go along with requests to create misleading skills or skills designed to facilitate unauthorized access, data exfiltration, or other malicious activities. Things like a “roleplay as an XYZ” are OK though. Read the fuller authoring guidance in `references/writing-skills.md` when considering scope or side effects.

Validate the target (here `<target-skill>` is the skill being authored, not necessarily this skill's directory):

```sh
uv run <skill-dir>/scripts/validate_skill.py <target-skill> --policy user
```

Use `--policy model` instead when autonomous selection is intended. Fix errors and review warnings before running evaluations.

### Test cases

After writing the draft, come up with 2–3 realistic test prompts — the kind of thing a real user would actually say. Share them with the user: “Here are a few test cases I'd like to try. Do these look right, or do you want to add more?” Then run them.

Save them to the target's `evals/evals.json`. Don't write assertions yet — just prompts, descriptive names, expected results, and any fixtures. Draft assertions while the runs are in progress.

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "name": "realistic-workflow",
      "prompt": "The user's concrete task request",
      "expected_output": "Description of a successful result",
      "files": []
    }
  ]
}
```

Read `references/schemas.md` before writing evaluation or grading JSON; `references/evaluation.md` covers prompt design, fixtures, and the full procedure.

## Running and evaluating test cases

This is one continuous sequence, not a stopping point after launching runs. Read `references/evaluation.md` before starting. Use the default persistent workspace `${XDG_STATE_HOME:-$HOME/.local/state}/skill-forge/<skill-name>/` or an explicit `--workspace`, outside any repo or skills root. Keep results in fresh `iteration-N/` directories.

### Step 1: Launch both arms together

Use one `bash` call with `async: true` and `timeout: 0` to launch `scripts/run_evals.py`; the script enforces per-run timeouts, and OMP clamps nonzero outer timeouts to 3600 seconds. It runs independent headless OMP processes, not in-session executor subagents. Pass the current session's model selector from the system prompt via `--model` so both arms match the user's experience:

```sh
uv run <skill-dir>/scripts/run_evals.py --skill <target-skill> --workspace <workspace> --iteration 1 --model <session-model> --runs 1 --concurrency 3
```

A new skill gets `with_skill` and `without_skill`. An existing skill gets `with_skill` and `old_skill` by adding `--baseline-skill <snapshot-skill-dir>`. Launch both arms in the same call, never one now and the other later. Results auto-deliver; don't poll. Keep working on assertions while it runs.

The default is **explicit-invocation simulation** (`--with-skill-mode invoke`), not a discovery score: the runner reproduces OMP's skill-body injection. Use `--with-skill-mode discover` only to measure autonomous selection plus task execution, labelled as discovery mode with a model-visible frozen copy. `--env isolated` is the default; `--env ambient` includes ordinary environment influences and must be labelled. Neither is an OS/filesystem/network security sandbox.

### Step 2: Draft assertions meanwhile

Draft quantitative assertions and explain them to the user. If assertions already exist, review them and explain what they check.

Good assertions are objectively verifiable and have descriptive names — they should read clearly in the benchmark viewer so someone glancing at the results immediately understands what each one checks. Subjective skills are better evaluated qualitatively; don't force assertions onto things that need human judgment.

Update the target's eval set and each iteration's `eval_metadata.json` after those files exist. The runner persists transcripts, `run.json`, and measured `timing.json`; do not estimate usage or replace it with grader metrics.

### Step 3: Grade completed runs

Read `roles/grader.md`, then dispatch a `task` batch with one fresh grader per completed run and a strict per-item `outputSchema` from `references/schemas.md`. The complete call example is in `references/evaluation.md`. Graders inspect actual artifacts and transcripts, write each run's `grading.json`, and yield the same object. Use deterministic scripts for assertions that can be checked programmatically, rather than eyeballing them.

Read `agent://<id>` for structured grader results after automatic delivery; inspect failure/schema status. Executor runs whose outcome is not `completed` are infrastructure outcomes, not automatic assertion failures or successes: retain them in benchmark `runs[]`, list their IDs in `metadata.excluded_runs`, warn, and exclude them from all `run_summary` statistics. Contaminated `without_skill` runs remain in statistics with prominent warnings; inspect `contamination.read_skill` and make no clean-control conclusions from those arms.

### Step 4: Aggregate, analyze, and launch the viewer

```sh
uv run <skill-dir>/scripts/aggregate_benchmark.py <workspace>/iteration-1 --skill-name <name> --skill-path <target-skill>
```

Dispatch a strict-schema analyst `task` using `roles/analyzer.md` in benchmark mode. Read its structured notes, merge them into `benchmark.json`'s `notes`, then launch the viewer. Preserve measured metrics and distinguish executor cost from grading/analysis cost. `timing.json`'s `token_scope` explains what is counted; background description compression is excluded.

Use a named `bash` service, `name: "skill-review-<slug>-1"`, with `ready: {port: 3117}` (no `async` or command timeout). Here `<slug>` is the first 20 characters of the skill name, keeping the service label within OMP's 48-character limit:

```sh
uv run <skill-dir>/scripts/generate_review.py <workspace>/iteration-1 --skill-name <name> --benchmark <workspace>/iteration-1/benchmark.json --host 127.0.0.1 --port 3117
```

For later iterations add `--previous <workspace>/iteration-(N-1)`. The viewer uses `assets/viewer.html`; do not write replacement HTML.

Tell the user the URL, not “I opened your browser.” On a remote host, provide `ssh -L 3117:127.0.0.1:3117 <user>@<host>`, then have them open http://localhost:3117. Explain that Outputs shows artifacts, grades, and feedback, while Benchmark shows the quantitative comparison.

If serving/tunnelling is impractical, use the same command with `--static <workspace>/iteration-1/review.html`; have the user copy/open it locally and return the downloaded feedback file. Tiny evaluations can use direct conversation or a genuinely needed structured `ask` choice instead.

### Step 5: Read feedback

When the user tells you they're done, read the iteration's `feedback.json`. `visited: false` with empty feedback means **not reviewed**, not approval; even `status: complete` alone doesn't prove every output was inspected. Focus improvements on concrete complaints and clarify skipped cases only when needed.

Stop the owned viewer with `write proc://skill-review-<slug>-1/kill`, omitting `content` and using the exact same service label. Never kill an unrelated listener to free the port.

## Improving the skill

You've run the cases, the user has reviewed them, and now you need to make the skill better based on feedback.

### How to think about improvements

1. **Generalize from the feedback.** The big picture thing that's happening here is that we're trying to create skills that can be used many times across many different prompts. Here you and the user are iterating on only a few examples over and over again because it helps move faster. The user knows these examples in and out and it's quick for them to assess new outputs. But if the skill you and the user are codeveloping works only for those examples, it's useless. Rather than put in fiddly overfitty changes, or oppressively constrictive directives, if there's some stubborn issue, you might try branching out and using different metaphors, or recommending different patterns of working. It's relatively cheap to try and maybe you'll land on something great.
2. **Keep the prompt lean.** Remove things that aren't pulling their weight. Make sure to read the transcripts, not just the final outputs — if it looks like the skill is making the model waste a bunch of time doing things that are unproductive, you can try getting rid of the parts of the skill that are making it do that and seeing what happens.
3. **Explain the why.** Try hard to explain the **why** behind everything you're asking the model to do. Today's LLMs are smart. They have good theory of mind and when given a good harness can go beyond rote instructions and really make things happen. Even if the feedback from the user is terse or frustrated, try to actually understand the task and why the user is writing what they wrote, and what they actually wrote, and then transmit this understanding into the instructions. If you find yourself writing ALWAYS or NEVER in all caps, or using super rigid structures, that's a yellow flag — if possible, reframe and explain the reasoning so that the model understands why the thing you're asking for is important. That's a more humane, powerful, and effective approach.
4. **Look for repeated work across test cases.** Read the transcripts from the test runs and notice if the executor agents all independently wrote similar helper scripts or took the same multi-step approach to something. If all three test cases resulted in an agent writing the same document-generation or chart-building helper, that's a strong signal the target skill should bundle that script. Write it once, put it in the target's scripts directory, and tell the skill to use it. This saves every future invocation from reinventing the wheel.

Take your time and really mull things over. I'd suggest writing a draft revision and then looking at it anew and making improvements. Really do your best to get into the head of the user and understand what they want and need.

### The iteration loop

1. Apply your improvements and validate the skill.
2. Rerun all test cases into a new `iteration-<N+1>/`, including baselines. For a new skill, the baseline stays `without_skill`. For an existing skill, choose the original snapshot or a previous-version snapshot deliberately and state which comparison you're making; never overwrite the original snapshot.
3. Launch the reviewer with `--previous` pointing at the prior iteration.
4. Wait for the user to review and tell you they're done.
5. Read new feedback, improve again, repeat.

Keep going until the user is happy, all relevant outputs were explicitly reviewed with no remaining concerns, or you're not making meaningful progress. Expand the test set to check changes beyond the familiar examples.

## Advanced: blind comparison

For “is the new version actually better?”, read `references/evaluation.md`'s blind-comparison procedure. This also works for new-skill versus no-skill comparisons. Use `scripts/prepare_blind.py` to randomize neutral A/B output directories, then a strict-schema comparator `task` reading `roles/comparator.md`. Do not show the comparator the key, arm identities, skills, or transcripts. Unblind only afterward, then use `roles/analyzer.md` in post-hoc mode to explain evidence-backed differences; a no-skill side has null instruction-following fields marked “not applicable.” This is optional; human review is usually sufficient.

## Description tuning

Only offer autonomous trigger tuning for **model-invocable** skills. For user-invoked skills, review the human-facing summary instead. An explicitly requested opt-in clone experiment tests hypothetical eligibility, not the installed user-only skill; never silently change policy.

Read `references/description-tuning.md` before designing trigger queries or using `scripts/run_loop.py`. It covers realistic positives and near-miss negatives, user review, OMP's cold preview and warm compressed hints, validation-set selection, and applying a result. The loop never edits SKILL.md for you.

## Finishing

Integrate the complete skill into the chosen active skills root; update its README/index if the repository has one. Validate with the intended policy, then check discovery from a cwd where that root is active:

```sh
uv run <skill-dir>/scripts/validate_skill.py <target-skill> --policy user
omp read skill://<name>
```

Use `--policy model` for model-invocable skills. The discovery command should print the intended SKILL.md; an “Available: …” list instead means it did not resolve. Tell the user where the skill lives and how to invoke it with `/skill:<name> <request>`. A model-invocable skill is additionally eligible for autonomous selection. Finish with an installed, discoverable directory, not an archive.

## Reference files: when to read

- `references/writing-skills.md` — before drafting or revising instructions, metadata, or resources.
- `references/omp-capabilities.md` — before choosing a surface or using unfamiliar OMP orchestration/tools.
- `assets/skill-template.md` — when starting a new skill.
- `references/schemas.md` — before writing eval JSON, grade files, benchmark notes, or strict role schemas.
- `references/evaluation.md` — before running paired evals, dispatching graders, reviewing outputs, or comparing blindly.
- `references/description-tuning.md` — before model-invocable trigger evaluation or tuning.
- `roles/grader.md` — before evidence-based assertion grading.
- `roles/comparator.md` — before blind output comparison.
- `roles/analyzer.md` — before benchmark observations or unblinded causal analysis.

The core loop is **understand → draft/edit → run paired trials → grade and show the human → improve → repeat → integrate**. If `todo` is available, use parent-owned phases such as intent/research, draft/validate, evals/grade, viewer/human review, revise, and finish so review doesn't get lost between tool calls.
