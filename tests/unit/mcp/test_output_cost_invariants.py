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

ASSERTION STYLE (locked exact-assertion rule, CLAUDE.md §0): absolute byte
counts here are environment-dependent (responses embed tmp paths), so exact
``==`` pins would be flaky. Per the rule's exception clause these tests assert
**documented relationships** (``toon <= json``, ``compact < default``), never
hand-waved numeric ceilings. A loose ceiling (e.g. ``ratio <= 2.5``) was
reviewed out: it passed despite the known ~1.96x bug — false confidence.
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


def _measure(tmp_path, tool_cls, needs_file: bool, **extra) -> tuple[int, int]:
    """Return (json_bytes, toon_bytes) for one tool invocation pair."""
    src = tmp_path / "sample.py"
    src.write_text(_SAMPLE)
    root = str(tmp_path)
    base: dict = {"file_path": str(src)} if needs_file else {}
    json_resp = asyncio.run(tool_cls(root).execute({**base, "output_format": "json"}))
    toon_resp = asyncio.run(
        tool_cls(root).execute({**base, "output_format": "toon", **extra})
    )
    return _bytes(json_resp), _bytes(toon_resp)


# (tool_cls, needs_file, human_id). project_health takes no file_path (strict
# params reject it) — it scans the whole tmp project.
_DECISION_TOOLS = [
    (FileHealthTool, True, "file_health"),
    (SafeToEditTool, True, "safe_to_edit"),
    (ProjectHealthTool, False, "project_health"),
]


@pytest.mark.parametrize(("tool_cls", "needs_file", "tool_id"), _DECISION_TOOLS)
@pytest.mark.parametrize("compact", [False, True], ids=["default", "compact_only"])
@pytest.mark.xfail(
    strict=True,
    reason=(
        "CLAUDE.md §1 premise ('TOON is 50-70% more token-efficient than JSON') "
        "is FALSE for metadata-heavy decision tools: default TOON is ~1.96x JSON "
        "(duplication) and even compacted (RFC-0012 Phase 1) it is ~1.08x — TOON "
        "only wins on bulk/tabular array data. This strict-xfail encodes the "
        "minimal floor of the §1 claim (toon <= json) per mode and is the "
        "ratchet: when RFC-0012 Phase 2 (disjoint-by-default) lands and a mode "
        "stops being larger than JSON, that parametrization flips to XPASS and "
        "FORCES removing its xfail so the invariant becomes enforced. Do NOT "
        "delete this to make CI quiet — that would re-bury the exact problem "
        "this file exists to surface."
    ),
)
def test_toon_meets_its_efficiency_premise(
    tmp_path, tool_cls, needs_file, tool_id, compact
):
    """The §1 premise as an executable invariant: TOON must be <= JSON.

    Currently xfail in BOTH modes (the premise does not hold for these
    tools). The point is not to pass — it is to keep the false premise
    *visible and tracked* in CI instead of asleep in a design doc.
    """
    jb, tb = _measure(tmp_path, tool_cls, needs_file, compact_only=compact)
    mode = "compact" if compact else "default"
    assert tb <= jb, f"{tool_id}[{mode}]: TOON {tb}B > JSON {jb}B ({tb / jb:.2f}x)"


@pytest.mark.parametrize(("tool_cls", "needs_file", "tool_id"), _DECISION_TOOLS)
def test_compact_only_strictly_reduces_default_toon(
    tmp_path, tool_cls, needs_file, tool_id
):
    """RFC-0012 Phase 1's reason to exist, as an invariant: compact < default.

    ``compact_only=True`` strips duplicated top-level metadata down to the
    TOON control surface, so for metadata-heavy decision tools the compact
    response must be STRICTLY smaller than the default TOON response. If
    this ever fails, Phase 1 has regressed into a no-op (the exact
    "fixed 3 times, never actually fixed" denylist trap — see
    feedback_toon-json-dup-denylist-trap)."""
    _, tb_default = _measure(tmp_path, tool_cls, needs_file)
    _, tb_compact = _measure(tmp_path, tool_cls, needs_file, compact_only=True)
    print(f"[{tool_id}] toon default={tb_default}B compact={tb_compact}B")
    assert tb_compact < tb_default, (
        f"{tool_id}: compact_only TOON ({tb_compact}B) is not smaller than "
        f"default TOON ({tb_default}B) — RFC-0012 Phase 1 compaction is a no-op."
    )


# ── RFC-0015 P1 rule-11 differential invariant ────────────────────────────────


def test_class_diagram_scoped_smaller_than_unscoped(monkeypatch) -> None:
    """Scoped class diagram bytes < unscoped bytes (rule-11 differential invariant).

    Scoping (file_path or class_name) restricts the node/edge set, so the
    serialized response for a scoped request MUST be strictly smaller than
    the unscoped whole-project response on the same class set.

    Exact == pin not applicable here because bytes vary with project content;
    the invariant is the *relationship* between scoped and unscoped (CLAUDE.md
    rule-11 exception for nondeterministic values — assert a documented
    invariant, not a hand-waved bound).
    """
    import asyncio
    import json as _json

    from tree_sitter_analyzer.mcp.tools import uml_tool as _uml_tool

    # A synthetic class set with 10 classes, only one in the target file.
    # The whole-project diagram covers all 10; the file-scoped diagram covers 1.
    ALL_CLASSES = [
        {"name": f"Class{i}", "parents": [], "file": f"src/mod{i}.py"}
        for i in range(10)
    ]
    TARGET_FILE = "src/mod0.py"

    class FakeHierarchyAll:
        def __init__(self, cache):
            pass

        def build(self):
            pass

        def all_classes(self):
            return ALL_CLASSES

    # Sentinel cache object: prevents _open_cache from trying to open a real DB.
    class SentinelCache:
        pass

    class FakeExporterProvider:
        def __init__(self, project_root):
            pass

        def uml_exporter(self):
            import tree_sitter_analyzer.uml_export as _export

            # Pass the sentinel cache so _open_cache skips ASTCache("/repo")
            return _export.UMLExporter("/repo", cache=SentinelCache())

    # Patch ClassHierarchy for the duration of this test
    import tree_sitter_analyzer.uml_export as _uml_export

    monkeypatch.setattr(_uml_export, "ClassHierarchy", FakeHierarchyAll)
    monkeypatch.setattr(_uml_tool, "CodeGraphVisualizationHub", FakeExporterProvider)

    tool = _uml_tool.CodeGraphUMLTool("/repo")

    # Unscoped
    unscoped = asyncio.run(tool.execute({"diagram": "class", "output_format": "json"}))
    # File-scoped
    scoped = asyncio.run(
        tool.execute(
            {"diagram": "class", "output_format": "json", "file_path": TARGET_FILE}
        )
    )

    unscoped_bytes = len(_json.dumps(unscoped, ensure_ascii=False))
    scoped_bytes = len(_json.dumps(scoped, ensure_ascii=False))

    assert scoped_bytes < unscoped_bytes, (
        f"Scoped class diagram ({scoped_bytes}B) is not smaller than "
        f"unscoped ({unscoped_bytes}B) — file_path scoping is a no-op."
    )
