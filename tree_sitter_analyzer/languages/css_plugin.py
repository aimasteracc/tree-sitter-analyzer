#!/usr/bin/env python3
"""
CSS Language Plugin

True CSS parser using tree-sitter-css for comprehensive CSS analysis.
Provides CSS-specific analysis capabilities including rule extraction,
selector parsing, and property analysis.
"""

import logging
from typing import TYPE_CHECKING, Any

from ..models import AnalysisResult, StyleElement
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error, log_info
from .css_helpers import (
    classify_rule as _classify_rule_standalone,
)
from .css_helpers import (
    create_style_element as _create_style_standalone,
)

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest

logger = logging.getLogger(__name__)


def _css_error_result(file_path: str, exc: Exception) -> AnalysisResult:
    """Build the canonical failure ``AnalysisResult`` for CSS parse errors."""
    return AnalysisResult(
        file_path=file_path,
        language="css",
        line_count=0,
        elements=[],
        node_count=0,
        query_results={},
        source_code="",
        success=False,
        error_message=str(exc),
    )


def _analyze_css_fallback(file_path: str, content: str) -> AnalysisResult:
    """Best-effort fallback when ``tree-sitter-css`` is not installed.

    Emits a single synthetic ``css`` StyleElement spanning the whole
    document so downstream tooling sees *something*. Truncates raw text
    to 200 chars for the FTS row.
    """
    lines = content.splitlines()
    line_count = len(lines)
    css_element = StyleElement(
        name="css",
        start_line=1,
        end_line=line_count,
        raw_text=content[:200] + "..." if len(content) > 200 else content,
        language="css",
        selector="*",
        properties={},
        element_class="other",
    )
    return AnalysisResult(
        file_path=file_path,
        language="css",
        line_count=line_count,
        elements=[css_element],
        node_count=1,
        query_results={},
        source_code=content,
        success=True,
        error_message=None,
    )


class CssElementExtractor(ElementExtractor):
    """CSS-specific element extractor using tree-sitter-css"""

    def __init__(self) -> None:
        self.property_categories = {
            # CSS プロパティの分類システム
            "layout": [
                "display",
                "position",
                "float",
                "clear",
                "overflow",
                "visibility",
                "z-index",
            ],
            "box_model": [
                "width",
                "height",
                "margin",
                "padding",
                "border",
                "box-sizing",
            ],
            "typography": [
                "font",
                "color",
                "text",
                "line-height",
                "letter-spacing",
                "word-spacing",
            ],
            "background": [
                "background",
                "background-color",
                "background-image",
                "background-position",
                "background-size",
            ],
            "flexbox": [
                "flex",
                "justify-content",
                "align-items",
                "align-content",
                "flex-direction",
                "flex-wrap",
            ],
            "grid": ["grid", "grid-template", "grid-area", "grid-column", "grid-row"],
            "animation": ["animation", "transition", "transform", "keyframes"],
            "responsive": [
                "media",
                "min-width",
                "max-width",
                "min-height",
                "max-height",
            ],
            "other": [],
        }

    def extract_functions(self, tree: "tree_sitter.Tree", source_code: str) -> list:
        """CSS doesn't have functions in the traditional sense, return empty list"""
        return []

    def extract_classes(self, tree: "tree_sitter.Tree", source_code: str) -> list:
        """CSS doesn't have classes in the traditional sense, return empty list"""
        return []

    def extract_variables(self, tree: "tree_sitter.Tree", source_code: str) -> list:
        """CSS doesn't have variables (except custom properties), return empty list"""
        return []

    def extract_imports(self, tree: "tree_sitter.Tree", source_code: str) -> list:
        """CSS doesn't have imports in the traditional sense, return empty list"""
        return []

    def extract_css_rules(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[StyleElement]:
        """Extract CSS rules using tree-sitter-css parser"""
        elements: list[StyleElement] = []

        try:
            if hasattr(tree, "root_node"):
                self._traverse_for_css_rules(tree.root_node, elements, source_code)
        except Exception as e:
            log_error(f"Error in CSS rule extraction: {e}")

        return elements

    def _traverse_for_css_rules(
        self, node: "tree_sitter.Node", elements: list[StyleElement], source_code: str
    ) -> None:
        """Traverse tree to find CSS rules using tree-sitter-css grammar"""
        if hasattr(node, "type") and self._is_css_rule_node(node.type):
            try:
                element = self._create_style_element(node, source_code)
                if element:
                    elements.append(element)
            except Exception as e:
                log_debug(f"Failed to extract CSS rule: {e}")

        # Continue traversing children
        if hasattr(node, "children"):
            for child in node.children:
                self._traverse_for_css_rules(child, elements, source_code)

    def _is_css_rule_node(self, node_type: str) -> bool:
        """Check if a node type represents a CSS rule in tree-sitter-css grammar"""
        css_rule_types = [
            "rule_set",
            "at_rule",
            "media_statement",
            "import_statement",
            "keyframes_statement",
            "supports_statement",
            "font_face_statement",
            "page_statement",
            "charset_statement",
            "namespace_statement",
        ]
        return node_type in css_rule_types

    def _create_style_element(
        self, node: "tree_sitter.Node", source_code: str
    ) -> StyleElement | None:
        """Create StyleElement from tree-sitter node using tree-sitter-css grammar"""
        return _create_style_standalone(
            node,
            lambda n: self._extract_node_text(n, source_code),
            self.property_categories,
        )

    def _classify_rule(self, properties: dict[str, str]) -> str:
        """Classify CSS rule based on properties"""
        return _classify_rule_standalone(properties, self.property_categories)

    def _extract_selector(self, node: "tree_sitter.Node", source_code: str) -> str:
        """Extract selector from CSS rule_set node"""
        from .css_helpers import extract_css_selector

        return extract_css_selector(
            node, lambda n: self._extract_node_text(n, source_code)
        )

    def _extract_properties(
        self, node: "tree_sitter.Node", source_code: str
    ) -> dict[str, str]:
        """Extract properties from CSS rule_set node"""
        from .css_helpers import extract_css_properties

        return extract_css_properties(
            node, lambda n: self._extract_node_text(n, source_code)
        )

    def _parse_declaration(
        self, decl_node: "tree_sitter.Node", source_code: str
    ) -> tuple[str, str]:
        """Parse individual CSS declaration"""
        from .css_helpers import parse_declaration

        return parse_declaration(
            decl_node, lambda n: self._extract_node_text(n, source_code)
        )

    def _extract_at_rule_name(self, node: "tree_sitter.Node", source_code: str) -> str:
        """Extract at-rule name from CSS at-rule node"""
        from .css_helpers import extract_at_rule_name

        return extract_at_rule_name(
            node, lambda n: self._extract_node_text(n, source_code)
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


class CssPlugin(LanguagePlugin):
    """CSS language plugin using tree-sitter-css for true CSS parsing"""

    def __init__(self) -> None:
        """Initialize CSS plugin with extractor."""
        super().__init__()
        self.extractor = CssElementExtractor()

    def get_language_name(self) -> str:
        return "css"

    def get_file_extensions(self) -> list[str]:
        return [".css", ".scss", ".sass", ".less"]

    def create_extractor(self) -> ElementExtractor:
        return CssElementExtractor()

    def get_tree_sitter_language(self) -> Any:
        """Get tree-sitter language object for CSS."""
        import tree_sitter
        import tree_sitter_css as ts_css

        return tree_sitter.Language(ts_css.language())

    def get_supported_element_types(self) -> list[str]:
        return ["css_rule"]

    def get_queries(self) -> dict[str, str]:
        """Return CSS-specific tree-sitter queries"""
        from ..queries.css import CSS_QUERIES

        return CSS_QUERIES

    def execute_query_strategy(
        self, query_key: str | None, language: str
    ) -> str | None:
        """Execute query strategy for CSS"""
        if language != "css":
            return None

        queries = self.get_queries()
        return queries.get(query_key) if query_key else None

    def get_element_categories(self) -> dict[str, list[str]]:
        """Return CSS element categories for query execution"""
        return {
            "layout": ["rule_set"],
            "box_model": ["rule_set"],
            "typography": ["rule_set"],
            "background": ["rule_set"],
            "flexbox": ["rule_set"],
            "grid": ["rule_set"],
            "animation": ["rule_set"],
            "responsive": ["media_statement"],
            "at_rules": ["at_rule"],
            "other": ["rule_set"],
        }

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """Analyze CSS file using tree-sitter-css parser.

        r37es (dogfood): 89 → ~15 lines. Tree-sitter parse path moved to
        ``_analyze_with_tree_sitter``; ImportError fallback moved to
        ``_analyze_css_fallback``; top-level exception envelope moved to
        ``_css_error_result``.
        """
        from ..encoding_utils import read_file_safe

        try:
            content, _encoding = read_file_safe(file_path)
        except Exception as e:
            log_error(f"Failed to analyze CSS file {file_path}: {e}")
            return _css_error_result(file_path, e)

        try:
            return self._analyze_with_tree_sitter(file_path, content)
        except ImportError:
            log_error("tree-sitter-css not available, falling back to basic parsing")
            return _analyze_css_fallback(file_path, content)
        except Exception as e:
            log_error(f"Failed to analyze CSS file {file_path}: {e}")
            return _css_error_result(file_path, e)

    def _analyze_with_tree_sitter(
        self, file_path: str, content: str
    ) -> "AnalysisResult":
        """Parse via ``tree-sitter-css``; may raise ``ImportError`` if missing."""
        import tree_sitter
        import tree_sitter_css as ts_css

        CSS_LANGUAGE = tree_sitter.Language(ts_css.language())
        parser = tree_sitter.Parser()
        parser.language = CSS_LANGUAGE
        tree = parser.parse(content.encode("utf-8"))

        extractor = self.create_extractor()
        elements = extractor.extract_css_rules(tree, content)
        log_info(f"Extracted {len(elements)} CSS rules from {file_path}")

        return AnalysisResult(
            file_path=file_path,
            language="css",
            line_count=len(content.splitlines()),
            elements=elements,
            node_count=len(elements),
            query_results={},
            source_code=content,
            success=True,
            error_message=None,
        )
