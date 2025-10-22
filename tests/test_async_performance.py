#!/usr/bin/env python3
"""Async performance tests"""

import asyncio
import os
import time
from pathlib import Path

import psutil
import pytest

from tree_sitter_analyzer.core.query_service import QueryService
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool


class TestAsyncPerformance:
    """非同期処理のパフォーマンステスト"""

    @pytest.fixture
    def small_python_file(self):
        """小さなPythonファイル"""
        # Create file in current directory to avoid security restrictions
        test_file = Path("test_small_file.py")
        try:
            test_file.write_text(
                """
def small_function():
    return "small"

class SmallClass:
    def method(self):
        pass
"""
            )
            yield str(test_file)
        finally:
            test_file.unlink(missing_ok=True)

    @pytest.fixture
    def medium_python_file(self):
        """中程度のPythonファイル"""
        # Create file in current directory to avoid security restrictions
        test_file = Path("test_medium_file.py")
        try:
            content = ""
            # 50個の関数とクラスを持つファイルを生成
            for i in range(50):
                content += f"""
def function_{i}():
    '''Function {i} for testing'''
    x = {i}
    y = x * 2
    z = y + 1
    return z

class Class_{i}:
    '''Class {i} for testing'''
    def __init__(self):
        self.value = {i}

    def method_{i}(self):
        return self.value * 2

    def calculate_{i}(self, x, y):
        return x + y + self.value
"""
            test_file.write_text(content)
            yield str(test_file)
        finally:
            test_file.unlink(missing_ok=True)

    @pytest.fixture
    def large_python_file(self):
        """大きなPythonファイル"""
        # Create file in current directory to avoid security restrictions
        test_file = Path("test_large_file.py")
        try:
            content = ""
            # 200個の関数とクラスを持つファイルを生成
            for i in range(200):
                content += f"""
def function_{i}():
    '''Function {i} for performance testing'''
    result = 0
    for j in range(10):
        result += j * {i}
    return result

class Class_{i}:
    '''Class {i} for performance testing'''
    def __init__(self):
        self.value = {i}
        self.data = [x for x in range(10)]

    def method_{i}(self):
        return sum(self.data) + self.value

    def complex_method_{i}(self, x, y, z):
        result = x + y + z
        for item in self.data:
            result += item * self.value
        return result

    @property
    def property_{i}(self):
        return self.value * 2
"""
            test_file.write_text(content)
            yield str(test_file)
        finally:
            test_file.unlink(missing_ok=True)

    @pytest.fixture
    def multiple_files(self):
        """複数のテストファイル"""
        files = []
        try:
            for i in range(5):
                test_file = Path(f"test_multi_{i}.py")
                content = ""
                for j in range(20):
                    content += f"""
def file_{i}_function_{j}():
    return {i} * {j}

class File_{i}_Class_{j}:
    def method(self):
        return {i} + {j}
"""
                test_file.write_text(content)
                files.append(str(test_file))

            yield files
        finally:
            for file_path in files:
                Path(file_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_performance_baseline_small_file(self, small_python_file):
        """小さなファイルのパフォーマンスベースライン"""
        service = QueryService()

        start_time = time.time()

        results = await service.execute_query(
            file_path=small_python_file, language="python", query_key="function"
        )

        end_time = time.time()
        duration = end_time - start_time

        # 結果の確認
        assert results is not None
        assert len(results) >= 1  # small_function

        # パフォーマンス要件: 1秒以内
        assert duration < 1.0, f"Small file query took too long: {duration:.3f}s"

        print(f"Small file performance: {duration:.3f}s for {len(results)} results")

    @pytest.mark.asyncio
    async def test_performance_baseline_medium_file(self, medium_python_file):
        """中程度のファイルのパフォーマンスベースライン"""
        service = QueryService()

        start_time = time.time()

        results = await service.execute_query(
            file_path=medium_python_file, language="python", query_key="function"
        )

        end_time = time.time()
        duration = end_time - start_time

        # 結果の確認
        assert results is not None
        assert len(results) >= 50  # 50個の関数

        # パフォーマンス要件: 3秒以内
        assert duration < 3.0, f"Medium file query took too long: {duration:.3f}s"

        print(f"Medium file performance: {duration:.3f}s for {len(results)} results")

    @pytest.mark.asyncio
    async def test_performance_baseline_large_file(self, large_python_file):
        """大きなファイルのパフォーマンスベースライン"""
        service = QueryService()

        start_time = time.time()

        results = await service.execute_query(
            file_path=large_python_file, language="python", query_key="function"
        )

        end_time = time.time()
        duration = end_time - start_time

        # 結果の確認
        assert results is not None
        assert len(results) >= 200  # 200個の関数

        # パフォーマンス要件: 5秒以内
        assert duration < 5.0, f"Large file query took too long: {duration:.3f}s"

        print(f"Large file performance: {duration:.3f}s for {len(results)} results")

    @pytest.mark.asyncio
    async def test_concurrent_performance_comparison(self, medium_python_file):
        """並行処理と逐次処理のパフォーマンス比較"""
        service = QueryService()

        # 逐次実行
        start_time = time.time()
        for _ in range(3):
            await service.execute_query(
                file_path=medium_python_file, language="python", query_key="function"
            )
        sequential_time = time.time() - start_time

        # 並行実行
        start_time = time.time()
        tasks = [
            service.execute_query(
                file_path=medium_python_file, language="python", query_key="function"
            )
            for _ in range(3)
        ]
        results = await asyncio.gather(*tasks)
        concurrent_time = time.time() - start_time

        # 結果の確認
        for result in results:
            assert result is not None
            assert len(result) >= 50

        # 並行実行が効率的であることを確認（少なくとも5%の改善、または同等の性能）
        efficiency = sequential_time / concurrent_time
        assert (
            efficiency > 0.95
        ), f"Concurrent execution not efficient enough: {efficiency:.2f}x"

        print(
            f"Sequential: {sequential_time:.3f}s, Concurrent: {concurrent_time:.3f}s, Efficiency: {efficiency:.2f}x"
        )

    @pytest.mark.asyncio
    async def test_multiple_files_concurrent_performance(self, multiple_files):
        """複数ファイルの並行処理パフォーマンス"""
        service = QueryService()

        # 逐次実行
        start_time = time.time()
        for file_path in multiple_files:
            await service.execute_query(
                file_path=file_path, language="python", query_key="function"
            )
        sequential_time = time.time() - start_time

        # 並行実行
        start_time = time.time()
        tasks = [
            service.execute_query(
                file_path=file_path, language="python", query_key="function"
            )
            for file_path in multiple_files
        ]
        results = await asyncio.gather(*tasks)
        concurrent_time = time.time() - start_time

        # 結果の確認
        for result in results:
            assert result is not None
            assert len(result) >= 20  # 各ファイルに20個の関数

        # 並行実行が効率的であることを確認
        efficiency = sequential_time / concurrent_time
        assert (
            efficiency > 1.2
        ), f"Multi-file concurrent execution not efficient: {efficiency:.2f}x"

        print(
            f"Multi-file Sequential: {sequential_time:.3f}s, Concurrent: {concurrent_time:.3f}s, Efficiency: {efficiency:.2f}x"
        )

    @pytest.mark.asyncio
    async def test_memory_usage_monitoring(self, large_python_file):
        """メモリ使用量の監視"""
        service = QueryService()
        process = psutil.Process(os.getpid())

        # 初期メモリ使用量
        initial_memory = process.memory_info().rss

        # クエリ実行
        results = await service.execute_query(
            file_path=large_python_file, language="python", query_key="function"
        )

        # 実行後メモリ使用量
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # 結果の確認
        assert results is not None
        assert len(results) >= 200

        # メモリ増加が10%以内であることを確認
        memory_increase_percent = (memory_increase / initial_memory) * 100
        assert (
            memory_increase_percent < 10.0
        ), f"Memory increase too high: {memory_increase_percent:.2f}%"

        print(
            f"Memory increase: {memory_increase_percent:.2f}% ({memory_increase / 1024 / 1024:.2f} MB)"
        )

    @pytest.mark.asyncio
    async def test_memory_usage_concurrent_execution(self, medium_python_file):
        """並行実行時のメモリ使用量"""
        service = QueryService()
        process = psutil.Process(os.getpid())

        # 初期メモリ使用量
        initial_memory = process.memory_info().rss

        # 10個の並行タスクを実行
        tasks = [
            service.execute_query(
                file_path=medium_python_file, language="python", query_key="function"
            )
            for _ in range(10)
        ]
        results = await asyncio.gather(*tasks)

        # 実行後メモリ使用量
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # 結果の確認
        for result in results:
            assert result is not None
            assert len(result) >= 50

        # メモリ増加が15%以内であることを確認（並行実行なので少し緩い制限）
        memory_increase_percent = (memory_increase / initial_memory) * 100
        assert (
            memory_increase_percent < 15.0
        ), f"Concurrent memory increase too high: {memory_increase_percent:.2f}%"

        print(
            f"Concurrent memory increase: {memory_increase_percent:.2f}% ({memory_increase / 1024 / 1024:.2f} MB)"
        )

    @pytest.mark.asyncio
    async def test_mcp_tool_performance(self, medium_python_file):
        """MCPツールのパフォーマンステスト"""
        import os

        tool = QueryTool(project_root=os.getcwd())

        start_time = time.time()

        result = await tool.execute(
            {"file_path": medium_python_file, "query_key": "function"}
        )

        end_time = time.time()
        duration = end_time - start_time

        # 結果の確認
        assert result["success"] is True
        assert result["count"] >= 50

        # パフォーマンス要件: 3秒以内
        assert duration < 3.0, f"MCP tool execution took too long: {duration:.3f}s"

        print(f"MCP tool performance: {duration:.3f}s for {result['count']} results")

    @pytest.mark.asyncio
    async def test_stress_test_high_concurrency(self, small_python_file):
        """高並行性ストレステスト"""
        service = QueryService()

        # 50個の並行タスクを実行
        start_time = time.time()
        tasks = [
            service.execute_query(
                file_path=small_python_file, language="python", query_key="function"
            )
            for _ in range(50)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()
        duration = end_time - start_time

        # 結果の確認
        successful_results = 0
        for result in results:
            if isinstance(result, list) and len(result) >= 1:
                successful_results += 1
            elif isinstance(result, Exception):
                print(f"Task failed with exception: {result}")

        # 少なくとも80%のタスクが成功することを確認
        success_rate = successful_results / len(tasks)
        assert success_rate >= 0.8, f"Success rate too low: {success_rate:.2f}"

        # パフォーマンス要件: 10秒以内
        assert duration < 10.0, f"High concurrency test took too long: {duration:.3f}s"

        print(
            f"High concurrency: {successful_results}/{len(tasks)} successful in {duration:.3f}s"
        )

    @pytest.mark.asyncio
    async def test_throughput_measurement(self, small_python_file):
        """スループット測定"""
        service = QueryService()

        # 1分間でどれだけのクエリを処理できるかを測定
        start_time = time.time()
        completed_queries = 0
        timeout = 10.0  # テスト時間を10秒に短縮

        while time.time() - start_time < timeout:
            try:
                result = await asyncio.wait_for(
                    service.execute_query(
                        file_path=small_python_file,
                        language="python",
                        query_key="function",
                    ),
                    timeout=1.0,
                )
                if result is not None:
                    completed_queries += 1
            except asyncio.TimeoutError:
                break
            except Exception as e:
                print(f"Query failed: {e}")

        end_time = time.time()
        actual_duration = end_time - start_time
        throughput = completed_queries / actual_duration

        # スループット要件: 1秒あたり5クエリ以上
        assert throughput >= 5.0, f"Throughput too low: {throughput:.2f} queries/sec"

        print(
            f"Throughput: {throughput:.2f} queries/sec ({completed_queries} queries in {actual_duration:.2f}s)"
        )

    @pytest.mark.asyncio
    async def test_latency_measurement(self, small_python_file):
        """レイテンシ測定"""
        service = QueryService()

        latencies = []

        # 20回のクエリ実行でレイテンシを測定
        for _ in range(20):
            start_time = time.time()

            result = await service.execute_query(
                file_path=small_python_file, language="python", query_key="function"
            )

            end_time = time.time()
            latency = end_time - start_time
            latencies.append(latency)

            assert result is not None

        # 統計計算
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        min_latency = min(latencies)

        # レイテンシ要件
        assert avg_latency < 0.5, f"Average latency too high: {avg_latency:.3f}s"
        assert max_latency < 1.0, f"Max latency too high: {max_latency:.3f}s"

        print(
            f"Latency - Avg: {avg_latency:.3f}s, Min: {min_latency:.3f}s, Max: {max_latency:.3f}s"
        )

    @pytest.mark.asyncio
    async def test_cpu_usage_monitoring(self, medium_python_file):
        """CPU使用率の監視"""
        service = QueryService()
        process = psutil.Process(os.getpid())

        # CPU使用率の測定開始
        process.cpu_percent()  # 初期化

        start_time = time.time()

        # 複数のクエリを並行実行
        tasks = [
            service.execute_query(
                file_path=medium_python_file, language="python", query_key="function"
            )
            for _ in range(5)
        ]
        results = await asyncio.gather(*tasks)

        end_time = time.time()
        duration = end_time - start_time

        # CPU使用率の取得
        cpu_percent = process.cpu_percent()

        # 結果の確認
        for result in results:
            assert result is not None
            assert len(result) >= 50

        print(f"CPU usage: {cpu_percent:.2f}% during {duration:.3f}s execution")

        # CPU使用率が異常に高くないことを確認（100%を超えることもあるが、200%以下であることを確認）
        assert cpu_percent < 200.0, f"CPU usage too high: {cpu_percent:.2f}%"

    @pytest.mark.asyncio
    async def test_file_io_performance(self, large_python_file):
        """ファイルI/Oパフォーマンステスト"""
        service = QueryService()

        # ファイルサイズの確認
        file_size = Path(large_python_file).stat().st_size

        start_time = time.time()

        # 非同期ファイル読み込みのテスト
        if hasattr(service, "_read_file_async"):
            content, encoding = await service._read_file_async(large_python_file)

            end_time = time.time()
            duration = end_time - start_time

            # 結果の確認
            assert isinstance(content, str)
            assert len(content) > 0
            assert isinstance(encoding, str)

            # I/Oパフォーマンス: 1MB/秒以上
            throughput_mbps = (file_size / 1024 / 1024) / duration
            assert (
                throughput_mbps > 1.0
            ), f"File I/O too slow: {throughput_mbps:.2f} MB/s"

            print(
                f"File I/O performance: {throughput_mbps:.2f} MB/s ({file_size / 1024:.2f} KB in {duration:.3f}s)"
            )
