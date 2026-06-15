"""Tests for MCP-equivalent CLI command handlers."""

from __future__ import annotations

from argparse import Namespace
from typing import Any

import pytest

from tree_sitter_analyzer.cli.commands import mcp_commands

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
                "compact_only": False,
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
                "compact_only": False,
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
                "compact_only": False,
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
                "compact_only": False,
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
            return {"success": True, "tool": tool_attr, "toon_content": "compact"}

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
    assert output == [{"success": True, "tool": tool_attr, "toon_content": "compact"}]
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
            "compact_only": False,
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
            "compact_only": False,
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


def test_mcp_cli_toon_output_prints_tool_toon_content(monkeypatch, capsys) -> None:
    class FakeProjectOverviewTool:
        def __init__(self, project_root: str | None = None) -> None:
            pass

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            return {"success": True, "toon_content": "project:compact"}

    monkeypatch.setattr(mcp_commands, "ProjectOverviewTool", FakeProjectOverviewTool)

    output: list[dict[str, Any]] = []
    errors: list[str] = []

    result = mcp_commands.handle_mcp_commands(
        _args(overview=True),
        output.append,
        errors.append,
        lambda: "toon",
    )

    assert result == 0
    assert errors == []
    assert output == []
    assert capsys.readouterr().out == "project:compact\n"


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
            "compact_only": False,
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
            "compact_only": False,
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
            "compact_only": False,
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
            "compact_only": False,
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
            "compact_only": False,
            "resource_profile": "default",
        },
    }


def test_callers_cli_delegates_to_callers_tool(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeCallersTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "toon_content": "callers result"}

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
            return {"success": True, "toon_content": "callees result"}

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
            return {"success": True, "toon_content": "resolve result"}

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


def test_compact_toon_cli_flag_forwards_compact_only(monkeypatch) -> None:
    """RFC-0012 CLI parity: --compact-toon reaches the MCP compact_only arg."""
    seen: dict[str, Any] = {}

    class FakeFileHealthTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(mcp_commands, "FileHealthTool", FakeFileHealthTool)

    result = mcp_commands.handle_mcp_commands(
        _args(file_health=True, compact_toon=True),
        lambda payload: None,
        lambda error: None,
        lambda: "toon",
    )

    assert result == 0
    assert seen["arguments"]["compact_only"] is True
