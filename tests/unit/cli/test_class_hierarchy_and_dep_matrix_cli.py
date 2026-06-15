"""Tests for class-hierarchy and dependency-matrix CLI parity."""

from __future__ import annotations

from argparse import Namespace
from typing import Any

from tree_sitter_analyzer.cli.commands import mcp_commands


def _args(**overrides: Any) -> Namespace:
    defaults: dict[str, Any] = {
        "file_path": "target.py",
        "project_root": "/repo",
        "class_hierarchy": False,
        "class_hierarchy_mode": "summary",
        "class_hierarchy_class": None,
        "class_hierarchy_depth": 10,
        "dependency_matrix": False,
        "dependency_matrix_mode": "summary",
        "dependency_matrix_file": None,
        "dependency_matrix_top_k": 10,
        "dependency_matrix_threshold": 0.7,
    }
    for flag in (
        "file_health",
        "project_health",
        "overview",
        "safe_to_edit",
        "change_impact",
        "refactor",
        "smart_context",
        "parser_readiness",
        "ast_cache",
        "call_graph",
        "callers",
        "callees",
        "ast_diff",
        "ast_path",
        "detect_routes",
        "codegraph_overview",
        "codegraph_navigate",
        "codegraph_impact",
        "codegraph_sitemap",
        "codegraph_xref",
        "code_similarity",
        "dead_code",
        "import_graph",
        "semantic_classify",
        "pr_review",
        "symbol_resolve",
        "symbol_search",
        "codegraph_complexity_heatmap",
        "symbol_lineage",
        "code_patterns",
    ):
        defaults[flag] = False
    defaults["dependencies"] = None
    defaults["symbol_search"] = False
    defaults["symbol_resolve"] = False
    defaults["symbol_resolve_mode"] = "resolve"
    defaults["callers"] = False
    defaults["callees"] = False
    defaults.update(overrides)
    return Namespace(**defaults)


def test_class_hierarchy_summary_cli(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeClassHierarchyTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "toon_content": "hierarchy summary"}

    monkeypatch.setattr(mcp_commands, "ClassHierarchyTool", FakeClassHierarchyTool)

    result = mcp_commands.handle_mcp_commands(
        _args(class_hierarchy=True),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "mode": "summary",
            "class_name": None,
            "max_depth": 10,
            "output_format": "json",
        },
    }


def test_class_hierarchy_subclasses_cli(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeClassHierarchyTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "toon_content": "subclasses"}

    monkeypatch.setattr(mcp_commands, "ClassHierarchyTool", FakeClassHierarchyTool)

    result = mcp_commands.handle_mcp_commands(
        _args(
            class_hierarchy=True,
            class_hierarchy_mode="subclasses",
            class_hierarchy_class="BaseWidget",
            class_hierarchy_depth=5,
        ),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "mode": "subclasses",
            "class_name": "BaseWidget",
            "max_depth": 5,
            "output_format": "json",
        },
    }


def test_class_hierarchy_impact_cli(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeClassHierarchyTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "toon_content": "impact"}

    monkeypatch.setattr(mcp_commands, "ClassHierarchyTool", FakeClassHierarchyTool)

    result = mcp_commands.handle_mcp_commands(
        _args(
            class_hierarchy=True,
            class_hierarchy_mode="impact",
            class_hierarchy_class="BaseHandler",
        ),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen["arguments"]["mode"] == "impact"
    assert seen["arguments"]["class_name"] == "BaseHandler"


def test_dependency_matrix_summary_cli(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeDependencyMatrixTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "toon_content": "coupling summary"}

    monkeypatch.setattr(
        mcp_commands, "CodeGraphDependencyMatrixTool", FakeDependencyMatrixTool
    )

    result = mcp_commands.handle_mcp_commands(
        _args(dependency_matrix=True),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "mode": "summary",
            "file_path": None,
            "top_k": 10,
            "threshold": 0.7,
            "output_format": "json",
        },
    }


def test_dependency_matrix_hotspots_cli(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeDependencyMatrixTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "toon_content": "hotspots"}

    monkeypatch.setattr(
        mcp_commands, "CodeGraphDependencyMatrixTool", FakeDependencyMatrixTool
    )

    result = mcp_commands.handle_mcp_commands(
        _args(
            dependency_matrix=True,
            dependency_matrix_mode="hotspots",
            dependency_matrix_top_k=5,
        ),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen["arguments"]["mode"] == "hotspots"
    assert seen["arguments"]["top_k"] == 5


def test_dependency_matrix_unstable_cli(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeDependencyMatrixTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "toon_content": "unstable"}

    monkeypatch.setattr(
        mcp_commands, "CodeGraphDependencyMatrixTool", FakeDependencyMatrixTool
    )

    result = mcp_commands.handle_mcp_commands(
        _args(
            dependency_matrix=True,
            dependency_matrix_mode="unstable",
            dependency_matrix_threshold=0.8,
        ),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen["arguments"]["mode"] == "unstable"
    assert seen["arguments"]["threshold"] == 0.8


def test_symbol_lineage_empty_string_returns_error_not_usage_dump() -> None:
    """#863: --symbol-lineage "" must emit a clean validation error, not a usage dump."""
    errors: list[str] = []
    result = mcp_commands.handle_mcp_commands(
        _args(symbol_lineage=""),
        lambda payload: None,
        errors.append,
        lambda: "json",
    )
    assert result == 1
    assert len(errors) == 1
    assert "symbol" in errors[0].lower() or "empty" in errors[0].lower()


def test_symbol_lineage_whitespace_only_returns_error() -> None:
    """#863: --symbol-lineage '   ' is treated the same as empty."""
    errors: list[str] = []
    result = mcp_commands.handle_mcp_commands(
        _args(symbol_lineage="   "),
        lambda payload: None,
        errors.append,
        lambda: "json",
    )
    assert result == 1
    assert len(errors) == 1


def test_dependency_matrix_file_cli(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeDependencyMatrixTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "toon_content": "file coupling"}

    monkeypatch.setattr(
        mcp_commands, "CodeGraphDependencyMatrixTool", FakeDependencyMatrixTool
    )

    result = mcp_commands.handle_mcp_commands(
        _args(
            dependency_matrix=True,
            dependency_matrix_mode="file",
            dependency_matrix_file="src/parser.py",
        ),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen["arguments"]["mode"] == "file"
    assert seen["arguments"]["file_path"] == "src/parser.py"


def test_symbol_search_empty_string_returns_error_not_file_path_fallback() -> None:
    """#738: --symbol-search "" must emit a clean validation error, not 'File path not specified'."""
    errors: list[str] = []
    result = mcp_commands.handle_mcp_commands(
        _args(symbol_search=""),
        lambda payload: None,
        errors.append,
        lambda: "json",
    )
    assert result == 1
    assert len(errors) == 1
    assert "symbol" in errors[0].lower() or "query" in errors[0].lower()
    assert "file" not in errors[0].lower()


def test_symbol_search_whitespace_only_returns_error() -> None:
    """#738: --symbol-search '   ' is treated the same as empty."""
    errors: list[str] = []
    result = mcp_commands.handle_mcp_commands(
        _args(symbol_search="   "),
        lambda payload: None,
        errors.append,
        lambda: "json",
    )
    assert result == 1
    assert len(errors) == 1
