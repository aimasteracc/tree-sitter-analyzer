"""NO1-010B patch-verifier core (RFC-0026 §2/§3, C40/C41).

Pure-logic pieces of the runner: segment-aware allowlist enforcement,
canonical patch-input bounds (C40/C41), and the five-criterion verdict
classifier. The sandboxed execution and staleness projection live with the
harness bridge.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .record import BenchmarkRecordError, UnknownReasonCode, path_allowed

# Canonical patch limits, bound into the registered manifest (RFC-0026 C41).
PATCH_MAX_BYTES = 1 * 1024 * 1024
PATCH_MAX_HUNKS = 512
PATCH_MAX_LINES_PER_HUNK = 2000
_HUNK_COUNT_MAX_DIGITS = len(str(PATCH_MAX_BYTES))
_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@(?: .*)?$")


class PatchBoundError(ValueError):
    """An over-bound patch; the runner must score it UNKNOWN, never apply it."""


class PatchFormatError(ValueError):
    """A diff header whose touched paths cannot be classified safely."""


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
        raw = header_line[len(prefix) :].rstrip()
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


def _physical_lines(patch_text: str) -> list[str]:
    """Split LF-delimited patch lines without a synthetic trailing item."""
    lines = patch_text.split("\n")
    if patch_text.endswith("\n"):
        lines.pop()
    return lines


def _is_dev_null_header(header_line: str, marker: str) -> bool:
    prefix = f"{marker} "
    return header_line.startswith(prefix) and header_line[len(prefix) :].rstrip() == (
        "/dev/null"
    )


def _is_paired_file_header(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    old_header, new_header = lines[index], lines[index + 1]
    return old_header.startswith("--- ") and new_header.startswith("+++ ")


def _hunk_count(raw: str | None) -> int:
    """Parse one hunk count without entering Python's unbounded-int path."""
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
    separator = body.find(" b/")
    if separator < 0 or body.find(" b/", separator + 1) >= 0:
        raise PatchFormatError("non-canonical diff --git header")
    old_path = DiffPath.from_git_token(body[:separator], "a/")
    if old_path is None:
        raise PatchFormatError("non-canonical diff --git header")
    new_path = DiffPath.from_git_token(body[separator + 1 :], "b/")
    if new_path is None:
        raise PatchFormatError("non-canonical diff --git header")
    return old_path, new_path


def _hunk_body_indexes(lines: list[str]) -> set[int]:
    """Return physical line indexes belonging to parsed unified-diff hunks."""

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

    lines = _physical_lines(patch_text)
    hunk_body = _hunk_body_indexes(lines)
    for line in lines:
        if not line.startswith("diff --git "):
            continue
        for parsed in _git_header_paths(line):
            append_path(parsed)
    for index, line in enumerate(lines[:-1]):
        if index in hunk_body or index + 1 in hunk_body:
            continue
        if not line.startswith("--- ") or not lines[index + 1].startswith("+++ "):
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
    """Enforce the canonical patch limits (RFC-0026 C40/C41).

    Over-bound patches raise :class:`PatchBoundError`; the runner scores them
    ``UNKNOWN`` and never invokes ``git apply``.
    """
    if len(patch_text.encode("utf-8")) > PATCH_MAX_BYTES:
        raise PatchBoundError("patch exceeds max bytes")
    lines = _physical_lines(patch_text)
    hunks = 0
    for line in lines:
        if line.startswith("@@"):
            hunks += 1
    if hunks > PATCH_MAX_HUNKS:
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


def allowlist_violations(
    touched: Iterable[str],
    allowed_paths: tuple[str, ...],
) -> list[str]:
    """Return touched paths that violate the allowlist.

    Directory entries match segment-aware descendants. RFC-0026 C25/C58 has
    no trusted-artifact exception inside the immutable candidate tree: runner
    caches and coverage data must be redirected to scratch, and any such path
    appearing here is a violation.
    """
    violations = []
    for rel in touched:
        try:
            allowed = path_allowed(rel, allowed_paths)
        except BenchmarkRecordError:
            allowed = False
        if not allowed:
            violations.append(rel)
    return violations


@dataclass(frozen=True)
class Verdict:
    status: str  # PASS | FAIL | UNKNOWN
    reason_code: str | None = None  # product/unknown reason, or None for PASS

    def as_reason(self) -> str:
        return self.reason_code or "PASS"


def preflight_agent_patch(patch_text: str) -> Verdict | None:
    """Map bounded agent-patch input failures to closed UNKNOWN outcomes."""
    try:
        diff_paths(patch_text)
    except PatchBoundError:
        return Verdict("UNKNOWN", "PATCH_OVER_BOUND")
    except (PatchFormatError, UnicodeEncodeError):
        return Verdict("UNKNOWN", "AGENT_OUTPUT_ERROR")
    return None


def classify(
    *,
    path_ok: bool,
    oracle_ok: bool,
    verification_ok: bool,
    stale_ok: bool,
    unsupported_ok: bool,
    selection_ok: bool | None = None,
    unknown_reason: UnknownReasonCode | None = None,
) -> Verdict:
    """Map the five VCSR criteria to an exact terminal verdict/reason pair.

    ``UNKNOWN`` takes precedence over every FAIL (RFC-0026 §3 fail-closed);
    the first failing criterion in a fixed order names the reason code.
    """
    if unknown_reason is not None:
        return Verdict("UNKNOWN", unknown_reason)
    if not path_ok:
        return Verdict("FAIL", "PATH_VIOLATION")
    if not oracle_ok:
        return Verdict("FAIL", "ORACLE_FAILED")
    if not verification_ok:
        return Verdict("FAIL", "VERIFICATION_FAILED")
    if not stale_ok:
        return Verdict("FAIL", "STALE_ROWS")
    if not unsupported_ok:
        return Verdict("FAIL", "UNSUPPORTED_RELATIONSHIP")
    if selection_ok is False:
        return Verdict("FAIL", "TEST_SELECTION_FAILED")
    return Verdict("PASS")
