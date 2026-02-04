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


def query_methods(graph: nx.DiGraph, class_name: str) -> list[dict]:
    """
    Query all methods of a class.

    Args:
        graph: Code graph
        class_name: Name of the class to query

    Returns:
        List of method dictionaries with their attributes

    Example:
        >>> query_methods(graph, "Calculator")
        [
            {"name": "add", "parameters": ["self", "a", "b"]},
            {"name": "subtract", "parameters": ["self", "a", "b"]}
        ]
    """
    methods = []

    # Find all class nodes with matching name
    class_nodes = [
        node_id
        for node_id, node_data in graph.nodes(data=True)
        if node_data.get("type") == "CLASS" and node_data.get("name") == class_name
    ]

    # For each matching class, find its methods
    for class_id in class_nodes:
        # Find all outgoing CONTAINS edges from this class
        for _, method_id, edge_data in graph.out_edges(class_id, data=True):
            if edge_data.get("type") == "CONTAINS":
                # Get the method node data
                method_data = graph.nodes[method_id]
                if method_data.get("type") == "FUNCTION":
                    # Extract method information
                    method_info = {
                        "name": method_data.get("name", ""),
                        "parameters": method_data.get("parameters", []),
                    }

                    # Add optional fields if present
                    if "return_type" in method_data:
                        method_info["return_type"] = method_data["return_type"]
                    if "start_line" in method_data:
                        method_info["start_line"] = method_data["start_line"]
                    if "end_line" in method_data:
                        method_info["end_line"] = method_data["end_line"]

                    methods.append(method_info)

    return methods


def filter_nodes(
    graph: nx.DiGraph, node_types: list[str] | None = None, file_pattern: str | None = None
) -> dict:
    """
    Filter graph by node types and file pattern.

    Args:
        graph: Code graph
        node_types: List of node types to include (e.g., ["CLASS", "FUNCTION"])
        file_pattern: Glob pattern for file paths (e.g., "src/**/*.py")

    Returns:
        Dictionary with "nodes" and "edges" keys containing filtered graph data

    Example:
        >>> filter_nodes(graph, node_types=["FUNCTION"], file_pattern="src/*.py")
        {"nodes": {...}, "edges": [...]}
    """
    from fnmatch import fnmatch
    from pathlib import Path

    filtered_nodes = {}
    filtered_edges = []

    # Filter nodes
    for node_id, node_data in graph.nodes(data=True):
        include = True

        # Filter by node type
        if node_types is not None:
            if node_data.get("type") not in node_types:
                include = False

        # Filter by file pattern (for nodes with file_path or module_id)
        if include and file_pattern is not None:
            # Get file path from node or trace back to module
            file_path = node_data.get("file_path")

            # If no direct file_path, try to find it through module_id
            if not file_path and "module_id" in node_data:
                module_id = node_data["module_id"]
                if module_id in graph.nodes:
                    file_path = graph.nodes[module_id].get("file_path")

            # Match against pattern
            if file_path:
                # Convert glob pattern to fnmatch format
                # Use forward slashes for consistency
                file_path_normalized = str(Path(file_path)).replace("\\", "/")
                pattern_normalized = file_pattern.replace("\\", "/")

                # Handle ** wildcards
                if "**" in pattern_normalized:
                    # Convert ** to *
                    pattern_normalized = pattern_normalized.replace("**/", "")
                    # Match if pattern is contained in path
                    include = pattern_normalized.replace("*", "") in file_path_normalized or fnmatch(
                        file_path_normalized, pattern_normalized
                    )
                else:
                    include = fnmatch(file_path_normalized, pattern_normalized)
            else:
                include = False

        if include:
            filtered_nodes[node_id] = dict(node_data)

    # Filter edges - only include edges between filtered nodes
    for u, v, edge_data in graph.edges(data=True):
        if u in filtered_nodes and v in filtered_nodes:
            filtered_edges.append({"source": u, "target": v, **edge_data})

    return {"nodes": filtered_nodes, "edges": filtered_edges}


def focus_subgraph(graph: nx.DiGraph, node_id: str, depth: int = 1) -> dict:
    """
    Extract subgraph focused on a node and its neighbors within specified depth.

    Args:
        graph: Code graph
        node_id: Central node ID to focus on
        depth: Distance from central node (default: 1)

    Returns:
        Dictionary with "nodes" and "edges" keys containing subgraph data

    Example:
        >>> focus_subgraph(graph, "Calculator.add", depth=1)
        {"nodes": {...}, "edges": [...]}
    """
    if node_id not in graph.nodes:
        # Return empty subgraph if node doesn't exist
        return {"nodes": {}, "edges": []}

    # Collect nodes within depth using BFS
    nodes_to_include = {node_id}
    current_layer = {node_id}

    for _ in range(depth):
        next_layer = set()

        for node in current_layer:
            # Add predecessors (incoming edges)
            for pred in graph.predecessors(node):
                next_layer.add(pred)

            # Add successors (outgoing edges)
            for succ in graph.successors(node):
                next_layer.add(succ)

        nodes_to_include.update(next_layer)
        current_layer = next_layer

    # Extract subgraph nodes
    subgraph_nodes = {node: dict(graph.nodes[node]) for node in nodes_to_include}

    # Extract subgraph edges
    subgraph_edges = []
    for u, v, edge_data in graph.edges(data=True):
        if u in nodes_to_include and v in nodes_to_include:
            subgraph_edges.append({"source": u, "target": v, **edge_data})

    return {"nodes": subgraph_nodes, "edges": subgraph_edges}
