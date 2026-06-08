"""Output-cost invariants — the missing efficiency *oracle*.

WHY THIS FILE EXISTS (read before editing):

The project shipped a TOON response that was ~196% the size of plain JSON for
metadata-heavy decision tools — i.e. the "token-efficient" format was almost
**twice as expensive** as the format it replaced. ~18,000 tests were green
through all of it, because every test asserted *"does the output match the
shape I expected?"* and none asserted *"is the output actually cheaper?"*. The
waste was found by a human **using** the tool, not by the suite.

Root cause: a *conformance* suite (does code match its spec?) cannot discover
that the spec itself is wasteful. The premise "TOON is 50-70% more
token-efficient than JSON" (CLAUDE.md §1) was written as prose and **never
encoded as an executable, falsifiable assertion**. So this file turns that
premise into a measured invariant. If a format claim is in a design doc, it
belongs here as a test — otherwise it is a belief, not a fact.

These are *non-functional* assertions (bytes, not fields). They are
deliberately coarse and self-documenting (they print the measured ratio) so the
cost is **visible in CI**, not buried.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool
from tree_sitter_analyzer.mcp.tools.project_health_tool import ProjectHealthTool
from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool

_SAMPLE = "def f(x):\n    if x:\n        return 1\n    return 2\n"


def _bytes(payload: dict) -> int:
    return len(json.dumps(payload, ensure_ascii=False))


def _measure(tmp_path, tool_cls, needs_file: bool) -> tuple[int, int, float]:
    """Return (json_bytes, toon_bytes, ratio) for a tool, default TOON mode."""
    src = tmp_path / "sample.py"
    src.write_text(_SAMPLE)
    root = str(tmp_path)
    base: dict = {"file_path": str(src)} if needs_file else {}
    json_resp = asyncio.run(tool_cls(root).execute({**base, "output_format": "json"}))
    toon_resp = asyncio.run(tool_cls(root).execute({**base, "output_format": "toon"}))
    jb, tb = _bytes(json_resp), _bytes(toon_resp)
    return jb, tb, tb / jb


# (tool_cls, needs_file, human_id). project_health takes no file_path (strict
# params reject it) — it scans the whole tmp project.
_DECISION_TOOLS = [
    (FileHealthTool, True, "file_health"),
    (SafeToEditTool, True, "safe_to_edit"),
    (ProjectHealthTool, False, "project_health"),
]

#: A regression *ceiling* on the default TOON/JSON size ratio per decision
#: tool. This is the snapshot guard: it passes today (the bug sits at ~1.96×)
#: but FAILS LOUDLY if a change makes the duplication worse (e.g. a third
#: encoding pass pushing it past ~2.5×). It is the test that turns "nobody
#: noticed it got bigger" into a red build.
_TOON_RATIO_CEILING = 2.5


@pytest.mark.parametrize(("tool_cls", "needs_file", "tool_id"), _DECISION_TOOLS)
def test_default_toon_not_grossly_larger_than_json(tmp_path, tool_cls, needs_file, tool_id):
    """Default TOON output must not blow past the recorded size ceiling.

    Snapshot/budget guard (analysis item #2): makes the *cost* visible and
    catches a *worsening* regression even though the absolute size is still
    bad by default (tracked separately below).
    """
    jb, tb, ratio = _measure(tmp_path, tool_cls, needs_file)
    print(f"[{tool_id}] json={jb}B toon={tb}B ratio={ratio:.2f}x")
    assert ratio <= _TOON_RATIO_CEILING, (
        f"{tool_id}: default TOON is {ratio:.2f}x JSON ({tb}B vs {jb}B), over the "
        f"{_TOON_RATIO_CEILING}x ceiling — the TOON/JSON duplication got WORSE. "
        "See RFC-0012."
    )


@pytest.mark.parametrize(("tool_cls", "needs_file", "tool_id"), _DECISION_TOOLS)
@pytest.mark.xfail(
    strict=True,
    reason=(
        "CLAUDE.md §1 premise ('TOON is 50-70% more token-efficient than JSON') "
        "is FALSE for metadata-heavy decision tools: default TOON is ~1.96x JSON "
        "(duplication) and even compacted (RFC-0012 Phase 1) it is ~1.08x — TOON "
        "only wins on bulk/tabular array data. This strict-xfail encodes the "
        "minimal floor of the §1 claim (toon <= json) and is the ratchet: when "
        "RFC-0012 Phase 2 (disjoint-by-default) lands and TOON stops being larger "
        "than JSON, this flips to XPASS and FORCES removing the xfail so the "
        "invariant becomes enforced. Do NOT delete this to make CI quiet — that "
        "would re-bury the exact problem this file exists to surface."
    ),
)
def test_toon_meets_its_efficiency_premise(tmp_path, tool_cls, needs_file, tool_id):
    """The §1 premise as an executable invariant: TOON must be <= JSON.

    Currently xfail (the premise does not hold for these tools). The point is
    not to pass — it is to keep the false premise *visible and tracked* in CI
    instead of asleep in a design doc.
    """
    jb, tb, ratio = _measure(tmp_path, tool_cls, needs_file)
    assert tb <= jb, f"{tool_id}: TOON {tb}B > JSON {jb}B (ratio {ratio:.2f}x)"
