#!/usr/bin/env python3
"""
Unit tests for get_code_outline tool TOON format support.

遵循项目测试规范：
- Unit tests = Mock-based only, NO real parser, NO tempfile, NO asyncio.analyze_file
- 测试 TOON 格式输出功能
- 验证 output_format 参数
- 验证格式化逻辑
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import GetCodeOutlineTool


class TestGetCodeOutlineToolToonFormat:
    """测试 TOON 格式支持的基本功能"""

    def test_tool_schema_includes_output_format_parameter(self):
        """工具 schema 应包含 output_format 参数"""
        tool = GetCodeOutlineTool(Path("/fake/project"))
        schema = tool.get_tool_schema()

        assert "output_format" in schema["properties"]
        assert schema["properties"]["output_format"]["type"] == "string"
        assert schema["properties"]["output_format"]["enum"] == ["json", "toon"]
        assert schema["properties"]["output_format"]["default"] == "toon"

    def test_default_output_format_is_toon(self):
        """默认输出格式应为 TOON"""
        tool = GetCodeOutlineTool(Path("/fake/project"))
        schema = tool.get_tool_schema()

        assert schema["properties"]["output_format"]["default"] == "toon"

    def test_validate_arguments_accepts_toon_format(self):
        """验证参数应接受 toon 格式"""
        tool = GetCodeOutlineTool(Path("/fake/project"))

        args = {
            "file_path": "/fake/file.py",
            "output_format": "toon",
        }

        assert tool.validate_arguments(args) is True

    def test_validate_arguments_accepts_json_format(self):
        """验证参数应接受 json 格式"""
        tool = GetCodeOutlineTool(Path("/fake/project"))

        args = {
            "file_path": "/fake/file.py",
            "output_format": "json",
        }

        assert tool.validate_arguments(args) is True

    def test_validate_arguments_rejects_invalid_format(self):
        """验证参数应拒绝无效格式"""
        tool = GetCodeOutlineTool(Path("/fake/project"))

        args = {
            "file_path": "/fake/file.py",
            "output_format": "xml",  # 无效格式
        }

        assert tool.validate_arguments(args) is False

    def test_validate_arguments_allows_missing_output_format(self):
        """验证参数应允许省略 output_format（使用默认值）"""
        tool = GetCodeOutlineTool(Path("/fake/project"))

        args = {
            "file_path": "/fake/file.py",
        }

        # 省略 output_format 应该可以通过验证
        assert tool.validate_arguments(args) is True


class TestGetCodeOutlineToolToonExecution:
    """测试 TOON 格式的执行逻辑"""

    @pytest.mark.asyncio
    async def test_execute_with_toon_format_returns_flat_envelope(self):
        """execute 使用 toon 格式时应返回扁平 envelope，包含 toon_content blob.

        M1 (round-26): the TOON path used to wrap the response in the MCP
        wire-format envelope (``{"content": [{"type":"text","text":...}]}``)
        directly inside ``execute()``. The fix routes TOON output through
        ``apply_toon_format_to_response`` which keeps metadata at the top
        level (success / file_path / summary_line / agent_summary / counts)
        and adds a ``toon_content`` blob alongside.
        """
        tool = GetCodeOutlineTool(Path("/fake/project"))

        # Mock analysis_engine.analyze
        mock_result = MagicMock()
        mock_result.language = "python"
        mock_result.file_path = "/fake/file.py"
        mock_result.total_lines = 100
        mock_result.classes = []
        mock_result.functions = []
        mock_result.variables = []
        mock_result.imports = []

        # Mock resolve_and_validate_file_path to bypass security validation
        # Mock Path.exists() to bypass file existence check
        with patch.object(
            tool, "resolve_and_validate_file_path", return_value="/fake/file.py"
        ):
            with patch("pathlib.Path.exists", return_value=True):
                with patch.object(
                    tool.analysis_engine,
                    "analyze",
                    new_callable=AsyncMock,
                    return_value=mock_result,
                ):
                    args = {
                        "file_path": "/fake/file.py",
                        "language": "python",
                        "output_format": "toon",
                    }

                    result = await tool.execute(args)

                    # The response is the flat envelope (no MCP wire-format
                    # wrapping). Top-level keys carry the canonical fields,
                    # and ``toon_content`` carries the formatted blob.
                    assert isinstance(result, dict)
                    assert result["success"] is True
                    assert result.get("format") == "toon"
                    assert "toon_content" in result
                    assert isinstance(result["toon_content"], str)

    @pytest.mark.asyncio
    async def test_execute_with_json_format_returns_structured_dict(self):
        """execute 使用 json 格式时应返回结构化 dict（无 toon_content blob）."""
        tool = GetCodeOutlineTool(Path("/fake/project"))

        # Mock analyze_file
        mock_result = MagicMock()
        mock_result.language = "python"
        mock_result.file_path = "/fake/file.py"
        mock_result.total_lines = 100
        mock_result.classes = []
        mock_result.functions = []
        mock_result.variables = []
        mock_result.imports = []

        # Mock resolve_and_validate_file_path to bypass security validation
        # Mock Path.exists() to bypass file existence check
        with patch.object(
            tool, "resolve_and_validate_file_path", return_value="/fake/file.py"
        ):
            with patch("pathlib.Path.exists", return_value=True):
                with patch.object(
                    tool.analysis_engine,
                    "analyze",
                    new_callable=AsyncMock,
                    return_value=mock_result,
                ):
                    args = {
                        "file_path": "/fake/file.py",
                        "language": "python",
                        "output_format": "json",
                    }

                    result = await tool.execute(args)

                    # The dict carries the canonical fields directly.
                    # JSON output does NOT add a ``toon_content`` blob.
                    assert isinstance(result, dict)
                    assert result["success"] is True
                    assert "outline" in result
                    assert "toon_content" not in result

    @pytest.mark.asyncio
    async def test_execute_defaults_to_toon_when_format_not_specified(self):
        """execute 在未指定格式时应默认使用 TOON, 返回 ``format=toon`` envelope."""
        tool = GetCodeOutlineTool(Path("/fake/project"))

        # Mock analyze_file
        mock_result = MagicMock()
        mock_result.language = "python"
        mock_result.file_path = "/fake/file.py"
        mock_result.total_lines = 100
        mock_result.classes = []
        mock_result.functions = []
        mock_result.variables = []
        mock_result.imports = []

        # Mock resolve_and_validate_file_path to bypass security validation
        # Mock Path.exists() to bypass file existence check
        with patch.object(
            tool, "resolve_and_validate_file_path", return_value="/fake/file.py"
        ):
            with patch("pathlib.Path.exists", return_value=True):
                with patch.object(
                    tool.analysis_engine,
                    "analyze",
                    new_callable=AsyncMock,
                    return_value=mock_result,
                ):
                    args = {
                        "file_path": "/fake/file.py",
                        "language": "python",
                        # 不指定 output_format
                    }

                    result = await tool.execute(args)

                    # 默认应该使用 TOON 格式 — envelope 携带 toon_content blob.
                    assert isinstance(result, dict)
                    assert result.get("format") == "toon"
                    assert "toon_content" in result


class TestGetCodeOutlineToolToonStructure:
    """测试 TOON 格式输出的结构正确性"""

    @pytest.mark.asyncio
    async def test_toon_output_contains_expected_fields(self):
        """TOON 输出应包含预期的字段"""
        tool = GetCodeOutlineTool(Path("/fake/project"))

        # Mock analyze_file 返回一个简单的结构
        mock_result = MagicMock()
        mock_result.language = "python"
        mock_result.file_path = "/fake/file.py"
        mock_result.total_lines = 100
        mock_result.classes = []
        mock_result.functions = []
        mock_result.variables = []
        mock_result.imports = []

        # Mock resolve_and_validate_file_path to bypass security validation
        # Mock Path.exists() to bypass file existence check
        with patch.object(
            tool, "resolve_and_validate_file_path", return_value="/fake/file.py"
        ):
            with patch("pathlib.Path.exists", return_value=True):
                with patch.object(
                    tool.analysis_engine,
                    "analyze",
                    new_callable=AsyncMock,
                    return_value=mock_result,
                ):
                    # 使用真实的 format_as_toon
                    args = {
                        "file_path": "/fake/file.py",
                        "language": "python",
                        "output_format": "toon",
                    }

                    result = await tool.execute(args)
                    # M1: TOON output now lives in ``toon_content`` on the
                    # flat envelope (no MCP wire-format wrapping).
                    toon_text = result["toon_content"]

                    # 验证 TOON 格式包含关键字段
                    assert "success:" in toon_text
                    assert "outline:" in toon_text
                    assert "file_path:" in toon_text
                    assert "language: python" in toon_text
                    assert "total_lines:" in toon_text

    @pytest.mark.asyncio
    async def test_toon_output_uses_compact_format(self):
        """TOON 输出应使用紧凑格式（无引号、无括号）"""
        tool = GetCodeOutlineTool(Path("/fake/project"))

        mock_result = MagicMock()
        mock_result.language = "python"
        mock_result.file_path = "/fake/file.py"
        mock_result.total_lines = 50
        mock_result.classes = []
        mock_result.functions = []
        mock_result.variables = []
        mock_result.imports = []

        # Mock resolve_and_validate_file_path to bypass security validation
        # Mock Path.exists() to bypass file existence check
        with patch.object(
            tool, "resolve_and_validate_file_path", return_value="/fake/file.py"
        ):
            with patch("pathlib.Path.exists", return_value=True):
                with patch.object(
                    tool.analysis_engine,
                    "analyze",
                    new_callable=AsyncMock,
                    return_value=mock_result,
                ):
                    args = {
                        "file_path": "/fake/file.py",
                        "language": "python",
                        "output_format": "toon",
                    }

                    result = await tool.execute(args)
                    # M1: TOON output now lives in ``toon_content`` on the
                    # flat envelope (no MCP wire-format wrapping).
                    toon_text = result["toon_content"]

                    # TOON 格式应该比 JSON 紧凑 — 花括号几乎为零，方括号
                    # 仅用于显式数组头（如 ``[N]{schema}:``）。Top-level fields
                    # are now hoisted (classes/methods/imports) so the bracket
                    # count rises slightly above the original threshold, but
                    # the format stays far more compact than JSON would be.
                    assert toon_text.count("{") < 5
                    assert toon_text.count("[") < 15


class TestGetCodeOutlineToolDefinition:
    """测试工具定义包含 output_format 信息"""

    def test_get_tool_definition_includes_output_format(self):
        """get_tool_definition 应包含 output_format 参数说明"""
        tool = GetCodeOutlineTool(Path("/fake/project"))
        definition = tool.get_tool_definition()

        # 检查描述中是否提到 TOON 格式
        description = definition["description"]
        assert "toon" in description.lower() or "TOON" in description, (
            "描述应提到 TOON 格式"
        )

        # 检查 inputSchema 包含 output_format
        input_schema = definition["inputSchema"]
        assert "output_format" in input_schema["properties"]
