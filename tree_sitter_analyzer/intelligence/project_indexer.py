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
_SKIP_DIRS = frozenset(
    {
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
    }
)

# Max files to index to avoid performance issues
_MAX_FILES = 2000


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

    @staticmethod
    def is_test_file(file_path: str) -> bool:
        """Classify a file path as a test file or source file.

        A file is considered a test file if:
        - Its basename starts with ``test_`` or ends with ``_test.py``
        - Its basename is ``conftest.py``
        - It lives under a ``tests/`` or ``test/`` directory
        """
        normalized = file_path.replace("\\", "/")
        basename = os.path.basename(normalized)

        # Name-based patterns
        if basename.startswith("test_") and basename.endswith(".py"):
            return True
        if basename.endswith("_test.py"):
            return True
        if basename == "conftest.py":
            return True

        # Directory-based patterns
        parts = normalized.split("/")
        for part in parts[:-1]:  # exclude the filename itself
            if part in ("tests", "test"):
                return True

        return False

    def get_test_files(self) -> set[str]:
        """Return the set of indexed file paths classified as test files."""
        return {
            self._relative_path(f)
            for f in self._indexed_files
            if self.is_test_file(self._relative_path(f))
        }

    def get_source_files(self) -> set[str]:
        """Return the set of indexed file paths classified as source files."""
        return {
            self._relative_path(f)
            for f in self._indexed_files
            if not self.is_test_file(self._relative_path(f))
        }

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
            logger.warning(
                f"Cannot index: path does not exist or is not a directory: {target}"
            )
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
        """Discover Python files under *root* using two-phase prioritisation.

        Phase 1: collect all **source** files (non-test).
        Phase 2: collect **test** files.

        This guarantees that core source directories (e.g. ``mcp/``) are always
        indexed even when ``_MAX_FILES`` would otherwise truncate them.
        """
        source_files: list[str] = []
        test_files: list[str] = []

        for dirpath, dirnames, filenames in os.walk(root):
            # Filter out skip directories in-place
            dirnames[:] = [
                d
                for d in dirnames
                if d not in _SKIP_DIRS and not d.endswith(".egg-info")
            ]

            for filename in filenames:
                if filename.endswith(".py"):
                    full_path = os.path.join(dirpath, filename)
                    rel = os.path.relpath(full_path, root).replace("\\", "/")
                    if self.is_test_file(rel):
                        test_files.append(full_path)
                    else:
                        source_files.append(full_path)

        # Combine: source first, then tests — honour the global cap
        combined = source_files + test_files
        if len(combined) > _MAX_FILES:
            logger.warning(
                f"Reached max file limit ({_MAX_FILES}). "
                f"Some files may not be indexed. "
                f"({len(source_files)} source, {len(test_files)} test, "
                f"keeping first {_MAX_FILES})"
            )
            combined = combined[:_MAX_FILES]
        return combined

    def _index_single_file(self, file_path: str) -> None:
        """Index a single Python file: extract symbols, calls, imports."""
        if file_path in self._indexed_files:
            return

        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                source_code = f.read()
        except OSError as e:
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

        # 3b. Extract attribute references (self.method, obj.attr) to catch
        # dict-dispatch, callback-passing, and other non-call references.
        self._extract_attribute_refs(tree.root_node, rel_path)

        # 3c. Extract isinstance/issubclass argument references.
        # isinstance(x, SomeClass) 中的 SomeClass 不会被调用图或属性引用捕获，
        # 需单独提取，避免将仅通过 isinstance 使用的类误判为死代码。
        self._extract_isinstance_refs(tree.root_node, rel_path)

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
                        child,
                        file_path,
                        source_code,
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
            simple_name = (
                base_name.rsplit(".", 1)[-1] if "." in base_name else base_name
            )
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

    # ------------------------------------------------------------------
    # Attribute reference extraction (v5)
    # ------------------------------------------------------------------
    def _extract_attribute_refs(self, root_node: Any, file_path: str) -> None:
        """Walk the AST and record *attribute* references.

        This catches ``self.method``, ``obj.attr``, etc. that appear outside
        of call-expression positions (which the CallGraphBuilder already
        handles).  The primary benefit is detecting dict-dispatch patterns
        such as ``{node_type: self._extract_xxx}`` and callback-passing
        patterns like ``atexit.register(cleanup_logging)``.
        """
        self._walk_for_attribute_refs(root_node, file_path)

    def _walk_for_attribute_refs(self, node: Any, file_path: str) -> None:
        """Recursively walk AST for ``attribute`` nodes and bare identifiers
        used as references (not definitions)."""
        if node.type == "attribute":
            # Extract the rightmost identifier as the attribute name
            children = [c for c in node.children if c.type == "identifier"]
            if len(children) >= 2:
                attr_name = self._node_text(children[-1])
                if attr_name and not attr_name.startswith("__"):
                    self._symbol_index.add_reference(
                        SymbolReference(
                            symbol_name=attr_name,
                            file_path=file_path,
                            line=node.start_point[0] + 1,
                            ref_type="attribute",
                        )
                    )
            # Don't recurse into attribute children — we already processed them
            return

        for child in node.children:
            self._walk_for_attribute_refs(child, file_path)

    # ------------------------------------------------------------------
    # isinstance/issubclass 参数引用提取 (fix-intelligence-graph)
    # ------------------------------------------------------------------

    # 需要提取类型参数的内置函数集合
    _TYPE_CHECK_BUILTINS = frozenset({"isinstance", "issubclass"})

    def _extract_isinstance_refs(self, root_node: Any, file_path: str) -> None:
        """走读 AST，提取 isinstance/issubclass 第二参数中的类名引用。

        isinstance(x, SomeClass) 和 isinstance(x, (A, B)) 中的类名
        不会被调用图或属性引用捕获，单独提取以避免死代码误报。
        """
        self._walk_for_isinstance_refs(root_node, file_path)

    def _walk_for_isinstance_refs(self, node: Any, file_path: str) -> None:
        """递归走读 AST，处理 isinstance/issubclass 调用节点。"""
        if node.type == "call":
            self._process_isinstance_call(node, file_path)

        for child in node.children:
            self._walk_for_isinstance_refs(child, file_path)

    def _process_isinstance_call(self, call_node: Any, file_path: str) -> None:
        """从 isinstance/issubclass 调用中提取类型参数引用。

        AST 结构：
          call
            function: identifier("isinstance")
            arguments: argument_list
              positional_argument: ...   (第一个参数：被检查对象)
              ,
              positional_argument: identifier/tuple (第二个参数：类型)
        """
        # 找到 function 子节点（被调函数名）
        func_name = None
        for child in call_node.children:
            if child.type in ("identifier", "attribute"):
                func_name = self._node_text(child)
                break

        if func_name not in self._TYPE_CHECK_BUILTINS:
            return

        # 找到 argument_list 子节点
        for child in call_node.children:
            if child.type == "argument_list":
                self._extract_type_args_from_argument_list(child, file_path)
                return

    def _extract_type_args_from_argument_list(
        self, arg_list_node: Any, file_path: str
    ) -> None:
        """从 argument_list 中提取第二个参数（类型参数）的类名引用。

        第二参数可以是：
        - 单个标识符：isinstance(x, SomeClass)
        - 元组：isinstance(x, (ClassA, ClassB))
        """
        # 收集实际参数（跳过逗号和括号）
        args = [
            c
            for c in arg_list_node.children
            if c.type not in (",", "(", ")", "comment")
            and c.type != "positional_separator"
        ]
        if len(args) < 2:
            return

        type_arg = args[1]  # 第二个参数是类型
        line = type_arg.start_point[0] + 1

        if type_arg.type == "identifier":
            # isinstance(x, SomeClass)
            name = self._node_text(type_arg)
            if name and not name.startswith("__"):
                self._symbol_index.add_reference(
                    SymbolReference(
                        symbol_name=name,
                        file_path=file_path,
                        line=line,
                        ref_type="type_check",
                    )
                )
        elif type_arg.type == "tuple":
            # isinstance(x, (ClassA, ClassB))
            for item in type_arg.children:
                if item.type == "identifier":
                    name = self._node_text(item)
                    if name and not name.startswith("__"):
                        self._symbol_index.add_reference(
                            SymbolReference(
                                symbol_name=name,
                                file_path=file_path,
                                line=item.start_point[0] + 1,
                                ref_type="type_check",
                            )
                        )

    def _extract_imports(
        self, root_node: Any, file_path: str, source_code: str
    ) -> None:
        """Extract import statements and build dependency edges + references."""
        self._walk_for_imports(root_node, file_path, source_code)

    def _walk_for_imports(
        self,
        node: Any,
        file_path: str,
        source_code: str,
        is_type_check_only: bool = False,
        is_inside_function: bool = False,
    ) -> None:
        """Recursively walk AST for import nodes.

        Args:
            node: Current AST node.
            file_path: Relative file path.
            source_code: Full source code.
            is_type_check_only: Whether we're inside an ``if TYPE_CHECKING:`` block.
            is_inside_function: Whether we're inside a function/method body（懒加载 import）.
        """
        if node.type == "import_statement":
            self._process_import_statement(
                node, file_path, is_type_check_only, is_inside_function
            )
        elif node.type == "import_from_statement":
            self._process_import_from_statement(
                node, file_path, is_type_check_only, is_inside_function
            )
        elif node.type == "if_statement":
            # Detect `if TYPE_CHECKING:` blocks
            in_type_checking = self._is_type_checking_guard(node)
            for child in node.children:
                self._walk_for_imports(
                    child,
                    file_path,
                    source_code,
                    is_type_check_only=in_type_checking or is_type_check_only,
                    is_inside_function=is_inside_function,
                )
            return
        elif node.type in ("function_definition", "async_function_definition"):
            # 进入函数/方法体，后续的 import 都是懒加载
            for child in node.children:
                self._walk_for_imports(
                    child,
                    file_path,
                    source_code,
                    is_type_check_only=is_type_check_only,
                    is_inside_function=True,
                )
            return

        for child in node.children:
            self._walk_for_imports(
                child, file_path, source_code, is_type_check_only, is_inside_function
            )

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
        self,
        node: Any,
        file_path: str,
        is_type_check_only: bool = False,
        is_lazy_import: bool = False,
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
                    is_lazy_import=is_lazy_import,
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
                            is_lazy_import=is_lazy_import,
                        )
                        break

    def _process_import_from_statement(
        self,
        node: Any,
        file_path: str,
        is_type_check_only: bool = False,
        is_lazy_import: bool = False,
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
                is_lazy_import=is_lazy_import,
            )

    def _add_import_edge(
        self,
        file_path: str,
        module_name: str,
        imported_names: list[str],
        line: int,
        is_relative: bool,
        is_type_check_only: bool = False,
        is_lazy_import: bool = False,
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
                is_lazy_import=is_lazy_import,
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
                is_lazy_import=is_lazy_import,
            )
            self._dep_graph.add_edge(edge)

    @staticmethod
    def _node_text(node: Any) -> str:
        """Get text from a tree-sitter node."""
        text = getattr(node, "text", b"")
        if isinstance(text, bytes):
            return text.decode("utf-8")
        return str(text)

    # reset() was removed in v3 (dead code — MCP server sets _indexer=None instead).
