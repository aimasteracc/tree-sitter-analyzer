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
    async def test_execute_with_toon_format_calls_format_as_toon(self):
        """execute 使用 toon 格式时应调用 format_as_toon"""
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
        with patch.object(tool, "resolve_and_validate_file_path", return_value="/fake/file.py"):
            with patch("pathlib.Path.exists", return_value=True):
                with patch.object(
                    tool.analysis_engine, "analyze", new_callable=AsyncMock, return_value=mock_result
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.format_as_toon"
                    ) as mock_format_toon:
                        with patch(
                            "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.format_as_json"
                        ) as mock_format_json:
                            mock_format_toon.return_value = "success: true\noutline: ..."
                            mock_format_json.return_value = '{"success": true}'

                            args = {
                                "file_path": "/fake/file.py",
                                "language": "python",
                                "output_format": "toon",
                            }

                            result = await tool.execute(args)

                            # 应该调用 format_as_toon
                            mock_format_toon.assert_called_once()
                            # 不应该调用 format_as_json
                            mock_format_json.assert_not_called()

                            # 返回结果应包含 TOON 格式的文本
                            assert result[0]["type"] == "text"
                            assert "success: true" in result[0]["text"]

    @pytest.mark.asyncio
    async def test_execute_with_json_format_calls_format_as_json(self):
        """execute 使用 json 格式时应调用 format_as_json"""
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
        with patch.object(tool, "resolve_and_validate_file_path", return_value="/fake/file.py"):
            with patch("pathlib.Path.exists", return_value=True):
                with patch.object(
                    tool.analysis_engine, "analyze", new_callable=AsyncMock, return_value=mock_result
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.format_as_toon"
                    ) as mock_format_toon:
                        with patch(
                            "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.format_as_json"
                        ) as mock_format_json:
                            mock_format_toon.return_value = "success: true\noutline: ..."
                            mock_format_json.return_value = '{"success": true}'

                            args = {
                                "file_path": "/fake/file.py",
                                "language": "python",
                                "output_format": "json",
                            }

                            result = await tool.execute(args)

                            # 应该调用 format_as_json
                            mock_format_json.assert_called_once()
                            # 不应该调用 format_as_toon
                            mock_format_toon.assert_not_called()

                            # 返回结果应包含 JSON 格式的文本
                            assert result[0]["type"] == "text"
                            assert '{"success": true}' in result[0]["text"]

    @pytest.mark.asyncio
    async def test_execute_defaults_to_toon_when_format_not_specified(self):
        """execute 在未指定格式时应默认使用 TOON"""
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
        with patch.object(tool, "resolve_and_validate_file_path", return_value="/fake/file.py"):
            with patch("pathlib.Path.exists", return_value=True):
                with patch.object(
                    tool.analysis_engine, "analyze", new_callable=AsyncMock, return_value=mock_result
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.format_as_toon"
                    ) as mock_format_toon:
                        with patch(
                            "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.format_as_json"
                        ) as mock_format_json:
                            mock_format_toon.return_value = "success: true\noutline: ..."
                            mock_format_json.return_value = '{"success": true}'

                            args = {
                                "file_path": "/fake/file.py",
                                "language": "python",
                                # 不指定 output_format
                            }

                            await tool.execute(args)

                            # 应该默认调用 format_as_toon
                            mock_format_toon.assert_called_once()
                            mock_format_json.assert_not_called()


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
        with patch.object(tool, "resolve_and_validate_file_path", return_value="/fake/file.py"):
            with patch("pathlib.Path.exists", return_value=True):
                with patch.object(
                    tool.analysis_engine, "analyze", new_callable=AsyncMock, return_value=mock_result
                ):
                    # 使用真实的 format_as_toon
                    args = {
                        "file_path": "/fake/file.py",
                        "language": "python",
                        "output_format": "toon",
                    }

                    result = await tool.execute(args)
                    toon_text = result[0]["text"]

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
        with patch.object(tool, "resolve_and_validate_file_path", return_value="/fake/file.py"):
            with patch("pathlib.Path.exists", return_value=True):
                with patch.object(
                    tool.analysis_engine, "analyze", new_callable=AsyncMock, return_value=mock_result
                ):
                    args = {
                        "file_path": "/fake/file.py",
                        "language": "python",
                        "output_format": "toon",
                    }

                    result = await tool.execute(args)
                    toon_text = result[0]["text"]

                    # TOON 格式不应该有 JSON 的括号和引号
                    # (注意：某些字符串仍需要引号，如包含特殊字符的)
                    assert toon_text.count("{") < 5  # 应该很少有花括号
                    assert toon_text.count("[") < 5  # 应该很少有方括号


class TestGetCodeOutlineToolDefinition:
    """测试工具定义包含 output_format 信息"""

    def test_get_tool_definition_includes_output_format(self):
        """get_tool_definition 应包含 output_format 参数说明"""
        tool = GetCodeOutlineTool(Path("/fake/project"))
        definition = tool.get_tool_definition()

        # 检查描述中是否提到 TOON 格式
        description = definition["description"]
        assert (
            "toon" in description.lower() or "TOON" in description
        ), "描述应提到 TOON 格式"

        # 检查 inputSchema 包含 output_format
        input_schema = definition["inputSchema"]
        assert "output_format" in input_schema["properties"]
