# Derived from Anthropic skill-creator (Apache-2.0); modified for OMP.
"""Ordered YAML frontmatter and OMP description-preview helpers."""

from dataclasses import dataclass
from pathlib import Path
import re

import yaml


SPEC_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
OMP_KEYS = {
    "disable-model-invocation", "disableModelInvocation", "hide", "enabled", "globs", "alwaysApply"
}
NAME_RE = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class SkillMdError(Exception):
    """A skill cannot be read or its frontmatter is malformed."""


@dataclass
class SkillDoc:
    path: Path
    base_dir: Path
    frontmatter: dict
    body: str
    raw: str

    @property
    def name(self) -> str | None:
        value = self.frontmatter.get("name")
        return value if isinstance(value, str) else None

    @property
    def description(self) -> str | None:
        value = self.frontmatter.get("description")
        return value if isinstance(value, str) else None

    @property
    def user_invoked(self) -> bool:
        return any(
            self.frontmatter.get(key) is True
            for key in ("disable-model-invocation", "disableModelInvocation", "hide")
        )


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split a line-one YAML block from Markdown, preserving YAML key order."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise SkillMdError("SKILL.md must start at line 1 with '---' YAML frontmatter")
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1:]).lstrip("\r\n")
    raise SkillMdError("SKILL.md frontmatter is missing its closing '---' delimiter")


def read_skill(skill_dir_or_md: Path) -> SkillDoc:
    """Read a skill directory or SKILL.md, raising SkillMdError on failure."""
    source = Path(skill_dir_or_md).expanduser().resolve()
    path = source if source.name == "SKILL.md" and not source.is_dir() else source / "SKILL.md"
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SkillMdError(f"Cannot read SKILL.md at {path}: {exc}") from exc
    yaml_text, body = split_frontmatter(raw)
    try:
        frontmatter = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise SkillMdError(f"Invalid YAML frontmatter in {path}: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise SkillMdError("SKILL.md frontmatter must be a YAML mapping")
    return SkillDoc(path, path.parent, frontmatter, body, raw)


def dump_skill_md(frontmatter: dict, body: str) -> str:
    """Serialize ordered frontmatter and a Markdown body as SKILL.md."""
    yaml_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True, width=10**6)
    body = body.lstrip("\r\n")
    return f"---\n{yaml_text}---\n\n{body}"


def make_model_visible(fm: dict) -> dict:
    """Copy frontmatter without the three OMP model-invocation hiding flags."""
    return {
        key: value for key, value in fm.items()
        if key not in {"disable-model-invocation", "disableModelInvocation", "hide"}
    }


def cold_preview(description: str) -> str:
    """Port OMP's previewSkillDescription exactly (before warm compression)."""
    # Match JavaScript whitespace and count/slice UTF-16 code units, including
    # a lone surrogate when JavaScript's slice ends halfway through a pair.
    description = re.sub(
        r"[\u0009-\u000d \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+",
        " ",
        description,
    ).strip(" ")
    encoded = description.encode("utf-16-le", errors="surrogatepass")
    if len(encoded) // 2 <= 100:
        return description
    sliced = encoded[:99 * 2]
    s = sliced.decode("utf-16-le", errors="surrogatepass")
    match = re.match(r"^.*?[.!?](?=\s|$)", s, flags=re.ASCII)
    if match and len(match.group(0).encode("utf-16-le", errors="surrogatepass")) // 2 >= 40:
        return match.group(0)
    last_space = s.rfind(" ")
    if last_space >= 0:
        n = s[:last_space].rstrip(" ")
    else:
        # JavaScript slice(0, -1) drops one code unit, not one Unicode character.
        n = sliced[:-2].decode("utf-16-le", errors="surrogatepass")
    return (n or s) + "…"
