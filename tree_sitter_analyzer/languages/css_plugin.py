#!/usr/bin/env python3
"""
CSS Language Plugin

True CSS parser using tree-sitter-css for comprehensive CSS analysis.
Provides CSS-specific analysis capabilities including rule extraction,
selector parsing, and property analysis.
"""

import logging
from typing import TYPE_CHECKING

from ..models import AnalysisResult, StyleElement
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error, log_info

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest

logger = logging.getLogger(__name__)


class CssElementExtractor(ElementExtractor):
    """CSS-specific element extractor using tree-sitter-css"""

    def __init__(self):
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
        elements = []

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
        try:
            # Extract selector and properties based on node type
            if node.type == "rule_set":
                selector = self._extract_selector(node, source_code)
                properties = self._extract_properties(node, source_code)
                element_class = self._classify_rule(properties)
                name = selector or "unknown_rule"
            elif node.type in [
                "at_rule",
                "media_statement",
                "import_statement",
                "keyframes_statement",
            ]:
                selector = self._extract_at_rule_name(node, source_code)
                properties = {}
                element_class = "at_rule"
                name = selector or "unknown_at_rule"
            else:
                selector = self._extract_node_text(node, source_code)[:50]
                properties = {}
                element_class = "other"
                name = selector or "unknown"

            # Extract raw text
            raw_text = self._extract_node_text(node, source_code)

            # Create StyleElement
            element = StyleElement(
                name=name,
                start_line=node.start_point[0] + 1
                if hasattr(node, "start_point")
                else 0,
                end_line=node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
                raw_text=raw_text,
                language="css",
                selector=selector,
                properties=properties,
                element_class=element_class,
            )

            return element

        except Exception as e:
            log_debug(f"Failed to create StyleElement: {e}")
            return None

    def _extract_selector(self, node: "tree_sitter.Node", source_code: str) -> str:
        """Extract selector from CSS rule_set node using tree-sitter-css grammar"""
        try:
            if hasattr(node, "children"):
                for child in node.children:
                    if hasattr(child, "type") and child.type == "selectors":
                        return self._extract_node_text(child, source_code).strip()

            # Fallback: extract from beginning of node text
            node_text = self._extract_node_text(node, source_code)
            if "{" in node_text:
                return node_text.split("{")[0].strip()

            return "unknown"
        except Exception:
            return "unknown"

    def _extract_properties(
        self, node: "tree_sitter.Node", source_code: str
    ) -> dict[str, str]:
        """Extract properties from CSS rule_set node using tree-sitter-css grammar"""
        properties = {}

        try:
            if hasattr(node, "children"):
                for child in node.children:
                    if hasattr(child, "type") and child.type == "block":
                        # Look for declarations within the block
                        for grandchild in child.children:
                            if (
                                hasattr(grandchild, "type")
                                and grandchild.type == "declaration"
                            ):
                                prop_name, prop_value = self._parse_declaration(
                                    grandchild, source_code
                                )
                                if prop_name:
                                    properties[prop_name] = prop_value
        except Exception as e:
            log_debug(f"Failed to extract properties: {e}")

        return properties

    def _parse_declaration(
        self, decl_node: "tree_sitter.Node", source_code: str
    ) -> tuple[str, str]:
        """Parse individual CSS declaration using tree-sitter-css grammar"""
        try:
            prop_name = ""
            prop_value = ""

            if hasattr(decl_node, "children"):
                for child in decl_node.children:
                    if hasattr(child, "type"):
                        if child.type == "property_name":
                            prop_name = self._extract_node_text(
                                child, source_code
                            ).strip()
                        elif child.type in ["value", "values"]:
                            prop_value = self._extract_node_text(
                                child, source_code
                            ).strip()

            # Fallback to simple parsing
            if not prop_name:
                decl_text = self._extract_node_text(decl_node, source_code)
                if ":" in decl_text:
                    parts = decl_text.split(":", 1)
                    prop_name = parts[0].strip()
                    prop_value = parts[1].strip().rstrip(";")

            return prop_name, prop_value
        except Exception:
            return "", ""

    def _extract_at_rule_name(self, node: "tree_sitter.Node", source_code: str) -> str:
        """Extract at-rule name from CSS at-rule node"""
        try:
            node_text = self._extract_node_text(node, source_code)
            if node_text.startswith("@"):
                # Extract @rule-name part
                parts = node_text.split()
                if parts:
                    return parts[0]
            return node_text[:50]  # Truncate for readability
        except Exception:
            return "unknown"

    def _classify_rule(self, properties: dict[str, str]) -> str:
        """Classify CSS rule based on properties"""
        if not properties:
            return "other"

        # Count properties in each category
        category_scores = dict.fromkeys(self.property_categories, 0)

        for prop_name in properties.keys():
            prop_name_lower = prop_name.lower()
            for category, props in self.property_categories.items():
                if any(prop in prop_name_lower for prop in props):
                    category_scores[category] += 1

        # Return category with highest score
        best_category = max(category_scores, key=category_scores.get)
        return best_category if category_scores[best_category] > 0 else "other"

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

    def get_language_name(self) -> str:
        return "css"

    def get_file_extensions(self) -> list[str]:
        return [".css", ".scss", ".sass", ".less"]

    def create_extractor(self) -> ElementExtractor:
        return CssElementExtractor()

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
        """Analyze CSS file using tree-sitter-css parser"""
        from ..encoding_utils import read_file_safe

        try:
            # Read file content
            content, encoding = read_file_safe(file_path)

            # Use tree-sitter-css for parsing
            try:
                import tree_sitter
                import tree_sitter_css as ts_css

                # Get CSS language
                CSS_LANGUAGE = tree_sitter.Language(ts_css.language())

                # Create parser
                parser = tree_sitter.Parser()
                parser.language = CSS_LANGUAGE

                # Parse the CSS content
                tree = parser.parse(content.encode("utf-8"))

                # Extract elements using the extractor
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

            except ImportError:
                log_error(
                    "tree-sitter-css not available, falling back to basic parsing"
                )
                # Fallback to basic parsing
                lines = content.splitlines()
                line_count = len(lines)

                # Create basic StyleElement for the CSS document
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
                elements = [css_element]

                return AnalysisResult(
                    file_path=file_path,
                    language="css",
                    line_count=line_count,
                    elements=elements,
                    node_count=len(elements),
                    query_results={},
                    source_code=content,
                    success=True,
                    error_message=None,
                )

        except Exception as e:
            log_error(f"Failed to analyze CSS file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language="css",
                line_count=0,
                elements=[],
                node_count=0,
                query_results={},
                source_code="",
                success=False,
                error_message=str(e),
            )
