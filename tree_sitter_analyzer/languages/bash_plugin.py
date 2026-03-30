#!/usr/bin/env python3
"""
Bash Language Plugin

Bash/Shell script-specific parsing and element extraction functionality.
Provides support for Bash shell script features including functions,
variable assignments, control flow structures, and command pipelines.
"""

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Optional

import anyio

if TYPE_CHECKING:
    import tree_sitter

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ..core.analysis_engine import AnalysisRequest
from ..encoding_utils import extract_text_slice, safe_encode
from ..models import AnalysisResult, CodeElement, Function
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error


class BashElementExtractor(ElementExtractor):
    """Bash-specific element extractor for shell scripts"""

    def __init__(self) -> None:
        """Initialize the Bash element extractor."""
        self.source_code: str = ""
        self.content_lines: list[str] = []

        # Performance optimization caches
        self._node_text_cache: dict[tuple[int, int], str] = {}
        self._processed_nodes: set[int] = set()
        self._file_encoding: str | None = None

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract Bash function definitions"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        functions: list[Function] = []

        # Extract function_definition nodes
        extractors = {
            "function_definition": self._extract_function,
        }

        if tree is not None and tree.root_node is not None:
            try:
                self._traverse_and_extract_iterative(
                    tree.root_node, extractors, functions, "function"
                )
                log_debug(f"Extracted {len(functions)} Bash functions")
            except Exception as e:
                log_debug(f"Error during function extraction: {e}")
                return []

        return functions

    def extract_classes(self, tree: "tree_sitter.Tree", source_code: str) -> list:
        """Bash does not have classes"""
        return []

    def extract_variables(self, tree: "tree_sitter.Tree", source_code: str) -> list:
        """Bash variable extraction not implemented in this phase"""
        return []

    def extract_imports(self, tree: "tree_sitter.Tree", source_code: str) -> list:
        """Bash does not have traditional imports (source statements are handled separately)"""
        return []

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()
        self._processed_nodes.clear()

    def _traverse_and_extract_iterative(
        self,
        root_node: Optional["tree_sitter.Node"],
        extractors: dict[str, Any],
        results: list[Any],
        element_type: str,
    ) -> None:
        """Iterative node traversal and extraction"""
        if not root_node:
            return

        target_node_types = set(extractors.keys())
        container_node_types = {
            "program",
            "function_definition",
            "compound_statement",
            "if_statement",
            "while_statement",
            "for_statement",
            "case_statement",
            "subshell",
            "command",
        }

        node_stack = [(root_node, 0)]
        processed_nodes = 0
        max_depth = 50

        while node_stack:
            current_node, depth = node_stack.pop()

            if depth > max_depth:
                log_debug(f"Maximum traversal depth ({max_depth}) exceeded")
                continue

            processed_nodes += 1
            node_type = current_node.type

            # Early termination for irrelevant nodes
            if (
                depth > 0
                and node_type not in target_node_types
                and node_type not in container_node_types
            ):
                continue

            # Process target nodes
            if node_type in target_node_types:
                node_id = id(current_node)

                if node_id in self._processed_nodes:
                    continue

                self._processed_nodes.add(node_id)

                # Extract element
                extractor = extractors.get(node_type)
                if extractor:
                    try:
                        element = extractor(current_node)
                        if element:
                            results.append(element)
                    except Exception:
                        # Skip nodes that cause extraction errors
                        pass

            # Add children to stack
            if current_node.children:
                try:
                    children_list = list(current_node.children)
                    children_iter: Iterator[tree_sitter.Node] = reversed(children_list)
                except TypeError:
                    # Fallback for Mock objects or other non-reversible types
                    children_list = list(current_node.children)
                    children_iter = iter(children_list)

                for child in children_iter:
                    node_stack.append((child, depth + 1))

        log_debug(f"Iterative traversal processed {processed_nodes} nodes")

    def _get_node_text_optimized(self, node: "tree_sitter.Node") -> str:
        """Get node text with optimized caching"""
        cache_key = (node.start_byte, node.end_byte)

        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]

        try:
            start_byte = node.start_byte
            end_byte = node.end_byte

            encoding = self._file_encoding or "utf-8"
            content_bytes = safe_encode("\n".join(self.content_lines), encoding)
            text = extract_text_slice(content_bytes, start_byte, end_byte, encoding)

            if text:
                self._node_text_cache[cache_key] = text
                return text
        except Exception as e:
            log_error(f"Error in _get_node_text_optimized: {e}")

        # Fallback to simple text extraction
        try:
            start_point = node.start_point
            end_point = node.end_point

            if start_point[0] < 0 or start_point[0] >= len(self.content_lines):
                return ""

            if end_point[0] < 0 or end_point[0] >= len(self.content_lines):
                return ""

            if start_point[0] == end_point[0]:
                line = self.content_lines[start_point[0]]
                start_col = max(0, min(start_point[1], len(line)))
                end_col = max(start_col, min(end_point[1], len(line)))
                result: str = line[start_col:end_col]
                self._node_text_cache[cache_key] = result
                return result
            else:
                lines = []
                for i in range(start_point[0], end_point[0] + 1):
                    if i < len(self.content_lines):
                        line = self.content_lines[i]
                        if i == start_point[0]:
                            start_col = max(0, min(start_point[1], len(line)))
                            lines.append(line[start_col:])
                        elif i == end_point[0]:
                            end_col = max(0, min(end_point[1], len(line)))
                            lines.append(line[:end_col])
                        else:
                            lines.append(line)
                result = "\n".join(lines)
                self._node_text_cache[cache_key] = result
                return result
        except Exception as fallback_error:
            log_error(f"Fallback text extraction also failed: {fallback_error}")
            return ""

    def _extract_function(self, node: "tree_sitter.Node") -> Function | None:
        """Extract Bash function information"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract function name
            name = self._extract_function_name(node)
            if not name:
                return None

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="bash",
                parameters=[],  # Bash functions don't have formal parameters in signature
                return_type="",  # Bash functions don't have type annotations
            )
        except Exception as e:
            log_error(f"Failed to extract Bash function info: {e}")
            return None

    def _extract_function_name(self, node: "tree_sitter.Node") -> str | None:
        """Extract function name from function_definition node"""
        try:
            # In tree-sitter-bash, function_definition has a "name" field
            for child in node.children:
                if child.type == "word":
                    # The first "word" child is typically the function name
                    return child.text.decode("utf8") if child.text else None
        except Exception:
            return None
        return None


class BashPlugin(LanguagePlugin):
    """Bash language plugin"""

    def __init__(self) -> None:
        """Initialize the Bash plugin"""
        super().__init__()
        self._language_cache: tree_sitter.Language | None = None
        self._extractor: BashElementExtractor | None = None

        # Legacy compatibility attributes
        self.language = "bash"
        self.extractor = self.get_extractor()

    def get_language_name(self) -> str:
        """Return the name of the programming language this plugin supports"""
        return "bash"

    def get_file_extensions(self) -> list[str]:
        """Return list of file extensions this plugin supports"""
        return [".sh", ".bash", ".zsh"]

    def create_extractor(self) -> ElementExtractor:
        """Create and return an element extractor for this language"""
        return BashElementExtractor()

    def get_extractor(self) -> ElementExtractor:
        """Get the cached extractor instance"""
        if self._extractor is None:
            self._extractor = BashElementExtractor()
        return self._extractor

    def get_language(self) -> str:
        """Get the language name (legacy compatibility)"""
        return "bash"

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract functions from the tree"""
        extractor = self.get_extractor()
        return extractor.extract_functions(tree, source_code)

    def extract_classes(self, tree: "tree_sitter.Tree", source_code: str) -> list:
        """Extract classes from the tree (Bash has no classes)"""
        return []

    def extract_variables(self, tree: "tree_sitter.Tree", source_code: str) -> list:
        """Extract variables from the tree"""
        return []

    def extract_imports(self, tree: "tree_sitter.Tree", source_code: str) -> list:
        """Extract imports from the tree"""
        return []

    def get_tree_sitter_language(self) -> Optional["tree_sitter.Language"]:
        """Get the Tree-sitter language object for Bash"""
        if self._language_cache is None:
            try:
                import tree_sitter
                import tree_sitter_bash

                language_capsule = tree_sitter_bash.language()
                self._language_cache = tree_sitter.Language(language_capsule)
            except ImportError:
                log_error("tree-sitter-bash not available")
                return None
            except Exception as e:
                log_error(f"Failed to load Bash language: {e}")
                return None
        return self._language_cache

    def get_supported_queries(self) -> list[str]:
        """Get list of supported query names for this language"""
        return [
            "function",
            "variable_assignment",
            "command",
            "pipeline",
            "if_statement",
            "while_statement",
            "for_statement",
            "case_statement",
        ]

    def is_applicable(self, file_path: str) -> bool:
        """Check if this plugin is applicable for the given file"""
        return any(
            file_path.lower().endswith(ext.lower())
            for ext in self.get_file_extensions()
        )

    def get_plugin_info(self) -> dict:
        """Get information about this plugin"""
        return {
            "name": "Bash Plugin",
            "language": self.get_language_name(),
            "extensions": self.get_file_extensions(),
            "version": "1.0.0",
            "supported_queries": self.get_supported_queries(),
            "features": [
                "Function definitions",
                "Variable assignments",
                "Control flow (if/while/for/case)",
                "Command extraction",
                "Pipeline detection",
            ],
        }

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """Analyze a Bash file and return the analysis results"""
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
                error_message="Could not load Bash language for parsing.",
            )

        try:
            from ..encoding_utils import read_file_safe_async

            # Non-blocking I/O
            source_code, _ = await read_file_safe_async(file_path)

            # Offload CPU-bound parsing to worker thread
            def _analyze_sync() -> tuple[list[CodeElement], int]:
                parser = tree_sitter.Parser()
                parser.language = language
                tree = parser.parse(bytes(source_code, "utf8"))

                extractor = self.create_extractor()

                elements: list[CodeElement] = []
                elements.extend(extractor.extract_functions(tree, source_code))

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
            log_error(f"Error analyzing Bash file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=False,
                error_message=str(e),
            )
