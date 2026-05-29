"""Metadata parsing helpers for project-local agent skills."""

from __future__ import annotations

from pathlib import Path

DESCRIPTION_KEY = "description"
DISABLE_MODEL_INVOCATION_KEY = "disable-model-invocation"
NAME_KEY = "name"


def read_skill_metadata(skill_path: Path) -> tuple[dict[str, str], str]:
    """Read front-matter metadata and body text from a SKILL.md file."""
    if not skill_path.exists():
        return {}, ""
    try:
        text = skill_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}, ""
    return split_front_matter(text)


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Extract simple YAML front-matter keys used by Codex skills."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    end_index = _front_matter_end_index(lines)
    if end_index is None:
        return {}, text
    metadata = _parse_front_matter_fields(lines[1:end_index])
    return metadata, "\n".join(lines[end_index + 1 :]).lstrip("\n")


def metadata_bool(metadata: dict[str, str], key: str, default: bool = False) -> bool:
    """Read a front-matter boolean value."""
    value = metadata.get(key)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _front_matter_end_index(lines: list[str]) -> int | None:
    """Return the closing front-matter delimiter line index."""
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return index
    return None


def _parse_front_matter_fields(lines: list[str]) -> dict[str, str]:
    """Parse the small subset of YAML used in skill front matter."""
    metadata: dict[str, str] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if not _is_metadata_key(line):
            index += 1
            continue
        key, raw_value = line.split(":", 1)
        value = raw_value.strip().strip('"')
        if value in {">", "|"}:
            block, index = _collect_front_matter_block(lines, index + 1)
            metadata[key.strip()] = " ".join(part.strip() for part in block).strip()
            continue
        metadata[key.strip()] = value
        index += 1
    return metadata


def _collect_front_matter_block(
    lines: list[str],
    start_index: int,
) -> tuple[list[str], int]:
    """Collect indented block scalar lines until the next metadata key."""
    block: list[str] = []
    index = start_index
    while index < len(lines):
        line = lines[index]
        if _is_metadata_key(line):
            break
        if line.strip():
            block.append(line)
        index += 1
    return block, index


def _is_metadata_key(line: str) -> bool:
    """Return True when a front-matter line starts a top-level key."""
    return bool(line) and not line.startswith((" ", "\t")) and ":" in line
