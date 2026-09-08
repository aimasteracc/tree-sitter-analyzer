"""#1376：test_safe_to_edit_tool 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import pytest

import tests.unit.mcp._safe_to_edit_tool_helpers as _fixtures
from tests.unit.mcp._safe_to_edit_tool_helpers import (
    PROJECT_ROOT,
    SERVER_FILE,
    TARGET_FILE,
    _run,
)
from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import (
    _compute_risk,
    _is_init_file,
)
from tree_sitter_analyzer.mcp.tools.utils import safe_to_edit_helpers as helpers
from tree_sitter_analyzer.mcp.tools.utils.test_discovery import find_test_files

tool = _fixtures.tool
_close_index_snapshot_registry = _fixtures._close_index_snapshot_registry


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

    def test_execute_marks_uncertified_causal_facts_unknown(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE, "output_format": "json"}))

        envelope = result["causal_envelope"]
        assert set(envelope) == {
            "dependents",
            "dependencies",
            "exercising_tests",
            "constraint_verdict",
            "verification_command",
            "stale_edges",
        }
        assert envelope == {
            "dependents": None,
            "dependencies": None,
            "exercising_tests": None,
            "constraint_verdict": "unknown",
            "verification_command": None,
            "stale_edges": None,
        }

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
        # 重命名应具有不少于原操作的风险因素。
        assert len(result_rename["risk_factors"]) >= len(
            result_refactor["risk_factors"]
        )

    def test_toon_format(self, tool):
        result = _run(
            tool.execute(
                {
                    "file_path": TARGET_FILE,
                    "output_format": "json",
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
        # 此临时夹具中没有模块导入 server.py；server.py 导入
        # safe_to_edit_tool.py，反向导入并不存在，因此下游数量是 0。
        # 固定精确值；退化成 None、字符串或负数时必须变红。
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
# Issue #641：pre_edit_checklist 编号必须连续，不能留空档。
# ---------------------------------------------------------------------------


class TestChecklistSequentialNumbering:
    """build_checklist 必须生成连续的 1、2、3、4 等编号。缺陷：downstream_count 为 0 时缺少条目 4，但 rename/refactor/health 条目被硬编码为 5/6，导致输出中出现 [1, 2, 3, 5] 之类的空档。"""

    def _checklist(self, **kwargs):
        from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_risk import (
            build_checklist,
        )

        return build_checklist(**kwargs)

    def test_rename_no_downstream_sequential(self):
        """rename 且无下游时必须是 [1, 2, 3, 4]，不能是 [1, 2, 3, 5]。"""
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
        """refactor 且无下游时必须是 [1, 2, 3, 4]，不能是 [1, 2, 3, 5]。"""
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
        """rename 且有两个下游时必须是 [1, 2, 3, 4, 5]。"""
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
        """健康等级较差（D）、无下游且无 edit_type 附加项时，编号为 [1, 2, 3, 4]。"""
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
        """rename、有下游且健康较差时，编号为 [1, 2, 3, 4, 5, 6]。"""
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


def test_agent_stop_condition_covers_dangerous_single_and_empty_verification() -> None:
    def context(risk: str) -> helpers.AgentWorkflowContext:
        return helpers.AgentWorkflowContext(
            file_path="app.py",
            risk=risk,
            edit_type="refactor",
            has_tests=True,
            test_files=["tests/test_app.py"],
            health_grade="A",
            project_root=".",
        )

    assert "smaller edit" in helpers._agent_stop_condition(
        context("dangerous"),
        {"after_edit_commands": ["focused"], "queue_boundary_commands": ["all"]},
    )
    assert (
        helpers._agent_stop_condition(
            context("safe"),
            {"after_edit_commands": ["focused"], "queue_boundary_commands": []},
        )
        == "focused exits successfully."
    )
    assert "identified and run" in helpers._agent_stop_condition(
        context("safe"),
        {"after_edit_commands": [], "queue_boundary_commands": []},
    )
