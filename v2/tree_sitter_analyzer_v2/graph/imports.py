"""
Import resolution for cross-file call tracking.

This module provides components for parsing and resolving Python import statements,
enabling cross-file call graph construction.

Components:
- Import: Dataclass representing a single import statement
- ImportResolver: Resolves import statements to file paths
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx


@dataclass
class Import:
    """Represents a single Python import statement.

    Examples:
        >>> # import os
        >>> Import(module="os", names=[], alias=None, import_type="absolute", level=0)

        >>> # from utils import helper
        >>> Import(module="utils", names=["helper"], alias=None, import_type="absolute", level=0)

        >>> # from . import sibling
        >>> Import(module="", names=["sibling"], alias=None, import_type="relative", level=1)

        >>> # import numpy as np
        >>> Import(module="numpy", names=[], alias={"numpy": "np"}, import_type="absolute", level=0)
    """

    module: str
    """Module name (e.g., 'utils.parser' or 'os')."""

    names: list[str]
    """Imported names (e.g., ['parse_data', 'validate'] for 'from x import parse_data, validate')."""

    alias: dict[str, str] | None
    """Aliases mapping (e.g., {'numpy': 'np'} for 'import numpy as np')."""

    import_type: str
    """Import type: 'absolute' or 'relative'."""

    level: int
    """Relative import level: 0 for absolute, 1 for '.', 2 for '..', etc."""

    wildcard: bool = False
    """True if import uses wildcard: 'from x import *'."""


class ImportResolver:
    """Resolves Python import statements to file paths.

    This class provides functionality to:
    - Parse import statements from Python files using tree-sitter
    - Resolve absolute imports (from package.module import func)
    - Resolve relative imports (from . import sibling)
    - Build import dependency graph for project

    Args:
        project_root: Root directory of the Python project

    Example:
        >>> resolver = ImportResolver(Path("/path/to/project"))
        >>> imports = resolver.parse_imports(Path("app/main.py"))
        >>> for imp in imports:
        ...     path = resolver.resolve_import(imp, Path("app/main.py"))
        ...     print(f"{imp.module} -> {path}")
    """

    def __init__(self, project_root: Path):
        """Initialize ImportResolver.

        Args:
            project_root: Root directory of the Python project
        """
        self.project_root = Path(project_root).resolve()
        self.module_cache: dict[str, Path | None] = {}
        """Cache for resolved module paths to avoid redundant file system checks."""

    def parse_imports(self, file_path: Path) -> list[Import]:
        """Extract all import statements from a Python file.

        Uses tree-sitter to parse the file and extract:
        - import statements: import x, import x as y
        - from-import statements: from x import y, from x import y as z
        - relative imports: from . import x, from .. import y

        Args:
            file_path: Path to Python file to parse

        Returns:
            List of Import objects representing all import statements

        Example:
            >>> imports = resolver.parse_imports(Path("app.py"))
            >>> [imp.module for imp in imports]
            ['os', 'sys', 'utils.helper']
        """
        from tree_sitter_analyzer_v2.core.parser import TreeSitterParser

        # Read file content
        file_path = Path(file_path)
        try:
            source_code = file_path.read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            return []

        # Parse with tree-sitter
        parser = TreeSitterParser("python")
        parse_result = parser.parse(source_code, str(file_path))

        if not parse_result.tree:
            return []

        # Extract imports
        imports: list[Import] = []
        self._traverse_for_imports(parse_result.tree, imports)
        return imports

    def _traverse_for_imports(self, node: Any, imports: list[Import]) -> None:
        """Recursively traverse AST to find import statements."""
        if node.type == "import_statement":
            # import x, import x as y
            import_obj = self._extract_import_statement(node)
            if import_obj:
                imports.append(import_obj)

        elif node.type == "import_from_statement":
            # from x import y, from . import y
            import_obj = self._extract_from_import(node)
            if import_obj:
                imports.append(import_obj)

        # Recursively check children
        for child in node.children:
            self._traverse_for_imports(child, imports)

    def _extract_import_statement(self, node: Any) -> Import | None:
        """Extract info from 'import x' or 'import x as y' statement."""
        for child in node.children:
            if child.type == "dotted_name":
                # Simple import: import os
                return Import(
                    module=child.text or "",
                    names=[],
                    alias=None,
                    import_type="absolute",
                    level=0,
                    wildcard=False,
                )
            elif child.type == "aliased_import":
                # import x as y
                module_name = None
                alias_name = None
                for grandchild in child.children:
                    if grandchild.type == "dotted_name":
                        module_name = grandchild.text
                    elif grandchild.type == "identifier":
                        alias_name = grandchild.text

                if module_name:
                    return Import(
                        module=module_name,
                        names=[],
                        alias={module_name: alias_name} if alias_name else None,
                        import_type="absolute",
                        level=0,
                        wildcard=False,
                    )

        return None

    def _extract_from_import(self, node: Any) -> Import | None:
        """Extract info from 'from x import y' or 'from . import y' statement."""
        module_name = ""
        imported_names: list[str] = []
        aliases: dict[str, str] = {}
        level = 0
        is_wildcard = False
        found_import_keyword = False

        for child in node.children:
            # Check for relative import prefix (., .., ...)
            if child.type == "relative_import":
                level = self._count_relative_level(child)
                # Extract module name from relative import if present
                for grandchild in child.children:
                    if grandchild.type == "dotted_name":
                        module_name = grandchild.text or ""
            # Regular module name (absolute import)
            elif child.type == "dotted_name" and not found_import_keyword:
                module_name = child.text or ""
            # Found "import" keyword
            elif child.text == "import":
                found_import_keyword = True
            # After "import", collect imported names
            elif found_import_keyword:
                if child.type == "wildcard_import" or child.text == "*":
                    is_wildcard = True
                    imported_names.append("*")
                elif child.type == "dotted_name" and child.text:
                    imported_names.append(child.text)
                elif child.type == "aliased_import":
                    # from x import y as z
                    name = None
                    alias = None
                    for grandchild in child.children:
                        if grandchild.type in ["identifier", "dotted_name"] and grandchild.text:
                            if name is None:
                                name = grandchild.text
                            else:
                                alias = grandchild.text
                    if name:
                        imported_names.append(name)
                        if alias:
                            aliases[name] = alias
                elif child.type == "identifier" and child.text:
                    imported_names.append(child.text)

        # Determine import type
        import_type = "relative" if level > 0 else "absolute"

        return Import(
            module=module_name,
            names=imported_names,
            alias=aliases if aliases else None,
            import_type=import_type,
            level=level,
            wildcard=is_wildcard,
        )

    def _count_relative_level(self, node: Any) -> int:
        """Count relative import level (., .., ...) from relative_import node."""
        level = 0
        for child in node.children:
            if child.type == "import_prefix":
                # Count dots in import_prefix
                text = child.text or ""
                level = text.count(".")
                break
        return level if level > 0 else 1  # Default to 1 if no prefix found

    def resolve_import(self, import_stmt: Import, from_file: Path) -> Path | None:
        """Resolve an import statement to actual file path.

        Resolution strategy:
        1. If relative import: resolve relative to from_file's directory
        2. If absolute import: resolve from project_root
        3. Return None if module is external (not in project) or not found

        Args:
            import_stmt: Import statement to resolve
            from_file: File containing the import statement (for relative imports)

        Returns:
            Resolved file path, or None if external/not found

        Example:
            >>> imp = Import(module="utils.helper", names=["parse"], ...)
            >>> resolver.resolve_import(imp, Path("app/main.py"))
            Path("/path/to/project/utils/helper.py")
        """
        if import_stmt.import_type == "relative":
            return self._resolve_relative(import_stmt, from_file)
        else:
            return self._resolve_absolute(import_stmt)

    def _resolve_absolute(self, import_stmt: Import) -> Path | None:
        """Resolve absolute import to file path.

        Converts module path to file path:
        - 'package.module' -> 'package/module.py'
        - 'package' -> 'package/__init__.py' (if exists)

        Args:
            import_stmt: Import statement with absolute module path

        Returns:
            Resolved file path, or None if not found in project

        Example:
            >>> imp = Import(module="utils.parser", ...)
            >>> resolver._resolve_absolute(imp)
            Path("/path/to/project/utils/parser.py")
        """
        if not import_stmt.module:
            return None

        # Check cache first
        cache_key = import_stmt.module
        if cache_key in self.module_cache:
            return self.module_cache[cache_key]

        # Convert module path to file path
        # e.g., "package.subpackage.module" -> "package/subpackage/module"
        parts = import_stmt.module.split(".")
        relative_path = Path(*parts) if len(parts) > 1 else Path(parts[0])

        # Try 1: module.py (preferred)
        candidate = self.project_root / relative_path.with_suffix(".py")
        if candidate.exists() and candidate.is_file():
            self.module_cache[cache_key] = candidate
            return candidate

        # Try 2: module/__init__.py (package)
        init_candidate = self.project_root / relative_path / "__init__.py"
        if init_candidate.exists() and init_candidate.is_file():
            self.module_cache[cache_key] = init_candidate
            return init_candidate

        # Not found in project (likely external package or typo)
        self.module_cache[cache_key] = None
        return None

    def _resolve_relative(self, import_stmt: Import, from_file: Path) -> Path | None:
        """Resolve relative import to file path.

        Handles:
        - from . import x (sibling)
        - from .. import x (parent)
        - from ...package import x (grandparent)

        Args:
            import_stmt: Import statement with relative module path
            from_file: File containing the import (determines base directory)

        Returns:
            Resolved file path, or None if invalid or not found

        Example:
            >>> imp = Import(module="", names=["helper"], level=1, ...)
            >>> resolver._resolve_relative(imp, Path("app/main.py"))
            Path("/path/to/project/app/helper.py")
        """
        from_file = Path(from_file)

        # Start from the directory containing from_file
        base_dir = from_file.parent

        # Go up 'level - 1' directories
        # level=1 means current directory (.), level=2 means parent (..), etc.
        try:
            for _ in range(import_stmt.level - 1):
                base_dir = base_dir.parent
                # Check if we've gone above project root
                if not base_dir.is_relative_to(self.project_root):
                    return None
        except (ValueError, OSError):
            # Can't go up further
            return None

        # If there's a module component, resolve it first
        if import_stmt.module:
            # e.g., "from ..utils import helper" -> base_dir / utils
            module_parts = import_stmt.module.split(".")
            module_path = Path(*module_parts) if len(module_parts) > 1 else Path(module_parts[0])
            base_dir = base_dir / module_path

        # Now resolve the imported name if present
        if import_stmt.names and import_stmt.names[0] != "*":
            # e.g., "from . import helper" or "from ..utils import helper"
            # Try to find helper.py in base_dir
            name = import_stmt.names[0]

            # Try 1: name.py (e.g., helper.py)
            candidate = base_dir / f"{name}.py"
            if candidate.exists() and candidate.is_file():
                return candidate

            # Try 2: name/__init__.py (e.g., helper/__init__.py)
            init_candidate = base_dir / name / "__init__.py"
            if init_candidate.exists() and init_candidate.is_file():
                return init_candidate

            # Try 3: If module was specified, return module's __init__.py
            # (the name might be defined in __init__.py)
            if import_stmt.module:
                module_init = base_dir / "__init__.py"
                if module_init.exists() and module_init.is_file():
                    return module_init
        else:
            # No specific name, resolve to module itself
            # Try 1: module.py
            if not import_stmt.module:
                return None

            # base_dir already has module path appended
            # Try as .py file first (go up one level and try as file)
            if import_stmt.module:
                module_as_file = base_dir.with_suffix(".py")
                if module_as_file.exists() and module_as_file.is_file():
                    return module_as_file

            # Try 2: module/__init__.py
            module_init = base_dir / "__init__.py"
            if module_init.exists() and module_init.is_file():
                return module_init

        # Not found
        return None

    def build_import_graph(self, files: list[Path]) -> nx.DiGraph:
        """Build import dependency graph for all files.

        Creates a directed graph where:
        - Nodes: File paths (as strings)
        - Edges: Import relationships (file1 imports from file2)
        - Edge attributes:
          - type: "IMPORTS"
          - imported_names: List of imported names
          - aliases: Dict of aliases (if any)

        Args:
            files: List of Python files to analyze

        Returns:
            NetworkX directed graph of import dependencies

        Example:
            >>> files = [Path("main.py"), Path("utils/helper.py")]
            >>> graph = resolver.build_import_graph(files)
            >>> graph.has_edge("main.py", "utils/helper.py")
            True
            >>> graph["main.py"]["utils/helper.py"]["type"]
            'IMPORTS'
        """
        graph: nx.DiGraph = nx.DiGraph()

        # Add all files as nodes first (using absolute paths for consistency)
        for file in files:
            file_abs = Path(file).resolve()
            graph.add_node(str(file_abs))

        # Process each file's imports
        for file in files:
            file = Path(file).resolve()

            # Parse imports from this file
            imports = self.parse_imports(file)

            # Resolve each import and create edges
            for import_stmt in imports:
                # Resolve import to file path
                target_file = self.resolve_import(import_stmt, file)

                # Only create edge if target is in our project and in the file list
                if target_file and str(target_file) in graph:
                    # Create edge with metadata
                    edge_data: dict[str, Any] = {
                        "type": "IMPORTS",
                        "imported_names": import_stmt.names,
                    }

                    # Add aliases if present
                    if import_stmt.alias:
                        edge_data["aliases"] = import_stmt.alias

                    graph.add_edge(str(file), str(target_file), **edge_data)

        return graph
