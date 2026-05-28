#!/usr/bin/env python3
"""
Phase 7: Performance Integration Tests

エンタープライズグレードのパフォーマンス統合テスト:
- 実世界の負荷条件下でのパフォーマンス検証
- スケーラビリティテスト
- メモリ効率性テスト
- 同時実行性能テスト
"""

import asyncio
import gc
import tempfile
from pathlib import Path

import psutil
import pytest

from tests.integration._test_phase7_performance_integration_helpers import (
    PerformanceProfiler,
    create_large_scale_structure,
    nonnegative_float_from_env,
    positive_int_from_env,
)
from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool as TableFormatTool,
)
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool

DEFAULT_SUSTAINED_LOAD_ITERATIONS = 12
DEFAULT_SUSTAINED_LOAD_INTERVAL_SECONDS = 0.05
DEFAULT_SCALABILITY_RECOVERY_SECONDS = 0.05
DEFAULT_RESOURCE_CLEANUP_SETTLE_SECONDS = 0.05
DEFAULT_MEMORY_EFFICIENCY_FILES = 8

_SEARCH_QUERIES = ["class", "function", "import", "def", "const"]


def _create_task_for_tool(tool, i: int, project_root: str):
    """Return an execute coroutine for the given tool/index, or None if no files."""
    if isinstance(tool, AnalyzeScaleTool):
        java_files = list(Path(project_root).glob("src/main/java/**/*.java"))
        if not java_files:
            return None
        return tool.execute({"file_path": str(java_files[i % len(java_files)])})
    if isinstance(tool, TableFormatTool):
        python_files = list(Path(project_root).glob("python/**/*.py"))
        if not python_files:
            return None
        return tool.execute(
            {
                "file_path": str(python_files[i % len(python_files)]),
                "format_type": "compact",
            }
        )
    if isinstance(tool, SearchContentTool):
        return tool.execute(
            {
                "roots": [project_root],
                "query": _SEARCH_QUERIES[i % len(_SEARCH_QUERIES)],
                "max_count": 10,
            }
        )
    return None


class TestPhase7PerformanceIntegration:
    """Phase 7 パフォーマンス統合テスト"""

    @pytest.fixture(scope="class")
    def large_scale_project(self):
        """大規模プロジェクト作成（パフォーマンステスト用）"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            # 大量のファイルを作成
            create_large_scale_structure(project_root)

            yield str(project_root)

    @pytest.mark.requires_fd
    @pytest.mark.requires_ripgrep
    @pytest.mark.asyncio
    async def test_large_scale_file_analysis_performance(self, large_scale_project):
        """大規模ファイル分析のパフォーマンステスト"""
        profiler = PerformanceProfiler()
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(large_scale_project)

        profiler.start_profiling()

        # 1. 全ファイル一覧取得（180ファイル）
        list_tool = ListFilesTool(large_scale_project)
        file_list_result = await list_tool.execute(
            {
                "roots": [large_scale_project],
                "extensions": ["java", "py", "js"],
                "limit": 200,
            }
        )

        assert file_list_result["success"]
        assert file_list_result["count"] == 180  # 100 Java + 50 Python + 30 JS

        # 2. 複数ファイルの並行分析
        scale_tool = AnalyzeScaleTool(large_scale_project)
        analysis_tasks = []

        # 各言語から5ファイルずつ選択
        test_files = [
            "src/main/java/com/enterprise/package0/GeneratedClass0.java",
            "src/main/java/com/enterprise/package1/GeneratedClass10.java",
            "src/main/java/com/enterprise/package2/GeneratedClass20.java",
            "python/modules/module_0.py",
            "python/modules/module_10.py",
            "python/modules/module_20.py",
            "frontend/src/components/GeneratedComponent0.js",
            "frontend/src/components/GeneratedComponent10.js",
            "frontend/src/components/GeneratedComponent20.js",
        ]

        for file_path in test_files:
            full_path = Path(large_scale_project) / file_path
            if full_path.exists():
                task = scale_tool.execute(
                    {"file_path": str(full_path), "include_complexity": True}
                )
                analysis_tasks.append(task)

        # 並行実行
        results = await asyncio.gather(*analysis_tasks)

        metrics = profiler.end_profiling()

        # パフォーマンス要件検証
        assert metrics["execution_time"] < 15.0, (
            f"実行時間が15秒を超過: {metrics['execution_time']:.2f}秒"
        )
        assert metrics["memory_mb"] < 200, (
            f"メモリ使用量が200MBを超過: {metrics['memory_mb']:.2f}MB"
        )

        # 結果検証
        successful_analyses = [r for r in results if r["success"]]
        assert len(successful_analyses) >= len(test_files) * 0.8, (
            "80%以上の分析が成功する必要があります"
        )

        print(f"大規模分析完了: {len(successful_analyses)}/{len(test_files)} 成功")
        print(
            f"実行時間: {metrics['execution_time']:.2f}秒, メモリ: {metrics['memory_mb']:.2f}MB"
        )

    @pytest.mark.requires_fd
    @pytest.mark.requires_ripgrep
    @pytest.mark.asyncio
    async def test_concurrent_search_performance(self, large_scale_project):
        """同時検索のパフォーマンステスト"""
        profiler = PerformanceProfiler()
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(large_scale_project)

        profiler.start_profiling()

        # 複数の検索クエリを並行実行
        search_tool = SearchContentTool(large_scale_project)
        search_queries = [
            ("class", ["*.java", "*.py", "*.js"]),
            ("function", ["*.py", "*.js"]),
            ("import", ["*.java", "*.py", "*.js"]),
            ("public", ["*.java"]),
            ("def ", ["*.py"]),
            ("const", ["*.js"]),
            ("useState", ["*.js"]),
            ("@dataclass", ["*.py"]),
            ("private", ["*.java"]),
            ("export", ["*.js"]),
        ]

        search_tasks = []
        for query, globs in search_queries:
            task = search_tool.execute(
                {
                    "roots": [large_scale_project],
                    "query": query,
                    "include_globs": globs,
                    "max_count": 50,
                }
            )
            search_tasks.append(task)

        # 並行実行
        results = await asyncio.gather(*search_tasks, return_exceptions=True)

        metrics = profiler.end_profiling()

        # パフォーマンス要件検証
        assert metrics["execution_time"] < 30.0, (
            f"検索実行時間が30秒を超過: {metrics['execution_time']:.2f}秒"
        )
        assert metrics["memory_mb"] < 150, (
            f"メモリ使用量が150MBを超過: {metrics['memory_mb']:.2f}MB"
        )

        # 結果検証
        successful_searches = [
            r for r in results if isinstance(r, dict) and r.get("success")
        ]
        assert len(successful_searches) >= len(search_queries) * 0.8, (
            "80%以上の検索が成功する必要があります"
        )

        total_matches = sum(r.get("count", 0) for r in successful_searches)
        assert total_matches > 0, "検索結果が見つからない"

        print(f"同時検索完了: {len(successful_searches)}/{len(search_queries)} 成功")
        print(
            f"総マッチ数: {total_matches}, 実行時間: {metrics['execution_time']:.2f}秒"
        )

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_memory_efficiency_under_load(self, large_scale_project):
        """負荷下でのメモリ効率性テスト"""
        profiler = PerformanceProfiler()
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(large_scale_project)

        # 初期メモリ使用量
        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024

        # 大量のファイル処理
        table_tool = TableFormatTool(large_scale_project)
        memory_measurements = []
        sample_file_count = positive_int_from_env(
            "TSA_MEMORY_EFFICIENCY_FILES",
            DEFAULT_MEMORY_EFFICIENCY_FILES,
        )

        # 複数ファイルを順次処理。長時間の専用検証では環境変数で拡張できる。
        java_files = list(Path(large_scale_project).glob("src/main/java/**/*.java"))[
            :sample_file_count
        ]

        for i, java_file in enumerate(java_files):
            profiler.start_profiling()

            result = await table_tool.execute(
                {
                    "file_path": str(java_file),
                    "format_type": "full",
                    "suppress_output": True,  # メモリ最適化
                    "output_file": f"temp_output_{i}",
                }
            )

            metrics = profiler.end_profiling()
            current_memory = psutil.Process().memory_info().rss / 1024 / 1024

            memory_measurements.append(
                {
                    "file_index": i,
                    "memory_used": metrics["memory_mb"],
                    "total_memory": current_memory,
                    "execution_time": metrics["execution_time"],
                }
            )

            assert result["success"], f"ファイル {i} の処理に失敗"

            # ガベージコレクション
            if i % 5 == 0:
                gc.collect()

        # メモリ効率性検証
        final_memory = psutil.Process().memory_info().rss / 1024 / 1024
        memory_growth = final_memory - initial_memory

        # メモリ増加が合理的な範囲内であることを確認
        assert memory_growth < 300, f"メモリ増加が300MBを超過: {memory_growth:.2f}MB"

        # 平均実行時間が合理的であることを確認
        avg_execution_time = sum(
            m["execution_time"] for m in memory_measurements
        ) / len(memory_measurements)
        assert avg_execution_time < 2.0, (
            f"平均実行時間が2秒を超過: {avg_execution_time:.2f}秒"
        )

        print("メモリ効率性テスト完了:")
        print(f"初期メモリ: {initial_memory:.2f}MB")
        print(f"最終メモリ: {final_memory:.2f}MB")
        print(f"メモリ増加: {memory_growth:.2f}MB")
        print(f"平均実行時間: {avg_execution_time:.2f}秒")

    @pytest.mark.requires_fd
    @pytest.mark.slow
    @pytest.mark.requires_ripgrep
    @pytest.mark.asyncio
    async def test_scalability_limits(self, large_scale_project):
        """スケーラビリティ限界テスト"""
        profiler = PerformanceProfiler()
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(large_scale_project)

        # 段階的に負荷を増加
        load_levels = [5, 10, 20, 30]
        recovery_interval = nonnegative_float_from_env(
            "TSA_SCALABILITY_RECOVERY_SECONDS",
            DEFAULT_SCALABILITY_RECOVERY_SECONDS,
        )
        scalability_results = []

        for load_level in load_levels:
            profiler.start_profiling()

            # 指定された数のタスクを並行実行
            tasks = []
            tools = [
                AnalyzeScaleTool(large_scale_project),
                TableFormatTool(large_scale_project),
                SearchContentTool(large_scale_project),
            ]

            for i in range(load_level):
                task = _create_task_for_tool(
                    tools[i % len(tools)], i, large_scale_project
                )
                if task is not None:
                    tasks.append(task)

            # 並行実行
            results = await asyncio.gather(*tasks, return_exceptions=True)
            metrics = profiler.end_profiling()

            # 結果分析
            successful_tasks = [
                r for r in results if isinstance(r, dict) and r.get("success")
            ]
            error_tasks = [r for r in results if isinstance(r, Exception)]

            success_rate = len(successful_tasks) / len(results) if results else 0

            scalability_results.append(
                {
                    "load_level": load_level,
                    "execution_time": metrics["execution_time"],
                    "memory_mb": metrics["memory_mb"],
                    "success_rate": success_rate,
                    "successful_tasks": len(successful_tasks),
                    "error_tasks": len(error_tasks),
                }
            )

            print(
                f"負荷レベル {load_level}: {metrics['execution_time']:.2f}秒, "
                f"成功率: {success_rate:.2%}, メモリ: {metrics['memory_mb']:.2f}MB"
            )

            # 基本的な要件確認
            assert success_rate >= 0.7, (
                f"負荷レベル {load_level} で成功率が70%を下回りました: {success_rate:.2%}"
            )

            # 短い休憩でシステム回復
            if recovery_interval:
                await asyncio.sleep(recovery_interval)

        # スケーラビリティ分析
        max_load_result = scalability_results[-1]
        assert max_load_result["execution_time"] < 60.0, (
            "最大負荷での実行時間が60秒を超過"
        )
        assert max_load_result["memory_mb"] < 500, (
            "最大負荷でのメモリ使用量が500MBを超過"
        )

        print("スケーラビリティテスト完了:")
        for result in scalability_results:
            print(
                f"  負荷 {result['load_level']}: {result['execution_time']:.2f}秒, "
                f"成功率 {result['success_rate']:.2%}, メモリ {result['memory_mb']:.2f}MB"
            )

    @pytest.mark.requires_fd
    @pytest.mark.slow
    @pytest.mark.requires_ripgrep
    @pytest.mark.asyncio
    async def test_sustained_load_performance(self, large_scale_project):
        """持続負荷パフォーマンステスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(large_scale_project)

        sample_count = positive_int_from_env(
            "TSA_SUSTAINED_LOAD_ITERATIONS",
            DEFAULT_SUSTAINED_LOAD_ITERATIONS,
        )
        sample_interval = nonnegative_float_from_env(
            "TSA_SUSTAINED_LOAD_INTERVAL_SECONDS",
            DEFAULT_SUSTAINED_LOAD_INTERVAL_SECONDS,
        )
        performance_samples = []

        for iteration in range(1, sample_count + 1):
            profiler = PerformanceProfiler()
            profiler.start_profiling()

            # 軽量なタスクを実行
            search_tool = SearchContentTool(large_scale_project)
            result = await search_tool.execute(
                {
                    "roots": [large_scale_project],
                    "query": f"class{iteration % 10}",
                    "max_count": 5,
                    "total_only": True,  # 軽量化
                }
            )

            metrics = profiler.end_profiling()

            performance_samples.append(
                {
                    "iteration": iteration,
                    "execution_time": metrics["execution_time"],
                    "memory_mb": metrics["memory_mb"],
                    "success": isinstance(result, dict)
                    and result.get("success", False)
                    or isinstance(result, int),
                }
            )

            # 短い間隔
            if sample_interval:
                await asyncio.sleep(sample_interval)

        # 持続負荷分析
        successful_iterations = [s for s in performance_samples if s["success"]]
        total_iterations = len(performance_samples)
        success_rate = (
            len(successful_iterations) / total_iterations if total_iterations > 0 else 0
        )

        avg_execution_time = (
            sum(s["execution_time"] for s in successful_iterations)
            / len(successful_iterations)
            if successful_iterations
            else 0
        )
        avg_memory = (
            sum(s["memory_mb"] for s in successful_iterations)
            / len(successful_iterations)
            if successful_iterations
            else 0
        )

        # 持続負荷要件検証
        assert success_rate >= 0.95, (
            f"持続負荷での成功率が95%を下回りました: {success_rate:.2%}"
        )
        assert avg_execution_time < 3.0, (
            f"平均実行時間が3秒を超過: {avg_execution_time:.2f}秒"
        )
        assert avg_memory < 100, f"平均メモリ使用量が100MBを超過: {avg_memory:.2f}MB"

        print("持続負荷テスト完了:")
        print(f"総反復回数: {total_iterations}")
        print(f"成功率: {success_rate:.2%}")
        print(f"平均実行時間: {avg_execution_time:.2f}秒")
        print(f"平均メモリ使用量: {avg_memory:.2f}MB")

    @pytest.mark.requires_fd
    @pytest.mark.slow
    @pytest.mark.requires_ripgrep
    @pytest.mark.asyncio
    async def test_resource_cleanup_efficiency(self, large_scale_project):
        """リソースクリーンアップ効率性テスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(large_scale_project)

        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024
        cleanup_settle_seconds = nonnegative_float_from_env(
            "TSA_RESOURCE_CLEANUP_SETTLE_SECONDS",
            DEFAULT_RESOURCE_CLEANUP_SETTLE_SECONDS,
        )

        # 大量のタスクを実行してリソースを消費
        for cycle in range(5):
            print(f"リソース消費サイクル {cycle + 1}/5")

            # 複数のツールを使用
            tools_and_params = [
                (
                    AnalyzeScaleTool(large_scale_project),
                    {
                        "file_path": str(
                            list(Path(large_scale_project).glob("**/*.java"))[0]
                        ),
                        "include_complexity": True,
                    },
                ),
                (
                    TableFormatTool(large_scale_project),
                    {
                        "file_path": str(
                            list(Path(large_scale_project).glob("**/*.py"))[0]
                        ),
                        "format_type": "full",
                    },
                ),
                (
                    SearchContentTool(large_scale_project),
                    {
                        "roots": [large_scale_project],
                        "query": "class",
                        "max_count": 100,
                    },
                ),
            ]

            # 各ツールを実行
            for tool, params in tools_and_params:
                result = await tool.execute(params)
                assert result["success"], f"サイクル {cycle} でツール実行に失敗"

            # 明示的なガベージコレクション
            gc.collect()

            current_memory = psutil.Process().memory_info().rss / 1024 / 1024
            memory_growth = current_memory - initial_memory

            print(f"  サイクル {cycle + 1} 後のメモリ増加: {memory_growth:.2f}MB")

            # メモリ増加が制御されていることを確認
            assert memory_growth < 200, (
                f"サイクル {cycle} でメモリ増加が200MBを超過: {memory_growth:.2f}MB"
            )

        # 最終クリーンアップ
        gc.collect()
        if cleanup_settle_seconds:
            await asyncio.sleep(cleanup_settle_seconds)

        final_memory = psutil.Process().memory_info().rss / 1024 / 1024
        total_growth = final_memory - initial_memory

        print("リソースクリーンアップテスト完了:")
        print(f"初期メモリ: {initial_memory:.2f}MB")
        print(f"最終メモリ: {final_memory:.2f}MB")
        print(f"総メモリ増加: {total_growth:.2f}MB")

        # 最終的なメモリ増加が合理的であることを確認
        assert total_growth < 150, f"総メモリ増加が150MBを超過: {total_growth:.2f}MB"

    @pytest.mark.asyncio
    async def test_error_recovery_performance(self, large_scale_project):
        """エラー回復パフォーマンステスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(large_scale_project)

        profiler = PerformanceProfiler()
        profiler.start_profiling()

        # 意図的にエラーを発生させるタスクと正常なタスクを混在
        tasks = []

        # 正常なタスク
        valid_java_file = str(list(Path(large_scale_project).glob("**/*.java"))[0])
        scale_tool = AnalyzeScaleTool(large_scale_project)

        for _i in range(5):
            task = scale_tool.execute(
                {"file_path": valid_java_file, "include_complexity": True}
            )
            tasks.append(("valid", task))

        # エラーを発生させるタスク
        for _i in range(3):
            task = scale_tool.execute(
                {
                    "file_path": "/nonexistent/file.java",  # 存在しないファイル
                    "include_complexity": True,
                }
            )
            tasks.append(("error", task))

        # 並行実行
        task_results = await asyncio.gather(
            *[task for _, task in tasks], return_exceptions=True
        )

        metrics = profiler.end_profiling()

        # 結果分析
        valid_results = []
        error_results = []

        for _i, (task_type, result) in enumerate(
            zip([t[0] for t in tasks], task_results, strict=False)
        ):
            if task_type == "valid":
                valid_results.append(result)
            else:
                error_results.append(result)

        # 正常なタスクが影響を受けていないことを確認
        successful_valid = [
            r for r in valid_results if isinstance(r, dict) and r.get("success")
        ]
        assert len(successful_valid) == 5, "エラーが正常なタスクに影響を与えました"

        # エラー処理が適切に行われていることを確認（例外またはエラー辞書）
        handled_errors = []
        for r in error_results:
            if isinstance(r, Exception):
                handled_errors.append(r)  # 例外として処理された
            elif isinstance(r, dict) and not r.get("success", True):
                handled_errors.append(r)  # エラー辞書として処理された

        assert len(handled_errors) >= 2, (
            f"エラーが適切に処理されていません: {len(handled_errors)}/3"
        )

        # パフォーマンスが大幅に劣化していないことを確認
        assert metrics["execution_time"] < 10.0, (
            f"エラー混在時の実行時間が10秒を超過: {metrics['execution_time']:.2f}秒"
        )

        print("エラー回復パフォーマンステスト完了:")
        print(f"正常タスク成功: {len(successful_valid)}/5")
        print(f"エラー処理: {len(handled_errors)}/3")
        print(f"実行時間: {metrics['execution_time']:.2f}秒")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
