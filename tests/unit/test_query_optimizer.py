"""Tests for query optimizer"""

import pytest
from tree_sitter_analyzer_v2.graph.advanced_storage import CodeGraphStorage
from tree_sitter_analyzer_v2.graph.query_optimizer import (
    QueryOptimizer,
    QueryPlan,
    IndexScanNode,
    FilterNode,
    JoinNode,
)


class TestQueryOptimizer:
    """Test query optimizer"""

    def test_simple_type_query_uses_index(self):
        """Test that simple type queries use index scan"""
        storage = CodeGraphStorage()
        for i in range(10):
            storage.add_node(f'f_{i}', 'function', {'name': f'func_{i}'})
        
        optimizer = QueryOptimizer(storage)
        plan = optimizer.optimize("find functions")
        
        assert isinstance(plan.root, IndexScanNode)
        assert plan.root.index_type == 'by_type'
        assert plan.estimated_cost < 100

    def test_file_filter_uses_index(self):
        """Test that file filters use file index"""
        storage = CodeGraphStorage()
        storage.add_node('f1', 'function', {'name': 'main', 'file': 'main.py'})
        storage.add_node('f2', 'function', {'name': 'helper', 'file': 'utils.py'})
        
        optimizer = QueryOptimizer(storage)
        plan = optimizer.optimize("find functions in file:main.py")
        
        # Should use file index first, then filter by type
        assert isinstance(plan.root, FilterNode)
        assert isinstance(plan.root.child, IndexScanNode)
        assert plan.root.child.index_type == 'by_file'

    def test_relationship_query_uses_join(self):
        """Test that relationship queries use join"""
        storage = CodeGraphStorage()
        storage.add_node('f1', 'function', {'name': 'main'})
        storage.add_node('f2', 'function', {'name': 'helper'})
        storage.add_edge('f1', 'f2', 'calls', {})
        
        optimizer = QueryOptimizer(storage)
        plan = optimizer.optimize("find functions called_by main")
        
        # Should have a join node
        assert plan.has_join()

    def test_cost_estimation(self):
        """Test cost estimation"""
        storage = CodeGraphStorage()
        
        # Add many nodes
        for i in range(1000):
            storage.add_node(f'f_{i}', 'function', {
                'name': f'func_{i}',
                'file': f'file_{i % 10}.py'
            })
        
        optimizer = QueryOptimizer(storage)
        
        # Type query should be cheap
        plan_type = optimizer.optimize("find functions")
        assert plan_type.estimated_cost < 1000
        
        # File query should be cheaper (fewer results)
        plan_file = optimizer.optimize("find functions in file:file_0.py")
        assert plan_file.estimated_cost < plan_type.estimated_cost

    def test_index_selection(self):
        """Test that optimizer selects best index"""
        storage = CodeGraphStorage()
        
        # Add nodes with different distributions
        for i in range(100):
            storage.add_node(f'f_{i}', 'function', {
                'name': f'func_{i}',
                'file': 'main.py'  # All in same file
            })
        
        optimizer = QueryOptimizer(storage)
        
        # File index should be selected (more selective)
        plan = optimizer.optimize("find functions in file:main.py")
        
        # Should use file index
        node = plan.root
        while hasattr(node, 'child'):
            node = node.child
        assert isinstance(node, IndexScanNode)
        assert node.index_type == 'by_file'

    def test_query_plan_execution(self):
        """Test executing optimized query plan"""
        storage = CodeGraphStorage()
        storage.add_node('f1', 'function', {'name': 'main', 'file': 'main.py'})
        storage.add_node('f2', 'function', {'name': 'helper', 'file': 'main.py'})
        storage.add_node('f3', 'function', {'name': 'util', 'file': 'utils.py'})
        
        optimizer = QueryOptimizer(storage)
        plan = optimizer.optimize("find functions in file:main.py")
        
        results = plan.execute()
        
        assert len(results) == 2
        assert all(r['file'] == 'main.py' for r in results)

    def test_complex_query_optimization(self):
        """Test optimization of complex queries"""
        storage = CodeGraphStorage()
        
        for i in range(50):
            storage.add_node(f'f_{i}', 'function', {
                'name': f'func_{i}',
                'file': f'file_{i % 5}.py',
                'complexity': i % 20
            })
        
        optimizer = QueryOptimizer(storage)
        plan = optimizer.optimize("find functions in file:file_0.py with complexity > 10")
        
        # Should use file index first (most selective)
        # Then filter by type and complexity
        assert plan.estimated_cost < 100
        
        results = plan.execute()
        assert all(r['file'] == 'file_0.py' for r in results)
        assert all(r['complexity'] > 10 for r in results)

    def test_query_plan_to_string(self):
        """Test query plan string representation"""
        storage = CodeGraphStorage()
        storage.add_node('f1', 'function', {'name': 'main'})
        
        optimizer = QueryOptimizer(storage)
        plan = optimizer.optimize("find functions")
        
        plan_str = str(plan)
        assert 'IndexScan' in plan_str
        assert 'by_type' in plan_str

    def test_empty_result_optimization(self):
        """Test optimization for queries with no results"""
        storage = CodeGraphStorage()
        storage.add_node('f1', 'function', {'name': 'main', 'file': 'main.py'})
        
        optimizer = QueryOptimizer(storage)
        plan = optimizer.optimize("find functions in file:nonexistent.py")
        
        results = plan.execute()
        assert len(results) == 0

    def test_optimizer_caches_plans(self):
        """Test that optimizer caches query plans"""
        storage = CodeGraphStorage()
        storage.add_node('f1', 'function', {'name': 'main'})
        
        optimizer = QueryOptimizer(storage)
        
        plan1 = optimizer.optimize("find functions")
        plan2 = optimizer.optimize("find functions")
        
        # Should return same plan (cached)
        assert plan1 is plan2

    def test_multiple_filters(self):
        """Test queries with multiple filters"""
        storage = CodeGraphStorage()
        
        for i in range(100):
            storage.add_node(f'f_{i}', 'function', {
                'name': f'func_{i}',
                'file': f'file_{i % 10}.py',
                'complexity': i % 30,
                'lines': i % 50
            })
        
        optimizer = QueryOptimizer(storage)
        plan = optimizer.optimize(
            "find functions in file:file_0.py with complexity > 10 with lines < 20"
        )
        
        results = plan.execute()
        assert all(r['file'] == 'file_0.py' for r in results)
        assert all(r['complexity'] > 10 for r in results)
        assert all(r['lines'] < 20 for r in results)
