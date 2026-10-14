"""Contract tests split from the former agent workflow monolith."""
# ruff: noqa: F401

from __future__ import annotations

import ast
import configparser
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import cast

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
    path = PROJECT_ROOT / "tree_sitter_analyzer" / "cache" / "extraction.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    assert "call_graph" not in imports
    assert "tree_sitter_analyzer.call_graph" not in imports


def test_call_graph_supported_exts_covers_function_extraction_languages() -> None:
    """CallGraph's file-scan allowlist must not silently narrow past what
    function_extraction.py already knows how to walk.

    Regression: found in the 2026-07-21 architecture-consistency dogfood
    pass (PR #1157). CallGraph.build() historically hardcoded its own
    7-language supported_exts set, independent of function_extraction's
    per-language dispatch tables. Rust/C#/Kotlin/Ruby/PHP/Swift/Lua all had
    working _FUNC_DEF_TYPES/_CALL_NODE_TYPES entries but were silently
    excluded from every CodeGraph-parity tool (--call-graph, --callers,
    --callees, dead-code detection, codegraph_* MCP tools) because the file
    scanner dropped their files before parsing. See call_graph.py's
    SUPPORTED_EXTS docstring.
    """
    from tree_sitter_analyzer.call_graph import SUPPORTED_EXTS
    from tree_sitter_analyzer.function_extraction import SUPPORTED_LANGUAGES
    from tree_sitter_analyzer.languages.lang_extension_map import EXT_TO_LANG

    exts_by_lang: dict[str, set[str]] = {}
    for ext, lang in EXT_TO_LANG.items():
        exts_by_lang.setdefault(lang, set()).add(ext)

    missing: dict[str, set[str]] = {}
    for lang in SUPPORTED_LANGUAGES:
        lang_exts = exts_by_lang.get(lang, set())
        uncovered = lang_exts - SUPPORTED_EXTS
        if uncovered:
            missing[lang] = uncovered

    assert missing == {}, (
        f"function_extraction supports these languages' node types but "
        f"CallGraph.SUPPORTED_EXTS omits their extensions: {missing}"
    )


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


# --- MCP / CLI 冷启动导入不变量（CLAUDE.md §11：延迟声明必须成为可执行不变量）---
# 2026-10-14 实测：spawn→initialize 回复 10.8 s、``--version`` 5.8 s。根因是握手前
# 就导入了分析栈（core / plugins / chardet / tree_sitter）、旧版工具别名与资源对象。
# 下列测试在独立子进程中钉住握手完成时与 ``--version`` 退出时已加载的模块，
# 不使用挂钟阈值；数值变化时须有意识地重新钉住（只允许往更少的方向走）。

# 分析栈及其重型依赖：任一前缀出现在 sys.modules 中即视为冷启动回退。
_ANALYSIS_STACK_ROOTS = (
    "chardet",
    "tree_sitter",
    "tree_sitter_analyzer.cache",
    "tree_sitter_analyzer.core",
    "tree_sitter_analyzer.encoding_utils",
    "tree_sitter_analyzer.formatters",
    "tree_sitter_analyzer.languages",
    "tree_sitter_analyzer.mcp.resources",
    "tree_sitter_analyzer.mcp.tools",
    "tree_sitter_analyzer.models",
    "tree_sitter_analyzer.plugins",
)

_MCP_INITIALIZE_PROBE = """
import asyncio, json, sys
from mcp.shared.memory import create_connected_server_and_client_session
from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

async def run():
    app = TreeSitterAnalyzerMCPServer(sys.argv[1])
    # 进入会话即完成真实 SDK 的 initialize 握手。
    async with create_connected_server_and_client_session(app.create_server()):
        return sorted(sys.modules)

print(json.dumps(asyncio.run(run())))
"""

_CLI_VERSION_PROBE = """
import json, sys
sys.argv = ["tree-sitter-analyzer", "--version"]
from tree_sitter_analyzer.cli_main import main
try:
    main()
except SystemExit as exc:
    code = exc.code
print(json.dumps({"code": code, "modules": sorted(sys.modules)}))
"""

# ``--version`` 退出时允许加载的全部 tree_sitter_analyzer 模块（精确集合）。
_CLI_VERSION_TSA_MODULES = {
    "tree_sitter_analyzer",
    "tree_sitter_analyzer.cli",
    "tree_sitter_analyzer.cli.argument_validator",
    "tree_sitter_analyzer.cli_main",
    "tree_sitter_analyzer.output_manager",
    "tree_sitter_analyzer.query_loader",
    "tree_sitter_analyzer.utils",
    "tree_sitter_analyzer.utils._logging_helpers",
    "tree_sitter_analyzer.utils._tree_sitter_compat_helpers",
    "tree_sitter_analyzer.utils.logging",
    "tree_sitter_analyzer.utils.text_utils",
    "tree_sitter_analyzer.utils.tree_sitter_compat",
}


def _run_probe(script: str, *args: str) -> str:
    """在全新解释器中运行探针，返回最后一行 stdout（JSON）。"""
    completed = subprocess.run(
        [sys.executable, "-c", script, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    return completed.stdout.strip().splitlines()[-1]


def _analysis_stack_modules(modules: list[str]) -> list[str]:
    """返回 modules 中属于分析栈前缀的模块名（已排序）。"""
    return sorted(
        name
        for name in modules
        for root in _ANALYSIS_STACK_ROOTS
        if name == root or name.startswith(root + ".")
    )


@pytest.fixture(scope="module")
def mcp_initialize_modules(tmp_path_factory: pytest.TempPathFactory) -> list[str]:
    """MCP 服务器回复 initialize 时子进程中已加载的全部模块。"""
    root = tmp_path_factory.mktemp("coldstart_root")
    return json.loads(_run_probe(_MCP_INITIALIZE_PROBE, str(root)))


@pytest.fixture(scope="module")
def cli_version_result() -> dict[str, object]:
    """``tree-sitter-analyzer --version`` 子进程的退出码与已加载模块。"""
    return json.loads(_run_probe(_CLI_VERSION_PROBE))


def test_mcp_initialize_loads_no_analysis_stack(
    mcp_initialize_modules: list[str],
) -> None:
    """initialize 回复前不得导入分析栈、工具模块或资源模块（2026-10-14 冷启动）。"""
    assert _analysis_stack_modules(mcp_initialize_modules) == []


def test_mcp_initialize_tsa_module_count_is_pinned(
    mcp_initialize_modules: list[str],
) -> None:
    """钉住 initialize 时已加载的 tree_sitter_analyzer 模块数（develop 28a7d5d5 基线为 299）。"""
    tsa = [
        m for m in mcp_initialize_modules if m.split(".")[0] == "tree_sitter_analyzer"
    ]
    assert len(tsa) == 50, tsa


def test_cli_version_exits_zero(cli_version_result: dict[str, object]) -> None:
    """``--version`` 快速路径以退出码 0 结束。"""
    assert cli_version_result["code"] == 0


def test_cli_version_loads_only_pinned_tsa_modules(
    cli_version_result: dict[str, object],
) -> None:
    """``--version`` 只加载钉住的轻量模块集合，不导入分析栈与 MCP 栈。"""
    modules = cast(list[str], cli_version_result["modules"])
    tsa = {m for m in modules if m.split(".")[0] == "tree_sitter_analyzer"}
    assert tsa == _CLI_VERSION_TSA_MODULES


def test_cli_version_loads_no_mcp_sdk(cli_version_result: dict[str, object]) -> None:
    """``--version`` 不得导入 MCP SDK 或 pydantic。"""
    modules = cast(list[str], cli_version_result["modules"])
    assert sorted({m.split(".")[0] for m in modules} & {"mcp", "pydantic"}) == []


def test_cli_version_fast_path_matches_full_parser_output(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """快速路径输出须与完整解析器的 ``--version`` 动作逐字一致。"""
    import tree_sitter_analyzer.cli_main as cli_main_module

    monkeypatch.setattr(sys, "argv", ["tree-sitter-analyzer", "--version"])
    with pytest.raises(SystemExit) as fast_exit:
        cli_main_module.main()
    fast = capsys.readouterr().out
    with pytest.raises(SystemExit) as full_exit:
        create_argument_parser().parse_args(["--version"])
    full = capsys.readouterr().out
    assert (fast, fast_exit.value.code) == (full, full_exit.value.code)
