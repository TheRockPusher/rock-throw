---
name: create-verification-skill
description: "Generate a project-local verify-app skill that launches, drives, and proves the app as a user would."
disable-model-invocation: true
---

# Create a verification skill

Generate `<repo>/.omp/skills/verify-<app>/`: a skill that lets a future agent launch the real app, exercise a feature as a user would, capture evidence, and clean up. Write it for an agent reading it cold, mid-task, who has never seen the app. Use the appended `User:` text for the target repo and any focus; default to the current repo.

## 1. Interview the repo, not the user

Answer from the codebase; ask only what you cannot observe.

- **Surface:** what a user touches (web UI, CLI/TUI, API, desktop, library). Pick the primary one; note the rest.
- **Run:** the repo's own dev command, ports, env vars, data locations, seed data, auth.
- **Drive:** existing harnesses first (Playwright specs, scripts, endpoints). Otherwise: web → OMP eval `browser` (read `xd://eval/browser`); CLI/TUI → `bash` with `pty`; HTTP → `curl`.
- **Observe:** screenshots, ARIA snapshots, transcripts, response bodies, exit codes, stored state.
- **Isolate:** a free port and a scratch data dir/HOME per run, so verification never touches the user's real data or instance.

If the app doesn't start as-is, fix or precisely report that first. An irrelevant missing asset blocking startup may be created by the generated skill, marked as verification scaffolding and removed in cleanup.

## 2. Write `verify-<app>/SKILL.md`

Read [references/verify-skill-contract.md](references/verify-skill-contract.md) first and meet every constraint in it: layout, frontmatter, the Launch → Doctor → Drive → Evidence → Cleanup sections, isolation, evidence location, and cleanup ownership. Ground every command in this repo; the skeleton there shows shape, not content.

## 3. Seed the feature map

Read [references/feature-map.md](references/feature-map.md), then create `features/README.md` and one file per top user-facing feature (3–5) in exactly that shape.

## 4. Prove it before handing over

Follow the generated skill end to end once: launch, doctor, drive one mapped feature, capture evidence, clean up. Then confirm evidence still exists and no process you started is left running. Fix failures and rerun cleanup after each failed attempt. An unexecuted skill is a draft, not a deliverable.

Within that same launch, run every other feature recipe exactly as written; mark any you could not run `Status: unverified` at the top of its file. Recipes that only read plausibly are where generated maps go wrong, and the next agent will trust them.

Before reporting, walk both references' constraints against the generated files and fix any miss. Report: skill path, features mapped, the proof run's evidence paths, and anything unverified.
