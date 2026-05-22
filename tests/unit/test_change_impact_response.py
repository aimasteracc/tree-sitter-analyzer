"""Unit tests for mcp/tools/utils/change_impact_response — response assembly."""

from tree_sitter_analyzer.mcp.tools.utils.change_impact_response import (
    AgentSummaryContext,
    ChangeImpactResponseContext,
    attach_queue_ledger,
    build_agent_summary,
    build_agent_summary_only_response,
    build_change_impact_response,
    build_no_changes_result,
)


def _make_verification(**overrides):
    return {
        "test_required": True,
        "test_runner": "pytest",
        "default_test_command": "pytest",
        "pytest_required": True,
        "pytest_command": "pytest -x",
        "test_command": "pytest -x",
        "verification_command": "pytest -x",
        "verification_reason": "changed files detected",
        **overrides,
    }


def _make_strategy(**overrides):
    return {
        "focused_test_command": "pytest tests/unit/test_foo.py",
        "verification_strategy": "focused",
        "verification_steps": ["pytest tests/unit/test_foo.py"],
        "verification_hint": "Run focused test first",
        **overrides,
    }


class TestBuildNoChangesResult:
    """Tests for build_no_changes_result."""

    def test_basic_no_changes(self):
        result = build_no_changes_result("diff")
        assert result["success"] is True
        assert result["changed_files"] == []
        assert result["agent_summary"]["risk"] == "none"
        assert result["agent_summary"]["changed_count"] == 0

    def test_scoped_mode(self):
        result = build_no_changes_result("diff", scope_paths=["src/"])
        assert result["agent_summary"]["scope"] == "scoped"

    def test_unscoped_mode(self):
        result = build_no_changes_result("diff")
        assert result["agent_summary"]["scope"] == "workspace"


class TestBuildAgentSummary:
    """Tests for build_agent_summary."""

    def test_basic_summary(self):
        ctx = AgentSummaryContext(
            risk="low",
            changed_files=["src/a.py", "src/b.py"],
            scope_paths=None,
            verification=_make_verification(),
            strategy=_make_strategy(),
            affected_count=3,
            tests_to_run_count=2,
        )
        summary = build_agent_summary(ctx)
        assert summary["risk"] == "low"
        assert summary["changed_count"] == 2
        assert summary["affected_count"] == 3
        assert summary["tests_to_run_count"] == 2
        assert "verification_command" in summary

    def test_changed_preview_limited_to_5(self):
        ctx = AgentSummaryContext(
            risk="high",
            changed_files=[f"file{i}.py" for i in range(10)],
            scope_paths=["src/"],
            verification=_make_verification(),
            strategy=_make_strategy(),
            affected_count=10,
            tests_to_run_count=5,
        )
        summary = build_agent_summary(ctx)
        assert len(summary["changed_preview"]) == 5

    def test_no_scope_hint_for_small_diff(self):
        ctx = AgentSummaryContext(
            risk="low",
            changed_files=["a.py"],
            scope_paths=None,
            verification=_make_verification(),
            strategy=_make_strategy(),
            affected_count=1,
            tests_to_run_count=1,
        )
        summary = build_agent_summary(ctx)
        assert "scope_hint" not in summary

    def test_scope_hint_for_large_unscoped_diff(self):
        ctx = AgentSummaryContext(
            risk="high",
            changed_files=[f"f{i}.py" for i in range(30)],
            scope_paths=None,
            verification=_make_verification(),
            strategy=_make_strategy(),
            affected_count=30,
            tests_to_run_count=10,
        )
        summary = build_agent_summary(ctx)
        assert "scope_hint" in summary
        assert "Large dirty" in summary["scope_hint"]

    def test_no_scope_hint_when_scoped(self):
        ctx = AgentSummaryContext(
            risk="high",
            changed_files=[f"f{i}.py" for i in range(30)],
            scope_paths=["src/"],
            verification=_make_verification(),
            strategy=_make_strategy(),
            affected_count=30,
            tests_to_run_count=10,
        )
        summary = build_agent_summary(ctx)
        assert "scope_hint" not in summary

    def test_focused_test_command_included(self):
        ctx = AgentSummaryContext(
            risk="low",
            changed_files=["a.py"],
            scope_paths=None,
            verification=_make_verification(),
            strategy=_make_strategy(focused_test_command="pytest test_a.py"),
            affected_count=1,
            tests_to_run_count=1,
        )
        summary = build_agent_summary(ctx)
        assert summary["focused_test_command"] == "pytest test_a.py"

    def test_next_step_with_focused_test(self):
        ctx = AgentSummaryContext(
            risk="low",
            changed_files=["a.py"],
            scope_paths=None,
            verification=_make_verification(verification_command="pytest"),
            strategy=_make_strategy(focused_test_command="pytest test_a.py"),
            affected_count=1,
            tests_to_run_count=1,
        )
        summary = build_agent_summary(ctx)
        assert "focused" in summary["next_step"].lower()

    def test_stop_condition_no_tests(self):
        ctx = AgentSummaryContext(
            risk="low",
            changed_files=["README.md"],
            scope_paths=None,
            verification=_make_verification(test_required=False),
            strategy=_make_strategy(),
            affected_count=0,
            tests_to_run_count=0,
        )
        summary = build_agent_summary(ctx)
        assert "docs-only" in summary["stop_condition"]


class TestBuildAgentSummaryOnlyResponse:
    """Tests for build_agent_summary_only_response."""

    def test_extracts_summary_fields(self):
        result = {
            "success": True,
            "mode": "diff",
            "scope_paths": ["src/"],
            "scope_filtered": True,
            "agent_summary": {
                "risk": "low",
                "changed_count": 2,
                "affected_count": 3,
                "tests_to_run_count": 1,
                "next_step": "Run tests",
                "stop_condition": "Tests pass",
            },
            "risk_level": "low",
            "changed_count": 2,
            "affected_count": 3,
            "tests_to_run_count": 1,
            "verification_command": "pytest",
        }
        response = build_agent_summary_only_response(result)
        assert response["agent_summary_only"] is True
        assert response["risk_level"] == "low"
        assert response["affected_count"] == 3
        assert response["next_step"] == "Run tests"


class TestAttachQueueLedger:
    """Tests for attach_queue_ledger."""

    def test_no_ledger_without_scope(self):
        result = {"success": True}
        out = attach_queue_ledger(
            result,
            mode="diff",
            scope_paths=None,
            scoped_changed_files=["a.py"],
            workspace_changed_files=["a.py", "b.py"],
        )
        assert "queue_ledger" not in out

    def test_ledger_with_scope(self):
        result = {"success": True, "verification_command": "pytest"}
        out = attach_queue_ledger(
            result,
            mode="diff",
            scope_paths=["src/"],
            scoped_changed_files=["src/a.py"],
            workspace_changed_files=["src/a.py", "tests/b.py"],
        )
        assert "queue_ledger" in out
        ledger = out["queue_ledger"]
        assert ledger["scoped_changed_count"] == 1
        assert ledger["out_of_scope_changed_count"] == 1
        assert "handoff" in ledger

    def test_preview_limited_to_5(self):
        result = {"success": True}
        out = attach_queue_ledger(
            result,
            mode="diff",
            scope_paths=["src/"],
            scoped_changed_files=[f"src/{i}.py" for i in range(10)],
            workspace_changed_files=[f"src/{i}.py" for i in range(10)],
        )
        assert len(out["queue_ledger"]["scoped_changed_preview"]) == 5

    def test_agent_summary_gets_scope_hint(self):
        result = {"success": True}
        out = attach_queue_ledger(
            result,
            mode="diff",
            scope_paths=["src/"],
            scoped_changed_files=["src/a.py"],
            workspace_changed_files=["src/a.py"],
        )
        assert "scope_hint" in out["agent_summary"]


class TestBuildChangeImpactResponse:
    """Tests for build_change_impact_response."""

    def test_full_response(self):
        import types

        request = types.SimpleNamespace(
            mode="diff",
            scope_paths=["src/"],
            changed_files=["src/a.py", "src/b.py"],
            diff_stat="+10 -5",
        )
        ctx = ChangeImpactResponseContext(
            request=request,
            risk="low",
            affected={"src/c.py", "src/d.py"},
            file_impacts=[{"file": "src/a.py", "impact": "direct"}],
            visible_tests=["test_a.py", "test_b.py"],
            all_tests=["test_a.py", "test_b.py", "test_c.py"],
            verification=_make_verification(),
            strategy=_make_strategy(),
            test_mapping={"src/a.py": ["test_a.py"]},
            agent_summary={"risk": "low"},
        )
        response = build_change_impact_response(ctx)
        assert response["success"] is True
        assert response["changed_count"] == 2
        assert response["affected_count"] == 2
        assert response["tests_to_run_count"] == 3
        assert response["tests_to_run_omitted_count"] == 1  # visible=2, all=3
        assert response["scope_filtered"] is True

    def test_empty_affected(self):
        import types

        request = types.SimpleNamespace(
            mode="diff",
            scope_paths=None,
            changed_files=["a.py"],
            diff_stat="",
        )
        ctx = ChangeImpactResponseContext(
            request=request,
            risk="none",
            affected=set(),
            file_impacts=[],
            visible_tests=[],
            all_tests=[],
            verification=_make_verification(test_required=False),
            strategy=_make_strategy(),
            test_mapping={},
            agent_summary={"risk": "none"},
        )
        response = build_change_impact_response(ctx)
        assert response["affected_files"] == []
