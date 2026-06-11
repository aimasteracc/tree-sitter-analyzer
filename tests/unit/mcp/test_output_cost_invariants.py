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
        "this file exists to surface. "
        "Last measured: 2026-06-11 (file_health ~1.96x, safe_to_edit ~1.96x, "
        "project_health ~1.08x compact). Re-measure after RFC-0012 Phase 2 lands."
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


# ── Issue #439: viz TOON/JSON duplication — rule-11 ratchets ─────────────────
#
# Before the fix, viz action=uml shipped nodes/edges/mermaid at the top level
# AND inside toon_content (1.78x).  After adding those fields to redundant_fields
# in apply_toon_format_to_response the top-level duplicates are dropped and
# TOON becomes < JSON.
#
# These tests are NOT xfail — the fix ships alongside them.  If a future change
# re-introduces the duplication, these go RED immediately.


def _make_synthetic_uml_response(n_classes: int = 20) -> dict:
    """Build a synthetic UML response dict (mimics CodeGraphUMLTool.execute output)."""
    from tree_sitter_analyzer.mcp.tools._response_builder import build_response
    from tree_sitter_analyzer.uml_export import UMLDiagram, UMLEdge

    edges = [
        UMLEdge(source=f"Class{i}", target=f"Class{i + 1}") for i in range(n_classes)
    ]
    nodes = [f"Class{i}" for i in range(n_classes + 1)]
    mermaid = "classDiagram\n" + "\n".join(
        [f"  Class{i} --> Class{i + 1}" for i in range(n_classes)]
    )
    diagram = UMLDiagram(
        diagram_type="class",
        mermaid_type="classDiagram",
        mermaid=mermaid,
        nodes=nodes,
        edges=edges,
    )
    return build_response(verdict="INFO", **diagram.to_dict())


def test_viz_uml_toon_no_bulk_duplication() -> None:
    """After the fix: nodes/edges/mermaid must NOT appear at top level of TOON response.

    These three fields are the bulk-content drivers of the 1.78x issue (#439).
    They are encoded inside toon_content and must be stripped from top level.
    """
    from tree_sitter_analyzer.mcp.utils.format_helper import (
        apply_toon_format_to_response,
    )

    response = _make_synthetic_uml_response(20)
    toon_resp = apply_toon_format_to_response(response, "toon")

    assert toon_resp.get("format") == "toon"
    assert "toon_content" in toon_resp
    # Bulk fields must NOT appear at top level — disjoint invariant.
    assert "nodes" not in toon_resp, (
        "nodes duplicated at top level of viz TOON response"
    )
    assert "edges" not in toon_resp, (
        "edges duplicated at top level of viz TOON response"
    )
    assert "mermaid" not in toon_resp, (
        "mermaid duplicated at top level of viz TOON response"
    )


def test_viz_graph_toon_no_mermaid_duplication() -> None:
    """action=graph: mermaid must not appear at top level of TOON response."""
    from tree_sitter_analyzer.mcp.tools._response_builder import build_response
    from tree_sitter_analyzer.mcp.utils.format_helper import (
        apply_toon_format_to_response,
    )

    mermaid = "flowchart TD\n" + "\n".join([f"  A{i} --> B{i}" for i in range(30)])
    stats = {"mode": "full", "node_count": 60, "edge_count": 30}
    response = build_response(verdict="INFO", mermaid=mermaid, stats=stats)
    toon_resp = apply_toon_format_to_response(response, "toon")

    assert toon_resp.get("format") == "toon"
    assert "mermaid" not in toon_resp, (
        "mermaid duplicated at top level of graph TOON response"
    )


def test_viz_similarity_toon_no_groups_duplication() -> None:
    """action=similarity: groups must not appear at top level of TOON response."""
    from tree_sitter_analyzer.mcp.utils.format_helper import (
        apply_toon_format_to_response,
    )

    groups = [
        {
            "type": "structural",
            "functions": [f"mod{i}.func", f"mod{i + 1}.func"],
            "similarity": 0.95,
        }
        for i in range(15)
    ]
    response = {
        "success": True,
        "verdict": "CAUTION",
        "project_root": "/repo",
        "stats": {"total_clone_instances": 30},
        "groups": groups,
    }
    toon_resp = apply_toon_format_to_response(response, "toon")

    assert toon_resp.get("format") == "toon"
    assert "groups" not in toon_resp, (
        "groups duplicated at top level of similarity TOON response"
    )


def test_viz_uml_toon_smaller_than_json() -> None:
    """Rule-11 differential invariant: viz UML TOON bytes < JSON bytes.

    The TOON format encodes bulk array/string data more compactly than JSON.
    After stripping the top-level duplicates (nodes/edges/mermaid), the TOON
    response must be strictly smaller than the plain JSON response.
    """
    from tree_sitter_analyzer.mcp.utils.format_helper import (
        apply_toon_format_to_response,
    )

    response = _make_synthetic_uml_response(20)
    toon_resp = apply_toon_format_to_response(response, "toon")
    json_resp = apply_toon_format_to_response(response, "json")

    toon_bytes = len(json.dumps(toon_resp, ensure_ascii=False))
    json_bytes = len(json.dumps(json_resp, ensure_ascii=False))
    assert toon_bytes < json_bytes, (
        f"viz uml TOON ({toon_bytes}B) >= JSON ({json_bytes}B) — "
        f"duplication re-introduced ({toon_bytes / json_bytes:.2f}x)"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "viz action=graph response is dominated by a single mermaid text blob. "
        "TOON wraps it in a JSON-quoted string inside toon_content rather than "
        "encoding it as a tabular structure, so toon_bytes > json_bytes even after "
        "stripping mermaid from the top-level (no duplication, just format overhead). "
        "The disjoint invariant (test_viz_graph_toon_no_mermaid_duplication) IS "
        "enforced. This xfail tracks the toon<json premise for graph specifically — "
        "if TOON ever gains native multi-line-string compression, un-xfail this. "
        "Last measured: 2026-06-11 (graph 40-edge mermaid blob: toon ~1.12x JSON)."
    ),
)
def test_viz_graph_toon_smaller_than_json() -> None:
    """Rule-11 ratchet: viz graph TOON bytes < JSON bytes (currently xfail — no duplication,
    but toon_content wrapper overhead > savings on a single text-blob response).
    """
    from tree_sitter_analyzer.mcp.tools._response_builder import build_response
    from tree_sitter_analyzer.mcp.utils.format_helper import (
        apply_toon_format_to_response,
    )

    mermaid = "flowchart TD\n" + "\n".join([f"  A{i} --> B{i}" for i in range(40)])
    stats = {"mode": "full", "node_count": 80, "edge_count": 40}
    response = build_response(verdict="INFO", mermaid=mermaid, stats=stats)

    toon_resp = apply_toon_format_to_response(response, "toon")
    json_resp = apply_toon_format_to_response(response, "json")

    toon_bytes = len(json.dumps(toon_resp, ensure_ascii=False))
    json_bytes = len(json.dumps(json_resp, ensure_ascii=False))
    assert toon_bytes < json_bytes, (
        f"viz graph TOON ({toon_bytes}B) >= JSON ({json_bytes}B) — "
        f"({toon_bytes / json_bytes:.2f}x)"
    )


def test_viz_boundary_toon_disjoint() -> None:
    """Through the handle_call_tool boundary: viz TOON top-level keys ∩ bulk keys == ∅.

    The inner UML tool mock returns a RAW JSON dict (nodes/edges/mermaid still
    at top level — NOT pre-cleaned TOON). The mock then calls the REAL
    apply_toon_format_to_response so the strip executes inside the boundary
    path. This ensures the test fails the day the strip is reverted, not just
    the day a new field name is added.

    Previous version fed a pre-cleaned TOON response to the mock (the strip had
    already run, so the test was vacuously true — P2 finding from adversarial
    review 2026-06-11).
    """
    from unittest.mock import Mock
    from unittest.mock import patch as _patch

    from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
    from tree_sitter_analyzer.mcp.utils.format_helper import (
        apply_toon_format_to_response,
    )

    # RAW inner response — nodes/edges/mermaid are still at the top level.
    # This is what the tool produces BEFORE apply_toon_format_to_response runs.
    raw_inner_response = _make_synthetic_uml_response(10)
    # Sanity: confirm the raw response has bulk fields (otherwise the test is
    # vacuous in the opposite direction — nothing to strip).
    assert "nodes" in raw_inner_response, "fixture must include nodes before formatting"
    assert "edges" in raw_inner_response, "fixture must include edges before formatting"
    assert "mermaid" in raw_inner_response, (
        "fixture must include mermaid before formatting"
    )

    # Capture the handle_call_tool handler
    server = TreeSitterAnalyzerMCPServer("/repo")
    with _patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True):
        with _patch("tree_sitter_analyzer.mcp.server.Server") as mock_server_class:
            mock_srv = Mock()
            captured: dict = {}

            def cap_decorator(name):
                def decorator(func):
                    captured[name] = func
                    return func

                return decorator

            mock_srv.call_tool.return_value = cap_decorator("call_tool")
            mock_srv.list_tools.return_value = cap_decorator("list_tools")
            mock_srv.get_capabilities.return_value = {}
            mock_server_class.return_value = mock_srv
            server.create_server()

    handler = captured["call_tool"]

    # Patch the inner UML tool's execute to call the REAL formatting on the raw
    # response. This mirrors what CodeGraphUMLTool.execute does: it builds a raw
    # dict then passes it through apply_toon_format_to_response. By doing the
    # same here we ensure the strip actually runs inside the test path.
    viz_facade = server.tools["viz"]
    uml_inner = viz_facade.action_map["uml"]

    async def run_test():
        async def fake_execute(_args):
            return apply_toon_format_to_response(raw_inner_response, "toon")

        with _patch.object(uml_inner, "execute", new=fake_execute):
            result = await handler("viz", {"action": "uml", "output_format": "toon"})
        return json.loads(result[0].text)

    body = asyncio.run(run_test())

    assert body.get("format") == "toon", (
        f"expected format=toon, got: {body.get('format')}"
    )
    assert "toon_content" in body
    # Disjoint invariant: bulk fields must not appear at top level
    bulk_keys = {"nodes", "edges", "mermaid"}
    leaked = bulk_keys & set(body)
    assert leaked == set(), (
        f"Bulk fields leaked to top level via handle_call_tool boundary: {leaked}"
    )


# ── P1.2: global value-based bulk-strip invariant (2026-06-11) ────────────────
#
# Structural invariant: no top-level key of a TOON response should carry a
# "bulk" collection value unless that key is in TOON_CONTROL_SURFACE.
#
# Bulk = json.dumps(v) > _BULK_THRESHOLD_BYTES for list or dict values.
# Threshold is tuned to allow small metadata (agent_summary ~150 B,
# warnings with 1-2 items ~170 B) while catching any data payload
# (callers/callees/nodes/edges/tree/groups with 3+ real items each ~100+ B
# apiece → well above 500 B when combined).
#
# This is the test that makes a hypothetical new field "results_v2 = [big_list]"
# fail CI on the day it is written, regardless of its name.

_BULK_THRESHOLD_BYTES = 500


def _is_bulk(value: object) -> bool:
    """Return True when ``value`` is a list/dict that exceeds the bulk threshold.

    Derived from the strip rule: TOON_CONTROL_SURFACE contains only scalars
    (strings / booleans / None). Any list or dict at the top level that is
    large enough to be a data payload is "bulk" and must not survive stripping.

    Threshold: _BULK_THRESHOLD_BYTES (500 B serialised). This allows:
    - agent_summary dicts (~150 B) to pass
    - warnings with 1-2 items (~170 B) to pass
    - callers/callees/nodes/edges/tree/groups with 3+ items (>500 B) to be caught
    """
    if not isinstance(value, (list, dict)):
        return False
    return len(json.dumps(value, ensure_ascii=False)) > _BULK_THRESHOLD_BYTES


# Parametric bulk shapes — realistic payloads that tools produce at top level.
# Each tuple: (field_name, value).  The strip should eliminate ALL of these.
# Item counts are chosen so each payload serialises to > _BULK_THRESHOLD_BYTES.
_BULK_SHAPES: list[tuple[str, object]] = [
    # callers: list of caller dicts (callers_tool / call_graph_tool mode=callers)
    # 12 items × ~65 B each ≈ 780 B  (> 500 B threshold)
    (
        "callers",
        [
            {"name": f"caller_{i}", "file": f"src/module_{i}.py", "line": i * 5}
            for i in range(12)
        ],
    ),
    # callees: list of callee dicts (callees_tool / call_graph_tool mode=callees)
    # 12 items × ~65 B each ≈ 780 B
    (
        "callees",
        [
            {"name": f"callee_{i}", "file": f"src/module_{i}.py", "line": i * 5}
            for i in range(12)
        ],
    ),
    # tree: nested call-tree dict (callee_tree / caller_tree tools)
    # root + 10 children × ~60 B each ≈ 640 B
    (
        "tree",
        {
            "root": {
                "name": "entry_point",
                "file": "src/main.py",
                "line": 1,
                "children": [
                    {
                        "name": f"handler_{i}",
                        "file": f"src/handlers/handler_{i}.py",
                        "line": i * 10,
                        "children": [],
                    }
                    for i in range(10)
                ],
            },
            "max_depth": 3,
            "node_count": 11,
            "truncated": False,
        },
    ),
    # gaps: skills gap-category dict (agent_skills_tool) with many entries
    # 4 categories × ~15 items × ~10 B each ≈ 600 B
    (
        "gaps",
        {
            "missing_trigger_text": [f"skill_{i}" for i in range(15)],
            "missing_description": [f"tool_{i}" for i in range(12)],
            "missing_name": [f"script_{i}" for i in range(10)],
            "missing_completion_guidance": [f"agent_{i}" for i in range(8)],
        },
    ),
    # nodes: UML node list (viz action=uml)
    # 60 class names × ~9 B each ≈ 540 B
    ("nodes", [f"ClassName{i:03d}" for i in range(60)]),
    # edges: UML edge list (viz action=uml)
    # 20 edge dicts × ~45 B each ≈ 900 B
    (
        "edges",
        [{"source": f"ClassA{i}", "target": f"ClassB{i}"} for i in range(20)],
    ),
    # groups: similarity group list (viz action=similarity)
    # 15 groups × ~55 B each ≈ 825 B
    (
        "groups",
        [
            {
                "type": "structural",
                "functions": [f"module_{i}.func_alpha", f"module_{i + 1}.func_beta"],
            }
            for i in range(15)
        ],
    ),
]


@pytest.mark.parametrize(
    "field_name,bulk_value", _BULK_SHAPES, ids=[s[0] for s in _BULK_SHAPES]
)
def test_toon_strip_no_bulk_at_top_level(field_name: str, bulk_value: object) -> None:
    """Global structural invariant: no bulk list/dict survives TOON formatting.

    For every known bulk-payload shape, verify that apply_toon_format_to_response
    does NOT emit that field at the top level of the TOON response.

    Threshold: _BULK_THRESHOLD_BYTES (500 B). The synthetic payloads are sized
    to be clearly above this threshold so the invariant is not vacuous.

    This is the P1.2 test that makes any new tool field that emits a bulk list
    or dict fail CI the day it is written, regardless of the field name.
    """
    from tree_sitter_analyzer.mcp.utils.format_helper import (
        TOON_CONTROL_SURFACE,
        apply_toon_format_to_response,
    )

    # Sanity: the synthetic bulk value is large enough to be caught.
    assert _is_bulk(bulk_value), (
        f"Test setup error: {field_name} value is not bulk "
        f"({len(json.dumps(bulk_value))} B < {_BULK_THRESHOLD_BYTES} B threshold). "
        "Increase the payload size."
    )
    # Sanity: the field is NOT in TOON_CONTROL_SURFACE (otherwise stripping it
    # would be wrong — control-surface fields must survive).
    assert field_name not in TOON_CONTROL_SURFACE, (
        f"Test setup error: {field_name!r} is in TOON_CONTROL_SURFACE. "
        "If it was intentionally promoted to the control surface, remove it from _BULK_SHAPES."
    )

    raw_response: dict = {
        "success": True,
        "verdict": "INFO",
        "format": "json",  # raw — not yet TOON-formatted
        field_name: bulk_value,
        "summary_line": f"Test payload for {field_name}",
    }
    toon_resp = apply_toon_format_to_response(raw_response, "toon")

    assert toon_resp.get("format") == "toon", (
        f"apply_toon_format_to_response did not produce a TOON response for {field_name}"
    )
    assert "toon_content" in toon_resp, (
        f"toon_content missing from TOON response for {field_name}"
    )
    assert field_name not in toon_resp, (
        f"Bulk field {field_name!r} survived TOON formatting at the top level. "
        f"Add it to redundant_fields in apply_toon_format_to_response."
    )
    # Secondary: all remaining keys should be in TOON_CONTROL_SURFACE or
    # be small scalar/metadata fields (not bulk collections).
    leaked_bulk = {
        k for k, v in toon_resp.items() if k not in TOON_CONTROL_SURFACE and _is_bulk(v)
    }
    assert leaked_bulk == set(), (
        f"Unexpected bulk collections remain at top level: {leaked_bulk}. "
        f"Keys: {sorted(toon_resp.keys())}"
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
