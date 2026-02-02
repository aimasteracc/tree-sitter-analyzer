"""
Symbol table for project-wide function/class registry.

This module provides components for building and querying a global symbol table,
enabling cross-file call resolution and function lookup.

Components:
- SymbolEntry: Represents a single function/class/method definition
- SymbolTable: Project-wide symbol registry with lookup capabilities
- SymbolTableBuilder: Constructs symbol table from file graphs
"""

from dataclasses import dataclass

import networkx as nx


@dataclass
class SymbolEntry:
    """Represents a single symbol (function/class/method) definition in the codebase.

    A symbol entry captures the essential information needed to identify and locate
    a code element across the project.

    Attributes:
        node_id: Unique identifier for this node (e.g., "app.py:main")
        file_path: Path to file containing this symbol (e.g., "app.py")
        name: Symbol name (e.g., "main", "Helper", "process_data")
        type: Symbol type - "FUNCTION", "CLASS", or "METHOD"
        line_start: Starting line number of symbol definition
        line_end: Ending line number of symbol definition

    Examples:
        >>> # Function definition
        >>> SymbolEntry(
        ...     node_id="app.py:main",
        ...     file_path="app.py",
        ...     name="main",
        ...     type="FUNCTION",
        ...     line_start=10,
        ...     line_end=25
        ... )

        >>> # Class definition
        >>> SymbolEntry(
        ...     node_id="models.py:User",
        ...     file_path="models.py",
        ...     name="User",
        ...     type="CLASS",
        ...     line_start=5,
        ...     line_end=50
        ... )

        >>> # Method definition
        >>> SymbolEntry(
        ...     node_id="models.py:User.save",
        ...     file_path="models.py",
        ...     name="save",
        ...     type="METHOD",
        ...     line_start=30,
        ...     line_end=35
        ... )
    """

    node_id: str
    """Unique identifier for this node (e.g., 'app.py:main')."""

    file_path: str
    """Path to file containing this symbol (e.g., 'app.py')."""

    name: str
    """Symbol name (e.g., 'main', 'Helper', 'process_data')."""

    type: str
    """Symbol type: 'FUNCTION', 'CLASS', or 'METHOD'."""

    line_start: int
    """Starting line number of symbol definition."""

    line_end: int
    """Ending line number of symbol definition."""


class SymbolTable:
    """Project-wide symbol registry for function/class/method lookup.

    This class maintains a global index of all symbols in the project, enabling
    fast lookup by name with context-aware disambiguation.

    Features:
    - Store multiple definitions for same name (handle duplicates across files)
    - Prioritize same-file definitions when context is provided
    - Support exact file path lookup

    Thread Safety:
        This class is NOT thread-safe. Use locks if accessing from multiple threads.

    Example:
        >>> table = SymbolTable()
        >>> entry = SymbolEntry(
        ...     node_id="utils.py:helper",
        ...     file_path="utils.py",
        ...     name="helper",
        ...     type="FUNCTION",
        ...     line_start=10,
        ...     line_end=20
        ... )
        >>> table.add(entry)
        >>> results = table.lookup("helper")
        >>> print(len(results))
        1
        >>> print(results[0].file_path)
        utils.py
    """

    def __init__(self):
        """Initialize an empty symbol table."""
        self._table: dict[str, list[SymbolEntry]] = {}
        """Internal storage: symbol_name → list of all definitions."""

    def add(self, entry: SymbolEntry) -> None:
        """Add a symbol entry to the table.

        If the symbol name already exists, this entry is appended to the list
        of definitions. This allows multiple files to define symbols with the
        same name (e.g., multiple 'main' functions).

        Args:
            entry: Symbol entry to add

        Example:
            >>> table = SymbolTable()
            >>> entry1 = SymbolEntry("app.py:helper", "app.py", "helper", "FUNCTION", 5, 10)
            >>> entry2 = SymbolEntry("utils.py:helper", "utils.py", "helper", "FUNCTION", 20, 30)
            >>> table.add(entry1)
            >>> table.add(entry2)
            >>> results = table.lookup("helper")
            >>> len(results)
            2
        """
        if entry.name not in self._table:
            self._table[entry.name] = []
        self._table[entry.name].append(entry)

    def lookup(self, name: str, context_file: str | None = None) -> list[SymbolEntry]:
        """Find all definitions of a symbol, optionally prioritizing context file.

        This method returns all symbol entries matching the given name. If a context
        file is provided, it prioritizes definitions from that file first.

        Priority Logic:
        1. If context_file is provided and symbol exists in that file: return only those
        2. Otherwise: return all definitions

        Args:
            name: Symbol name to search for
            context_file: Optional file path for context-based prioritization

        Returns:
            List of matching symbol entries. Empty list if symbol not found.
            If context_file provided and matches exist, returns only same-file matches.
            Otherwise returns all matches.

        Example:
            >>> # Without context: returns all definitions
            >>> results = table.lookup("helper")
            >>> len(results)
            2

            >>> # With context: prioritizes same-file definition
            >>> results = table.lookup("helper", context_file="app.py")
            >>> len(results)
            1
            >>> results[0].file_path
            'app.py'
        """
        results = self._table.get(name, [])

        # If context provided, prioritize same-file definitions
        if context_file:
            same_file = [e for e in results if e.file_path == context_file]
            if same_file:
                return same_file

        return results

    def lookup_in_file(self, name: str, file_path: str) -> SymbolEntry | None:
        """Find a symbol definition in a specific file.

        This method searches for an exact match: symbol name must match AND
        file path must match.

        Args:
            name: Symbol name to search for
            file_path: Exact file path where symbol should be defined

        Returns:
            Symbol entry if found in the specified file, None otherwise

        Example:
            >>> entry = table.lookup_in_file("helper", "utils.py")
            >>> if entry:
            ...     print(f"Found {entry.name} at line {entry.line_start}")
            Found helper at line 20
        """
        entries = self._table.get(name, [])
        for entry in entries:
            if entry.file_path == file_path:
                return entry
        return None

    def lookup_qualified(
        self, qualified_name: str, context_file: str | None = None
    ) -> list[SymbolEntry]:
        """Find symbols by qualified name (for Java: ClassName.methodName).

        This method supports Java-style qualified names where methods/fields are
        referenced as "ClassName.methodName" or fully qualified as
        "com.example.service.UserService.createUser".

        Resolution Strategy:
        1. Try exact match of the full qualified name
        2. Try matching the simple name (last component after final dot)
        3. Filter results by context file if provided

        Args:
            qualified_name: Qualified symbol name (e.g., "UserService.createUser")
            context_file: Optional file path for context-based prioritization

        Returns:
            List of matching symbol entries

        Example:
            >>> # Java method call: repository.save(email)
            >>> entries = table.lookup_qualified("save")
            >>> # Returns all 'save' methods

            >>> # Java static call: UserRepository.save(email)
            >>> entries = table.lookup_qualified("UserRepository.save")
            >>> # Returns save() method in UserRepository class

            >>> # With context
            >>> entries = table.lookup_qualified("createUser", context_file="UserService.java")
            >>> # Prioritizes createUser() in UserService.java
        """
        # Strategy 1: Try exact match first
        if qualified_name in self._table:
            results = self._table[qualified_name]
            if context_file:
                same_file = [e for e in results if e.file_path == context_file]
                if same_file:
                    return same_file
            return results

        # Strategy 2: Extract simple name (last component after dot)
        # For "UserService.createUser", extract "createUser"
        if "." in qualified_name:
            simple_name = qualified_name.split(".")[-1]
            class_part = qualified_name.rsplit(".", 1)[0]  # "UserService"

            # Lookup simple name
            results = self._table.get(simple_name, [])

            # Filter by class name if possible
            # Check if node_id contains the class part
            filtered = []
            for entry in results:
                # node_id format: "module:UserService:class:UserService:method:createUser"
                # Check if class_part appears in node_id
                if class_part in entry.node_id or class_part in entry.file_path:
                    filtered.append(entry)

            # If we found matches by class filtering, return them
            if filtered:
                if context_file:
                    same_file = [e for e in filtered if e.file_path == context_file]
                    if same_file:
                        return same_file
                return filtered

            # Otherwise return all simple name matches
            if context_file:
                same_file = [e for e in results if e.file_path == context_file]
                if same_file:
                    return same_file
            return results

        # Strategy 3: Fallback to regular lookup
        return self.lookup(qualified_name, context_file)


class SymbolTableBuilder:
    """Build symbol table from code graphs.

    This class extracts function/class/method definitions from per-file code graphs
    and constructs a unified project-wide symbol table.

    The builder processes NetworkX DiGraph objects (one per file) that contain nodes
    with 'type' attribute indicating node type (FUNCTION, CLASS, METHOD, etc.).

    Example:
        >>> builder = SymbolTableBuilder()
        >>> file_graphs = {
        ...     "app.py": graph1,  # NetworkX DiGraph with function nodes
        ...     "utils.py": graph2  # NetworkX DiGraph with function nodes
        ... }
        >>> table = builder.build(file_graphs)
        >>> results = table.lookup("main")
    """

    def build(self, file_graphs: dict[str, nx.DiGraph]) -> SymbolTable:
        """Build symbol table from all file graphs.

        This method iterates through all provided file graphs, extracts nodes
        representing functions/classes/methods, and adds them to a new symbol table.

        Extraction Rules:
        - Only nodes with type='FUNCTION', 'CLASS', or 'METHOD' are extracted
        - Each node must have 'name' attribute
        - Line information (line_start, line_end) defaults to 0 if missing

        Args:
            file_graphs: Dictionary mapping file paths to their NetworkX DiGraph
                        representation. Each graph should contain nodes with:
                        - type: "FUNCTION", "CLASS", or "METHOD"
                        - name: Symbol name
                        - line_start: Starting line (optional, defaults to 0)
                        - line_end: Ending line (optional, defaults to 0)

        Returns:
            Populated SymbolTable with all extracted symbols

        Example:
            >>> builder = SymbolTableBuilder()
            >>> # Assume graphs have FUNCTION/METHOD nodes with 'name', 'type', etc.
            >>> table = builder.build({"app.py": graph1, "utils.py": graph2})
            >>> table.lookup("helper")
            [SymbolEntry(node_id='utils.py:helper', ...)]
        """
        table = SymbolTable()

        for file_path, graph in file_graphs.items():
            for node_id, data in graph.nodes(data=True):
                # Only extract FUNCTION, CLASS, and METHOD nodes
                if data.get("type") in ["FUNCTION", "CLASS", "METHOD"]:
                    entry = SymbolEntry(
                        node_id=node_id,
                        file_path=file_path,
                        name=data["name"],
                        type=data["type"],
                        line_start=data.get("line_start", 0),
                        line_end=data.get("line_end", 0),
                    )
                    table.add(entry)

        return table
