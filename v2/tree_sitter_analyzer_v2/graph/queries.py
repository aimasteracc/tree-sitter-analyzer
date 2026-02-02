"""
Code Graph Query Functions - Milestone 2: Call Relationship Analysis.

Provides query functions for analyzing code graphs:
- get_callers(): Find all functions that call a given function
- get_call_chain(): Find call paths between two functions
- find_definition(): Find function definitions by name
"""

import networkx as nx


def get_callers(graph: nx.DiGraph, function_id: str) -> list[str]:
    """
    Find all functions that call the given function.

    Args:
        graph: Code graph
        function_id: Node ID of the target function

    Returns:
        List of node IDs that call this function
    """
    callers = []

    # Find all edges pointing to this function with type='CALLS'
    for source, target, edge_data in graph.in_edges(function_id, data=True):
        if edge_data.get("type") == "CALLS":
            callers.append(source)

    return callers


def get_call_chain(graph: nx.DiGraph, start: str, end: str, max_depth: int = 10) -> list[list[str]]:
    """
    Find all call paths from start function to end function.

    Args:
        graph: Code graph
        start: Starting function node ID
        end: Ending function node ID
        max_depth: Maximum path depth to search (default: 10)

    Returns:
        List of paths, where each path is a list of node IDs
    """
    try:
        # Use NetworkX to find all simple paths
        # We need to use a subgraph with only CALLS edges
        calls_graph = nx.DiGraph()

        # Add only CALLS edges to the subgraph
        for u, v, data in graph.edges(data=True):
            if data.get("type") == "CALLS":
                calls_graph.add_edge(u, v)

        # Find all simple paths (no cycles)
        paths = list(nx.all_simple_paths(calls_graph, start, end, cutoff=max_depth))
        return paths
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


def find_definition(graph: nx.DiGraph, name: str) -> list[str]:
    """
    Find all function/class definitions with the given name.

    Args:
        graph: Code graph
        name: Function or class name to search for

    Returns:
        List of node IDs matching the name
    """
    matches = []

    for node_id, node_data in graph.nodes(data=True):
        if node_data.get("name") == name:
            if node_data["type"] in ("FUNCTION", "CLASS"):
                matches.append(node_id)

    return matches
