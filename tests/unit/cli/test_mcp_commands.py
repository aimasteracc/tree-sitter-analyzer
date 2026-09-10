"""Tests for MCP-equivalent CLI command handlers."""

from __future__ import annotations

from argparse import Namespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from tree_sitter_analyzer.cli.commands import mcp_commands
from tree_sitter_analyzer.cli_main import create_argument_parser

MCP_COMMAND_FLAGS = (
    "file_health",
    "parser_readiness",
    "project_health",
    "overview",
    "safe_to_edit",
    "change_impact",
    "dependencies",
    "refactor",
    "smart_context",
    "callers",
    "callees",
    "symbol_resolve",
    "codegraph_context",
    "codegraph_query",
)


def _certify_pulse_cli_project(root):
    """真实 CLI 用例通过完整索引建立源码认证。"""
    import asyncio

    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    result = asyncio.run(CodeGraphFullIndexTool(str(root)).execute({"mode": "full"}))
    assert result["scope_complete"] is True


def test_pulse_cli_real_index_emits_json_success(tmp_path, monkeypatch, capsys):
    # PR #1352：运行真实 CLI 解析/分发/工具/序列化，不 mock 任一业务层。
    import json
    import logging
    import sys

    from tree_sitter_analyzer.cli_main import main

    source = tmp_path / "a.py"
    source.write_text(
        'def greet():\n    """Hello CLI."""\n    return 1\n', encoding="utf-8"
    )
    _certify_pulse_cli_project(tmp_path)
    capsys.readouterr()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tsa",
            "a.py",
            "--project-root",
            str(tmp_path),
            "--pulse",
            "greet",
            "--format",
            "json",
        ],
    )
    # CLI 的日志配置属于进程级副作用；测试结束后必须还原，避免污染其他日志见证。
    loggers = [
        logging.getLogger(name)
        for name in (
            "",
            "tree_sitter_analyzer",
            "tree_sitter_analyzer.performance",
            "tree_sitter_analyzer.plugins",
            "tree_sitter_analyzer.plugins.manager",
        )
    ]
    levels = [logger.level for logger in loggers]
    try:
        with pytest.raises(SystemExit) as exited:
            main()
    finally:
        for logger, level in zip(loggers, levels, strict=True):
            logger.setLevel(level)
    assert exited.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["source_evidence"]["freshness"] == "fresh"
    assert payload["result"]["sym"]["n"] == "greet"
    assert payload["result"]["sym"]["doc"] == "Hello CLI."
    assert [logger.level for logger in loggers] == levels


def test_batch_cli_project_sequence_keeps_results_and_warning_capture(
    tmp_path, monkeypatch, capsys, caplog
):
    # PR #1352：真实 CLI 依次访问同名项目数据，CLI 后的 WARNING 见证不依赖默认级别。
    import json
    import logging
    import sys

    from tree_sitter_analyzer.api.pulse import query_pulse
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cli_main import main

    roots = []
    for label in ("first", "second"):
        root = tmp_path / label
        root.mkdir()
        source = root / "a.py"
        source.write_text(
            f'def greet():\n    """{label} greet"""\n    pass\n\ndef other():\n    """{label} other"""\n    pass\n',
            encoding="utf-8",
        )
        _certify_pulse_cli_project(root)
        roots.append(root)
    targets = [{"file": "a.py", "symbol": name} for name in ("greet", "other")]
    loggers = [
        logging.getLogger(name)
        for name in (
            "",
            "tree_sitter_analyzer",
            "tree_sitter_analyzer.performance",
            "tree_sitter_analyzer.plugins",
            "tree_sitter_analyzer.plugins.manager",
        )
    ]
    levels = [logger.level for logger in loggers]
    try:
        for root in (roots[0], roots[1], roots[0]):
            capsys.readouterr()
            monkeypatch.setattr(
                sys,
                "argv",
                [
                    "tsa",
                    "--project-root",
                    str(root),
                    "--pulse-batch",
                    json.dumps(targets),
                    "--format",
                    "json",
                ],
            )
            with pytest.raises(SystemExit) as exited:
                main()
            assert exited.value.code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["success"] is True
            assert payload["source_evidence"]["freshness"] == "fresh"
            assert (
                payload["count"],
                payload["error_count"],
                payload["truncated_count"],
            ) == (2, 0, 0)
            assert [r["sym"]["doc"] for r in payload["results"]] == [
                f"{root.name} greet",
                f"{root.name} other",
            ]
            cache = ASTCache(str(root))
            import sqlite3

            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            try:
                # 告警测试在私有副本注入数据，已发布版本不能作为写入夹具。
                cache.get_conn().backup(conn)
                conn.execute(
                    "INSERT OR REPLACE INTO ast_symbol_activation(symbol_id,file_path,last_modified_commit,computed_at) "
                    "SELECT id,file_path,?,0 FROM ast_symbol_rows WHERE name='greet'",
                    ("a" * 40,),
                )
                caplog.clear()
                with caplog.at_level(
                    logging.WARNING, logger="tree_sitter_analyzer.api.pulse"
                ):
                    assert (
                        query_pulse(conn, "a.py", "greet").git_heat.commit_msg is None
                    )
                assert (
                    "tree_sitter_analyzer.api.pulse",
                    logging.WARNING,
                    "COMMIT_MESSAGE_MISSING: a.py:greet",
                ) in caplog.record_tuples
            finally:
                conn.close()
                cache.close()
    finally:
        for logger, level in zip(loggers, levels, strict=True):
            logger.setLevel(level)


def _args(**overrides: Any) -> Namespace:
    defaults = dict.fromkeys(MCP_COMMAND_FLAGS, False)
    defaults["dependencies"] = None
    defaults["callers"] = False
    defaults["callees"] = False
    defaults["callers_file"] = None
    defaults["callees_file"] = None
    defaults["symbol_resolve"] = False
    defaults["symbol_resolve_mode"] = "resolve"
    defaults["codegraph_context"] = False
    defaults["codegraph_context_max_nodes"] = 30
    defaults["codegraph_context_max_code_blocks"] = 8
    defaults["codegraph_query"] = False
    defaults["codegraph_query_max_symbols"] = 20
    defaults["codegraph_query_max_files"] = 8
    defaults["codegraph_query_outline_only"] = False
    defaults["codegraph_query_compact"] = False
    defaults.update(
        {
            "file_path": "target.py",
            "edit_type": "refactor",
            "project_root": "/repo",
            "min_grade": "C",
            "max_files": 30,
            "change_impact_mode": "diff",
            "change_impact_include_tests": True,
        }
    )
    defaults.update(overrides)
    return Namespace(**defaults)


@pytest.mark.parametrize(
    ("flag_overrides", "tool_attr", "expected_tool_args"),
    [
        (
            {"file_health": True},
            "FileHealthTool",
            {
                "file_path": "target.py",
                "output_format": "json",
            },
        ),
        (
            {"parser_readiness": True},
            "ParserReadinessTool",
            {
                "language": "target.py",
                "include_supported": False,
                "output_format": "json",
            },
        ),
        (
            {"project_health": True},
            "ProjectHealthTool",
            {
                "min_grade": "C",
                "max_files": 30,
                "output_format": "json",
            },
        ),
        (
            {"overview": True},
            "ProjectOverviewTool",
            {"include_health": True, "output_format": "json"},
        ),
        (
            {"safe_to_edit": True},
            "SafeToEditTool",
            {
                "file_path": "target.py",
                "edit_type": "refactor",
                "output_format": "json",
            },
        ),
        (
            {"change_impact": True},
            "ChangeImpactTool",
            {
                "mode": "diff",
                "pr_url": "",
                "include_tests": True,
                "output_format": "json",
                "scope_paths": [],
                # v1.12: agent_summary_only is the new default; --change-
                # impact-full opts out. Without --change-impact-full the
                # dispatcher emits the trimmed surface.
                "agent_summary_only": True,
                "scope_mode": "report",
                "resource_profile": "default",
            },
        ),
        (
            {"dependencies": "cycles"},
            "DependencyAnalysisTool",
            {"mode": "cycles", "output_format": "json"},
        ),
        (
            {"dependencies": "file_deps"},
            "DependencyAnalysisTool",
            {"mode": "file_deps", "output_format": "json", "file_path": "target.py"},
        ),
        (
            {"refactor": True},
            "RefactoringSuggestionsTool",
            {"file_path": "target.py", "output_format": "json"},
        ),
        (
            {"smart_context": True},
            "SmartContextTool",
            {"file_path": "target.py", "output_format": "json"},
        ),
        (
            {"codegraph_context": "trace target"},
            "CodeGraphContextTool",
            {
                "task": "trace target",
                "max_nodes": 30,
                "max_code_blocks": 8,
                "output_format": "json",
                "include_graph": False,  # RFC-0006: lean default
            },
        ),
        (
            {"codegraph_query": "search('target').explore()"},
            "CodeGraphQueryTool",
            {
                "query": "search('target').explore()",
                "max_symbols": 20,
                "max_files": 8,
                "include_code": True,
                "compact": False,
                "output_format": "json",
            },
        ),
    ],
)
def test_mcp_cli_commands_delegate_to_matching_tool(
    monkeypatch,
    flag_overrides: dict[str, Any],
    tool_attr: str,
    expected_tool_args: dict[str, Any],
) -> None:
    seen: dict[str, Any] = {}

    class FakeTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "tool": tool_attr}

    monkeypatch.setattr(mcp_commands, tool_attr, FakeTool)

    output: list[dict[str, Any]] = []
    errors: list[str] = []

    result = mcp_commands.handle_mcp_commands(
        _args(**flag_overrides),
        output.append,
        errors.append,
        lambda: "json",
    )

    assert result == 0
    assert errors == []
    assert output == [{"success": True, "tool": tool_attr}]
    assert seen == {
        "project_root": "/repo",
        "arguments": expected_tool_args,
    }


def test_safe_to_edit_cli_forwards_requested_edit_type(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeSafeToEditTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(mcp_commands, "SafeToEditTool", FakeSafeToEditTool)

    result = mcp_commands.handle_mcp_commands(
        _args(safe_to_edit=True, edit_type="rename"),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "file_path": "target.py",
            "edit_type": "rename",
            "output_format": "json",
        },
    }


def test_project_health_cli_forwards_requested_max_files(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeProjectHealthTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(mcp_commands, "ProjectHealthTool", FakeProjectHealthTool)

    result = mcp_commands.handle_mcp_commands(
        _args(project_health=True, max_files=7),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "min_grade": "C",
            "max_files": 7,
            "output_format": "json",
        },
    }


def test_parser_readiness_cli_forwards_language_option(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeParserReadinessTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(mcp_commands, "ParserReadinessTool", FakeParserReadinessTool)

    result = mcp_commands.handle_mcp_commands(
        _args(
            parser_readiness=True,
            file_path=None,
            parser_readiness_language="swift",
            parser_readiness_include_supported=True,
        ),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "language": "swift",
            "include_supported": True,
            "output_format": "json",
        },
    }


def test_safe_to_edit_cli_falls_back_to_schema_default_for_legacy_namespaces(
    monkeypatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeSafeToEditTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(mcp_commands, "SafeToEditTool", FakeSafeToEditTool)

    args = _args(safe_to_edit=True)
    delattr(args, "edit_type")

    result = mcp_commands.handle_mcp_commands(
        args,
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen["arguments"]["edit_type"] == "refactor"


@pytest.mark.parametrize(
    ("flag_overrides", "expected_error"),
    [
        ({"file_health": True}, "--file-health requires a file path"),
        ({"safe_to_edit": True}, "--safe-to-edit requires a file path"),
        (
            {"dependencies": "file_deps"},
            "--dependencies requires a file path for file_deps and blast_radius modes",
        ),
        (
            {"dependencies": "blast_radius"},
            "--dependencies requires a file path for file_deps and blast_radius modes",
        ),
        ({"refactor": True}, "--refactor requires a file path"),
        ({"smart_context": True}, "--smart-context requires a file path"),
    ],
)
def test_file_scoped_mcp_cli_commands_require_file_path(
    flag_overrides: dict[str, Any],
    expected_error: str,
) -> None:
    output: list[dict[str, Any]] = []
    errors: list[str] = []

    result = mcp_commands.handle_mcp_commands(
        _args(file_path=None, **flag_overrides),
        output.append,
        errors.append,
        lambda: "json",
    )

    assert result == 1
    assert output == []
    assert errors == [expected_error]


@pytest.mark.parametrize(
    ("mode", "expected_mode"),
    [
        ("summary", "summary"),
        ("cycles", "cycles"),
        ("full", "summary"),
    ],
)
def test_project_scoped_dependency_modes_do_not_require_file_path(
    monkeypatch,
    mode: str,
    expected_mode: str,
) -> None:
    seen: dict[str, Any] = {}

    class FakeDependencyAnalysisTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(
        mcp_commands, "DependencyAnalysisTool", FakeDependencyAnalysisTool
    )

    result = mcp_commands.handle_mcp_commands(
        _args(file_path=None, dependencies=mode),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {"mode": expected_mode, "output_format": "json"},
    }


def test_change_impact_cli_does_not_require_file_path(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeChangeImpactTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "changed_files": []}

    monkeypatch.setattr(mcp_commands, "ChangeImpactTool", FakeChangeImpactTool)

    output: list[dict[str, Any]] = []
    errors: list[str] = []
    args = Namespace(
        change_impact=True,
        file_path=None,
        project_root="/repo",
    )

    result = mcp_commands.handle_mcp_commands(
        args,
        output.append,
        errors.append,
        lambda: "json",
    )

    assert result == 0
    assert errors == []
    assert output == [{"success": True, "changed_files": []}]
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "mode": "diff",
            "pr_url": "",
            "include_tests": True,
            "output_format": "json",
            "scope_paths": [],
            # v1.12: default flip — agent_summary_only is now True unless
            # --change-impact-full is passed.
            "agent_summary_only": True,
            "scope_mode": "report",
            "resource_profile": "default",
        },
    }


def test_change_impact_cli_forwards_scope_paths(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeChangeImpactTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "changed_files": []}

    monkeypatch.setattr(mcp_commands, "ChangeImpactTool", FakeChangeImpactTool)

    result = mcp_commands.handle_mcp_commands(
        _args(
            change_impact=True,
            change_impact_scope=[
                "tree_sitter_analyzer/mcp/tools",
                "tests/unit/mcp",
            ],
        ),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "mode": "diff",
            "pr_url": "",
            "include_tests": True,
            "output_format": "json",
            "scope_paths": [
                "tree_sitter_analyzer/mcp/tools",
                "tests/unit/mcp",
            ],
            # v1.12 default flip: trimmed surface unless --change-impact-full.
            "agent_summary_only": True,
            "scope_mode": "report",
            "resource_profile": "default",
        },
    }


def test_change_impact_cli_forwards_scope_mode_strict(monkeypatch) -> None:
    """#8 CLI parity: --change-impact-scope-mode strict reaches the MCP tool."""
    seen: dict[str, Any] = {}

    class FakeChangeImpactTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "changed_files": []}

    monkeypatch.setattr(mcp_commands, "ChangeImpactTool", FakeChangeImpactTool)

    result = mcp_commands.handle_mcp_commands(
        _args(
            change_impact=True,
            change_impact_scope=["tree_sitter_analyzer/mcp/tools"],
            change_impact_scope_mode="strict",
        ),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen["arguments"]["scope_mode"] == "strict"
    assert seen["arguments"]["scope_paths"] == ["tree_sitter_analyzer/mcp/tools"]


def test_change_impact_cli_forwards_resource_profile(monkeypatch) -> None:
    """Local resource profile must reach the MCP change-impact tool."""
    seen: dict[str, Any] = {}

    class FakeChangeImpactTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "changed_files": []}

    monkeypatch.setattr(mcp_commands, "ChangeImpactTool", FakeChangeImpactTool)

    result = mcp_commands.handle_mcp_commands(
        _args(
            change_impact=True,
            change_impact_resource_profile="local_low_impact",
        ),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen["arguments"]["resource_profile"] == "local_low_impact"


def test_change_impact_cli_forwards_agent_summary_only(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeChangeImpactTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(mcp_commands, "ChangeImpactTool", FakeChangeImpactTool)

    result = mcp_commands.handle_mcp_commands(
        _args(change_impact=True, agent_summary_only=True),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "mode": "diff",
            "pr_url": "",
            "include_tests": True,
            "output_format": "json",
            "scope_paths": [],
            "agent_summary_only": True,
            "scope_mode": "report",
            "resource_profile": "default",
        },
    }


def test_change_impact_cli_forwards_mode_and_test_discovery_toggle(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeChangeImpactTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(mcp_commands, "ChangeImpactTool", FakeChangeImpactTool)

    result = mcp_commands.handle_mcp_commands(
        _args(
            change_impact=True,
            change_impact_mode="staged",
            change_impact_include_tests=False,
        ),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "mode": "staged",
            "pr_url": "",
            "include_tests": False,
            "output_format": "json",
            "scope_paths": [],
            # v1.12 default flip: trimmed surface unless --change-impact-full.
            "agent_summary_only": True,
            "scope_mode": "report",
            "resource_profile": "default",
        },
    }


def test_change_impact_cli_forwards_change_impact_full(monkeypatch) -> None:
    """``--change-impact-full`` flips agent_summary_only back to False.

    Mirrors the v1.12 default-flip contract: by default the dispatcher
    emits the trimmed agent surface; ``--change-impact-full`` is the
    explicit opt-out for callers who genuinely need the 145 KB envelope.
    """
    seen: dict[str, Any] = {}

    class FakeChangeImpactTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(mcp_commands, "ChangeImpactTool", FakeChangeImpactTool)

    result = mcp_commands.handle_mcp_commands(
        _args(change_impact=True, change_impact_full=True),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "mode": "diff",
            "pr_url": "",
            "include_tests": True,
            "output_format": "json",
            "scope_paths": [],
            "agent_summary_only": False,
            "scope_mode": "report",
            "resource_profile": "default",
        },
    }


def test_change_impact_fail_on_risk_exits_1_on_caution_verdict(monkeypatch) -> None:
    """--change-impact-fail-on-risk caution: exit 1 when verdict is CAUTION."""

    class FakeChangeImpactTool:
        def __init__(self, project_root: str | None = None) -> None:
            pass

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            return {"success": True, "verdict": "CAUTION", "changed_files": []}

    monkeypatch.setattr(mcp_commands, "ChangeImpactTool", FakeChangeImpactTool)

    result = mcp_commands.handle_mcp_commands(
        _args(change_impact=True, change_impact_fail_on_risk="caution"),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 1


def test_change_impact_fail_on_risk_exits_0_below_threshold(monkeypatch) -> None:
    """--change-impact-fail-on-risk caution: exit 0 when verdict is INFO (below threshold)."""

    class FakeChangeImpactTool:
        def __init__(self, project_root: str | None = None) -> None:
            pass

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            return {"success": True, "verdict": "INFO", "changed_files": []}

    monkeypatch.setattr(mcp_commands, "ChangeImpactTool", FakeChangeImpactTool)

    result = mcp_commands.handle_mcp_commands(
        _args(change_impact=True, change_impact_fail_on_risk="caution"),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0


def test_change_impact_fail_on_risk_unsafe_only_exits_1_for_unsafe(monkeypatch) -> None:
    """--change-impact-fail-on-risk unsafe: exit 1 only when verdict is UNSAFE."""

    class FakeChangeImpactTool:
        def __init__(self, project_root: str | None = None) -> None:
            pass

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            return {"success": True, "verdict": "UNSAFE", "changed_files": []}

    monkeypatch.setattr(mcp_commands, "ChangeImpactTool", FakeChangeImpactTool)

    result = mcp_commands.handle_mcp_commands(
        _args(change_impact=True, change_impact_fail_on_risk="unsafe"),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 1


def test_change_impact_fail_on_risk_unsafe_exits_0_for_caution(monkeypatch) -> None:
    """--change-impact-fail-on-risk unsafe: exit 0 for CAUTION (below UNSAFE threshold)."""

    class FakeChangeImpactTool:
        def __init__(self, project_root: str | None = None) -> None:
            pass

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            return {"success": True, "verdict": "CAUTION", "changed_files": []}

    monkeypatch.setattr(mcp_commands, "ChangeImpactTool", FakeChangeImpactTool)

    result = mcp_commands.handle_mcp_commands(
        _args(change_impact=True, change_impact_fail_on_risk="unsafe"),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0


def test_change_impact_no_fail_on_risk_exits_0_on_any_verdict(monkeypatch) -> None:
    """Without --change-impact-fail-on-risk, any verdict exits 0 on success."""

    class FakeChangeImpactTool:
        def __init__(self, project_root: str | None = None) -> None:
            pass

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            return {"success": True, "verdict": "UNSAFE", "changed_files": []}

    monkeypatch.setattr(mcp_commands, "ChangeImpactTool", FakeChangeImpactTool)

    result = mcp_commands.handle_mcp_commands(
        _args(change_impact=True),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0


def test_change_impact_fail_on_risk_review_exits_1_for_warn(monkeypatch) -> None:
    """--change-impact-fail-on-risk review: WARN (above REVIEW) must exit 1."""

    class FakeChangeImpactTool:
        def __init__(self, project_root: str | None = None) -> None:
            pass

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            return {"success": True, "verdict": "WARN", "changed_files": []}

    monkeypatch.setattr(mcp_commands, "ChangeImpactTool", FakeChangeImpactTool)

    result = mcp_commands.handle_mcp_commands(
        _args(change_impact=True, change_impact_fail_on_risk="review"),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 1


def test_change_impact_fail_on_risk_review_exits_0_for_caution(monkeypatch) -> None:
    """--change-impact-fail-on-risk review: CAUTION (below REVIEW) must exit 0."""

    class FakeChangeImpactTool:
        def __init__(self, project_root: str | None = None) -> None:
            pass

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            return {"success": True, "verdict": "CAUTION", "changed_files": []}

    monkeypatch.setattr(mcp_commands, "ChangeImpactTool", FakeChangeImpactTool)

    result = mcp_commands.handle_mcp_commands(
        _args(change_impact=True, change_impact_fail_on_risk="review"),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0


def test_callers_cli_delegates_to_callers_tool(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeCallersTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(mcp_commands, "CodeGraphCallersTool", FakeCallersTool)

    result = mcp_commands.handle_mcp_commands(
        _args(callers="parse_file", callers_file="src/parser.py"),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "function_name": "parse_file",
            "file_path": "src/parser.py",
            "limit": 50,
            "output_format": "json",
        },
    }


def test_callees_cli_delegates_to_callees_tool(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeCalleesTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(mcp_commands, "CodeGraphCalleesTool", FakeCalleesTool)

    result = mcp_commands.handle_mcp_commands(
        _args(callees="main", callees_file=None),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "function_name": "main",
            "file_path": None,
            "limit": 50,
            "output_format": "json",
        },
    }


def test_symbol_resolve_cli_delegates_to_resolve_tool(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeResolveTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(mcp_commands, "CodeGraphSymbolResolveTool", FakeResolveTool)

    result = mcp_commands.handle_mcp_commands(
        _args(symbol_resolve="UserService.get_user", symbol_resolve_mode="resolve"),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "symbol": "UserService.get_user",
            "mode": "resolve",
            "output_format": "json",
        },
    }


@pytest.mark.parametrize(
    ("flag_overrides", "tool_attr", "expected_tool_args"),
    [
        (
            {
                "safe_to_edit": True,
                "access_mode": "read_existing",
                "snapshot_id": "idxsnap_01",
                "source_generation": "gen_01",
            },
            "SafeToEditTool",
            {
                "file_path": "target.py",
                "edit_type": "refactor",
                "output_format": "json",
                "access_mode": "read_existing",
                "snapshot_id": "idxsnap_01",
                "source_generation": "gen_01",
            },
        ),
        (
            {
                "change_impact": True,
                "access_mode": "read_existing",
            },
            "ChangeImpactTool",
            {
                "mode": "diff",
                "pr_url": "",
                "include_tests": True,
                "output_format": "json",
                "scope_paths": [],
                "agent_summary_only": True,
                "scope_mode": "report",
                "resource_profile": "default",
                "access_mode": "read_existing",
            },
        ),
        (
            {
                "codegraph_context": "trace target",
                "access_mode": "read_existing",
                "snapshot_id": "idxsnap_01",
                "source_generation": "gen_01",
            },
            "CodeGraphContextTool",
            {
                "task": "trace target",
                "max_nodes": 30,
                "max_code_blocks": 8,
                "output_format": "json",
                "include_graph": False,
                "access_mode": "read_existing",
                "snapshot_id": "idxsnap_01",
                "source_generation": "gen_01",
            },
        ),
        (
            {
                "ast_diff": True,
                "access_mode": "read_existing",
                "diff_snapshot_id": "diffsnap_01",
            },
            "ASTDiffTool",
            {
                "mode": "diff_files",
                "old_file": None,
                "new_file": None,
                "old_source": None,
                "new_source": None,
                "file_path": None,
                "old_ref": "HEAD~1",
                "new_ref": "HEAD",
                "language": None,
                "include_node_bodies": False,
                "output_format": "json",
                "access_mode": "read_existing",
                "diff_snapshot_id": "diffsnap_01",
            },
        ),
        (
            {
                "semantic_classify": True,
                "access_mode": "read_existing",
                "diff_snapshot_id": "diffsnap_01",
            },
            "SemanticClassifyTool",
            {
                "mode": "classify_file",
                "file_path": "target.py",
                "old_ref": "HEAD~1",
                "new_ref": "HEAD",
                "language": None,
                "include_ast_nodes": False,
                "hunk_cap": 50,
                "output_format": "json",
                "access_mode": "read_existing",
                "diff_snapshot_id": "diffsnap_01",
            },
        ),
    ],
)
def test_read_existing_controls_forwarded_to_tool(
    monkeypatch,
    flag_overrides: dict[str, Any],
    tool_attr: str,
    expected_tool_args: dict[str, Any],
) -> None:
    """RFC-0022 process-local controls reach the MCP tool on the CLI-handler path.

    Codex P1 (#1257): these controls were MCP-only because the CLI bridge
    dropped them; the in-process bridge must forward access_mode / snapshot
    IDs verbatim so RFC-0022 routing can compose index.status, nav.context
    and edit snapshot consumers in one process.
    """
    seen: dict[str, Any] = {}

    class FakeTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "tool": tool_attr}

    monkeypatch.setattr(mcp_commands, tool_attr, FakeTool)

    output: list[dict[str, Any]] = []
    errors: list[str] = []

    result = mcp_commands.handle_mcp_commands(
        _args(**flag_overrides),
        output.append,
        errors.append,
        lambda: "json",
    )

    assert result == 0
    assert errors == []
    assert output == [{"success": True, "tool": tool_attr}]
    assert seen == {
        "project_root": "/repo",
        "arguments": expected_tool_args,
    }


@pytest.mark.parametrize(
    ("flag_overrides", "tool_attr"),
    [
        ({"safe_to_edit": True}, "SafeToEditTool"),
        ({"change_impact": True}, "ChangeImpactTool"),
        ({"codegraph_context": "trace target"}, "CodeGraphContextTool"),
        ({"ast_diff": True}, "ASTDiffTool"),
        ({"semantic_classify": True}, "SemanticClassifyTool"),
    ],
)
def test_read_existing_controls_absent_are_not_forwarded(
    monkeypatch, flag_overrides: dict[str, Any], tool_attr: str
) -> None:
    """Ordinary CLI namespaces (the parser never populates the controls) forward none.

    Keeps the bridge strictly opt-in for in-process RFC-0022 routers.
    """
    seen: dict[str, Any] = {}

    class FakeTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(mcp_commands, tool_attr, FakeTool)

    result = mcp_commands.handle_mcp_commands(
        _args(**flag_overrides),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    for control in (
        "access_mode",
        "snapshot_id",
        "source_generation",
        "diff_snapshot_id",
        "route_lease_id",
    ):
        assert control not in seen["arguments"]


@pytest.mark.parametrize(
    ("argv", "tool", "expected"),
    [
        (
            ["--rename", "before", "--rename-new-name", "after"],
            "CodeGraphRefactorTool",
            {"symbol": "before", "new_name": "after", "mode": "preview"},
        ),
        (
            [
                "--rename",
                "before",
                "--rename-new-name",
                "after",
                "--rename-mode",
                "apply",
            ],
            "CodeGraphRefactorTool",
            {"symbol": "before", "new_name": "after", "mode": "apply"},
        ),
        (
            ["sample.py", "--unreachable-code"],
            "UnreachableCodeTool",
            {
                "mode": "file",
                "file_path": "sample.py",
                "include_test_files": False,
                "max_files": 500,
            },
        ),
        (
            [
                "--unreachable-code",
                "--unreachable-code-mode",
                "project",
                "--unreachable-code-include-tests",
                "--unreachable-code-max-files",
                "7",
            ],
            "UnreachableCodeTool",
            {"mode": "project", "include_test_files": True, "max_files": 7},
        ),
        (
            ["--detect-middleware"],
            "MiddlewareDetectorTool",
            {"mode": "all", "framework": "all"},
        ),
        (
            [
                "--detect-middleware",
                "--detect-middleware-mode",
                "lookup",
                "--detect-middleware-url-prefix",
                "/api",
                "--detect-middleware-framework",
                "express",
            ],
            "MiddlewareDetectorTool",
            {"mode": "lookup", "url_prefix": "/api", "framework": "express"},
        ),
    ],
)
@pytest.mark.parametrize("output_format", ["json"])
def test_recovered_routes_delegate_all_arguments(
    argv, tool, expected, output_format, monkeypatch
):
    args = create_argument_parser().parse_args(argv)
    executed = AsyncMock(return_value={"success": True, "verdict": "OK"})

    class FakeTool:
        def __init__(self, *args, **kwargs):
            self.execute = executed

    monkeypatch.setattr(mcp_commands, tool, FakeTool, raising=False)
    assert (
        mcp_commands.handle_mcp_commands(
            args, lambda result: None, pytest.fail, lambda: output_format
        )
        == 0
    )
    assert executed.call_args.args[0] == {**expected, "output_format": output_format}


def test_unreachable_file_mode_requires_positional_path():
    args = create_argument_parser().parse_args(["--unreachable-code"])
    errors = []
    assert (
        mcp_commands.handle_mcp_commands(
            args, lambda result: None, errors.append, lambda: "json"
        )
        == 1
    )
    assert "requires a file path" in errors[0]


def test_rename_missing_new_name_returns_validation_envelope():
    args = create_argument_parser().parse_args(["--rename", "before"])
    results = []
    assert (
        mcp_commands.handle_mcp_commands(
            args, results.append, pytest.fail, lambda: "json"
        )
        == 1
    )
    assert results[0]["success"] is False
    assert "--rename-new-name" in results[0]["error"]


@pytest.mark.slow_ok  # 五次真实 CLI 进程启动及临时项目索引，验证跨进程写入边界。
def test_real_cli_recovered_routes(tmp_path):
    """在可丢弃项目上验证真实入口、预览不写文件以及显式应用。"""
    import json
    import subprocess
    import sys

    source = tmp_path / "sample.py"
    original = "def before():\n    return 1\n    print('unreachable')\n\nbefore()\n"
    source.write_text(original, encoding="utf-8")

    def run(*argv):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--project-root",
                str(tmp_path),
                *argv,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        return json.loads(completed.stdout)

    unreachable = run(str(source), "--unreachable-code")
    assert unreachable.get("error") is None
    assert unreachable["success"] is True
    assert unreachable["unreachable_count"] == 1
    assert unreachable["unreachable_blocks"][0]["start_line"] == 3
    middleware = run("--detect-middleware")
    assert middleware.get("error") is None
    assert middleware["success"] is True
    assert middleware["middleware_count"] == 0
    run("--ast-cache", "index")
    preview = run("--rename", "before", "--rename-new-name", "after")
    assert preview["success"] is True
    assert source.read_text(encoding="utf-8") == original
    applied = run(
        "--rename", "before", "--rename-new-name", "after", "--rename-mode", "apply"
    )
    assert applied["success"] is True
    assert source.read_text(encoding="utf-8") == original.replace("before", "after")


@pytest.mark.parametrize("output_format", ["json", "toon"])
def test_verify_plan_cli_forwards_descriptor_and_output_format(output_format):
    args = create_argument_parser().parse_args(["--verify-plan", "descriptor"])
    from tree_sitter_analyzer.cli.commands.mcp_command_helpers import (
        find_selected_mcp_command,
    )

    spec = find_selected_mcp_command(args, mcp_commands.MCP_COMMAND_SPECS)
    assert spec.tool_attr == "VerificationTool"
    assert spec.build_tool_args(args, output_format) == {
        "request": "descriptor",
        "output_format": output_format,
    }
