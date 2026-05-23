#!/usr/bin/env python3
"""
AST Path Navigator — Answer "what's at line X of file Y?"

Given a source file and a line number, walks the Tree-sitter AST to produce
the full scope path from the root to that line — enclosing module, class,
function, block, and the exact node at the line.

Also supports:
- scope_at: find the innermost enclosing named scope (function/class/method)
- siblings: list sibling declarations at the same scope level
- outline: return the full hierarchical outline of a file

CodeGraph parity: equivalent to CodeGraph's "go to definition context" and
"enclosing scope" queries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .core.parser import Parser
from .language_detector import LanguageDetector
from .utils import setup_logger

logger = setup_logger(__name__)

_NAMED_SCOPE_TYPES: dict[str, set[str]] = {
    "python": {
        "module",
        "class_definition",
        "function_definition",
        "decorated_definition",
    },
    "javascript": {
        "program",
        "class_declaration",
        "function_declaration",
        "method_definition",
        "arrow_function",
        "export_statement",
    },
    "typescript": {
        "program",
        "class_declaration",
        "function_declaration",
        "method_definition",
        "arrow_function",
        "export_statement",
        "interface_declaration",
        "type_alias_declaration",
        "enum_declaration",
        "namespace_declaration",
        "abstract_class_declaration",
    },
    "java": {
        "program",
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "method_declaration",
        "constructor_declaration",
        "record_declaration",
        "annotation_type_declaration",
    },
    "go": {
        "source_file",
        "function_declaration",
        "method_declaration",
        "type_declaration",
    },
    "c": {
        "translation_unit",
        "function_definition",
        "struct_specifier",
        "enum_specifier",
    },
    "cpp": {
        "translation_unit",
        "function_definition",
        "class_specifier",
        "struct_specifier",
        "namespace_definition",
        "enum_specifier",
        "template_declaration",
    },
}


@dataclass
class ASTNode:
    """A single node in the AST path."""

    type: str
    name: str | None
    start_line: int
    end_line: int
    is_named_scope: bool
    children_count: int
    field_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.type,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "is_scope": self.is_named_scope,
            "children_count": self.children_count,
        }
        if self.name is not None:
            d["name"] = self.name
        if self.field_name is not None:
            d["field"] = self.field_name
        return d


@dataclass
class ASTPathResult:
    """Full result of an AST path query."""

    file_path: str
    language: str
    target_line: int | None
    path: list[ASTNode] = field(default_factory=list)
    node_at_line: ASTNode | None = None
    enclosing_scope: ASTNode | None = None
    siblings: list[ASTNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "file": self.file_path,
            "language": self.language,
            "path": [n.to_dict() for n in self.path],
        }
        if self.target_line is not None:
            d["target_line"] = self.target_line
        if self.node_at_line is not None:
            d["node_at_line"] = self.node_at_line.to_dict()
        if self.enclosing_scope is not None:
            d["enclosing_scope"] = self.enclosing_scope.to_dict()
        if self.siblings:
            d["siblings"] = [s.to_dict() for s in self.siblings]
        return d


def _node_name(node: Any, source: str, language: str) -> str | None:
    """Extract a human-readable name from an AST node."""
    if not hasattr(node, "children"):
        return None
    for child in node.children:
        if child.type in (
            "identifier",
            "property_identifier",
            "type_identifier",
            "field_identifier",
        ):
            text = child.text
            return text.decode("utf-8") if isinstance(text, bytes) else str(text)
    if language == "python":
        for child in node.children:
            if child.type == "identifier":
                text = child.text
                return text.decode("utf-8") if isinstance(text, bytes) else str(text)
    if language in ("c", "cpp"):
        for child in node.children:
            if child.type == "function_declarator":
                for sub in child.children:
                    if sub.type in ("identifier", "field_identifier"):
                        text = sub.text
                        return (
                            text.decode("utf-8")
                            if isinstance(text, bytes)
                            else str(text)
                        )
            if child.type == "identifier":
                text = child.text
                return text.decode("utf-8") if isinstance(text, bytes) else str(text)
    return None


def _is_named_scope(node_type: str, language: str) -> bool:
    """Check if a node type represents a named scope."""
    return node_type in _NAMED_SCOPE_TYPES.get(language, set())


def _build_ast_node(
    node: Any, source: str, language: str, field_name: str | None = None
) -> ASTNode:
    """Build an ASTNode from a tree-sitter node."""
    return ASTNode(
        type=node.type,
        name=_node_name(node, source, language),
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        is_named_scope=_is_named_scope(node.type, language),
        children_count=node.child_count,
        field_name=field_name,
    )


class ASTPathNavigator:
    """
    Navigate the AST of a source file to answer scope/path queries.

    Usage::

        nav = ASTPathNavigator()
        result = nav.path_at_line("src/main.py", 42)
        # result.path → [module, class Foo, method bar, ...]
    """

    def __init__(self) -> None:
        self._parser = Parser()
        self._detector = LanguageDetector()

    def _parse(
        self, file_path: str, language: str | None = None
    ) -> tuple[Any, str, str]:
        """Parse file and return (tree, source, language)."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if language is None:
            detected = self._detector.detect_language(str(path))
            language = detected[0] if detected else None
            if not language or language == "unknown":
                raise ValueError(f"Cannot detect language for {file_path}")
        result = self._parser.parse_file(str(path), language)
        if not result.success or result.tree is None:
            raise ValueError(f"Parse failed for {file_path}: {result.error_message}")
        return result.tree, result.source_code, language

    def path_at_line(
        self,
        file_path: str,
        line: int,
        language: str | None = None,
    ) -> ASTPathResult:
        """
        Find the full AST path from root to the node at the given line.

        Returns the chain of enclosing scopes + the exact leaf node at that line.
        """
        tree, source, lang = self._parse(file_path, language)
        root = tree.root_node

        path_nodes: list[ASTNode] = []
        leaf_node: ASTNode | None = None

        def _walk(node: Any, field_name: str | None = None) -> bool:
            if not hasattr(node, "start_point"):
                return False
            start = node.start_point[0] + 1
            end = node.end_point[0] + 1
            if line < start or line > end:
                return False

            ast_node = _build_ast_node(node, source, lang, field_name)
            path_nodes.append(ast_node)

            if hasattr(node, "children"):
                found = False
                for i, child in enumerate(node.children):
                    cf = None
                    if hasattr(node, "field_name_for_child"):
                        try:
                            cf = node.field_name_for_child(i)
                        except Exception:  # nosec B110
                            pass
                    if _walk(child, cf):
                        found = True
                        break

                if not found:
                    nonlocal leaf_node
                    leaf_node = ast_node

            return True

        _walk(root)

        enclosing = None
        for n in reversed(path_nodes):
            if n.is_named_scope and n.name:
                enclosing = n
                break

        return ASTPathResult(
            file_path=file_path,
            language=lang,
            target_line=line,
            path=path_nodes,
            node_at_line=leaf_node,
            enclosing_scope=enclosing,
        )

    def scope_at(
        self,
        file_path: str,
        line: int,
        language: str | None = None,
    ) -> ASTPathResult:
        """
        Find the innermost named scope enclosing the given line.

        Like path_at_line but stops at the innermost function/class/method.
        """
        result = self.path_at_line(file_path, line, language)
        if result.enclosing_scope:
            result.siblings = self._get_siblings(
                file_path, result.enclosing_scope, result.language, source=None
            )
        return result

    def outline(
        self,
        file_path: str,
        language: str | None = None,
        max_depth: int = 3,
    ) -> ASTPathResult:
        """
        Return the hierarchical outline of a file (top-level declarations).

        Walks the AST up to max_depth collecting named scopes.
        """
        tree, source, lang = self._parse(file_path, language)
        root = tree.root_node
        items: list[ASTNode] = []

        def _collect(node: Any, depth: int) -> None:
            if depth > max_depth:
                return
            if not hasattr(node, "children"):
                return
            for child in node.children:
                if _is_named_scope(child.type, lang):
                    ast_node = _build_ast_node(child, source, lang)
                    if ast_node.name:
                        items.append(ast_node)
                    _collect(child, depth + 1)
                elif depth == 0:
                    _collect(child, depth + 1)

        _collect(root, 0)

        return ASTPathResult(
            file_path=file_path,
            language=lang,
            target_line=None,
            path=items,
        )

    def _get_siblings(
        self,
        file_path: str,
        scope_node: ASTNode,
        language: str,
        source: str | None = None,
    ) -> list[ASTNode]:
        """Get sibling declarations at the same scope level."""
        if source is None:
            _, src, _ = self._parse(file_path, language)
            source = src

        tree, _, _ = self._parse(file_path, language)
        root = tree.root_node
        siblings: list[ASTNode] = []

        def _find_and_collect(node: Any, depth: int = 0) -> bool:
            if not hasattr(node, "start_point"):
                return False
            start = node.start_point[0] + 1
            end = node.end_point[0] + 1
            if start == scope_node.start_line and end == scope_node.end_line:
                parent = node.parent
                if parent and hasattr(parent, "children"):
                    for child in parent.children:
                        if _is_named_scope(child.type, language):
                            sib = _build_ast_node(child, source, language)
                            if sib.name and not (
                                sib.start_line == scope_node.start_line
                                and sib.end_line == scope_node.end_line
                            ):
                                siblings.append(sib)
                return True
            if hasattr(node, "children"):
                for child in node.children:
                    if _find_and_collect(child, depth + 1):
                        return True
            return False

        _find_and_collect(root)
        return siblings
