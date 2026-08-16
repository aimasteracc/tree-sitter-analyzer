"""Unit tests for SafeToEditTool."""

import asyncio
import os
import sys
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade
from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import (
    SafeToEditTool,
    _compute_risk,
    _is_init_file,
)
from tree_sitter_analyzer.mcp.tools.utils.test_discovery import find_test_files

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
TARGET_FILE = "tree_sitter_analyzer/mcp/tools/safe_to_edit_tool.py"
SERVER_FILE = "tree_sitter_analyzer/mcp/server.py"


@pytest.fixture
def tool(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'sample'\n")

    target = tmp_path / TARGET_FILE
    target.parent.mkdir(parents=True)
    target.write_text(
        """
class SafeToEditTool:
    def execute(self):
        return "safe"
""".strip()
    )

    server = tmp_path / SERVER_FILE
    server.write_text(
        """
from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool


def create_tool():
    return SafeToEditTool()
""".strip()
    )

    test_file = tmp_path / "tests/unit/mcp/test_safe_to_edit_tool.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_safe_to_edit_tool(): pass\n")

    t = SafeToEditTool(str(tmp_path))
    t.set_project_path(str(tmp_path))
    return t


def _run(coro):
    return asyncio.run(coro)


class TestSafeToEditTool:
    def test_tool_definition(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "safe_to_edit"
        assert "file_path" in defn["inputSchema"]["properties"]
        assert "edit_type" in defn["inputSchema"]["properties"]

    def test_validate_arguments_missing_path(self, tool):
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({})

    def test_validate_arguments_empty_path(self, tool):
        with pytest.raises(ValueError, match="non-empty string"):
            tool.validate_arguments({"file_path": ""})

    def test_validate_arguments_valid(self, tool):
        assert tool.validate_arguments({"file_path": "some_file.py"})

    def test_execute_returns_risk_level(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE}))
        assert "risk_level" in result
        assert result["risk_level"] in ("safe", "caution", "dangerous")

    def test_execute_includes_health_grade(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE}))
        assert "health_grade" in result
        assert result["health_grade"] in ("A", "B", "C", "D", "F")

    def test_execute_includes_pre_edit_checklist(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE, "output_format": "json"}))
        assert "pre_edit_checklist" in result
        checklist = "\n".join(result["pre_edit_checklist"])
        assert "RISK" in checklist
        assert "Run existing tests FIRST" in checklist
        assert "Run same verification AFTER editing" in checklist

    def test_execute_includes_structured_agent_workflow(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE, "output_format": "json"}))

        workflow = result["agent_workflow"]

        assert workflow["edit_strategy"] in {
            "direct_focused_edit",
            "focused_edit_with_tests",
            "split_into_atomic_edits",
            "trace_references_before_edit",
        }
        assert workflow["before_edit_commands"] == [
            "uv run pytest tests/unit/mcp/test_safe_to_edit_tool.py -q"
        ]
        assert workflow["after_edit_commands"][0] == (
            "uv run pytest tests/unit/mcp/test_safe_to_edit_tool.py -q"
        )
        assert (
            "uv run python -m tree_sitter_analyzer "
            "tree_sitter_analyzer/mcp/tools/safe_to_edit_tool.py "
            "--file-health --format json"
        ) in workflow["after_edit_commands"]
        assert workflow["queue_boundary_commands"] == ["uv run pytest -q"]

    def test_execute_includes_compact_agent_summary(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE}))

        summary = result["agent_summary"]

        assert summary["risk"] == result["risk_level"]
        assert summary["edit_strategy"] == "direct_focused_edit"
        assert summary["preflight_command"] == (
            "uv run pytest tests/unit/mcp/test_safe_to_edit_tool.py -q"
        )
        assert summary["verification_command"] == (
            "uv run pytest tests/unit/mcp/test_safe_to_edit_tool.py -q"
        )
        assert summary["queue_boundary_command"] == "uv run pytest -q"
        assert summary["stop_condition"] == (
            "uv run pytest tests/unit/mcp/test_safe_to_edit_tool.py -q passes; "
            "run uv run pytest -q at the queue boundary."
        )

    def test_pre_edit_checklist_uses_uv_pytest_contract(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE, "output_format": "json"}))
        checklist = "\n".join(result["pre_edit_checklist"])

        assert "uv run pytest" in checklist
        assert "Run existing tests FIRST: pytest " not in checklist

    def test_execute_includes_risk_factors(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE, "output_format": "json"}))
        assert "risk_factors" in result
        assert isinstance(result["risk_factors"], list)

    def test_execute_includes_dependency_info(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE}))
        assert "downstream_count" in result
        assert "dependency_count" in result

    def test_execute_includes_test_files(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE, "output_format": "json"}))
        assert "test_files_nearby" in result

    def test_edit_type_rename_higher_risk(self, tool):
        result_refactor = _run(
            tool.execute(
                {
                    "file_path": TARGET_FILE,
                    "edit_type": "refactor",
                    "output_format": "json",
                }
            )
        )
        result_rename = _run(
            tool.execute(
                {
                    "file_path": TARGET_FILE,
                    "edit_type": "rename",
                    "output_format": "json",
                }
            )
        )
        # Rename should have at least as many risk factors
        assert len(result_rename["risk_factors"]) >= len(
            result_refactor["risk_factors"]
        )

    def test_toon_format(self, tool):
        result = _run(
            tool.execute(
                {
                    "file_path": TARGET_FILE,
                    "output_format": "toon",
                }
            )
        )
        assert "risk_level" in result

    def test_json_format(self, tool):
        result = _run(
            tool.execute(
                {
                    "file_path": TARGET_FILE,
                    "output_format": "json",
                }
            )
        )
        assert "risk_level" in result
        assert result.get("format") != "toon" or "risk_level" in result

    def test_file_not_found(self, tool):
        with pytest.raises(ValueError, match="File not found"):
            _run(tool.execute({"file_path": "nonexistent_file.py"}))

    def test_well_connected_file_has_downstream(self, tool):
        result = _run(tool.execute({"file_path": SERVER_FILE}))
        # In this temp fixture nothing imports server.py (server.py imports
        # safe_to_edit_tool.py, not the reverse), so its downstream count is 0.
        # Pin the exact value: a regression to None/str/negative must go red.
        assert isinstance(result["downstream_count"], int)
        assert result["downstream_count"] == 0


class TestRiskComputation:
    def test_safe_with_no_risk_factors(self):
        risk, factors = _compute_risk(
            forward_count=0,
            dep_count=2,
            health_grade="A",
            has_tests=True,
            edit_type="fix_bug",
            is_init_file=False,
        )
        assert risk == "safe"
        good_factors = [f for f in factors if f["severity"] == "good"]
        assert len(good_factors) == 1

    def test_caution_with_moderate_downstream(self):
        risk, factors = _compute_risk(
            forward_count=8,
            dep_count=5,
            health_grade="C",
            has_tests=False,
            edit_type="refactor",
            is_init_file=False,
        )
        assert risk in ("caution", "dangerous")

    def test_dangerous_with_high_downstream_no_tests(self):
        risk, factors = _compute_risk(
            forward_count=30,
            dep_count=15,
            health_grade="D",
            has_tests=False,
            edit_type="rename",
            is_init_file=True,
        )
        assert risk == "dangerous"

    def test_rename_adds_risk_factor(self):
        _, factors_refactor = _compute_risk(
            forward_count=3,
            dep_count=2,
            health_grade="A",
            has_tests=True,
            edit_type="refactor",
            is_init_file=False,
        )
        _, factors_rename = _compute_risk(
            forward_count=3,
            dep_count=2,
            health_grade="A",
            has_tests=True,
            edit_type="rename",
            is_init_file=False,
        )
        rename_risk_factors = [
            f for f in factors_rename if f["factor"] == "rename_risk"
        ]
        assert len(rename_risk_factors) == 1

    def test_init_file_flagged(self):
        risk, factors = _compute_risk(
            forward_count=0,
            dep_count=0,
            health_grade="A",
            has_tests=True,
            edit_type="fix_bug",
            is_init_file=True,
        )
        init_factors = [f for f in factors if f["factor"] == "init_file"]
        assert len(init_factors) == 1


class TestHelperFunctions:
    def test_is_init_file_true(self):
        assert _is_init_file("src/__init__.py")

    def test_is_init_file_false(self):
        assert not _is_init_file("src/main.py")

    def test_find_test_files_for_known_file(self):
        tests = find_test_files(
            str(PROJECT_ROOT / "tree_sitter_analyzer" / "health_scorer.py"),
            str(PROJECT_ROOT),
        )
        assert isinstance(tests, list)


# ---------------------------------------------------------------------------
# Issue #641 — pre_edit_checklist numbering must be sequential (no gap)
# ---------------------------------------------------------------------------


class TestChecklistSequentialNumbering:
    """build_checklist must emit 1, 2, 3, 4, ... without skipping any number.

    Bug: when downstream_count == 0, item 4 is absent but items for
    rename/refactor/health were hardcoded as 5/6. This left gaps like
    [1, 2, 3, 5] in the rendered checklist.
    """

    def _checklist(self, **kwargs):
        from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_risk import (
            build_checklist,
        )

        return build_checklist(**kwargs)

    def test_rename_no_downstream_sequential(self):
        """rename + 0 downstream: must be [1, 2, 3, 4], not [1, 2, 3, 5]."""
        items = self._checklist(
            risk="safe",
            downstream_count=0,
            has_tests=True,
            test_files=["tests/test_foo.py"],
            edit_type="rename",
        )
        numbers = [item.split(".")[0] for item in items]
        assert numbers == ["1", "2", "3", "4"]

    def test_refactor_no_downstream_sequential(self):
        """refactor + 0 downstream: must be [1, 2, 3, 4], not [1, 2, 3, 5]."""
        items = self._checklist(
            risk="safe",
            downstream_count=0,
            has_tests=True,
            test_files=["tests/test_foo.py"],
            edit_type="refactor",
        )
        numbers = [item.split(".")[0] for item in items]
        assert numbers == ["1", "2", "3", "4"]

    def test_rename_with_downstream_sequential(self):
        """rename + 2 downstream: must be [1, 2, 3, 4, 5]."""
        items = self._checklist(
            risk="safe",
            downstream_count=2,
            has_tests=True,
            test_files=["tests/test_foo.py"],
            edit_type="rename",
        )
        numbers = [item.split(".")[0] for item in items]
        assert numbers == ["1", "2", "3", "4", "5"]

    def test_health_grade_no_downstream_sequential(self):
        """poor health (D) + 0 downstream + no edit_type addon: [1, 2, 3, 4]."""
        items = self._checklist(
            risk="caution",
            downstream_count=0,
            has_tests=False,
            test_files=[],
            edit_type="fix_bug",
            health_grade="D",
            file_path="src/foo.py",
        )
        numbers = [item.split(".")[0] for item in items]
        assert numbers == ["1", "2", "3", "4"]

    def test_rename_downstream_and_health_sequential(self):
        """rename + downstream + poor health: [1, 2, 3, 4, 5, 6]."""
        items = self._checklist(
            risk="caution",
            downstream_count=3,
            has_tests=True,
            test_files=["tests/test_foo.py"],
            edit_type="rename",
            health_grade="D",
            file_path="src/foo.py",
        )
        numbers = [item.split(".")[0] for item in items]
        assert numbers == ["1", "2", "3", "4", "5", "6"]


@pytest.mark.asyncio
async def test_edit_safe_explicit_read_existing_honors_compact_only(
    tmp_path,
) -> None:
    import sys

    file_path = tmp_path / "inside.py"
    file_path.write_text("value = 1\n")
    result = await build_edit_facade(str(tmp_path)).execute(
        {
            "action": "safe",
            "file_path": "inside.py",
            "access_mode": "read_existing",
            "snapshot_id": "idxsnap_test",
            "source_generation": "idxsrc-v3:test",
            "output_format": "toon",
            "compact_only": True,
        }
    )

    if sys.platform.startswith("linux"):
        # RFC-0022 P0.4: the certified backend runs and classifies the
        # missing snapshot; the classified failure keeps the same TOON
        # control surface and the wire-owner echo.
        assert result["format"] == "toon"
        assert "INDEX_SNAPSHOT_UNKNOWN" in result["toon_content"]
        assert {
            key: result[key]
            for key in (
                "success",
                "verdict",
                "access_mode",
                "access_state",
                "access_reason",
                "output_format",
                "action_version",
            )
        } == {
            "success": False,
            "verdict": "ERROR",
            "access_mode": "read_existing",
            "access_state": "unknown",
            "access_reason": "INDEX_SNAPSHOT_UNKNOWN",
            "output_format": "toon",
            "action_version": "edit.safe/v1",
        }
        return

    assert result == {
        "format": "toon",
        "toon_content": (
            "success: true\n"
            "verdict: WARN\n"
            "access_mode: read_existing\n"
            "access_state: unknown\n"
            "access_reason: READ_EXISTING_AUTHORITY_UNCERTIFIED\n"
            "source_snapshots: []\n"
            "output_format: toon\n"
            # RFC-0022 P0.5: wire owner echo in the TOON control surface.
            "action_version: edit.safe/v1"
        ),
        "success": True,
        "verdict": "WARN",
        "access_mode": "read_existing",
        "access_state": "unknown",
        "access_reason": "READ_EXISTING_AUTHORITY_UNCERTIFIED",
        "output_format": "toon",
        # RFC-0022 P0.5: wire owner echo on the envelope.
        "action_version": "edit.safe/v1",
    }


@pytest.mark.asyncio
async def test_read_existing_rejects_traversal_before_unavailable(tmp_path):
    tool = SafeToEditTool(str(tmp_path))

    with pytest.raises(
        ValueError,
        match=r"^Invalid file path: Security validation failed:",
    ):
        await tool.execute(
            {
                "file_path": "../outside.py",
                "access_mode": "read_existing",
                "snapshot_id": "idxsnap_test",
                "source_generation": "idxsrc-v3:test",
                "output_format": "json",
            }
        )


def test_execute_read_existing_fails_closed_without_project_root() -> None:
    # Codex P1 (#1257): with project_root unbound, resolve_and_validate_
    # file_path would pass base_path=None into SecurityValidator and skip
    # the project-boundary layer; the read_existing route must fail closed
    # with the stable MISSING_PROJECT_ROOT error. Review P2 (#1299): the
    # failure is a classified envelope (evidence + action_version), not a
    # bare raise.
    tool = SafeToEditTool()  # no project root bound
    result = _run(
        tool.execute(
            {
                "file_path": "src/app.py",
                "access_mode": "read_existing",
                "snapshot_id": "snap-1",
                "source_generation": "1",
            }
        )
    )
    assert result["success"] is False
    assert result["error_code"] == "MISSING_PROJECT_ROOT"
    assert result["access_reason"] == "MISSING_PROJECT_ROOT"
    assert result["access_state"] == "missing"
    assert result["action_version"] == "edit.safe/v1"
    assert result["source_snapshots"] == []


# ---------------------------------------------------------------------------
# RFC-0022 P0.4: certified-axis index-snapshot consumers (portable gate open)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _close_index_snapshot_registry():
    yield
    from tree_sitter_analyzer.index_snapshot import REGISTRY

    REGISTRY.close_all()


def _indexed_project(tmp_path: Path) -> Path:
    """Index one small project and return its resolved root."""
    from tree_sitter_analyzer.ast_cache import ASTCache

    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.py").write_text(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "class UserService:\n"
        "    def get_user(self, user_id):\n"
        "        return self._find_user(user_id)\n"
        "\n"
        "    def _find_user(self, user_id):\n"
        "        return {'id': user_id}\n",
        encoding="utf-8",
    )
    (project / "routes.py").write_text(
        "from app import UserService\n"
        "\n"
        "def dispatch(request):\n"
        "    return UserService().get_user(1)\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(project))
    cache.index_project(max_files=20)
    cache.close()
    return project.resolve()


def _publish_index_snapshot(project: Path, *, source_generation: str | None = None):
    """Publish one real index.db connection under the process-global registry.

    The published capability carries the REAL captured source generation and
    a full source scope so the consumer's after-read recapture passes: a
    hand-faked generation would raise SOURCE_GENERATION_MISMATCH on exit.
    """
    import sqlite3

    from tree_sitter_analyzer.index_snapshot import (
        REGISTRY,
        IndexSnapshot,
        _capture_sources_with_deadline,
    )
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    scope = make_source_scope_descriptor()
    current = _capture_sources_with_deadline(str(project), scope, deadline=10**18)
    assert current.state == "exact", current.reason
    conn = sqlite3.connect(str(project / ".ast-cache" / "index.db"))
    conn.row_factory = sqlite3.Row
    snapshot = IndexSnapshot(
        None,
        current.fingerprint,
        "index-fp",
        source_generation or current.generation,
        "complete",
        None,
        str(project.resolve()),
        2,
        None,
        None,
        scope,
    )
    return REGISTRY.publish(snapshot, conn, 0)


@pytest.mark.slow_ok  # real git + index_project + source capture: subprocess work
@pytest.mark.skipif(
    sys.platform.startswith("win") or not os.path.exists("/dev/fd"),
    reason="tracked: RFC-0022 P0.4 source recapture needs POSIX /dev/fd",
)
@pytest.mark.asyncio
async def test_edit_safe_read_existing_consumes_published_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The certified backend serves the risk envelope from the snapshot."""
    import tree_sitter_analyzer.read_existing_access as read_access

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    project = _indexed_project(tmp_path)
    published = _publish_index_snapshot(project)

    tool = SafeToEditTool(str(project))
    result = await tool.execute(
        {
            "file_path": "app.py",
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": published.source_generation,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert result["access_mode"] == "read_existing"
    assert result["access_state"] == "available"
    assert result["access_reason"] is None
    assert result["source_snapshots"] == [
        {
            "kind": "index",
            "snapshot_id": published.snapshot_id,
            "source_generation": published.source_generation,
        }
    ]
    # The echo must come from the ACQUIRED snapshot, byte-matching the
    # source_snapshots record (RFC-0022 route-table common rule 5).
    assert result["snapshot_id"] == published.snapshot_id
    assert result["source_generation"] == published.source_generation
    assert result["action_version"] == "edit.safe/v1"
    assert result["risk_level"] in {"safe", "caution", "dangerous"}
    assert result["health_grade"]


def test_certified_commands_use_extension_runner(tmp_path: Path) -> None:
    """Codex P2 round-7 (C32): the certified runner is inferred from the
    target extension, never forced to pytest."""
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        AgentWorkflowContext,
        build_agent_workflow,
    )

    go_workflow = build_agent_workflow(
        AgentWorkflowContext(
            file_path="handler.go",
            risk="safe",
            edit_type="refactor",
            has_tests=True,
            test_files=["handler_test.go"],
            health_grade="A",
            project_root=str(tmp_path),
            certified=True,
        )
    )
    assert "go test" in str(go_workflow.get("after_edit_commands", []))

    java_workflow = build_agent_workflow(
        AgentWorkflowContext(
            file_path="Calc.java",
            risk="safe",
            edit_type="refactor",
            has_tests=True,
            test_files=["CalcTest.java"],
            health_grade="A",
            project_root=str(tmp_path),
            certified=True,
        )
    )
    # C35: ambiguous ecosystems omit the command rather than guess.
    assert "mvn test" not in str(java_workflow.get("after_edit_commands", []))
    assert "go test" not in str(java_workflow.get("after_edit_commands", []))
    # C41: the queue-boundary list stays empty, never [""].
    assert java_workflow.get("queue_boundary_commands") == []
    # C41: the queue-boundary list stays empty, never [""].
    assert java_workflow.get("queue_boundary_commands") == []

    rust_workflow = build_agent_workflow(
        AgentWorkflowContext(
            file_path="lib.rs",
            risk="safe",
            edit_type="refactor",
            has_tests=True,
            test_files=["tests/lib_test.rs"],
            health_grade="A",
            project_root=str(tmp_path),
            certified=True,
        )
    )
    assert "cargo test" in str(rust_workflow.get("after_edit_commands", []))

    js_workflow = build_agent_workflow(
        AgentWorkflowContext(
            file_path="app.js",
            risk="safe",
            edit_type="refactor",
            has_tests=True,
            test_files=["__tests__/app.test.js"],
            health_grade="A",
            project_root=str(tmp_path),
            certified=True,
        )
    )
    # C39: JS/TS npm-vs-pnpm-vs-Yarn cannot be distinguished snapshot-bound.
    assert "npm test" not in str(js_workflow.get("after_edit_commands", []))

    py_workflow = build_agent_workflow(
        AgentWorkflowContext(
            file_path="app.py",
            risk="safe",
            edit_type="refactor",
            has_tests=True,
            test_files=["tests/test_app.py"],
            health_grade="A",
            project_root=str(tmp_path),
            certified=True,
        )
    )
    assert "uv run pytest" in str(py_workflow.get("after_edit_commands", []))


def test_certified_commands_ignore_live_config_files(tmp_path: Path) -> None:
    """Codex P2 round-6 (C28): certified checklists/workflows use the
    analyzer's pytest default, never live non-inventoried config files."""
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        AgentWorkflowContext,
        build_agent_workflow,
    )
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_risk import (
        build_checklist,
    )

    (tmp_path / "package.json").write_text('{"scripts": {"test": "node test"}}')
    live_workflow = build_agent_workflow(
        AgentWorkflowContext(
            file_path="app.py",
            risk="safe",
            edit_type="refactor",
            has_tests=True,
            test_files=["tests/test_app.py"],
            health_grade="A",
            project_root=str(tmp_path),
        )
    )
    assert "npm test" in str(live_workflow.get("after_edit_commands", []))

    certified_workflow = build_agent_workflow(
        AgentWorkflowContext(
            file_path="app.py",
            risk="safe",
            edit_type="refactor",
            has_tests=True,
            test_files=["tests/test_app.py"],
            health_grade="A",
            project_root=str(tmp_path),
            certified=True,
        )
    )
    assert "npm test" not in str(certified_workflow.get("after_edit_commands", []))
    assert "uv run pytest" in str(certified_workflow.get("after_edit_commands", []))

    certified_checklist = build_checklist(
        "safe",
        0,
        False,
        [],
        "refactor",
        project_root=str(tmp_path),
        certified=True,
    )
    assert all("npm test" not in item for item in certified_checklist)

    # C35: ambiguous ecosystem + no tests -> the checklist omits the
    # command items entirely instead of advertising an unverifiable runner.
    no_command = build_checklist(
        "safe",
        0,
        False,
        [],
        "refactor",
        file_path="Calc.java",
        project_root=str(tmp_path),
        certified=True,
    )
    assert all("command" not in item.lower() for item in no_command)

    # C35: ambiguous ecosystem + tests -> the test items still appear,
    # but without an advertised command.
    java_tests = build_checklist(
        "safe",
        0,
        True,
        ["CalcTest.java"],
        "refactor",
        file_path="Calc.java",
        project_root=str(tmp_path),
        certified=True,
    )
    assert any("Run existing tests FIRST" in item for item in java_tests)
    assert all(
        "java" not in item.lower() and "mvn" not in item.lower() for item in java_tests
    )

    # Certified python + tests -> the pytest command items are present.
    py_tests = build_checklist(
        "safe",
        0,
        True,
        ["tests/test_app.py"],
        "refactor",
        file_path="app.py",
        project_root=str(tmp_path),
        certified=True,
    )
    assert any("uv run pytest" in item for item in py_tests)


def test_live_violations_query_degrades_on_corrupt_db_file(
    tmp_path: Path,
) -> None:
    """A non-SQLite index.db degrades to an empty violation list."""
    from tree_sitter_analyzer.mcp.tools.utils.constraint_violation_query import (
        violations_for_files,
    )

    (tmp_path / ".ast-cache").mkdir()
    (tmp_path / ".ast-cache" / "index.db").write_text(
        "not-a-sqlite-database", encoding="utf-8"
    )
    assert violations_for_files(str(tmp_path), ["app.py"]) == []


def test_snapshot_dependency_view_degrades_on_closed_conn() -> None:
    """An unreadable connection degrades to an empty view, never raises."""
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
    )

    conn = sqlite3.connect(":memory:")
    conn.close()
    view = build_snapshot_file_dependency_view(conn, "app.py")
    assert view.dependents_of("app.py") == []
    assert view.dependencies_of("app.py") == []


def test_read_existing_payload_missing_indexed_file_returns_not_found(
    tmp_path: Path,
) -> None:
    """An indexed target missing at read time still answers FILE_NOT_FOUND.

    Codex P1 round-4 (C19): the inventory gate passes (the file IS in
    ast_index), then the existence probe answers from the filesystem.
    """
    import sqlite3
    from types import SimpleNamespace

    from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE ast_index (file_path TEXT)")
    conn.execute("INSERT INTO ast_index VALUES ('app.py')")
    tool = SafeToEditTool(str(tmp_path))
    with pytest.raises(ValueError, match="FILE_NOT_FOUND"):
        tool._read_existing_payload(
            {"file_path": "app.py", "edit_type": "refactor"},
            str(tmp_path / "app.py"),
            conn,
            snapshot=SimpleNamespace(canonical_root=str(tmp_path.resolve())),
        )


def test_read_existing_payload_language_detection_degrades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A detector failure on the snapshot route degrades to no language key.

    Codex-review P3 (#1299): language detection is best-effort — an
    exception must yield a language-less result, never a crash.
    """
    import sqlite3
    from types import SimpleNamespace

    import tree_sitter_analyzer.mcp.tools.safe_to_edit_tool as tool_module

    target = tmp_path / "app.py"
    target.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        tool_module,
        "_syntax_error_response",
        lambda resolved, file_path, edit_type: None,
    )

    def boom(*args, **kwargs):
        raise RuntimeError("detector down")

    monkeypatch.setattr(
        "tree_sitter_analyzer.language_detector.detect_language_from_file", boom
    )
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # The FILE_NOT_INDEXED gate needs the target present in ast_index.
    conn.execute("CREATE TABLE ast_index (file_path TEXT)")
    conn.execute("INSERT INTO ast_index VALUES ('app.py')")
    tool = tool_module.SafeToEditTool(str(tmp_path))
    result = tool._read_existing_payload(
        {"file_path": "app.py", "edit_type": "refactor"},
        str(target),
        conn,
        snapshot=SimpleNamespace(canonical_root=str(tmp_path)),
    )
    assert result["success"] is True
    assert "language" not in result


def test_snapshot_constraint_query_reads_from_given_conn() -> None:
    """The conn variant returns rows and degrades to [] on a missing table."""
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.constraint_violation_query import (
        violations_for_files_from_conn,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_constraint_violations ("
        "rule_id TEXT NOT NULL, caller_file TEXT NOT NULL, "
        "caller_name TEXT NOT NULL, caller_line INTEGER NOT NULL, "
        "callee_name TEXT NOT NULL, callee_file TEXT NOT NULL DEFAULT '', "
        "severity TEXT NOT NULL, detected_at INTEGER NOT NULL)"
    )
    conn.execute(
        "INSERT INTO ast_constraint_violations VALUES "
        "('R1', 'app.py', 'app', 1, 'secret', '', 'error', 1)"
    )
    rows = violations_for_files_from_conn(conn, ["app.py"])
    assert rows == [
        {
            "rule_id": "R1",
            "caller_file": "app.py",
            "caller_name": "app",
            "caller_line": 1,
            "callee_name": "secret",
            "callee_file": "",
            "severity": "error",
            "detected_at": 1,
            "factor": "constraint_violation",
        }
    ]
    assert violations_for_files_from_conn(conn, []) == []
    bare = sqlite3.connect(":memory:")
    assert violations_for_files_from_conn(bare, ["app.py"]) == []


def test_format_result_reads_constraints_from_snapshot_conn(
    tmp_path: Path,
) -> None:
    """Snapshot-mode formatting ignores rows that cannot prove freshness."""
    import sqlite3
    from types import SimpleNamespace

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        SafeToEditContext,
        SafeToEditFacts,
        _format_safe_to_edit_result,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_constraint_violations ("
        "rule_id TEXT NOT NULL, caller_file TEXT NOT NULL, "
        "caller_name TEXT NOT NULL, caller_line INTEGER NOT NULL, "
        "callee_name TEXT NOT NULL, callee_file TEXT NOT NULL DEFAULT '', "
        "severity TEXT NOT NULL, detected_at INTEGER NOT NULL)"
    )
    conn.execute(
        "INSERT INTO ast_constraint_violations VALUES "
        "('R1', 'app.py', 'app', 1, 'secret', '', 'error', 1)"
    )
    health = SimpleNamespace(grade="A", total=95, dimensions={})
    facts = SafeToEditFacts(
        dependents=[],
        dependencies=[],
        health=health,
        test_files=[],
        has_tests=False,
        risk="safe",
        risk_factors=[],
        pre_edit_checklist=[],
    )
    context = SafeToEditContext(
        file_path="app.py",
        edit_type="refactor",
        resolved_path=str(tmp_path / "app.py"),
        project_root=str(tmp_path),
        graph=None,
        scorer=None,
        snapshot_conn=conn,
    )
    result = _format_safe_to_edit_result(context, facts)
    # C21: the seeded error row is unbound to the snapshot generation and
    # must not escalate the verdict.
    assert result["verdict"] == "SAFE"
    assert not any(
        factor.get("factor") == "constraint_violation"
        for factor in result["risk_factors"]
    )


@pytest.mark.slow_ok  # real git + index_project + source capture: subprocess work
@pytest.mark.skipif(
    sys.platform.startswith("win") or not os.path.exists("/dev/fd"),
    reason="tracked: RFC-0022 P0.4 source recapture needs POSIX /dev/fd",
)
@pytest.mark.asyncio
async def test_edit_safe_read_existing_ignores_unbound_constraint_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unbound constraint rows never escalate; the certified read stays zero-write.

    Codex P1 (#1299 round-4, C21): reindexing stamps the manifest without
    recomputing ast_constraint_violations, so the rows cannot prove they
    match the published generation — the certified route must NOT promote
    UNSAFE from them. The route also never creates
    ``.ast-cache/fixture_index.json`` (zero-write read).
    """
    import sqlite3

    import tree_sitter_analyzer.read_existing_access as read_access
    from tree_sitter_analyzer.index_snapshot import (
        REGISTRY,
        IndexSnapshot,
        _capture_sources_with_deadline,
    )
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    project = _indexed_project(tmp_path)
    scope = make_source_scope_descriptor()
    current = _capture_sources_with_deadline(str(project), scope, deadline=10**18)
    assert current.state == "exact", current.reason
    conn = sqlite3.connect(str(project / ".ast-cache" / "index.db"))
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO ast_constraint_violations VALUES "
        "('R1', 'app.py', 'app', 1, 'secret', '', 'error', 1)"
    )
    conn.commit()
    snapshot = IndexSnapshot(
        None,
        current.fingerprint,
        "index-fp",
        current.generation,
        "complete",
        None,
        str(project.resolve()),
        2,
        None,
        None,
        scope,
    )
    published = REGISTRY.publish(snapshot, conn, 0)

    tool = SafeToEditTool(str(project))
    result = await tool.execute(
        {
            "file_path": "app.py",
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": published.source_generation,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert result["access_state"] == "available"
    # The seeded error-severity row must NOT escalate: it cannot prove it
    # belongs to the published generation (C21). The CAUTION verdict comes
    # from the snapshot dependency view (routes.py imports app.py), never
    # from constraint rows.
    assert result["verdict"] == "CAUTION"
    assert result["downstream_count"] == 1
    assert not any(
        factor.get("factor") == "constraint_violation"
        for factor in result["risk_factors"]
    )
    # Zero-write: the certified read never persisted a fixture index.
    assert not (project / ".ast-cache" / "fixture_index.json").exists()


@pytest.mark.slow_ok  # real git + index_project + source capture: subprocess work
@pytest.mark.skipif(
    sys.platform.startswith("win") or not os.path.exists("/dev/fd"),
    reason="tracked: RFC-0022 P0.4 source recapture needs POSIX /dev/fd",
)
@pytest.mark.asyncio
async def test_edit_safe_read_existing_unindexed_target_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A target outside the snapshot inventory is never served uncertified.

    Codex P1 (#1299): hidden/excluded files are not covered by the source
    recaptures, so the certified route rejects them with FILE_NOT_INDEXED
    instead of reading and scoring their live bytes.
    """
    import tree_sitter_analyzer.read_existing_access as read_access

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    project = _indexed_project(tmp_path)
    # Broken syntax on purpose (Codex P1 round-3): the inventory gate must
    # run BEFORE the syntax probe, so a broken out-of-inventory file can
    # never short-circuit into a syntax-error success envelope.
    (project / ".hidden.py").write_text("def broken(:\n", encoding="utf-8")
    published = _publish_index_snapshot(project)

    tool = SafeToEditTool(str(project))
    result = await tool.execute(
        {
            "file_path": ".hidden.py",
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": published.source_generation,
            "output_format": "json",
        }
    )

    assert result["success"] is False
    assert result["error_code"] == "FILE_NOT_INDEXED"
    assert result["access_reason"] == "FILE_NOT_INDEXED"
    assert result["action_version"] == "edit.safe/v1"
    assert result["source_snapshots"] == [
        {
            "kind": "index",
            "snapshot_id": published.snapshot_id,
            "source_generation": published.source_generation,
        }
    ]


@pytest.mark.slow_ok  # real git + index_project + source capture: subprocess work
@pytest.mark.skipif(
    sys.platform.startswith("win") or not os.path.exists("/dev/fd"),
    reason="tracked: RFC-0022 P0.4 source recapture needs POSIX /dev/fd",
)
@pytest.mark.asyncio
async def test_edit_safe_read_existing_generation_mismatch_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wrong source_generation token classifies, never a successful read."""
    import tree_sitter_analyzer.read_existing_access as read_access

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    project = _indexed_project(tmp_path)
    published = _publish_index_snapshot(project)

    tool = SafeToEditTool(str(project))
    result = await tool.execute(
        {
            "file_path": "app.py",
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": "WRONG-GENERATION",
            "output_format": "json",
        }
    )

    assert result["success"] is False
    assert result["access_state"] == "unknown"
    assert result["access_reason"] == "SOURCE_GENERATION_MISMATCH"
    assert result["error_code"] == "SOURCE_GENERATION_MISMATCH"
    assert result["source_snapshots"] == []
    assert result["action_version"] == "edit.safe/v1"


# RFC-0022 P0.4: the snapshot dependency view degrades to an empty view on
# schema drift (legacy connection without the edges/ast_index tables) so the
# route still classifies honestly instead of crashing.
def test_snapshot_dependency_view_degrades_on_schema_drift() -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
        snapshot_inventory,
    )

    conn = sqlite3.connect(":memory:")
    view = build_snapshot_file_dependency_view(conn, "app.py")
    assert view.dependents_of("app.py") == []
    assert view.dependencies_of("app.py") == []
    # An unreadable inventory degrades to the empty set (fail-closed).
    assert snapshot_inventory(conn) == frozenset()

    # edges present but ast_index absent: exact resolution probes the missing
    # table and degrades to not-indexed.
    conn.execute("CREATE TABLE edges (file_path TEXT, callee_name TEXT, kind TEXT)")
    conn.execute("INSERT INTO edges VALUES ('routes.py', 'app', 'imports')")
    partial = build_snapshot_file_dependency_view(conn, "app.py")
    assert partial.dependents_of("app.py") == []

    # Codex P2 (#1299): a current-version but damaged edges table (present,
    # missing the callee_name column this reader selects) fails the route
    # instead of silently degrading to an empty view (which would undercount
    # risk).
    import pytest

    damaged = sqlite3.connect(":memory:")
    damaged.row_factory = sqlite3.Row
    damaged.execute(
        "CREATE TABLE edges (source_node_id TEXT, target_node_id TEXT, "
        "kind TEXT, file_path TEXT)"
    )
    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        build_snapshot_file_dependency_view(damaged, "app.py")


# RFC-0022 P0.4: the snapshot dependency view resolves exact IMPORTS edges
# AND recalls member imports via the imports_json needle pass, matching the
# legacy live axis ('from pkg import app' / 'from . import app').
def test_snapshot_dependency_view_recalls_member_imports() -> None:
    import json
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE edges (file_path TEXT, callee_name TEXT, kind TEXT)")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.execute("INSERT INTO edges VALUES ('routes.py', 'app', 'imports')")
    # C44: a BLOB callee_name row must not abort the whole edges pass.
    conn.execute(
        "INSERT INTO edges VALUES ('blobbed.py', ?, 'imports')", (b"blob-module",)
    )
    # The target's OWN import row can also carry a BLOB (pass-1 skip).
    conn.execute("INSERT INTO edges VALUES ('app.py', ?, 'imports')", (b"blob-own",))
    conn.execute("INSERT INTO edges VALUES ('app.py', 'app', 'imports')")
    # 'app.py' importing a module that does not index -> resolved is None.
    conn.execute("INSERT INTO edges VALUES ('app.py', 'missing.mod', 'imports')")
    # Relative import spec ('.sibling') exercises the relative branch.
    conn.execute("INSERT INTO edges VALUES ('pkg/app.py', '.sibling', 'imports')")
    # Parent-relative spec ('..') is rejected outright.
    conn.execute("INSERT INTO edges VALUES ('pkg/app.py', '..up', 'imports')")
    conn.execute(
        "INSERT INTO ast_index VALUES ('routes.py', ?)",
        (json.dumps([{"text": "from app import UserService", "line": 1}]),),
    )
    conn.execute(
        "INSERT INTO ast_index VALUES ('unrelated.py', ?)",
        (json.dumps([{"text": "import os", "line": 1}]),),
    )
    conn.execute(
        "INSERT INTO ast_index VALUES ('odd.py', ?)",
        (json.dumps([{"text": 123, "line": 1}]),),
    )
    conn.execute(
        "INSERT INTO ast_index VALUES ('app.py', ?)",
        (json.dumps([{"text": "import os", "line": 1}]),),
    )
    conn.execute("INSERT INTO ast_index VALUES ('broken.py', 'not-json')")
    # C40: a valid-JSON non-array cell (42) must be skipped per row, NOT
    # abort the whole needle pass — the later matching row still counts.
    conn.execute("INSERT INTO ast_index VALUES ('scalar.py', '42')")
    conn.execute(
        "INSERT INTO ast_index VALUES ('later.py', ?)",
        (json.dumps([{"text": "from app import Member", "line": 1}]),),
    )
    view = build_snapshot_file_dependency_view(conn, "app.py")
    # 'routes.py' matches the needle pass; 'unrelated.py' exercises the
    # non-match branch (no dependent added); 'later.py' proves the pass
    # survived the malformed 'scalar.py' row.
    assert view.dependents_of("app.py") == ["later.py", "routes.py"]


@pytest.mark.slow_ok  # real git + index_project + source capture: subprocess work
@pytest.mark.skipif(
    sys.platform.startswith("win") or not os.path.exists("/dev/fd"),
    reason="tracked: RFC-0022 P0.4 source recapture needs POSIX /dev/fd",
)
@pytest.mark.asyncio
async def test_edit_safe_read_existing_syntax_error_short_circuits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken file short-circuits the snapshot route like the legacy axis."""
    import tree_sitter_analyzer.read_existing_access as read_access

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    project = _indexed_project(tmp_path)
    (project / "app.py").write_text("def broken(:\n", encoding="utf-8")
    published = _publish_index_snapshot(project)

    tool = SafeToEditTool(str(project))
    result = await tool.execute(
        {
            "file_path": "app.py",
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": published.source_generation,
            "output_format": "json",
        }
    )
    assert result["success"] is True
    assert result["verdict"] == "ERROR"
    assert result["access_state"] == "available"
    assert result["source_snapshots"] == [
        {
            "kind": "index",
            "snapshot_id": published.snapshot_id,
            "source_generation": published.source_generation,
        }
    ]


@pytest.mark.slow_ok  # real git + index_project + source capture: subprocess work
@pytest.mark.skipif(
    sys.platform.startswith("win") or not os.path.exists("/dev/fd"),
    reason="tracked: RFC-0022 P0.4 source recapture needs POSIX /dev/fd",
)
@pytest.mark.asyncio
async def test_edit_safe_read_existing_missing_file_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing target fails closed on the snapshot route.

    Codex P1 round-4 (C19): the inventory gate precedes every live-filesystem
    probe — a file the snapshot never indexed (missing or not) is answered
    from the snapshot with FILE_NOT_INDEXED, never from uncertified disk
    state. (An indexed-but-deleted file surfaces as SOURCE_GENERATION_MISMATCH
    in the pre-read recapture instead.)
    """
    import tree_sitter_analyzer.read_existing_access as read_access

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    project = _indexed_project(tmp_path)
    published = _publish_index_snapshot(project)

    tool = SafeToEditTool(str(project))
    result = await tool.execute(
        {
            "file_path": "does_not_exist.py",
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": published.source_generation,
            "output_format": "json",
        }
    )
    assert result["success"] is False
    assert result["error_code"] == "FILE_NOT_INDEXED"
    assert result["access_reason"] == "FILE_NOT_INDEXED"
    assert result["access_state"] == "unknown"
    assert result["action_version"] == "edit.safe/v1"
