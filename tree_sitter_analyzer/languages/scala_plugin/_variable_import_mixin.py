"""Variable (val/var), import, comment, and annotation extraction for Scala."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

from ...models import Expression, Import, Variable
from ...utils import log_error
from ..shared.traversal import node_range


class ScalaVariableImportMixin:
    """val/var, import, comment, and annotation extraction, mixed into
    ``ScalaElementExtractor``."""

    def _extract_val(self, node: tree_sitter.Node) -> Variable | None:
        """Extract val definition (immutable)"""
        return self._extract_variable(node, is_val=True)

    def _extract_var(self, node: tree_sitter.Node) -> Variable | None:
        """Extract var definition (mutable)"""
        return self._extract_variable(node, is_val=False)

    def _extract_variable(
        self, node: tree_sitter.Node, is_val: bool = True
    ) -> Variable | None:
        """Common extraction logic for val/var"""
        try:
            # Extract name (handles plain ``identifier`` and ``pattern_list``
            # forms). r37ca: extracted to drop ``_extract_variable`` nesting
            # from 7 to ≤3.
            name = self._extract_scala_variable_name(node)

            start_line, end_line = node_range(node)

            # r37dw (dogfood): reuse _scala_type_after_colon + _scala_visibility.
            var_type = self._scala_type_after_colon(node, "Inferred")
            visibility = self._scala_visibility(node)
            docstring = self._extract_docstring(node)
            raw_text = self._get_node_text(node)

            var = Variable(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="scala",
                variable_type=var_type,
                visibility=visibility,
                docstring=docstring,
            )
            var.is_val = is_val
            var.is_var = not is_val

            return var

        except Exception as e:
            log_error(f"Error extracting Scala variable: {e}")
            return None

    def _extract_scala_variable_name(self, node: tree_sitter.Node) -> str:
        """Scala val/var binds a name either as a direct ``identifier`` child
        or as the first identifier inside a ``pattern_list``.

        r37ca (dogfood): extracted from ``_extract_variable`` to flatten its
        7-deep nesting (for-elif-for-if-break).
        r37dw: pattern_list inner scan moved into ``_first_identifier_in``
        helper to drop nesting from 6 to 3.
        """
        for child in node.children:
            if child.type == "identifier":
                return str(self._get_node_text(child))
            if child.type == "pattern_list":
                inner = self._first_identifier_in(child)
                if inner is not None:
                    return inner
        return "unknown"

    def _first_identifier_in(self, node: tree_sitter.Node) -> str | None:
        """Return the first ``identifier`` child's text or ``None``."""
        for grandchild in node.children:
            if grandchild.type == "identifier":
                return str(self._get_node_text(grandchild))
        return None

    def _extract_import(self, node: tree_sitter.Node) -> Import | None:
        """Extract import declaration"""
        try:
            raw_text = self._get_node_text(node)
            start_line, end_line = node_range(node)

            # Parse import path
            # import_declaration -> 'import' import_expression
            name = "unknown"
            for child in node.children:
                if child.type != "import":
                    # Take the import expression text
                    name = self._get_node_text(child)
                    break

            return Import(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="scala",
                import_statement=raw_text,
            )
        except Exception as e:
            log_error(f"Error extracting Scala import: {e}")
            return None

    def _extract_comment(self, node: tree_sitter.Node) -> Expression | None:
        """Extract Scala block comment"""
        try:
            raw_text = self._get_node_text(node)
            start_line, end_line = node_range(node)

            # Get preview (first 50 chars)
            preview = raw_text[:50] if len(raw_text) > 50 else raw_text

            return Expression(
                name="block_comment",
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="scala",
                expression_kind="block_comment",
                preview=preview,
            )
        except Exception as e:
            log_error(f"Error extracting Scala comment: {e}")
            return None

    def _extract_annotation(self, node: tree_sitter.Node) -> Expression | None:
        """Extract Scala annotation"""
        try:
            raw_text = self._get_node_text(node)
            start_line, end_line = node_range(node)

            # Extract annotation name from the tree
            # annotation -> @ stable_type_identifier
            annotation_name = "unknown"
            for child in node.children:
                if child.type in (
                    "stable_type_identifier",
                    "type_identifier",
                    "identifier",
                ):
                    annotation_name = self._get_node_text(child)
                    break
                # Handle simple identifier after @
                if child.type == "identifier":
                    annotation_name = self._get_node_text(child)
                    break

            return Expression(
                name=annotation_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="scala",
                expression_kind="annotation",
                node_type="annotation",
            )
        except Exception as e:
            log_error(f"Error extracting Scala annotation: {e}")
            return None
