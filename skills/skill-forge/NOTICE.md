# Notice

This skill (`skill-forge`) is a derivative work of Anthropic's `skill-creator` skill, renamed to avoid confusion with the original:

- Source: https://github.com/anthropics/skills/tree/main/skills/skill-creator (commit `8a1541c`)
- Copyright 2026 Anthropic, PBC
- License: Apache License 2.0 — see `LICENSE.txt` in this directory

Every file derived from the upstream skill carries a one-line modification notice at its top. Files without that notice are new.

## Changes from upstream

- Runs on Oh My Pi (`omp`) with no Claude Code, Claude.ai, or Cowork dependency.
- User-invoked by default (`disable-model-invocation: true`); invoked as `/skill:skill-forge <request>`.
- With-skill and baseline runs are isolated headless `omp -p --mode json` processes (`scripts/run_evals.py`). The with-skill arm reproduces OMP's `/skill:` invocation message. Tokens, cost, and duration are measured from the run transcript.
- Grader, comparator, and analyzer prompts moved to `roles/` and run as OMP `task` subagents with strict output schemas.
- Description tuning uses fresh `omp --mode rpc` processes and records the routing hint OMP actually renders (a cold preview first, then a cached compressed hint). It applies only to model-invocable skills.
- Upstream defects fixed: inconsistent run-directory layout, reversed baseline delta, character counts reported as tokens, viewer port killing, unsafe HTML/JSON embedding, and feedback status races.
- New: `validate_skill.py` (OMP frontmatter rules, reference checks, leftovers from other hosts), `prepare_blind.py`, and the `references/writing-skills.md` and `references/omp-capabilities.md` guides.
- Removed: `.skill` packaging, Claude.ai/Cowork-specific sections, and the `.claude/commands` trigger shim.
