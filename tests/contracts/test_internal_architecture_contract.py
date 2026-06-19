"""Contract tests split from the former agent workflow monolith."""
# ruff: noqa: F401

from __future__ import annotations

import ast
import configparser
import os
import re
from pathlib import Path

import pytest

try:
    import tomllib  # Python 3.11+ stdlib
except ImportError:  # Python 3.10 — fall back to the tomli back-port
    import tomli as tomllib
from hypothesis import settings as hypothesis_settings

from tree_sitter_analyzer.cli_main import create_argument_parser
from tree_sitter_analyzer.mcp.server import _create_tool_registry

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKIPPED_SCAN_DIRS = {
    ".git",
    ".benchmark-repos",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
}

def test_package_and_mcp_versions_are_aligned() -> None:
    """Release prep must keep package and MCP server versions in lockstep."""
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_version = data["project"]["version"]
    package_init = (PROJECT_ROOT / "tree_sitter_analyzer" / "__init__.py").read_text(
        encoding="utf-8"
    )

    assert data["tool"]["mcp"]["server_version"] == project_version
    assert f'__version__ = "{project_version}"' in package_init


def test_ast_cache_call_edge_extraction_does_not_depend_on_call_graph() -> None:
    """ASTCache and CallGraph must share extraction helpers without a back-edge."""
    path = PROJECT_ROOT / "tree_sitter_analyzer" / "_ast_extraction.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    assert "call_graph" not in imports
    assert "tree_sitter_analyzer.call_graph" not in imports


def test_callee_resolution_algorithm_has_single_shared_home() -> None:
    """CallGraph/CrossFile/Synapse may expose APIs, but not bespoke algorithms."""
    call_graph = (PROJECT_ROOT / "tree_sitter_analyzer" / "call_graph.py").read_text(
        encoding="utf-8"
    )
    cross_file = (
        PROJECT_ROOT / "tree_sitter_analyzer" / "cross_file_resolver.py"
    ).read_text(encoding="utf-8")
    synapse_context = (
        PROJECT_ROOT / "tree_sitter_analyzer" / "synapse_resolver" / "_context.py"
    ).read_text(encoding="utf-8")

    assert "def _resolve_callee_from_cache" not in call_graph
    assert "CalleeResolver(" in call_graph
    assert "CalleeResolver(" in cross_file
    assert "CalleeResolver(" in synapse_context
def test_no_mcp_tool_imports_from_cli() -> None:
    """ARCH-A1 regression: ``mcp/tools/*.py`` must not import from
    ``tree_sitter_analyzer.cli.*``. The dependency arrow goes one way:
    ``cli/`` may use ``mcp/`` tools, but ``mcp/tools/`` reaches shared
    builders via ``tree_sitter_analyzer.services`` instead.

    The shared builders live (physically) in ``cli/`` for now and are
    re-exported from ``services/``; a future sprint can do the file
    move under that boundary without changing any consumer.
    """
    tools_dir = PROJECT_ROOT / "tree_sitter_analyzer" / "mcp" / "tools"
    offenders: list[str] = []
    for path in sorted(tools_dir.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                # Catch both absolute and relative styles:
                #   from tree_sitter_analyzer.cli.X import …
                #   from ...cli.X import …
                if (
                    node.module.startswith("tree_sitter_analyzer.cli.")
                    or node.module.startswith("cli.")
                    or (node.level >= 1 and node.module.startswith("cli."))
                ):
                    offenders.append(f"{path.name}:{node.lineno}: from {node.module}")
                # Relative imports like ``from ...cli.X import Y`` have
                # module='cli.X' and level=3 — the .startswith check above
                # already catches them, but be explicit for readability.
    assert offenders == [], (
        "mcp/tools/* must not import from cli/* (ARCH-A1). Reach via "
        "tree_sitter_analyzer.services instead:\n  " + "\n  ".join(offenders)
    )


def _class_overrides_set_project_path(node: ast.ClassDef) -> bool:
    """Return True if the class body contains a ``set_project_path`` method."""
    return any(
        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == "set_project_path"
        for item in node.body
    )


def test_no_mcp_tool_overrides_set_project_path() -> None:
    """ARCH-A4 regression: ``BaseMCPTool.set_project_path`` is final by
    convention; tools that need to react to a project-root rebind must
    override :meth:`_on_project_root_changed` instead, so the dual-track
    init / rebind paths can't drift apart again.

    Each pattern this test catches has bitten the project at least once:
      * a subclass overriding set_project_path but forgetting to call
        super() (silently leaves base attributes pointing at the old root)
      * a subclass overriding both ``__init__`` AND ``set_project_path``
        with different init logic (constructor-built tools observe
        different state than rebound ones)
    """
    tools_dir = PROJECT_ROOT / "tree_sitter_analyzer" / "mcp" / "tools"
    offenders: list[str] = []
    for path in sorted(tools_dir.glob("*.py")):
        if path.name == "base_tool.py":
            continue  # the base class itself is allowed to define it
        pname = path.name
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if _class_overrides_set_project_path(node):
                offenders.append(f"{pname}::{node.name}.set_project_path")
    assert offenders == [], (
        "These tools override BaseMCPTool.set_project_path. Move the body "
        "into _on_project_root_changed instead (ARCH-A4):\n  " + "\n  ".join(offenders)
    )


def test_mcp_command_specs_have_resolvable_tool_classes() -> None:
    """ARCH-A2 regression: every MCP_COMMAND_SPECS entry's ``tool_attr``
    must be resolvable via ``_get_tool_class`` (i.e. present in
    ``_TOOL_CLASS_NAMES``). Adding a spec without updating the lookup
    set used to fail at runtime with ``Unknown MCP tool: …``; this test
    catches the drift at collection time."""
    from tree_sitter_analyzer.cli.commands.mcp_commands import (
        _TOOL_CLASS_NAMES,
        MCP_COMMAND_SPECS,
    )

    referenced = {spec.tool_attr for spec in MCP_COMMAND_SPECS}
    available = set(_TOOL_CLASS_NAMES)
    missing = referenced - available
    assert not missing, (
        f"MCP_COMMAND_SPECS references tool classes not registered in "
        f"_TOOL_CLASS_NAMES: {sorted(missing)}. Either add the class name "
        f"to the dict in cli/commands/mcp_commands.py or remove the spec."
    )
    # Informational: don't enforce the reverse (extra classes), since a
    # tool might intentionally exist without a CLI spec (e.g. internal
    # helpers).


def test_mcp_server_module_does_not_eagerly_import_tools() -> None:
    """PERF-3 regression: ``tree_sitter_analyzer.mcp.server`` must not import
    the 23 individual tool modules at module load. Tool imports belong inside
    ``_create_tool_registry`` so callers that only touch the server module's
    surface (e.g. for help-text introspection) don't pay the cold-start tax.
    """
    source = (PROJECT_ROOT / "tree_sitter_analyzer" / "mcp" / "server.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    offending: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Module):
            for stmt in node.body:
                if isinstance(stmt, ast.ImportFrom) and stmt.module:
                    if stmt.module.startswith(".tools."):
                        offending.append(stmt.module)
    assert offending == [], (
        "Top-level imports of .tools.* are forbidden in mcp/server.py "
        f"(PERF-3). Move them inside _create_tool_registry. Offenders: {offending}"
    )
