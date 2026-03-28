#!/usr/bin/env python3
"""
Integration tests for get_code_outline tool TOON format support.

使用真实文件和真实 tree-sitter 解析，验证 TOON 格式输出的正确性。
遵循项目集成测试规范：真实 tree-sitter 解析 + tempfile + asyncio.run()
"""

import json
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import GetCodeOutlineTool

# ---------------------------------------------------------------------------
# 测试用代码片段
# ---------------------------------------------------------------------------

PYTHON_CODE = '''\
"""Sample Python module for outline testing."""


class Calculator:
    """Simple calculator class."""

    def __init__(self, initial: float = 0.0) -> None:
        """Initialize with optional starting value."""
        self.value = initial

    def add(self, x: float) -> float:
        """Add x to current value."""
        self.value += x
        return self.value

    def subtract(self, x: float) -> float:
        """Subtract x from current value."""
        self.value -= x
        return self.value

    def reset(self) -> None:
        """Reset value to zero."""
        self.value = 0.0


def format_result(label: str, value: float) -> str:
    """Format a result string."""
    return f"{label}: {value:.2f}"
'''

JAVA_CODE = """\
package com.example;

import java.util.List;
import java.util.ArrayList;

public class DataService {

    private String name;
    private int count;

    public DataService(String name) {
        this.name = name;
        this.count = 0;
    }

    public String getName() {
        return name;
    }

    public int getCount() {
        return count;
    }

    public List<String> getItems() {
        return new ArrayList<>();
    }

    public void increment() {
        count++;
    }
}
"""


# ---------------------------------------------------------------------------
# Python 文件集成测试
# ---------------------------------------------------------------------------


class TestGetCodeOutlineToonIntegrationPython:
    """Python 文件 TOON 格式集成测试"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_python_file_toon_output_structure(self):
        """Python 文件 TOON 格式输出应包含预期结构字段"""
        tool = GetCodeOutlineTool()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(PYTHON_CODE)
            temp_path = f.name

        try:
            result = await tool.execute(
                {"file_path": temp_path, "output_format": "toon"}
            )

            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["type"] == "text"

            toon_text = result[0]["text"]
            # 验证 TOON 格式关键字段
            assert "success:" in toon_text
            assert "outline:" in toon_text
            assert "file_path:" in toon_text
            assert "language: python" in toon_text
            assert "total_lines:" in toon_text
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_python_file_toon_detects_classes_and_methods(self):
        """Python 文件 TOON 输出应检测到类和方法"""
        tool = GetCodeOutlineTool()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(PYTHON_CODE)
            temp_path = f.name

        try:
            result = await tool.execute(
                {"file_path": temp_path, "output_format": "toon"}
            )

            toon_text = result[0]["text"]
            # 应包含类名和方法名
            assert "Calculator" in toon_text
            assert "add" in toon_text or "subtract" in toon_text
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_python_file_json_format_parseable(self):
        """Python 文件 JSON 格式应可解析"""
        tool = GetCodeOutlineTool()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(PYTHON_CODE)
            temp_path = f.name

        try:
            result = await tool.execute(
                {"file_path": temp_path, "output_format": "json"}
            )

            json_text = result[0]["text"]
            data = json.loads(json_text)

            assert data["success"] is True
            assert "outline" in data
            assert data["outline"]["language"] == "python"
        finally:
            Path(temp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Java 文件集成测试
# ---------------------------------------------------------------------------


class TestGetCodeOutlineToonIntegrationJava:
    """Java 文件 TOON 格式集成测试"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_java_file_toon_output_structure(self):
        """Java 文件 TOON 格式输出应包含预期结构字段"""
        tool = GetCodeOutlineTool()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(JAVA_CODE)
            temp_path = f.name

        try:
            result = await tool.execute(
                {"file_path": temp_path, "output_format": "toon"}
            )

            toon_text = result[0]["text"]
            assert "success:" in toon_text
            assert "outline:" in toon_text
            assert "language: java" in toon_text
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_java_file_toon_detects_class(self):
        """Java 文件 TOON 输出应检测到 DataService 类"""
        tool = GetCodeOutlineTool()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(JAVA_CODE)
            temp_path = f.name

        try:
            result = await tool.execute(
                {"file_path": temp_path, "output_format": "toon"}
            )

            toon_text = result[0]["text"]
            assert "DataService" in toon_text
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_java_file_default_format_is_toon(self):
        """未指定 output_format 时应默认返回 TOON 格式"""
        tool = GetCodeOutlineTool()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(JAVA_CODE)
            temp_path = f.name

        try:
            # 不指定 output_format
            result = await tool.execute({"file_path": temp_path})

            toon_text = result[0]["text"]
            # TOON 格式应以 "success: true" 开头，而非 JSON 的 "{"
            assert not toon_text.strip().startswith("{")
            assert "success:" in toon_text
        finally:
            Path(temp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# TOON vs JSON 对比测试
# ---------------------------------------------------------------------------


class TestGetCodeOutlineToonVsJsonComparison:
    """TOON 与 JSON 格式对比测试"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_toon_is_shorter_than_json(self):
        """TOON 输出长度应小于等效 JSON 输出"""
        tool = GetCodeOutlineTool()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(JAVA_CODE)
            temp_path = f.name

        try:
            toon_result = await tool.execute(
                {"file_path": temp_path, "output_format": "toon"}
            )
            json_result = await tool.execute(
                {"file_path": temp_path, "output_format": "json"}
            )

            toon_len = len(toon_result[0]["text"])
            json_len = len(json_result[0]["text"])

            # TOON 应明显比 JSON 短
            assert toon_len < json_len, (
                f"TOON ({toon_len} chars) should be shorter than JSON ({json_len} chars)"
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_both_formats_contain_same_class_names(self):
        """TOON 和 JSON 应包含相同的类名信息"""
        tool = GetCodeOutlineTool()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(JAVA_CODE)
            temp_path = f.name

        try:
            toon_result = await tool.execute(
                {"file_path": temp_path, "output_format": "toon"}
            )
            json_result = await tool.execute(
                {"file_path": temp_path, "output_format": "json"}
            )

            toon_text = toon_result[0]["text"]
            json_text = json_result[0]["text"]

            # 两种格式都应包含类名
            assert "DataService" in toon_text
            assert "DataService" in json_text

            # JSON 应可解析
            data = json.loads(json_text)
            assert data["success"] is True
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_result_type_is_text_content_block(self):
        """两种格式的返回值都应是 MCP text content block"""
        tool = GetCodeOutlineTool()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(PYTHON_CODE)
            temp_path = f.name

        try:
            for fmt in ("toon", "json"):
                result = await tool.execute(
                    {"file_path": temp_path, "output_format": fmt}
                )
                assert isinstance(result, list), f"format={fmt}: result should be list"
                assert len(result) == 1, f"format={fmt}: result should have 1 item"
                assert result[0]["type"] == "text", f"format={fmt}: type should be text"
                assert isinstance(result[0]["text"], str), (
                    f"format={fmt}: text should be str"
                )
        finally:
            Path(temp_path).unlink(missing_ok=True)
