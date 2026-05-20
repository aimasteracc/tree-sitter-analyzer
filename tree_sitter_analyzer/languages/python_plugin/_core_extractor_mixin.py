"""Core state, traversal, and text helpers for the Python extractor."""

from __future__ import annotations

import sys
from typing import Any

from ...encoding_utils import extract_text_slice, safe_encode
from ...utils import log_debug, log_error, log_warning
from ._extractor_helpers import (
    _PARAMETER_NODE_TYPES,
    TraversalRuntime,
    _extract_node_text_by_bytes,
    _extract_node_text_by_points,
    find_docstring_after_line,
    run_iterative_traversal,
)


class PythonExtractorCoreMixin:
    def _reset_caches(self) -> None:
        """Reset performance caches."""
        self._node_text_cache.clear()
        self._processed_nodes.clear()
        self._element_cache.clear()
        self._docstring_cache.clear()
        self._complexity_cache.clear()

    def _detect_file_characteristics(self) -> None:
        """Detect Python file characteristics."""
        self.is_module = "import " in self.source_code or "from " in self.source_code
        self.framework_type = ""

        if "django" in self.source_code or "from django" in self.source_code:
            self.framework_type = "django"
        elif "flask" in self.source_code or "from flask" in self.source_code:
            self.framework_type = "flask"
        elif "fastapi" in self.source_code or "from fastapi" in self.source_code:
            self.framework_type = "fastapi"

    def _traverse_and_extract_iterative(
        self,
        root_node: Any | None,
        extractors: dict[str, Any],
        results: list[Any],
        element_type: str,
    ) -> None:
        """Iterative node traversal and extraction with caching."""
        log_debug_fn, _, log_warning_fn = self._logging_hooks()
        run_iterative_traversal(
            root_node,
            TraversalRuntime(
                extractors=extractors,
                results=results,
                element_type=element_type,
                element_cache=self._element_cache,
                processed_node_ids=self._processed_nodes,
                log_debug_fn=log_debug_fn,
                log_warning_fn=log_warning_fn,
            ),
        )

    def _get_node_text_optimized(self, node: Any) -> str:
        """Get node text with optimized caching using position-based keys."""
        cache_key = (node.start_byte, node.end_byte)

        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]

        try:
            start_byte = node.start_byte
            end_byte = node.end_byte
            safe_encode_fn, extract_text_slice_fn = self._encoding_hooks()

            encoding = self._file_encoding or "utf-8"
            text = _extract_node_text_by_bytes(
                self.content_lines,
                encoding,
                start_byte,
                end_byte,
                safe_encode_fn=safe_encode_fn,
                extract_text_slice_fn=extract_text_slice_fn,
            )

            if text:
                self._node_text_cache[cache_key] = text
                return text
        except Exception as exc:
            log_error(f"Error in _get_node_text_optimized: {exc}")

        try:
            start_point = node.start_point
            end_point = node.end_point

            result = _extract_node_text_by_points(
                self.content_lines, start_point, end_point
            )
            self._node_text_cache[cache_key] = result
            return result
        except Exception as fallback_error:
            log_error(f"Fallback text extraction also failed: {fallback_error}")
            return ""

    def _encoding_hooks(self) -> tuple[Any, Any]:
        """Return encoding helpers from the public extractor module for patchability."""
        module = sys.modules.get(self.__class__.__module__)
        if module is None:
            return safe_encode, extract_text_slice
        return (
            getattr(module, "safe_encode", safe_encode),
            getattr(module, "extract_text_slice", extract_text_slice),
        )

    def _logging_hooks(self) -> tuple[Any, Any, Any]:
        """Return log helpers from the public extractor module for patchability."""
        module = sys.modules.get(self.__class__.__module__)
        if module is None:
            return log_debug, log_error, log_warning
        return (
            getattr(module, "log_debug", log_debug),
            getattr(module, "log_error", log_error),
            getattr(module, "log_warning", log_warning),
        )

    def _extract_parameters_from_node_optimized(self, params_node: Any) -> list[str]:
        """Extract function parameters with type hints."""
        parameters = []

        for child in params_node.children:
            if child.type in _PARAMETER_NODE_TYPES:
                parameters.append(self._get_node_text_optimized(child))

        return parameters

    def _extract_docstring_for_line(self, target_line: int) -> str | None:
        """Extract docstring for the specified line."""
        if target_line in self._docstring_cache:
            return self._docstring_cache[target_line]

        try:
            result = find_docstring_after_line(self.content_lines, target_line)
            if result.should_cache:
                self._docstring_cache[target_line] = result.cache_value
            return result.value

        except Exception as exc:
            log_debug(f"Failed to extract docstring: {exc}")
            return None

    def _calculate_complexity_optimized(self, node: Any) -> int:
        """Calculate cyclomatic complexity efficiently."""
        import re

        node_id = id(node)
        if node_id in self._complexity_cache:
            return self._complexity_cache[node_id]

        complexity = 1
        try:
            node_text = self._get_node_text_optimized(node).lower()
            keywords = [
                "if",
                "elif",
                "while",
                "for",
                "except",
                "and",
                "or",
                "with",
                "match",
                "case",
            ]
            for keyword in keywords:
                pattern = rf"\b{keyword}\b"
                matches = re.findall(pattern, node_text)
                complexity += len(matches)
        except Exception as exc:
            log_debug(f"Failed to calculate complexity: {exc}")

        self._complexity_cache[node_id] = complexity
        return complexity
