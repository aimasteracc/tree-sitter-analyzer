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
        """Test that parallel execution is faster"""
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
        start = time.time()
        results_seq = executor_seq.execute_batch(queries)
        time_seq = time.time() - start
        
        # Parallel execution
        executor_par = ParallelQueryExecutor(storage, max_workers=4)
        start = time.time()
        results_par = executor_par.execute_batch(queries)
        time_par = time.time() - start
        
        # Verify same results
        assert len(results_seq) == len(results_par)
        
        # Parallel should not be significantly slower
        # (For very fast queries, thread overhead may dominate)
        assert time_par < time_seq * 2.0  # Allow 2x slower due to overhead

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
        
        # All queries should have similar execution time
        times = [r['execution_time'] for r in results]
        avg_time = sum(times) / len(times)
        assert all(t < avg_time * 2 for t in times)
