#!/usr/bin/env python3
"""
User Story 3 統合テスト: クエリ実行 (Query)

User Story 3: 精密コード抽出・クエリ実行
- query_code: Tree-sitterクエリによる構造解析

このテストスイートは、query_codeツールが各言語・各クエリタイプで
正常に動作することを検証します。

Note: the shared temp_project fixture is defined in conftest.py.
"""

import json
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool


class TestUserStory3QueryIntegration:
    """User Story 3: クエリ実行統合テスト"""

    @pytest.fixture
    def tools(self, temp_project):
        """テスト用ツールインスタンスを作成"""
        project_root = str(temp_project)
        return {
            "extract": ReadPartialTool(project_root),
            "query": QueryTool(project_root),
        }

    @pytest.mark.asyncio
    async def test_03_query_code_java_methods(self, tools, temp_project):
        """Javaメソッドクエリテスト"""
        query_tool = tools["query"]

        result = await query_tool.execute(
            {
                "file_path": "src/ComplexService.java",
                "query_key": "methods",
                "output_format": "json",
            }
        )

        assert result["success"] is True
        assert "results" in result
        assert result["count"] == 11

        method_names = [
            r["content"] for r in result["results"] if "initialize" in r["content"]
        ]
        assert len(method_names) == 5
        print(f"✓ Javaメソッドクエリテスト成功: {result['count']}個のメソッド検出")

    @pytest.mark.asyncio
    async def test_04_query_code_typescript_interfaces(self, tools, temp_project):
        """TypeScriptインターフェースクエリテスト"""
        query_tool = tools["query"]

        result = await query_tool.execute(
            {
                "file_path": "src/DataManager.ts",
                "query_key": "interfaces",
                "result_format": "summary",
                "output_format": "json",
            }
        )

        assert result["success"] is True
        assert "captures" in result
        assert result["total_count"] == 6

        if "interface" in result["captures"]:
            interfaces = result["captures"]["interface"]["items"]
            interface_names = [item["name"] for item in interfaces]
            assert any(
                "DataItem" in name or "DataManagerConfig" in name
                for name in interface_names
            )

        print(
            f"✓ TypeScriptインターフェースクエリテスト成功: {result['total_count']}個検出"
        )

    @pytest.mark.asyncio
    async def test_05_query_code_python_classes(self, tools, temp_project):
        """Pythonクラスクエリテスト"""
        query_tool = tools["query"]

        result = await query_tool.execute(
            {
                "file_path": "src/analytics_engine.py",
                "query_key": "classes",
                "output_format": "json",
            }
        )

        assert result["success"] is True
        assert result["count"] == 18

        class_contents = [r["content"] for r in result["results"]]
        class_names = []
        for content in class_contents:
            if "class " in content:
                lines = content.split("\n")
                for line in lines:
                    if line.strip().startswith("class "):
                        class_names.append(line.strip())
                        break

        assert any("AnalyticsEngine" in name for name in class_names)
        print(f"✓ Pythonクラスクエリテスト成功: {len(class_names)}個のクラス検出")

    @pytest.mark.asyncio
    async def test_06_query_code_custom_query(self, tools, temp_project):
        """カスタムクエリテスト"""
        query_tool = tools["query"]

        result = await query_tool.execute(
            {
                "file_path": "src/ComplexService.java",
                "query_string": "(constructor_declaration) @constructor",
                "output_format": "json",
            }
        )

        assert result["success"] is True
        assert result["count"] == 4

        # 恒真陷阱 fixed: the old `constructor_found or result["count"] > 0`
        # inside `if result["count"] > 0` was vacuously true — and the live
        # value of constructor_found is False (Java constructor source never
        # contains the literal "constructor"). Pin the real declarations.
        constructor_names = [r["content"].split("(")[0] for r in result["results"]]
        assert constructor_names == [
            "public ComplexService",
            "public ComplexService",
            "public ServiceException",
            "public ServiceException",
        ]

        print(f"✓ カスタムクエリテスト成功: {result['count']}個の結果")

    @pytest.mark.asyncio
    async def test_07_query_with_filter(self, tools, temp_project):
        """フィルタ付きクエリテスト"""
        query_tool = tools["query"]

        result = await query_tool.execute(
            {
                "file_path": "src/analytics_engine.py",
                "query_key": "functions",
                "filter": "name=~create*",
                "output_format": "json",
            }
        )

        assert result["success"] is True

        if result["count"] > 0:
            for r in result["results"]:
                assert "create" in r["content"].lower()

        print(f"✓ フィルタ付きクエリテスト成功: {result['count']}個の結果")

    @pytest.mark.asyncio
    async def test_09_large_file_performance(self, tools, temp_project):
        """大規模ファイルでのパフォーマンステスト"""
        import time

        query_tool = tools["query"]

        start_time = time.time()

        result = await query_tool.execute(
            {
                "file_path": "src/analytics_engine.py",
                "query_key": "functions",
                "output_format": "json",
            }
        )

        end_time = time.time()
        execution_time = end_time - start_time

        assert result["success"] is True
        assert execution_time < 5.0

        print(
            f"✓ 大規模ファイルパフォーマンステスト成功: {execution_time:.2f}秒で{result['count']}個の関数を解析"
        )

    @pytest.mark.asyncio
    async def test_11_file_output_optimization(self, tools, temp_project):
        """ファイル出力とトークン最適化テスト"""
        query_tool = tools["query"]

        result = await query_tool.execute(
            {
                "file_path": "src/analytics_engine.py",
                "query_key": "functions",
                "output_file": "functions_analysis",
                "suppress_output": True,
                "output_format": "json",
            }
        )

        assert result["success"] is True
        assert result["file_saved"] is True
        assert "output_file_path" in result

        assert "results" not in result
        assert "count" in result

        output_file = Path(result["output_file_path"])
        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            file_content = json.load(f)
            assert "results" in file_content
            assert (
                len(file_content["results"]) == 52
            )  # was 104 (double-captured before #557); 52 is the correct single-capture count

        print(
            f"✓ ファイル出力最適化テスト成功: {result['count']}個の結果を{output_file.name}に保存"
        )

    @pytest.mark.asyncio
    async def test_13_markdown_analysis(self, tools, temp_project):
        """Markdownファイル解析テスト"""
        query_tool = tools["query"]

        result = await query_tool.execute(
            {
                "file_path": "docs/API_Reference.md",
                "query_key": "headers",
                "result_format": "summary",
                "output_format": "json",
            }
        )

        assert result["success"] is True
        assert result["total_count"] == 12

        if "header" in result["captures"]:
            headers = result["captures"]["header"]["items"]
            header_names = [item["name"] for item in headers]
            assert any("API Reference" in name for name in header_names)

        print(f"✓ Markdown解析テスト成功: {result['total_count']}個のヘッダー検出")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
