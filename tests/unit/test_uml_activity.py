"""Tests for P2-A: diagram=activity control-flow diagram (RFC-0015).

RED-first: all tests were written before the implementation.
Run with: uv run pytest tests/unit/test_uml_activity.py -n 0 -q
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools.uml_tool import CodeGraphUMLTool

# ---------------------------------------------------------------------------
# Schema / enum tests
# ---------------------------------------------------------------------------


def test_uml_tool_schema_lists_diagrams_with_activity() -> None:
    """Enum must include 'activity' after Phase-2 landing (re-pinned)."""
    tool = CodeGraphUMLTool()
    enum = tool.get_tool_schema()["properties"]["diagram"]["enum"]
    assert enum == ["class", "package", "component", "sequence", "activity"]


def test_activity_in_diagram_enum() -> None:
    tool = CodeGraphUMLTool()
    assert "activity" in tool.get_tool_schema()["properties"]["diagram"]["enum"]


def test_function_name_declared_in_schema() -> None:
    tool = CodeGraphUMLTool()
    props = tool.get_tool_schema()["properties"]
    assert "function_name" in props
    assert props["function_name"]["type"] == "string"


def test_max_nodes_declared_in_schema() -> None:
    tool = CodeGraphUMLTool()
    props = tool.get_tool_schema()["properties"]
    assert "max_nodes" in props
    assert props["max_nodes"]["type"] == "integer"
    assert props["max_nodes"]["default"] == 50


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


def test_activity_diagram_requires_function_name() -> None:
    tool = CodeGraphUMLTool()
    with pytest.raises(ValueError, match="function_name is required"):
        tool.validate_arguments({"diagram": "activity"})


def test_activity_diagram_with_function_name_passes_validation() -> None:
    tool = CodeGraphUMLTool()
    # Should NOT raise
    tool.validate_arguments({"diagram": "activity", "function_name": "my_func"})


def test_activity_diagram_unknown_value_still_rejected() -> None:
    tool = CodeGraphUMLTool()
    with pytest.raises(ValueError, match="Unsupported UML diagram"):
        tool.validate_arguments({"diagram": "unknown_type"})


# ---------------------------------------------------------------------------
# UMLExporter.activity_diagram — via real tree-sitter parse
# ---------------------------------------------------------------------------


def test_activity_diagram_mermaid_type_and_comment(tmp_path: Path) -> None:
    """activity_diagram returns flowchart TD with the RFC comment header."""
    src = tmp_path / "mod.py"
    src.write_text("def my_func(x):\n    if x > 0:\n        return x\n    return 0\n")
    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.activity_diagram("my_func", file_path=str(src))

    assert diagram.mermaid.startswith("flowchart TD")
    assert (
        "%% NOTE: activity diagram is a structural AST approximation" in diagram.mermaid
    )
    assert diagram.metadata["diagram_type"] == "activity"


def test_activity_diagram_metadata_analysis_kind(tmp_path: Path) -> None:
    src = tmp_path / "mod.py"
    src.write_text("def my_func(x):\n    if x:\n        return 1\n    return 0\n")
    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.activity_diagram("my_func", file_path=str(src))
    assert diagram.metadata.get("analysis_kind") == "structural_approximation"


def test_activity_diagram_node_count_simple_if(tmp_path: Path) -> None:
    """Simple if/else function: entry + condition + two return branches = 4 nodes."""
    src = tmp_path / "mod.py"
    src.write_text(
        "def simple_func(x):\n    if x > 0:\n        return x\n    return 0\n"
    )
    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.activity_diagram("simple_func", file_path=str(src))
    # entry + if-condition + return(true branch) + return(false branch) = 4
    assert len(diagram.nodes) == 4


def test_activity_diagram_for_loop(tmp_path: Path) -> None:
    """For loop: entry + loop-header + return = 3 nodes."""
    src = tmp_path / "mod.py"
    src.write_text(
        "def loop_func(items):\n    for item in items:\n        pass\n    return None\n"
    )
    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.activity_diagram("loop_func", file_path=str(src))
    # entry + for-loop + return = 3
    assert len(diagram.nodes) == 3


def test_activity_diagram_while_loop(tmp_path: Path) -> None:
    """While loop: entry + while-condition + return = 3 nodes."""
    src = tmp_path / "mod.py"
    src.write_text(
        "def while_func(n):\n    while n > 0:\n        n -= 1\n    return n\n"
    )
    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.activity_diagram("while_func", file_path=str(src))
    # entry + while + return = 3
    assert len(diagram.nodes) == 3


def test_activity_diagram_try_except(tmp_path: Path) -> None:
    """Try/except: entry + try + except + exit = 4 nodes.

    The implicit exit node is added because neither the try nor the except
    branch terminates with return/raise — execution falls through to exit.
    """
    src = tmp_path / "mod.py"
    src.write_text(
        "def try_func():\n    try:\n        pass\n    except Exception:\n        pass\n"
    )
    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.activity_diagram("try_func", file_path=str(src))
    # entry + try + except + exit = 4 (exit added: no branch terminates)
    assert len(diagram.nodes) == 4


def test_activity_diagram_raise_statement(tmp_path: Path) -> None:
    """Raise: entry + raise = 2 nodes."""
    src = tmp_path / "mod.py"
    src.write_text("def raise_func():\n    raise ValueError('err')\n")
    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.activity_diagram("raise_func", file_path=str(src))
    # entry + raise = 2
    assert len(diagram.nodes) == 2


def test_activity_diagram_empty_function_returns_not_found(tmp_path: Path) -> None:
    """Empty (stub) function: zero CFG nodes -> NOT_FOUND with next_step."""
    src = tmp_path / "mod.py"
    src.write_text("def empty_func():\n    pass\n")
    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    result = exporter.activity_diagram("empty_func", file_path=str(src))
    assert result.metadata.get("verdict") == "NOT_FOUND"
    assert "next_step" in result.metadata


def test_activity_diagram_missing_file_returns_not_found(tmp_path: Path) -> None:
    """When the file no longer exists, return NOT_FOUND."""
    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    result = exporter.activity_diagram(
        "my_func", file_path=str(tmp_path / "nonexistent.py")
    )
    assert result.metadata.get("verdict") == "NOT_FOUND"
    assert "next_step" in result.metadata


def test_activity_diagram_function_not_found_in_file_returns_not_found(
    tmp_path: Path,
) -> None:
    """When the function name doesn't exist in the file, return NOT_FOUND."""
    src = tmp_path / "mod.py"
    src.write_text("def other_func():\n    pass\n")

    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    result = exporter.activity_diagram("missing_func", file_path=str(src))
    assert result.metadata.get("verdict") == "NOT_FOUND"


def test_activity_diagram_max_nodes_cap(tmp_path: Path) -> None:
    """max_nodes=2 truncates: only 2 nodes emitted + truncated flag set."""
    src = tmp_path / "mod.py"
    src.write_text("def big_func(x):\n    if x > 0:\n        return x\n    return 0\n")
    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.activity_diagram("big_func", file_path=str(src), max_nodes=2)
    assert len(diagram.nodes) == 2
    assert diagram.truncated is True
    assert "%% NOTE: diagram truncated" in diagram.mermaid


# ---------------------------------------------------------------------------
# Rule-11 latency invariant: single parse per call
# ---------------------------------------------------------------------------


def test_activity_diagram_parse_count_exactly_one(tmp_path: Path) -> None:
    """Activity diagram triggers exactly ONE tree-sitter parse, not more.

    Rule-11 invariant: re-parsing regressions are caught here.
    parse_count must be exactly 1.
    """
    src = tmp_path / "mod.py"
    src.write_text(
        "def my_func(x):\n"
        "    if x > 0:\n"
        "        return x\n"
        "    for i in range(10):\n"
        "        pass\n"
        "    return 0\n"
    )

    import tree_sitter_analyzer.uml_activity as _activity_module

    parse_call_count = 0
    original_parse = _activity_module._parse_file_for_activity

    def counting_parse(file_path: str, language: str = "python"):
        nonlocal parse_call_count
        parse_call_count += 1
        return original_parse(file_path, language)

    from tree_sitter_analyzer.uml_export import UMLExporter

    with patch.object(_activity_module, "_parse_file_for_activity", counting_parse):
        exporter = UMLExporter(str(tmp_path))
        exporter.activity_diagram("my_func", file_path=str(src))

    assert parse_call_count == 1  # exact pin — rule-11 invariant


def test_activity_diagram_wall_clock_bound(tmp_path: Path) -> None:
    """Activity diagram on a ~100-line function must complete in < 2000ms.

    Rule-11 latency invariant: one file read + one tree-sitter parse.
    2000ms is conservative — typical is < 50ms.
    """
    # Build a ~100-line function with 20 if-branches
    lines = ["def big_func(items):\n"]
    for i in range(20):
        lines.append(f"    if items[{i}]:\n")
        lines.append(f"        return {i}\n")
    lines.append("    return -1\n")
    src = tmp_path / "big.py"
    src.write_text("".join(lines))

    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    t0 = time.monotonic()
    exporter.activity_diagram("big_func", file_path=str(src))
    elapsed_ms = (time.monotonic() - t0) * 1000
    # documented wall-clock bound; nondeterministic timing = documented invariant
    assert elapsed_ms < 2000


# ---------------------------------------------------------------------------
# CLI flag tests
# ---------------------------------------------------------------------------


def test_phase2_cli_flags_registered() -> None:
    """--uml-function and --uml-max-nodes must be registered in the CLI parser."""
    from tree_sitter_analyzer.cli_main import create_argument_parser

    parser = create_argument_parser()
    long_flags = {a.option_strings[-1] for a in parser._actions if a.option_strings}
    for flag in ("--uml-function", "--uml-max-nodes"):
        assert flag in long_flags, f"Phase-2 CLI flag missing: {flag}"


def test_uml_enum_includes_activity_in_cli() -> None:
    """--uml choices must include 'activity'."""
    from tree_sitter_analyzer.cli_main import create_argument_parser

    parser = create_argument_parser()
    uml_action = next(a for a in parser._actions if "--uml" in (a.option_strings or []))
    assert "activity" in uml_action.choices


def test_build_uml_tool_args_passes_function_name() -> None:
    """_build_uml_tool_args must forward function_name when set."""
    from tree_sitter_analyzer.cli.commands.mcp_commands._builders import (
        _build_uml_tool_args,
    )

    class FakeArgs:
        uml = "activity"
        uml_source = None
        uml_target = None
        uml_max_edges = 80
        uml_max_depth = 8
        uml_max_paths = 3
        uml_package_depth = 2
        uml_no_external_bases = False
        uml_file_path = None
        uml_class_name = None
        uml_include_tests = False
        uml_function = "my_func"
        uml_max_nodes = 50

    result = _build_uml_tool_args(FakeArgs(), "json")
    assert result["function_name"] == "my_func"
    assert result["max_nodes"] == 50
    assert result["diagram"] == "activity"


def test_build_uml_tool_args_omits_function_name_when_none() -> None:
    """_build_uml_tool_args must NOT include function_name key when not provided."""
    from tree_sitter_analyzer.cli.commands.mcp_commands._builders import (
        _build_uml_tool_args,
    )

    class FakeArgs:
        uml = "class"
        uml_source = None
        uml_target = None
        uml_max_edges = 80
        uml_max_depth = 8
        uml_max_paths = 3
        uml_package_depth = 2
        uml_no_external_bases = False
        uml_file_path = None
        uml_class_name = None
        uml_include_tests = False
        uml_function = None
        uml_max_nodes = 50

    result = _build_uml_tool_args(FakeArgs(), "json")
    assert "function_name" not in result


# ---------------------------------------------------------------------------
# execute() boundary test (real MCP tool path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activity_diagram_via_execute(tmp_path: Path) -> None:
    """activity diagram via the real execute() boundary (MCP tool path)."""
    src = tmp_path / "mod.py"
    src.write_text("def my_func(x):\n    if x > 0:\n        return x\n    return 0\n")

    tool = CodeGraphUMLTool(str(tmp_path))
    result = await tool.execute(
        {
            "diagram": "activity",
            "function_name": "my_func",
            "file_path": str(src),
            "output_format": "json",
        }
    )
    assert result["success"] is True
    assert result["diagram_type"] == "activity"
    assert "flowchart TD" in result["mermaid"]


@pytest.mark.asyncio
async def test_activity_diagram_missing_function_name_error(tmp_path: Path) -> None:
    """activity without function_name returns error response via execute()."""
    tool = CodeGraphUMLTool(str(tmp_path))
    try:
        await tool.execute({"diagram": "activity", "output_format": "json"})
        raise AssertionError("Expected ValueError")
    except ValueError as e:
        assert "function_name is required" in str(e)
