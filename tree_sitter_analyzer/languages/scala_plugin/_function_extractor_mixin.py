"""Function/method definition and declaration extraction for Scala."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

from ...models import Function
from ...utils import log_error
from ..shared.traversal import node_range
from ._complexity import calculate_scala_complexity


class ScalaFunctionExtractionMixin:
    """Function/method extraction, mixed into ``ScalaElementExtractor``."""

    def _traverse_functions_with_context(
        self,
        node: tree_sitter.Node,
        results: list[Function],
        parent_class: str | None,
        receiver_type: str | None,
    ) -> None:
        stack: list[tuple[tree_sitter.Node, str | None, str | None]] = [
            (node, parent_class, receiver_type)
        ]
        while stack:
            current, current_parent, current_receiver = stack.pop()
            node_type = current.type

            if node_type in (
                "class_definition",
                "object_definition",
                "trait_definition",
                "enum_definition",
            ):
                new_parent = self._scala_class_like_name(current)
                for child in reversed(current.children):
                    stack.append((child, new_parent, None))
                continue

            if node_type == "given_definition":
                new_parent = self._scala_given_name(current)
                for child in reversed(current.children):
                    stack.append((child, new_parent, None))
                continue

            if node_type == "extension_definition":
                new_receiver = self._scala_extension_receiver_type(current)
                for child in reversed(current.children):
                    stack.append((child, current_parent, new_receiver))
                continue

            if node_type == "function_definition":
                fn = self._extract_function(current)
                if fn:
                    fn.parent_class = current_parent
                    fn.receiver_type = current_receiver
                    results.append(fn)
                for child in reversed(current.children):
                    stack.append((child, current_parent, current_receiver))
                continue

            if node_type == "function_declaration":
                fn = self._extract_function_declaration(current)
                if fn:
                    fn.parent_class = current_parent
                    fn.receiver_type = current_receiver
                    results.append(fn)
                for child in reversed(current.children):
                    stack.append((child, current_parent, current_receiver))
                continue

            for child in reversed(current.children):
                stack.append((child, current_parent, current_receiver))

    def _extract_function(self, node: tree_sitter.Node) -> Function | None:
        """Extract function definition (with body)"""
        return self._extract_function_common(node)

    def _extract_function_declaration(self, node: tree_sitter.Node) -> Function | None:
        """Extract function declaration (abstract, without body)"""
        return self._extract_function_common(node)

    def _extract_function_common(self, node: tree_sitter.Node) -> Function | None:
        """Common extraction logic for Scala functions.

        r37dw (dogfood): flatten name-fallback (depth 6) + return-type
        scan + visibility scan into focused helpers.
        """
        try:
            name = self._scala_function_name(node)
            start_line, end_line = node_range(node)
            parameters: list[str] = []
            for child in node.children:
                if "parameter" in child.type:
                    parameters.extend(self._extract_parameters(child))
            return_type = self._scala_return_type(node)
            visibility = self._scala_visibility(node)

            # Extract docstring
            docstring = self._extract_docstring(node)
            raw_text = self._get_node_text(node)

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="scala",
                parameters=parameters,
                return_type=return_type,
                visibility=visibility,
                modifiers=self._scala_modifiers(node),
                docstring=docstring,
                is_constructor=name == "this",
                complexity_score=calculate_scala_complexity(node),
            )

        except Exception as e:
            log_error(f"Error extracting Scala function: {e}")
            return None

    def _scala_function_name(self, node: tree_sitter.Node) -> str:
        """Return the function name, falling back to the first identifier child.

        r37dw (dogfood): lifted from ``_extract_function_common`` to
        flatten its name-resolution branch from depth 6 to 3.
        """
        name_node = node.child_by_field_name("name")
        if name_node:
            return self._get_node_text(name_node)
        for child in node.children:
            if child.type == "identifier":
                return self._get_node_text(child)
        return "anonymous"

    def _scala_return_type(self, node: tree_sitter.Node) -> str:
        """Return the type annotation after a ``:`` child, default ``Unit``.

        For variable declarations use ``_scala_type_after_colon(node, "Inferred")``
        instead — function return types want ``Unit`` as the missing-type sentinel.

        Issue #594: ``def get(key: String) = "legacy"`` must not claim
        Unit — the expression body infers the type. Full inference is a
        non-goal; pin trivial literals, otherwise emit "" (unknown,
        matching the Go plugin's absent-return-type convention). Block
        bodies / abstract defs without an explicit type really are
        Unit-defaulted — keep. Mirrors the Kotlin fix for #591/#593.
        """
        if any(child.type == ":" for child in node.children):
            return self._scala_type_after_colon(node, "Unit")
        inferred = self._scala_expression_body_type(node)
        if inferred is not None:
            return inferred
        return "Unit"

    def _scala_expression_body_type(self, node: tree_sitter.Node) -> str | None:
        """Infer the return type of an expression-body def (issue #594).

        Returns:
            * ``None`` — no expression body (block body or abstract def);
              caller keeps the ``Unit`` default, which is correct there.
            * a pinned literal type (``String``/``Int``/``Boolean``/``Double``)
              for trivial literal bodies (Scala's ``string`` node covers
              raw triple-quoted strings too — live-verified node shapes).
            * ``""`` (unknown) for any other expression body — honest "no
              claim", never a fabricated ``Unit``.
        """
        children = node.children
        expr = None
        for i, child in enumerate(children):
            if child.type == "=":
                if i + 1 >= len(children):
                    return ""  # malformed: '=' with nothing after it
                expr = children[i + 1]
                break
        if expr is None:
            return None  # block body or abstract def → Unit default is correct
        if expr.type == "indented_block":
            # `def f =\n  "x"` wraps the RHS in an indented_block (Codex P2
            # on #597); a single-expression block is the same literal case.
            named = [c for c in expr.children if c.is_named and c.type != "comment"]
            if len(named) != 1:
                return ""
            expr = named[0]
        if expr.type == "string":
            return "String"
        if expr.type == "floating_point_literal":
            return "Double"
        if expr.type == "integer_literal":
            # Signed decimal literals (`-1`) are a single integer_literal node
            # and infer Int (Codex P2 on #597); 42L / 0xFF etc. stay unknown.
            text = self._get_node_text(expr)
            digits = text[1:] if text[:1] in ("-", "+") else text
            return "Int" if digits.isdigit() else ""
        if expr.type == "boolean_literal":
            return "Boolean"
        return ""

    def _extract_parameters(self, param_node: tree_sitter.Node) -> list[str]:
        """Extract parameters from a parameter clause.

        r37dw (dogfood): flatten nesting 6 → 3 via _scala_parameter_pair
        (mirror of kotlin r37dt).
        """
        parameters: list[str] = []
        for child in param_node.children:
            if child.type in ("parameter", "class_parameter"):
                param_name, param_type = self._scala_parameter_pair(child)
                if param_name:
                    type_str = param_type or "Any"
                    parameters.append(f"{param_name}: {type_str}")
            elif child.type == "parameters" or "parameter" in child.type:
                # Recursively extract nested parameters
                parameters.extend(self._extract_parameters(child))
        return parameters

    def _scala_parameter_pair(
        self, parameter_node: tree_sitter.Node
    ) -> tuple[str, str]:
        """Return ``(name, type)`` from a Scala ``parameter`` / ``class_parameter``.

        Recognises ``identifier`` for the name and any node whose type
        contains ``"type"`` (including ``type_identifier``) for the type.
        Empty strings when either side is missing; caller fills ``"Any"``
        for blank types to match Scala's defaulting.
        """
        param_name = ""
        param_type = ""
        for grandchild in parameter_node.children:
            if grandchild.type == "identifier":
                param_name = self._get_node_text(grandchild)
            elif "type" in grandchild.type or grandchild.type == "type_identifier":
                param_type = self._get_node_text(grandchild)
        return param_name, param_type
