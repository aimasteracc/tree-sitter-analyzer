"""Primary-key deduplication for streamed constraint violations."""

from __future__ import annotations


def claim_violation(
    seen: set[tuple[str, str, int, str]],
    rule_id: str,
    caller_file: str,
    caller_line: int,
    callee_name: str,
) -> bool:
    """Claim one persisted violation identity, returning false for duplicates."""
    key = (rule_id, caller_file, caller_line, callee_name)
    if key in seen:
        return False
    seen.add(key)
    return True
