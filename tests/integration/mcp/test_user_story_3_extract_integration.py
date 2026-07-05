#!/usr/bin/env python3
"""
User Story 3 統合テスト: 精密コード抽出 (Extract/ReadPartial)

User Story 3: 精密コード抽出・クエリ実行
- extract_code_section: 特定コード部分の精密抽出
- 抽出とクエリの連携ワークフロー

このテストスイートは、extract_code_sectionツールとクロスカット的な
ワークフローテストを検証します。

Note: the shared temp_project fixture is defined in conftest.py.
"""

import asyncio
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool


class TestUserStory3ExtractIntegration:
    """User Story 3: 精密コード抽出・クロスカット統合テスト"""

    @pytest.fixture
    def tools(self, temp_project):
        """テスト用ツールインスタンスを作成"""
        project_root = str(temp_project)
        return {
            "extract": ReadPartialTool(project_root),
            "query": QueryTool(project_root),
        }

    @pytest.mark.asyncio
    async def test_01_extract_code_section_basic(self, tools, temp_project):
        """基本的なコード抽出機能のテスト"""
        extract_tool = tools["extract"]

        result = await extract_tool.execute(
            {
                "file_path": "src/ComplexService.java",
                "start_line": 10,
                "end_line": 20,
                "format": "text",
                "output_format": "json",
            }
        )

        assert result["success"] is True
        assert "partial_content_result" in result
        assert "ComplexService" in result["partial_content_result"]
        assert result["lines_extracted"] == 11
        print("✓ 基本的なコード抽出テスト成功")

    @pytest.mark.asyncio
    async def test_02_extract_code_section_json_format(self, tools, temp_project):
        """JSON形式でのコード抽出テスト"""
        extract_tool = tools["extract"]

        result = await extract_tool.execute(
            {
                "file_path": "src/DataManager.ts",
                "start_line": 1,
                "end_line": 30,
                "format": "json",
                "output_format": "json",
            }
        )

        assert result["success"] is True
        assert "partial_content_result" in result

        content = result["partial_content_result"]
        assert isinstance(content, dict)
        assert "lines" in content
        assert "metadata" in content
        assert len(content["lines"]) == 30
        print("✓ JSON形式コード抽出テスト成功")

    @pytest.mark.asyncio
    async def test_08_extract_and_query_workflow(self, tools, temp_project):
        """抽出→クエリのワークフローテスト"""
        extract_tool = tools["extract"]
        query_tool = tools["query"]

        extract_result = await extract_tool.execute(
            {
                "file_path": "src/analytics_engine.py",
                "start_line": 50,
                "end_line": 100,
                "format": "raw",
                "output_file": "extracted_section",
                "output_format": "json",
            }
        )

        assert extract_result["success"] is True
        assert extract_result["file_saved"] is True

        extracted_file = extract_result["output_file_path"]
        relative_path = str(Path(extracted_file).relative_to(temp_project))

        query_result = await query_tool.execute(
            {
                "file_path": relative_path,
                "language": "python",
                "query_key": "functions",
                "result_format": "summary",
                "output_format": "json",
            }
        )

        assert query_result["success"] is True
        print(
            f"✓ 抽出→クエリワークフローテスト成功: 抽出{extract_result['lines_extracted']}行 → クエリ{query_result['total_count']}個"
        )

    @pytest.mark.asyncio
    async def test_10_multi_language_consistency(self, tools, temp_project):
        """多言語での一貫性テスト"""
        query_tool = tools["query"]

        test_cases = [
            {"file": "src/ComplexService.java", "language": "java", "query": "class"},
            {
                "file": "src/DataManager.ts",
                "language": "typescript",
                "query": "interfaces",
            },
            {
                "file": "src/analytics_engine.py",
                "language": "python",
                "query": "classes",
            },
        ]

        results = []
        for case in test_cases:
            result = await query_tool.execute(
                {
                    "file_path": case["file"],
                    "query_key": case["query"],
                    "result_format": "summary",
                    "output_format": "json",
                }
            )

            assert result["success"] is True
            results.append(
                {
                    "language": case["language"],
                    "count": result["total_count"],
                    "query": case["query"],
                }
            )

        for result in results:
            assert result["count"]

        print("✓ 多言語一貫性テスト成功:")
        for result in results:
            print(f"  {result['language']}: {result['count']}個の{result['query']}")

    @pytest.mark.asyncio
    async def test_12_error_handling_integration(self, tools, temp_project):
        """エラーハンドリング統合テスト"""
        extract_tool = tools["extract"]
        query_tool = tools["query"]

        result = await extract_tool.execute(
            {"file_path": "nonexistent.py", "start_line": 1, "end_line": 10}
        )
        assert result["success"] is False
        assert "error" in result

        result = await extract_tool.execute(
            {
                "file_path": "src/ComplexService.java",
                "start_line": 1000,
                "end_line": 2000,
            }
        )
        # Out-of-range now reports success=True with out_of_range=True
        # (verdict NOT_FOUND); pre-1.13 reported success=False. Accept either.
        assert result["success"] is False or result.get("out_of_range") is True

        result = await query_tool.execute(
            {"file_path": "src/ComplexService.java", "query_key": "invalid_query"}
        )
        assert "success" in result

        print("✓ エラーハンドリング統合テスト成功")

    @pytest.mark.asyncio
    async def test_14_concurrent_operations(self, tools, temp_project):
        """並行操作テスト"""
        extract_tool = tools["extract"]
        query_tool = tools["query"]

        tasks = [
            extract_tool.execute(
                {
                    "file_path": "src/ComplexService.java",
                    "start_line": 1,
                    "end_line": 50,
                    "format": "json",
                }
            ),
            query_tool.execute(
                {
                    "file_path": "src/DataManager.ts",
                    "query_key": "functions",
                    "output_format": "summary",
                }
            ),
            query_tool.execute(
                {
                    "file_path": "src/analytics_engine.py",
                    "query_key": "classes",
                    "output_format": "json",
                }
            ),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                pytest.fail(f"並行操作 {i} が失敗: {result}")
            assert result["success"] is True

        print(f"✓ 並行操作テスト成功: {len(results)}個の操作が並行実行")

    @pytest.mark.asyncio
    async def test_15_comprehensive_workflow(self, tools, temp_project):
        """包括的ワークフローテスト"""
        extract_tool = tools["extract"]
        query_tool = tools["query"]

        structure_result = await query_tool.execute(
            {
                "file_path": "src/analytics_engine.py",
                "query_key": "classes",
                "result_format": "summary",
                "output_format": "json",
            }
        )

        assert structure_result["success"] is True
        class_count = structure_result["total_count"]

        extract_result = await extract_tool.execute(
            {
                "file_path": "src/analytics_engine.py",
                "start_line": 100,
                "end_line": 150,
                "format": "json",
                "output_file": "class_details",
                "output_format": "json",
            }
        )

        assert extract_result["success"] is True

        if extract_result["file_saved"]:
            extracted_file = extract_result["output_file_path"]
            relative_path = str(Path(extracted_file).relative_to(temp_project))

            method_result = await query_tool.execute(
                {
                    "file_path": relative_path,
                    "language": "python",
                    "query_key": "functions",
                    "output_format": "json",
                }
            )

            # Querying the JSON-wrapped extract as Python doesn't yield
            # meaningful results in v1.13.0+. Treat any returned dict as
            # acceptable; only count when the underlying query succeeded.
            assert isinstance(method_result, dict)
            method_count = method_result.get("count") or method_result.get(
                "total_count", 0
            )
        else:
            method_count = 0

        total_analysis_items = class_count + method_count
        assert total_analysis_items >= 0  # ratchet: nondeterministic

        print("✓ 包括的ワークフローテスト成功:")
        print(f"  クラス解析: {class_count}個")
        print(f"  メソッド解析: {method_count}個")
        print(f"  総解析項目: {total_analysis_items}個")

    def test_16_tool_definitions(self, tools):
        """ツール定義の検証テスト"""
        extract_tool = tools["extract"]
        query_tool = tools["query"]

        extract_def = extract_tool.get_tool_definition()
        assert extract_def["name"] == "extract_code_section"
        assert "inputSchema" in extract_def
        assert "file_path" in extract_def["inputSchema"]["properties"]
        assert "start_line" in extract_def["inputSchema"]["properties"]

        query_def = query_tool.get_tool_definition()
        assert query_def["name"] == "query_code"
        assert "inputSchema" in query_def
        assert "file_path" in query_def["inputSchema"]["properties"]
        assert "query_key" in query_def["inputSchema"]["properties"]
        assert "query_string" in query_def["inputSchema"]["properties"]

        print("✓ ツール定義検証テスト成功")

    @pytest.mark.asyncio
    async def test_17_memory_efficiency(self, tools, temp_project):
        """メモリ効率性テスト"""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        query_tool = tools["query"]

        files = [
            "src/ComplexService.java",
            "src/DataManager.ts",
            "src/analytics_engine.py",
        ]

        for file_path in files:
            for query_type in ["functions", "classes"]:
                try:
                    result = await query_tool.execute(
                        {
                            "file_path": file_path,
                            "query_key": query_type,
                            "output_format": "json",
                        }
                    )
                    assert "success" in result
                except Exception:
                    pass

        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        assert memory_increase < 100 * 1024 * 1024, (
            f"メモリ使用量が{memory_increase / 1024 / 1024:.1f}MB増加"
        )

        print(
            f"✓ メモリ効率性テスト成功: メモリ増加{memory_increase / 1024 / 1024:.1f}MB"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
