"""Integration tests for SOLID Principles MCP Tool."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.solid_principles_tool import SOLIDPrinciplesTool


@pytest.fixture
def tool() -> SOLIDPrinciplesTool:
    return SOLIDPrinciplesTool()


def _write_tmp(content: str, suffix: str = ".py") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


class TestSOLIDPrinciplesToolDefinition:
    def test_tool_name(self, tool: SOLIDPrinciplesTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "solid_principles"

    def test_tool_has_description(self, tool: SOLIDPrinciplesTool) -> None:
        defn = tool.get_tool_definition()
        assert "SOLID" in defn["description"]
        assert "SRP" in defn["description"]

    def test_tool_schema_requires_file_path(self, tool: SOLIDPrinciplesTool) -> None:
        defn = tool.get_tool_definition()
        assert "file_path" in defn["inputSchema"]["properties"]
        assert "file_path" in defn["inputSchema"]["required"]

    def test_tool_schema_has_format(self, tool: SOLIDPrinciplesTool) -> None:
        defn = tool.get_tool_definition()
        assert "format" in defn["inputSchema"]["properties"]


class TestSOLIDPrinciplesToolExecution:
    @pytest.mark.asyncio
    async def test_execute_clean_python(self, tool: SOLIDPrinciplesTool) -> None:
        code = """
class UserService:
    def __init__(self, db):
        self.db = db

    def get_user(self, user_id):
        return self.db.find(user_id)
"""
        path = _write_tmp(code)
        try:
            result = await tool.execute({"file_path": path})
            assert result["result"]["overall_score"] == 100.0
            assert result["result"]["violation_count"] == 0
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_execute_python_with_violations(
        self, tool: SOLIDPrinciplesTool,
    ) -> None:
        methods = "\n".join(f"    def method_{i}(self): pass" for i in range(12))
        code = f"class GodClass:\n{methods}\n"
        path = _write_tmp(code)
        try:
            result = await tool.execute({"file_path": path})
            assert result["result"]["violation_count"] > 0
            assert result["result"]["overall_score"] < 100.0
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_execute_toon_format(self, tool: SOLIDPrinciplesTool) -> None:
        code = "x = 1\n"
        path = _write_tmp(code)
        try:
            result = await tool.execute({
                "file_path": path,
                "format": "toon",
            })
            assert "content" in result
            assert "summary" in result
            assert result["summary"]["overall_score"] == 100.0
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_execute_javascript(self, tool: SOLIDPrinciplesTool) -> None:
        code = """
class Handler {
  process(obj) {
    if (obj instanceof Array) {
      return this.handleArray(obj);
    }
  }
}
"""
        path = _write_tmp(code, suffix=".js")
        try:
            result = await tool.execute({"file_path": path})
            assert result["result"]["violation_count"] > 0
            violations = result["result"]["violations"]
            assert any(v["principle"] == "OCP" for v in violations)
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_execute_java(self, tool: SOLIDPrinciplesTool) -> None:
        code = """
public interface FatInterface {
    void method0();
    void method1();
    void method2();
    void method3();
    void method4();
    void method5();
    void method6();
    void method7();
    void method8();
    void method9();
    void method10();
    void method11();
    void method12();
    void method13();
    void method14();
    void method15();
    void method16();
}
"""
        path = _write_tmp(code, suffix=".java")
        try:
            result = await tool.execute({"file_path": path})
            assert result["result"]["violation_count"] > 0
            violations = result["result"]["violations"]
            assert any(v["principle"] == "ISP" for v in violations)
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_execute_go(self, tool: SOLIDPrinciplesTool) -> None:
        code = """package main

type Reader interface {
    Read(p []byte) (n int, err error)
}
"""
        path = _write_tmp(code, suffix=".go")
        try:
            result = await tool.execute({"file_path": path})
            assert result["result"]["violation_count"] == 0
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_execute_typescript(self, tool: SOLIDPrinciplesTool) -> None:
        code = """
class CleanService {
  private data: any[] = [];
  add(item: any): void { this.data.push(item); }
  get(index: number): any { return this.data[index]; }
}
"""
        path = _write_tmp(code, suffix=".ts")
        try:
            result = await tool.execute({"file_path": path})
            assert result["result"]["violation_count"] == 0
        finally:
            Path(path).unlink()


class TestSOLIDPrinciplesToolValidation:
    def test_validate_valid_arguments(self, tool: SOLIDPrinciplesTool) -> None:
        assert tool.validate_arguments({"file_path": "/tmp/test.py"})

    def test_validate_invalid_format(self, tool: SOLIDPrinciplesTool) -> None:
        with pytest.raises(ValueError, match="Invalid format"):
            tool.validate_arguments({
                "file_path": "/tmp/test.py",
                "format": "xml",
            })

    def test_validate_missing_file_path(self, tool: SOLIDPrinciplesTool) -> None:
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({})
