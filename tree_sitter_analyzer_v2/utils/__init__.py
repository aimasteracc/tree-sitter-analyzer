"""
Utility modules for tree-sitter-analyzer v2.

Provides:
- binaries: Binary file detection
- encoding: Encoding detection and safe file reading
"""

from tree_sitter_analyzer_v2.utils import binaries
from tree_sitter_analyzer_v2.utils.encoding import EncodingCache, EncodingDetector

__all__ = ["binaries", "EncodingCache", "EncodingDetector"]
