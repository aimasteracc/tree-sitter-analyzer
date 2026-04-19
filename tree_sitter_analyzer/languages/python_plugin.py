#!/usr/bin/env python3
"""
Python Language Plugin

Thin plugin wrapper for Python analysis.
Core extraction logic lives in python_extractor.py.
"""

from typing import TYPE_CHECKING, Any, Optional

import anyio

if TYPE_CHECKING:
    import tree_sitter

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ..core.request import AnalysisRequest
from ..models import (
    AnalysisResult,
    Class,
    CodeElement,
    Function,
    Import,
    Variable,
)
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_error
from ..utils.tree_sitter_compat import TreeSitterQueryCompat
from .python_extractor import PythonElementExtractor


class PythonPlugin(LanguagePlugin):
    """Python language plugin for the new architecture"""

    def __init__(self) -> None:
        """Initialize the Python plugin"""
        super().__init__()
        self._language_cache: tree_sitter.Language | None = None
        self._extractor: PythonElementExtractor | None = None
        self._knowledge: PythonKnowledge | None = None

        # Legacy compatibility attributes for tests
        self.language = "python"
        self.extractor = self.get_extractor()

    def get_language_name(self) -> str:
        """Return the name of the programming language this plugin supports"""
        return "python"

    def get_file_extensions(self) -> list[str]:
        """Return list of file extensions this plugin supports"""
        return [".py", ".pyw", ".pyi"]

    def create_extractor(self) -> ElementExtractor:
        """Create and return an element extractor for this language"""
        return PythonElementExtractor()

    def get_extractor(self) -> ElementExtractor:
        """Get the cached extractor instance, creating it if necessary"""
        if self._extractor is None:
            self._extractor = PythonElementExtractor()
        return self._extractor

    @property
    def knowledge(self) -> "PythonKnowledge":
        if self._knowledge is None:
            self._knowledge = PythonKnowledge()
        return self._knowledge

    def get_language(self) -> str:
        """Get the language name for Python (legacy compatibility)"""
        return "python"

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract functions from the tree (legacy compatibility)"""
        extractor = self.get_extractor()
        return extractor.extract_functions(tree, source_code)

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """Extract classes from the tree (legacy compatibility)"""
        extractor = self.get_extractor()
        return extractor.extract_classes(tree, source_code)

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract variables from the tree (legacy compatibility)"""
        extractor = self.get_extractor()
        return extractor.extract_variables(tree, source_code)

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract imports from the tree (legacy compatibility)"""
        extractor = self.get_extractor()
        return extractor.extract_imports(tree, source_code)

    def get_tree_sitter_language(self) -> Optional["tree_sitter.Language"]:
        """Get the Tree-sitter language object for Python"""
        if self._language_cache is None:
            try:
                import tree_sitter
                import tree_sitter_python as tspython

                # PyCapsuleオブジェクトをLanguageオブジェクトに変換
                language_capsule = tspython.language()
                self._language_cache = tree_sitter.Language(language_capsule)
            except ImportError:
                log_error("tree-sitter-python not available")
                return None
            except Exception as e:
                log_error(f"Failed to load Python language: {e}")
                return None
        return self._language_cache

    def get_supported_queries(self) -> list[str]:
        """Get list of supported query names for this language"""
        return [
            "function",
            "class",
            "variable",
            "import",
            "async_function",
            "method",
            "decorator",
            "exception",
            "comprehension",
            "lambda",
            "context_manager",
            "type_hint",
            "docstring",
            "django_model",
            "flask_route",
            "fastapi_endpoint",
        ]

    def is_applicable(self, file_path: str) -> bool:
        """Check if this plugin is applicable for the given file"""
        return any(
            file_path.lower().endswith(ext.lower())
            for ext in self.get_file_extensions()
        )

    def get_plugin_info(self) -> dict[str, Any]:
        """Get information about this plugin"""
        return {
            "name": "Python Plugin",
            "language": self.get_language_name(),
            "extensions": self.get_file_extensions(),
            "version": "2.0.0",
            "supported_queries": self.get_supported_queries(),
            "features": [
                "Async/await functions",
                "Type hints support",
                "Decorators",
                "Context managers",
                "Comprehensions",
                "Lambda expressions",
                "Exception handling",
                "Docstring extraction",
                "Django framework support",
                "Flask framework support",
                "FastAPI framework support",
                "Dataclass support",
                "Abstract class detection",
                "Complexity analysis",
            ],
        }

    def execute_query_strategy(
        self, query_key: str | None, language: str
    ) -> str | None:
        """Execute query strategy for Python language"""
        queries = self.get_queries()
        return queries.get(query_key) if query_key else None

    def _get_node_type_for_element(self, element: Any) -> str:
        """Get appropriate node type for element"""
        from ..models import Class, Function, Import, Variable

        if isinstance(element, Function):
            return "function_definition"
        elif isinstance(element, Class):
            return "class_definition"
        elif isinstance(element, Variable):
            return "assignment"
        elif isinstance(element, Import):
            return "import_statement"
        else:
            return "unknown"

    def get_element_categories(self) -> dict[str, list[str]]:
        """
        Get element categories mapping query keys to node types

        Returns:
            Dictionary mapping query keys to lists of node types
        """
        return {
            # Function-related queries
            "function": ["function_definition"],
            "functions": ["function_definition"],
            "async_function": ["function_definition"],
            "async_functions": ["function_definition"],
            "method": ["function_definition"],
            "methods": ["function_definition"],
            "lambda": ["lambda"],
            "lambdas": ["lambda"],
            # Class-related queries
            "class": ["class_definition"],
            "classes": ["class_definition"],
            # Import-related queries
            "import": ["import_statement", "import_from_statement"],
            "imports": ["import_statement", "import_from_statement"],
            "from_import": ["import_from_statement"],
            "from_imports": ["import_from_statement"],
            # Variable-related queries
            "variable": ["assignment"],
            "variables": ["assignment"],
            # Decorator-related queries
            "decorator": ["decorator"],
            "decorators": ["decorator"],
            # Exception-related queries
            "exception": ["raise_statement", "except_clause"],
            "exceptions": ["raise_statement", "except_clause"],
            # Comprehension-related queries
            "comprehension": [
                "list_comprehension",
                "set_comprehension",
                "dictionary_comprehension",
                "generator_expression",
            ],
            "comprehensions": [
                "list_comprehension",
                "set_comprehension",
                "dictionary_comprehension",
                "generator_expression",
            ],
            # Context manager queries
            "context_manager": ["with_statement"],
            "context_managers": ["with_statement"],
            # Type hint queries
            "type_hint": ["type"],
            "type_hints": ["type"],
            # Docstring queries
            "docstring": ["string"],
            "docstrings": ["string"],
            # Framework-specific queries
            "django_model": ["class_definition"],
            "django_models": ["class_definition"],
            "flask_route": ["decorator"],
            "flask_routes": ["decorator"],
            "fastapi_endpoint": ["function_definition"],
            "fastapi_endpoints": ["function_definition"],
            # Generic queries
            "all_elements": [
                "function_definition",
                "class_definition",
                "import_statement",
                "import_from_statement",
                "assignment",
                "decorator",
                "raise_statement",
                "except_clause",
                "list_comprehension",
                "set_comprehension",
                "dictionary_comprehension",
                "generator_expression",
                "with_statement",
                "type",
                "string",
                "lambda",
            ],
        }

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """Analyze a Python file and return the analysis results."""
        if not TREE_SITTER_AVAILABLE:
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=False,
                error_message="Tree-sitter library not available.",
            )

        language = self.get_tree_sitter_language()
        if not language:
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=False,
                error_message="Could not load Python language for parsing.",
            )

        try:
            from ..encoding_utils import read_file_safe_async

            # 1. Non-blocking I/O
            source_code, _ = await read_file_safe_async(file_path)

            # 2. Offload CPU-bound parsing and extraction to worker threads
            def _analyze_sync() -> tuple[list[CodeElement], int]:
                parser = tree_sitter.Parser()
                parser.language = language
                tree = parser.parse(bytes(source_code, "utf8"))

                extractor = self.create_extractor()
                extractor.current_file = file_path  # Set current file for context

                elements: list[CodeElement] = []

                # Extract all element types
                elements.extend(extractor.extract_functions(tree, source_code))
                elements.extend(extractor.extract_classes(tree, source_code))
                elements.extend(extractor.extract_variables(tree, source_code))
                elements.extend(extractor.extract_imports(tree, source_code))

                # Extract comprehensions and expressions (for grammar coverage)
                elements.extend(extractor.extract_comprehensions(tree, source_code))  # type: ignore[attr-defined]
                elements.extend(extractor.extract_expressions(tree, source_code))

                from ..utils.tree_sitter_compat import count_nodes_iterative

                node_count = 0
                if tree and tree.root_node:
                    node_count = count_nodes_iterative(tree.root_node)

                return elements, node_count

            elements, node_count = await anyio.to_thread.run_sync(_analyze_sync)

            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=True,
                elements=elements,
                line_count=len(source_code.splitlines()),
                node_count=node_count,
            )
        except Exception as e:
            log_error(f"Error analyzing Python file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=False,
                error_message=str(e),
            )

    def execute_query(
        self, tree: "tree_sitter.Tree", query_name: str
    ) -> dict[str, Any]:
        """Execute a specific query on the tree"""
        try:
            language = self.get_tree_sitter_language()
            if not language:
                return {"error": "Language not available"}

            # Simple query execution for testing
            if query_name == "function":
                query_string = "(function_definition) @function"
            elif query_name == "class":
                query_string = "(class_definition) @class"
            else:
                return {"error": f"Unknown query: {query_name}"}

            captures = TreeSitterQueryCompat.safe_execute_query(
                language, query_string, tree.root_node, fallback_result=[]
            )
            return {"captures": captures, "query": query_string}

        except Exception as e:
            log_error(f"Query execution failed: {e}")
            return {"error": str(e)}

    def extract_elements(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[CodeElement]:
        """Extract elements from source code using tree-sitter AST"""
        extractor = self.get_extractor()
        elements: list[CodeElement] = []

        try:
            elements.extend(extractor.extract_functions(tree, source_code))
            elements.extend(extractor.extract_classes(tree, source_code))
            elements.extend(extractor.extract_variables(tree, source_code))
            elements.extend(extractor.extract_imports(tree, source_code))
        except Exception as e:
            log_error(f"Failed to extract elements: {e}")

        return elements


class PythonKnowledge:
    """AST knowledge for Python."""

    @property
    def function_nodes(self) -> frozenset[str]:
        return frozenset({"function_definition", "async_function_definition"})

    @property
    def class_nodes(self) -> frozenset[str]:
        return frozenset({"class_definition"})

    @property
    def scope_boundary_nodes(self) -> frozenset[str]:
        return frozenset({"function_definition", "class_definition", "lambda"})

    @property
    def import_nodes(self) -> frozenset[str]:
        return frozenset({"import_statement", "import_from_statement"})

    @property
    def loop_nodes(self) -> frozenset[str]:
        return frozenset({"for_statement", "while_statement", "for_in_clause"})

    @property
    def exception_nodes(self) -> frozenset[str]:
        return frozenset({"try_statement", "except_clause", "finally_clause", "raise_statement"})

    @property
    def assignment_nodes(self) -> frozenset[str]:
        return frozenset({"assignment", "variable_declarator"})

    @property
    def nesting_nodes(self) -> frozenset[str]:
        return frozenset({"if_statement", "for_statement", "while_statement", "with_statement", "try_statement", "match_statement"})

    @property
    def block_nodes(self) -> frozenset[str]:
        return frozenset({"block"})

    @property
    def parameter_nodes(self) -> frozenset[str]:
        return frozenset({"parameters", "default_parameter", "typed_parameter", "typed_default_parameter"})

    @property
    def raise_nodes(self) -> frozenset[str]:
        return frozenset({"raise_statement"})

    @property
    def boolean_operator_nodes(self) -> frozenset[str]:
        return frozenset({"boolean_operator"})

    @property
    def naming_conventions(self) -> dict[str, str]:
        return {
            "function": "snake_case", "method": "snake_case",
            "variable": "snake_case", "parameter": "snake_case",
            "class": "PascalCase", "constant": "UPPER_SNAKE",
        }
