"""Shared, fail-closed unified-diff validation for NO1-010B."""

from __future__ import annotations

import re
from dataclasses import dataclass

PATCH_MAX_BYTES = 1 * 1024 * 1024
PATCH_MAX_HUNKS = 512
PATCH_MAX_LINES_PER_HUNK = 2000
_HUNK_COUNT_MAX_DIGITS = len(str(PATCH_MAX_BYTES))
_GIT_HEADER_SEPARATOR_MAX = 64
_HUNK_HEADER_RE = re.compile(
    r"^@@ -[0-9]+(?:,([0-9]+))? \+[0-9]+(?:,([0-9]+))? @@(?: .*)?$"
)
_MODE_HEADER_RE = re.compile(
    r"^(?:(?:old|new) mode|(?:deleted|new) file mode) [0-7]{6}$"
)
_INDEX_HEADER_RE = re.compile(r"^index [0-9a-f]+\.\.[0-9a-f]+(?: [0-7]{6})?$")
_SIMILARITY_HEADER_RE = re.compile(r"^(?:dis)?similarity index (?:100|[0-9]{1,2})%$")
_EXTENDED_PATH_PREFIXES = ("rename from ", "rename to ", "copy from ", "copy to ")


class PatchBoundError(ValueError):
    """An over-bound patch; the runner must score it UNKNOWN, never apply it."""


class PatchFormatError(ValueError):
    """A patch whose structure or touched paths cannot be classified safely."""


@dataclass(frozen=True)
class DiffPath:
    """One canonical repository-relative path touched by a unified diff."""

    rel_path: str

    @classmethod
    def from_diff_header(cls, header_line: str, marker: str) -> DiffPath | None:
        """Parse one canonical ``--- a/`` or ``+++ b/`` diff header."""
        prefix = f"{marker} "
        side = "a/" if marker == "---" else "b/"
        if not header_line.startswith(prefix):
            return None
        raw = _paired_header_token(header_line, marker)
        if raw == "/dev/null" or not raw.startswith(side):
            return None
        value = raw[len(side) :]
        if value.startswith("/") or value.startswith("./"):
            return None
        if (
            not value
            or "\\" in value
            or any(char in "\t\r\n\v\f" for char in value)
            or any(part in {"", ".", ".."} for part in value.split("/"))
        ):
            return None
        return cls(value)

    @classmethod
    def from_git_token(cls, token: str, side: str) -> DiffPath | None:
        """Parse one unquoted canonical path from a ``diff --git`` header."""
        if not token.startswith(side):
            return None
        value = token[len(side) :]
        if (
            not value
            or value.startswith("/")
            or "\\" in value
            or any(char in "\t\r\n\v\f" for char in value)
            or any(part in {"", ".", ".."} for part in value.split("/"))
        ):
            return None
        return cls(value)

    @classmethod
    def from_extended_header(cls, line: str, prefix: str) -> DiffPath | None:
        """Parse an unquoted rename/copy path (which has no a/ or b/ prefix)."""
        return cls.from_git_token(f"a/{line[len(prefix) :]}", "a/")


def physical_lines(patch_text: str) -> list[str]:
    """Split LF/CRLF patch text without a synthetic trailing item."""
    lines = patch_text.split("\n")
    if patch_text.endswith("\n"):
        lines.pop()
    return [line.removesuffix("\r") for line in lines]


def _paired_header_token(header_line: str, marker: str) -> str:
    """Keep path spaces while removing an optional tab-delimited timestamp."""
    return header_line[len(marker) + 1 :].split("\t", 1)[0]


def _is_dev_null_header(header_line: str, marker: str) -> bool:
    prefix = f"{marker} "
    return (
        header_line.startswith(prefix)
        and _paired_header_token(header_line, marker) == "/dev/null"
    )


def _is_paired_file_header(lines: list[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and lines[index].startswith("--- ")
        and lines[index + 1].startswith("+++ ")
    )


def _hunk_count(raw: str | None) -> int:
    if raw is None:
        return 1
    if len(raw) > _HUNK_COUNT_MAX_DIGITS:
        raise PatchBoundError("patch hunk count exceeds numeric bound")
    return int(raw)


def _git_header_paths(line: str) -> tuple[DiffPath, DiffPath]:
    """Parse one unquoted Git header, including canonical paths with spaces."""
    prefix = "diff --git "
    if not line.startswith(f"{prefix}a/"):
        raise PatchFormatError("non-canonical diff --git header")
    body = line[len(prefix) :]
    candidates: list[tuple[DiffPath, DiffPath]] = []
    for candidate_count, match in enumerate(re.finditer(r" b/", body), 1):
        if candidate_count > _GIT_HEADER_SEPARATOR_MAX:
            raise PatchFormatError("too many Git header separators")
        separator = match.start()
        old_path = DiffPath.from_git_token(body[:separator], "a/")
        new_path = DiffPath.from_git_token(body[separator + 1 :], "b/")
        if old_path is not None and new_path is not None:
            candidates.append((old_path, new_path))
    if len(candidates) == 1:
        return candidates[0]
    same_path = [pair for pair in candidates if pair[0].rel_path == pair[1].rel_path]
    if len(same_path) == 1:
        return same_path[0]
    raise PatchFormatError("non-canonical diff --git header")


def _hunk_body_indexes(lines: list[str]) -> set[int]:
    indexes: set[int] = set()
    in_hunk = False
    remaining_old: int | None = None
    remaining_new: int | None = None
    for index, line in enumerate(lines):
        if line.startswith("@@"):
            match = _HUNK_HEADER_RE.fullmatch(line)
            in_hunk = True
            remaining_old = _hunk_count(match.group(1)) if match else None
            remaining_new = _hunk_count(match.group(2)) if match else None
            continue
        if not in_hunk:
            continue
        if line.startswith("diff --git "):
            in_hunk = False
            continue
        if remaining_old == 0 and remaining_new == 0:
            if _is_paired_file_header(lines, index):
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


def diff_paths(patch_text: str) -> list[DiffPath]:
    """Return the canonical paths a unified diff touches (bounded first)."""
    bound_patch(patch_text)
    paths: list[DiffPath] = []
    seen: set[str] = set()

    def append_path(parsed: DiffPath) -> None:
        if parsed.rel_path not in seen:
            seen.add(parsed.rel_path)
            paths.append(parsed)

    lines = physical_lines(patch_text)
    hunk_body = _hunk_body_indexes(lines)
    for line in lines:
        if line.startswith("diff --git "):
            for parsed in _git_header_paths(line):
                append_path(parsed)
    for index, line in enumerate(lines):
        if index in hunk_body:
            continue
        for prefix in _EXTENDED_PATH_PREFIXES:
            if line.startswith(prefix):
                extended_path = DiffPath.from_extended_header(line, prefix)
                if extended_path is None:
                    raise PatchFormatError("non-canonical extended path header")
                append_path(extended_path)
                break
    for index, line in enumerate(lines[:-1]):
        if index in hunk_body or index + 1 in hunk_body:
            continue
        if not _is_paired_file_header(lines, index):
            continue
        pair_paths: list[DiffPath] = []
        for marker, header in (("---", line), ("+++", lines[index + 1])):
            header_path = DiffPath.from_diff_header(header, marker)
            if header_path is None:
                if _is_dev_null_header(header, marker):
                    continue
                raise PatchFormatError("non-canonical paired file header")
            pair_paths.append(header_path)
        if not pair_paths:
            raise PatchFormatError("paired file header has no repository path")
        for parsed in pair_paths:
            append_path(parsed)
    return paths


def bound_patch(patch_text: str) -> None:
    """Enforce the RFC-0026 C40/C41 canonical patch limits."""
    if len(patch_text.encode("utf-8")) > PATCH_MAX_BYTES:
        raise PatchBoundError("patch exceeds max bytes")
    lines = physical_lines(patch_text)
    if sum(line.startswith("@@") for line in lines) > PATCH_MAX_HUNKS:
        raise PatchBoundError("patch exceeds max hunks")
    hunk_body = _hunk_body_indexes(lines)
    current_hunk_lines = 0
    for index, line in enumerate(lines):
        if line.startswith("@@"):
            current_hunk_lines = 0
        elif index in hunk_body:
            current_hunk_lines += 1
            if current_hunk_lines > PATCH_MAX_LINES_PER_HUNK:
                raise PatchBoundError("patch exceeds max lines per hunk")


def _patch_has_changed_hunk(lines: list[str]) -> bool:
    file_header_seen = False
    in_hunk = False
    remaining_old = remaining_new = 0
    hunk_changed = completed_change = False
    for index, line in enumerate(lines):
        if in_hunk:
            if line == r"\ No newline at end of file":
                continue
            if line.startswith(" ") and remaining_old and remaining_new:
                remaining_old -= 1
                remaining_new -= 1
            elif line.startswith("-") and remaining_old:
                remaining_old -= 1
                hunk_changed = True
            elif line.startswith("+") and remaining_new:
                remaining_new -= 1
                hunk_changed = True
            else:
                return False
            if remaining_old == 0 and remaining_new == 0:
                completed_change = completed_change or hunk_changed
                in_hunk = False
            continue
        if line.startswith("diff --git "):
            file_header_seen = False
        elif _is_paired_file_header(lines, index):
            file_header_seen = True
        elif line.startswith("+++ ") and index and lines[index - 1].startswith("--- "):
            continue
        elif line.startswith("@@"):
            match = _HUNK_HEADER_RE.fullmatch(line)
            if not file_header_seen or match is None:
                return False
            old_count, new_count = match.groups()
            remaining_old = _hunk_count(old_count)
            remaining_new = _hunk_count(new_count)
            hunk_changed = False
            in_hunk = bool(remaining_old or remaining_new)
        elif line.startswith(("+", "-")):
            return False
    return completed_change and not in_hunk


def _git_metadata_block_state(
    git_paths: tuple[DiffPath, DiffPath],
    fields: dict[str, str],
) -> tuple[bool, bool]:
    """Validate one Git metadata block and report whether it changes content."""

    rename = {key for key in fields if key.startswith("rename ")}
    copy = {key for key in fields if key.startswith("copy ")}
    if rename and (rename != {"rename from", "rename to"} or copy):
        return False, False
    if copy and copy != {"copy from", "copy to"}:
        return False, False
    old_path, new_path = (path.rel_path for path in git_paths)
    if rename and (
        fields["rename from"] != old_path or fields["rename to"] != new_path
    ):
        return False, False
    if copy and (fields["copy from"] != old_path or fields["copy to"] != new_path):
        return False, False

    modes = {
        key
        for key in fields
        if key in {"old mode", "new mode", "new file mode", "deleted file mode"}
    }
    if modes & {"old mode", "new mode"} and modes != {"old mode", "new mode"}:
        return False, False
    if modes & {"new file mode", "deleted file mode"} and len(modes) != 1:
        return False, False
    mode_changed = (
        modes in ({"new file mode"}, {"deleted file mode"})
        or modes == {"old mode", "new mode"}
        and fields["old mode"] != fields["new mode"]
    )
    if mode_changed and not rename and not copy and old_path != new_path:
        return False, False
    return True, bool(rename or copy or mode_changed)


def _metadata_state(lines: list[str]) -> tuple[bool, bool]:
    """Validate metadata forms and relationships; return ``(valid, changed)``."""

    hunk_body = _hunk_body_indexes(lines)
    paired_indexes = {
        item
        for index in range(len(lines) - 1)
        if _is_paired_file_header(lines, index)
        for item in (index, index + 1)
    }
    current_paths: tuple[DiffPath, DiffPath] | None = None
    current_fields: dict[str, str] = {}
    metadata_changed = False

    def finish_block() -> bool:
        nonlocal metadata_changed
        if current_paths is None:
            return not current_fields
        valid, changed = _git_metadata_block_state(current_paths, current_fields)
        metadata_changed = metadata_changed or changed
        return valid

    for index, line in enumerate(lines):
        if index in hunk_body or index in paired_indexes or not line:
            continue
        if line.startswith("diff --git "):
            if not finish_block():
                return False, False
            current_paths = _git_header_paths(line)
            current_fields = {}
            continue
        if _HUNK_HEADER_RE.fullmatch(line):
            continue
        extended_prefix = next(
            (prefix for prefix in _EXTENDED_PATH_PREFIXES if line.startswith(prefix)),
            None,
        )
        if extended_prefix is not None:
            if current_paths is None:
                return False, False
            key = extended_prefix.rstrip()
            parsed = DiffPath.from_extended_header(line, extended_prefix)
            if parsed is None or key in current_fields:
                return False, False
            current_fields[key] = parsed.rel_path
            continue
        if _MODE_HEADER_RE.fullmatch(line):
            if current_paths is None:
                return False, False
            key = next(
                prefix
                for prefix in (
                    "old mode",
                    "new mode",
                    "new file mode",
                    "deleted file mode",
                )
                if line.startswith(f"{prefix} ")
            )
            if key in current_fields:
                return False, False
            current_fields[key] = line[len(key) + 1 :]
            continue
        if _INDEX_HEADER_RE.fullmatch(line) or _SIMILARITY_HEADER_RE.fullmatch(line):
            if current_paths is None:
                return False, False
            continue
        return False, False
    return (True, metadata_changed) if finish_block() else (False, False)


def validate_patch(patch_text: str) -> list[DiffPath]:
    """Validate a changed canonical patch and return all touched paths."""
    paths = diff_paths(patch_text)
    lines = physical_lines(patch_text)
    text_changed = _patch_has_changed_hunk(lines)
    metadata_valid, metadata_changed = _metadata_state(lines)
    if not paths or not metadata_valid or not (text_changed or metadata_changed):
        raise PatchFormatError("patch must be a changed canonical unified diff")
    return paths
