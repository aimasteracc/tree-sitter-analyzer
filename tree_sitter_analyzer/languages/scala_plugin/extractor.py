"""Scala Element Extractor — core state, traversal, and public extract_* API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

from ...encoding_utils import extract_text_slice, safe_encode
from ...models import Class, Expression, Function, Import, Package, Variable
from ...plugins.base import ElementExtractor
from ...utils import log_debug
from ..shared.traversal import node_range
from ._class_extractor_mixin import ScalaClassExtractionMixin
from ._function_extractor_mixin import ScalaFunctionExtractionMixin
from ._scaladoc import _parse_scaladoc_text
from ._variable_import_mixin import ScalaVariableImportMixin

__all__ = ["ScalaElementExtractor"]


class ScalaElementExtractor(
    ScalaFunctionExtractionMixin,
    ScalaClassExtractionMixin,
    ScalaVariableImportMixin,
    ElementExtractor,
):
    """Scala-specific element extractor"""

    def __init__(self) -> None:
        """Initialize the Scala element extractor."""
        self.current_package: str = ""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self._node_text_cache: dict[tuple[int, int], str] = {}

    def extract_functions(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Function]:
        """Extract Scala function definitions and declarations"""
        self._setup(source_code)

        functions: list[Function] = []

        self._traverse_functions_with_context(tree.root_node, functions, None, None)

        log_debug(f"Extracted {len(functions)} Scala functions")
        return functions

    def extract_classes(self, tree: tree_sitter.Tree, source_code: str) -> list[Class]:
        """Extract Scala class, object, trait, enum, given, and type definitions."""
        self._setup(source_code)

        # Extract package first
        self._extract_package(tree.root_node)

        classes: list[Class] = []
        self._traverse_classes_with_context(tree.root_node, classes, parent_class=None)

        log_debug(f"Extracted {len(classes)} Scala classes/objects/traits")
        return classes

    def extract_variables(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Variable]:
        """Extract Scala val and var definitions"""
        self._setup(source_code)

        variables: list[Variable] = []

        extractors = {
            "val_definition": self._extract_val,
            "var_definition": self._extract_var,
        }

        self._traverse_and_extract(
            tree.root_node,
            extractors,
            variables,
        )

        log_debug(f"Extracted {len(variables)} Scala val/var definitions")
        return variables

    def extract_imports(self, tree: tree_sitter.Tree, source_code: str) -> list[Import]:
        """Extract Scala imports"""
        self._setup(source_code)

        imports: list[Import] = []

        extractors = {
            "import_declaration": self._extract_import,
        }

        self._traverse_and_extract(
            tree.root_node,
            extractors,
            imports,
        )

        log_debug(f"Extracted {len(imports)} Scala imports")
        return imports

    def extract_packages(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Package]:
        """Extract Scala package"""
        self._setup(source_code)

        # r37dt (dogfood): mirror of kotlin r37ds — flatten nesting 6 → 3
        # via _find_package_clause_node helper.
        packages: list[Package] = []
        self._extract_package(tree.root_node)
        if not self.current_package:
            return packages
        package_node = self._find_package_clause_node(tree.root_node)
        if package_node is None:
            return packages
        _pkg_start, _pkg_end = node_range(package_node)
        packages.append(
            Package(
                name=self.current_package,
                start_line=_pkg_start,
                end_line=_pkg_end,
                raw_text=self._get_node_text(package_node),
                language="scala",
            )
        )
        return packages

    @staticmethod
    def _find_package_clause_node(
        root_node: tree_sitter.Node,
    ) -> tree_sitter.Node | None:
        """Return the first ``package_clause`` child or ``None``."""
        for child in root_node.children:
            if child.type == "package_clause":
                return child
        return None

    def extract_comments(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Expression]:
        """Extract Scala block comments"""
        self._setup(source_code)

        comments: list[Expression] = []

        extractors = {
            "block_comment": self._extract_comment,
        }

        self._traverse_and_extract(tree.root_node, extractors, comments)

        log_debug(f"Extracted {len(comments)} Scala comments")
        return comments

    def extract_annotations(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Expression]:
        """Extract Scala annotations"""
        self._setup(source_code)

        annotations: list[Expression] = []

        extractors = {
            "annotation": self._extract_annotation,
        }

        self._traverse_and_extract(tree.root_node, extractors, annotations)

        log_debug(f"Extracted {len(annotations)} Scala annotations")
        return annotations

    def _setup(self, source_code: str) -> None:
        """Set source code and reset caches — called at the top of every extract_* method."""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()
        if not self.source_code:
            self.current_package = ""

    def _traverse_and_extract(
        self,
        node: tree_sitter.Node,
        extractors: dict[str, Any],
        results: list[Any],
    ) -> None:
        """Iterative traversal to find and extract elements (stack-safe)."""
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type in extractors:
                element = extractors[current.type](current)
                if element:
                    results.append(element)
            stack.extend(reversed(current.children))

    def _extract_package(self, node: tree_sitter.Node) -> None:
        """Extract package declaration from package_clause.

        r37dw (dogfood): flatten nesting 6 → 3 via
        ``_scala_package_name_from_clause`` (mirror of kotlin r37ds).
        """
        for child in node.children:
            if child.type != "package_clause":
                continue
            pkg_name = self._scala_package_name_from_clause(child)
            if pkg_name is not None:
                self.current_package = pkg_name
                return

    def _scala_package_name_from_clause(
        self, package_clause: tree_sitter.Node
    ) -> str | None:
        """Return the package name string from a ``package_clause`` node.

        Scala's grammar emits ``package_identifier`` for qualified names
        (``a.b.c``) or plain ``identifier`` for top-level packages; some
        forks fall back to a node whose ``type`` contains the substring
        ``"identifier"``. We accept any of those at the first match.
        """
        for grandchild in package_clause.children:
            if grandchild.type in ("package_identifier", "identifier"):
                return self._get_node_text(grandchild)
            if "identifier" in grandchild.type:
                return self._get_node_text(grandchild)
        return None

    def _scala_visibility(self, node: tree_sitter.Node) -> str:
        """Return ``private`` / ``protected`` / ``public`` from a modifiers child.

        Scans for the first ``modifiers`` child and checks its text for
        the explicit keywords. Defaults to ``public`` when no modifiers
        node is present or contains neither keyword.

        Qualified-access modifiers such as ``private[pkg]`` /
        ``protected[this]`` are emitted by ``_scala_modifiers`` as the
        single literal token ``private[pkg]`` (not a bare ``private``), so
        match the keyword as a prefix rather than by exact membership —
        otherwise ``private[pkg] class Secret`` is misreported as public.
        """
        modifiers = self._scala_modifiers(node)
        if any(m == "private" or m.startswith("private[") for m in modifiers):
            return "private"
        if any(m == "protected" or m.startswith("protected[") for m in modifiers):
            return "protected"
        return "public"

    def _scala_modifiers(self, node: tree_sitter.Node) -> list[str]:
        modifiers: list[str] = []
        for child in node.children:
            if child.type != "modifiers":
                continue
            for modifier in child.children:
                text = self._get_node_text(modifier)
                if text:
                    modifiers.append(text)
            if not modifiers:
                text = self._get_node_text(child)
                if text:
                    modifiers.extend(text.split())
            break
        return modifiers

    def _scala_type_after_colon(self, node: tree_sitter.Node, default: str) -> str:
        """Scan ``node.children`` for ``:`` and return the next sibling text.

        Returns ``default`` when no ``:`` child exists or it's the last
        child (caller picks ``"Unit"`` for functions, ``"Inferred"`` for
        val/var declarations to match Scala-language conventions).
        """
        children = node.children
        for i, child in enumerate(children):
            if child.type == ":":
                if i + 1 < len(children):
                    return self._get_node_text(children[i + 1])
                return default
        return default

    def _get_node_text(self, node: tree_sitter.Node) -> str:
        """Get node text with caching using position-based keys"""
        cache_key = (node.start_byte, node.end_byte)
        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]

        try:
            start_byte = node.start_byte
            end_byte = node.end_byte
            encoding = "utf-8"
            content_bytes = safe_encode("\n".join(self.content_lines), encoding)
            text = extract_text_slice(content_bytes, start_byte, end_byte, encoding)
            self._node_text_cache[cache_key] = text
            return text
        except Exception:
            return ""

    def _extract_docstring(self, node: tree_sitter.Node) -> str | None:
        """Extract Scaladoc comments (/** ... */)"""
        # Scala uses /** ... */ for documentation comments
        # Look for block_comment nodes that immediately precede this node
        if not node.parent:
            return None

        # Find the immediately preceding block_comment sibling
        prev_comment = None
        prev_sibling = None

        for sibling in node.parent.children:
            if sibling == node:
                break
            prev_sibling = sibling

        # r37dw (dogfood): flatten nesting 6 → 3 via _last_nearby_block_comment.
        if prev_sibling and prev_sibling.type == "block_comment":
            prev_comment = prev_sibling
        elif prev_sibling and prev_sibling.type != "block_comment":
            prev_comment = self._last_nearby_block_comment(node)

        # r37dw (dogfood): scaladoc parsing抽到 _parse_scaladoc_text.
        if prev_comment is None:
            return None
        return _parse_scaladoc_text(self._get_node_text(prev_comment))

    def _last_nearby_block_comment(
        self, node: tree_sitter.Node
    ) -> tree_sitter.Node | None:
        """Return the last ``block_comment`` sibling within 2 lines of ``node``.

        Walks left-to-right through ``node.parent.children`` up to (but
        not including) ``node`` itself; tracks the most recent
        ``block_comment`` and only returns it when it ends ≤ 2 lines
        before ``node`` starts. ``None`` when no eligible comment exists
        (Scaladoc must be adjacent for the binding to be unambiguous).
        """
        last_close: tree_sitter.Node | None = None
        if node.parent is None:
            return None
        for sibling in node.parent.children:
            if sibling == node:
                break
            if sibling.type == "block_comment":
                if node.start_point[0] - sibling.end_point[0] <= 2:
                    last_close = sibling
        return last_close
