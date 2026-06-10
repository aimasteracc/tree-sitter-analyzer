"""Tests for P2-A: diagram=activity control-flow diagram (RFC-0015).

RED-first: all tests were written before the implementation.
Run with: uv run pytest tests/unit/test_uml_activity.py -n 0 -q
"""

from __future__ import annotations

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


def test_activity_diagram_large_function_parse_count(tmp_path: Path) -> None:
    """~100-line function: parse count must be exactly 1 (rule-11 invariant).

    The old wall-clock bound (< 2000ms) was a hand-waved nondeterministic
    ceiling that CLAUDE.md rule-11 explicitly bans. The parse-count == 1 IS
    the deterministic invariant — a regression to multiple parses shows up
    here while timing cannot.
    """
    # Build a ~100-line function with 20 if-branches
    lines = ["def big_func(items):\n"]
    for i in range(20):
        lines.append(f"    if items[{i}]:\n")
        lines.append(f"        return {i}\n")
    lines.append("    return -1\n")
    src = tmp_path / "big.py"
    src.write_text("".join(lines))

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
        exporter.activity_diagram("big_func", file_path=str(src))

    assert (
        parse_call_count == 1
    )  # exact pin — rule-11 invariant; nondeterministic timing banned


# ---------------------------------------------------------------------------
# P1-1: exact label text assertions — no double prefix for return/raise
# ---------------------------------------------------------------------------


def test_return_label_exact_text(tmp_path: Path) -> None:
    """Return node label must be 'return x' NOT 'return return x'.

    tree-sitter return_statement text already contains the keyword;
    prepending it again produces a double prefix.
    """
    src = tmp_path / "mod.py"
    src.write_text("def f(x):\n    return x\n")
    from tree_sitter_analyzer.uml_activity import build_activity_cfg

    cfg = build_activity_cfg("f", str(src))
    return_nodes = [n for n in cfg.nodes if n.kind == "return"]
    assert len(return_nodes) == 1
    assert return_nodes[0].label == "return x"


def test_raise_label_exact_text(tmp_path: Path) -> None:
    """Raise node label must be 'raise ValueError…' NOT 'raise raise ValueError…'."""
    src = tmp_path / "mod.py"
    src.write_text("def f():\n    raise ValueError('err')\n")
    from tree_sitter_analyzer.uml_activity import build_activity_cfg

    cfg = build_activity_cfg("f", str(src))
    raise_nodes = [n for n in cfg.nodes if n.kind == "raise"]
    assert len(raise_nodes) == 1
    assert raise_nodes[0].label.startswith("raise ")
    assert not raise_nodes[0].label.startswith("raise raise ")


# ---------------------------------------------------------------------------
# P1-2: newline inside labels must not appear in rendered Mermaid
# ---------------------------------------------------------------------------


def test_escape_label_strips_newlines() -> None:
    """_escape_label must replace \\n and \\r with space (Mermaid ["..."] safety)."""
    from tree_sitter_analyzer.uml_export import _escape_label

    assert _escape_label("line1\nline2") == "line1 line2"
    assert _escape_label("line1\r\nline2") == "line1 line2"
    assert _escape_label("a\rb") == "a b"


def test_multiline_condition_no_newline_in_mermaid(tmp_path: Path) -> None:
    """Mermaid output must contain no raw newline inside a [\"...\"] label.

    A multiline condition string (e.g. from a lambda) must be flattened to a
    space-separated single line so that Mermaid parsers don't break.
    """
    from tree_sitter_analyzer.uml_export import _escape_label

    multiline = "x > 0\nand y > 0"
    escaped = _escape_label(multiline)
    # The rendered mermaid line would be: '  node["<escaped>"]'
    mermaid_line = f'  node["{escaped}"]'
    assert "\n" not in mermaid_line
    assert "\r" not in mermaid_line


# ---------------------------------------------------------------------------
# P2-1: metadata["note"] must always be present on successful diagrams
# ---------------------------------------------------------------------------


def test_activity_diagram_metadata_note_always_set(tmp_path: Path) -> None:
    """Successful activity diagram must carry metadata['note'] (RFC-0015 stale-file contract).

    activity ALWAYS re-parses from disk; the note is unconditional.
    """
    src = tmp_path / "mod.py"
    src.write_text("def f(x):\n    if x:\n        return 1\n    return 0\n")
    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.activity_diagram("f", file_path=str(src))
    assert "note" in diagram.metadata
    assert diagram.metadata["note"] == (
        "parsed from current file content; may differ from indexed symbols"
    )


# ---------------------------------------------------------------------------
# P2-2: try/except both-return — NO spurious exit edge
# ---------------------------------------------------------------------------


def test_try_except_both_return_no_exit_edge(tmp_path: Path) -> None:
    """When every try/except branch terminates (return/raise), NO exit node is added.

    The spurious try→exit edge must NOT appear when all branches terminate.
    """
    src = tmp_path / "mod.py"
    src.write_text(
        "def f():\n"
        "    try:\n"
        "        return 1\n"
        "    except Exception:\n"
        "        return 2\n"
    )
    from tree_sitter_analyzer.uml_activity import build_activity_cfg

    cfg = build_activity_cfg("f", str(src))

    # Exact node set: entry, try, return(try), except, return(except) — NO exit
    assert len(cfg.nodes) == 5
    kinds = [n.kind for n in cfg.nodes]
    assert kinds.count("exit") == 0

    # Exact edge set: entry→try, try→return, try→except, except→return
    assert len(cfg.edges) == 4
    edge_pairs = {(e.source_id, e.target_id) for e in cfg.edges}
    node_by_kind = {}
    for n in cfg.nodes:
        node_by_kind.setdefault(n.kind, []).append(n.node_id)
    entry_id = node_by_kind["entry"][0]
    try_id = node_by_kind["try"][0]
    except_id = node_by_kind["except"][0]
    assert (entry_id, try_id) in edge_pairs
    assert (try_id, except_id) in edge_pairs
    # No edge from try to exit
    assert all(e.target_id not in node_by_kind.get("exit", []) for e in cfg.edges)


# ---------------------------------------------------------------------------
# P2-3: nested function / qualified lookup
# ---------------------------------------------------------------------------


def test_find_function_bare_name_picks_outermost(tmp_path: Path) -> None:
    """DFS-preorder: bare name returns the outermost match (first encountered)."""
    src = tmp_path / "mod.py"
    src.write_text(
        "def outer(x):\n    def inner(y):\n        return y + 1\n    return inner(x)\n"
    )
    from tree_sitter_analyzer.uml_activity import build_activity_cfg

    cfg = build_activity_cfg("outer", str(src))
    # outer has one return statement: "return inner(x)"
    return_labels = [n.label for n in cfg.nodes if n.kind == "return"]
    assert len(return_labels) == 1
    assert return_labels[0] == "return inner(x)"


def test_find_function_qualified_name_picks_inner(tmp_path: Path) -> None:
    """Qualified 'outer.inner' lookup navigates into outer's scope to find inner."""
    src = tmp_path / "mod.py"
    src.write_text(
        "def outer(x):\n    def inner(y):\n        return y + 1\n    return inner(x)\n"
    )
    from tree_sitter_analyzer.uml_activity import build_activity_cfg

    cfg = build_activity_cfg("outer.inner", str(src))
    # inner has one return statement: "return y + 1"
    return_labels = [n.label for n in cfg.nodes if n.kind == "return"]
    assert len(return_labels) == 1
    assert return_labels[0] == "return y + 1"


# ---------------------------------------------------------------------------
# P3: True/False edge labels on if-condition branches
# ---------------------------------------------------------------------------


def test_if_true_false_edge_labels_with_else(tmp_path: Path) -> None:
    """Condition→true-body edge is labeled 'True'; condition→else-body is 'False'."""
    src = tmp_path / "mod.py"
    src.write_text(
        "def f(x):\n    if x > 0:\n        return 1\n    else:\n        return 0\n"
    )
    from tree_sitter_analyzer.uml_activity import build_activity_cfg

    cfg = build_activity_cfg("f", str(src))
    cond_nodes = [n for n in cfg.nodes if n.kind == "condition"]
    assert len(cond_nodes) == 1
    cond_id = cond_nodes[0].node_id
    edges_from_cond = [e for e in cfg.edges if e.source_id == cond_id]
    assert len(edges_from_cond) == 2
    labels = {e.label for e in edges_from_cond}
    assert labels == {"True", "False"}


def test_if_true_false_edge_labels_no_else(tmp_path: Path) -> None:
    """Condition→true-body is 'True'; condition falls through to next stmt as 'False'."""
    src = tmp_path / "mod.py"
    src.write_text("def f(x):\n    if x > 0:\n        return 1\n    return 0\n")
    from tree_sitter_analyzer.uml_activity import build_activity_cfg

    cfg = build_activity_cfg("f", str(src))
    cond_nodes = [n for n in cfg.nodes if n.kind == "condition"]
    assert len(cond_nodes) == 1
    cond_id = cond_nodes[0].node_id
    edges_from_cond = [e for e in cfg.edges if e.source_id == cond_id]
    # condition → return_1 (True), condition → return_0 (False)
    assert len(edges_from_cond) == 2
    labels = {e.label for e in edges_from_cond}
    assert labels == {"True", "False"}


# ---------------------------------------------------------------------------
# P3: for-loop label renders both sides of 'in'
# ---------------------------------------------------------------------------


def test_for_loop_label_includes_both_sides(tmp_path: Path) -> None:
    """For loop node label must be 'item in items', not just 'item'."""
    src = tmp_path / "mod.py"
    src.write_text(
        "def f(items):\n    for item in items:\n        pass\n    return None\n"
    )
    from tree_sitter_analyzer.uml_activity import build_activity_cfg

    cfg = build_activity_cfg("f", str(src))
    loop_nodes = [n for n in cfg.nodes if n.kind == "loop"]
    assert len(loop_nodes) == 1
    assert loop_nodes[0].label == "item in items"


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
