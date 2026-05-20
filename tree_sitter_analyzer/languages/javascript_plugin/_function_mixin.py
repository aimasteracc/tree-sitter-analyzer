"""Function and method extraction wrappers for the JavaScript plugin."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

from ...models import Function
from ._function_helpers import (
    extract_arrow_function,
    extract_function,
    extract_generator_function,
    extract_method,
)


class JavaScriptFunctionExtractionMixin:
    """Function-oriented extraction methods shared by JavaScript extractors."""

    def _extract_function_optimized(self, node: "tree_sitter.Node") -> Function | None:
        """Extract regular function information with detailed metadata."""
        return extract_function(
            node,
            self._parse_function_signature_optimized,
            self._extract_jsdoc_for_line,
            self._calculate_complexity_optimized,
            self.content_lines,
            self.framework_type,
        )

    def _extract_arrow_function_optimized(
        self, node: "tree_sitter.Node"
    ) -> Function | None:
        """Extract arrow function information."""
        return extract_arrow_function(
            node,
            self._get_node_text_optimized,
            self._extract_parameters,
            self._extract_jsdoc_for_line,
            self._calculate_complexity_optimized,
            self.framework_type,
        )

    def _extract_method_optimized(self, node: "tree_sitter.Node") -> Function | None:
        """Extract method information from class."""
        return extract_method(
            node,
            self._parse_method_signature_optimized,
            self._extract_jsdoc_for_line,
            self._calculate_complexity_optimized,
            self._get_node_text_optimized,
            self.framework_type,
        )

    def _extract_generator_function_optimized(
        self, node: "tree_sitter.Node"
    ) -> Function | None:
        """Extract generator function information."""
        return extract_generator_function(
            node,
            self._parse_function_signature_optimized,
            self._extract_jsdoc_for_line,
            self._calculate_complexity_optimized,
            self._get_node_text_optimized,
            self.framework_type,
        )

    def _parse_function_signature_optimized(
        self, node: "tree_sitter.Node"
    ) -> tuple[str, list[str], bool, bool] | None:
        """Parse function signature for regular functions."""
        try:
            name = None
            parameters = []

            node_text = self._get_node_text_optimized(node)
            is_async = "async" in node_text
            is_generator = node.type == "generator_function_declaration"

            for child in node.children:
                if child.type == "identifier":
                    name = child.text.decode("utf8") if child.text else None
                elif child.type == "formal_parameters":
                    parameters = self._extract_parameters(child)

            return name or "", parameters, is_async, is_generator
        except Exception:
            return None

    def _parse_method_signature_optimized(
        self, node: "tree_sitter.Node"
    ) -> tuple[str, list[str], bool, bool, bool, bool, bool] | None:
        """Parse method signature for class methods."""
        try:
            name = None
            parameters = []
            is_getter = False
            is_setter = False
            is_constructor = False

            node_text = self._get_node_text_optimized(node)
            is_async = "async" in node_text
            is_static = "static" in node_text

            for child in node.children:
                if child.type == "property_identifier":
                    name = self._get_node_text_optimized(child)
                    is_constructor = name == "constructor"
                elif child.type == "formal_parameters":
                    parameters = self._extract_parameters(child)

            if "get " in node_text:
                is_getter = True
            elif "set " in node_text:
                is_setter = True

            return (
                name or "",
                parameters,
                is_async,
                is_static,
                is_getter,
                is_setter,
                is_constructor,
            )
        except Exception:
            return None

    def _extract_parameters(self, params_node: "tree_sitter.Node") -> list[str]:
        """Extract function parameters."""
        parameters = []

        for child in params_node.children:
            if child.type == "identifier":
                param_name = self._get_node_text_optimized(child)
                parameters.append(param_name)
            elif child.type == "rest_parameter":
                rest_text = self._get_node_text_optimized(child)
                parameters.append(rest_text)
            elif child.type in ["object_pattern", "array_pattern"]:
                destructure_text = self._get_node_text_optimized(child)
                parameters.append(destructure_text)

        return parameters
