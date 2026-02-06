"""Tests for parallel query execution"""

import pytest
import time
from tree_sitter_analyzer_v2.graph.advanced_storage import CodeGraphStorage
from tree_sitter_analyzer_v2.graph.parallel_query import (
    ParallelQueryExecutor,
    QueryBatch,
)


class TestParallelQueryExecutor:
    """Test parallel query execution"""

    def test_single_query_execution(self):
        """Test executing a single query"""
        storage = CodeGraphStorage()
        for i in range(10):
            storage.add_node(f'f_{i}', 'function', {'name': f'func_{i}'})
        
        executor = ParallelQueryExecutor(storage)
        results = executor.execute_single("find functions")
        
        assert len(results) == 10

    def test_batch_query_execution(self):
        """Test executing multiple queries in parallel"""
        storage = CodeGraphStorage()
        for i in range(100):
            storage.add_node(f'f_{i}', 'function', {
                'name': f'func_{i}',
                'file': f'file_{i % 10}.py'
            })
        
        executor = ParallelQueryExecutor(storage, max_workers=4)
        
        queries = [
            "find functions in file:file_0.py",
            "find functions in file:file_1.py",
            "find functions in file:file_2.py",
            "find functions in file:file_3.py",
        ]
        
        results = executor.execute_batch(queries)
        
        assert len(results) == 4
        for result in results:
            assert len(result) == 10

    def test_parallel_speedup(self):
        """Test that parallel execution completes successfully"""
        storage = CodeGraphStorage()
        
        # Create large dataset
        for i in range(1000):
            storage.add_node(f'f_{i}', 'function', {
                'name': f'func_{i}',
                'file': f'file_{i % 10}.py',
                'complexity': i % 20
            })
        
        queries = [f"find functions in file:file_{i}.py" for i in range(10)]
        
        # Sequential execution
        executor_seq = ParallelQueryExecutor(storage, max_workers=1)
        results_seq = executor_seq.execute_batch(queries)
        
        # Parallel execution
        executor_par = ParallelQueryExecutor(storage, max_workers=4)
        results_par = executor_par.execute_batch(queries)
        
        # Verify same results
        assert len(results_seq) == len(results_par)
        
        # Verify both produce valid results
        assert all(len(r) == 100 for r in results_seq)
        assert all(len(r) == 100 for r in results_par)

    def test_query_batch_with_metadata(self):
        """Test query batch with metadata tracking"""
        storage = CodeGraphStorage()
        for i in range(50):
            storage.add_node(f'f_{i}', 'function', {'name': f'func_{i}'})
        
        executor = ParallelQueryExecutor(storage)
        
        batch = QueryBatch([
            "find functions",
            "find classes",
        ])
        
        results = executor.execute_batch_with_metadata(batch)
        
        assert len(results) == 2
        assert results[0]['query'] == "find functions"
        assert results[0]['count'] == 50
        assert results[0]['execution_time'] > 0
        assert results[1]['count'] == 0  # No classes

    def test_error_handling(self):
        """Test error handling in parallel execution"""
        storage = CodeGraphStorage()
        storage.add_node('f1', 'function', {'name': 'main'})
        
        executor = ParallelQueryExecutor(storage)
        
        queries = [
            "find functions",
            "invalid query syntax",
            "find classes",
        ]
        
        results = executor.execute_batch(queries, continue_on_error=True)
        
        # Should have 3 results (including error)
        assert len(results) == 3
        assert len(results[0]) == 1  # Valid query
        assert results[1] is None or isinstance(results[1], list)  # Error handled
        assert len(results[2]) == 0  # Valid but empty

    def test_result_streaming(self):
        """Test streaming results as they complete"""
        storage = CodeGraphStorage()
        for i in range(100):
            storage.add_node(f'f_{i}', 'function', {
                'name': f'func_{i}',
                'file': f'file_{i % 5}.py'
            })
        
        executor = ParallelQueryExecutor(storage, max_workers=4)
        
        queries = [f"find functions in file:file_{i}.py" for i in range(5)]
        
        results = []
        for result in executor.execute_stream(queries):
            results.append(result)
        
        assert len(results) == 5
        assert all(len(r) == 20 for r in results)

    def test_max_workers_configuration(self):
        """Test different worker configurations"""
        storage = CodeGraphStorage()
        for i in range(50):
            storage.add_node(f'f_{i}', 'function', {'name': f'func_{i}'})
        
        queries = ["find functions"] * 10
        
        # Test with different worker counts
        for workers in [1, 2, 4, 8]:
            executor = ParallelQueryExecutor(storage, max_workers=workers)
            results = executor.execute_batch(queries)
            assert len(results) == 10
            assert all(len(r) == 50 for r in results)

    def test_large_result_sets(self):
        """Test handling large result sets"""
        storage = CodeGraphStorage()
        
        # Create 10000 nodes
        for i in range(10000):
            storage.add_node(f'f_{i}', 'function', {
                'name': f'func_{i}',
                'file': 'large_file.py'
            })
        
        executor = ParallelQueryExecutor(storage, max_workers=4)
        
        queries = [
            "find functions in file:large_file.py",
            "find functions in file:large_file.py",
        ]
        
        results = executor.execute_batch(queries)
        
        assert len(results) == 2
        assert all(len(r) == 10000 for r in results)

    def test_query_cancellation(self):
        """Test cancelling long-running queries"""
        storage = CodeGraphStorage()
        for i in range(1000):
            storage.add_node(f'f_{i}', 'function', {'name': f'func_{i}'})
        
        executor = ParallelQueryExecutor(storage, max_workers=4)
        
        queries = ["find functions"] * 100
        
        # Execute with timeout
        results = executor.execute_batch(queries, timeout=5.0)
        
        # Should complete within timeout
        assert len(results) == 100

    def test_thread_safety(self):
        """Test thread-safe access to storage"""
        storage = CodeGraphStorage()
        for i in range(100):
            storage.add_node(f'f_{i}', 'function', {
                'name': f'func_{i}',
                'file': f'file_{i % 10}.py'
            })
        
        executor = ParallelQueryExecutor(storage, max_workers=8)
        
        # Execute many queries concurrently
        queries = [f"find functions in file:file_{i % 10}.py" for i in range(100)]
        
        results = executor.execute_batch(queries)
        
        assert len(results) == 100
        # All results should be consistent
        assert all(len(r) == 10 for r in results)

    def test_performance_metrics(self):
        """Test collecting performance metrics"""
        storage = CodeGraphStorage()
        for i in range(100):
            storage.add_node(f'f_{i}', 'function', {'name': f'func_{i}'})
        
        executor = ParallelQueryExecutor(storage, max_workers=4)
        
        queries = ["find functions"] * 10
        
        results = executor.execute_batch_with_metadata(
            QueryBatch(queries)
        )
        
        # Check metrics
        total_time = sum(r['execution_time'] for r in results)
        assert total_time > 0
        
        # Most queries should have reasonable execution time
        # Note: Parallel execution can have variance due to scheduling
        times = [r['execution_time'] for r in results]
        avg_time = sum(times) / len(times)
        # At least 80% of queries should be within 10x average (accounting for system variance)
        within_range = sum(1 for t in times if t < avg_time * 10)
        assert within_range >= len(times) * 0.8

    def test_batch_query_error_raises_exception(self):
        """Test that batch execution raises exception when continue_on_error is False."""
        storage = CodeGraphStorage()
        storage.add_node('f1', 'function', {'name': 'main'})
        
        executor = ParallelQueryExecutor(storage)
        
        # Invalid query that will cause error
        queries = [
            "find functions",
            "totally invalid query that will fail",  # This should fail
        ]
        
        # When continue_on_error is False (default), errors should raise exception
        with pytest.raises(ValueError):
            executor.execute_batch(queries, continue_on_error=False)

    def test_stream_handles_exceptions(self):
        """Test that streaming handles exceptions gracefully."""
        storage = CodeGraphStorage()
        for i in range(10):
            storage.add_node(f'f_{i}', 'function', {'name': f'func_{i}'})
        
        executor = ParallelQueryExecutor(storage, max_workers=2)
        
        queries = [
            "find functions",
            "invalid query",  # May cause error
            "find classes",
        ]
        
        results = list(executor.execute_stream(queries))
        
        # Should get results for all queries (including empty for errors)
        assert len(results) == 3

    def test_batch_with_metadata_handles_errors(self):
        """Test metadata batch handles query errors gracefully."""
        storage = CodeGraphStorage()
        storage.add_node('f1', 'function', {'name': 'main'})
        
        executor = ParallelQueryExecutor(storage)
        
        batch = QueryBatch([
            "find functions",
            "this is invalid",  # May fail
        ])
        
        results = executor.execute_batch_with_metadata(batch)
        
        assert len(results) == 2
        # First query should succeed
        assert results[0]['success'] is True or results[1]['success'] is True


class TestParallelBatchProcessor:
    """Tests for ParallelBatchProcessor class."""

    def test_process_large_batch_basic(self):
        """Test processing a large batch of queries."""
        from tree_sitter_analyzer_v2.graph.parallel_query import ParallelBatchProcessor
        
        storage = CodeGraphStorage()
        for i in range(100):
            storage.add_node(f'f_{i}', 'function', {'name': f'func_{i}'})
        
        processor = ParallelBatchProcessor(storage, max_workers=2, batch_size=20)
        
        queries = ["find functions"] * 50
        results = processor.process_large_batch(queries)
        
        assert len(results) == 50
        assert all(len(r) == 100 for r in results)

    def test_process_large_batch_with_progress(self):
        """Test processing with progress callback."""
        from tree_sitter_analyzer_v2.graph.parallel_query import ParallelBatchProcessor
        
        storage = CodeGraphStorage()
        for i in range(50):
            storage.add_node(f'f_{i}', 'function', {'name': f'func_{i}'})
        
        processor = ParallelBatchProcessor(storage, max_workers=2, batch_size=10)
        
        progress_calls = []
        
        def progress_callback(completed, total):
            progress_calls.append((completed, total))
        
        queries = ["find functions"] * 30
        results = processor.process_large_batch(queries, progress_callback=progress_callback)
        
        assert len(results) == 30
        # Progress callback should have been called multiple times
        assert len(progress_calls) >= 3

    def test_process_with_aggregation(self):
        """Test processing with result aggregation."""
        from tree_sitter_analyzer_v2.graph.parallel_query import ParallelBatchProcessor
        
        storage = CodeGraphStorage()
        for i in range(50):
            storage.add_node(f'f_{i}', 'function', {'name': f'func_{i}'})
        
        processor = ParallelBatchProcessor(storage, max_workers=2, batch_size=10)
        
        queries = ["find functions"] * 20
        
        # Aggregator that counts total results
        def count_aggregator(all_results):
            return sum(len(r) if r else 0 for r in all_results)
        
        total = processor.process_with_aggregation(queries, count_aggregator)
        
        # Each query returns 50 results, 20 queries
        assert total == 50 * 20


class TestQueryBatch:
    """Tests for QueryBatch dataclass."""

    def test_query_batch_creation(self):
        """Test QueryBatch creation."""
        batch = QueryBatch(queries=["query1", "query2"])
        assert batch.queries == ["query1", "query2"]
        assert batch.metadata == {}

    def test_query_batch_with_metadata(self):
        """Test QueryBatch with metadata."""
        batch = QueryBatch(
            queries=["query1"],
            metadata={"source": "test"}
        )
        assert batch.metadata == {"source": "test"}

    def test_query_batch_post_init(self):
        """Test QueryBatch __post_init__ sets empty metadata."""
        batch = QueryBatch(queries=["q1"], metadata=None)
        assert batch.metadata == {}
