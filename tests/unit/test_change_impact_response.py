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

    def test_local_low_impact_summary_uses_local_command(self):
        ctx = AgentSummaryContext(
            risk="low",
            changed_files=["a.py"],
            scope_paths=None,
            verification=_make_verification(
                verification_command="uv run pytest -q",
                default_test_command="uv run pytest -q",
            ),
            strategy=_make_strategy(
                focused_test_command="uv run pytest tests/unit/test_a.py -q",
                low_impact_focused_test_command=(
                    "nice -n 15 uv run pytest tests/unit/test_a.py -n 2 -q"
                ),
                local_verification_command=(
                    "nice -n 15 uv run pytest tests/unit/test_a.py -n 2 -q"
                ),
                ci_verification_command="uv run pytest -q",
                resource_profile="local_low_impact",
                verification_strategy="local_low_impact_focused_then_ci",
                verification_steps=[
                    "nice -n 15 uv run pytest tests/unit/test_a.py -n 2 -q"
                ],
            ),
            affected_count=1,
            tests_to_run_count=1,
        )

        summary = build_agent_summary(ctx)

        assert summary["verification_command"] == (
            "nice -n 15 uv run pytest tests/unit/test_a.py -n 2 -q"
        )
        assert summary["local_verification_command"] == (
            "nice -n 15 uv run pytest tests/unit/test_a.py -n 2 -q"
        )
        assert summary["low_impact_focused_test_command"] == (
            "nice -n 15 uv run pytest tests/unit/test_a.py -n 2 -q"
        )
        assert summary["ci_verification_command"] == "uv run pytest -q"
        assert summary["resource_profile"] == "local_low_impact"
        assert "low-impact" in summary["next_step"]

    def test_local_low_impact_summary_without_ci_command(self):
        ctx = AgentSummaryContext(
            risk="low",
            changed_files=["a.py"],
            scope_paths=None,
            verification=_make_verification(
                verification_command="nice -n 15 pytest tests/unit/test_a.py -n 2 -q"
            ),
            strategy=_make_strategy(
                local_verification_command=(
                    "nice -n 15 pytest tests/unit/test_a.py -n 2 -q"
                ),
                verification_steps=["nice -n 15 pytest tests/unit/test_a.py -n 2 -q"],
            ),
            affected_count=1,
            tests_to_run_count=1,
        )

        summary = build_agent_summary(ctx)

        assert summary["next_step"] == (
            "Run low-impact local verification: "
            "nice -n 15 pytest tests/unit/test_a.py -n 2 -q"
        )
        assert summary["stop_condition"] == (
            "nice -n 15 pytest tests/unit/test_a.py -n 2 -q exits successfully locally."
        )

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

    def test_agent_summary_only_preserves_low_impact_fields(self):
        result = {
            "success": True,
            "mode": "diff",
            "scope_paths": [],
            "scope_filtered": False,
            "agent_summary": {
                "risk": "medium",
                "changed_count": 1,
                "affected_count": 2,
                "tests_to_run_count": 1,
                "next_step": "Run low-impact local verification",
                "verification_command": (
                    "nice -n 15 uv run pytest tests/unit/test_a.py -n 2 -q"
                ),
                "focused_test_command": "uv run pytest tests/unit/test_a.py -q",
                "low_impact_focused_test_command": (
                    "nice -n 15 uv run pytest tests/unit/test_a.py -n 2 -q"
                ),
                "local_verification_command": (
                    "nice -n 15 uv run pytest tests/unit/test_a.py -n 2 -q"
                ),
                "ci_verification_command": "uv run pytest -q",
                "resource_profile": "local_low_impact",
                "verification_strategy": "local_low_impact_focused_then_ci",
                "stop_condition": "low-impact local verification passes",
            },
            "risk_level": "medium",
            "changed_count": 1,
            "affected_count": 2,
            "tests_to_run_count": 1,
            "verification_command": (
                "nice -n 15 uv run pytest tests/unit/test_a.py -n 2 -q"
            ),
            "focused_test_command": "uv run pytest tests/unit/test_a.py -q",
            "low_impact_focused_test_command": (
                "nice -n 15 uv run pytest tests/unit/test_a.py -n 2 -q"
            ),
            "local_verification_command": (
                "nice -n 15 uv run pytest tests/unit/test_a.py -n 2 -q"
            ),
            "ci_verification_command": "uv run pytest -q",
            "resource_profile": "local_low_impact",
            "verification_strategy": "local_low_impact_focused_then_ci",
            "verification_steps": [
                "nice -n 15 uv run pytest tests/unit/test_a.py -n 2 -q"
            ],
        }

        response = build_agent_summary_only_response(result)

        assert response["verification_command"] == (
            "nice -n 15 uv run pytest tests/unit/test_a.py -n 2 -q"
        )
        assert response["local_verification_command"] == (
            "nice -n 15 uv run pytest tests/unit/test_a.py -n 2 -q"
        )
        assert response["low_impact_focused_test_command"] == (
            "nice -n 15 uv run pytest tests/unit/test_a.py -n 2 -q"
        )
        assert response["ci_verification_command"] == "uv run pytest -q"
        assert response["resource_profile"] == "local_low_impact"

    def test_agent_summary_only_does_not_emit_contradictory_legacy_scalars(self):
        """Compact mode must not expose stale top-level fields that fight summary."""
        result = {
            "success": True,
            "mode": "diff",
            "scope_paths": [],
            "scope_filtered": False,
            "agent_summary": {
                "risk": "high",
                "changed_count": 1,
                "affected_count": 8,
                "tests_to_run_count": 2,
                "changed_preview": ["tree_sitter_analyzer/example.py"],
                "next_step": "Run verification",
                "verification_command": "uv run pytest tests/unit/test_example.py -q",
                "stop_condition": "focused tests pass",
            },
            "risk_level": "high",
            "changed_count": 1,
            "affected_count": 8,
            "tests_to_run_count": 2,
        }

        response = build_agent_summary_only_response(result)

        assert response["risk_level"] == "high"
        assert response["changed_count"] == 1
        assert response["verification_command"] == (
            "uv run pytest tests/unit/test_example.py -q"
        )
        assert "pytest_required" not in response
        assert "changed_files" not in response
        assert "changed_preview" not in response
        assert "impact_level" not in response


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

    def test_report_mode_is_default_and_keeps_out_of_scope_preview(self):
        """Default ``scope_mode`` (report) preserves today's behavior: the
        out-of-scope dirty files are previewed, not muted (byte-parity)."""
        result = {"success": True}
        out = attach_queue_ledger(
            result,
            mode="diff",
            scope_paths=["src/"],
            scoped_changed_files=["src/a.py"],
            workspace_changed_files=["src/a.py", "tests/b.py", "docs/c.md"],
        )
        ledger = out["queue_ledger"]
        assert ledger["out_of_scope_changed_count"] == 2
        assert ledger["out_of_scope_changed_preview"] == ["tests/b.py", "docs/c.md"]
        assert ledger.get("out_of_scope_muted", False) is False
        assert ledger.get("scope_mode", "report") == "report"

    def test_strict_mode_mutes_out_of_scope_preview(self):
        """``scope_mode='strict'`` fully mutes the out-of-scope dirty file list
        so the actionable scoped message is not buried — while keeping an honest
        count so the agent still knows untouched dirt exists (#8)."""
        result = {"success": True}
        out = attach_queue_ledger(
            result,
            mode="diff",
            scope_paths=["src/"],
            scoped_changed_files=["src/a.py"],
            workspace_changed_files=["src/a.py", "tests/b.py", "docs/c.md"],
            scope_mode="strict",
        )
        ledger = out["queue_ledger"]
        # Honest count retained (faithful reporting), but the noisy list muted.
        assert ledger["out_of_scope_changed_count"] == 2
        assert ledger["out_of_scope_changed_preview"] == []
        assert ledger["out_of_scope_muted"] is True
        assert ledger["scope_mode"] == "strict"

    def test_strict_scope_hint_does_not_bury_scoped_message(self):
        """In strict mode the scope_hint leads with the scoped queue and clearly
        flags the muted count, rather than dwelling on out-of-scope noise."""
        result = {"success": True}
        out = attach_queue_ledger(
            result,
            mode="diff",
            scope_paths=["src/"],
            scoped_changed_files=["src/a.py", "src/b.py"],
            workspace_changed_files=["src/a.py", "src/b.py", "tests/x.py"],
            scope_mode="strict",
        )
        hint = out["agent_summary"]["scope_hint"]
        assert hint.startswith("Scoped queue has 2 changed file(s)")
        assert "muted" in hint


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
        # visible=2, all=3 → 1 test omitted from the visible slice.
        assert response["tests_to_run_omitted_count"] == 1
        assert response["scope_filtered"] is True

    def test_full_response_exposes_low_impact_local_and_ci_commands(self):
        import types

        request = types.SimpleNamespace(
            mode="diff",
            scope_paths=[],
            changed_files=["src/a.py"],
            diff_stat="+1",
        )
        local_command = "nice -n 15 uv run pytest tests/unit/test_a.py -n 2 -q"
        ctx = ChangeImpactResponseContext(
            request=request,
            risk="low",
            affected={"src/a.py"},
            file_impacts=[{"file": "src/a.py"}],
            visible_tests=["tests/unit/test_a.py"],
            all_tests=["tests/unit/test_a.py"],
            verification=_make_verification(
                verification_command="uv run pytest -q",
                default_test_command="uv run pytest -q",
            ),
            strategy=_make_strategy(
                focused_test_command="uv run pytest tests/unit/test_a.py -q",
                low_impact_focused_test_command=local_command,
                local_verification_command=local_command,
                ci_verification_command="uv run pytest -q",
                resource_profile="local_low_impact",
                verification_strategy="local_low_impact_focused_then_ci",
                verification_steps=[local_command],
            ),
            test_mapping={"src/a.py": ["tests/unit/test_a.py"]},
            agent_summary={"risk": "low", "verification_command": local_command},
        )

        response = build_change_impact_response(ctx)

        assert response["verification_command"] == local_command
        assert response["local_verification_command"] == local_command
        assert response["low_impact_focused_test_command"] == local_command
        assert response["ci_verification_command"] == "uv run pytest -q"
        assert response["resource_profile"] == "local_low_impact"

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
