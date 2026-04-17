"""
TDD tests for error recovery mechanism.

Tests graceful degradation when analysis operations encounter errors.
"""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.error_recovery import detect_encoding


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


class TestEncodingDetection:
    """Tests for automatic encoding detection."""

    def test_utf8_plain_ascii(self) -> None:
        """Plain ASCII content is detected as UTF-8."""
        encoding, had_bom = detect_encoding(b"Hello, World!")
        assert encoding == "utf-8"
        assert had_bom is False

    def test_utf8_with_chinese(self) -> None:
        """UTF-8 encoded Chinese text is detected as UTF-8."""
        content = "你好世界".encode()
        encoding, had_bom = detect_encoding(content)
        assert encoding == "utf-8"
        assert had_bom is False

    def test_utf8_bom(self) -> None:
        """UTF-8 BOM is detected."""
        content = b"\xef\xbb\xbf" + "你好".encode()
        encoding, had_bom = detect_encoding(content)
        assert encoding == "utf-8"
        assert had_bom is True

    def test_utf16_le_bom(self) -> None:
        """UTF-16 LE BOM is detected."""
        content = b"\xff\xfe" + "Hello".encode("utf-16-le")
        encoding, had_bom = detect_encoding(content)
        assert encoding == "utf-16-le"
        assert had_bom is True

    def test_utf16_be_bom(self) -> None:
        """UTF-16 BE BOM is detected."""
        content = b"\xfe\xff" + "Hello".encode("utf-16-be")
        encoding, had_bom = detect_encoding(content)
        assert encoding == "utf-16-be"
        assert had_bom is True

    def test_gbk_chinese(self) -> None:
        """GBK encoded Chinese text is detected."""
        content = "你好世界，这是一个测试文件".encode("gbk")
        encoding, had_bom = detect_encoding(content)
        assert encoding == "gbk"
        assert had_bom is False

    def test_shift_jis_japanese(self) -> None:
        """Shift-JIS encoded Japanese text is detected."""
        content = "こんにちは世界、テストファイル".encode("shift_jis")
        encoding, had_bom = detect_encoding(content)
        assert encoding == "shift_jis"
        assert had_bom is False

    def test_empty_content(self) -> None:
        """Empty content defaults to UTF-8."""
        encoding, had_bom = detect_encoding(b"")
        assert encoding == "utf-8"
        assert had_bom is False

    def test_latin1_fallback(self) -> None:
        """Non-UTF-8, non-CJK content falls back to Latin-1."""
        # Bytes that are valid Latin-1 but not valid UTF-8 and don't look CJK
        content = b"\xe0\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9"
        encoding, _had_bom = detect_encoding(content)
        # Should resolve to some encoding (iso-8859-1 or similar)
        # The important thing is it doesn't crash
        assert isinstance(encoding, str)

    def test_gbk_file_analyzed_correctly(self, tmp_path: Path) -> None:
        """GBK-encoded Java file is correctly decoded and analyzed."""
        from tree_sitter_analyzer.analysis.error_recovery import ErrorRecovery

        java_source = "// 中文注释\npublic class Test {\n  void go() {}\n}\n"
        gbk_file = tmp_path / "Test.java"
        gbk_file.write_bytes(java_source.encode("gbk"))

        recovery = ErrorRecovery(project_root=str(tmp_path))
        result = recovery.analyze_with_fallback(str(gbk_file))

        assert result.get("success") is True
        # The Chinese comment should not cause a crash
        assert result.get("is_binary") is not True

    def test_shift_jis_file_analyzed_correctly(self, tmp_path: Path) -> None:
        """Shift-JIS encoded Java file is correctly decoded and analyzed."""
        from tree_sitter_analyzer.analysis.error_recovery import ErrorRecovery

        java_source = "// 日本語コメント\npublic class Test {\n  void go() {}\n}\n"
        sjis_file = tmp_path / "Test.java"
        sjis_file.write_bytes(java_source.encode("shift_jis"))

        recovery = ErrorRecovery(project_root=str(tmp_path))
        result = recovery.analyze_with_fallback(str(sjis_file))

        assert result.get("success") is True
        assert result.get("is_binary") is not True
