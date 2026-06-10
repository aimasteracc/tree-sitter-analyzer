"""Tests for UML Mermaid export helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tree_sitter_analyzer import uml_export
from tree_sitter_analyzer.uml_export import (
    UMLEdge,
    UMLExporter,
    _clamp_edges,
    _component_name,
    _package_name,
    render_class_mermaid,
    render_flowchart_mermaid,
    render_sequence_mermaid,
)


def test_render_class_mermaid_uses_inheritance_arrows() -> None:
    mermaid = render_class_mermaid(
        ["BaseTool", "QueryTool"],
        [UMLEdge("BaseTool", "QueryTool", "inherits")],
    )

    assert mermaid.startswith("classDiagram")
    assert "class BaseTool" in mermaid
    assert "BaseTool <|-- QueryTool" in mermaid


def test_render_flowchart_mermaid_labels_weighted_edges() -> None:
    mermaid = render_flowchart_mermaid(
        ["cli", "mcp"],
        [UMLEdge("cli", "mcp", "3", 3)],
    )

    assert mermaid.startswith("flowchart LR")
    assert 'cli["cli"]' in mermaid
    assert "cli -->|3| mcp" in mermaid


def test_render_flowchart_mermaid_supports_unlabeled_edges() -> None:
    mermaid = render_flowchart_mermaid(["cli", "core"], [UMLEdge("cli", "core")])

    assert "cli --> core" in mermaid


def test_render_sequence_mermaid_uses_first_call_path() -> None:
    mermaid = render_sequence_mermaid(
        [
            {
                "hops": [
                    {"caller": "handler", "callee": "service"},
                    {"caller": "service", "callee": "repository"},
                ]
            }
        ],
        max_hops=10,
    )

    assert mermaid.startswith("sequenceDiagram")
    assert 'participant handler as "handler"' in mermaid
    assert "handler->>+service: call" in mermaid
    assert "service->>+repository: call" in mermaid


def test_render_sequence_mermaid_empty_path_is_explicit() -> None:
    mermaid = render_sequence_mermaid([], max_hops=10)

    assert "No call path found" in mermaid


def test_render_sequence_mermaid_empty_hops_are_explicit() -> None:
    mermaid = render_sequence_mermaid([{"hops": [{}]}], max_hops=10)

    assert mermaid == "sequenceDiagram\n  participant EmptyPath"


def test_render_sequence_mermaid_skips_incomplete_hops() -> None:
    mermaid = render_sequence_mermaid(
        [{"hops": [{"caller": "entry", "callee": ""}]}],
        max_hops=10,
    )

    assert 'participant entry as "entry"' in mermaid
    assert "entry->>" not in mermaid


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("", "root"),
        ("main.py", "root"),
        ("tree_sitter_analyzer/cli/main.py", "tree_sitter_analyzer.cli"),
        ("src/pkg/module.py", "src.pkg"),
    ],
)
def test_package_name_groups_file_paths(path: str, expected: str) -> None:
    assert _package_name(path, max_depth=2) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("", "root"),
        ("main.py", "root"),
        ("tree_sitter_analyzer/api.py", "tree_sitter_analyzer.root"),
        ("tree_sitter_analyzer/mcp/tools/uml_tool.py", "mcp"),
        ("tests/unit/test_uml_export.py", "tests"),
    ],
)
def test_component_name_groups_project_components(path: str, expected: str) -> None:
    assert _component_name(path) == expected


def test_clamp_edges_merges_duplicates_and_reports_truncation() -> None:
    edges, truncated = _clamp_edges(
        [
            UMLEdge("cli", "mcp", "uses", 1),
            UMLEdge("cli", "mcp", "uses", 2),
            UMLEdge("api", "core", "uses", 1),
        ],
        max_edges=1,
    )

    assert truncated is True
    assert edges == [UMLEdge("cli", "mcp", "uses", 3)]


def test_class_diagram_uses_internal_and_common_external_bases(monkeypatch) -> None:
    class FakeHierarchy:
        def __init__(self, cache: object) -> None:
            self.cache = cache

        def build(self) -> None:
            pass

        def all_classes(self) -> list[dict[str, object]]:
            return [
                {"name": "Base", "parents": []},
                {"name": "Child", "parents": ["pkg.Base", "ABC"]},
            ]

    monkeypatch.setattr(uml_export, "ClassHierarchy", FakeHierarchy)

    diagram = UMLExporter("/repo", cache=object()).class_diagram(max_edges=10)

    assert diagram.diagram_type == "class"
    # scope field added by RFC-0015 P1-A; re-pinned from {"source": "class_hierarchy"}
    assert diagram.metadata == {"source": "class_hierarchy", "scope": "whole_project"}
    assert UMLEdge("Base", "Child", "inherits") in diagram.edges
    assert UMLEdge("ABC", "Child", "inherits") in diagram.edges
    assert "Base <|-- Child" in diagram.mermaid


def test_class_diagram_closes_owned_cache_and_falls_back_to_nodes(monkeypatch) -> None:
    closed: list[bool] = []

    class FakeCache:
        def __init__(self, project_root: str) -> None:
            assert project_root == "/repo"

        def close(self) -> None:
            closed.append(True)

    class FakeHierarchy:
        def __init__(self, cache: object) -> None:
            self.cache = cache

        def build(self) -> None:
            pass

        def all_classes(self) -> list[dict[str, object]]:
            return [
                {},
                {"name": "Lonely", "parents": ["NotIncluded"]},
            ]

    monkeypatch.setattr(uml_export, "ClassHierarchy", FakeHierarchy)
    monkeypatch.setattr("tree_sitter_analyzer.ast_cache.ASTCache", FakeCache)

    diagram = UMLExporter("/repo").class_diagram(
        max_edges=10, include_external_bases=False
    )

    assert closed == [True]
    assert diagram.nodes == ["Lonely"]
    assert diagram.edges == []
    assert diagram.mermaid == "classDiagram\n  class Lonely"


def test_package_diagram_aggregates_import_edges(monkeypatch) -> None:
    class FakeImportGraph:
        def __init__(self, project_root: str) -> None:
            assert project_root == "/repo"

        def build(self) -> SimpleNamespace:
            return SimpleNamespace(
                edges=[
                    SimpleNamespace(
                        source_file="pkg/a.py",
                        target_file="pkg/b.py",
                    ),
                    SimpleNamespace(
                        source_file="pkg/a.py",
                        target_file="other/c.py",
                    ),
                    SimpleNamespace(
                        source_file="pkg/d.py",
                        target_file="other/c.py",
                    ),
                ]
            )

    monkeypatch.setattr(uml_export, "ImportGraph", FakeImportGraph)

    diagram = UMLExporter("/repo").package_diagram(max_edges=10, package_depth=1)

    assert diagram.diagram_type == "package"
    assert diagram.metadata == {"source": "import_graph", "package_depth": 1}
    assert diagram.edges == [UMLEdge("pkg", "other", "2", 2)]
    assert "pkg -->|2| other" in diagram.mermaid


def test_component_diagram_aggregates_top_level_components(monkeypatch) -> None:
    class FakeImportGraph:
        def __init__(self, project_root: str) -> None:
            assert project_root == "/repo"

        def build(self) -> SimpleNamespace:
            return SimpleNamespace(
                edges=[
                    SimpleNamespace(
                        source_file="tree_sitter_analyzer/cli/main.py",
                        target_file="tree_sitter_analyzer/mcp/tools/uml_tool.py",
                    ),
                    SimpleNamespace(
                        source_file="tree_sitter_analyzer/api.py",
                        target_file="tree_sitter_analyzer/api.py",
                    ),
                ]
            )

    monkeypatch.setattr(uml_export, "ImportGraph", FakeImportGraph)

    diagram = UMLExporter("/repo").component_diagram(max_edges=10)

    assert diagram.diagram_type == "component"
    assert diagram.metadata == {
        "source": "import_graph",
        "group_by": "top_level_component",
    }
    assert diagram.edges == [UMLEdge("cli", "mcp", "1", 1)]
    assert "cli -->|1| mcp" in diagram.mermaid


def test_sequence_diagram_uses_call_path_and_marks_static_approximation(
    monkeypatch,
) -> None:
    class FakeCallPathResult:
        truncated = False

        def to_dict(self) -> dict[str, object]:
            return {
                "paths": [
                    {
                        "hops": [
                            {"caller": "entry", "callee": "service"},
                            {"caller": "service", "callee": "repository"},
                        ]
                    }
                ]
            }

    class FakeCallPathFinder:
        def __init__(self, project_root: str, cache: object | None = None) -> None:
            assert project_root == "/repo"
            assert cache == "cache"

        def find_path(
            self,
            source_function: str,
            target_function: str,
            max_depth: int,
            max_paths: int,
        ) -> FakeCallPathResult:
            assert (source_function, target_function) == ("entry", "repository")
            assert (max_depth, max_paths) == (5, 2)
            return FakeCallPathResult()

    monkeypatch.setattr(uml_export, "CallPathFinder", FakeCallPathFinder)

    diagram = UMLExporter("/repo", cache="cache").sequence_diagram(
        source="entry",
        target="repository",
        max_depth=5,
        max_paths=2,
        max_hops=1,
    )

    assert diagram.diagram_type == "sequence"
    assert diagram.metadata == {
        "source": "call_path",
        "analysis_kind": "static_approximation",
        "path_count": 1,
    }
    assert diagram.truncated is True
    assert diagram.nodes == ["entry", "service"]
    assert diagram.edges == [UMLEdge("entry", "service", "call")]
