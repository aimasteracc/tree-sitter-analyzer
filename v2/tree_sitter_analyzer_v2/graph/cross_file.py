"""
Cross-file call resolution for building project-level call graphs.

This module provides functionality to resolve function calls across file boundaries,
using import information and symbol tables to create a unified call graph.

Components:
- CrossFileCallResolver: Resolves function calls to definitions across files
"""

import networkx as nx

from tree_sitter_analyzer_v2.graph.symbols import SymbolEntry, SymbolTable


class CrossFileCallResolver:
    """Resolve function calls to definitions across file boundaries.

    This class combines import information and symbol table data to resolve
    function calls that cross file boundaries. It uses a priority-based approach:
    1. Same-file definitions (highest priority)
    2. Direct imports (based on import graph)
    3. Skip ambiguous or unresolved calls (conservative approach)

    The resolver produces a unified call graph by:
    - Merging individual file graphs
    - Adding cross-file CALLS edges based on import relationships
    - Tracking unresolved calls for diagnostics

    Thread Safety:
        This class is NOT thread-safe. Use locks if accessing from multiple threads.

    Example:
        >>> resolver = CrossFileCallResolver(import_graph, symbol_table)
        >>> combined_graph = resolver.resolve(file_graphs)
        >>> # Check for unresolved calls
        >>> warnings = resolver.get_unresolved_calls()
        >>> for warning in warnings:
        ...     print(warning)
    """

    def __init__(self, import_graph: nx.DiGraph, symbol_table: SymbolTable):
        """Initialize CrossFileCallResolver.

        Args:
            import_graph: NetworkX directed graph of import relationships.
                         Nodes are file paths, edges represent IMPORTS.
                         Edge attributes must include:
                         - type: "IMPORTS"
                         - imported_names: List of imported symbols
                         - aliases: Dict of aliases (optional)

            symbol_table: Project-wide symbol table containing all function/class/method
                         definitions. Used to look up call targets.

        Example:
            >>> import_graph = nx.DiGraph()
            >>> import_graph.add_edge("main.py", "utils.py",
            ...     type="IMPORTS", imported_names=["helper"])
            >>> symbol_table = SymbolTable()
            >>> # ... populate symbol_table ...
            >>> resolver = CrossFileCallResolver(import_graph, symbol_table)
        """
        self.import_graph = import_graph
        """Import dependency graph (file-level)."""

        self.symbol_table = symbol_table
        """Project-wide symbol registry."""

        self.unresolved: list[str] = []
        """List of unresolved call warnings for diagnostics."""

    def resolve(self, file_graphs: dict[str, nx.DiGraph]) -> nx.DiGraph:
        """Resolve cross-file function calls and create unified call graph.

        This method:
        1. Combines all individual file graphs into one unified graph
        2. Iterates through all function nodes in each file
        3. For each function, finds outgoing CALLS edges
        4. Resolves call targets using import context and symbol table
        5. Adds cross-file CALLS edges to the unified graph

        Resolution Strategy:
        - Priority 1: Same-file definitions (no import needed)
        - Priority 2: Direct imports (unambiguous, single match)
        - Skip: Ambiguous imports (multiple matches)
        - Skip: Unresolved calls (not found in imports or symbol table)

        Args:
            file_graphs: Dictionary mapping file paths to their NetworkX DiGraph
                        representation. Each graph contains nodes representing
                        functions, methods, classes, etc., with CALLS edges
                        between them.

        Returns:
            Unified NetworkX DiGraph containing:
            - All nodes from all file graphs
            - All intra-file CALLS edges (preserved)
            - New cross-file CALLS edges (resolved via imports)
            - Edge attribute "cross_file": True for cross-file edges

        Example:
            >>> file_graphs = {
            ...     "main.py": main_graph,
            ...     "utils.py": utils_graph
            ... }
            >>> combined = resolver.resolve(file_graphs)
            >>> # Check if main calls utils.helper
            >>> combined.has_edge("main.py:main", "utils.py:helper")
            True
        """
        # Step 1: Combine all file graphs into one unified graph
        combined = nx.DiGraph()
        for graph in file_graphs.values():
            combined = nx.compose(combined, graph)

        # Step 2: For each function in each file, resolve external calls
        for file_path, graph in file_graphs.items():
            for node_id, data in graph.nodes(data=True):
                # Only process FUNCTION and METHOD nodes
                if data.get("type") not in ["FUNCTION", "METHOD"]:
                    continue

                # Get all calls made by this function
                calls = self._get_call_nodes(graph, node_id)

                # Step 3: Resolve each call and add cross-file edges
                for call_name in calls:
                    # Try to resolve this call
                    target = self._resolve_call(call_name, file_path, node_id)

                    # If resolved and not a self-loop, add edge
                    if target and target != node_id:
                        # Determine if this is a cross-file call
                        target_file = self._get_file(target)
                        is_cross_file = target_file != file_path

                        # Add CALLS edge with cross_file attribute
                        combined.add_edge(
                            node_id,
                            target,
                            type="CALLS",
                            cross_file=is_cross_file,
                        )

        return combined

    def _resolve_call(self, call_name: str, from_file: str, caller_node_id: str) -> str | None:
        """Resolve a function call to its definition node ID.

        This method implements the priority-based resolution strategy:
        1. Check for same-file definition (highest priority)
        2. Check for direct imports (via import graph)
        3. Return None for ambiguous or unresolved calls

        Conservative Approach:
        - If multiple imported files define the same symbol: skip (ambiguous)
        - If symbol not found in imports: skip (external or stdlib)
        - Track all unresolved/ambiguous calls in self.unresolved

        Args:
            call_name: Name of the called function (e.g., "helper", "process_data")
            from_file: File path containing the call site (e.g., "app/main.py")
            caller_node_id: Node ID of the calling function (for diagnostics)

        Returns:
            Node ID of the resolved definition, or None if:
            - Call is ambiguous (multiple matches)
            - Call is unresolved (not found)
            - Call is to external library (out of scope)

        Example:
            >>> # Same-file call
            >>> target = resolver._resolve_call("helper", "app.py", "app.py:main")
            >>> target
            'app.py:helper'

            >>> # Cross-file call via import
            >>> target = resolver._resolve_call("process", "main.py", "main.py:main")
            >>> target
            'utils/data.py:process'

            >>> # Ambiguous call (multiple imports)
            >>> target = resolver._resolve_call("format", "app.py", "app.py:main")
            >>> target is None
            True
            >>> "Ambiguous call" in resolver.unresolved[0]
            True
        """
        # Priority 1: Same-file definitions (highest priority)
        same_file_def = self.symbol_table.lookup_in_file(call_name, from_file)
        if same_file_def:
            return same_file_def.node_id

        # Priority 1.5: Java qualified calls (ClassName.methodName)
        # For Java, call_name might be qualified like "UserService.createUser"
        if "." in call_name:
            # Try qualified lookup
            qualified_defs = self.symbol_table.lookup_qualified(call_name, from_file)
            if len(qualified_defs) == 1:
                return qualified_defs[0].node_id
            elif len(qualified_defs) > 1:
                # Filter by imported files if possible
                imported_qualified = self._filter_by_imports(qualified_defs, from_file)
                if len(imported_qualified) == 1:
                    return imported_qualified[0].node_id
                # Still ambiguous - skip
                if qualified_defs:
                    self.unresolved.append(
                        f"{caller_node_id}: Ambiguous qualified call to '{call_name}' "
                        f"(found in {len(qualified_defs)} locations)"
                    )
                    return None

        # Priority 2: Direct imports
        imported_defs = self._find_imported_symbols(call_name, from_file)
        if len(imported_defs) == 1:
            # Unambiguous - single import
            return imported_defs[0].node_id
        elif len(imported_defs) > 1:
            # Ambiguous - log warning and skip
            self.unresolved.append(
                f"{caller_node_id}: Ambiguous call to '{call_name}' "
                f"(found in {len(imported_defs)} files)"
            )
            return None

        # Priority 3: Not found
        # (Could be stdlib, external package, or unresolved)
        return None

    def _find_imported_symbols(self, symbol_name: str, from_file: str) -> list[SymbolEntry]:
        """Find all imported definitions of a symbol from a given file.

        This method traverses the import graph to find which files are imported
        by from_file, then checks if any of those files define the symbol.

        Import Matching Rules:
        - Exact match: symbol_name in imported_names
        - Wildcard: '*' in imported_names (import all)
        - Respect aliases: check both original and aliased names

        Args:
            symbol_name: Name to search for in imported files
            from_file: File that contains the import statements

        Returns:
            List of SymbolEntry objects representing all imported definitions
            of the symbol. Empty list if:
            - from_file has no imports
            - Symbol not found in any imported file
            - Symbol is external (not in project)

        Example:
            >>> # Find "helper" imported by "main.py"
            >>> entries = resolver._find_imported_symbols("helper", "main.py")
            >>> len(entries)
            1
            >>> entries[0].file_path
            'utils.py'

            >>> # Multiple files define "format"
            >>> entries = resolver._find_imported_symbols("format", "app.py")
            >>> len(entries)
            2
        """
        results = []

        # Get all files imported by from_file
        if from_file not in self.import_graph:
            return results

        for imported_file in self.import_graph.successors(from_file):
            edge_data = self.import_graph[from_file][imported_file]
            imported_names = edge_data.get("imported_names", [])

            # Check if symbol is in imported names or if wildcard import
            if symbol_name in imported_names or "*" in imported_names:
                # Look up symbol in imported file
                entry = self.symbol_table.lookup_in_file(symbol_name, imported_file)
                if entry:
                    results.append(entry)
            else:
                # For Java: imported_names contains class names, not method names
                # Check if any imported class contains this method
                # Example: imported_names=["UserRepository"], symbol_name="save"
                #          → check if UserRepository.java has save() method
                entry = self.symbol_table.lookup_in_file(symbol_name, imported_file)
                if entry:
                    # Verify the entry's node_id contains one of the imported class names
                    for class_name in imported_names:
                        if class_name in entry.node_id:
                            results.append(entry)
                            break

        return results

    def _filter_by_imports(
        self, symbol_entries: list[SymbolEntry], from_file: str
    ) -> list[SymbolEntry]:
        """Filter symbol entries to only include those from imported files.

        This helper method is used for Java qualified calls to prioritize
        methods from imported classes.

        Args:
            symbol_entries: List of symbol entries to filter
            from_file: File that contains the call site

        Returns:
            Filtered list containing only entries from imported files

        Example:
            >>> # If from_file imports UserService.java, prioritize entries from that file
            >>> filtered = resolver._filter_by_imports(all_entries, "App.java")
        """
        if from_file not in self.import_graph:
            return symbol_entries

        # Get all files imported by from_file
        imported_files = set(self.import_graph.successors(from_file))

        # Filter entries to only those from imported files
        filtered = [e for e in symbol_entries if e.file_path in imported_files]

        return filtered if filtered else symbol_entries  # Fallback to all if none match

    def _get_call_nodes(self, graph: nx.DiGraph, node_id: str) -> list[str]:
        """Extract all function calls made by a given node.

        This helper method finds all outgoing CALLS edges from a node and
        returns the list of called function names. It also checks for
        unresolved_calls stored in node data.

        Args:
            graph: File-level code graph
            node_id: Node ID to extract calls from

        Returns:
            List of called function names (not node IDs, just names)

        Example:
            >>> calls = resolver._get_call_nodes(graph, "main.py:process")
            >>> calls
            ['helper', 'validate', 'format']
        """
        calls = []

        # Check if node exists in graph
        if node_id not in graph:
            return calls

        # Method 1: Find all outgoing CALLS edges (for same-file calls)
        for successor in graph.successors(node_id):
            edge_data = graph[node_id][successor]
            if edge_data.get("type") == "CALLS":
                # Extract function name from successor node
                successor_data = graph.nodes[successor]
                call_name = successor_data.get("name")
                if call_name:
                    calls.append(call_name)

        # Method 2: Check for unresolved calls in node data (for cross-file calls)
        node_data = graph.nodes[node_id]
        unresolved_calls = node_data.get("unresolved_calls", [])
        if unresolved_calls:
            calls.extend(unresolved_calls)

        # Remove duplicates while preserving order
        seen = set()
        unique_calls = []
        for call in calls:
            if call not in seen:
                seen.add(call)
                unique_calls.append(call)

        return unique_calls

    def _get_file(self, node_id: str) -> str:
        """Extract file path from a node ID.

        Node IDs typically follow the format "file_path:function_name".
        This method extracts the file path portion.

        Args:
            node_id: Full node identifier (e.g., "utils/helper.py:process")

        Returns:
            File path portion (e.g., "utils/helper.py")

        Example:
            >>> resolver._get_file("app/main.py:main")
            'app/main.py'
        """
        # Split on ':' and return the first part (file path)
        if ":" in node_id:
            return node_id.split(":", 1)[0]
        return node_id  # If no colon, return as-is

    def get_unresolved_calls(self) -> list[str]:
        """Get list of unresolved call warnings.

        This method returns diagnostic information about calls that could not
        be resolved during the resolution process. Each warning string describes:
        - Caller node ID
        - Called function name
        - Reason for failure (ambiguous, not found, etc.)

        Returns:
            List of warning strings for unresolved calls

        Example:
            >>> warnings = resolver.get_unresolved_calls()
            >>> for warning in warnings:
            ...     print(warning)
            main.py:process: Ambiguous call to 'format' (found in 2 files)
            app.py:main: Call to 'external_lib' not found in imports
        """
        return self.unresolved
