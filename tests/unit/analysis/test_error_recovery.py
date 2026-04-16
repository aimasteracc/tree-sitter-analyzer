"""
TDD tests for error recovery mechanism.

Tests graceful degradation when analysis operations encounter errors.
"""
from __future__ import annotations

from pathlib import Path

import pytest


class TestErrorRecovery:
    """Error recovery with fallback strategies."""

    def test_corrupted_file_returns_success(self, tmp_path: Path) -> None:
        """Corrupted Java file still returns a result (tree-sitter is resilient)."""
        from tree_sitter_analyzer.analysis.error_recovery import ErrorRecovery

        bad_java = tmp_path / "Broken.java"
        bad_java.write_bytes(b"\x00\x01\x02public class Broken {\x00}\n")

        recovery = ErrorRecovery(project_root=str(tmp_path))
        result = recovery.analyze_with_fallback(str(bad_java))

        assert result.get("success") is True

    def test_binary_file_detected(self, tmp_path: Path) -> None:
        """Binary file is detected and returns encoding info."""
        from tree_sitter_analyzer.analysis.error_recovery import ErrorRecovery

        binary = tmp_path / "data.bin"
        binary.write_bytes(bytes(range(256)))

        recovery = ErrorRecovery(project_root=str(tmp_path))
        result = recovery.analyze_with_fallback(str(binary))

        assert result.get("success") is True
        assert result.get("is_binary") is True

    def test_empty_file_returns_minimal(self, tmp_path: Path) -> None:
        """Empty file returns minimal valid result."""
        from tree_sitter_analyzer.analysis.error_recovery import ErrorRecovery

        empty = tmp_path / "Empty.java"
        empty.write_text("")

        recovery = ErrorRecovery(project_root=str(tmp_path))
        result = recovery.analyze_with_fallback(str(empty))

        assert result.get("success") is True
        assert result.get("recovery_mode") is True

    def test_valid_file_analyzes(self, tmp_path: Path) -> None:
        """Valid file analyzes successfully."""
        from tree_sitter_analyzer.analysis.error_recovery import ErrorRecovery

        valid = tmp_path / "Valid.java"
        valid.write_text("public class Valid { void go() {} }\n")

        recovery = ErrorRecovery(project_root=str(tmp_path))
        result = recovery.analyze_with_fallback(str(valid))

        assert result.get("success") is True

    def test_regex_fallback_directly(self) -> None:
        """Regex fallback extracts class names from text."""
        from tree_sitter_analyzer.analysis.error_recovery import ErrorRecovery

        recovery = ErrorRecovery(project_root="/tmp")
        text = "public class Foo {\n  void bar()\n"
        result = recovery._regex_fallback("Test.java", text, 2)

        assert result["success"] is True
        assert result["recovery_mode"] is True
        class_names = [c["name"] for c in result["classes"]]
        assert "Foo" in class_names

    def test_nonexistent_file_returns_error(self, tmp_path: Path) -> None:
        """Nonexistent file returns error result, not crash."""
        from tree_sitter_analyzer.analysis.error_recovery import ErrorRecovery

        recovery = ErrorRecovery(project_root=str(tmp_path))
        result = recovery.analyze_with_fallback(str(tmp_path / "NoFile.java"))

        assert result.get("success") is False
        assert result.get("recovery_mode") is True
        assert "error" in result
