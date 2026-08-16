"""NO1-010A / RFC-0022 Phase A: task surface stays internal-only.

The three-task prototype (understand / plan_change / assess_change) must
stay an internal experiment: no MCP facade registration, no CLI flags, no
codemap surface (RFC-0022 §Public surface: Phase A — internal experiment
only). This contract fails if any future change registers it without the
pre-registration menu gate.
"""

from __future__ import annotations


def test_no_task_facade_is_registered() -> None:
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    tools, _ = create_tool_registry(".")
    facade_names = {name for name, _ in tools}
    assert "task" not in facade_names
    assert facade_names == {
        "search",
        "nav",
        "structure",
        "health",
        "edit",
        "project",
        "index",
        "viz",
    }


def test_no_task_actions_hide_inside_existing_facades() -> None:
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(None)
    actions = set(facade.action_map) | set(facade.bespoke_map)
    assert not {"understand", "plan_change", "assess_change"} & actions


def test_cli_parser_has_no_task_flags() -> None:
    from tree_sitter_analyzer.cli_main import create_argument_parser

    parser = create_argument_parser()
    flags = {option for action in parser._actions for option in action.option_strings}
    assert not {"--understand", "--plan-change", "--assess-change"} & flags
    assert not any("task-outcome" in flag for flag in flags)


def test_task_package_declares_internal_only_status() -> None:
    import pathlib

    package_init = (
        pathlib.Path(__file__).parent.parent.parent
        / "tree_sitter_analyzer"
        / "task"
        / "__init__.py"
    )
    docstring = package_init.read_text(encoding="utf-8").split('"""')[1]
    assert "internal experiment only" in docstring
    assert (
        "Not registered as an MCP facade, CLI command, or codemap surface" in docstring
    )


def test_task_package_never_imports_analyzer_internals() -> None:
    """The task layer boundary (RFC-0022 §Non-negotiable boundary).

    ``tree_sitter_analyzer/task/`` MUST NOT import analyzer internals — no
    parser, diff reader, cache, graph, constraint engine, or command runner.
    """
    import pathlib

    package_dir = (
        pathlib.Path(__file__).parent.parent.parent / "tree_sitter_analyzer" / "task"
    )
    forbidden = (
        "ast_cache",
        "mcp",
        "cli",
        "constraints",
        "semantic_change_classifier",
        "call_graph",
        "dependency",
        "subprocess",
        "shutil",
        "sqlite3",
    )
    for module in package_dir.glob("*.py"):
        for line in module.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if stripped.startswith(("from .", "import .")):
                continue
            lowered = stripped.lower()
            assert not any(term in lowered for term in forbidden), (
                f"{module.name} violates the task boundary: {stripped}"
            )


def test_harness_is_the_only_internal_bridge() -> None:
    """Only the experiment harness may import both task and MCP adapters."""
    import pathlib

    harness = (
        pathlib.Path(__file__).parent.parent.parent
        / "tree_sitter_analyzer"
        / "task_harness.py"
    )
    assert harness.exists()
    text = harness.read_text(encoding="utf-8")
    assert "from .task" in text
    assert ".mcp.tools" in text
