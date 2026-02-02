"""
Code graph module for tree-sitter-analyzer v2.

Provides graph-based code analysis enabling:
- Self-analysis of projects
- Call chain tracing
- Impact analysis
- LLM-friendly code structure representation
"""

from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
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
from tree_sitter_analyzer_v2.graph.queries import (
    find_definition,
    get_call_chain,
    get_callers,
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
]
