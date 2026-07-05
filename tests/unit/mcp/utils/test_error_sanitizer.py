"""Tests for the central exception sanitizer (SEC-2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.utils.error_sanitizer import (
    safe_error_message,
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
