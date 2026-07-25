"""Tests for the central exception sanitizer (SEC-2)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.utils.error_sanitizer import (
    bounded_safe_error_message,
    safe_error_message,
    sanitize_error_detail,
    sanitize_exception,
    sanitize_message,
)


class TestSanitizeMessage:
    def test_empty_string(self):
        assert sanitize_message("", "/tmp") == ""

    def test_no_paths_in_message(self):
        assert (
            sanitize_message("invalid query syntax", "/tmp") == "invalid query syntax"
        )

    def test_inside_project_root_becomes_relative(self, tmp_path: Path):
        target = tmp_path / "src" / "main.py"
        target.parent.mkdir(parents=True)
        target.write_text("x = 1\n")
        msg = f"[Errno 2] missing: '{target}'"
        cleaned = sanitize_message(msg, str(tmp_path))
        assert str(target) not in cleaned
        assert "./src/main.py" in cleaned

    def test_outside_project_root_is_redacted(self, tmp_path: Path):
        msg = "Permission denied: '/etc/shadow'"
        cleaned = sanitize_message(msg, str(tmp_path))
        assert "/etc/shadow" not in cleaned
        assert "<external-path>" in cleaned

    def test_no_project_root_redacts_everything(self):
        msg = "No such file: '/Users/alice/secret.txt'"
        cleaned = sanitize_message(msg, None)
        assert "alice" not in cleaned
        assert "<external-path>" in cleaned

    def test_idempotent(self, tmp_path: Path):
        msg = f"failure at '{tmp_path}/x.py'"
        once = sanitize_message(msg, str(tmp_path))
        twice = sanitize_message(once, str(tmp_path))
        assert once == twice

    @pytest.mark.parametrize(
        ("message", "expected"),
        [
            ("failure path=/etc/shadow", "failure path=<external-path>"),
            ("failure [/etc/shadow]", "failure [<external-path>]"),
            ("failure {/etc/shadow}", "failure {<external-path>}"),
        ],
    )
    def test_external_path_is_redacted_at_punctuation_boundaries(
        self,
        message: str,
        expected: str,
        tmp_path: Path,
    ):
        assert sanitize_message(message, str(tmp_path)) == expected

    def test_project_path_is_relative_at_equals_boundary(self, tmp_path: Path):
        target = tmp_path / "src" / "bad.py"
        assert sanitize_message(f"path={target}", str(tmp_path)) == "path=./src/bad.py"

    @pytest.mark.parametrize("prefix", ["failure-", "failure_", "failure."])
    def test_external_path_is_redacted_after_word_punctuation(
        self,
        prefix: str,
        tmp_path: Path,
    ):
        assert (
            sanitize_message(f"{prefix}/etc/shadow", str(tmp_path))
            == f"{prefix}<external-path>"
        )

    def test_unquoted_external_path_with_spaces_is_fully_redacted(self, tmp_path: Path):
        assert (
            sanitize_message(
                "failed /Users/alice/My Secrets/key.txt",
                str(tmp_path),
            )
            == "failed <external-path>"
        )

    def test_unquoted_project_path_with_spaces_stays_actionable(self, tmp_path: Path):
        target = tmp_path / "My Secrets" / "key.txt"
        assert (
            sanitize_message(f"failed {target}", str(tmp_path))
            == "failed ./My Secrets/key.txt"
        )

    @pytest.mark.skipif(os.name == "nt", reason="POSIX host path interpretation")
    @pytest.mark.parametrize(
        "external_path",
        [r"C:\Users\alice\secret.txt", r"\\server\share\secret.txt"],
    )
    def test_windows_paths_are_not_treated_as_project_relative_on_posix(
        self,
        external_path: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.chdir(tmp_path)
        cleaned = sanitize_message(f"denied {external_path}", str(tmp_path))
        assert cleaned == "denied <external-path>"


class TestSanitizeErrorDetail:
    def test_sanitizes_copy_without_mutating_core_detail(self, tmp_path: Path):
        detail = {
            "file": str(tmp_path / "src" / "bad.py"),
            "status": "error",
            "error_message": "denied /etc/shadow",
        }

        cleaned = sanitize_error_detail(detail, str(tmp_path))

        assert cleaned == {
            "file": "./src/bad.py",
            "status": "error",
            "error_message": "denied <external-path>",
        }
        assert detail["file"] == str(tmp_path / "src" / "bad.py")
        assert detail["error_message"] == "denied /etc/shadow"

    def test_truncation_is_exact_and_explicit(self):
        cleaned = sanitize_error_detail(
            {"file": "src/bad.swift", "status": "error", "reason": "x" * 501}
        )

        assert cleaned["reason"] == ("x" * 497) + "..."
        assert cleaned["reason_truncated"] is True

    def test_structured_file_path_handles_spaces(self, tmp_path: Path):
        project_root = tmp_path / "my project"
        file_path = project_root / "src folder" / "bad.py"

        cleaned = sanitize_error_detail(
            {"file": str(file_path), "status": "error"},
            str(project_root),
        )

        assert cleaned["file"] == "./src folder/bad.py"

    def test_structured_file_path_redacts_relative_traversal(self, tmp_path: Path):
        cleaned = sanitize_error_detail(
            {"file": "../outside/secret.py", "status": "error"},
            str(tmp_path),
        )

        assert cleaned["file"] == "<external-path>"

    def test_unknown_fields_are_dropped(self):
        cleaned = sanitize_error_detail(
            {
                "file": "src/bad.py",
                "status": "error",
                "context": "path=/etc/passwd",
                "blob": "x" * 2_000,
            }
        )

        assert cleaned == {"file": "src/bad.py", "status": "error"}


class TestSanitizeException:
    def test_includes_exception_class_name(self, tmp_path: Path):
        try:
            raise FileNotFoundError("missing")
        except FileNotFoundError as e:
            out = sanitize_exception(e, str(tmp_path))
            assert out.startswith("FileNotFoundError:")

    def test_strips_absolute_path_from_message(self, tmp_path: Path):
        secret = tmp_path / "outside_dir"
        try:
            raise PermissionError(f"denied at {secret}/secret.env")
        except PermissionError as e:
            out = sanitize_exception(e, str(tmp_path))
            # path is inside tmp_path so it should become relative
            assert str(secret) not in out
            assert "./outside_dir/secret.env" in out

    def test_redacts_external_paths(self):
        try:
            raise OSError("could not read /Users/private/.ssh/id_rsa")
        except OSError as e:
            out = sanitize_exception(e, "/tmp/safe_project")
            assert "id_rsa" not in out
            assert "/Users/private" not in out
            assert "<external-path>" in out


class TestSafeErrorMessage:
    def test_safe_error_message_with_class(self, tmp_path: Path):
        try:
            raise ValueError("boom")
        except ValueError as e:
            out = safe_error_message(e, str(tmp_path), include_class=True)
            assert "ValueError" in out
            assert "boom" in out

    def test_safe_error_message_without_class(self, tmp_path: Path):
        try:
            raise ValueError("boom")
        except ValueError as e:
            out = safe_error_message(e, str(tmp_path), include_class=False)
            assert "ValueError" not in out
            assert "boom" in out

    def test_bounded_message_reports_exact_truncation(self, tmp_path: Path):
        message, truncated = bounded_safe_error_message(
            RuntimeError("x" * 1_000),
            str(tmp_path),
            prefix="Sync failed: ",
        )

        assert len(message) == 500
        assert message.endswith("...")
        assert truncated is True


class TestIntegrationWithErrorRecovery:
    """The error_recovery helper is the central error response builder.
    Make sure it actually invokes the sanitiser."""

    def test_build_agent_friendly_error_redacts_paths(self, tmp_path: Path):
        from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
            build_agent_friendly_error,
        )

        try:
            raise FileNotFoundError(
                "[Errno 2] No such file or directory: '/etc/shadow'"
            )
        except FileNotFoundError as e:
            body = build_agent_friendly_error("read_partial", e)
        assert "/etc/shadow" not in body["error"], body["error"]
        assert "<external-path>" in body["error"]


class TestFileOutputManagerPathTraversal:
    """SEC-1: refusing to write outside the configured output directory."""

    def test_rejects_parent_traversal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from tree_sitter_analyzer.mcp.utils.file_output_manager import (
            FileOutputManager,
        )

        monkeypatch.setenv("TREE_SITTER_OUTPUT_PATH", str(tmp_path))
        mgr = FileOutputManager(project_root=str(tmp_path))
        with pytest.raises(ValueError, match="outside the output directory"):
            mgr.save_to_file("anything", filename="../../etc/cron.d/backdoor")

    def test_rejects_absolute_path_outside(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from tree_sitter_analyzer.mcp.utils.file_output_manager import (
            FileOutputManager,
        )

        monkeypatch.setenv("TREE_SITTER_OUTPUT_PATH", str(tmp_path))
        mgr = FileOutputManager(project_root=str(tmp_path))
        with pytest.raises(ValueError, match="outside the output directory"):
            mgr.save_to_file("anything", filename="/etc/passwd")

    def test_allows_in_directory_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from tree_sitter_analyzer.mcp.utils.file_output_manager import (
            FileOutputManager,
        )

        monkeypatch.setenv("TREE_SITTER_OUTPUT_PATH", str(tmp_path))
        mgr = FileOutputManager(project_root=str(tmp_path))
        result_path = mgr.save_to_file("hello world\n", filename="sub/output.txt")
        assert (tmp_path / "sub" / "output.txt").exists()
        # Result should be inside tmp_path.
        assert str(tmp_path) in result_path
