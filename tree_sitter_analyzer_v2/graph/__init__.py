"""
Code graph module for tree-sitter-analyzer v2.

Provides graph-based code analysis enabling:
- Self-analysis of projects
- Call chain tracing
- Impact analysis
- LLM-friendly code structure representation
"""

from tree_sitter_analyzer_v2.graph.advanced_storage import (
    CodeGraphStorage,
    GraphIndex,
    GraphQuery,
)
from tree_sitter_analyzer_v2.graph.backup import (
    BackupManager,
    BackupMetadata,
    IncrementalBackup,
)
from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
from tree_sitter_analyzer_v2.graph.compression import (
    CompressionStats,
    GraphCompressor,
    MemoryMappedStorage,
)
from tree_sitter_analyzer_v2.graph.export import (
    export_for_llm,
    export_to_call_flow,
    export_to_dependency_graph,
    export_to_mermaid,
)
from tree_sitter_analyzer_v2.graph.incremental import (
    detect_changes,
    update_graph,
)
from tree_sitter_analyzer_v2.graph.parallel_query import (
    ParallelBatchProcessor,
    ParallelQueryExecutor,
    QueryBatch,
)
from tree_sitter_analyzer_v2.graph.queries import (
    find_definition,
    get_call_chain,
    get_callers,
)
from tree_sitter_analyzer_v2.graph.query_optimizer import (
    FilterNode,
    IndexScanNode,
    JoinNode,
    QueryOptimizer,
    QueryPlan,
)
from tree_sitter_analyzer_v2.graph.realtime import (
    FileWatcher,
    RealtimeUpdateEngine,
)
from tree_sitter_analyzer_v2.graph.transactions import (
    IsolationLevel,
    Transaction,
    TransactionError,
    TransactionManager,
)

__all__ = [
    "CodeGraphBuilder",
    "get_callers",
    "get_call_chain",
    "find_definition",
    "export_for_llm",
    "export_to_mermaid",
    "export_to_call_flow",
    "export_to_dependency_graph",
    "detect_changes",
    "update_graph",
    "CodeGraphStorage",
    "GraphIndex",
    "GraphQuery",
    "FileWatcher",
    "RealtimeUpdateEngine",
    "GraphCompressor",
    "CompressionStats",
    "MemoryMappedStorage",
    "QueryOptimizer",
    "QueryPlan",
    "IndexScanNode",
    "FilterNode",
    "JoinNode",
    "ParallelQueryExecutor",
    "QueryBatch",
    "ParallelBatchProcessor",
    "Transaction",
    "TransactionManager",
    "TransactionError",
    "IsolationLevel",
    "BackupManager",
    "IncrementalBackup",
    "BackupMetadata",
]
