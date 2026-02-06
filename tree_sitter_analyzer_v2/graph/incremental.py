"""
Code Graph Incremental Updates - Milestone 4: Incremental Updates.

Provides mtime-based change detection and incremental graph updates.
"""

from pathlib import Path

import networkx as nx


def detect_changes(graph: nx.DiGraph, file_path: str) -> list[str]:
    """
    Detect if a file has changed by comparing its mtime with cached metadata.

    Args:
        graph: Code graph with cached file metadata
        file_path: Path to file to check

    Returns:
        List of changed file paths (empty if no changes)
    """
    changed_files = []

    # Get current file mtime
    try:
        current_mtime = Path(file_path).stat().st_mtime
    except FileNotFoundError:
        return []

    # Check if graph has metadata for this file
    # Look for module nodes with this file_path
    for _node_id, node_data in graph.nodes(data=True):
        if node_data.get("type") == "MODULE":
            stored_path = node_data.get("file_path")
            if stored_path and Path(stored_path).resolve() == Path(file_path).resolve():
                # Found module node for this file
                stored_mtime = node_data.get("mtime", 0)
                if current_mtime > stored_mtime:
                    changed_files.append(file_path)
                return changed_files

    # No metadata found - file not in graph yet (no changes)
    return []


def update_graph(graph: nx.DiGraph, file_path: str) -> nx.DiGraph:
    """
    Incrementally update graph when a file changes.

    Args:
        graph: Existing code graph
        file_path: Path to changed file

    Returns:
        Updated graph with new nodes/edges for changed file
    """
    from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder

    # Find all nodes associated with this file (before copying)
    nodes_to_remove = []
    file_path_resolved = str(Path(file_path).resolve())

    for node_id, node_data in graph.nodes(data=True):
        # Check if node belongs to this file
        node_file_path = node_data.get("file_path", "")
        if node_file_path and Path(node_file_path).resolve() == Path(file_path_resolved):
            nodes_to_remove.append(node_id)

    # Re-analyze the changed file
    builder = CodeGraphBuilder()
    new_graph = builder.build_from_file(file_path)

    # Create updated graph by composition (more efficient than copy+modify)
    # Start with new graph, then add nodes from old graph that aren't being replaced
    updated_graph = new_graph.copy()

    for node_id, node_data in graph.nodes(data=True):
        if node_id not in nodes_to_remove and node_id not in updated_graph:
            updated_graph.add_node(node_id, **node_data)

    # Add edges from old graph (excluding edges involving removed nodes)
    for source, target, edge_data in graph.edges(data=True):
        if source not in nodes_to_remove and target not in nodes_to_remove:
            if not updated_graph.has_edge(source, target):
                updated_graph.add_edge(source, target, **edge_data)

    return updated_graph
