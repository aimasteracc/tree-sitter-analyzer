#!/usr/bin/env python3
"""
Project Indexer for Code Intelligence Graph.

Scans a project directory and populates SymbolIndex, CallGraphBuilder,
and DependencyGraphBuilder with data from all Python source files.

Designed for lazy, on-demand graph construction as described in the design doc:
"Graphs are built on-demand per MCP tool call, not maintained as a persistent index."
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .call_graph import CallGraphBuilder
from .dependency_graph import DependencyGraphBuilder
from .import_resolver import PythonImportResolver
from .models import DependencyEdge, SymbolDefinition, SymbolReference
from .symbol_index import SymbolIndex

logger = logging.getLogger(__name__)

try:
    import tree_sitter
    import tree_sitter_python

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

# Directories to skip during scanning
_SKIP_DIRS = frozenset({
    "__pycache__",
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".env",
    ".tox",
    ".nox",
    ".mypy_cache",
    ".pytest_cache",
    ".hypothesis",
    "htmlcov",
    ".eggs",
    "dist",
    "build",
    "*.egg-info",
})

# Max files to index to avoid performance issues
_MAX_FILES = 500


class ProjectIndexer:
    """
    Scans a project and populates intelligence data structures.

    Lazily indexes Python files under a project root, extracting:
    - Symbol definitions (classes, functions, methods)
    - Symbol references (calls, imports, inheritance)
    - Call sites (function/method calls)
    - Dependency edges (import relationships)
    - Inheritance relationships
    """

    def __init__(self, project_root: str) -> None:
        self._project_root = project_root
        self._symbol_index = SymbolIndex()
        self._call_graph = CallGraphBuilder()
        self._dep_graph = DependencyGraphBuilder()
        self._import_resolver = PythonImportResolver()
        self._indexed = False
        self._indexed_files: set[str] = set()
        self._parser: Any = None

    @property
    def symbol_index(self) -> SymbolIndex:
        """Get the populated symbol index."""
        return self._symbol_index

    @property
    def call_graph(self) -> CallGraphBuilder:
        """Get the populated call graph."""
        return self._call_graph

    @property
    def dep_graph(self) -> DependencyGraphBuilder:
        """Get the populated dependency graph."""
        return self._dep_graph

    @property
    def is_indexed(self) -> bool:
        """Whether the project has been indexed."""
        return self._indexed

    def _get_parser(self) -> Any:
        """Get or create a tree-sitter parser for Python."""
        if self._parser is not None:
            return self._parser

        if not TREE_SITTER_AVAILABLE:
            return None

        try:
            language = tree_sitter.Language(tree_sitter_python.language())
            parser = tree_sitter.Parser()
            if hasattr(parser, "set_language"):
                parser.set_language(language)
            else:
                parser.language = language
            self._parser = parser
            return parser
        except Exception:
            return None

    def ensure_indexed(self, path: str | None = None) -> None:
        """
        Ensure the project (or a specific path) is indexed.

        This is the main entry point. Call before querying any data structure.
        Indexing is idempotent — calling multiple times is safe.

        Args:
            path: Optional sub-path to index. Defaults to project_root.
        """
        if self._indexed:
            return
        self.index_project(path)

    def index_project(self, path: str | None = None) -> None:
        """
        Index all Python files under the given path.

        Args:
            path: Directory to scan. Defaults to project_root.
        """
        target = path or self._project_root
        if not target or not os.path.isdir(target):
            logger.warning(f"Cannot index: path does not exist or is not a directory: {target}")
            self._indexed = True
            return

        py_files = self._discover_python_files(target)
        logger.info(f"Indexing {len(py_files)} Python files under {target}")

        for file_path in py_files:
            try:
                self._index_single_file(file_path)
            except Exception as e:
                logger.debug(f"Failed to index {file_path}: {e}")

        self._indexed = True
        logger.info(
            f"Indexing complete: {len(self._indexed_files)} files, "
            f"{sum(len(v) for v in self._symbol_index.get_all_definitions().values())} definitions, "
            f"{sum(len(v) for v in self._symbol_index.get_all_references().values())} references"
        )

    def _discover_python_files(self, root: str) -> list[str]:
        """Discover all Python files under root, respecting skip rules."""
        py_files: list[str] = []

        for dirpath, dirnames, filenames in os.walk(root):
            # Filter out skip directories in-place
            dirnames[:] = [
                d for d in dirnames
                if d not in _SKIP_DIRS and not d.endswith(".egg-info")
            ]

            for filename in filenames:
                if filename.endswith(".py"):
                    full_path = os.path.join(dirpath, filename)
                    py_files.append(full_path)

                    if len(py_files) >= _MAX_FILES:
                        logger.warning(
                            f"Reached max file limit ({_MAX_FILES}). "
                            f"Some files may not be indexed."
                        )
                        return py_files

        return py_files

    def _index_single_file(self, file_path: str) -> None:
        """Index a single Python file: extract symbols, calls, imports."""
        if file_path in self._indexed_files:
            return

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source_code = f.read()
        except (OSError, IOError) as e:
            logger.debug(f"Cannot read {file_path}: {e}")
            return

        # Use relative path for consistent indexing
        rel_path = self._relative_path(file_path)

        # 1. Extract call sites using CallGraphBuilder
        call_sites = self._call_graph.extract_calls_from_source(source_code, rel_path)

        # 2. Parse AST for symbols and imports
        parser = self._get_parser()
        if parser is None:
            self._indexed_files.add(file_path)
            return

        try:
            tree = parser.parse(source_code.encode("utf-8"))
        except Exception:
            self._indexed_files.add(file_path)
            return

        # 3. Extract symbol definitions, references, imports, inheritance
        self._extract_symbols(tree.root_node, rel_path, source_code)
        self._extract_imports(tree.root_node, rel_path, source_code)

        # 4. Add call sites as symbol references for cross-referencing
        for call_site in call_sites:
            self._symbol_index.add_reference(
                SymbolReference(
                    symbol_name=call_site.callee_name,
                    file_path=rel_path,
                    line=call_site.line,
                    ref_type="call",
                    context_function=call_site.caller_function,
                )
            )

        self._indexed_files.add(file_path)

    def _relative_path(self, file_path: str) -> str:
        """Convert absolute path to relative path from project root."""
        try:
            return os.path.relpath(file_path, self._project_root).replace("\\", "/")
        except ValueError:
            # On Windows, relpath can fail across drives
            return file_path.replace("\\", "/")

    def _extract_symbols(
        self, root_node: Any, file_path: str, source_code: str
    ) -> None:
        """Extract class and function definitions from AST."""
        self._walk_for_symbols(root_node, file_path, source_code, parent_class=None)

    def _walk_for_symbols(
        self,
        node: Any,
        file_path: str,
        source_code: str,
        parent_class: str | None,
    ) -> None:
        """Recursively walk AST nodes to extract symbol definitions."""
        if node.type == "class_definition":
            class_info = self._extract_class_def(node, file_path, source_code)
            if class_info:
                self._symbol_index.add_definition(class_info["definition"])

                # Handle inheritance
                if class_info.get("bases"):
                    for base in class_info["bases"]:
                        self._symbol_index.set_class_parent(
                            class_info["definition"].name, base
                        )
                        # Add inheritance reference
                        self._symbol_index.add_reference(
                            SymbolReference(
                                symbol_name=base,
                                file_path=file_path,
                                line=class_info["definition"].line,
                                ref_type="inheritance",
                            )
                        )

                # Walk children with class context
                for child in node.children:
                    self._walk_for_symbols(
                        child, file_path, source_code,
                        parent_class=class_info["definition"].name,
                    )
                return

        if node.type in ("function_definition", "async_function_definition"):
            func_def = self._extract_function_def(
                node, file_path, source_code, parent_class
            )
            if func_def:
                self._symbol_index.add_definition(func_def)

        # Continue walking children
        for child in node.children:
            self._walk_for_symbols(child, file_path, source_code, parent_class)

    def _extract_class_def(
        self, node: Any, file_path: str, source_code: str
    ) -> dict[str, Any] | None:
        """Extract a class definition from a class_definition node."""
        class_name = None
        bases: list[str] = []

        for child in node.children:
            if child.type == "identifier":
                class_name = self._node_text(child)
            elif child.type == "argument_list":
                # Extract base classes
                for arg_child in child.children:
                    if arg_child.type == "identifier":
                        bases.append(self._node_text(arg_child))
                    elif arg_child.type == "attribute":
                        bases.append(self._node_text(arg_child))

        if not class_name:
            return None

        line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        # Extract docstring
        docstring = self._extract_docstring(node)

        # Extract decorators/modifiers
        modifiers = self._extract_decorators(node, source_code)

        # Detect abstract classes from inheritance (ABC, Protocol, ABCMeta)
        abstract_bases = {"ABC", "ABCMeta", "Protocol"}
        for base_name in bases:
            # Handle qualified names like abc.ABC
            simple_name = base_name.rsplit(".", 1)[-1] if "." in base_name else base_name
            if simple_name in abstract_bases:
                if simple_name not in modifiers:
                    modifiers.append(simple_name)

        # Check for @abstractmethod in child methods
        if self._has_abstract_method(node):
            if "abstractmethod" not in modifiers:
                modifiers.append("abstractmethod")

        definition = SymbolDefinition(
            name=class_name,
            file_path=file_path,
            line=line,
            end_line=end_line,
            symbol_type="class",
            docstring=docstring,
            modifiers=modifiers,
        )

        return {"definition": definition, "bases": bases}

    @staticmethod
    def _has_abstract_method(class_node: Any) -> bool:
        """Check if a class has any @abstractmethod-decorated methods."""
        for child in class_node.children:
            if child.type == "block":
                for stmt in child.children:
                    if stmt.type == "decorated_definition":
                        for dec_child in stmt.children:
                            if dec_child.type == "decorator":
                                text = getattr(dec_child, "text", b"")
                                if isinstance(text, bytes):
                                    text = text.decode("utf-8")
                                if "abstractmethod" in text:
                                    return True
        return False

    def _extract_function_def(
        self,
        node: Any,
        file_path: str,
        source_code: str,
        parent_class: str | None,
    ) -> SymbolDefinition | None:
        """Extract a function/method definition from a function_definition node."""
        func_name = None
        parameters: list[str] = []

        for child in node.children:
            if child.type == "identifier":
                func_name = self._node_text(child)
            elif child.type == "parameters":
                parameters = self._extract_parameters(child)

        if not func_name:
            return None

        line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        # Determine symbol type
        symbol_type = "method" if parent_class else "function"

        # Extract return type annotation
        return_type = None
        for child in node.children:
            if child.type == "type":
                return_type = self._node_text(child)

        # Extract docstring
        docstring = self._extract_docstring(node)

        # Extract decorators
        modifiers = self._extract_decorators(node, source_code)

        return SymbolDefinition(
            name=func_name,
            file_path=file_path,
            line=line,
            end_line=end_line,
            symbol_type=symbol_type,
            parameters=parameters,
            return_type=return_type,
            parent_class=parent_class,
            docstring=docstring,
            modifiers=modifiers,
        )

    def _extract_parameters(self, params_node: Any) -> list[str]:
        """Extract parameter names from a parameters node."""
        params: list[str] = []
        for child in params_node.children:
            if child.type == "identifier":
                params.append(self._node_text(child))
            elif child.type in (
                "default_parameter",
                "typed_parameter",
                "typed_default_parameter",
            ):
                # Get the name from the first identifier child
                for sub in child.children:
                    if sub.type == "identifier":
                        params.append(self._node_text(sub))
                        break
            elif child.type in ("list_splat_pattern", "dictionary_splat_pattern"):
                for sub in child.children:
                    if sub.type == "identifier":
                        params.append("*" + self._node_text(sub))
                        break
        return params

    def _extract_docstring(self, node: Any) -> str | None:
        """Extract docstring from a class or function node."""
        # Look for the body (block node), then first expression_statement with string
        for child in node.children:
            if child.type == "block":
                for block_child in child.children:
                    if block_child.type == "expression_statement":
                        for expr_child in block_child.children:
                            if expr_child.type == "string":
                                text = self._node_text(expr_child)
                                # Strip quotes
                                if text.startswith(('"""', "'''")):
                                    return text[3:-3].strip()
                                elif text.startswith(('"', "'")):
                                    return text[1:-1].strip()
                        break  # Only check first statement
                break
        return None

    def _extract_decorators(self, node: Any, source_code: str) -> list[str]:
        """Extract decorator names from a decorated definition."""
        decorators: list[str] = []
        # Check sibling nodes before the definition
        parent = node.parent
        if parent and parent.type == "decorated_definition":
            for child in parent.children:
                if child.type == "decorator":
                    text = self._node_text(child)
                    if text.startswith("@"):
                        decorators.append(text[1:].split("(")[0])
        return decorators

    def _extract_imports(
        self, root_node: Any, file_path: str, source_code: str
    ) -> None:
        """Extract import statements and build dependency edges + references."""
        self._walk_for_imports(root_node, file_path, source_code)

    def _walk_for_imports(
        self, node: Any, file_path: str, source_code: str,
        is_type_check_only: bool = False,
    ) -> None:
        """Recursively walk AST for import nodes.

        Args:
            node: Current AST node.
            file_path: Relative file path.
            source_code: Full source code.
            is_type_check_only: Whether we're inside an ``if TYPE_CHECKING:`` block.
        """
        if node.type == "import_statement":
            self._process_import_statement(node, file_path, is_type_check_only)
        elif node.type == "import_from_statement":
            self._process_import_from_statement(node, file_path, is_type_check_only)
        elif node.type == "if_statement":
            # Detect `if TYPE_CHECKING:` blocks
            in_type_checking = self._is_type_checking_guard(node)
            for child in node.children:
                self._walk_for_imports(child, file_path, source_code,
                                       is_type_check_only=in_type_checking or is_type_check_only)
            return

        for child in node.children:
            self._walk_for_imports(child, file_path, source_code, is_type_check_only)

    @staticmethod
    def _is_type_checking_guard(if_node: Any) -> bool:
        """Check if an if_statement node is `if TYPE_CHECKING:`."""
        for child in if_node.children:
            if child.type == "identifier":
                text = getattr(child, "text", b"")
                if isinstance(text, bytes):
                    text = text.decode("utf-8")
                return text == "TYPE_CHECKING"
        return False

    def _process_import_statement(
        self, node: Any, file_path: str, is_type_check_only: bool = False
    ) -> None:
        """Process 'import X' or 'import X as Y' statements."""
        for child in node.children:
            if child.type == "dotted_name":
                module_name = self._node_text(child)
                self._add_import_edge(
                    file_path=file_path,
                    module_name=module_name,
                    imported_names=[],
                    line=node.start_point[0] + 1,
                    is_relative=False,
                    is_type_check_only=is_type_check_only,
                )
            elif child.type == "aliased_import":
                for sub in child.children:
                    if sub.type == "dotted_name":
                        module_name = self._node_text(sub)
                        self._add_import_edge(
                            file_path=file_path,
                            module_name=module_name,
                            imported_names=[],
                            line=node.start_point[0] + 1,
                            is_relative=False,
                            is_type_check_only=is_type_check_only,
                        )
                        break

    def _process_import_from_statement(
        self, node: Any, file_path: str, is_type_check_only: bool = False
    ) -> None:
        """Process 'from X import Y, Z' or 'from X import *' statements.

        Tree-sitter AST structure:
          import_from_statement
            from
            relative_import OR dotted_name  (the module)
            import
            dotted_name / identifier / import_list / wildcard_import  (the imported names)
        """
        module_name = ""
        imported_names: list[str] = []
        is_relative = False
        seen_import_keyword = False

        for child in node.children:
            if child.type == "import":
                # The 'import' keyword separates module from imported names
                seen_import_keyword = True
                continue

            if not seen_import_keyword:
                # Before 'import' keyword: module specification
                if child.type == "relative_import":
                    is_relative = True
                    module_name = self._node_text(child)
                elif child.type == "dotted_name":
                    module_name = self._node_text(child)
                elif child.type == "import_prefix":
                    prefix_text = self._node_text(child)
                    if prefix_text and all(c == "." for c in prefix_text):
                        is_relative = True
                        module_name = prefix_text
            else:
                # After 'import' keyword: imported names
                if child.type == "dotted_name":
                    imported_names.append(self._node_text(child))
                elif child.type == "identifier":
                    imported_names.append(self._node_text(child))
                elif child.type == "wildcard_import":
                    imported_names.append("*")
                elif child.type == "import_list":
                    for item in child.children:
                        if item.type == "dotted_name":
                            imported_names.append(self._node_text(item))
                        elif item.type == "identifier":
                            imported_names.append(self._node_text(item))
                        elif item.type == "aliased_import":
                            for sub in item.children:
                                if sub.type in ("dotted_name", "identifier"):
                                    imported_names.append(self._node_text(sub))
                                    break

        if not module_name and is_relative:
            module_name = "."

        if module_name:
            # Add import reference for each imported name
            for name in imported_names:
                if name != "*":
                    self._symbol_index.add_reference(
                        SymbolReference(
                            symbol_name=name,
                            file_path=file_path,
                            line=node.start_point[0] + 1,
                            ref_type="import",
                        )
                    )

            self._add_import_edge(
                file_path=file_path,
                module_name=module_name,
                imported_names=imported_names,
                line=node.start_point[0] + 1,
                is_relative=is_relative,
                is_type_check_only=is_type_check_only,
            )

    def _add_import_edge(
        self,
        file_path: str,
        module_name: str,
        imported_names: list[str],
        line: int,
        is_relative: bool,
        is_type_check_only: bool = False,
    ) -> None:
        """Resolve an import and add a dependency edge."""
        # Need absolute path of source file for relative import resolution
        abs_source = os.path.join(self._project_root, file_path)

        resolved = self._import_resolver.resolve_import(
            module_name=module_name,
            imported_names=imported_names,
            source_file=abs_source,
            project_root=self._project_root,
            is_relative=is_relative,
        )

        if resolved.is_resolved and not resolved.is_external and resolved.resolved_path:
            target_rel = self._relative_path(resolved.resolved_path)
            edge = DependencyEdge(
                source_file=file_path,
                target_file=target_rel,
                target_module=module_name,
                imported_names=imported_names,
                is_external=False,
                line=line,
                is_type_check_only=is_type_check_only,
            )
            self._dep_graph.add_edge(edge)
        elif resolved.is_external:
            # Still record external deps (without target_file)
            edge = DependencyEdge(
                source_file=file_path,
                target_file="",
                target_module=module_name,
                imported_names=imported_names,
                is_external=True,
                line=line,
                is_type_check_only=is_type_check_only,
            )
            self._dep_graph.add_edge(edge)

    @staticmethod
    def _node_text(node: Any) -> str:
        """Get text from a tree-sitter node."""
        text = getattr(node, "text", b"")
        if isinstance(text, bytes):
            return text.decode("utf-8")
        return str(text)

    def reset(self) -> None:
        """Reset the indexer to allow re-indexing."""
        self._symbol_index.clear()
        self._dep_graph.clear()
        self._call_graph = CallGraphBuilder()
        self._indexed = False
        self._indexed_files.clear()
