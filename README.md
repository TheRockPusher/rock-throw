# rock-throw

A personal skill collection, packaged as an [Oh My Pi](https://github.com/can1357/oh-my-pi) (`omp`) plugin.

## Skills

| Skill | Invoke | What it does |
|---|---|---|
| [skill-forge](skills/skill-forge/SKILL.md) | `/skill:skill-forge <request>` | Creates, improves, and evaluates OMP skills. Drafts SKILL.md, runs paired with/without-skill evals, opens a review page, and tunes descriptions. OMP-native port of Anthropic's `skill-creator`. |

## Conventions

- **Layout:** each skill lives in its own flat directory, `skills/<name>/SKILL.md`. OMP does not discover nested skill folders.
- **User-invoked by default:** every skill sets `disable-model-invocation: true`, so the model is not offered it automatically. You call it with `/skill:<name>`. This only hides the skill; it does not lock it — anything can still read it at `skill://<name>`.
- **Frontmatter:** always set `name` (must match the directory name) and a short, human-facing `description`.
- **Python:** bundled scripts declare their dependencies inline (PEP 723) and run with `uv run`. Never use pip.
- **Validation:** before committing a skill, run `uv run skills/skill-forge/scripts/validate_skill.py skills/<name> --policy user`.

## Install

The repo is an OMP extension package: `package.json` contains `"omp": {}`, and OMP picks up the `skills/` directory next to it.

```sh
# Install from GitHub (marketplace catalog in .omp-plugin/marketplace.json)
omp plugin marketplace add TheRockPusher/rock-throw
omp plugin install rock-throw@rock-throw

# Try a local checkout without installing (this session only)
omp -e /path/to/rock-throw

# Or install a local checkout as a live link
omp plugin link /path/to/rock-throw
```

With the live link, edits to the checkout take effect after `/reload-plugins` or a restart. Install only one way at a time; a link and a marketplace copy with the same name collide.

To check that OMP can see a skill, run this from a directory where the plugin is active:

```sh
omp read skill://skill-forge
```

## Attribution

`skills/skill-forge` is derived from Anthropic's Apache-2.0 [`skill-creator`](https://github.com/anthropics/skills/tree/main/skills/skill-creator) and renamed to avoid confusion with it. See [`skills/skill-forge/NOTICE.md`](skills/skill-forge/NOTICE.md) and [`skills/skill-forge/LICENSE.txt`](skills/skill-forge/LICENSE.txt).
