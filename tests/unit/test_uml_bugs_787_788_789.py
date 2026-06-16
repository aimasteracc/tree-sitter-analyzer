"""Tests for three UML bugs: #787 sequence truncated flag, #788 empty activity,
#789 include_tests priority.

Written RED-first (TDD): each test must FAIL before the fix and PASS after.
"""

from __future__ import annotations

from tree_sitter_analyzer import uml_export
from tree_sitter_analyzer.uml_export import UMLExporter

# ── Bug #787 — sequence diagram truncated flag ────────────────────────────────


def _make_call_path_result(truncated: bool, hops: list) -> object:
    """Return a fake CallPathFinder result."""

    class FakeResult:
        pass

    result = FakeResult()
    result.truncated = truncated  # type: ignore[attr-defined]

    def to_dict():
        return {"paths": [{"hops": hops}]}

    result.to_dict = to_dict  # type: ignore[attr-defined]
    return result


def test_sequence_truncated_false_when_complete_2node_1edge(monkeypatch) -> None:
    """Bug #787: a 2-node/1-edge direct call with result.truncated=True must
    produce truncated=False in the diagram — the diagram itself is not clipped.
    """

    class FakeFinder:
        def __init__(self, project_root, cache=None):
            pass

        def find_path(self, source_function, target_function, max_depth, max_paths):
            return _make_call_path_result(
                truncated=True,  # BFS said it found the path — set truncated=True
                hops=[{"caller": "entry", "callee": "service"}],
            )

    monkeypatch.setattr(uml_export, "CallPathFinder", FakeFinder)

    exporter = UMLExporter("/repo", cache=object())
    diagram = exporter.sequence_diagram(
        source="entry",
        target="service",
        max_hops=12,  # far larger than 1 hop — no clipping occurs
    )

    # The diagram is complete: 1 hop, max_hops=12, nothing was cut.
    # truncated must be False even though result.truncated was True.
    assert diagram.truncated is False


def test_sequence_truncated_true_when_hops_clipped(monkeypatch) -> None:
    """Bug #787 (counterpart): truncated=True when actual hops exceed max_hops."""

    class FakeFinder:
        def __init__(self, project_root, cache=None):
            pass

        def find_path(self, source_function, target_function, max_depth, max_paths):
            return _make_call_path_result(
                truncated=False,
                hops=[
                    {"caller": "a", "callee": "b"},
                    {"caller": "b", "callee": "c"},
                    {"caller": "c", "callee": "d"},
                ],
            )

    monkeypatch.setattr(uml_export, "CallPathFinder", FakeFinder)

    exporter = UMLExporter("/repo", cache=object())
    diagram = exporter.sequence_diagram(
        source="a",
        target="d",
        max_hops=2,  # 3 hops but max_hops=2 → clipped
    )

    # 3 hops, max_hops=2 → truncated must be True
    assert diagram.truncated is True


def test_sequence_truncated_false_when_no_paths(monkeypatch) -> None:
    """Bug #787 (empty path): no paths → truncated=False (nothing to clip)."""

    class FakeFinder:
        def __init__(self, project_root, cache=None):
            pass

        def find_path(self, source_function, target_function, max_depth, max_paths):
            return _make_call_path_result(truncated=True, hops=[])

    monkeypatch.setattr(uml_export, "CallPathFinder", FakeFinder)

    exporter = UMLExporter("/repo", cache=object())
    diagram = exporter.sequence_diagram(source="x", target="y")

    assert diagram.truncated is False


def test_sequence_truncated_true_when_path_search_clipped(monkeypatch) -> None:
    """Bug #959: path-count truncation must survive when hops are not clipped."""

    class FakeFinder:
        def __init__(self, project_root, cache=None):
            pass

        def find_path(self, source_function, target_function, max_depth, max_paths):
            assert max_paths == 1
            return _make_call_path_result(
                truncated=True,
                hops=[{"caller": "entry", "callee": "service"}],
            )

    monkeypatch.setattr(uml_export, "CallPathFinder", FakeFinder)

    exporter = UMLExporter("/repo", cache=object())
    diagram = exporter.sequence_diagram(
        source="entry",
        target="service",
        max_hops=12,
        max_paths=1,
    )

    assert diagram.truncated is True


# ── Bug #788 — activity empty Mermaid on None/empty body ──────────────────────


def test_activity_empty_body_returns_nonempty_mermaid(tmp_path) -> None:
    """Bug #788: empty_body error must NOT return a bare 'flowchart TD\\n'.

    The mermaid string must contain a visible indicator (node, note, or label)
    so consumers see a non-empty diagram string, not a degenerate header only.
    """
    import tree_sitter_analyzer.uml_activity as _uml_activity_mod

    src = tmp_path / "stub.py"
    src.write_text('def stub():\n    """Just a stub."""\n    pass\n')

    class FakeCFG:
        error = "empty_body"
        nodes: list = []
        edges: list = []
        truncated = False

    _original_build = _uml_activity_mod.build_activity_cfg

    try:
        _uml_activity_mod.build_activity_cfg = lambda fn, fp, mn: FakeCFG()  # type: ignore[attr-defined]
        exporter = UMLExporter(str(tmp_path), cache=object())
        diagram = exporter.activity_diagram(function_name="stub", file_path=str(src))
    finally:
        _uml_activity_mod.build_activity_cfg = _original_build  # type: ignore[attr-defined]

    # The mermaid must NOT be just a bare header — it must contain some content
    # beyond "flowchart TD\n" to be useful to consumers.
    assert diagram.mermaid != "flowchart TD\n", (
        "empty_body must not produce a bare 'flowchart TD\\n' — "
        f"got: {diagram.mermaid!r}"
    )
    # Pin the exact length so deterministic Mermaid drift fails loudly.
    assert len(diagram.mermaid) == 50, (
        f"mermaid is too short to be useful: {diagram.mermaid!r}"
    )


def test_activity_file_missing_returns_nonempty_mermaid(tmp_path) -> None:
    """Bug #788 companion: file_missing error mermaid must also be non-empty."""
    import tree_sitter_analyzer.uml_activity as _uml_activity_mod

    class FakeCFGMissing:
        error = "file_missing"
        nodes: list = []
        edges: list = []
        truncated = False

    _original_build = _uml_activity_mod.build_activity_cfg

    try:
        _uml_activity_mod.build_activity_cfg = lambda fn, fp, mn: FakeCFGMissing()  # type: ignore[attr-defined]
        exporter = UMLExporter(str(tmp_path), cache=object())
        diagram = exporter.activity_diagram(
            function_name="gone",
            file_path=str(tmp_path / "nonexistent.py"),
        )
    finally:
        _uml_activity_mod.build_activity_cfg = _original_build  # type: ignore[attr-defined]

    assert diagram.mermaid != "flowchart TD\n", (
        f"file_missing must produce non-degenerate mermaid, got {diagram.mermaid!r}"
    )


def test_activity_function_missing_returns_nonempty_mermaid(tmp_path) -> None:
    """Bug #788 companion: function_missing error mermaid must also be non-empty."""
    import tree_sitter_analyzer.uml_activity as _uml_activity_mod

    class FakeCFGFunctionMissing:
        error = "function_missing"
        nodes: list = []
        edges: list = []
        truncated = False

    _original_build = _uml_activity_mod.build_activity_cfg

    try:
        _uml_activity_mod.build_activity_cfg = lambda fn, fp, mn: (  # type: ignore[attr-defined]
            FakeCFGFunctionMissing()
        )
        exporter = UMLExporter(str(tmp_path), cache=object())
        src = tmp_path / "real.py"
        src.write_text("def other(): pass\n")
        diagram = exporter.activity_diagram(
            function_name="missing_fn",
            file_path=str(src),
        )
    finally:
        _uml_activity_mod.build_activity_cfg = _original_build  # type: ignore[attr-defined]

    assert diagram.mermaid != "flowchart TD\n", (
        f"function_missing must produce non-degenerate mermaid, got {diagram.mermaid!r}"
    )


# ── Bug #789 — include_tests displaces production classes ─────────────────────


def _make_hierarchy_factory(classes):
    """Return a FakeHierarchy class for the given class list."""

    class FakeHierarchy:
        def __init__(self, cache):
            pass

        def build(self):
            pass

        def all_classes(self):
            return classes

    return FakeHierarchy


def test_include_tests_production_classes_not_displaced(monkeypatch) -> None:
    """Bug #789: when include_tests=True and total edges > max_edges, production
    class edges must be prioritised over test class edges.

    Design: test edges that sort ALPHABETICALLY FIRST (low target names) would
    displace production edges in the current code (all weights=1, sorted by
    source/target ascending after -weight sort). With the fix, production edges
    are filled first.

    Setup:
    - Production: Zebra extends Base (edge Base→Zebra)
    - Test:       Aardvark extends Base (edge Base→Aardvark — sorts BEFORE Base→Zebra!)

    With max_edges=1 and the current buggy code, Base→Aardvark wins over
    Base→Zebra because "Aardvark" < "Zebra" alphabetically. After the fix,
    the production edge Base→Zebra must survive.
    """
    classes = [
        {"name": "Base", "parents": [], "file": "src/base.py"},
        # Production subclass: target name "Zebra" sorts AFTER test class
        {"name": "Zebra", "parents": ["Base"], "file": "src/zebra.py"},
        # Test subclass: target name "Aardvark" sorts BEFORE "Zebra"
        {
            "name": "Aardvark",
            "parents": ["Base"],
            "file": "tests/unit/test_aardvark.py",
        },
    ]
    monkeypatch.setattr(uml_export, "ClassHierarchy", _make_hierarchy_factory(classes))

    exporter = UMLExporter("/repo", cache=object())
    # max_edges=1: only one edge fits; production must win over test
    diagram = exporter.class_diagram(max_edges=1, include_tests=True)

    # The production edge Base→Zebra must be the one that survives
    pairs = {(e.source, e.target) for e in diagram.edges}
    assert ("Base", "Zebra") in pairs, (
        f"Production edge Base→Zebra was displaced by test edge. Got: {pairs}"
    )
    assert len(diagram.edges) == 1


def test_include_tests_production_first_when_all_fit(monkeypatch) -> None:
    """Bug #789 (no truncation): when all edges fit, nothing is displaced."""
    classes = [
        {"name": "A", "parents": [], "file": "src/a.py"},
        {"name": "B", "parents": ["A"], "file": "src/b.py"},
        {"name": "TestX", "parents": ["A"], "file": "tests/unit/test_x.py"},
    ]
    monkeypatch.setattr(uml_export, "ClassHierarchy", _make_hierarchy_factory(classes))

    exporter = UMLExporter("/repo", cache=object())
    # max_edges=10: all 2 edges fit, nothing displaced, no truncation
    diagram = exporter.class_diagram(max_edges=10, include_tests=True)

    # Both A→B (production) and A→TestX (test) must be present
    pairs = {(e.source, e.target) for e in diagram.edges}
    assert ("A", "B") in pairs, "Production edge A→B must be present"
    assert ("A", "TestX") in pairs, "Test edge A→TestX must also be present"
    assert diagram.truncated is False


def test_include_tests_deduplicates_identical_production_and_test_edges(
    monkeypatch,
) -> None:
    """Bug #959: prod/test allocation must not emit duplicate class edges."""
    classes = [
        {"name": "Base", "parents": [], "file": "src/base.py"},
        {"name": "Worker", "parents": ["Base"], "file": "src/worker.py"},
        {"name": "Worker", "parents": ["Base"], "file": "tests/unit/test_worker.py"},
    ]
    monkeypatch.setattr(uml_export, "ClassHierarchy", _make_hierarchy_factory(classes))

    exporter = UMLExporter("/repo", cache=object())
    diagram = exporter.class_diagram(max_edges=10, include_tests=True)

    edge_signatures = [
        (edge.source, edge.target, edge.label, edge.weight) for edge in diagram.edges
    ]
    assert edge_signatures == [("Base", "Worker", "inherits", 2)]


def test_include_tests_false_excludes_test_classes_unchanged(monkeypatch) -> None:
    """Bug #789 regression: include_tests=False still excludes test classes."""
    classes = [
        {"name": "A", "parents": [], "file": "src/a.py"},
        {"name": "TestX", "parents": ["A"], "file": "tests/unit/test_x.py"},
    ]
    monkeypatch.setattr(uml_export, "ClassHierarchy", _make_hierarchy_factory(classes))

    exporter = UMLExporter("/repo", cache=object())
    diagram = exporter.class_diagram(max_edges=10, include_tests=False)

    # TestX must not appear
    node_names = set(diagram.nodes)
    assert "TestX" not in node_names
    assert "A" in node_names
