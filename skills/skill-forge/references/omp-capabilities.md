<!-- Derived from Anthropic skill-creator (Apache-2.0); modified for OMP. -->
# OMP capabilities for skill authors

## Contents

- [Scope and availability](#scope-and-availability)
- [Skill contract and invocation](#skill-contract-and-invocation)
- [Internal URLs](#internal-urls)
- [Bundled programs](#bundled-programs)
- [Ordinary tool idioms](#ordinary-tool-idioms)
- [Orchestration recipes](#orchestration-recipes)
- [User choices and progress](#user-choices-and-progress)
- [Surface-selection matrix](#surface-selection-matrix)
- [Packaging and discovery pitfalls](#packaging-and-discovery-pitfalls)
- [Optional features and further reading](#optional-features-and-further-reading)

## Scope and availability

This reference targets OMP 18.5.x. A skill is passive guidance: it does not enable tools, grant authorization, register APIs, or enforce hooks. Tools can be disabled, restricted by session policy, or exposed as discoverable `xd://` devices rather than top-level calls. Eval backends, browser, LSP, task isolation, memory, and interactive UI have their own prerequisites.

Use the current tool roster and exact live schemas. Read the matching device/helper docs before first use. If a required facility or selected model is unavailable, report the missing prerequisite; do not claim it ran or silently substitute another runtime/model. Optional branches can be skipped only when the requested deliverable does not depend on them.

Examples below illustrate documented interfaces, not a promise that every feature is enabled in the current session. Follow the assignment's verification policy: a skill does not authorize builds, tests, installs, or global configuration changes by itself.

Sources: [custom tools](omp://custom-tools.md), [eval](omp://tools/eval.md), [task](omp://tools/task.md).

## Skill contract and invocation

Author `skills/<name>/SKILL.md` with frontmatter at line one, explicit matching `name`, and a meaningful nonempty `description`. Use a lowercase ASCII hyphen-separated slug. The default here is `disable-model-invocation: true`, with a short human-facing description.

When skill commands are enabled, `/skill:<name> request text`:

1. Loads the discovered file and strips frontmatter.
2. Embeds the body with a user-invocation announcement.
3. Adds `[Skill directory: <absolute base directory>]` and relative-resource guidance.
4. Appends optional literal `User: request text`.

Interpret that appended text as the request and constraints. Skills do not perform variable or positional-argument template substitution. Invocation does not change cwd. A whitespace-delimited skill token can also appear inside prose; OMP removes it and passes the surrounding prose as arguments, subject to the documented command/sigil exclusions.

Hidden skills are omitted from model advertisement, **not protected from access**. `read skill://<name>`, `/skill:<name>`, and agent `autoloadSkills` can still load them. Autoload uses a provenance-only message, not a claim that the human invoked the skill. Do not infer side-effect authorization from every load, or silently initiate another user-only workflow; give the human its actual command instead.

Skills do not become rules by setting `globs` or `alwaysApply`. Task children receive discovered skills; there is no per-task skill-pinning field. Sharing a skill list is not isolation for a no-skill benchmark. See [skills](omp://skills.md) and [task agent discovery](omp://task-agent-discovery.md).

## Internal URLs

Internal URLs identify runtime resources. They are not universally filesystem paths for external programs. Copy real returned IDs, discovered names, and edit tags; do not invent them. Use bounded ranges when reading large resources.

| Address or operation | Purpose | Boundary |
|---|---|---|
| `skill://<name>` | `read` opens the skill's `SKILL.md`. | Shell filesystem/glob operations treat the bare URI as the directory; use `/SKILL.md` for the file there. |
| `skill://<name>/<path>` | Read a bundled reference, script, template, or asset. | Exact discovered name; no absolute asset paths or parent traversal. |
| `skill://<namespace>/<name>/<path>` | Access a runtime namespaced skill copy. | Namespace is assigned by discovery, not authored into the raw name. |
| `local://report.md` | Session-shared scratch files; readable/writable/editable and usable by eval file helpers. | Task children share the parent's local root; not a permanent installation or repository. |
| `artifact://<id>:20-80` | Read full spilled tool output with pagination. | Immutable; use actual returned IDs. `:raw:20-80` omits anchors/prefixes. |
| `agent://<id>` | Inspect live status/output or retained published output. | Prefer structured JSON fields; JSON presence alone does not establish schema validity. |
| `agent://<id>/reports/0/data` | Extract a structured result field. | Slash paths extract JSON; dot-qualified IDs identify nested children. |
| `write agent://<id>` | Message an existing peer/worker; parked agents can revive. | Message the agent itself, not a JSON extraction path. |
| `write agent://all` | Broadcast to visible live peers. | Not a synchronization barrier or ownership contract. |
| `history://`, `history://<id>` | Find registered transcripts and inspect retained work. | Read-only; do not guess agent IDs. |
| `proc://`, `proc://<id>` | Inspect caller-visible jobs and services. | Inspection does not consume delivery or replace a wait barrier. |
| `write proc://<id>/kill` | Cancel owned work or stop a service. | Omit content; cancellation is not reversible pause. |
| `write proc://<service>` | Send text to named-service stdin; empty text sends Enter. | Not arbitrary stdin for ordinary finite background jobs. |
| `write proc://<service>/mode` | Set `persist`, `session`, or `detached` service lifecycle. | Runtime/ownership constraints apply. |
| `omp://skills.md`, `omp://tools/task.md` | Built-in OMP reference documentation. | Documentation, not bundled executable code. Read only relevant sections. |
| `xd://<device>` | Discover/read mounted device docs and schema. | Availability depends on the live session. |
| `write xd://<device>` | Dispatch JSON arguments in `write.content`. | Underlying approval tier still applies; not a shell command. |
| `xd://eval/agents`, `xd://eval/judge`, `xd://eval/helpers`, `xd://eval/browser` | Persistent eval helper documentation. | Read before using corresponding helpers. |
| `rule://<name>` | Read an applicable domain rule. | Rule selection and enforcement depend on the rule type. |
| `memory://root`, `memory://<id>` | Read backend-specific memory artifacts/rows. | Backend and session scope matter; not authoritative current source. |
| `mcp://<uri>` | Read connected server resources. | Connected service and permissions required. |
| `pr://<N>/diff/all`, `issue://<N>` | Read GitHub material through the runtime. | Use actual repository/issue identity and cite retrieved evidence. |
| `ssh://host/path` | Configured POSIX remote UTF-8 file operations. | Encode literal colon, question mark, and hash as `%3A`, `%3F`, `%23`. |

Asset containment differs by provider: strict package providers also realpath-check their roots. Do not present every skill URI as a universal symlink sandbox. See [read](omp://tools/read.md), [write](omp://tools/write.md), [skills](omp://skills.md), and [wait](omp://tools/wait.md).

## Bundled programs

External programs receive argv literally; they do not automatically resolve internal URLs. Define `<skill-dir>` as the physical absolute directory from invocation, then run:

```sh
uv run <skill-dir>/scripts/x.py
```

Replace the symbolic directory with the actual path; quote spaces. In the **native OMP bash tool**, an alternative is:

```sh
uv run "$(realpath skill://<name>/scripts/x.py)"
```

The embedded shell/coreutils resolves `realpath` before uv opens the script. Resolve other external-program input paths too, including file-backed `local://` arguments. Do not give an external program an unresolved skill URI, use URI cwd for it, or put the resolution inside another external shell that lacks OMP's virtual filesystem. User/RPC shell execution is a different surface; use physical paths there. Named services/PTYS require physical cwd.

Python entry scripts declare Python 3.11+ and dependencies with PEP 723:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
```

Use explicit version ranges for real dependencies. Run dependency-bearing programs through uv rather than mutating a global environment. Library modules need no entry metadata. A `%load` cell can load a local-backed internal URI into eval, setting file/import context, but **does not** install dependencies from PEP 723 metadata. This repository uses uv for Python dependency management; dependency-free eval helpers avoid an extra provisioning path.

See [bash runtime](omp://bash-tool-runtime.md), [bash](omp://tools/bash.md), [eval scripts](omp://tools/eval.md), and [Python runtime](omp://python-repl.md).

## Ordinary tool idioms

| Need | Preferred idiom |
|---|---|
| Unknown behavior/location | Start with descriptive `find`, scoped to a known subsystem. Weak scores are not absence evidence. |
| Known literal, regex, symbol | `grep`; read the returned ranges before editing. |
| Known names/structure | `glob`, not semantic search or shell listings. |
| Source, static URL, image, document, archive, SQLite | `read`; use ranges, and reread explicitly named omissions in structural summaries. |
| Existing file changes | Follow the live `edit` mode; hashline mode requires observed snapshot tags and original line numbers. Re-read after stale-tag/intervening-change errors. |
| New file/full replacement | `write`; never replace a full file from a truncated projection. |
| Real executable or short factual command | `bash`, with physical cwd and finite timeout for finite work. Use specialized tools for file/search/edit operations. |
| Primary-source web research | `web_search` for unknown URLs; `read` for known URLs; cite actual primary sources. |
| Authenticated/interactive/JS page | Read `xd://eval/browser`, then use eval's global `browser`; reobserve after navigation/rerender. |
| Semantic navigation/rename | Read `xd://lsp`; check available servers and exact operation defaults. |
| Structural transformation | Read `xd://ast_edit`; preview, inspect parse issues, then resolve or reject. Preview is not an applied change. |

LSP rename can apply by default; whole-workspace diagnostics can run real checkers. Respect verification restrictions before dispatching. Optional `ast_grep` is disabled by default; parse failures invalidate confident absence claims. AST edit previews require a later `write xd://resolve` with a reason to apply, or `xd://reject` to discard. Narrow the target paths.

Browser is an eval helper, not a standalone tool. Direct host browser calls do not produce ordinary tool-call events, so tool hooks and trace-based grading may need different evidence. Browser availability cannot be created by a skill instruction.

Exact contracts: [find](omp://tools/find.md), [grep](omp://tools/grep.md), [glob](omp://tools/glob.md), [read](omp://tools/read.md), [edit](omp://tools/edit.md), [write](omp://tools/write.md), [web search](omp://tools/web_search.md), [LSP](omp://tools/lsp.md), [AST edit](omp://tools/ast-edit.md).

## Orchestration recipes

### Task batch with explicit shared context and output contract

Use independent slices only when they justify fan-out. Set ownership/interfaces first, supply complete requirements, and choose the most specific available agent. General work omits the `agent` field; do not specify the generic default's name.

Illustrative `task` arguments for two independent read-only reviews:

```json
{
  "context": "Review the proposed skill at skill://csv-cleaner. Return evidence-backed findings; do not edit files or run builds, tests, linters, or formatters. Each finding must identify its source and impact.",
  "tasks": [
    {
      "name": "ReviewIntent",
      "agent": "reviewer",
      "task": "Read SKILL.md. Review whether its input, outcome, side-effect, and invocation contracts are internally consistent. Return only findings about those contracts.",
      "solutionSpace": "Contract inconsistencies are open; no known defect.",
      "outputSchema": {
        "type": "object",
        "properties": {"findings": {"type": "array", "items": {"type": "string"}}},
        "required": ["findings"],
        "additionalProperties": false
      },
      "schemaMode": "strict"
    },
    {
      "name": "ReviewResources",
      "agent": "reviewer",
      "task": "Read SKILL.md and its bundled references. Review reference reachability, read conditions, and duplicated or contradictory resource guidance. Return only findings about resource navigation.",
      "solutionSpace": "Resource-navigation failure modes are open; no known defect.",
      "outputSchema": {
        "type": "object",
        "properties": {"findings": {"type": "array", "items": {"type": "string"}}},
        "required": ["findings"],
        "additionalProperties": false
      },
      "schemaMode": "strict"
    }
  ]
}
```

Replace the example's discovered name with the real target before dispatch. `outputSchema` and `schemaMode` are **per item**. Strict schema mode fails invalid output; permissive mode can return invalid data after retries with warnings. Check validation status and errors, not just JSON presence. `solutionSpace` describes uncertainty/openness, not work size or duration.

Children do not inherit the parent's conversation or eval variables. Pass complete assignments and relevant repository rules explicitly; do not assume `AGENTS.md` or appended-system instructions reach every worker. Share large data via `local://` instead of repeating it inline.

Per-item model selection uses real available selectors; `@default` means the parent's live model. Requested unresolved selectors fail preflight. Task item `tools` names **parent eval-defined tools**, not an arbitrary built-in allowlist. Durable tool restrictions belong in custom agent frontmatter or runtime policy. Isolation fields exist only when isolation is enabled and applicable; ordinary task spawning does not imply a private worktree.

Results auto-deliver. Keep doing independent useful work, message an existing agent with `write agent://<id>` for follow-up, and use the zero-argument `wait` tool only when blocked. Do not poll. One integration owner verifies after all edits land, when verification is authorized. See [task](omp://tools/task.md), [agent discovery](omp://task-agent-discovery.md), and [session-type context](omp://system-prompt-customization.md).

### Persistent eval, agents, workpools, and bulk judgment

One eval call is one cell; state persists per language and subagents have separate kernels. Top-level `await` works. Python uses keyword arguments; JavaScript uses one trailing options object and async file/helper operations. Retry only a failed step: earlier state mutations may have succeeded. Do not repeat successful setup.

Read [agent helpers](xd://eval/agents), [judge helpers](xd://eval/judge), and [setup helpers](xd://eval/helpers) before use. Python orchestration patterns:

```python
# result_schema and the assignment must be defined from the actual contract.
h = agent(assignment, agent="reviewer", schema=result_schema,
          schema_mode="strict", model="@default")
# The agent keeps working while the calling agent handles another slice.
result = await h.wait()

# Repeated independent items with shared context; define assignments first.
pool = workpool("reviewer", name="case-review", context=shared_contract)
pool.push(*assignments)
```

There is no `pool.wait()`: follow the documented drain/barrier API. The first full drain settles/closes a workpool; use a new named pool for a later phase. Workers may be reused, so do not assume each item is a fresh independent context. Eval's `wait(handles, ...)` barrier is distinct from the zero-argument OMP `wait` tool.

For bulk probabilistic judgment, freeze the rubric before evaluating data. This cell illustrates two states and one question, not deterministic testing:

```python
questions = {
    "reports_rejections": {
        "type": "bool",
        "instructions": "Does the report state how many input rows were rejected?"
    }
}
states = {
    "case-a": {"report": "Accepted 10 rows; rejected 2 rows with missing emails."},
    "case-b": {"report": "Wrote the cleaned contacts file."}
}
batch = await judge_batch(states, questions, concurrency=2, retries=1, min_ok=1)
settled = await batch.drain(timeout=30)
# Inspect each returned (key, item): item.answers or item.error.
# A bool answer is a yes probability, not a Python bool or ground-truth check.
```

Retain failures and probabilities when reporting judgment. Use deterministic artifact checks for exact facts. `completion` is a stateless, tool-free transformation; `agent` has its own tools/history context; `judge_batch` shares a frozen rubric across many states. None substitutes for actual execution or evidence collection. Kernel-defined tools execute in the parent kernel and can be shared by name with workers; they are temporary interfaces, not distributable runtime tools.

### Finite background work and named services

Use `bash` with `async: true` for finite programs when independent work remains. Results auto-deliver; do not poll `proc://` merely to learn whether completion happened.

A long-lived review viewer uses a project-unique **named service**, not shell backgrounding. Example arguments after resolving both symbolic paths:

```json
{
  "command": "uv run <skill-dir>/scripts/generate_review.py <workspace>/iteration-1 --host 127.0.0.1 --port 3117",
  "name": "csv-cleaner-review-iteration-1",
  "ready": {"port": 3117}
}
```

Named services cannot combine with `async: true` or a command timeout; readiness has its own timeout. If both a log pattern and port are given, both must pass. Reusing a live name restarts it, so use a unique name. Inspect via `proc://<returned-id-or-name>`, send stdin only when useful, and stop only the owned service with `write proc://<id>/kill` (omit content).

Bind the viewer to loopback. When the user is on another computer, provide the SSH tunnel command with their actual host, then the local URL; do not assume a browser can open on the remote machine. Never kill an unrelated process to free a port. See [bash](omp://tools/bash.md), [wait](omp://tools/wait.md), and [evaluation viewer procedure](evaluation.md).

## User choices and progress

Use `ask` only for genuinely missing human decisions, not facts in files or tools. It can collect several questions with unique IDs/option labels; `recommended` is a zero-based index. Users can supply custom notes instead of a listed choice. Ask is interactive/prompt-surface gated and generally absent in headless workers. Cancellation/headless invocation aborts; configured timeouts can select a default. Check `timedOut` before treating an answer as explicit authorization. See [ask](omp://tools/ask.md).

Use optional `todo` phases for sufficiently complex work only when the live policy allows it. It takes **one op**, not an operations array:

```json
{"op":"init","list":[
  {"phase":"Author","items":["Clarify the skill contract","Draft the skill"]},
  {"phase":"Evaluate","items":["Evaluate representative cases","Apply evidence-backed refinements"]}
]}
```

Then use an operation such as `{"op":"done","task":"Draft the skill"}`. Exact task text and phase names are identifiers. One task remains active; completion auto-starts the next pending task. Init replaces the list, failed ops roll back, and ordinary children do not inherit parent-owned todos. See [todo](omp://tools/todo.md).

## Surface-selection matrix

Choose the smallest surface that honestly implements the requested behavior. These can coexist in an OMP package; packaging is not a reason to install executable integration for plain guidance.

| Surface | Choose for | Boundary / primary reference |
|---|---|---|
| **Authored skill** | Optional named procedure with references/templates/scripts; human invocation or deliberate model discovery. | Guidance, not a registered executable API or universal policy. [Skills](omp://skills.md). |
| **Rulebook rule** | Domain requirements read when task/code context makes them relevant. | Description advertises policy; globs are advisory, not automatic activation. [Rule matching](omp://rulebook-matching-pipeline.md). |
| **Sticky / always-apply rule** | A few short requirements that must travel on every request. | Not long optional tutorials or OS containment. Native `RULES.md` is sticky. [Context files](omp://context-files.md). |
| **TTSR rule** | Correct recurring prose/tool-argument patterns using regex, source AST, or completed-output judgment. | Scope, repeat, and pattern coverage limit detection; question rules never interrupt. Not a comprehensive security sandbox. [TTSR lifecycle](omp://ttsr-injection-lifecycle.md). |
| **Custom tool** | A real model-callable executable function with parameter schema, cancellation, side effects, and structured results. | Prompt-only procedures do not need a tool. Multi-event runtime integration belongs in extensions. [Custom tools](omp://custom-tools.md). |
| **Extension** | Host lifecycle/UI/provider integration, tools, commands, shortcuts, and session control. | In-process JS/TS expands trust; not needed for an on-demand documentation bundle. [Extensions](omp://extensions.md). |
| **Hook / event interceptor** | Pre-tool policy, redaction, audit, context rewriting, lifecycle behavior. | Prefer ExtensionAPI handlers for new work; a filename alone is not event registration, and regex hooks are not complete containment. [Hooks](omp://hooks.md), [hook authoring](omp://skills/authoring-hooks.md). |
| **File slash command** | A small user-only prompt entrypoint needing aggregate/positional argument substitution. | Commands have their own templating; skills consume appended user text. Avoid a redundant wrapper for the existing skill command. [Slash internals](omp://slash-command-internals.md). |
| **Custom task agent** | Durable specialist identity with system prompt, tools/spawns/model/output contract, and optional autoload. | For one temporary assignment, use task context; shared knowledge belongs in a skill. [Agent discovery](omp://task-agent-discovery.md). |
| **MCP server** | Separately hosted/transported tools, resources, prompts, remote auth, or cross-client services. | Not in-process OMP UI/events; do not silently install a server as a skill dependency. [MCP authoring](omp://mcp-server-tool-authoring.md). |
| **AGENTS.md/context file** | Broad repo/account background and conventions loaded at session opening. | Optional workflow would tax all sessions; task context inheritance requires care. [Context files](omp://context-files.md). |
| **Memory** | Grounded learned facts/decisions/heuristic lessons across sessions. | Current user/repo evidence wins; not distributable source or authoritative permanent instructions. [Memory](omp://memory.md). |
| **Managed skill** | Auto-learned repeatable procedure stored apart from authored skills. | `manage_skill` writes isolated managed-skills with name/description frontmatter, not this repository's authored files. [Manage skill](omp://tools/manage_skill.md). |

Rule deduplication is first-wins by name, unlike differing skills' namespacing. Accepted TTSR triggers take precedence over always-apply bucketing. Rulebook globs are hints; TTSR path scopes are gates. Direct eval host calls may not pass through ordinary tool hooks. Enforcement claims need the real runtime policy and its coverage, not forceful skill prose.

Extensions and custom tools run code rather than act as sandboxes. Register during factory load and perform runtime actions in handlers; consult their distinct execution signatures instead of transplanting code. MCP normalization of some internal file-backed URLs is a separate bridge behavior, not proof that arbitrary external argv is rewritten.

## Packaging and discovery pitfalls

### Choose the carrier deliberately

For this repository, an OMP extension package is a resource bundle even without executable extensions:

```json
{"name":"rock-throw","version":"0.1.0","private":true,"omp":{}}
```

Flat sibling `skills/`, and optional real `agents/`/`commands/`, are discovered from the package root. Add `omp.extensions` only for actual runtime code; do not create a no-op module just to ship skills.

- **Development:** `omp -e <repo>` explicitly loads a package directory and its sibling resources. Passing only an extension file is not equivalent root authorization.
- **Live checkout installation:** `omp plugin link <repo>` links the user-global checkout. Update by editing/pulling the source, then reload skill resources or restart as appropriate; package upgrade is not a checkout update mechanism.
- **Skills-only configuration:** set `skills.customDirectories` to the **parent containing skill directories**, such as `<repo>/skills`. Use an absolute path and preferably a temporary overlay with `omp --config <overlay.yml>` for evaluation/development. This does not load package agents or commands.

Setting `skills.customDirectories` replaces an array rather than merges it. Inspect existing non-secret configuration before an explicitly authorized persistent change; do not overwrite other roots for convenience. No perpetual resource watcher is promised: reload/restart after edits. See [extension loading](omp://extension-loading.md), [package/link plumbing](omp://plugin-manager-installer-plumbing.md), [settings](omp://settings.md), and [configuration overlays](omp://config-usage.md).

### Provider and discovery traps

- Roots scan one level: `skills/group/name/SKILL.md` is not automatically discovered by conventional scanning. Point a custom root at the group if nesting is intentional.
- Raw names cannot contain slash/backslash; runtime namespaces are assigned by discovery. Include meaningful name and description regardless of provider permissiveness.
- Identical same-name copies can collapse; differing copies keep a highest-precedence bare name and receive namespace aliases for the others. Use the **resolved** name for `/skill:` and `skill://`.
- Custom-directory skills outrank provider copies; authored skills outrank registry/managed copies. Exclusions also apply to resolved names; namespacing is not an exclusion bypass.
- The Agent Plugins standard has a closed skill-frontmatter set: `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`. OMP hiding extensions cause rejection/skipping there. Skillshare publishing shares this restriction. The conventional OMP package route accepts the repository's default hiding flag.
- Unknown keys retained by a permissive scanner are not runtime promises. `enabled: false`, hidden advertisement, discovery exclusions, and `--no-skills` are different controls.
- Hidden skills remain addressable; descriptions remain required in native/custom/package roots. Visible descriptions spend prompt context each session; OMP shows a cold preview and later compressed routing hint, not necessarily the authored paragraph. See [description tuning](description-tuning.md).
- `omp skill list` lists registry-managed installs, not all local discovered skills. It is not a universal discovery check.

Check from a cwd/configuration where the chosen root is active:

```sh
omp read skill://<name>
```

Replace the name with the actual resolved skill name. A successful read returns its instructions; an unavailable name can return an “Available: …” list instead. Do not mistake that list for successful resolution. With an explicit package root, use `omp -e <repo> read skill://<name>`. Verify the intended copy/name rather than another installed duplicate. See [skills](omp://skills.md).

## Optional features and further reading

- [Checkpoint](omp://tools/checkpoint.md) is disabled by default and summarizes exploratory conversation; it is **not** a git/filesystem snapshot or rollback for scripts.
- [AST search](omp://tools/ast-grep.md) is optional and disabled by default; do not require it without checking availability.
- [Memory](omp://memory.md) defaults off. Native project context uses the nearest nonempty ancestor `.omp` directory; adding a closer directory can change which native files load. See [context files](omp://context-files.md).
- [Manage skill](omp://tools/manage_skill.md) is gated by auto-learn, independently of memory, and writes generated managed space. [Learn](omp://tools/learn.md) can save a lesson before a later skill mutation fails; do not treat partial results as full success.
- [Extension authoring](omp://skills/authoring-extensions.md), [custom tools](omp://custom-tools.md), and [MCP authoring](omp://mcp-server-tool-authoring.md) contain actual runtime schemas. Link those rather than copying a large drifting contract into a skill.

For authoring decisions and the delivery checklist, read [writing skills](writing-skills.md). For actual paired executor isolation and grader/viewer procedures, read [evaluation](evaluation.md). These examples explain available surfaces; only report operations and verification actually exercised.
