"""NO1-010B patch-verifier core (RFC-0026 §2/§3, C40/C41).

Pure-logic pieces of the runner: segment-aware allowlist enforcement,
canonical patch-input bounds, and the five-criterion verdict classifier.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .patch import (
    PATCH_MAX_BYTES,
    PATCH_MAX_HUNKS,
    PATCH_MAX_LINES_PER_HUNK,
    DiffPath,
    PatchBoundError,
    PatchFormatError,
    bound_patch,
    diff_paths,
    validate_patch,
)
from .record import BenchmarkRecordError, UnknownReasonCode, path_allowed

__all__ = [
    "PATCH_MAX_BYTES",
    "PATCH_MAX_HUNKS",
    "PATCH_MAX_LINES_PER_HUNK",
    "DiffPath",
    "PatchBoundError",
    "PatchFormatError",
    "Verdict",
    "allowlist_violations",
    "bound_patch",
    "classify",
    "diff_paths",
    "preflight_agent_patch",
]


def allowlist_violations(
    touched: Iterable[str],
    allowed_paths: tuple[str, ...],
) -> list[str]:
    """Return touched paths that violate the segment-aware allowlist."""
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
    reason_code: str | None = None

    def as_reason(self) -> str:
        return self.reason_code or "PASS"


def preflight_agent_patch(patch_text: str) -> Verdict | None:
    """Map bounded agent-patch input failures to closed UNKNOWN outcomes."""
    try:
        validate_patch(patch_text)
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
    """Map the VCSR criteria to an exact terminal verdict/reason pair."""
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
