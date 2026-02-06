"""
Code Graph LLM Export - Milestone 3: LLM Optimization.

Exports code graphs in token-optimized TOON format for LLM consumption.
"""

from typing import Any

import networkx as nx


def export_for_llm(
    graph: nx.DiGraph,
    max_tokens: int = 4000,
    detail_level: str = "summary",
    include_private: bool = True,
    output_format: str = "toon",
) -> str:
    """
    Export code graph in LLM-friendly TOON format.

    Args:
        graph: Code graph to export
        max_tokens: Maximum tokens allowed (approximate)
        detail_level: 'summary' or 'detailed'
        include_private: Include private functions (names starting with _)
        output_format: Output format ('toon' currently)

    Returns:
        TOON-formatted string representation
    """
    if output_format != "toon":
        raise ValueError(f"Unsupported output format: {output_format}")

    # Collect nodes by type
    modules = []
    classes = []
    functions = []

    for node_id, node_data in graph.nodes(data=True):
        node_type = node_data.get("type")
        if node_type == "MODULE":
            modules.append((node_id, node_data))
        elif node_type == "CLASS":
            classes.append((node_id, node_data))
        elif node_type == "FUNCTION":
            functions.append((node_id, node_data))

    # Filter private functions if requested
    if not include_private and detail_level == "summary":
        functions = [
            (nid, data) for nid, data in functions if not data.get("name", "").startswith("_")
        ]

    # Build TOON output
    lines = []

    # Header with counts
    lines.append(f"MODULES: {len(modules)}")
    lines.append(f"CLASSES: {len(classes)}")
    lines.append(f"FUNCTIONS: {len(functions)}")
    lines.append("")

    # Export modules with their contents
    for module_id, module_data in modules:
        module_name = module_data.get("name", "unknown")
        lines.append(f"MODULE: {module_name}")

        # Find classes in this module
        module_classes = [
            (cid, cdata) for cid, cdata in classes if cdata.get("module_id") == module_id
        ]

        for class_id, class_data in module_classes:
            class_name = class_data.get("name", "UnknownClass")
            lines.append(f"  CLASS: {class_name}")

            # Find methods in this class
            class_methods = [
                (fid, fdata) for fid, fdata in functions if fdata.get("class_id") == class_id
            ]

            for method_id, method_data in class_methods:
                method_line = _format_function(method_data, detail_level, indent=4)
                lines.append(method_line)

                # Add call information (always show for insight)
                _add_call_info(graph, method_id, lines, indent=6, detail_level=detail_level)

        # Find module-level functions
        module_functions = [
            (fid, fdata)
            for fid, fdata in functions
            if fdata.get("module_id") == module_id and fdata.get("class_id") is None
        ]

        for func_id, func_data in module_functions:
            func_line = _format_function(func_data, detail_level, indent=2)
            lines.append(func_line)

            # Add call information (always show for insight)
            _add_call_info(graph, func_id, lines, indent=4, detail_level=detail_level)

        lines.append("")  # Blank line between modules

    # Join lines
    output = "\n".join(lines)

    # Truncate if exceeds max_tokens (rough estimate: 1 token ≈ 4 chars)
    max_chars = max_tokens * 4
    if len(output) > max_chars:
        output = output[:max_chars] + "\n... (truncated)"

    return output


def _format_function(func_data: dict[str, Any], detail_level: str, indent: int = 0) -> str:
    """
    Format a function node for TOON output.

    Args:
        func_data: Function node data
        detail_level: 'summary' or 'detailed'
        indent: Indentation level

    Returns:
        Formatted string
    """
    prefix = " " * indent
    name = func_data.get("name", "unknown")

    if detail_level == "summary":
        # Summary: just name
        return f"{prefix}FUNC: {name}"
    else:
        # Detailed: name + params + return type
        params = func_data.get("params", [])
        params_str = ", ".join(params) if params else ""
        return_type = func_data.get("return_type", "None")

        parts = [f"{prefix}FUNC: {name}"]
        if params_str:
            parts.append(f"PARAMS: {params_str}")
        if return_type and return_type != "None":
            parts.append(f"RETURN: {return_type}")

        return " | ".join(parts)


def _add_call_info(
    graph: nx.DiGraph,
    func_id: str,
    lines: list[str],
    indent: int = 0,
    detail_level: str = "summary",
) -> None:
    """
    Add CALLS information to output.

    Args:
        graph: Code graph
        func_id: Function node ID
        lines: Output lines list (modified in place)
        indent: Indentation level
        detail_level: 'summary' or 'detailed'
    """
    prefix = " " * indent

    # Find who this function calls
    calls = []
    for source, target, edge_data in graph.out_edges(func_id, data=True):
        if edge_data.get("type") == "CALLS":
            target_name = graph.nodes[target].get("name", target)
            calls.append(target_name)

    if calls:
        calls_str = ", ".join(calls)
        lines.append(f"{prefix}CALLS: {calls_str}")

    # Find who calls this function (only in detailed mode to save tokens)
    if detail_level == "detailed":
        called_by = []
        for source, target, edge_data in graph.in_edges(func_id, data=True):
            if edge_data.get("type") == "CALLS":
                source_name = graph.nodes[source].get("name", source)
                called_by.append(source_name)

        if called_by:
            called_by_str = ", ".join(called_by)
            lines.append(f"{prefix}CALLED_BY: {called_by_str}")


def export_to_mermaid(
    graph: nx.DiGraph, max_nodes: int = 50, show_classes: bool = True, direction: str = "TD"
) -> str:
    """
    Export code graph as Mermaid flowchart diagram.

    Args:
        graph: Code graph to visualize
        max_nodes: Maximum number of nodes to include (prevents huge diagrams)
        show_classes: Include class containers
        direction: Graph direction ("TD" = top-down, "LR" = left-right)

    Returns:
        Mermaid diagram as string

    Example:
        >>> graph = builder.build_from_file("app.py")
        >>> mermaid = export_to_mermaid(graph)
        >>> print(mermaid)
        graph TD
            main[main] --> helper[helper]
            helper --> utils[utils]
    """
    lines = [f"graph {direction}"]

    # Collect function nodes (main content)
    function_nodes = []
    class_nodes = {}  # class_id -> class_name

    for node_id, node_data in graph.nodes(data=True):
        node_type = node_data.get("type")

        if node_type == "FUNCTION":
            # Skip private functions in visualization to reduce clutter
            name = node_data.get("name", "unknown")
            if not name.startswith("_"):
                function_nodes.append((node_id, node_data))

        elif node_type == "CLASS" and show_classes:
            class_name = node_data.get("name", "UnknownClass")
            class_nodes[node_id] = class_name

    # Limit nodes to prevent overwhelming diagrams
    function_nodes = function_nodes[:max_nodes]

    # Add subgraphs for classes
    if show_classes and class_nodes:
        for class_id, class_name in class_nodes.items():
            # Find methods in this class
            class_methods = [
                (fid, fdata) for fid, fdata in function_nodes if fdata.get("class_id") == class_id
            ]

            if class_methods:
                lines.append(f"    subgraph {class_name}")
                for method_id, method_data in class_methods:
                    method_name = method_data.get("name", "unknown")
                    safe_id = _safe_node_id(method_id)
                    lines.append(f"        {safe_id}[{method_name}]")
                lines.append("    end")

    # Add module-level functions (not in classes)
    module_functions = [
        (fid, fdata) for fid, fdata in function_nodes if fdata.get("class_id") is None
    ]

    for func_id, func_data in module_functions:
        func_name = func_data.get("name", "unknown")
        safe_id = _safe_node_id(func_id)
        lines.append(f"    {safe_id}[{func_name}]")

    # Add CALLS edges
    function_ids = {fid for fid, _ in function_nodes}

    for source, target, edge_data in graph.edges(data=True):
        if edge_data.get("type") == "CALLS":
            # Only include edges between visible nodes
            if source in function_ids and target in function_ids:
                source_safe = _safe_node_id(source)
                target_safe = _safe_node_id(target)
                lines.append(f"    {source_safe} --> {target_safe}")

    return "\n".join(lines)


def export_to_call_flow(graph: nx.DiGraph, start_function: str, max_depth: int = 5) -> str:
    """
    Export call flow diagram starting from a specific function.

    Shows the execution flow from start_function down through its callees.

    Args:
        graph: Code graph
        start_function: Name of starting function
        max_depth: Maximum call depth to show

    Returns:
        Mermaid flowchart showing call flow

    Example:
        >>> mermaid = export_to_call_flow(graph, "main", max_depth=3)
        graph TD
            main[main] --> process[process]
            process --> validate[validate]
    """
    from tree_sitter_analyzer_v2.graph.queries import find_definition

    lines = ["graph TD"]

    # Find starting function
    start_nodes = find_definition(graph, start_function)
    if not start_nodes:
        return f"graph TD\n    error[Function '{start_function}' not found]"

    # BFS to explore call flow
    visited = set()
    queue = [(start_nodes[0], 0)]  # (node_id, depth)

    while queue:
        current_id, depth = queue.pop(0)

        if current_id in visited or depth > max_depth:
            continue

        visited.add(current_id)
        current_name = graph.nodes[current_id].get("name", "unknown")
        safe_current = _safe_node_id(current_id)

        # Add current node
        if depth == 0:
            lines.append(f"    {safe_current}[{current_name}]:::start")
        else:
            lines.append(f"    {safe_current}[{current_name}]")

        # Find who current calls
        for _, target, edge_data in graph.out_edges(current_id, data=True):
            if edge_data.get("type") == "CALLS":
                # target_name = graph.nodes[target].get("name", "unknown")  # Reserved for future use
                safe_target = _safe_node_id(target)

                # Add edge
                lines.append(f"    {safe_current} --> {safe_target}")

                # Queue for exploration
                if target not in visited:
                    queue.append((target, depth + 1))

    # Add styling
    lines.append("    classDef start fill:#90EE90")

    return "\n".join(lines)


def export_to_dependency_graph(graph: nx.DiGraph, max_modules: int = 20) -> str:
    """
    Export module dependency diagram.

    Shows how modules depend on each other (simplified high-level view).

    Args:
        graph: Code graph
        max_modules: Maximum modules to show

    Returns:
        Mermaid diagram showing module dependencies
    """
    lines = ["graph LR"]  # Left-right for dependencies

    # Collect modules
    modules = []
    for node_id, node_data in graph.nodes(data=True):
        if node_data.get("type") == "MODULE":
            modules.append((node_id, node_data))

    modules = modules[:max_modules]

    # Add module nodes
    module_ids = set()
    for module_id, module_data in modules:
        module_name = module_data.get("name", "unknown")
        safe_id = _safe_node_id(module_id)
        module_ids.add(module_id)
        lines.append(f"    {safe_id}[{module_name}]")

    # Add dependencies (inferred from function calls across modules)
    module_deps = set()  # (source_module, target_module)

    for source, target, edge_data in graph.edges(data=True):
        if edge_data.get("type") == "CALLS":
            # Find modules of source and target
            source_module = graph.nodes[source].get("module_id")
            target_module = graph.nodes[target].get("module_id")

            if (
                source_module
                and target_module
                and source_module != target_module
                and source_module in module_ids
                and target_module in module_ids
            ):
                module_deps.add((source_module, target_module))

    # Add dependency edges
    for source_mod, target_mod in module_deps:
        source_safe = _safe_node_id(source_mod)
        target_safe = _safe_node_id(target_mod)
        lines.append(f"    {source_safe} --> {target_safe}")

    return "\n".join(lines)


def _safe_node_id(node_id: str) -> str:
    """
    Convert node ID to Mermaid-safe identifier.

    Mermaid has restrictions on node IDs (no colons, slashes, etc.)

    Args:
        node_id: Original node ID

    Returns:
        Safe identifier
    """
    # Replace problematic characters
    safe = node_id.replace(":", "_")
    safe = safe.replace("/", "_")
    safe = safe.replace(".", "_")
    safe = safe.replace("-", "_")

    return safe
