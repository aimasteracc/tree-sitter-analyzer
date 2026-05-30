"""Backward-compatibility re-export.

The implementation now lives in the core layer:
    tree_sitter_analyzer/_graph_cache_fingerprint.py

This shim keeps existing MCP-tool imports working without changes.
"""

from ..._graph_cache_fingerprint import (  # noqa: F401
    _EXCLUDE_DIRS,
    _SOURCE_EXTS,
    GraphFingerprint,
    compute_graph_fingerprint,
)
