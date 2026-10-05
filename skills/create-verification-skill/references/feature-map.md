# Feature map contract

The map is the repo's maintained verification source. Shape adapted from pstack's [feature-map example](https://github.com/cursor/plugins/tree/main/pstack/skills/create-verification-skill/references/feature-map-example).

## `features/README.md`

Exactly these H2s, in order:

1. `Baseline preconditions`: the state every recipe starts from (launched via SKILL.md Launch, Doctor passing, `run.env` sourced, seed data if any).
2. `Driving conventions`: handle preferences, how to call the harness, and how to reset to baseline (fresh launch, or a named reset command).
3. `Proof and skip reporting`: what each recipe records, and that a skipped entry point is reported as skipped, never as verified through another path.
4. `Features`: one bullet per feature file, a relative Markdown link to the file plus what it covers. Index order is the order a full-map run follows.

## Feature files (3–5)

```text
# <Feature name>

Status: unverified        ← only if the recipe was not run as written; say why

<one paragraph: the user-visible behavior>

## Sub-features
## How to get to it (user POV)
## Driving it with <harness>
## Gotchas
```

Exactly those four H2s, in that order, nothing else at H2.

- **Sub-features**: short IDs (`create-save`), one line each.
- **How to get to it (user POV)**: every user entry point (button, shortcut, command, route). A recipe that covers only some of them says which.
- **Driving it with \<harness\>**: a `Preconditions:` list, then numbered steps of the form **Action.** exact command. Observable result. The last step saves evidence to the run's evidence dir.
- **Gotchas**: traps that waste or invalidate a run.

## Recipe constraints

- **Runnable as written** against the baseline, in index order, after any earlier recipe: no edits, no invented values.
- **Order-independent data.** Create uniquely named records and read back the IDs the app returns; never assume an empty store or a fixed ID like `1`.
- **Second view for every mutation.** After the user-facing action, read the result through another path (reload, list, API, stored file).
- **Exact expectations.** Quote the literal text, status, or exit code. When a pipe is involved, capture the producer's exit code (`set -o pipefail` or `PIPESTATUS`), not the last command's.
- **User path only.** No internal setters, test-only endpoints, or direct DB writes to cause the behavior; direct reads for the second view are fine.

## Example feature file

```markdown
# Create a note

A user saves a titled note from the browser and sees it in the list and on its own page.

## Sub-features

- `create-open` opens a blank editor from `New note`.
- `create-save` persists title and body.
- `create-validate` rejects an empty title.

## How to get to it (user POV)

- Choose the `New note` link on `/`.
- Open `/notes/new` directly.

## Driving it with OMP browser

Preconditions:

- Baseline from `features/README.md`; `run.env` sourced.

1. **Open editor.** `tab.goto($BASE_URL + "/")`, click link `New note`. A form named `Note editor` appears.
2. **Save.** Fill `Title` with `Release checklist $RUN_ID`, `Body` with `Tag and publish`, click `Save note`. URL becomes `/notes/<id>`; heading reads the title. Record `<id>` from the URL.
3. **Second view.** `curl -s $BASE_URL/api/notes` contains an object with that `<id>` and title.
4. **Validate.** Open `/notes/new`, click `Save note` with an empty title. Alert `Title is required`; no new row in `/api/notes`.
5. **Proof.** Screenshot and ARIA snapshot to `$EVIDENCE/create-note/`.

## Gotchas

- Titles are trimmed on save; assert the rendered title.
- A redirect alone is not proof; check `/api/notes`.
```
