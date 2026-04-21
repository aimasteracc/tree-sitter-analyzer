"""typescript_plugin mixin — functions."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

from ...models import (
    Function,
)
from ...utils import log_debug, log_error
from ._base import _TypeScriptElementBase


class FunctionsMixin(_TypeScriptElementBase):

    def _extract_function_optimized(self, node: tree_sitter.Node) -> Function | None:
        """Extract regular function information with detailed metadata"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract function details
            function_info = self._parse_function_signature_optimized(node)
            if not function_info:
                return None

            name, parameters, is_async, is_generator, return_type, generics = (
                function_info
            )

            # Skip if no name found
            if name is None:
                return None

            # Extract TSDoc
            tsdoc = self._extract_tsdoc_for_line(start_line)

            # Calculate complexity
            complexity_score = self._calculate_complexity_optimized(node)

            # Extract raw text
            start_line_idx = max(0, start_line - 1)
            end_line_idx = min(len(self.content_lines), end_line)
            raw_text = "\n".join(self.content_lines[start_line_idx:end_line_idx])

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="typescript",
                parameters=parameters,
                return_type=return_type or "any",
                is_async=is_async,
                is_generator=is_generator,
                docstring=tsdoc,
                complexity_score=complexity_score,
                # TypeScript-specific properties
                is_arrow=False,
                is_method=False,
                framework_type=self.framework_type,
                node_type=node.type,
            )
        except Exception as e:
            log_error(f"Failed to extract function info: {e}")
            import traceback

            traceback.print_exc()
            return None

    def _extract_function_signature_optimized(
        self, node: tree_sitter.Node
    ) -> Function | None:
        """Extract function signature (overload declaration without body)"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract function signature details (similar to method signature)
            function_info = self._parse_function_signature_optimized(node)
            if not function_info:
                return None

            name, parameters, is_async, _, return_type, generics = function_info

            # Skip if no name found
            if name is None:
                return None

            # Extract TSDoc
            tsdoc = self._extract_tsdoc_for_line(start_line)

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="typescript",
                parameters=parameters,
                return_type=return_type or "any",
                is_async=is_async,
                docstring=tsdoc,
                complexity_score=0,  # Signatures have no complexity
                # TypeScript-specific properties
                is_arrow=False,
                is_method=False,
                framework_type=self.framework_type,
                node_type="function_signature",
            )
        except Exception as e:
            log_debug(f"Failed to extract function signature info: {e}")
            return None
