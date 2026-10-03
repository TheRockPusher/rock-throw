<!-- Derived from Anthropic skill-creator (Apache-2.0); modified for OMP. -->
# Writing skills for OMP

## Contents

- [Start with the job, not the template](#start-with-the-job-not-the-template)
- [Anatomy and progressive disclosure](#anatomy-and-progressive-disclosure)
- [Frontmatter and provider compatibility](#frontmatter-and-provider-compatibility)
- [Choose an invocation policy](#choose-an-invocation-policy)
- [Write the description for its audience](#write-the-description-for-its-audience)
- [Inputs and bundled resources](#inputs-and-bundled-resources)
- [Writing style and completion gates](#writing-style-and-completion-gates)
- [Principle of Lack of Surprise](#principle-of-lack-of-surprise)
- [Develop from evidence](#develop-from-evidence)
- [Anti-patterns](#anti-patterns)
- [Pre-delivery checklist](#pre-delivery-checklist)
- [Sources and companion references](#sources-and-companion-references)

## Start with the job, not the template

A skill supplies optional procedural knowledge. Aim for a predictable process and a complete result, not identical wording on every run. Before drafting, identify the user's intended outcome, inputs, constraints, and observable success conditions. Read the current conversation, repository conventions, existing skill, and existing harnesses before asking the user for facts already available there.

Choose the right OMP surface first. Repository-wide conventions belong in context files or rules; a callable runtime API belongs in a tool; deterministic interception needs runtime integration. Read [OMP capabilities](omp-capabilities.md#surface-selection-matrix) when this distinction matters. A skill can teach or coordinate these surfaces but cannot create permissions or enforcement by describing them.

Select two or three realistic scenarios and expected results before writing extensive prose. Write the smallest useful draft, run it on those scenarios, and revise from evidence. Do not make a large interview, elaborate scaffolding, or a universal benchmark a prerequisite for a small skill.

## Anatomy and progressive disclosure

Use a flat discovered layout:

```text
skills/
  csv-cleaner/
    SKILL.md
    scripts/       # optional executable helpers
    references/    # optional instructions and technical reference
    assets/        # optional output templates and data
```

`SKILL.md` starts with YAML frontmatter, then Markdown instructions. The file name is exact. The directory and authored name agree; a raw name never contains a slash or backslash. Conventional discovery scans one level below each skills root, not arbitrary nested categories. See [OMP skills](omp://skills.md).

Keep three loading levels distinct:

1. **Metadata:** OMP advertises visible skill names and rendered description hints when skill-reading tooling is active. Hidden skills are excluded from that list.
2. **Body:** the full instructions are read on demand or injected by invocation/autoload.
3. **Resources:** references and assets are read only when needed; executable scripts can run without loading their source into model context.

Every visible description spends prompt tokens in sessions that advertise skills. Optional details belong in the body or resources, not in a permanent description. Progressive disclosure is not an excuse to hide mandatory steps.

Keep the main body below 500 lines and roughly 5,000 tokens unless a concrete need justifies more. These are authoring targets, not runtime quotas. Inline what every branch needs; move material behind a pointer when only some branches need it.

- Link every required resource directly from `SKILL.md`, at the step where it is used.
- Give each pointer a read condition: “For spreadsheet input, read the spreadsheet guide before parsing.”
- Keep reference reachability one hop from the main file. A folder is fine; a chain hiding core instructions is not.
- Give reference files longer than 100 lines a contents list near the top so ranged reads remain useful.
- Keep definitions beside their conditions and exceptions. Maintain one authoritative home for each rule or schema.
- For domain variants, put selection and the common workflow in the body, and separate variant-specific references. Read only the selected variant.

## Frontmatter and provider compatibility

Use explicit `name` and `description` even where a provider allows omission. Quote descriptions containing punctuation, especially colon-space, or use a correctly indented folded YAML scalar. Parse YAML; a regex check cannot establish scalar validity.

The [Agent Skills specification](https://agentskills.io/specification) defines:

| Field | Contract |
|---|---|
| `name` | Required, 1–64 characters. Prefer conservative ASCII lowercase alphanumeric words separated by single hyphens; match the directory name. |
| `description` | Required, nonempty string, at most 1,024 characters. |
| `license` | Optional license name or reference to a bundled license file. |
| `compatibility` | Optional environment-requirements string, at most 500 characters. Omit when unnecessary. |
| `metadata` | Optional string-to-string mapping. |
| `allowed-tools` | Optional, experimental space-separated string; support varies by host. Not a promised security boundary. |

OMP conventional scanners also recognize `disable-model-invocation` (normalized to `disableModelInvocation`), `hide`, and `enabled`. `enabled: false` skips discovery, unlike hiding. Skill `globs` and `alwaysApply` are metadata, not automatic activation controls. Permissively retained unknown keys do not imply runtime behavior.

| Discovery route | Frontmatter behavior relevant here |
|---|---|
| Native OMP directories, OMP extension packages, custom directories | Accept the conventional hiding flags; require a meaningful description. |
| Conventional marketplace plugin scanning | Accepts hiding flags; still author a description for portability and human use. |
| Agent Plugins standard | Closed set: `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`. Rejects `disable-model-invocation`, `hide`, `enabled`, `globs`, and `alwaysApply`; invalid skills are skipped, not merely hidden. |
| Skillshare publishing | Uses the same closed-set validation; default user-invoked frontmatter is incompatible as-is. Runtime scanning of installed skills and publishing validation are different stages. |

Do not add an Agent Plugins root manifest merely to package this repository: its default user-invoked skills need the conventional OMP route. Use an OMP `package.json` with `"omp": {}` and flat `skills/` instead. See [skills](omp://skills.md) and [package/install plumbing](omp://plugin-manager-installer-plumbing.md).

Do not invent frontmatter permissions. Omit `allowed-tools` unless its behavior is established for the target runtime. Document actual required capabilities and side effects in the body.

## Choose an invocation policy

Default to **user-invoked** in this repository unless the user deliberately requests autonomous discovery:

```yaml
---
name: csv-cleaner
description: "Clean CSV contacts and report the changes."
disable-model-invocation: true
---
```

The human runs `/skill:csv-cleaner <request>` when skill commands are enabled. Its description is a browsing summary, not a trigger advertisement.

For a **model-invocable** skill, omit hiding flags and write a discriminative routing description. This is a policy decision, not a side effect of rewriting prose. Evaluate explicit task execution separately from discovery behavior.

**Hiding is not access control.** A hidden skill remains readable through `skill://<name>`, invocable with `/skill:<name>`, and available for agent autoload. Preserve the user's policy in instructions rather than claiming the loader enforces a hard authorization boundary. Autoload is provenance, not proof that a human authorized side effects. See [runtime skill behavior](omp://skills.md).

A user-only workflow must not silently initiate another user-only workflow. If it needs that workflow, tell the human the `/skill:<name>` command and why it is needed. Shared knowledge can instead live in explicitly permitted reference files; reading a reference and initiating a workflow are distinct acts.

## Write the description for its audience

### User-invoked skills

Write one short, factual human-facing line describing the job and scope. Strip “Use when the user says…”, trigger lists, synonym piles, and implicit autonomous invocation promises. Keep the required field; hidden does not mean description-optional. A summary around 160 characters or shorter is usually enough.

### Model-invocable skills

Use third-person or compact verb-led wording. Front-load the capability, distinguishing inputs/outputs, and actual selection boundary. Give each distinct trigger branch one place; synonymous keywords are not new branches. Avoid universal “always use” language unless measured failures justify it without excessive false positives.

OMP does not necessarily show the entire authored description:

- The initial cold preview is at most 100 characters after whitespace collapse.
- For a longer description, OMP examines the first 99 characters for a sentence boundary. A complete first sentence of at least 40 characters can be retained; otherwise it cuts at a word boundary and adds an ellipsis.
- Background compression produces a routing hint of at most 12 words and 160 characters, cached from the compression prompt, name, and description. The selected hint is frozen for the session.

Make the first sentence stand alone as a precise routing hint of at most 100 characters. Do not bury the differentiating task in sentence three. Visible hints consume prompt tokens every session that advertises the skill list, even though the full body is lazy-loaded.

For positive and near-miss examples, rendered-hint inspection, and repeated trigger trials, read [description tuning](description-tuning.md). Tune actual model-invocable skills, not the automatic trigger rate of a hidden skill. A labelled opt-in clone tests hypothetical eligibility, not the original invocation policy.

## Inputs and bundled resources

### Interpret the appended request

OMP `/skill:<name> args` injects the body, adds `[Skill directory: <absolute path>]`, and appends optional literal `User: <args>` text. Use that appended text as the requested operation, inputs, and constraints. There is no skill-body variable or positional-argument substitution. The text is not automatically a shell argv vector, and invocation does not change cwd.

If the skill accepts named operations or flags, explain how to interpret the user text. If inputs are missing, look in supplied context/files first, then ask only for information genuinely unavailable. Do not treat input text as executable shell source.

### Resolve paths before running external programs

Define `<skill-dir>` as the physical absolute directory in `[Skill directory: …]`. Resolve a bundled path against that directory, not the user's cwd. Read references with `skill://<name>/<path>` using the exact discovered name; namespaced copies use their resolved runtime name.

Canonical Python command:

```sh
uv run <skill-dir>/scripts/x.py
```

Replace `<skill-dir>` with the actual path and quote it if it contains spaces. When no invocation directory is available, the native OMP `bash` tool can resolve the URI before handing it to uv:

```sh
uv run "$(realpath skill://<name>/scripts/x.py)"
```

External programs do not resolve internal URIs themselves. Resolve other file-backed URI arguments too. Do not rely on another external shell, a user/RPC bash route, or a URI cwd to reproduce the native tool's virtual filesystem. Use physical paths outside that surface. See [bash runtime](omp://bash-tool-runtime.md) and [bash tool](omp://tools/bash.md).

### Bundle only useful resources

- **Scripts:** deterministic or repeatedly recreated operations. Document when to run them, their inputs, outputs, dependencies, and failure behavior. Prefer an existing helper over generating equivalent code on every invocation.
- **References:** instructions, schemas, rubrics, and branch-specific technical details. Keep each file focused and linked with a read condition.
- **Assets:** files copied or filled into the delivered artifact, such as templates or fixture data. Do not mislabel instructional reference as output assets.

Python entry scripts use Python 3.11 or later and PEP 723 inline metadata:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
```

Declare any needed dependencies and version ranges explicitly, and run with uv. Library modules need no entry-script metadata. Loading a file into an eval kernel does not provision dependencies from this block. Do not install packages globally for convenience or silently return empty success after missing inputs, denied access, or infrastructure failure.

## Writing style and completion gates

Prefer imperative instructions and plain language. State the condition before the action. Use real input/output examples when they disambiguate the task; do not decorate every section with symmetrical lists or a forced template.

Explain briefly why a non-obvious constraint matters so the model can generalize. Avoid heavy-handed all-caps requirements for ordinary editorial judgment; retain exact requirements for fragile sequences, safety boundaries, data contracts, and output formats. Start with a draft, then examine it with fresh eyes and remove prose that does not change a decision.

Choose degrees of freedom deliberately:

| Freedom | Appropriate use |
|---|---|
| High | Interpreting intent, weighing alternatives, contextual prose revision. |
| Medium | Preferred patterns with parameters, realistic cases, adaptable output sections. |
| Low | Exact schemas, isolation, destructive actions, benchmark comparability, required script sequences. |

End each phase with a checkable, exhaustive done condition. “Review the output” is an action, not a gate; “Done when every requested column is present and each rejected row has a recorded reason” is a gate. Include every named outcome so the agent does not stop at an attractive intermediate artifact.

Separate ordered workflow steps from reference material. Keep each concept in one authoritative location, link instead of duplicating it, and look up cheap environment facts instead of caching them in prose. Prefer a positive target to negation-only steering, while retaining genuine safety prohibitions.

## Principle of Lack of Surprise

This goes without saying, but skills must not contain malware, exploit code, or any content that could compromise system security. A skill's contents should not surprise the user in their intent if described. Don't go along with requests to create misleading skills or skills designed to facilitate unauthorized access, data exfiltration, or other malicious activities. Things like a "roleplay as an XYZ" are OK though.

Describe consequential side effects, data access, network dependencies, and required authorization honestly. Keep secrets out of bundled files, fixtures, transcripts, and review artifacts. A named optional procedure is not permission to alter unrelated user configuration or data.

## Develop from evidence

Use the same organic task and inputs for independent candidate/baseline runs. A new skill compares with no skill; an edited skill compares with a pre-edit snapshot. Keep authoring conversation, hidden judge rubric, and other candidates out of execution context. Task subagents inheriting skills are not by themselves a no-skill isolation guarantee.

Grade actual outputs and tool/file-reading evidence, not the candidate's claim that it followed instructions. Use deterministic checks for exact properties and human or independent rubric review for qualitative ones. Subjective work can still benefit from blind comparison; do not force a meaningless binary assertion just to produce a percentage.

Inspect navigation and traces as well as final artifacts: missed references, wasted steps, recurring helper generation, and unsupported assumptions reveal causes. Revise the general workflow rather than add exceptions for individual eval prompts. Add fresh cases before claiming broad effectiveness. Preserve earlier runs, record expectation changes, and do not present a repeatedly consulted holdout as untouched final evidence. Follow [evaluation](evaluation.md) for the runnable procedure.

## Anti-patterns

- Explaining ordinary concepts the model already knows or adding no-op advice such as “be clear.”
- Trigger-heavy metadata for hidden skills, vague routing hints, or promotional first-person descriptions.
- Required guidance hidden behind vague pointers, reference chains, or long files without navigation.
- Duplicated rules, stale environment facts, unexplained jargon, and compressed fragments that lose meaning.
- Many equivalent tool choices without one known-good default or a justified escape hatch.
- Mandatory scripts, PRs, multi-model panels, or extensive benchmarks for every small instructions-only change.
- Overfitting one transcript, converting one-off preferences into permanent rules, or declaring success from self-report.
- Opaque dependencies, brittle personal install paths, global configuration changes for an eval, and secrets in evidence.
- Suppressing required-input or permission failures with fake defaults, or reporting missing metrics as zero.
- Treating a valid document, a build result, or an undifferentiating pass rate as proof of the requested behavior.

## Pre-delivery checklist

- [ ] YAML parses; the name is a matching valid slug; the required description is present.
- [ ] Frontmatter is accepted by the chosen provider, and the intended invocation policy is preserved.
- [ ] The description addresses the human or model audience appropriately; model routing uses a self-contained first sentence.
- [ ] Core steps and every named outcome have observable, exhaustive done conditions.
- [ ] Every bundled reference exists, has a read condition, and is reachable directly from `SKILL.md`.
- [ ] The body meets the size targets or explains the exception; references over 100 lines have navigation.
- [ ] Each rule/schema has one authoritative home; cheap environment facts are looked up rather than cached.
- [ ] Scripts are justified, documented, dependency-aware, uv-run where Python, and fail clearly on required errors.
- [ ] Only real OMP APIs and paths are used; optional capabilities and interactive-only operations are guarded.
- [ ] Real task execution, baseline separation, objective checks, human judgments, and measured cost are distinguishable evidence.
- [ ] Iterations preserve earlier evidence, redact secrets, stop only owned processes, and leave unrelated config/data intact.
- [ ] Existing human docs/index/change notes and actual installation/invocation instructions match the delivered behavior.
- [ ] Structural validation and `omp read skill://<name>` discovery checks are recorded if exercised; only exercised checks are claimed.
- [ ] A draft-only request is labelled draft-only; missing prerequisites or unverified requirements are stated, not hidden.

## Sources and companion references

The portable format comes from the [Agent Skills specification](https://agentskills.io/specification). The workflow and lack-of-surprise principle are derived from Anthropic's skill-creator; editorial discipline also draws on [Matt's writing-for-agents](https://github.com/mattpocock/skills) and [pstack](https://github.com/cursor/plugins/tree/main/pstack). Host-specific conventions from those sources are not OMP contracts.

- [OMP skills](omp://skills.md): loading, frontmatter, invocation, URI behavior, and collisions.
- [OMP capabilities](omp-capabilities.md): live tool idioms and surface selection.
- [Skill templates](../assets/skill-template.md): minimal user-invoked and model-invocable starting points.
- [Evaluation](evaluation.md): paired execution, evidence, grading, and human review.
- [Description tuning](description-tuning.md): rendered routing hints and selection tests.
