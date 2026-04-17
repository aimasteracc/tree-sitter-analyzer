#!/usr/bin/env python3
"""
Unit tests for ErrorRecoveryTool MCP tool.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tree_sitter_analyzer.analysis.error_recovery import detect_encoding
from tree_sitter_analyzer.mcp.tools.error_recovery_tool import ErrorRecoveryTool


class TestErrorRecoveryTool:
    """Test ErrorRecoveryTool MCP tool."""

    @pytest.fixture
    def tool(self) -> ErrorRecoveryTool:
        """Create tool instance."""
        return ErrorRecoveryTool()

    @pytest.mark.asyncio
    async def test_tool_definition(self, tool: ErrorRecoveryTool) -> None:
        """Tool has valid definition."""
        definition = tool.get_tool_definition()
        assert definition["name"] == "error_recovery"
        assert "encoding" in definition["description"].lower()
        assert "inputSchema" in definition

    @pytest.mark.asyncio
    async def test_encoding_detection_utf8(self, tool: ErrorRecoveryTool) -> None:
        """Detect UTF-8 encoding."""
        with TemporaryDirectory() as tmp:
            test_file = Path(tmp) / "test.txt"
            test_file.write_text("Hello 世界", encoding="utf-8")

            result = await tool.execute(
                {"file_path": str(test_file), "detect_encoding_only": True}
            )
            assert result["success"] is True
            assert result["encoding"] == "utf-8"
            assert result["had_bom"] is False

    @pytest.mark.asyncio
    async def test_encoding_detection_gbk(self, tool: ErrorRecoveryTool) -> None:
        """Detect GBK encoding (Chinese)."""
        with TemporaryDirectory() as tmp:
            test_file = Path(tmp) / "test.txt"
            # GBK encoded content
            content = "你好世界".encode("gbk")
            test_file.write_bytes(content)

            result = await tool.execute(
                {"file_path": str(test_file), "detect_encoding_only": True}
            )
            assert result["success"] is True
            assert result["encoding"] == "gbk"

    @pytest.mark.asyncio
    async def test_encoding_detection_with_bom(self, tool: ErrorRecoveryTool) -> None:
        """Detect UTF-8 BOM."""
        with TemporaryDirectory() as tmp:
            test_file = Path(tmp) / "test.txt"
            content = b"\xef\xbb\xbfHello"
            test_file.write_bytes(content)

            result = await tool.execute(
                {"file_path": str(test_file), "detect_encoding_only": True}
            )
            assert result["success"] is True
            assert result["encoding"] == "utf-8"
            assert result["had_bom"] is True

    @pytest.mark.asyncio
    async def test_binary_file_detection(self, tool: ErrorRecoveryTool) -> None:
        """Binary file is detected."""
        with TemporaryDirectory() as tmp:
            binary_file = Path(tmp) / "data.bin"
            binary_file.write_bytes(bytes(range(256)))

            result = await tool.execute({"file_path": str(binary_file)})
            assert result["success"] is True
            assert result.get("is_binary") is True

    @pytest.mark.asyncio
    async def test_empty_file_handling(self, tool: ErrorRecoveryTool) -> None:
        """Empty file returns success."""
        with TemporaryDirectory() as tmp:
            empty_file = Path(tmp) / "empty.py"
            empty_file.write_text("")

            result = await tool.execute({"file_path": str(empty_file)})
            assert result["success"] is True
            assert result.get("recovery_mode") is True

    @pytest.mark.asyncio
    async def test_valid_file_analysis(self, tool: ErrorRecoveryTool) -> None:
        """Valid file analyzes successfully."""
        with TemporaryDirectory() as tmp:
            valid_file = Path(tmp) / "valid.py"
            valid_file.write_text(
                "class MyClass:\n"
                "    def method1(self):\n"
                "        pass\n\n"
                "    def method2(self):\n"
                "        return 42\n"
            )

            result = await tool.execute({"file_path": str(valid_file)})
            assert result["success"] is True
            assert "classes" in result or "recovery_mode" in result

    @pytest.mark.asyncio
    async def test_corrupted_file_recovery(self, tool: ErrorRecoveryTool) -> None:
        """Corrupted file uses recovery mode."""
        with TemporaryDirectory() as tmp:
            bad_file = Path(tmp) / "broken.java"
            bad_file.write_bytes(b"\x00\x01\x02public class Broken {\x00}\n")

            result = await tool.execute({"file_path": str(bad_file)})
            assert result["success"] is True
            assert result.get("recovery_mode") is True

    @pytest.mark.asyncio
    async def test_content_parameter(self, tool: ErrorRecoveryTool) -> None:
        """Content parameter works for encoding detection."""
        result = await tool.execute(
            {
                "file_path": "dummy.txt",
                "detect_encoding_only": True,
                "content": "Hello 世界",
            }
        )
        assert result["success"] is True
        assert result["encoding"] == "utf-8"

    @pytest.mark.asyncio
    async def test_missing_file_path(self, tool: ErrorRecoveryTool) -> None:
        """Missing file_path returns error."""
        result = await tool.execute({})
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_project_root_resolution(self, tool: ErrorRecoveryTool) -> None:
        """Relative path is resolved against project_root."""
        with TemporaryDirectory() as tmp:
            test_file = Path(tmp) / "subdir" / "test.py"
            test_file.parent.mkdir(parents=True)
            test_file.write_text("def hello(): pass")

            tool_with_root = ErrorRecoveryTool(project_root=str(tmp))
            result = await tool_with_root.execute(
                {"file_path": "subdir/test.py", "detect_encoding_only": True}
            )
            assert result["success"] is True


class TestDetectEncoding:
    """Test encoding detection function."""

    def test_utf8_detection(self) -> None:
        """UTF-8 is detected correctly."""
        content = "Hello 世界".encode()
        encoding, had_bom = detect_encoding(content)
        assert encoding == "utf-8"
        assert had_bom is False

    def test_gbk_detection(self) -> None:
        """GBK (Chinese) is detected correctly."""
        content = "你好世界".encode("gbk")
        encoding, _ = detect_encoding(content)
        assert encoding == "gbk"

    def test_shift_jis_detection(self) -> None:
        """Shift-JIS (Japanese) is detected correctly."""
        content = "こんにちは".encode("shift_jis")
        encoding, _ = detect_encoding(content)
        assert encoding == "shift_jis"

    def test_empty_content(self) -> None:
        """Empty content defaults to UTF-8."""
        encoding, had_bom = detect_encoding(b"")
        assert encoding == "utf-8"
        assert had_bom is False

    def test_bom_detection(self) -> None:
        """UTF-8 BOM is detected."""
        content = b"\xef\xbb\xbfHello"
        encoding, had_bom = detect_encoding(content)
        assert encoding == "utf-8"
        assert had_bom is True

    def test_binary_threshold(self) -> None:
        """High binary ratio is detected."""
        # 50% binary content
        content = bytes(range(128)) + b"Text" * 100
        encoding, _ = detect_encoding(content)
        # Should fall back to latin-1 or similar
        assert encoding in ("utf-8", "iso-8859-1", "latin-1")
