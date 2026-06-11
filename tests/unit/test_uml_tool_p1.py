"""Phase-1 tests for CodeGraphUMLTool — RFC-0015 P1-A/B/C/D (schema + validator + scoping).

Tests are written RED-first; implemented GREEN by the same commit.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.uml_tool import CodeGraphUMLTool

# ── P1-A: schema declares new params ──────────────────────────────────────────


def test_uml_schema_declares_file_path() -> None:
    tool = CodeGraphUMLTool()
    assert "file_path" in tool.get_tool_schema()["properties"]


def test_uml_schema_declares_class_name() -> None:
    tool = CodeGraphUMLTool()
    assert "class_name" in tool.get_tool_schema()["properties"]


def test_uml_schema_declares_include_tests() -> None:
    tool = CodeGraphUMLTool()
    props = tool.get_tool_schema()["properties"]
    assert "include_tests" in props
    assert props["include_tests"]["default"] is False


def test_uml_schema_not_required() -> None:
    """New params must NOT be in required (they are optional)."""
    tool = CodeGraphUMLTool()
    required = tool.get_tool_schema().get("required", [])
    for param in ("file_path", "class_name", "include_tests"):
        assert param not in required, f"{param} must not be in required"


# ── P1-B: float coercion and bool rejection via shared validator ───────────────


def test_max_edges_float_whole_number_coerced() -> None:
    tool = CodeGraphUMLTool()
    args: dict = {"diagram": "class", "max_edges": 30.0}
    tool.validate_arguments(args)
    assert args["max_edges"] == 30
    assert type(args["max_edges"]) is int


def test_max_edges_float_fractional_rejected() -> None:
    tool = CodeGraphUMLTool()
    with pytest.raises(ValueError, match="max_edges"):
        tool.validate_arguments({"diagram": "class", "max_edges": 30.5})


def test_max_edges_bool_true_rejected() -> None:
    tool = CodeGraphUMLTool()
    with pytest.raises(ValueError, match="max_edges"):
        tool.validate_arguments({"diagram": "class", "max_edges": True})


def test_max_edges_bool_false_rejected() -> None:
    tool = CodeGraphUMLTool()
    with pytest.raises(ValueError, match="max_edges"):
        tool.validate_arguments({"diagram": "class", "max_edges": False})


def test_max_depth_float_coerced() -> None:
    tool = CodeGraphUMLTool()
    args: dict = {"diagram": "sequence", "source": "a", "target": "b", "max_depth": 5.0}
    tool.validate_arguments(args)
    assert args["max_depth"] == 5
    assert type(args["max_depth"]) is int


# ── P1-C: test-corpus exclusion in sitemap tool ────────────────────────────────


def test_sitemap_tool_accepts_float_whole_number() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_sitemap_tool import (
        CodeGraphSitemapTool,
    )

    tool = CodeGraphSitemapTool()
    args: dict = {"mode": "full", "max_files": 50.0}
    tool.validate_arguments(args)
    assert args["max_files"] == 50
    assert type(args["max_files"]) is int


def test_sitemap_tool_rejects_bool_max_files() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_sitemap_tool import (
        CodeGraphSitemapTool,
    )

    tool = CodeGraphSitemapTool()
    with pytest.raises(ValueError, match="max_files"):
        tool.validate_arguments({"mode": "full", "max_files": True})


def test_sitemap_tool_rejects_bool_max_symbols() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_sitemap_tool import (
        CodeGraphSitemapTool,
    )

    tool = CodeGraphSitemapTool()
    with pytest.raises(ValueError, match="max_symbols"):
        tool.validate_arguments({"mode": "api", "max_symbols": False})


# ── P1-D diagram enum unchanged in Phase 1 ────────────────────────────────────


def test_uml_tool_schema_lists_diagrams_phase1() -> None:
    """Re-pinned in P2-B (RFC-0015): 'state' added; enum now has 5 elements.

    Old assertion (Phase 1 only, before state was added): 4 elements.
    This branch (feature/uml-state-diagram) adds 'state', so the pin is 5.
    Integration note: when the activity branch merges, update to 6 elements
    (["class", "package", "component", "sequence", "activity", "state"]).
    """
    tool = CodeGraphUMLTool()
    assert tool.get_tool_schema()["properties"]["diagram"]["enum"] == [
        "class",
        "package",
        "component",
        "sequence",
        "state",
    ]
