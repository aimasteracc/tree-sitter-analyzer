"""Import and export extraction methods for the JavaScript extractor."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ...models import Import
from ...utils import log_debug
from ._export_helpers import extract_commonjs_exports, parse_export_statement
from ._import_helpers import (
    extract_commonjs_requires,
    extract_import_names,
    parse_import_statement,
)

if TYPE_CHECKING:
    import tree_sitter


class JavaScriptImportExportMixin:
    """Import/export-specific extraction methods."""

    # Extract elements from AST: _extract_import_info_simple
    def _extract_import_info_simple(self, node: tree_sitter.Node) -> Import | None:
        """Extract import information from import_statement node."""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            source_bytes = self.source_code.encode("utf-8")
            raw_text = source_bytes[node.start_byte : node.end_byte].decode("utf-8")

            import_names: list[str] = []
            module_path = ""
            for child in node.children:
                if child.type == "import_clause":
                    import_names.extend(self._extract_import_names(child))
                elif child.type == "string":
                    module_text = source_bytes[
                        child.start_byte : child.end_byte
                    ].decode("utf-8")
                    module_path = module_text.strip("\"'")

            primary_name = import_names[0] if import_names else "unknown"
            return Import(
                name=primary_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="javascript",
                module_path=module_path,
                module_name=module_path,
                imported_names=import_names,
            )
        except Exception as e:
            log_debug(f"Failed to extract import info: {e}")
            return None

    # Extract elements from AST: _extract_import_names
    def _extract_import_names(self, import_clause_node: tree_sitter.Node) -> list[str]:
        """Extract import names from import clause."""
        return extract_import_names(import_clause_node, self.source_code)

    # Extract elements from AST: _extract_import_info_enhanced
    def _extract_import_info_enhanced(
        self, node: tree_sitter.Node, source_code: str
    ) -> Import | None:
        """Extract enhanced import information."""
        try:
            import_text = self._get_node_text_optimized(node)
            import_info = self._parse_import_statement(import_text)
            if not import_info:
                return None

            _import_type, names, source, _is_default, _is_namespace = import_info
            return Import(
                name=names[0] if names else "unknown",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=import_text,
                language="javascript",
                module_path=source,
                module_name=source,
                imported_names=names,
            )
        except Exception as e:
            log_debug(f"Failed to extract import info: {e}")
            return None

    # Extract elements from AST: _extract_dynamic_import
    def _extract_dynamic_import(self, node: tree_sitter.Node) -> Import | None:
        """Extract dynamic import() calls."""
        try:
            node_text = self._get_node_text_optimized(node)
            import_match = re.search(
                r"import\s*\(\s*[\"']([^\"']+)[\"']\s*\)",
                node_text,
            )
            if not import_match:
                return None

            source = import_match.group(1)
            return Import(
                name="dynamic_import",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=node_text,
                language="javascript",
                module_path=source,
                module_name=source,
                imported_names=["dynamic_import"],
            )
        except Exception as e:
            log_debug(f"Failed to extract dynamic import: {e}")
            return None

    # Extract elements from AST: _extract_commonjs_requires
    def _extract_commonjs_requires(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Import]:
        """Extract CommonJS require() statements."""
        return extract_commonjs_requires(source_code)

    # Extract elements from AST: _extract_export_info
    def _extract_export_info(self, node: tree_sitter.Node) -> dict[str, Any] | None:
        """Extract export information."""
        try:
            export_text = self._get_node_text_optimized(node)
            export_info = self._parse_export_statement(export_text)
            if not export_info:
                return None

            export_type, names, is_default = export_info
            return {
                "type": export_type,
                "names": names,
                "is_default": is_default,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "raw_text": export_text,
            }
        except Exception as e:
            log_debug(f"Failed to extract export info: {e}")
            return None

    # Extract elements from AST: _extract_commonjs_exports
    def _extract_commonjs_exports(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[dict[str, Any]]:
        """Extract CommonJS module.exports statements."""
        return extract_commonjs_exports(source_code)

    # Parse input into structured data: _parse_import_statement
    def _parse_import_statement(
        self, import_text: str
    ) -> tuple[str, list[str], str, bool, bool] | None:
        """Parse import statement to extract details."""
        return parse_import_statement(import_text)

    # Parse input into structured data: _parse_export_statement
    def _parse_export_statement(
        self, export_text: str
    ) -> tuple[str, list[str], bool] | None:
        """Parse export statement to extract details."""
        return parse_export_statement(export_text)
