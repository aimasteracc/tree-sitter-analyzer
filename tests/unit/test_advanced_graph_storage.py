"""Tests for advanced graph storage engine"""

import pytest

from tree_sitter_analyzer_v2.graph.advanced_storage import (
    CodeGraphStorage,
    GraphIndex,
    GraphQuery,
)


class TestGraphIndex:
    """Test graph indexing system"""

    def test_create_index(self):
        """Test creating an index"""
        index = GraphIndex()
        index.add('file:main.py', 'node_1')
        index.add('file:main.py', 'node_2')
        
        results = index.get('file:main.py')
        assert len(results) == 2
        assert 'node_1' in results
        assert 'node_2' in results

    def test_remove_from_index(self):
        """Test removing from index"""
        index = GraphIndex()
        index.add('type:function', 'func_1')
        index.remove('type:function', 'func_1')
        
        results = index.get('type:function')
        assert len(results) == 0

    def test_multi_level_index(self):
        """Test multi-level indexing"""
        index = GraphIndex()
        index.add('file:main.py', 'node_1')
        index.add('type:function', 'node_1')
        index.add('name:main', 'node_1')
        
        # Can find by any index
        assert 'node_1' in index.get('file:main.py')
        assert 'node_1' in index.get('type:function')
        assert 'node_1' in index.get('name:main')


class TestCodeGraphStorage:
    """Test advanced graph storage"""

    def test_add_node(self):
        """Test adding a node"""
        storage = CodeGraphStorage()
        storage.add_node('func_1', 'function', {
            'name': 'main',
            'file': 'main.py',
            'lines': 10
        })
        
        node = storage.get_node('func_1')
        assert node['type'] == 'function'
        assert node['name'] == 'main'
        assert node['file'] == 'main.py'

    def test_add_edge(self):
        """Test adding an edge"""
        storage = CodeGraphStorage()
        storage.add_node('func_1', 'function', {'name': 'main'})
        storage.add_node('func_2', 'function', {'name': 'helper'})
        storage.add_edge('func_1', 'func_2', 'calls', {})
        
        edges = storage.get_edges_from('func_1')
        assert len(edges) == 1
        assert edges[0]['target'] == 'func_2'
        assert edges[0]['type'] == 'calls'

    def test_query_by_type(self):
        """Test querying nodes by type"""
        storage = CodeGraphStorage()
        storage.add_node('func_1', 'function', {'name': 'main'})
        storage.add_node('func_2', 'function', {'name': 'helper'})
        storage.add_node('class_1', 'class', {'name': 'User'})
        
        functions = storage.query_by_type('function')
        assert len(functions) == 2

    def test_query_by_file(self):
        """Test querying nodes by file"""
        storage = CodeGraphStorage()
        storage.add_node('func_1', 'function', {'name': 'main', 'file': 'main.py'})
        storage.add_node('func_2', 'function', {'name': 'helper', 'file': 'utils.py'})
        
        main_nodes = storage.query_by_file('main.py')
        assert len(main_nodes) == 1
        assert main_nodes[0]['name'] == 'main'

    def test_get_subgraph(self):
        """Test extracting subgraph"""
        storage = CodeGraphStorage()
        storage.add_node('func_1', 'function', {'name': 'main'})
        storage.add_node('func_2', 'function', {'name': 'helper'})
        storage.add_node('func_3', 'function', {'name': 'util'})
        storage.add_edge('func_1', 'func_2', 'calls', {})
        storage.add_edge('func_2', 'func_3', 'calls', {})
        
        # Get subgraph with depth 1
        subgraph = storage.get_subgraph('func_1', depth=1)
        assert 'func_1' in subgraph['nodes']
        assert 'func_2' in subgraph['nodes']
        assert 'func_3' not in subgraph['nodes']

    def test_version_history(self):
        """Test version history tracking"""
        storage = CodeGraphStorage()
        storage.add_node('func_1', 'function', {'name': 'main', 'lines': 10})
        
        # Update node
        storage.update_node('func_1', {'lines': 15})
        
        # Check history
        history = storage.get_history('func_1')
        assert len(history) >= 2
        assert history[0]['lines'] == 10
        assert history[-1]['lines'] == 15


class TestGraphQuery:
    """Test code query language"""

    def test_simple_query(self):
        """Test simple CQL query"""
        storage = CodeGraphStorage()
        storage.add_node('func_1', 'function', {'name': 'main'})
        storage.add_node('func_2', 'function', {'name': 'helper'})
        
        query = GraphQuery(storage)
        results = query.execute('find functions')
        
        assert len(results) == 2

    def test_query_with_filter(self):
        """Test query with filter"""
        storage = CodeGraphStorage()
        storage.add_node('func_1', 'function', {'name': 'main', 'file': 'main.py'})
        storage.add_node('func_2', 'function', {'name': 'helper', 'file': 'utils.py'})
        
        query = GraphQuery(storage)
        results = query.execute('find functions in file:main.py')
        
        assert len(results) == 1
        assert results[0]['name'] == 'main'

    def test_query_with_relationship(self):
        """Test query with relationship"""
        storage = CodeGraphStorage()
        storage.add_node('func_1', 'function', {'name': 'main'})
        storage.add_node('func_2', 'function', {'name': 'helper'})
        storage.add_edge('func_1', 'func_2', 'calls', {})
        
        query = GraphQuery(storage)
        results = query.execute('find functions called_by main')
        
        assert len(results) == 1
        assert results[0]['name'] == 'helper'

    def test_query_with_condition(self):
        """Test query with condition"""
        storage = CodeGraphStorage()
        storage.add_node('func_1', 'function', {'name': 'main', 'complexity': 5})
        storage.add_node('func_2', 'function', {'name': 'complex', 'complexity': 15})
        
        query = GraphQuery(storage)
        results = query.execute('find functions with complexity > 10')
        
        assert len(results) == 1
        assert results[0]['name'] == 'complex'
