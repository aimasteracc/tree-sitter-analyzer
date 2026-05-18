"""Default extractor traversal helpers."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

from ..models import Class as ModelClass
from ..models import Function as ModelFunction
from ..models import Import as ModelImport
from ..models import Variable as ModelVariable
from ..utils import log_debug

FUNCTION_NODE_TYPES = (
    "function_definition",
    "function_declaration",
    "method_definition",
    "function",
    "method",
    "procedure",
    "subroutine",
)
CLASS_NODE_TYPES = (
    "class_definition",
    "class_declaration",
    "interface_definition",
    "class",
    "interface",
    "struct",
    "enum",
)
VARIABLE_NODE_TYPES = (
    "variable_declaration",
    "variable_definition",
    "field_declaration",
    "assignment",
    "declaration",
    "variable",
    "field",
)
IMPORT_NODE_TYPES = (
    "import_statement",
    "import_declaration",
    "include_statement",
    "import",
    "include",
    "require",
    "use",
)


def _node_start_line(node: "tree_sitter.Node") -> int:
    if hasattr(node, "start_point"):
        return node.start_point[0] + 1
    return 0


def _node_end_line(node: "tree_sitter.Node") -> int:
    if hasattr(node, "end_point"):
        return node.end_point[0] + 1
    return 0


def _iter_children(node: "tree_sitter.Node") -> object:
    return getattr(node, "children", ())


def _tree_root_node(tree: "tree_sitter.Tree") -> object | None:
    return getattr(tree, "root_node", None)


def _node_type_matches(node_type: str, candidates: tuple[str, ...]) -> bool:
    lowered = node_type.lower()
    return any(candidate in lowered for candidate in candidates)


def _is_function_node(node_type: str) -> bool:
    return _node_type_matches(node_type, FUNCTION_NODE_TYPES)


def _is_class_node(node_type: str) -> bool:
    return _node_type_matches(node_type, CLASS_NODE_TYPES)


def _is_variable_node(node_type: str) -> bool:
    return _node_type_matches(node_type, VARIABLE_NODE_TYPES)


def _is_import_node(node_type: str) -> bool:
    return _node_type_matches(node_type, IMPORT_NODE_TYPES)


def _find_identifier_child(node: "tree_sitter.Node") -> object | None:
    return next(
        (
            child
            for child in getattr(node, "children", ())
            if getattr(child, "type", None) == "identifier"
        ),
        None,
    )


def _format_fallback_node_name(node: "tree_sitter.Node") -> str:
    return f"element_{node.start_point[0]}_{node.start_point[1]}"


def _extract_node_text(node: "tree_sitter.Node", source_code: str) -> str:
    try:
        if hasattr(node, "start_byte") and hasattr(node, "end_byte"):
            source_bytes = source_code.encode("utf-8")
            node_bytes = source_bytes[node.start_byte : node.end_byte]
            return node_bytes.decode("utf-8", errors="replace")
        return ""
    except Exception as e:
        log_debug(f"Failed to extract node text: {e}")
        return ""


def _get_language_hint() -> str:
    return "unknown"


class DefaultNodeMixin:
    """Node classification and text helpers used by the default extractor."""

    _tree_root_node = staticmethod(_tree_root_node)
    _is_function_node = staticmethod(_is_function_node)
    _is_class_node = staticmethod(_is_class_node)
    _is_variable_node = staticmethod(_is_variable_node)
    _is_import_node = staticmethod(_is_import_node)
    _find_identifier_child = staticmethod(_find_identifier_child)
    _format_fallback_node_name = staticmethod(_format_fallback_node_name)
    _extract_node_text = staticmethod(_extract_node_text)
    _get_language_hint = staticmethod(_get_language_hint)

    def _extract_node_name(
        self, node: "tree_sitter.Node", source_code: str
    ) -> str | None:
        """Extract name from a tree-sitter node."""
        try:
            identifier = self._find_identifier_child(node)
            if identifier is not None:
                return self._extract_node_text(identifier, source_code)
            return self._format_fallback_node_name(node)
        except Exception:
            return None

    def _element_fields(
        self, node: "tree_sitter.Node", source_code: str
    ) -> dict[str, object]:
        return {
            "name": self._extract_node_name(node, source_code) or "unknown",
            "start_line": _node_start_line(node),
            "end_line": _node_end_line(node),
            "raw_text": self._extract_node_text(node, source_code),
            "language": self._get_language_hint(),
        }


class DefaultTraverseAppendMixin(DefaultNodeMixin):
    """Build model elements from matched AST nodes."""

    def _append_function(
        self,
        node: "tree_sitter.Node",
        functions: list[ModelFunction],
        source_code: str,
    ) -> None:
        try:
            functions.append(ModelFunction(**self._element_fields(node, source_code)))
        except Exception as e:
            log_debug(f"Failed to extract function: {e}")

    def _append_class(
        self,
        node: "tree_sitter.Node",
        classes: list[ModelClass],
        source_code: str,
    ) -> None:
        try:
            classes.append(ModelClass(**self._element_fields(node, source_code)))
        except Exception as e:
            log_debug(f"Failed to extract class: {e}")

    def _append_variable(
        self,
        node: "tree_sitter.Node",
        variables: list[ModelVariable],
        source_code: str,
    ) -> None:
        try:
            variables.append(ModelVariable(**self._element_fields(node, source_code)))
        except Exception as e:
            log_debug(f"Failed to extract variable: {e}")

    def _append_import(
        self,
        node: "tree_sitter.Node",
        imports: list[ModelImport],
        source_code: str,
    ) -> None:
        try:
            imports.append(ModelImport(**self._element_fields(node, source_code)))
        except Exception as e:
            log_debug(f"Failed to extract import: {e}")


class DefaultTraverseMixin(DefaultTraverseAppendMixin):
    """Recursive traversal methods used by the default extractor."""

    def _traverse_for_functions(
        self,
        node: "tree_sitter.Node",
        functions: list[ModelFunction],
        lines: list[str],
        source_code: str,
    ) -> None:
        """Traverse tree to find function-like nodes."""
        if self._is_function_node(getattr(node, "type", "")):
            self._append_function(node, functions, source_code)

        for child in _iter_children(node):
            self._traverse_for_functions(child, functions, lines, source_code)

    def _traverse_for_classes(
        self,
        node: "tree_sitter.Node",
        classes: list[ModelClass],
        lines: list[str],
        source_code: str,
    ) -> None:
        """Traverse tree to find class-like nodes."""
        if self._is_class_node(getattr(node, "type", "")):
            self._append_class(node, classes, source_code)

        for child in _iter_children(node):
            self._traverse_for_classes(child, classes, lines, source_code)

    def _traverse_for_variables(
        self,
        node: "tree_sitter.Node",
        variables: list[ModelVariable],
        lines: list[str],
        source_code: str,
    ) -> None:
        """Traverse tree to find variable declarations."""
        if self._is_variable_node(getattr(node, "type", "")):
            self._append_variable(node, variables, source_code)

        for child in _iter_children(node):
            self._traverse_for_variables(child, variables, lines, source_code)

    def _traverse_for_imports(
        self,
        node: "tree_sitter.Node",
        imports: list[ModelImport],
        lines: list[str],
        source_code: str,
    ) -> None:
        """Traverse tree to find import statements."""
        if self._is_import_node(getattr(node, "type", "")):
            self._append_import(node, imports, source_code)

        for child in _iter_children(node):
            self._traverse_for_imports(child, imports, lines, source_code)
