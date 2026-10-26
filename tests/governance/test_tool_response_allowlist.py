"""The tool-response allowlist may only shrink.

``tests/tool_response_allowlist.py`` silences known envelope violations found
by ``tests/pytest_tool_response_guard.py``. Each entry must be well formed and
name a tracking issue, and the number of entries is pinned: fixing a producer
removes its entry and lowers ``MAX_ENTRIES`` in the same PR. Raising it is a
review-visible decision, never a side effect.
"""

from __future__ import annotations

import re

from tests.tool_response_allowlist import ALLOWLIST
from tree_sitter_analyzer.mcp.tools.tool_response import ENVELOPE_RULES

#: Pinned entry count. Lower it when an entry is removed; never raise it to
#: make a new violation pass. Fix the producer instead.
MAX_ENTRIES = 0

_ISSUE = re.compile(r"^#\d+$")
_KEYS = {"tool", "rule", "issue", "reason"}


def test_allowlist_does_not_grow() -> None:
    assert len(ALLOWLIST) <= MAX_ENTRIES, (
        f"tests/tool_response_allowlist.py has {len(ALLOWLIST)} entries; the "
        f"pinned maximum is {MAX_ENTRIES}. Fix the producer instead of "
        "allowlisting a new violation."
    )


def test_pin_is_tight() -> None:
    # A removed entry must lower the pin, or the slack lets a new one slip in.
    assert len(ALLOWLIST) == MAX_ENTRIES, (
        f"lower MAX_ENTRIES to {len(ALLOWLIST)} in {__file__}"
    )


def test_entries_are_well_formed() -> None:
    malformed = [
        entry
        for entry in ALLOWLIST
        if set(entry) != _KEYS
        or entry["rule"] not in ENVELOPE_RULES
        or not _ISSUE.match(entry["issue"])
        or not entry["tool"].strip()
        or not entry["reason"].strip()
    ]
    assert malformed == []


def test_entries_are_unique() -> None:
    pairs = [(entry["tool"], entry["rule"]) for entry in ALLOWLIST]
    assert len(pairs) == len(set(pairs))
