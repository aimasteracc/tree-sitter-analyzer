#!/usr/bin/env python3
"""
Bash Language Plugin

Bash/Shell script-specific parsing and element extraction functionality.
Provides support for Bash shell script features including functions,
variable assignments, control flow structures, and command pipelines.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import anyio

if TYPE_CHECKING:
    import tree_sitter

    from ..core.request import AnalysisRequest
    from ..models import AnalysisResult

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ..encoding_utils import extract_text_slice, safe_encode
from ..models import AnalysisResult, CodeElement, Expression, Function, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error
from .shared.traversal import node_range

# Import at runtime for analyze_file method
try:
    from ..core.request import AnalysisRequest as _AnalysisRequest
except ImportError:
    _AnalysisRequest = None  # type: ignore[misc, assignment]


# Container node types in the Bash AST. A node of one of these types may
# enclose target nodes deeper in the tree, so the traversal descends into
# them even when the type itself isn't an extraction target. Listed as a
# module-level frozenset so the iterative traversal doesn't re-create the
# set on every call (r37f1 dogfood).
_BASH_CONTAINER_NODE_TYPES: frozenset[str] = frozenset(
    {
        "program",
        "function_definition",
        "compound_statement",
        "if_statement",
        "while_statement",
        "for_statement",
        "c_style_for_statement",
        "case_statement",
        "case_item",
        "elif_clause",
        "do_group",
        "subshell",
        "command",
        "list",
        "redirected_statement",
        "pipeline",
        "declaration_command",
        "variable_assignment",
        "array",
        "test_command",
        "heredoc_redirect",
        "heredoc_body",
        "simple_expansion",
        "expansion",
        "command_substitution",
        "string",
        "binary_expression",
        "unary_expression",
        "subscript",
    }
)


# ---------------------------------------------------------------------------
# Cyclomatic complexity for Bash
# ---------------------------------------------------------------------------

_BASH_DECISION_TYPES: frozenset[str] = frozenset(
    {
        "if_statement",
        "elif_clause",
        "while_statement",  # covers both 'while' and 'until' loops
        "for_statement",
        "c_style_for_statement",
        # The ``case`` construct counts once via ``case_statement``; the
        # individual ``case_item`` arms are NOT counted (construct-once),
        # matching every other plugin. See #1090 (C/C++ switch counts once).
        "case_statement",
    }
)

_BASH_LOGIC_OP_TOKENS: frozenset[str] = frozenset({"&&", "||"})


def _safe_children_bash(node: Any) -> list[Any]:
    """Return children list from a tree-sitter node, empty list on any error."""
    try:
        children = getattr(node, "children", None)
        if children is None:
            return []
        return list(children)
    except (TypeError, AttributeError):
        return []


def calculate_bash_complexity(node: Any) -> int:
    """Return cyclomatic complexity for a Bash function node.

    complexity = 1 + decision_points.
    Decision points: if_statement, elif_clause, while_statement (covers
    both while and until), for_statement, c_style_for_statement, case_item
    (non-leaf nodes), and ``&&`` / ``||`` leaf operator tokens.
    """
    decisions = 0
    stack = [node]
    while stack:
        cur = stack.pop()
        children = _safe_children_bash(cur)
        is_leaf = len(children) == 0
        node_type = getattr(cur, "type", None)
        if not is_leaf and node_type in _BASH_DECISION_TYPES:
            decisions += 1
        elif is_leaf and node_type in _BASH_LOGIC_OP_TOKENS:
            decisions += 1
        stack.extend(children)
    return 1 + decisions


def _push_bash_children(
    node_stack: list[tuple[tree_sitter.Node, int]],
    current_node: tree_sitter.Node,
    depth: int,
) -> None:
    """Append ``current_node.children`` to ``node_stack`` in reversed order.

    Uses ``reversed()`` for the natural iterative-DFS order (so the first
    child gets popped first); falls back to forward iteration when
    ``children`` isn't reversible (Mock objects in tests).

    r37f1 (dogfood): lifted from ``_traverse_and_extract_iterative`` so
    the parent body stays linear.
    """
    if not current_node.children:
        return
    try:
        children_list = list(current_node.children)
        children_iter: Iterator[tree_sitter.Node] = reversed(children_list)
    except TypeError:
        # Fallback for Mock objects or other non-reversible types
        children_list = list(current_node.children)
        children_iter = iter(children_list)

    for child in children_iter:
        node_stack.append((child, depth + 1))


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
        self, tree: tree_sitter.Tree, source_code: str
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

    # Build the expression extractor dict once from the kind maps + singletons.
    # Using dict.fromkeys(keys, value) groups all types that share a handler.
    _EXPRESSION_EXTRACTORS: dict[str, str] = {}  # populated in __init_subclass__ below

    @classmethod
    def _build_expression_extractors(cls) -> dict[str, Any]:
        """Return {node_type: extractor_method_name} — built lazily and cached."""
        return {
            **dict.fromkeys(cls._CONTROL_FLOW_KIND, "_extract_control_flow"),
            "subshell": "_extract_subshell",
            "array": "_extract_array",
            "subscript": "_extract_subscript",
            "list": "_extract_list",
            **dict.fromkeys(cls._REDIRECT_KIND, "_extract_redirect"),
            "process_substitution": "_extract_process_substitution",
            "comment": "_extract_comment",
            **dict.fromkeys(cls._STRING_PATTERN_KIND, "_extract_string_pattern"),
        }

    def extract_expressions(
        self, tree: tree_sitter.Tree | None, source_code: str
    ) -> list[Expression]:
        """Extract Bash expressions (control flow, arrays, redirects, etc.)"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()
        expressions: list[Expression] = []
        if tree is None or tree.root_node is None:
            return expressions
        # Resolve method names to bound methods at call time.
        method_map = {
            nt: getattr(self, mn)
            for nt, mn in self._build_expression_extractors().items()
        }
        try:
            self._traverse_and_extract_iterative(
                tree.root_node, method_map, expressions, "expression"
            )
            log_debug(f"Extracted {len(expressions)} Bash expressions")
        except Exception as e:
            log_debug(f"Error during expression extraction: {e}")
            return []
        return expressions

    def extract_classes(self, tree: tree_sitter.Tree, source_code: str) -> list[Any]:
        """Bash does not have classes"""
        return []

    def extract_variables(self, tree: tree_sitter.Tree, source_code: str) -> list[Any]:
        """Extract Bash variable assignments.

        Bug #776: this method was a no-op stub, so variables were never
        returned from the pipeline.  We now walk the AST and collect
        ``variable_assignment`` nodes, extracting the variable name from the
        ``variable_name`` child and the raw text as the initializer.

        Nodes inside ``declaration_command`` (``declare``, ``export``,
        ``readonly``, ``local``) are also included — they wrap
        ``variable_assignment`` children that the top-level traversal reaches
        automatically.
        """
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        variables: list[Variable] = []

        try:
            extractors = {
                "variable_assignment": self._extract_variable,
            }
            self._traverse_and_extract_iterative(
                tree.root_node, extractors, variables, "variable"
            )
            log_debug(f"Extracted {len(variables)} Bash variables")
        except Exception as e:
            log_debug(f"Error during variable extraction: {e}")
            return []

        return variables

    def _extract_variable(self, node: tree_sitter.Node) -> Variable | None:
        """Extract a Bash variable from a ``variable_assignment`` node."""
        try:
            start_line, end_line = node_range(node)
            raw_text = self._get_node_text_optimized(node)

            # The first child of variable_assignment is variable_name.
            name: str | None = None
            for child in node.children:
                if child.type == "variable_name":
                    name = child.text.decode("utf-8") if child.text else None
                    break

            if not name:
                return None

            return Variable(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="bash",
                initializer=raw_text,
            )
        except Exception as e:
            log_error(f"Failed to extract Bash variable: {e}")
            return None

    def extract_imports(self, tree: tree_sitter.Tree, source_code: str) -> list[Any]:
        """Bash does not have traditional imports (source statements are handled separately)"""
        return []

    def extract_elements(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> dict[str, list[Any]]:
        """Unified extraction entry point grouped by type."""
        return {
            "functions": self.extract_functions(tree, source_code),
            "classes": self.extract_classes(tree, source_code),
            "imports": self.extract_imports(tree, source_code),
            "variables": self.extract_variables(tree, source_code),
        }

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()
        self._processed_nodes.clear()

    def _traverse_and_extract_iterative(
        self,
        root_node: tree_sitter.Node | None,
        extractors: dict[str, Any],
        results: list[Any],
        element_type: str,
    ) -> None:
        """Iterative node traversal and extraction.

        r37f1 (dogfood): 87→~25 lines. The container-node frozenset moved
        to module-level ``_BASH_CONTAINER_NODE_TYPES`` (was reconstructed
        on every call); the child-stacking child-iter compat shim moved to
        ``_push_bash_children``.
        """
        if not root_node:
            return

        target_node_types = set(extractors.keys())
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

            # Early termination for irrelevant nodes.
            if (
                depth > 0
                and node_type not in target_node_types
                and node_type not in _BASH_CONTAINER_NODE_TYPES
            ):
                continue

            # Process target nodes.
            if node_type in target_node_types:
                # r37cd (dogfood): extracted to flatten 7-deep nesting.
                self._try_extract_bash_node(
                    current_node, node_type, extractors, results
                )

            _push_bash_children(node_stack, current_node, depth)

        log_debug(f"Iterative traversal processed {processed_nodes} nodes")

    def _extract_multiline_text(
        self,
        start_point: tuple[int, int],
        end_point: tuple[int, int],
    ) -> str:
        """Slice multi-line node text from ``self.content_lines``.

        r37ce (dogfood): extracted from ``_get_node_text_optimized``'s
        fallback branch to drop nesting from 8 to ≤3. Handles the
        first-line / last-line / interior-line columns.
        """
        lines: list[str] = []
        for i in range(start_point[0], end_point[0] + 1):
            if i >= len(self.content_lines):
                continue
            line = self.content_lines[i]
            line_len = len(line)
            if i == start_point[0]:
                start_col = max(0, min(start_point[1], line_len))
                lines.append(line[start_col:])
            elif i == end_point[0]:
                end_col = max(0, min(end_point[1], line_len))
                lines.append(line[:end_col])
            else:
                lines.append(line)
        return "\n".join(lines)

    def _try_extract_bash_node(
        self,
        current_node: tree_sitter.Node,
        node_type: str,
        extractors: dict[str, Any],
        results: list[Any],
    ) -> None:
        """Look up the extractor for a node type and append its result.

        r37cd (dogfood): extracted from the stack-traversal loop in
        ``_extract_elements_iterative`` to drop nesting from 7 to ≤3.
        Skips already-processed nodes (by id) and swallows per-extractor
        errors so a single bad node doesn't abort the walk.
        """
        node_id = id(current_node)
        if node_id in self._processed_nodes:
            return
        self._processed_nodes.add(node_id)
        extractor = extractors.get(node_type)
        if not extractor:
            return
        try:
            element = extractor(current_node)
        except Exception:
            return
        if element:
            results.append(element)

    def _get_node_text_optimized(self, node: tree_sitter.Node) -> str:
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
            # r37ce (dogfood): extracted to drop nesting from 8 to ≤3.
            result = self._extract_multiline_text(start_point, end_point)
            self._node_text_cache[cache_key] = result
            return result
        except Exception as fallback_error:
            log_error(f"Fallback text extraction also failed: {fallback_error}")
            return ""

    def _extract_function(self, node: tree_sitter.Node) -> Function | None:
        """Extract Bash function information"""
        try:
            start_line, end_line = node_range(node)

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
                complexity_score=calculate_bash_complexity(node),
            )
        except Exception as e:
            log_error(f"Failed to extract Bash function info: {e}")
            return None

    def _extract_function_name(self, node: tree_sitter.Node) -> str | None:
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

    # -----------------------------------------------------------------------
    # Node-type → expression-kind lookup tables for _make_expression
    # -----------------------------------------------------------------------
    _CONTROL_FLOW_KIND: dict[str, str] = {
        "while_statement": "while_loop",
        "for_statement": "for_loop",
        "c_style_for_statement": "c_style_for_loop",
        "case_statement": "case_statement",
        "case_item": "case_item",
        "elif_clause": "elif_clause",
        "do_group": "do_group",
    }
    _REDIRECT_KIND: dict[str, str] = {
        "file_redirect": "file_redirect",
        "herestring_redirect": "herestring_redirect",
        "heredoc_content": "heredoc_content",
        "file_descriptor": "file_descriptor",
    }
    _STRING_PATTERN_KIND: dict[str, str] = {
        "raw_string": "raw_string",
        "regex": "regex",
        "brace_expression": "brace_expression",
        "extglob_pattern": "extglob_pattern",
        "special_variable_name": "special_variable_name",
        "postfix_expression": "postfix_expression",
    }

    def _make_expression(
        self, node: tree_sitter.Node, kind: str, name: str | None = None
    ) -> Expression:
        """Build an Expression element for *node* with the given *kind*.

        ``name`` defaults to *kind* when not provided.
        """
        start_line, end_line = node_range(node)
        raw_text = self._get_node_text_optimized(node)
        preview = raw_text[:50].replace("\n", " ") if raw_text else ""
        return Expression(
            name=name if name is not None else kind,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="bash",
            expression_kind=kind,
            preview=preview,
        )

    def _extract_control_flow(self, node: tree_sitter.Node) -> Expression | None:
        """Extract control flow statements (while, for, case, if branches)."""
        try:
            kind = self._CONTROL_FLOW_KIND.get(node.type, node.type)
            return self._make_expression(node, kind)
        except Exception as e:
            log_error(f"Failed to extract control flow: {e}")
            return None

    def _extract_subshell(self, node: tree_sitter.Node) -> Expression | None:
        """Extract subshell expressions."""
        try:
            return self._make_expression(node, "subshell")
        except Exception as e:
            log_error(f"Failed to extract subshell: {e}")
            return None

    def _extract_array(self, node: tree_sitter.Node) -> Expression | None:
        """Extract array expressions."""
        try:
            return self._make_expression(node, "array")
        except Exception as e:
            log_error(f"Failed to extract array: {e}")
            return None

    def _extract_subscript(self, node: tree_sitter.Node) -> Expression | None:
        """Extract subscript/array indexing expressions.

        For an assignment target (``arr[0]=x``) unwraps to the base name.
        A subscript read keeps the ``subscript`` label (#949 Codex P2).
        """
        try:
            parent = node.parent
            name_field = (
                parent.child_by_field_name("name")
                if parent is not None and parent.type == "variable_assignment"
                else None
            )
            is_assignment_target = name_field is not None and name_field.id == node.id
            base = None
            if is_assignment_target:
                base = node.child_by_field_name("name")
                if base is None:
                    for child in node.children:
                        if child.type in ("variable_name", "word"):
                            base = child
                            break
            name = self._get_node_text_optimized(base) if base is not None else ""
            return self._make_expression(node, "subscript", name or "subscript")
        except Exception as e:
            log_error(f"Failed to extract subscript: {e}")
            return None

    def _extract_list(self, node: tree_sitter.Node) -> Expression | None:
        """Extract list expressions (command lists with && or ||)."""
        try:
            return self._make_expression(node, "list")
        except Exception as e:
            log_error(f"Failed to extract list: {e}")
            return None

    def _extract_redirect(self, node: tree_sitter.Node) -> Expression | None:
        """Extract redirection expressions."""
        try:
            kind = self._REDIRECT_KIND.get(node.type, node.type)
            return self._make_expression(node, kind)
        except Exception as e:
            log_error(f"Failed to extract redirect: {e}")
            return None

    def _extract_process_substitution(
        self, node: tree_sitter.Node
    ) -> Expression | None:
        """Extract process substitution expressions."""
        try:
            return self._make_expression(node, "process_substitution")
        except Exception as e:
            log_error(f"Failed to extract process substitution: {e}")
            return None

    def _extract_comment(self, node: tree_sitter.Node) -> Expression | None:
        """Extract comment nodes, skipping shebang lines (#!).

        Bug #777: ``#!/usr/bin/env bash`` is a ``comment`` node in the grammar.
        Shebang lines are interpreter metadata, not symbolic comments.
        """
        try:
            raw_text = self._get_node_text_optimized(node)
            if raw_text.startswith("#!"):
                return None
            return self._make_expression(node, "comment")
        except Exception as e:
            log_error(f"Failed to extract comment: {e}")
            return None

    def _extract_string_pattern(self, node: tree_sitter.Node) -> Expression | None:
        """Extract string and pattern expressions."""
        try:
            kind = self._STRING_PATTERN_KIND.get(node.type, node.type)
            return self._make_expression(node, kind)
        except Exception as e:
            log_error(f"Failed to extract string/pattern: {e}")
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

    def extract_elements(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> dict[str, list[Any]]:
        """Unified extraction entry point — delegates to the extractor."""
        return self.get_extractor().extract_elements(tree, source_code)

    def get_tree_sitter_language(self) -> tree_sitter.Language | None:
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

                all_elements: list[CodeElement] = []
                all_elements.extend(extractor.extract_functions(tree, source_code))
                all_elements.extend(extractor.extract_expressions(tree, source_code))
                # Bug #776: wire variables into the async pipeline as well.
                all_elements.extend(extractor.extract_variables(tree, source_code))

                from ..utils.tree_sitter_compat import count_nodes_iterative

                node_count = 0
                if tree and tree.root_node:
                    node_count = count_nodes_iterative(tree.root_node)

                return all_elements, node_count

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
