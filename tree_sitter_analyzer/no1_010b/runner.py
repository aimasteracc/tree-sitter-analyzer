"""NO1-010B patch-verifier core (RFC-0026 §2/§3, C40/C41).

Pure-logic pieces of the runner: segment-aware allowlist enforcement,
canonical patch-input bounds (C40/C41), and the five-criterion verdict
classifier. The sandboxed execution and staleness projection live with the
harness bridge.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .record import UnknownReasonCode, path_allowed

# Canonical patch limits, bound into the registered manifest (RFC-0026 C41).
PATCH_MAX_BYTES = 1 * 1024 * 1024
PATCH_MAX_HUNKS = 512
PATCH_MAX_LINES_PER_HUNK = 2000


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


def diff_paths(patch_text: str) -> list[DiffPath]:
    """Return the canonical paths a unified diff touches (bounded first)."""
    bound_patch(patch_text)
    paths: list[DiffPath] = []
    lines = _physical_lines(patch_text)
    for line in lines:
        if not line.startswith("diff --git "):
            continue
        tokens = line.split(" ")
        if len(tokens) != 4:
            # Quoted/escaped or otherwise ambiguous paths fail closed. The
            # bounded seed corpus uses canonical unquoted repository paths.
            raise PatchFormatError("non-canonical diff --git header")
        for token, side in ((tokens[2], "a/"), (tokens[3], "b/")):
            parsed = DiffPath.from_git_token(token, side)
            if parsed is None:
                raise PatchFormatError("non-canonical diff --git header")
            if parsed not in paths:
                paths.append(parsed)
    for index, line in enumerate(lines[:-1]):
        if not line.startswith("--- ") or not lines[index + 1].startswith("+++ "):
            continue
        for marker, header in (("---", line), ("+++", lines[index + 1])):
            parsed = DiffPath.from_diff_header(header, marker)
            if parsed is not None and parsed not in paths:
                paths.append(parsed)
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
    current_hunk_lines = 0
    in_hunk = False
    for index, line in enumerate(lines):
        if line.startswith("@@"):
            in_hunk = True
            current_hunk_lines = 0
        elif in_hunk and (
            line.startswith("diff --git ")
            or (
                line.startswith("--- ")
                and index + 1 < len(lines)
                and lines[index + 1].startswith("+++ ")
            )
        ):
            in_hunk = False
        elif in_hunk:
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
        if not path_allowed(rel, allowed_paths):
            violations.append(rel)
    return violations


@dataclass(frozen=True)
class Verdict:
    status: str  # PASS | FAIL | UNKNOWN
    reason_code: str | None = None  # product/unknown reason, or None for PASS

    def as_reason(self) -> str:
        return self.reason_code or "PASS"


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
