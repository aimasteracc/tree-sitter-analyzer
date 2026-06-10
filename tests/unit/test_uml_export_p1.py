"""Phase-1 export tests — RFC-0015 P1-A (scoping), P1-C (test exclusion),
P1-D (truncation note), P1-E (sequence observability label).

Tests are written RED-first; implemented GREEN by the same commit.
"""

from __future__ import annotations

from tree_sitter_analyzer import uml_export
from tree_sitter_analyzer.uml_export import (
    UMLEdge,
    UMLExporter,
    render_class_mermaid,
)

# ── helpers / fixtures ─────────────────────────────────────────────────────────


def _make_fake_hierarchy(classes):
    """Return a monkeypatch-able FakeHierarchy class for the given class list."""

    class FakeHierarchy:
        def __init__(self, cache: object) -> None:
            pass

        def build(self) -> None:
            pass

        def all_classes(self):
            return classes

    return FakeHierarchy


# ── P1-A: file_path scoping ────────────────────────────────────────────────────


def test_class_diagram_file_scoped_scope_field(monkeypatch) -> None:
    classes = [
        {"name": "InFile", "parents": [], "file": "src/a.py"},
        {"name": "Other", "parents": [], "file": "src/b.py"},
    ]
    monkeypatch.setattr(uml_export, "ClassHierarchy", _make_fake_hierarchy(classes))
    exporter = UMLExporter("/repo", cache=object())
    diagram = exporter.class_diagram(file_path="src/a.py")
    assert diagram.metadata["scope"] == "file"
    assert "InFile" in diagram.nodes
    assert "Other" not in diagram.nodes


def test_class_diagram_class_neighbourhood_scope_field(monkeypatch) -> None:
    classes = [
        {"name": "Base", "parents": [], "file": "src/x.py"},
        {"name": "MyClass", "parents": ["Base"], "file": "src/x.py"},
        {"name": "Child", "parents": ["MyClass"], "file": "src/x.py"},
        {"name": "Unrelated", "parents": [], "file": "src/x.py"},
    ]
    monkeypatch.setattr(uml_export, "ClassHierarchy", _make_fake_hierarchy(classes))
    exporter = UMLExporter("/repo", cache=object())
    diagram = exporter.class_diagram(class_name="MyClass")
    assert diagram.metadata["scope"] == "class_neighbourhood"
    assert "MyClass" in diagram.nodes
    # direct parent and direct child should be included
    assert "Base" in diagram.nodes
    assert "Child" in diagram.nodes
    # unrelated class must NOT appear
    assert "Unrelated" not in diagram.nodes


def test_class_diagram_whole_project_scope_label(monkeypatch) -> None:
    classes = [{"name": "A", "parents": [], "file": "src/a.py"}]
    monkeypatch.setattr(uml_export, "ClassHierarchy", _make_fake_hierarchy(classes))
    exporter = UMLExporter("/repo", cache=object())
    diagram = exporter.class_diagram()
    assert diagram.metadata["scope"] == "whole_project"


# ── P1-C: test-corpus exclusion ────────────────────────────────────────────────


def test_class_diagram_excludes_test_classes_by_default(monkeypatch) -> None:
    """include_tests=False (default) strips test-corpus classes."""
    classes = [
        {"name": "ProdA", "parents": [], "file": "src/a.py"},
        {"name": "ProdB", "parents": [], "file": "src/b.py"},
        {"name": "Cat", "parents": [], "file": "tests/fixtures/animals.py"},
        {"name": "Animal", "parents": [], "file": "tests/test_data/base.py"},
        {"name": "TestBase", "parents": [], "file": "tests/unit/test_stuff.py"},
    ]
    monkeypatch.setattr(uml_export, "ClassHierarchy", _make_fake_hierarchy(classes))
    exporter = UMLExporter("/repo", cache=object())
    diagram = exporter.class_diagram()
    test_nodes = [n for n in diagram.nodes if n in {"Cat", "Animal", "TestBase"}]
    # exact: zero test nodes should appear in the default (include_tests=False) view
    assert test_nodes == []


def test_class_diagram_include_tests_restores_all(monkeypatch) -> None:
    classes = [
        {"name": "ProdA", "parents": [], "file": "src/a.py"},
        {"name": "Cat", "parents": [], "file": "tests/fixtures/animals.py"},
        {"name": "Animal", "parents": [], "file": "tests/test_data/base.py"},
        {"name": "TestBase", "parents": [], "file": "tests/unit/test_stuff.py"},
    ]
    monkeypatch.setattr(uml_export, "ClassHierarchy", _make_fake_hierarchy(classes))
    exporter = UMLExporter("/repo", cache=object())
    diagram = exporter.class_diagram(include_tests=True)
    test_nodes = [n for n in diagram.nodes if n in {"Cat", "Animal", "TestBase"}]
    # exact pin — re-measure if fixture changes
    assert len(test_nodes) == 3


# ── P1-D: truncation note in mermaid output ────────────────────────────────────


def test_render_class_mermaid_truncated_has_note() -> None:
    mermaid = render_class_mermaid(
        ["A", "B"], [UMLEdge("A", "B", "inherits")], truncated=True
    )
    assert "%% NOTE: diagram truncated" in mermaid


def test_render_class_mermaid_not_truncated_no_note() -> None:
    mermaid = render_class_mermaid(
        ["A", "B"], [UMLEdge("A", "B", "inherits")], truncated=False
    )
    assert "%% NOTE: diagram truncated" not in mermaid


def test_class_diagram_mermaid_contains_truncation_note_when_capped(
    monkeypatch,
) -> None:
    """End-to-end: class_diagram with max_edges=1 on 2 edges → truncated=True → mermaid note."""
    classes = [
        {"name": "A", "parents": [], "file": "src/a.py"},
        {"name": "B", "parents": ["A"], "file": "src/b.py"},
        {"name": "C", "parents": ["A"], "file": "src/c.py"},
    ]
    monkeypatch.setattr(uml_export, "ClassHierarchy", _make_fake_hierarchy(classes))
    exporter = UMLExporter("/repo", cache=object())
    diagram = exporter.class_diagram(max_edges=1)
    assert diagram.truncated is True
    assert "%% NOTE: diagram truncated" in diagram.mermaid


# ── P1-E: sequence observability label ────────────────────────────────────────


def test_sequence_source_reflects_synapse(monkeypatch) -> None:
    """When a hop has callee_file, metadata.source = call_path+synapse_resolved."""

    class FakeResult:
        truncated = False

        def to_dict(self):
            return {
                "paths": [
                    {
                        "hops": [
                            {
                                "caller": "entry",
                                "callee": "service",
                                "callee_file": "src/service.py",
                            }
                        ]
                    }
                ]
            }

    class FakeFinder:
        def __init__(self, project_root, cache=None):
            pass

        def find_path(self, source_function, target_function, max_depth, max_paths):
            return FakeResult()

    monkeypatch.setattr(uml_export, "CallPathFinder", FakeFinder)
    exporter = UMLExporter("/repo", cache=object())
    diagram = exporter.sequence_diagram("entry", "service")
    assert diagram.metadata["source"] == "call_path+synapse_resolved"


def test_sequence_source_falls_back_without_synapse(monkeypatch) -> None:
    """When no hop has callee_file, metadata.source = call_path."""

    class FakeResult:
        truncated = False

        def to_dict(self):
            return {"paths": [{"hops": [{"caller": "entry", "callee": "service"}]}]}

    class FakeFinder:
        def __init__(self, project_root, cache=None):
            pass

        def find_path(self, source_function, target_function, max_depth, max_paths):
            return FakeResult()

    monkeypatch.setattr(uml_export, "CallPathFinder", FakeFinder)
    exporter = UMLExporter("/repo", cache=object())
    diagram = exporter.sequence_diagram("entry", "service")
    assert diagram.metadata["source"] == "call_path"
