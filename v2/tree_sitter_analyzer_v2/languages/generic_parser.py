"""
Generic language parser driven by LanguageProfile data.

Instead of writing a 300-700 LOC parser for each language, this module
provides a single GenericLanguageParser that uses a LanguageProfile to
extract functions, classes, and imports from any tree-sitter supported language.

Usage:
    from tree_sitter_analyzer_v2.languages.profiles import GO_PROFILE
    parser = GenericLanguageParser(GO_PROFILE)
    result = parser.parse(source_code, "main.go")
"""

from __future__ import annotations

import logging
from typing import Any

from tree_sitter_analyzer_v2.core.parser import TreeSitterParser
from tree_sitter_analyzer_v2.core.types import ASTNode, LanguageParseResult, LanguageProfile

logger = logging.getLogger(__name__)


class GenericLanguageParser:
    """Language-agnostic parser driven by a LanguageProfile configuration."""

    def __init__(self, profile: LanguageProfile) -> None:
        self._profile = profile
        self._parser = TreeSitterParser(profile.tree_sitter_name)

    @property
    def profile(self) -> LanguageProfile:
        """Return the language profile."""
        return self._profile

    def parse(self, source_code: str, file_path: str = "") -> LanguageParseResult:
        """Parse source code using the language profile.

        Args:
            source_code: Source code to parse.
            file_path: Optional file path for metadata.

        Returns:
            LanguageParseResult with functions, classes, imports, metadata.
        """
        parse_result = self._parser.parse(source_code, file_path)
        root = parse_result.tree

        functions: list[dict[str, Any]] = []
        classes: list[dict[str, Any]] = []
        imports: list[dict[str, Any]] = []
        package: str = ""

        if root is not None:
            self._walk(root, functions, classes, imports, source_code)
            if self._profile.has_packages and self._profile.package_node_type:
                package = self._extract_package(root)

        lines = source_code.splitlines()
        result: dict[str, Any] = {
            "ast": root,
            "functions": functions,
            "classes": classes,
            "imports": imports,
            "metadata": {
                "total_functions": len(functions),
                "total_classes": len(classes),
                "total_imports": len(imports),
                "total_lines": len(lines),
            },
            "errors": parse_result.has_errors,
        }
        if package:
            result["metadata"]["package"] = package

        return result  # type: ignore[return-value]

    # ── AST traversal ──

    def _walk(
        self,
        node: ASTNode,
        functions: list[dict[str, Any]],
        classes: list[dict[str, Any]],
        imports: list[dict[str, Any]],
        source_code: str,
    ) -> None:
        """Walk AST and extract elements based on profile node types."""
        p = self._profile

        if node.type in p.function_node_types:
            func = self._extract_function(node, source_code)
            if func:
                functions.append(func)
            return  # don't recurse into function body for top-level

        # Top-level methods (e.g., Go receiver methods)
        if node.type in p.method_node_types and node.type not in p.function_node_types:
            func = self._extract_function(node, source_code)
            if func:
                functions.append(func)
            return

        if node.type in p.class_node_types:
            cls = self._extract_class(node, source_code)
            if cls:
                classes.append(cls)
            return

        if node.type in p.import_node_types:
            imp = self._extract_import(node)
            if imp:
                imports.append(imp)
            return

        if node.type in p.interface_node_types:
            iface = self._extract_interface(node, source_code)
            if iface:
                classes.append(iface)
            return

        for child in node.children:
            self._walk(child, functions, classes, imports, source_code)

    # ── Function extraction ──

    def _extract_function(self, node: ASTNode, source_code: str) -> dict[str, Any] | None:
        """Extract function information from an AST node."""
        name = self._find_child_text(node, self._profile.name_field)
        if not name:
            name = self._find_identifier_text(node)
        if not name:
            return None

        params = self._extract_params_from_node(node)
        return_type = self._find_child_text(node, self._profile.return_type_field) or ""
        visibility = self._detect_visibility(node, name)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        return {
            "name": name,
            "start_line": start_line,
            "end_line": end_line,
            "visibility": visibility,
            "parameters": params,
            "return_type": return_type,
            "is_async": self._is_async(node),
        }

    # ── Class extraction ──

    def _extract_class(self, node: ASTNode, source_code: str) -> dict[str, Any] | None:
        """Extract class/struct/type information from an AST node."""
        name = self._find_child_text(node, self._profile.name_field)
        if not name:
            name = self._find_type_identifier(node)
        if not name:
            return None

        methods: list[dict[str, Any]] = []
        self._extract_methods_from_body(node, methods, source_code)

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        visibility = self._detect_visibility(node, name)

        return {
            "name": name,
            "start_line": start_line,
            "end_line": end_line,
            "visibility": visibility,
            "methods": methods,
        }

    def _extract_interface(self, node: ASTNode, source_code: str) -> dict[str, Any] | None:
        """Extract interface/trait information."""
        info = self._extract_class(node, source_code)
        if info:
            info["is_interface"] = True
        return info

    def _extract_methods_from_body(
        self, node: ASTNode, methods: list[dict[str, Any]], source_code: str
    ) -> None:
        """Recursively find method declarations inside a class/struct body."""
        p = self._profile
        for child in node.children:
            if child.type in p.method_node_types or child.type in p.function_node_types:
                method = self._extract_function(child, source_code)
                if method:
                    methods.append(method)
            else:
                self._extract_methods_from_body(child, methods, source_code)

    # ── Import extraction ──

    def _extract_import(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract import information from an AST node."""
        # Try to get the full text of the import
        text = node.text or ""
        if not text:
            return None

        # Clean up the import text
        text = text.strip().rstrip(";")

        return {
            "module": text,
            "line": node.start_point[0] + 1,
        }

    # ── Package extraction ──

    def _extract_package(self, root: ASTNode) -> str:
        """Extract package declaration from root."""
        pkg_type = self._profile.package_node_type
        for child in root.children:
            if child.type == pkg_type:
                name = self._find_child_text(child, self._profile.name_field)
                if name:
                    return name
                # Fallback: get text and clean
                if child.text:
                    return child.text.strip().split()[-1].rstrip(";")
        return ""

    # ── Parameter extraction ──

    def _extract_params_from_node(self, func_node: ASTNode) -> list[dict[str, Any]]:
        """Extract parameters from a function node, searching all param-like children."""
        params: list[dict[str, Any]] = []

        # Collect all parameter_list / parameters children
        param_nodes: list[ASTNode] = []
        for child in func_node.children:
            if child.type in (self._profile.params_field, "parameter_list",
                              "formal_parameters", "parameters"):
                param_nodes.append(child)
            # C/C++: params inside function_declarator
            if child.type in ("function_declarator",):
                for sub in child.children:
                    if sub.type in ("parameter_list", "formal_parameters", "parameters"):
                        param_nodes.append(sub)

        # For Go methods, skip receiver (first parameter_list) and use second
        if self._profile.name == "go" and len(param_nodes) >= 2:
            param_nodes = param_nodes[1:]  # skip receiver

        for params_node in param_nodes[:1]:  # only process first params list
            for child in params_node.children:
                if child.type in ("parameter_declaration", "parameter", "formal_parameter",
                                  "required_parameter", "optional_parameter"):
                    name = self._find_identifier_text(child)
                    if name:
                        type_text = self._find_type_text(child)
                        param: dict[str, Any] = {"name": name}
                        if type_text:
                            param["type"] = type_text
                        params.append(param)

        return params

    # ── Visibility detection ──

    def _detect_visibility(self, node: ASTNode, name: str) -> str:
        """Detect visibility of a symbol based on profile rules."""
        p = self._profile

        # Check for explicit visibility modifier in node
        if p.visibility_node_type:
            vis = self._find_child_text(node, p.visibility_node_type)
            if vis:
                return vis.lower()

        # Check for visibility keywords in node text
        if node.text and p.public_keywords:
            node_text_lower = node.text.lower()
            for kw in p.public_keywords:
                if kw.lower() in node_text_lower:
                    return "public"

        # Language-specific: Go uses capitalization for visibility
        if p.name == "go" and name:
            return "public" if name[0].isupper() else "private"

        # Language-specific: Rust uses 'pub' keyword
        if p.name == "rust":
            for child in node.children:
                if child.type == "visibility_modifier":
                    return "public"
            return "private"

        return p.default_visibility

    # ── Async detection ──

    def _is_async(self, node: ASTNode) -> bool:
        """Check if a function is async."""
        if not self._profile.has_async:
            return False
        if node.text and self._profile.async_keyword in (node.text or ""):
            return True
        return False

    # ── AST utility methods ──

    def _find_child_text(self, node: ASTNode, field_type: str) -> str:
        """Find a named child and return its text."""
        for child in node.children:
            if child.type == field_type:
                return child.text or ""
        return ""

    def _find_child_by_type(self, node: ASTNode, node_type: str) -> ASTNode | None:
        """Find a child node by type."""
        for child in node.children:
            if child.type == node_type:
                return child
        return None

    def _find_identifier_text(self, node: ASTNode) -> str:
        """Find the first identifier child and return its text."""
        for child in node.children:
            if child.type in ("identifier", "type_identifier", "name", "field_identifier"):
                return child.text or ""
            # C/C++: function_declarator wraps the identifier
            if child.type in ("function_declarator", "pointer_declarator"):
                inner = self._find_identifier_text(child)
                if inner:
                    return inner
        return ""

    def _find_type_identifier(self, node: ASTNode) -> str:
        """Find a type_identifier in node children (for Go type declarations)."""
        for child in node.children:
            if child.type == "type_identifier":
                return child.text or ""
            if child.type == "type_spec":
                return self._find_type_identifier(child)
        return self._find_identifier_text(node)

    def _find_type_text(self, node: ASTNode) -> str:
        """Find type annotation text in a parameter."""
        for child in node.children:
            if child.type in ("type_identifier", "primitive_type", "generic_type",
                              "pointer_type", "slice_type", "array_type",
                              "qualified_type", "reference_type"):
                return child.text or ""
        return ""
