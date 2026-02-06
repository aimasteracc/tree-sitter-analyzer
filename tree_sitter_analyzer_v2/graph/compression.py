"""Graph compression module for efficient storage"""

import json
import lzma
import time
import zlib
from dataclasses import dataclass
from typing import Literal

from tree_sitter_analyzer_v2.graph.advanced_storage import CodeGraphStorage


@dataclass
class CompressionStats:
    """Statistics about compression operation"""

    original_size: int
    compressed_size: int
    compression_ratio: float
    compression_time: float
    algorithm: str


class GraphCompressor:
    """Compresses and decompresses code graphs"""

    def __init__(self, algorithm: Literal['zlib', 'lzma'] = 'zlib'):
        """
        Initialize compressor

        Args:
            algorithm: Compression algorithm to use ('zlib' or 'lzma')
        """
        self.algorithm = algorithm
        self._stats: CompressionStats | None = None

    def compress(self, storage: CodeGraphStorage) -> bytes:
        """
        Compress a graph storage

        Args:
            storage: CodeGraphStorage to compress

        Returns:
            Compressed bytes
        """
        start_time = time.time()

        # Serialize to JSON
        data = {
            'nodes': storage.nodes,
            'edges': {
                f'{k[0]}->{k[1]}': v
                for k, v in storage.edges.items()
            },
            'version_history': dict(storage.version_history),
        }

        json_str = json.dumps(data, separators=(',', ':'))
        json_bytes = json_str.encode('utf-8')

        # Compress
        if self.algorithm == 'lzma':
            compressed = lzma.compress(
                json_bytes,
                format=lzma.FORMAT_XZ,
                preset=9  # Maximum compression
            )
        else:  # zlib
            compressed = zlib.compress(json_bytes, level=9)

        # Calculate stats
        compression_time = time.time() - start_time
        self._stats = CompressionStats(
            original_size=len(json_bytes),
            compressed_size=len(compressed),
            compression_ratio=len(json_bytes) / len(compressed) if len(compressed) > 0 else 1.0,
            compression_time=compression_time,
            algorithm=self.algorithm
        )

        return compressed

    def decompress(self, compressed: bytes) -> CodeGraphStorage:
        """
        Decompress bytes back to graph storage

        Args:
            compressed: Compressed bytes

        Returns:
            Reconstructed CodeGraphStorage
        """
        # Decompress
        if self.algorithm == 'lzma':
            json_bytes = lzma.decompress(compressed)
        else:  # zlib
            json_bytes = zlib.decompress(compressed)

        json_str = json_bytes.decode('utf-8')
        data = json.loads(json_str)

        # Reconstruct storage
        storage = CodeGraphStorage()

        # Restore nodes
        for node_id, node_data in data['nodes'].items():
            node_type = node_data.pop('type')
            storage.add_node(node_id, node_type, node_data)

        # Restore edges
        for edge_key, edge_data in data['edges'].items():
            source, target = edge_key.split('->')
            edge_type = edge_data.pop('type')
            storage.add_edge(source, target, edge_type, edge_data)

        # Restore version history
        for node_id, history in data.get('version_history', {}).items():
            storage.version_history[node_id] = history

        return storage

    def get_stats(self) -> CompressionStats:
        """
        Get statistics about last compression operation

        Returns:
            CompressionStats object
        """
        if self._stats is None:
            return CompressionStats(
                original_size=0,
                compressed_size=0,
                compression_ratio=1.0,
                compression_time=0.0,
                algorithm=self.algorithm
            )
        return self._stats


class MemoryMappedStorage:
    """Memory-mapped file storage for large graphs"""

    def __init__(self, filepath: str):
        """
        Initialize memory-mapped storage

        Args:
            filepath: Path to storage file
        """
        self.filepath = filepath
        self._compressor = GraphCompressor(algorithm='lzma')

    def save(self, storage: CodeGraphStorage) -> None:
        """
        Save graph to file

        Args:
            storage: CodeGraphStorage to save
        """
        compressed = self._compressor.compress(storage)

        with open(self.filepath, 'wb') as f:
            f.write(compressed)

    def load(self) -> CodeGraphStorage:
        """
        Load graph from file

        Returns:
            Loaded CodeGraphStorage
        """
        with open(self.filepath, 'rb') as f:
            compressed = f.read()

        return self._compressor.decompress(compressed)

    def get_size(self) -> int:
        """
        Get file size in bytes

        Returns:
            File size
        """
        import os
        if os.path.exists(self.filepath):
            return os.path.getsize(self.filepath)
        return 0
