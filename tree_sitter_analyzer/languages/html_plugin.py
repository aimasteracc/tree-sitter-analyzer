#!/usr/bin/env python3
"""
HTML Language Plugin

True HTML parser using tree-sitter-html for comprehensive HTML analysis.
Provides HTML-specific analysis capabilities including element extraction,
attribute parsing, and document structure analysis.
"""

import logging
from typing import TYPE_CHECKING, Any

from ..models import AnalysisResult, MarkupElement
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error, log_info
from .html_helpers import (
    classify_element as _classify_standalone,
)
from .html_helpers import (
    create_markup_element as _create_markup_standalone,
)

if TYPE_CHECKING:
    import tree_sitter

    from ..core.request import AnalysisRequest

logger = logging.getLogger(__name__)


def _html_error_result(file_path: str, exc: Exception) -> AnalysisResult:
    """Build the canonical failure ``AnalysisResult`` for HTML parse errors."""
    return AnalysisResult(
        file_path=file_path,
        language="html",
        line_count=0,
        elements=[],
        node_count=0,
        query_results={},
        source_code="",
        success=False,
        error_message=str(exc),
    )


def _analyze_html_fallback(file_path: str, content: str) -> AnalysisResult:
    """Best-effort fallback when ``tree-sitter-html`` is not installed.

    Emits a single synthetic ``html`` MarkupElement spanning the whole
    document so downstream tooling sees *something* instead of an empty
    elements list. Truncates raw text to 200 chars for the FTS row.
    """
    lines = content.splitlines()
    line_count = len(lines)
    html_element = MarkupElement(
        name="html",
        start_line=1,
        end_line=line_count,
        raw_text=content[:200] + "..." if len(content) > 200 else content,
        language="html",
        tag_name="html",
        attributes={},
        parent=None,
        children=[],
        element_class="structure",
    )
    return AnalysisResult(
        file_path=file_path,
        language="html",
        line_count=line_count,
        elements=[html_element],
        node_count=1,
        query_results={},
        source_code=content,
        success=True,
        error_message=None,
    )


class HtmlElementExtractor(ElementExtractor):
    """HTML-specific element extractor using tree-sitter-html"""

    def __init__(self) -> None:
        self.element_categories = {
            # HTML要素の分類システム
            "structure": [
                "html",
                "body",
                "div",
                "span",
                "section",
                "article",
                "aside",
                "nav",
                "main",
                "header",
                "footer",
            ],
            "heading": ["h1", "h2", "h3", "h4", "h5", "h6"],
            "text": [
                "p",
                "a",
                "strong",
                "em",
                "b",
                "i",
                "u",
                "small",
                "mark",
                "del",
                "ins",
                "sub",
                "sup",
            ],
            "list": ["ul", "ol", "li", "dl", "dt", "dd"],
            "media": [
                "img",
                "video",
                "audio",
                "source",
                "track",
                "canvas",
                "svg",
                "picture",
            ],
            "form": [
                "form",
                "input",
                "textarea",
                "button",
                "select",
                "option",
                "optgroup",
                "label",
                "fieldset",
                "legend",
            ],
            "table": [
                "table",
                "thead",
                "tbody",
                "tfoot",
                "tr",
                "td",
                "th",
                "caption",
                "colgroup",
                "col",
            ],
            "metadata": [
                "head",
                "title",
                "meta",
                "link",
                "style",
                "script",
                "noscript",
                "base",
            ],
        }

    def extract_functions(self, tree: "tree_sitter.Tree", source_code: str) -> list:
        """HTML doesn't have functions, return empty list"""
        return []

    def extract_classes(self, tree: "tree_sitter.Tree", source_code: str) -> list:
        """HTML doesn't have classes in the traditional sense, return empty list"""
        return []

    def extract_variables(self, tree: "tree_sitter.Tree", source_code: str) -> list:
        """HTML doesn't have variables, return empty list"""
        return []

    def extract_imports(self, tree: "tree_sitter.Tree", source_code: str) -> list:
        """HTML doesn't have imports, return empty list"""
        return []

    def extract_html_elements(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[MarkupElement]:
        """Extract HTML elements using tree-sitter-html parser"""
        elements: list[MarkupElement] = []

        try:
            if hasattr(tree, "root_node"):
                self._traverse_for_html_elements(
                    tree.root_node, elements, source_code, None
                )
        except Exception as e:
            log_error(f"Error in HTML element extraction: {e}")

        return elements

    def _traverse_for_html_elements(
        self,
        node: "tree_sitter.Node",
        elements: list[MarkupElement],
        source_code: str,
        parent: MarkupElement | None,
    ) -> None:
        """Traverse tree to find HTML elements using tree-sitter-html grammar.

        r37ch (dogfood): tool flagged this at nesting depth 8 (L163). The
        per-html-node creation logic moved into ``_try_create_html_element``.
        """
        if hasattr(node, "type") and self._is_html_element_node(node.type):
            created = self._try_create_html_element(node, elements, source_code, parent)
            if created:
                return

        # Continue traversing children if this node is not an HTML element
        if hasattr(node, "children"):
            for child in node.children:
                self._traverse_for_html_elements(child, elements, source_code, parent)

    def _try_create_html_element(
        self,
        node: "tree_sitter.Node",
        elements: list[MarkupElement],
        source_code: str,
        parent: MarkupElement | None,
    ) -> bool:
        """Create a MarkupElement for ``node`` and recurse with it as parent.

        r37ch (dogfood): extracted from ``_traverse_for_html_elements`` to
        drop nesting from 8 to ≤3. Returns True when an element was
        created (signalling the caller NOT to walk children again with
        the parent context).
        """
        try:
            element = self._create_markup_element(node, source_code, parent)
        except Exception as e:
            log_debug(f"Failed to extract HTML element: {e}")
            return False
        if not element:
            return False
        elements.append(element)
        if hasattr(node, "children"):
            for child in node.children:
                self._traverse_for_html_elements(child, elements, source_code, element)
        return True

    def _is_html_element_node(self, node_type: str) -> bool:
        """Check if a node type represents an HTML element in tree-sitter-html grammar"""
        # Only process top-level element nodes to avoid duplication
        # tree-sitter-html structure: element contains start_tag/end_tag
        # Processing only 'element' avoids counting start_tag separately
        html_element_types = [
            "element",
            "self_closing_tag",
            "script_element",
            "style_element",
        ]
        return node_type in html_element_types

    def _create_markup_element(
        self,
        node: "tree_sitter.Node",
        source_code: str,
        parent: MarkupElement | None,
    ) -> MarkupElement | None:
        """Create MarkupElement from tree-sitter node using tree-sitter-html grammar"""
        return _create_markup_standalone(
            node,
            lambda n: self._extract_node_text(n, source_code),
            self.element_categories,
            parent,
        )

    def _classify_element(self, tag_name: str) -> str:
        """Classify HTML element based on tag name"""
        return _classify_standalone(tag_name, self.element_categories)

    def _extract_tag_name(self, node: "tree_sitter.Node", source_code: str) -> str:
        """Extract tag name from HTML element node"""
        from .html_helpers import extract_html_tag_name

        return extract_html_tag_name(
            node, lambda n: self._extract_node_text(n, source_code)
        )

    def _extract_attributes(
        self, node: "tree_sitter.Node", source_code: str
    ) -> dict[str, str]:
        """Extract attributes from HTML element node"""
        from .html_helpers import extract_html_attributes

        return extract_html_attributes(
            node, lambda n: self._extract_node_text(n, source_code)
        )

    def _parse_attribute(
        self, attr_node: "tree_sitter.Node", source_code: str
    ) -> tuple[str, str]:
        """Parse individual attribute node"""
        from .html_helpers import parse_attribute

        return parse_attribute(
            attr_node, lambda n: self._extract_node_text(n, source_code)
        )

    def _extract_node_text(self, node: "tree_sitter.Node", source_code: str) -> str:
        """Extract text content from a tree-sitter node"""
        try:
            if hasattr(node, "start_byte") and hasattr(node, "end_byte"):
                source_bytes = source_code.encode("utf-8")
                node_bytes = source_bytes[node.start_byte : node.end_byte]
                return node_bytes.decode("utf-8", errors="replace")
            return ""
        except Exception as e:
            log_debug(f"Failed to extract node text: {e}")
            return ""


class HtmlPlugin(LanguagePlugin):
    """HTML language plugin using tree-sitter-html for true HTML parsing"""

    def get_language_name(self) -> str:
        return "html"

    def get_file_extensions(self) -> list[str]:
        return [".html", ".htm", ".xhtml"]

    def create_extractor(self) -> ElementExtractor:
        return HtmlElementExtractor()

    def get_tree_sitter_language(self) -> Any:
        """Get tree-sitter language object for HTML."""
        import tree_sitter
        import tree_sitter_html as ts_html

        return tree_sitter.Language(ts_html.language())

    def get_supported_element_types(self) -> list[str]:
        return ["html_element"]

    def get_queries(self) -> dict[str, str]:
        """Return HTML-specific tree-sitter queries"""
        from ..queries.html import HTML_QUERIES

        return HTML_QUERIES

    def execute_query_strategy(
        self, query_key: str | None, language: str
    ) -> str | None:
        """Execute query strategy for HTML"""
        if language != "html":
            return None

        queries = self.get_queries()
        return queries.get(query_key) if query_key else None

    def get_element_categories(self) -> dict[str, list[str]]:
        """Return HTML element categories for query execution"""
        return {
            "structure": ["element"],
            "heading": ["element"],
            "text": ["element"],
            "list": ["element"],
            "media": ["element"],
            "form": ["element"],
            "table": ["element"],
            "metadata": ["element"],
        }

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """Analyze HTML file using tree-sitter-html parser.

        r37er (dogfood): 91 → ~15 lines. Tree-sitter parse path moved to
        ``_analyze_with_tree_sitter``; ImportError fallback moved to
        ``_analyze_html_fallback``; top-level exception envelope moved to
        ``_html_error_result``.
        """
        from ..encoding_utils import read_file_safe

        try:
            content, _encoding = read_file_safe(file_path)
        except Exception as e:
            log_error(f"Failed to analyze HTML file {file_path}: {e}")
            return _html_error_result(file_path, e)

        try:
            return self._analyze_with_tree_sitter(file_path, content)
        except ImportError:
            log_error("tree-sitter-html not available, falling back to basic parsing")
            return _analyze_html_fallback(file_path, content)
        except Exception as e:
            log_error(f"Failed to analyze HTML file {file_path}: {e}")
            return _html_error_result(file_path, e)

    def _analyze_with_tree_sitter(
        self, file_path: str, content: str
    ) -> "AnalysisResult":
        """Parse via ``tree-sitter-html``; may raise ``ImportError`` if missing."""
        import tree_sitter
        import tree_sitter_html as ts_html

        HTML_LANGUAGE = tree_sitter.Language(ts_html.language())
        parser = tree_sitter.Parser()
        parser.language = HTML_LANGUAGE
        tree = parser.parse(content.encode("utf-8"))

        extractor = self.create_extractor()
        elements = extractor.extract_html_elements(tree, content)
        log_info(f"Extracted {len(elements)} HTML elements from {file_path}")

        return AnalysisResult(
            file_path=file_path,
            language="html",
            line_count=len(content.splitlines()),
            elements=elements,
            node_count=len(elements),
            query_results={},
            source_code=content,
            success=True,
            error_message=None,
        )
