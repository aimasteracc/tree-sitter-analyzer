"""Canonical unified-diff hunk parsing and resource bounds."""

from __future__ import annotations

import re

PATCH_MAX_BYTES = 1 * 1024 * 1024
PATCH_MAX_HUNKS = 512
PATCH_MAX_LINES_PER_HUNK = 2000
_HUNK_COUNT_MAX_DIGITS = len(str(PATCH_MAX_BYTES))
HUNK_HEADER_RE = re.compile(
    r"^@@ -[0-9]+(?:,([0-9]+))? \+[0-9]+(?:,([0-9]+))? @@(?: .*)?$"
)


class GitHunkBoundError(ValueError):
    """A unified diff exceeds a registered resource bound."""


def physical_lines(patch_text: str) -> list[str]:
    """Split LF/CRLF patch text without a synthetic trailing item."""
    lines = patch_text.split("\n")
    if patch_text.endswith("\n"):
        lines.pop()
    return [line.removesuffix("\r") for line in lines]


def hunk_count(raw: str | None) -> int:
    if raw is None:
        return 1
    if len(raw) > _HUNK_COUNT_MAX_DIGITS:
        raise GitHunkBoundError("patch hunk count exceeds numeric bound")
    return int(raw)


def hunk_body_indexes(lines: list[str]) -> set[int]:
    indexes: set[int] = set()
    in_hunk = False
    remaining_old: int | None = None
    remaining_new: int | None = None
    for index, line in enumerate(lines):
        if line.startswith("@@"):
            match = HUNK_HEADER_RE.fullmatch(line)
            in_hunk = True
            remaining_old = hunk_count(match.group(1)) if match else None
            remaining_new = hunk_count(match.group(2)) if match else None
            continue
        if not in_hunk:
            continue
        if line.startswith("diff --git "):
            in_hunk = False
            continue
        if remaining_old == 0 and remaining_new == 0:
            if (
                index + 1 < len(lines)
                and line.startswith("--- ")
                and lines[index + 1].startswith("+++ ")
            ):
                in_hunk = False
                continue
            if line.startswith("\\ No newline at end of file"):
                indexes.add(index)
                continue
        indexes.add(index)
        if remaining_old is None or remaining_new is None or not line:
            continue
        if line[0] == " ":
            remaining_old = max(0, remaining_old - 1)
            remaining_new = max(0, remaining_new - 1)
        elif line[0] == "-":
            remaining_old = max(0, remaining_old - 1)
        elif line[0] == "+":
            remaining_new = max(0, remaining_new - 1)
    return indexes


def bound_patch(patch_text: str) -> None:
    """Enforce the RFC-0026 C40/C41 canonical patch limits."""
    if len(patch_text.encode("utf-8")) > PATCH_MAX_BYTES:
        raise GitHunkBoundError("patch exceeds max bytes")
    lines = physical_lines(patch_text)
    if sum(line.startswith("@@") for line in lines) > PATCH_MAX_HUNKS:
        raise GitHunkBoundError("patch exceeds max hunks")
    hunk_body = hunk_body_indexes(lines)
    current_hunk_lines = 0
    for index, line in enumerate(lines):
        if line.startswith("@@"):
            current_hunk_lines = 0
        elif index in hunk_body:
            current_hunk_lines += 1
            if current_hunk_lines > PATCH_MAX_LINES_PER_HUNK:
                raise GitHunkBoundError("patch exceeds max lines per hunk")


def patch_has_changed_hunk(lines: list[str]) -> bool:
    """Return whether all text hunks are canonical and at least one changes bytes."""
    file_header_seen = False
    in_hunk = False
    remaining_old = remaining_new = 0
    completed_change = False
    old_lines: list[tuple[str, bool]] = []
    new_lines: list[tuple[str, bool]] = []
    for index, line in enumerate(lines):
        if in_hunk:
            if line == r"\ No newline at end of file":
                continue
            has_newline = not (
                index + 1 < len(lines)
                and lines[index + 1] == r"\ No newline at end of file"
            )
            if line.startswith(" ") and remaining_old and remaining_new:
                remaining_old -= 1
                remaining_new -= 1
                old_lines.append((line[1:], has_newline))
                new_lines.append((line[1:], has_newline))
            elif line.startswith("-") and remaining_old:
                remaining_old -= 1
                old_lines.append((line[1:], has_newline))
            elif line.startswith("+") and remaining_new:
                remaining_new -= 1
                new_lines.append((line[1:], has_newline))
            else:
                return False
            if remaining_old == 0 and remaining_new == 0:
                completed_change = completed_change or old_lines != new_lines
                in_hunk = False
            continue
        if line.startswith("diff --git "):
            file_header_seen = False
        elif (
            index + 1 < len(lines)
            and line.startswith("--- ")
            and lines[index + 1].startswith("+++ ")
        ):
            file_header_seen = True
        elif line.startswith("+++ ") and index and lines[index - 1].startswith("--- "):
            continue
        elif line.startswith("@@"):
            match = HUNK_HEADER_RE.fullmatch(line)
            if not file_header_seen or match is None:
                return False
            old_count, new_count = match.groups()
            remaining_old = hunk_count(old_count)
            remaining_new = hunk_count(new_count)
            old_lines = []
            new_lines = []
            in_hunk = bool(remaining_old or remaining_new)
        elif line == r"\ No newline at end of file":
            continue
        elif line.startswith(("+", "-")):
            return False
    return completed_change and not in_hunk
