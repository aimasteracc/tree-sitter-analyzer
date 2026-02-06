"""Tests for graph compression"""

import pytest
from tree_sitter_analyzer_v2.graph.compression import (
    GraphCompressor,
    CompressionStats,
)
from tree_sitter_analyzer_v2.graph.advanced_storage import CodeGraphStorage


class TestGraphCompressor:
    """Test graph compression"""

    def test_compress_empty_graph(self):
        """Test compressing empty graph"""
        storage = CodeGraphStorage()
        compressor = GraphCompressor()
        
        compressed = compressor.compress(storage)
        
        assert compressed is not None
        assert len(compressed) > 0
        assert len(compressed) < 100  # Should be very small

    def test_compress_and_decompress(self):
        """Test compression and decompression round-trip"""
        storage = CodeGraphStorage()
        storage.add_node('func_1', 'function', {
            'name': 'main',
            'file': 'main.py',
            'lines': 10
        })
        storage.add_node('func_2', 'function', {
            'name': 'helper',
            'file': 'utils.py',
            'lines': 5
        })
        storage.add_edge('func_1', 'func_2', 'calls', {})
        
        compressor = GraphCompressor()
        compressed = compressor.compress(storage)
        decompressed = compressor.decompress(compressed)
        
        # Verify nodes
        assert len(decompressed.nodes) == 2
        assert decompressed.get_node('func_1')['name'] == 'main'
        assert decompressed.get_node('func_2')['name'] == 'helper'
        
        # Verify edges
        edges = decompressed.get_edges_from('func_1')
        assert len(edges) == 1
        assert edges[0]['target'] == 'func_2'
        assert edges[0]['type'] == 'calls'

    def test_compression_ratio(self):
        """Test compression achieves good ratio"""
        storage = CodeGraphStorage()
        
        # Add many nodes with repetitive data
        for i in range(100):
            storage.add_node(f'func_{i}', 'function', {
                'name': f'function_{i}',
                'file': 'main.py',  # Same file for all
                'lines': 10,
                'complexity': 5,
                'docstring': 'This is a test function' * 10  # Repetitive text
            })
        
        # Add edges
        for i in range(99):
            storage.add_edge(f'func_{i}', f'func_{i+1}', 'calls', {})
        
        compressor = GraphCompressor()
        compressed = compressor.compress(storage)
        stats = compressor.get_stats()
        
        # Should achieve at least 5x compression
        assert stats.compression_ratio >= 5.0
        assert stats.original_size > 0
        assert stats.compressed_size > 0
        assert stats.compressed_size < stats.original_size

    def test_compress_with_unicode(self):
        """Test compression handles unicode correctly"""
        storage = CodeGraphStorage()
        storage.add_node('func_1', 'function', {
            'name': 'test_unicode',
            'docstring': 'Function with unicode: 你好世界 🚀'
        })
        
        compressor = GraphCompressor()
        compressed = compressor.compress(storage)
        decompressed = compressor.decompress(compressed)
        
        node = decompressed.get_node('func_1')
        assert 'unicode: 你好世界 🚀' in node['docstring']

    def test_compress_large_graph(self):
        """Test compression on large graph"""
        storage = CodeGraphStorage()
        
        # Add 1000 nodes
        for i in range(1000):
            storage.add_node(f'node_{i}', 'function', {
                'name': f'func_{i}',
                'file': f'file_{i % 10}.py',  # 10 different files
                'lines': i % 100
            })
        
        # Add 5000 edges
        for i in range(5000):
            source = f'node_{i % 1000}'
            target = f'node_{(i + 1) % 1000}'
            storage.add_edge(source, target, 'calls', {})
        
        compressor = GraphCompressor()
        compressed = compressor.compress(storage)
        decompressed = compressor.decompress(compressed)
        
        # Verify integrity
        assert len(decompressed.nodes) == 1000
        assert len(decompressed.edges) >= 1000  # At least 1000 unique edges

    def test_compression_stats(self):
        """Test compression statistics"""
        storage = CodeGraphStorage()
        for i in range(50):
            storage.add_node(f'n_{i}', 'function', {'name': f'f_{i}'})
        
        compressor = GraphCompressor()
        compressor.compress(storage)
        stats = compressor.get_stats()
        
        assert isinstance(stats, CompressionStats)
        assert stats.original_size > 0
        assert stats.compressed_size > 0
        assert stats.compression_ratio > 1.0
        assert stats.compression_time > 0

    def test_incremental_compression(self):
        """Test incremental compression updates"""
        storage = CodeGraphStorage()
        storage.add_node('n1', 'function', {'name': 'f1'})
        
        compressor = GraphCompressor()
        compressed1 = compressor.compress(storage)
        
        # Add more nodes
        storage.add_node('n2', 'function', {'name': 'f2'})
        storage.add_node('n3', 'function', {'name': 'f3'})
        
        compressed2 = compressor.compress(storage)
        
        # Second compression should be larger
        assert len(compressed2) > len(compressed1)

    def test_compression_preserves_indexes(self):
        """Test that decompression rebuilds indexes"""
        storage = CodeGraphStorage()
        storage.add_node('f1', 'function', {'name': 'main', 'file': 'main.py'})
        storage.add_node('f2', 'function', {'name': 'helper', 'file': 'main.py'})
        storage.add_node('c1', 'class', {'name': 'User', 'file': 'models.py'})
        
        compressor = GraphCompressor()
        compressed = compressor.compress(storage)
        decompressed = compressor.decompress(compressed)
        
        # Test indexes work
        functions = decompressed.query_by_type('function')
        assert len(functions) == 2
        
        main_py_nodes = decompressed.query_by_file('main.py')
        assert len(main_py_nodes) == 2

    def test_compression_algorithm_choice(self):
        """Test different compression algorithms"""
        storage = CodeGraphStorage()
        for i in range(100):
            storage.add_node(f'n_{i}', 'function', {
                'name': f'func_{i}',
                'data': 'x' * 1000  # Highly compressible
            })
        
        compressor_zlib = GraphCompressor(algorithm='zlib')
        compressor_lzma = GraphCompressor(algorithm='lzma')
        
        compressed_zlib = compressor_zlib.compress(storage)
        compressed_lzma = compressor_lzma.compress(storage)
        
        # Both should compress significantly
        assert len(compressed_zlib) < len(storage.nodes) * 100
        assert len(compressed_lzma) < len(storage.nodes) * 100
        
        # LZMA should achieve better compression
        assert len(compressed_lzma) <= len(compressed_zlib)
