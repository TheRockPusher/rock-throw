# Contract for the generated `verify-<app>` skill

Every rule here is a constraint the generated skill must meet; check each one before handing over. The skeleton at the end shows the required shape.

## Layout

```text
<repo>/.omp/skills/verify-<app>/
  SKILL.md            # required; sections below, in order
  features/           # required; see feature-map.md
    README.md
    <feature>.md      # 3–5 files
  scripts/            # optional helpers
<repo>/.omp/evidence/verify-<app>/<run-id>/   # created by runs, never by cleanup
```

## Frontmatter

- `name: verify-<app>`, identical to the directory name.
- `description`: one sentence naming the app, its surface (web UI, CLI, API…), and when to use it ("prove a change to … in a running instance"). No angle brackets.
- Leave it model-invocable (no `disable-model-invocation`): the point is that future agents find it unprompted.

## Sections (H2, this order)

1. **Launch**: one copy-pasteable command sequence from a clean checkout to a ready instance.
   - Allocate a run ID, a scratch dir (`mktemp -d`), and a free port (bind port 0) per run. Point every data location the app uses (DB file, data dir, `HOME` when the app falls back to it) into scratch. Write all of it to one file (e.g. `<scratch>/run.env`) and print its path; later sections source that file instead of asking the reader to invent values.
   - Servers: an OMP named `bash` service with `ready` (port and/or log regex), named after the run ID. CLIs: no server; every invocation goes through a wrapper that sources `run.env`.
   - State the exact ready signal.
2. **Doctor**: one read-only command that exits non-zero unless the instance is up, is ours (PID/cwd/env matches this run), serves the expected version, and uses scratch data. Run it first whenever anything looks off.
3. **Drive**: the harness for this surface and how to call it. Use stable handles (labels, roles, routes, prompts, flags), never coordinates or tab order. Point to `features/` for per-feature recipes.
4. **Evidence**: what counts as proof and where it goes.
   - Path: `<repo>/.omp/evidence/verify-<app>/<run-id>/`, outside scratch.
   - Proof is the user action plus the resulting state, plus a second read-only view of the side effect (stored row, file, list, stats), never only a success message.
   - CLI proof records command, stdout, stderr, exit code. UI proof records a screenshot and an ARIA/DOM snapshot. HTTP proof records request, status, body.
5. **Cleanup**: stops only what this run started, then removes scratch.
   - Stop the named service (`write proc://<service>/kill`) or a PID recorded at launch, after checking it still belongs to this run. Never kill by process name or port alone.
   - Remove any scaffolding the run created (see below); leave evidence in place and list it.
   - Safe to run twice and after a failed launch.
6. **Helpers** (when the generated skill ships scripts): each script is executable, exits non-zero on failure, and its exact invocation appears in SKILL.md.

## Global constraints

- **No reader-invented values.** No `<placeholder>`, `TODO`, or "your port" in any command. Runtime values come from `run.env` or from an earlier command's printed output, named explicitly.
- **Never touch the user's real state.** No command may run the app against default data paths, default ports, or the real `HOME`.
- **Scaffolding.** If startup needs a missing asset the feature under test never uses, create it only when absent, mark it (e.g. a `.verify-<app>-scaffold` file naming the run), and have cleanup remove only marked scaffolding. Never edit app source.
- **Size.** SKILL.md stays under ~150 lines; per-feature detail lives in `features/`.

## Skeleton

````markdown
---
name: verify-notes
description: "Launch the Notes web app in an isolated instance and prove UI/API behavior in a real browser."
---

# Verify Notes

Use before claiming any change to Notes works. Start with Launch, run Doctor, then follow one recipe in `features/`.

## Launch

```sh
.omp/skills/verify-notes/scripts/new-run.sh    # prints RUN_ENV=/tmp/verify-notes.XXXX/run.env
```
Start the named service `verify-notes-<RUN_ID from run.env>`: command `.omp/skills/verify-notes/scripts/serve.sh <RUN_ENV>`, ready port `$PORT`, ready log `Notes listening on`.

## Doctor

`.omp/skills/verify-notes/scripts/doctor.sh <RUN_ENV>` → `doctor: OK version=1.4.0 db=/tmp/verify-notes.XXXX/notes.db`

## Drive

OMP eval `browser` (read `xd://eval/browser`) at `$BASE_URL`; `curl` for `/api/*`. Recipes: `features/README.md`.

## Evidence

`.omp/evidence/verify-notes/<RUN_ID>/`: screenshot + ARIA snapshot per step, `db.sh` dump after each mutation.

## Cleanup

`write proc://verify-notes-<RUN_ID>/kill`, then `.omp/skills/verify-notes/scripts/cleanup.sh <RUN_ENV>`; it lists the retained evidence.
````
