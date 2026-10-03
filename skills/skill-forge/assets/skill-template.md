<!-- Derived from Anthropic skill-creator (Apache-2.0); modified for OMP. -->
# Minimal OMP skill templates

These are two alternative starting points for the same concrete example, not two skills to install together. Choose the invocation policy first. Adapt the name, description, purpose, inputs, steps, done conditions, and output to the real job; keep the directory name identical to the authored name. Remove editorial comments when they no longer help. Do not ship generic instructions, unfinished substitutions, or links to files that do not exist.

The example needs no helper program or separate reference. Its resource section therefore contains an authoring comment rather than a fake bundled path. Add direct, condition-bearing pointers only when real resources are bundled; otherwise omit that section. For the actual authoring rules, read [Writing skills](../references/writing-skills.md). For optional runtime integration, read [OMP capabilities](../references/omp-capabilities.md).

## User-invoked default

Use this when the human chooses the workflow explicitly with `/skill:csv-cleaner request text`. The description is a human-facing one-line summary; preserve the hiding flag unless autonomous discovery is explicitly requested.

```markdown
---
name: csv-cleaner
description: "Clean CSV contacts and report the changes."
disable-model-invocation: true
---

# Clean CSV contacts

## Purpose

Produce a cleaned copy of a contact CSV and an evidence-backed change report without modifying the source file.

## Inputs

Use the appended `User:` text as the request, input-file location, cleaning rules, and output constraints. Resolve missing facts from supplied context and the input file first. Ask only for a cleaning decision that remains genuinely ambiguous.

<!-- Adapt input discovery to the actual workflow. Skill arguments are appended
user text, not variable substitution or a shell argv vector. -->

## Workflow

1. Read the input and identify its header, encoding, row count, and requested cleaning rules. Confirm the output location if it is not established by the request.
   Done when the exact source, required transformations, preserved columns, and destination are known.
2. Apply only the requested transformations, preserving the source and recording any rejected rows with their reasons. Ask before overwriting an existing destination.
   Done when the cleaned copy exists and every source row is accounted for as retained or rejected.
3. Read the output and check its columns, row accounting, and requested transformations against the input and request.
   Done when every requirement has a reported check result or an explicit unverified condition.

<!-- Keep steps ordered and done conditions exhaustive. For the real job,
replace CSV-specific details rather than adding unrelated ceremony. -->

## Output format

Return the cleaned file's path, source/retained/rejected row counts, a concise list of changes, rejection reasons, and the checks actually exercised. State unresolved ambiguity or unverified requirements. Do not equate a valid CSV with completion of every requested transformation.

## Bundled resources

<!-- If resources are needed, add direct links to existing bundled references
with their read conditions, and assets with their copy/fill instructions.
For each real helper, document inputs, outputs, and when to run it. Resolve
relative paths against the invocation's [Skill directory: …] directory.
Run Python entry scripts through uv using their physical absolute paths.
If no bundle is needed, remove this section; do not create empty scaffolds. -->
```

## Model-invocable alternative

Use this only when the user wants autonomous selection. Omit both invocation-hiding flags. The first description sentence below is a complete routing hint under 100 characters; no important distinguishing fact is deferred to a later sentence. Evaluate routing separately from task execution.

```markdown
---
name: csv-cleaner
description: "Cleans CSV contact files while preserving columns and reporting rejected rows."
---

# Clean CSV contacts

## Purpose

Produce a cleaned copy of a contact CSV and a change report using the user's requested transformations. This workflow is for CSV contact data, not spreadsheet layout or general data analysis.

## Inputs

Use the current user request and supplied context to locate the contact CSV and cleaning rules. If loaded through `/skill:csv-cleaner`, consume the appended `User:` text as that request. A model-selected or autoloaded body does not establish authorization to overwrite files or add unrelated transformations.

<!-- Keep the routing hint discriminative and the body valid under both
explicit invocation and on-demand reading. Do not assume every load is a
human invocation, or interpret user text as executable shell source. -->

## Workflow

1. Read the input, identify its columns and row count, and resolve the requested transformations and output location. Ask only for missing decisions that cannot be established from context.
   Done when the source, preservation requirements, allowed transformations, and destination are explicit.
2. Write a cleaned copy, preserving the source and recording rejected rows with reasons. Ask before overwriting an existing destination.
   Done when every source row is accounted for and the requested artifact exists.
3. Inspect the artifact against all stated requirements and summarize actual evidence.
   Done when column preservation, row accounting, and each requested transformation have a check result or a stated unverified condition.

## Output format

Return the cleaned file's path, source/retained/rejected row counts, applied transformations, rejection reasons, and actual check results. State unresolved constraints separately from successful work.

## Bundled resources

<!-- Add only pointers to real bundled files, directly from this body.
State which branch reads each reference, which artifact uses each asset,
and which step runs each helper. Use the exact discovered skill name for
skill:// asset reads, and the physical skill directory for external programs.
Python helpers need PEP 723 metadata and uv invocation. Remove this section
if the finished workflow has no bundled resources. -->
```

## Before using either template

- Preserve the chosen policy; hiding removes advertisement, not URI/command access.
- Replace the entire concrete example with the actual job, not just its title.
- Keep every named outcome in the workflow's done conditions.
- Ensure frontmatter is valid YAML and accepted by the chosen discovery provider. Agent Plugins closed-set validation rejects the default hiding flag; use the conventional OMP package/native/custom-directory route for user-invoked skills.
- Validate and check discovery when authorized, then report the actual location and resolved invocation name. Claim only checks actually performed.
