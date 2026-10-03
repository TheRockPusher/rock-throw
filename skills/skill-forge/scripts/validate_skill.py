# Derived from Anthropic skill-creator (Apache-2.0); modified for OMP.
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6,<7"]
# ///
"""Validate portable skill structure, OMP invocation policy, and bundled resources."""

import argparse
import ast
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from skillmd import NAME_RE, OMP_KEYS, SPEC_KEYS, SkillMdError, cold_preview, read_skill


TEXT_SUFFIXES = {".md", ".py", ".html", ".js", ".json", ".yaml", ".yml", ".txt", ".sh"}
RESOURCE_PREFIXES = ("references/", "scripts/", "assets/", "roles/")
MARKDOWN_LINK = re.compile(r"!?\[[^\]\n]*\]\(\s*(<[^>\n]*>|[^)\n]*?)\s*\)")
BACKTICK_PATH = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")

# These literals are the sole permitted host-specific text in this validator.
HOST_LEFTOVERS = (
    "claude -p",
    ".claude/",
    "CLAUDE_",
    "Skill tool",
    "$ARGUMENTS",
    "${CLAUDE_SKILL_DIR}",
    "present_files",
    "AskUserQuestion",
    "TodoWrite",
    "subagent_type",
    "uv run skill://",
    "pip install",
)


def _bundled_texts(base_dir: Path, errors: list[str]) -> dict[Path, str]:
    texts = {}
    for path in sorted(base_dir.rglob("*")):
        if path.name in {"NOTICE.md", "LICENSE.txt"} or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if not path.is_file() or not path.resolve().is_relative_to(base_dir):
            continue
        try:
            texts[path] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"Cannot read bundled text {path.relative_to(base_dir)}: {exc}")
    return texts


def _host_scan_text(path: Path, text: str) -> str:
    """Exclude only this validator's allowed detection-pattern declaration."""
    if path.resolve() != Path(__file__).resolve():
        return text
    lines = text.splitlines(keepends=True)
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "HOST_LEFTOVERS"
            for target in node.targets
        ):
            for index in range(node.lineno - 1, node.end_lineno):
                lines[index] = "\n"
    return "".join(lines)


def _has_contents(text: str) -> bool:
    top = "\n".join(text.splitlines()[:40])
    anchor_entries = re.findall(r"(?m)^\s*(?:[-*+] |\d+[.)] )\[[^\]\n]+\]\(#[^)]+\)", top)
    if len(anchor_entries) >= 2:
        return True
    heading = re.search(r"(?im)^#{1,6}\s+(?:table of contents|contents|on this page)\s*#*\s*$", top)
    if heading:
        section = re.split(r"(?m)^#{1,6}\s", top[heading.end():], maxsplit=1)[0]
        return len(re.findall(r"(?m)^\s*(?:[-*+] |\d+[.)] )\S", section)) >= 2
    return False


def _relative_target(value: str, *, origin: Path, base_dir: Path, skill_name: str | None) -> Path | None:
    value = value.strip()
    if not value or any(char in value for char in "<>*?[]"):
        return None
    if value.startswith("#"):
        return None
    if value.startswith("skill://"):
        prefix = f"skill://{skill_name}/" if skill_name is not None else None
        if prefix is None or not value.startswith(prefix):
            return None
        value = value[len(prefix):]
        parent = base_dir
        # OMP read selectors are not part of a bundled filename.
        value = re.sub(r":(?:\d+(?:[-+]\d*)?|raw|img)(?::.*)?$", "", value)
    else:
        if urlsplit(value).scheme or value.startswith(("/", "\\", "~")):
            return None
        parent = origin
    value = unquote(value.split("#", 1)[0])
    if not value or any(char in value for char in "<>*?[]"):
        return None
    target = (parent / value).resolve()
    return target if target.is_relative_to(base_dir) else None


def _references(
    path: Path, text: str, base_dir: Path, skill_name: str | None
) -> tuple[set[Path], set[Path]]:
    """Separate explicit links from advisory bare backticked resource mentions."""
    targets = set()
    mentions = set()
    for match in MARKDOWN_LINK.finditer(text):
        value = match.group(1)
        # A quoted optional Markdown title is not part of the destination.
        value = re.sub(r"\s+['\"][^'\"]*['\"]\s*$", "", value)
        if value.startswith("<") and value.endswith(">"):
            value = value[1:-1]
        target = _relative_target(value, origin=path.parent, base_dir=base_dir, skill_name=skill_name)
        if target is not None:
            targets.add(target)
    for match in BACKTICK_PATH.finditer(text):
        value = match.group(1)
        if re.search(r"[\s*<>{}$…]", value):
            continue
        if value.startswith(RESOURCE_PREFIXES) or value in {
            prefix.rstrip("/") for prefix in RESOURCE_PREFIXES
        }:
            target = _relative_target(value, origin=base_dir, base_dir=base_dir, skill_name=skill_name)
            if target is not None:
                mentions.add(target)
    if skill_name is not None:
        pattern = r"skill://" + re.escape(skill_name) + r"/[^\s`\"')}\]]+"
        for match in re.finditer(pattern, text):
            target = _relative_target(
                match.group(0).rstrip(".,;"), origin=base_dir, base_dir=base_dir, skill_name=skill_name
            )
            if target is not None:
                targets.add(target)
    return targets, mentions


def validate_skill(skill_dir: Path, *, policy: str = "any", strict_spec: bool = False) -> dict:
    """Collect every structural error and authoring warning without changing files."""
    errors: list[str] = []
    warnings: list[str] = []
    name = None
    preview = None
    effective_policy = "model"
    source = Path(skill_dir).expanduser().resolve()
    base_dir = source.parent if source.name == "SKILL.md" and not source.is_dir() else source
    try:
        doc = read_skill(source)
    except SkillMdError as exc:
        errors.append(str(exc))
        doc = None

    if doc is not None:
        fm = doc.frontmatter
        name = doc.name
        description = doc.description
        effective_policy = "user" if doc.user_invoked else "model"
        if "name" not in fm:
            errors.append("Missing 'name' in frontmatter")
        elif name is None:
            errors.append("'name' must be a string")
        else:
            if re.fullmatch(NAME_RE, name) is None:
                errors.append("'name' must be lowercase ASCII letters/digits separated by single hyphens")
            if len(name) > 64:
                errors.append(f"'name' exceeds 64 characters ({len(name)})")
            if "/" in name or "\\" in name:
                errors.append("'name' must not contain path separators")
            if name != doc.base_dir.name:
                errors.append(f"'name' {name!r} does not match skill directory {doc.base_dir.name!r}")

        if "description" not in fm:
            errors.append("Missing 'description' in frontmatter")
        elif description is None:
            errors.append("'description' must be a string")
        else:
            preview = cold_preview(description)
            if not description.strip():
                errors.append("'description' must not be empty")
            if len(description) > 1024:
                errors.append(f"'description' exceeds 1024 characters ({len(description)})")
            if "<" in description or ">" in description:
                warnings.append("'description' contains angle brackets; prefer plain description text")
            if not doc.user_invoked and preview != description:
                warnings.append(f"Cold preview: {preview!r}; model sees only this until compression")
            if doc.user_invoked and (
                len(description) > 160 or re.search(r"\b(?:use when|whenever the user)\b", description, re.I)
            ):
                warnings.append("User-invoked descriptions are human-facing: prefer a short summary (about 160 characters), not trigger lists")

        if "compatibility" in fm:
            compatibility = fm["compatibility"]
            if not isinstance(compatibility, str):
                errors.append("'compatibility' must be a string")
            elif len(compatibility) > 500:
                errors.append(f"'compatibility' exceeds 500 characters ({len(compatibility)})")
        if "metadata" in fm:
            metadata = fm["metadata"]
            if not isinstance(metadata, dict) or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in metadata.items()
            ):
                warnings.append("'metadata' should be a string-to-string mapping")
        for key in fm:
            if strict_spec and key not in SPEC_KEYS:
                errors.append(f"Frontmatter key {key!r} is outside the strict Agent Skills specification")
            if key not in SPEC_KEYS | OMP_KEYS:
                warnings.append(f"Unknown frontmatter key {key!r}")
        if policy != "any" and policy != effective_policy:
            errors.append(f"Requested {policy!r} policy, but the effective invocation policy is {effective_policy!r}")
        body_lines = len(doc.body.splitlines())
        if body_lines > 500:
            warnings.append(f"SKILL.md body has {body_lines} lines; move detail into references (recommended maximum: 500)")

    texts = _bundled_texts(base_dir, errors)
    for path, text in texts.items():
        relative = path.relative_to(base_dir)
        if path.suffix.lower() == ".md":
            targets, mentions = _references(path, text, base_dir, name)
            for target in sorted(targets):
                if not target.is_file():
                    errors.append(f"{relative}: referenced bundled file is missing: {target.relative_to(base_dir)}")
            for target in sorted(mentions - targets):
                if not target.exists():
                    warnings.append(f"{relative}: backticked resource may be an example or is missing: {target.relative_to(base_dir)}")
            if relative.parts[0] in {"references", "roles"}:
                line_count = len(text.splitlines())
                if line_count > 100 and not _has_contents(text):
                    warnings.append(f"{relative}: {line_count} lines without a contents list near the top")
        scan_text = _host_scan_text(path, text)
        for pattern in HOST_LEFTOVERS:
            for match in re.finditer(re.escape(pattern), scan_text):
                line = scan_text.count("\n", 0, match.start()) + 1
                warnings.append(f"{relative}:{line}: host-specific leftover {pattern!r}")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "name": name,
        "policy": effective_policy,
        "cold_preview": preview,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_dir", type=Path, help="Skill directory (or its SKILL.md)")
    parser.add_argument("--policy", choices=("user", "model", "any"), default="any")
    parser.add_argument("--strict-spec", action="store_true", help="Reject OMP extensions and all other non-spec keys")
    parser.add_argument("--json", action="store_true", help="Print the structured validation result")
    args = parser.parse_args()
    result = validate_skill(args.skill_dir, policy=args.policy, strict_spec=args.strict_spec)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for error in result["errors"]:
            print("ERROR " + " ".join(error.splitlines()))
        for warning in result["warnings"]:
            print("WARN " + " ".join(warning.splitlines()))
        status = "OK" if result["ok"] else "FAILED"
        print(f"{status}: {len(result['errors'])} error(s), {len(result['warnings'])} warning(s)")
        print(f"Name: {result['name']!r}; effective invocation policy: {result['policy']}")
        print(f"Cold preview: {result['cold_preview']!r}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
