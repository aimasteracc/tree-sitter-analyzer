"""Function extraction mixin for the Python element extractor."""

from __future__ import annotations

import traceback
from typing import Any

from ...models import Function
from ...utils import log_debug, log_error, log_warning
from ._extractor_helpers import (
    DetailedFunctionBuildInput,
    FunctionBuildInput,
    _extract_decorated_function_decorators,
    _parse_function_signature_children,
    _return_type_from_signature_text,
    _strip_docstring_quotes,
    build_detailed_function_element,
    build_function_element,
    function_raw_text,
    node_line_range,
    node_raw_text,
)


class PythonFunctionExtractionMixin:
    def extract_functions(self, tree: Any, source_code: str) -> list[Function]:
        """Extract Python function definitions with comprehensive details."""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()
        self._detect_file_characteristics()

        functions: list[Function] = []
        extractors = {
            "function_definition": self._extract_function_optimized,
        }

        if tree is not None and tree.root_node is not None:
            try:
                self._traverse_and_extract_iterative(
                    tree.root_node, extractors, functions, "function"
                )
                log_debug(f"Extracted {len(functions)} Python functions")
            except Exception as exc:
                log_debug(f"Error during function extraction: {exc}")
                return []

        return functions

    def _extract_function_optimized(self, node: Any) -> Function | None:
        """Extract function information with detailed metadata."""
        try:
            start_line, end_line = node_line_range(node)
            function_info = self._parse_function_signature_optimized(node)
            if not function_info:
                return None

            name, parameters, is_async, decorators, return_type = function_info
            docstring = self._extract_docstring_for_line(start_line)
            complexity_score = self._calculate_complexity_optimized(node)
            raw_text = function_raw_text(self.content_lines, start_line, end_line)

            return build_function_element(
                FunctionBuildInput(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    parameters=parameters,
                    return_type=return_type,
                    is_async=is_async,
                    decorators=decorators,
                    docstring=docstring,
                    complexity_score=complexity_score,
                    framework_type=self.framework_type,
                )
            )
        except Exception as exc:
            log_error(f"Failed to extract function info: {exc}")
            traceback.print_exc()
            return None

    def _parse_function_signature_optimized(
        self, node: Any
    ) -> tuple[str, list[str], bool, list[str], str | None] | None:
        """Parse function signature for Python functions."""
        try:
            node_text = self._get_node_text_optimized(node)
            is_async = node_text.strip().startswith("async def")
            return_type = _return_type_from_signature_text(node_text)

            decorators = _extract_decorated_function_decorators(
                node.parent, self._get_node_text_optimized
            )
            name, parameters, return_type = _parse_function_signature_children(
                node,
                self._get_node_text_optimized,
                self._extract_parameters_from_node_optimized,
                return_type,
            )

            return name, parameters, is_async, decorators, return_type
        except Exception:
            return None

    def _extract_detailed_function_info(
        self, node: Any, source_code: str, is_async: bool = False
    ) -> Function | None:
        """Extract comprehensive function information from AST node."""
        try:
            name = self._extract_name_from_node(node, source_code)
            if not name:
                return None

            parameters = self._extract_parameters_from_node(node, source_code)
            decorators = self._extract_decorators_from_node(node, source_code)
            return_type = self._extract_return_type_from_node(node, source_code)
            start_line, end_line = node_line_range(node)

            return build_detailed_function_element(
                DetailedFunctionBuildInput(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=node_raw_text(node, source_code),
                    parameters=parameters,
                    return_type=return_type,
                    decorators=decorators,
                )
            )

        except Exception as exc:
            log_warning(f"Could not extract detailed function info: {exc}")
            return None

    def _extract_return_type_from_node(self, node: Any, source_code: str) -> str | None:
        """Extract return type annotation from function node."""
        node_text = self._get_node_text_optimized(node)
        if "->" in node_text:
            parts = node_text.split("->")
            if len(parts) > 1:
                return_part = parts[1].split(":")[0].strip()
                return_type = return_part.replace("\n", " ").strip()
                if return_type and not return_type.startswith("@"):
                    return return_type

        for child in node.children:
            if child.type == "type":
                type_text = source_code[child.start_byte : child.end_byte]
                if type_text and not type_text.startswith("@"):
                    return type_text
        return None

    def _extract_docstring_from_node(self, node: Any, source_code: str) -> str | None:
        """Extract docstring from function/class node."""
        block = next((child for child in node.children if child.type == "block"), None)
        if block is None:
            return None

        statement = next(
            (stmt for stmt in block.children if stmt.type == "expression_statement"),
            None,
        )
        if statement is None:
            return None

        string_node = next(
            (expr for expr in statement.children if expr.type == "string"),
            None,
        )
        if string_node is None or not self._validate_node(string_node):
            return None

        docstring = source_code[string_node.start_byte : string_node.end_byte]
        return _strip_docstring_quotes(docstring)
