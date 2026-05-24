"""Tests for ``--affected`` CLI dispatcher (CodeGraph CLI parity).

Closes the last surface advantage CodeGraph held over TSA's CLI —
``codegraph affected <files>`` ↔ ``tree-sitter-analyzer --affected
<files>``. These tests pin the dispatcher's contract so the parity
claim cannot silently regress.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.cli.commands.affected_command import (
    _DEFAULT_TEST_GLOBS,
    _is_test_path,
    run_affected,
)


class TestIsTestPath:
    @pytest.mark.parametrize(
        "path",
        [
            "tests/unit/test_foo.py",
            "src/foo/tests/test_bar.py",
            "test_quick.py",
            "foo_test.py",
            "some/dir/foo_test.go",
            "myapp/src/test/java/Foo.java",
            "foo.test.ts",
            "foo.spec.tsx",
            "components/__tests__/Button.test.js",
            "Tests/Alamofire/SessionTests.swift",
            "SessionTests.swift",
        ],
    )
    def test_recognised_test_paths(self, path: str) -> None:
        assert _is_test_path(path, _DEFAULT_TEST_GLOBS) is True, path

    @pytest.mark.parametrize(
        "path",
        [
            "src/main.py",
            "foo/bar.go",
            "src/main/java/Foo.java",
            "components/Button.tsx",
            "Sources/Alamofire/Session.swift",
            "README.md",
        ],
    )
    def test_non_test_paths_rejected(self, path: str) -> None:
        assert _is_test_path(path, _DEFAULT_TEST_GLOBS) is False, path

    def test_custom_filter_overrides_defaults(self) -> None:
        # When a custom filter is supplied, ``tests/...`` should NOT match
        # unless the filter explicitly covers it.
        custom = ("e2e/*.spec.ts",)
        assert _is_test_path("tests/unit/test_x.py", custom) is False
        assert _is_test_path("e2e/login.spec.ts", custom) is True


class TestRunAffected:
    """End-to-end smoke tests using a mocked DependencyAnalysisTool.

    We bypass the real blast-radius computation so these stay fast and
    deterministic — the dependency-graph code itself is covered by its
    own test suite.
    """

    def test_missing_project_root_returns_1(self, tmp_path, capsys):
        errs: list[str] = []
        args = SimpleNamespace(
            project_root=str(tmp_path / "does-not-exist"),
            affected=["foo.py"],
        )
        rc = run_affected(args, errs.append)
        assert rc == 1
        assert any("project root" in e for e in errs)

    def test_no_files_returns_1(self, tmp_path, capsys):
        errs: list[str] = []
        args = SimpleNamespace(project_root=str(tmp_path), affected=[])
        rc = run_affected(args, errs.append)
        assert rc == 1
        assert any("at least one FILE" in e for e in errs)

    def test_invalid_files_only_returns_1(self, tmp_path, capsys):
        errs: list[str] = []
        args = SimpleNamespace(
            project_root=str(tmp_path),
            affected=["nope.py"],
        )
        rc = run_affected(args, errs.append)
        assert rc == 1
        assert any("none of the requested files exist" in e for e in errs)

    def test_happy_path_with_test_files(self, tmp_path, capsys):
        src = tmp_path / "src.py"
        src.write_text("def foo(): pass\n")

        # Mock the dependency tool to return a hand-curated forward_impact.
        async def fake_execute(self, args):  # noqa: ARG001
            return {
                "success": True,
                "forward_impact": [
                    "tests/unit/test_src.py",
                    "tests/integration/test_other.py",
                    "src/consumer.py",  # not a test — should be filtered out
                    "README.md",  # also non-test
                ],
            }

        args = SimpleNamespace(
            project_root=str(tmp_path),
            affected=["src.py"],
            output_format="json",
        )
        with patch(
            "tree_sitter_analyzer.mcp.tools.dependency_analysis_tool"
            ".DependencyAnalysisTool.execute",
            new=fake_execute,
        ):
            rc = run_affected(args, lambda _e: None)
        assert rc == 0

        out = capsys.readouterr().out
        assert "test_src.py" in out
        assert "test_other.py" in out
        assert "consumer.py" not in out
        assert "README.md" not in out
        # Envelope shape pinned.
        assert '"verdict": "INFO"' in out
        assert '"test_files_total": 2' in out
        assert '"affected_files_total": 4' in out

    def test_no_matches_returns_not_found_verdict(self, tmp_path, capsys):
        src = tmp_path / "src.py"
        src.write_text("def foo(): pass\n")

        async def fake_execute(self, args):  # noqa: ARG001
            return {"success": True, "forward_impact": ["src/consumer.py"]}

        args = SimpleNamespace(
            project_root=str(tmp_path),
            affected=["src.py"],
            output_format="json",
        )
        with patch(
            "tree_sitter_analyzer.mcp.tools.dependency_analysis_tool"
            ".DependencyAnalysisTool.execute",
            new=fake_execute,
        ):
            rc = run_affected(args, lambda _e: None)
        assert rc == 0
        out = capsys.readouterr().out
        assert '"verdict": "NOT_FOUND"' in out
        assert '"test_files_total": 0' in out

    def test_quiet_mode_emits_paths_only(self, tmp_path, capsys):
        src = tmp_path / "src.py"
        src.write_text("def foo(): pass\n")

        async def fake_execute(self, args):  # noqa: ARG001
            return {
                "success": True,
                "forward_impact": [
                    "tests/unit/test_a.py",
                    "tests/unit/test_b.py",
                ],
            }

        args = SimpleNamespace(
            project_root=str(tmp_path),
            affected=["src.py"],
            affected_quiet=True,
        )
        with patch(
            "tree_sitter_analyzer.mcp.tools.dependency_analysis_tool"
            ".DependencyAnalysisTool.execute",
            new=fake_execute,
        ):
            rc = run_affected(args, lambda _e: None)
        assert rc == 0
        out = capsys.readouterr().out
        lines = [line for line in out.splitlines() if line.strip()]
        assert lines == ["tests/unit/test_a.py", "tests/unit/test_b.py"]
        # No envelope keys leaked in quiet mode.
        assert "verdict" not in out
        assert "affected_files_total" not in out

    def test_custom_filter_used(self, tmp_path, capsys):
        src = tmp_path / "src.py"
        src.write_text("def foo(): pass\n")

        async def fake_execute(self, args):  # noqa: ARG001
            return {
                "success": True,
                "forward_impact": [
                    "tests/unit/test_a.py",  # would match default
                    "e2e/login.spec.ts",  # only matches custom
                ],
            }

        args = SimpleNamespace(
            project_root=str(tmp_path),
            affected=["src.py"],
            affected_filter="e2e/*.spec.ts",
            output_format="json",
        )
        with patch(
            "tree_sitter_analyzer.mcp.tools.dependency_analysis_tool"
            ".DependencyAnalysisTool.execute",
            new=fake_execute,
        ):
            rc = run_affected(args, lambda _e: None)
        assert rc == 0
        out = capsys.readouterr().out
        assert "e2e/login.spec.ts" in out
        # Default-pattern matches are excluded under the custom filter.
        assert "test_a.py" not in out
        assert '"filter_used": "e2e/*.spec.ts"' in out

    def test_invalid_files_listed_when_any_succeed(self, tmp_path, capsys):
        src = tmp_path / "real.py"
        src.write_text("def foo(): pass\n")

        async def fake_execute(self, args):  # noqa: ARG001
            return {
                "success": True,
                "forward_impact": ["tests/unit/test_real.py"],
            }

        args = SimpleNamespace(
            project_root=str(tmp_path),
            affected=["real.py", "nope.py"],
            output_format="json",
        )
        with patch(
            "tree_sitter_analyzer.mcp.tools.dependency_analysis_tool"
            ".DependencyAnalysisTool.execute",
            new=fake_execute,
        ):
            rc = run_affected(args, lambda _e: None)
        # Real file resolved successfully → exit 0; the bad input is
        # surfaced inside the envelope instead of crashing the run.
        assert rc == 0
        out = capsys.readouterr().out
        assert '"invalid_input_files"' in out
        assert '"nope.py"' in out
