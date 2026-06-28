#!/usr/bin/env python3
"""
Ruby Language Plugin

Provides Ruby-specific parsing and element extraction functionality.
Supports extraction of classes, modules, methods, constants, variables, and require statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ..models import Class, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_error
from ..utils.tree_sitter_compat import get_node_text_safe
from .shared.traversal import node_range
from .ruby_helpers import (
    extract_attr_methods as _extract_attrs_standalone,
)
from .ruby_helpers import (
    extract_require_statement as _extract_require_standalone,
)

# Non-leaf statement types that each add one cyclomatic complexity decision point.
# (case/when are handled specially in _ruby_calculate_complexity — see inline comments.)
_RUBY_DECISION_STATEMENT_TYPES: frozenset[str] = frozenset({
    "if", "elsif", "unless", "while", "until",
    "rescue", "for",
    "conditional",    # ternary  x > 0 ? a : b
    "if_modifier",    # expr if cond
    "unless_modifier", "while_modifier", "until_modifier",
})

# Leaf operator tokens that are themselves a decision branch.
_RUBY_LOGIC_OP_TOKENS: frozenset[str] = frozenset({"&&", "||"})


def _safe_children(node: object) -> list[object]:
    """Return children list from a tree-sitter node, empty list on any error."""
    try:
        children = getattr(node, "children", None)
        if children is None:
            return []
        return list(children)
    except (TypeError, AttributeError):
        return []


def _ruby_calculate_complexity(node: object) -> int:
    """Return cyclomatic complexity for a Ruby method node.

    complexity = 1 + (number of decision points).

    Decision points are:
    - Non-leaf nodes whose type is in _RUBY_DECISION_STATEMENT_TYPES (statement
      nodes like ``if``, ``elsif``, ``while``, etc.).  Non-leaf distinguishes
      the statement from the same-named keyword *token* that lives inside it.
    - Leaf tokens ``&&`` / ``||`` inside ``binary`` expressions.
    """
    decisions = 0
    stack = [node]
    while stack:
        cur = stack.pop()
        children = _safe_children(cur)
        is_leaf = len(children) == 0
        node_type = getattr(cur, "type", None)
        if not is_leaf and node_type == "case":
            # Valued ``case expr`` is a construct-once switch (+1); a
            # conditionless ``case`` adds nothing itself — its ``when`` arms
            # are counted individually below.
            if _ruby_case_has_subject(cur):
                decisions += 1
        elif not is_leaf and node_type == "when":
            # A ``when`` is a decision only inside a conditionless ``case``
            # (where it is an independent predicate, like ``elsif``).
            parent = getattr(cur, "parent", None)
            if (
                parent is not None
                and getattr(parent, "type", None) == "case"
                and not _ruby_case_has_subject(parent)
            ):
                decisions += 1
        elif not is_leaf and node_type in _RUBY_DECISION_STATEMENT_TYPES:
            decisions += 1
        elif is_leaf and node_type in _RUBY_LOGIC_OP_TOKENS:
            decisions += 1
        stack.extend(children)
    return 1 + decisions


def _ruby_case_has_subject(case_node: Any) -> bool:
    """True for a valued ``case expr`` (switch); False for conditionless ``case``."""
    try:
        return case_node.child_by_field_name("value") is not None
    except (AttributeError, TypeError):
        return False


# Type alias for the element cache key — avoids triple-nested generic annotation
# inside __init__, which would push identifier leaves to AST depth 17.
_ElementCacheKey = tuple[tuple[int, int], str]


class RubyElementExtractor(ElementExtractor):
    """Ruby AST extractor: Classes/Modules → Class, methods → Function, ivars/consts → Variable, requires → Import."""

    def __init__(self) -> None:
        super().__init__()
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self.current_module: str = ""

        # Performance optimization caches - use position-based keys for deterministic caching
        self._node_text_cache: dict[tuple[int, int], str] = {}
        self._processed_nodes: set[tuple[int, int]] = set()
        self._element_cache: dict[_ElementCacheKey, Any] = {}

    def _reset_caches(self) -> None:
        """Reset all internal caches for a new file analysis."""
        self._node_text_cache.clear()
        self._processed_nodes.clear()
        self._element_cache.clear()
        self.current_module = ""

    def _get_node_text_optimized(self, node: tree_sitter.Node) -> str:
        """Get node text with position-based caching for deterministic behavior."""
        cache_key = (node.start_byte, node.end_byte)
        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]
        # Use byte offsets via get_node_text_safe to handle multibyte chars correctly.
        text = get_node_text_safe(node, self.source_code)
        self._node_text_cache[cache_key] = text
        return text

    _VISIBILITY_KEYWORDS: frozenset[str] = frozenset({"private", "protected", "public"})

    def _determine_visibility(self, node: tree_sitter.Node | None) -> str:
        """Determine visibility by scanning preceding siblings for private/protected/public."""
        if node is None or node.parent is None:
            return "public"
        current = "public"
        for child in node.parent.children:
            if child.start_byte == node.start_byte:
                break
            if child.type == "identifier":
                text = child.text.decode(errors="replace") if child.text else ""
                if text in self._VISIBILITY_KEYWORDS:
                    current = text
        return current

    def extract_classes(self, tree: tree_sitter.Tree, source_code: str) -> list[Class]:
        """Extract Ruby classes and modules."""
        self.source_code = source_code
        self.content_lines = source_code.splitlines()
        self._reset_caches()

        classes: list[Class] = []
        stack: list[tree_sitter.Node] = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type in ("class", "module"):
                class_elem = self._extract_class_element(node)
                if class_elem:
                    classes.append(class_elem)
            for child in reversed(node.children):
                stack.append(child)
        return classes

    def _extract_class_element(self, node: tree_sitter.Node) -> Class | None:
        """Extract a single class or module element."""
        try:
            name_node = next(
                (c for c in node.children if c.type in ("constant", "scope_resolution")), None
            )
            if not name_node:
                return None
            name = self._get_node_text_optimized(name_node)
            start, end = node_range(node)
            return Class(
                name=name, start_line=start, end_line=end,
                visibility="public", is_abstract=False, full_qualified_name=name,
                superclass=self._find_ruby_superclass(node),
                interfaces=[], modifiers=[], annotations=[],
                class_type="module" if node.type == "module" else "class",
            )
        except Exception as e:
            log_error(f"Error extracting class element: {e}")
            return None

    def _find_ruby_superclass(self, class_node: tree_sitter.Node) -> str | None:
        """Return superclass name for ``class Foo < Bar``; None if no superclass.

        Theme-C (2026-06-10): skip the ``<`` token — real name is first non-operator child.
        """
        for child in class_node.children:
            if child.type != "superclass":
                continue
            for sub in child.children:
                if sub.type == "<":
                    continue
                text = self._get_node_text_optimized(sub)
                return str(text) if text else None
            return None
        return None

    def extract_functions(self, tree: tree_sitter.Tree, source_code: str) -> list[Function]:
        """Extract Ruby methods (instance, singleton, and attr_* methods)."""
        self.source_code = source_code
        self.content_lines = source_code.splitlines()

        functions: list[Function] = []
        stack: list[tuple[tree_sitter.Node, str]] = [(tree.root_node, "")]
        while stack:
            node, parent_class = stack.pop()
            if node.type == "method":
                elem = self._extract_method_element(node, parent_class)
                if elem:
                    functions.append(elem)
            elif node.type == "singleton_method":
                elem = self._extract_singleton_method_element(node, parent_class)
                if elem:
                    functions.append(elem)
            elif node.type == "call":
                functions.extend(self._extract_attr_methods(node, parent_class))
            new_parent = parent_class
            if node.type in ("class", "module"):
                resolved = self._find_ruby_class_name(node)
                if resolved is not None:
                    new_parent = resolved
            for child in reversed(node.children):
                stack.append((child, new_parent))
        return functions

    def _find_ruby_class_name(self, class_or_module_node: tree_sitter.Node) -> str | None:
        """Return the class/module name (first constant or scope_resolution child)."""
        for child in class_or_module_node.children:
            if child.type in ("constant", "scope_resolution"):
                return self._get_node_text_optimized(child)
        return None

    def _extract_method_element(self, node: tree_sitter.Node, parent_class: str) -> Function | None:
        """Extract an instance method element."""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None
            name = self._get_node_text_optimized(name_node)
            start, end = node_range(node)
            return Function(
                name=name,  # bare name; owner in receiver_type (#535)
                start_line=start, end_line=end,
                visibility=self._determine_visibility(node),
                is_static=False, is_async=False, is_abstract=False,
                parameters=self._extract_ruby_parameters(node.child_by_field_name("parameters")),
                return_type="", modifiers=[], annotations=[],
                receiver_type=parent_class if parent_class else None,
                is_constructor=name == "initialize",
                complexity_score=_ruby_calculate_complexity(node),
            )
        except Exception as e:
            log_error(f"Error extracting method element: {e}")
            return None

    _RUBY_PARAMETER_NODE_TYPES: tuple[str, ...] = (
        "identifier",
        "optional_parameter",
        "splat_parameter",
        "hash_splat_parameter",
        "block_parameter",
        "keyword_parameter",  # #768: name: default — was silently dropped
    )

    def _extract_ruby_parameters(self, params_node: tree_sitter.Node | None) -> list[str]:
        """Return parameter texts from a Ruby ``parameters`` node; empty list if None."""
        if params_node is None:
            return []
        return [
            self._get_node_text_optimized(p)
            for p in params_node.children
            if p.type in self._RUBY_PARAMETER_NODE_TYPES
        ]

    def _extract_singleton_method_element(self, node: tree_sitter.Node, parent_class: str) -> Function | None:
        """Extract a singleton (class-level) method element."""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None
            name = self._get_node_text_optimized(name_node)
            start, end = node_range(node)
            return Function(
                name=name,  # bare name; owner in receiver_type (#535)
                start_line=start, end_line=end,
                visibility=self._determine_visibility(node),
                is_static=True,  # singleton methods are class methods
                is_async=False, is_abstract=False,
                parameters=self._extract_ruby_parameters(node.child_by_field_name("parameters")),
                return_type="", modifiers=[], annotations=[],
                receiver_type=parent_class if parent_class else None,
                complexity_score=_ruby_calculate_complexity(node),
            )
        except Exception as e:
            log_error(f"Error extracting singleton method element: {e}")
            return None

    def _extract_attr_methods(
        self, node: tree_sitter.Node, parent_class: str
    ) -> list[Function]:
        """Extract attr_accessor, attr_reader, attr_writer methods."""
        return _extract_attrs_standalone(
            node, parent_class, self._get_node_text_optimized
        )

    def extract_variables(self, tree: tree_sitter.Tree, source_code: str) -> list[Variable]:
        """Extract Ruby instance variables, class variables, and constants."""
        self.source_code = source_code
        self.content_lines = source_code.splitlines()

        variables: list[Variable] = []

        # Stack carries (node, parent_class, in_non_init_method).
        # in_non_init_method=True means we are inside a method body that is
        # NOT initialize — assignments there are local state, not fields (#770).
        stack: list[tuple[tree_sitter.Node, str, bool]] = [(tree.root_node, "", False)]

        while stack:
            node, parent_class, in_non_init_method = stack.pop()
            if node.type == "assignment" and not in_non_init_method:
                var_elem = self._extract_assignment_variable(node, parent_class)
                if var_elem:
                    variables.append(var_elem)
            new_parent = parent_class
            if node.type in ("class", "module"):
                resolved = self._find_ruby_class_name(node)
                if resolved is not None:
                    new_parent = resolved
            # Track if children are inside a non-initialize method (skip field extraction there).
            # singleton_method is never a field source.
            new_in_non_init = in_non_init_method
            if node.type == "method":
                name_node = node.child_by_field_name("name")
                new_in_non_init = (self._get_node_text_optimized(name_node) if name_node else "") != "initialize"
            elif node.type == "singleton_method":
                new_in_non_init = True
            for child in reversed(node.children):
                stack.append((child, new_parent, new_in_non_init))
        return variables

    # Only emit real Ruby fields: @ivar, @@cvar, CONSTANT, scoped A::B (#770, #902).
    _RUBY_VAR_LNODE_TYPES: frozenset[str] = frozenset({
        "instance_variable", "class_variable", "constant", "scope_resolution",
    })

    def _extract_assignment_variable(self, node: tree_sitter.Node, parent_class: str) -> Variable | None:
        """Extract a field/constant variable from an assignment node."""
        try:
            left_node = node.child_by_field_name("left")
            if not left_node or left_node.type not in self._RUBY_VAR_LNODE_TYPES:
                return None
            var_text = self._get_node_text_optimized(left_node)
            is_constant = left_node.type in ("constant", "scope_resolution")
            is_class_var = left_node.type == "class_variable"
            start, end = node_range(node)
            return Variable(
                name=var_text.lstrip("@$"),  # bare name; owner via parent linkage (#535)
                start_line=start, end_line=end,
                visibility="public" if is_constant else "private",
                is_static=is_class_var or is_constant,
                is_constant=is_constant, is_final=is_constant,
                variable_type="", modifiers=[],
            )
        except Exception as e:
            log_error(f"Error extracting variable: {e}")
            return None

    def extract_imports(self, tree: tree_sitter.Tree, source_code: str) -> list[Import]:
        """Extract Ruby require / require_relative / load statements."""
        self.source_code = source_code
        self.content_lines = source_code.splitlines()

        imports: list[Import] = []
        stack: list[tree_sitter.Node] = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type == "call":
                elem = self._extract_require_statement(node)
                if elem:
                    imports.append(elem)
            for child in reversed(node.children):
                stack.append(child)

        return imports

    def _extract_require_statement(self, node: tree_sitter.Node) -> Import | None:
        """Extract require statement."""
        return _extract_require_standalone(node, self._get_node_text_optimized)


class RubyPlugin(LanguagePlugin):
    """Ruby language plugin using tree-sitter-ruby. Supports Ruby 3+ syntax."""

    _language_instance: tree_sitter.Language | None = None

    def get_language_name(self) -> str:
        return "ruby"

    def get_file_extensions(self) -> list[str]:
        return [".rb"]

    def get_tree_sitter_language(self) -> tree_sitter.Language:
        """Get the tree-sitter Language instance for Ruby (cached class-level)."""
        if not TREE_SITTER_AVAILABLE:
            raise ImportError(
                "tree-sitter is not installed. Install it with: pip install tree-sitter"
            )
        if RubyPlugin._language_instance is None:
            try:
                import tree_sitter_ruby
                RubyPlugin._language_instance = tree_sitter.Language(tree_sitter_ruby.language())
            except ImportError as e:
                raise ImportError(
                    "tree-sitter-ruby is not installed. Install it with: pip install tree-sitter-ruby"
                ) from e
        return RubyPlugin._language_instance

    def create_extractor(self) -> ElementExtractor:
        return RubyElementExtractor()

    def extract_elements(self, tree: tree_sitter.Tree, source_code: str) -> dict[str, list]:
        """Unified extraction entry point — delegates to the extractor."""
        return self.create_extractor().extract_elements(tree, source_code)

    async def analyze_file(self, file_path: str, request: AnalysisRequest) -> AnalysisResult:
        """Analyze a Ruby source file and return structured elements."""
        from ..models import AnalysisResult
        try:
            content = await self._load_file_safe(file_path)
            language = self.get_tree_sitter_language()
            parser = tree_sitter.Parser(language)
            tree = parser.parse(content.encode("utf-8"))
            extractor = self.create_extractor()
            all_elements = (
                extractor.extract_classes(tree, content)
                + extractor.extract_functions(tree, content)
                + extractor.extract_variables(tree, content)
                + extractor.extract_imports(tree, content)
            )
            return AnalysisResult(
                language=self.get_language_name(), file_path=file_path, success=True,
                elements=all_elements, line_count=len(content.splitlines()),
                node_count=self._count_nodes(tree.root_node),
            )
        except Exception as e:
            log_error(f"Error analyzing Ruby file {file_path}: {e}")
            return AnalysisResult(
                language=self.get_language_name(), file_path=file_path, success=False,
                error_message=str(e), elements=[], node_count=0,
            )

    def _count_nodes(self, node: tree_sitter.Node) -> int:
        """Recursively count AST nodes."""
        count = 1
        for child in node.children:
            count += self._count_nodes(child)
        return count

    async def _load_file_safe(self, file_path: str) -> str:
        """Load file with chardet encoding detection."""
        import chardet
        try:
            with open(file_path, "rb") as f:
                raw_content = f.read()
            detected = chardet.detect(raw_content)
            encoding = detected.get("encoding", "utf-8")
            return raw_content.decode(encoding or "utf-8")
        except Exception as e:
            log_error(f"Error loading file {file_path}: {e}")
            raise OSError(f"Failed to load file {file_path}: {e}") from e
