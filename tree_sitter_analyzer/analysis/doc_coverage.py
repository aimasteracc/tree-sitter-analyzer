#!/usr/bin/env python3
"""
Documentation Coverage Analyzer.

Detects which functions, classes, and methods lack documentation.
Supports Python docstrings, JSDoc, JavaDoc, and Go doc comments.

Outputs coverage statistics and lists of undocumented elements.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter

from tree_sitter_analyzer.utils import setup_logger

if TYPE_CHECKING:
    pass

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

_LANGUAGE_MODULES: dict[str, str] = {
    ".py": "tree_sitter_python",
    ".js": "tree_sitter_javascript",
    ".ts": "tree_sitter_typescript",
    ".tsx": "tree_sitter_typescript",
    ".jsx": "tree_sitter_javascript",
    ".java": "tree_sitter_java",
    ".go": "tree_sitter_go",
}

_LANGUAGE_FUNCS: dict[str, str] = {
    ".ts": "language_typescript",
    ".tsx": "language_tsx",
}


@dataclass(frozen=True)
class DocElement:
    """A code element that may or may not have documentation."""

    name: str
    element_type: str  # function, class, method, interface, type, module
    file_path: str
    line_number: int
    has_doc: bool
    doc_content: str | None = None


@dataclass(frozen=True)
class DocCoverageResult:
    """Result of documentation coverage analysis."""

    elements: tuple[DocElement, ...]
    total_elements: int
    documented_count: int
    coverage_percent: float

    def get_missing_docs(self) -> list[DocElement]:
        return [e for e in self.elements if not e.has_doc]


class DocCoverageAnalyzer:
    """Analyzes documentation coverage across source files."""

    def __init__(self) -> None:
        self._languages: dict[str, tree_sitter.Language] = {}
        self._parsers: dict[str, tree_sitter.Parser] = {}

    def _get_parser(
        self, extension: str
    ) -> tuple[tree_sitter.Language | None, tree_sitter.Parser | None]:
        if extension not in _LANGUAGE_MODULES:
            return None, None
        if extension not in self._parsers:
            module_name = _LANGUAGE_MODULES[extension]
            try:
                lang_module = __import__(module_name)
                func_name = _LANGUAGE_FUNCS.get(extension, "language")
                language_func = getattr(lang_module, func_name)
                language = tree_sitter.Language(language_func())
                self._languages[extension] = language
                parser = tree_sitter.Parser(language)
                self._parsers[extension] = parser
            except Exception as e:
                logger.error(f"Failed to load language for {extension}: {e}")
                return None, None
        return self._languages.get(extension), self._parsers.get(extension)

    def analyze_file(self, file_path: Path | str) -> DocCoverageResult:
        path = Path(file_path)
        if not path.exists():
            return DocCoverageResult(
                elements=(), total_elements=0, documented_count=0, coverage_percent=100.0
            )

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return DocCoverageResult(
                elements=(), total_elements=0, documented_count=0, coverage_percent=100.0
            )

        elements = self._extract_elements(path, ext)
        total = len(elements)
        documented = sum(1 for e in elements if e.has_doc)
        pct = (documented / total * 100.0) if total > 0 else 100.0

        return DocCoverageResult(
            elements=tuple(elements),
            total_elements=total,
            documented_count=documented,
            coverage_percent=round(pct, 2),
        )

    def analyze_directory(self, dir_path: Path | str) -> DocCoverageResult:
        path = Path(dir_path)
        all_elements: list[DocElement] = []

        for ext in SUPPORTED_EXTENSIONS:
            for fp in path.rglob(f"*{ext}"):
                if ".git" in fp.parts or "node_modules" in fp.parts:
                    continue
                result = self.analyze_file(fp)
                all_elements.extend(result.elements)

        total = len(all_elements)
        documented = sum(1 for e in all_elements if e.has_doc)
        pct = (documented / total * 100.0) if total > 0 else 100.0

        return DocCoverageResult(
            elements=tuple(all_elements),
            total_elements=total,
            documented_count=documented,
            coverage_percent=round(pct, 2),
        )

    def _extract_elements(self, path: Path, ext: str) -> list[DocElement]:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return []

        content = path.read_bytes()
        tree = parser.parse(content)

        if ext == ".py":
            return self._extract_python(tree.root_node, content, str(path))
        if ext in {".js", ".ts", ".tsx", ".jsx"}:
            return self._extract_js(tree.root_node, content, str(path))
        if ext == ".java":
            return self._extract_java(tree.root_node, content, str(path))
        if ext == ".go":
            return self._extract_go(tree.root_node, content, str(path))
        return []

    def _extract_python(self, root: tree_sitter.Node, content: bytes, file_path: str) -> list[DocElement]:
        elements: list[DocElement] = []
        module_doc = self._get_python_module_doc(root, content)
        elements.append(
            DocElement(
                name=Path(file_path).stem,
                element_type="module",
                file_path=file_path,
                line_number=1,
                has_doc=module_doc is not None,
                doc_content=module_doc,
            )
        )

        # Walk for functions, classes
        self._walk_python_node(root, content, file_path, elements)
        return elements

    def _get_python_module_doc(self, root: tree_sitter.Node, content: bytes) -> str | None:
        for child in root.children:
            if child.type == "expression_statement":
                first = child.child_by_field_name("value") or (
                    child.children[0] if child.children else None
                )
                if first and first.type == "string":
                    return content[first.start_byte:first.end_byte].decode("utf-8", errors="replace")
            if child.type in {"function_definition", "class_definition", "decorated_definition"}:
                break
        return None

    def _walk_python_node(
        self,
        node: tree_sitter.Node,
        content: bytes,
        file_path: str,
        elements: list[DocElement],
        parent_class: bool = False,
    ) -> None:
        if node.type == "decorated_definition":
            for child in node.children:
                if child.type in {"function_definition", "class_definition"}:
                    self._walk_python_node(child, content, file_path, elements, parent_class)
            return

        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                has_doc, doc_text = self._check_python_docstring(node, content)
                elements.append(
                    DocElement(
                        name=name,
                        element_type="method" if parent_class else "function",
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        has_doc=has_doc,
                        doc_content=doc_text,
                    )
                )

        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                has_doc, doc_text = self._check_python_docstring(node, content)
                elements.append(
                    DocElement(
                        name=name,
                        element_type="class",
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        has_doc=has_doc,
                        doc_content=doc_text,
                    )
                )
            for child in node.children:
                if child.type == "block":
                    self._walk_python_node(child, content, file_path, elements, parent_class=True)
                else:
                    self._walk_python_node(child, content, file_path, elements, parent_class)
            return

        for child in node.children:
            self._walk_python_node(child, content, file_path, elements, parent_class)

    def _check_python_docstring(
        self, node: tree_sitter.Node, content: bytes
    ) -> tuple[bool, str | None]:
        body = node.child_by_field_name("body")
        if not body or not body.children:
            return False, None
        first = body.children[0]
        if first.type == "expression_statement":
            val = first.child_by_field_name("value") or (
                first.children[0] if first.children else None
            )
            if val and val.type == "string":
                text = content[val.start_byte:val.end_byte].decode("utf-8", errors="replace")
                return True, text
        return False, None

    def _extract_js(self, root: tree_sitter.Node, content: bytes, file_path: str) -> list[DocElement]:
        elements: list[DocElement] = []
        self._walk_js_node(root, content, file_path, elements)
        return elements

    def _walk_js_node(
        self,
        node: tree_sitter.Node,
        content: bytes,
        file_path: str,
        elements: list[DocElement],
    ) -> None:
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                has_doc, doc_text = self._check_preceding_jsdoc(node, content)
                elements.append(
                    DocElement(
                        name=name,
                        element_type="function",
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        has_doc=has_doc,
                        doc_content=doc_text,
                    )
                )

        elif node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                has_doc, doc_text = self._check_preceding_jsdoc(node, content)
                elements.append(
                    DocElement(
                        name=name,
                        element_type="class",
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        has_doc=has_doc,
                        doc_content=doc_text,
                    )
                )

        elif node.type == "method_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                has_doc, doc_text = self._check_preceding_jsdoc(node, content)
                elements.append(
                    DocElement(
                        name=name,
                        element_type="method",
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        has_doc=has_doc,
                        doc_content=doc_text,
                    )
                )

        for child in node.children:
            self._walk_js_node(child, content, file_path, elements)

    def _check_preceding_jsdoc(
        self, node: tree_sitter.Node, content: bytes
    ) -> tuple[bool, str | None]:
        sibling = node.prev_named_sibling
        if sibling and sibling.type in {"comment", "document_comment"}:
            text = content[sibling.start_byte:sibling.end_byte].decode("utf-8", errors="replace")
            if "/**" in text or "*/" in text:
                return True, text
        return False, None

    def _extract_java(self, root: tree_sitter.Node, content: bytes, file_path: str) -> list[DocElement]:
        elements: list[DocElement] = []
        self._walk_java_node(root, content, file_path, elements)
        return elements

    def _walk_java_node(
        self,
        node: tree_sitter.Node,
        content: bytes,
        file_path: str,
        elements: list[DocElement],
    ) -> None:
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                has_doc, doc_text = self._check_preceding_javadoc(node, content)
                elements.append(
                    DocElement(
                        name=name,
                        element_type="class",
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        has_doc=has_doc,
                        doc_content=doc_text,
                    )
                )

        elif node.type == "interface_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                has_doc, doc_text = self._check_preceding_javadoc(node, content)
                elements.append(
                    DocElement(
                        name=name,
                        element_type="interface",
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        has_doc=has_doc,
                        doc_content=doc_text,
                    )
                )

        elif node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                has_doc, doc_text = self._check_preceding_javadoc(node, content)
                elements.append(
                    DocElement(
                        name=name,
                        element_type="method",
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        has_doc=has_doc,
                        doc_content=doc_text,
                    )
                )

        for child in node.children:
            self._walk_java_node(child, content, file_path, elements)

    def _check_preceding_javadoc(
        self, node: tree_sitter.Node, content: bytes
    ) -> tuple[bool, str | None]:
        sibling = node.prev_named_sibling
        if sibling and sibling.type == "block_comment":
            text = content[sibling.start_byte:sibling.end_byte].decode("utf-8", errors="replace")
            if text.startswith("/*"):
                return True, text
        return False, None

    def _extract_go(self, root: tree_sitter.Node, content: bytes, file_path: str) -> list[DocElement]:
        elements: list[DocElement] = []
        self._walk_go_node(root, content, file_path, elements)
        return elements

    def _walk_go_node(
        self,
        node: tree_sitter.Node,
        content: bytes,
        file_path: str,
        elements: list[DocElement],
    ) -> None:
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                has_doc, doc_text = self._check_preceding_go_comment(node, content)
                elements.append(
                    DocElement(
                        name=name,
                        element_type="function",
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        has_doc=has_doc,
                        doc_content=doc_text,
                    )
                )

        elif node.type == "type_declaration":
            for child in node.children:
                if child.type == "type_spec":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        name = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                        has_doc, doc_text = self._check_preceding_go_comment(node, content)
                        elements.append(
                            DocElement(
                                name=name,
                                element_type="type",
                                file_path=file_path,
                                line_number=node.start_point[0] + 1,
                                has_doc=has_doc,
                                doc_content=doc_text,
                            )
                        )

        for child in node.children:
            self._walk_go_node(child, content, file_path, elements)

    def _check_preceding_go_comment(
        self, node: tree_sitter.Node, content: bytes
    ) -> tuple[bool, str | None]:
        sibling = node.prev_named_sibling
        if sibling and sibling.type == "comment":
            text = content[sibling.start_byte:sibling.end_byte].decode("utf-8", errors="replace")
            if text.startswith("//"):
                return True, text
        return False, None
