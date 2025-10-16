#!/usr/bin/env python3
"""
HTML Language Plugin

True HTML parser using tree-sitter-html for comprehensive HTML analysis.
Provides HTML-specific analysis capabilities including element extraction,
attribute parsing, and document structure analysis.
"""

import logging
from typing import TYPE_CHECKING

from ..models import AnalysisResult, MarkupElement
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error, log_info

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest

logger = logging.getLogger(__name__)


class HtmlElementExtractor(ElementExtractor):
    """HTML-specific element extractor using tree-sitter-html"""

    def __init__(self):
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
        elements = []

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
        """Traverse tree to find HTML elements using tree-sitter-html grammar"""
        if hasattr(node, "type") and self._is_html_element_node(node.type):
            try:
                element = self._create_markup_element(node, source_code, parent)
                if element:
                    elements.append(element)

                    # Process children with this element as parent
                    if hasattr(node, "children"):
                        for child in node.children:
                            self._traverse_for_html_elements(
                                child, elements, source_code, element
                            )
                    return
            except Exception as e:
                log_debug(f"Failed to extract HTML element: {e}")

        # Continue traversing children if this node is not an HTML element
        if hasattr(node, "children"):
            for child in node.children:
                self._traverse_for_html_elements(child, elements, source_code, parent)

    def _is_html_element_node(self, node_type: str) -> bool:
        """Check if a node type represents an HTML element in tree-sitter-html grammar"""
        html_element_types = [
            "element",
            "start_tag",
            "self_closing_tag",
            "script_element",
            "style_element",
            "void_element",
        ]
        return node_type in html_element_types

    def _create_markup_element(
        self, node: "tree_sitter.Node", source_code: str, parent: MarkupElement | None
    ) -> MarkupElement | None:
        """Create MarkupElement from tree-sitter node using tree-sitter-html grammar"""
        try:
            # Extract tag name using tree-sitter-html structure
            tag_name = self._extract_tag_name(node, source_code)
            if not tag_name:
                return None

            # Extract attributes using tree-sitter-html structure
            attributes = self._extract_attributes(node, source_code)

            # Determine element class based on tag name
            element_class = self._classify_element(tag_name)

            # Extract text content
            raw_text = self._extract_node_text(node, source_code)

            # Create MarkupElement
            element = MarkupElement(
                name=tag_name,
                start_line=node.start_point[0] + 1
                if hasattr(node, "start_point")
                else 0,
                end_line=node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
                raw_text=raw_text,
                language="html",
                tag_name=tag_name,
                attributes=attributes,
                parent=parent,
                children=[],
                element_class=element_class,
            )

            # Add to parent's children if parent exists
            if parent:
                parent.children.append(element)

            return element

        except Exception as e:
            log_debug(f"Failed to create MarkupElement: {e}")
            return None

    def _extract_tag_name(self, node: "tree_sitter.Node", source_code: str) -> str:
        """Extract tag name from HTML element node using tree-sitter-html grammar"""
        try:
            # For tree-sitter-html, tag names are in specific child nodes
            if hasattr(node, "children"):
                for child in node.children:
                    if hasattr(child, "type"):
                        # Handle different node types in tree-sitter-html
                        if child.type == "tag_name":
                            return self._extract_node_text(child, source_code).strip()
                        elif child.type in ["start_tag", "self_closing_tag"]:
                            # Look for tag_name within start_tag or self_closing_tag
                            for grandchild in child.children:
                                if (
                                    hasattr(grandchild, "type")
                                    and grandchild.type == "tag_name"
                                ):
                                    return self._extract_node_text(
                                        grandchild, source_code
                                    ).strip()

            # Fallback: try to extract from node text
            node_text = self._extract_node_text(node, source_code)
            if node_text.startswith("<"):
                # Extract tag name from <tagname ...> pattern
                tag_part = node_text.split(">")[0].split()[0]
                return tag_part.lstrip("<").rstrip(">")

            return "unknown"
        except Exception:
            return "unknown"

    def _extract_attributes(
        self, node: "tree_sitter.Node", source_code: str
    ) -> dict[str, str]:
        """Extract attributes from HTML element node using tree-sitter-html grammar"""
        attributes = {}

        try:
            if hasattr(node, "children"):
                for child in node.children:
                    if hasattr(child, "type"):
                        # Handle attribute nodes in tree-sitter-html
                        if child.type == "attribute":
                            attr_name, attr_value = self._parse_attribute(
                                child, source_code
                            )
                            if attr_name:
                                attributes[attr_name] = attr_value
                        elif child.type in ["start_tag", "self_closing_tag"]:
                            # Look for attributes within start_tag or self_closing_tag
                            for grandchild in child.children:
                                if (
                                    hasattr(grandchild, "type")
                                    and grandchild.type == "attribute"
                                ):
                                    attr_name, attr_value = self._parse_attribute(
                                        grandchild, source_code
                                    )
                                    if attr_name:
                                        attributes[attr_name] = attr_value
        except Exception as e:
            log_debug(f"Failed to extract attributes: {e}")

        return attributes

    def _parse_attribute(
        self, attr_node: "tree_sitter.Node", source_code: str
    ) -> tuple[str, str]:
        """Parse individual attribute node using tree-sitter-html grammar"""
        try:
            # In tree-sitter-html, attributes have specific structure
            attr_name = ""
            attr_value = ""

            if hasattr(attr_node, "children"):
                for child in attr_node.children:
                    if hasattr(child, "type"):
                        if child.type == "attribute_name":
                            attr_name = self._extract_node_text(
                                child, source_code
                            ).strip()
                        elif child.type == "quoted_attribute_value":
                            attr_value = (
                                self._extract_node_text(child, source_code)
                                .strip()
                                .strip('"')
                                .strip("'")
                            )
                        elif child.type == "attribute_value":
                            attr_value = self._extract_node_text(
                                child, source_code
                            ).strip()

            # Fallback to simple parsing
            if not attr_name:
                attr_text = self._extract_node_text(attr_node, source_code)
                if "=" in attr_text:
                    name, value = attr_text.split("=", 1)
                    attr_name = name.strip()
                    attr_value = value.strip().strip('"').strip("'")
                else:
                    # Boolean attribute
                    attr_name = attr_text.strip()
                    attr_value = ""

            return attr_name, attr_value
        except Exception:
            return "", ""

    def _classify_element(self, tag_name: str) -> str:
        """Classify HTML element based on tag name"""
        tag_name_lower = tag_name.lower()

        for category, tags in self.element_categories.items():
            if tag_name_lower in tags:
                return category

        return "unknown"

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
        """Analyze HTML file using tree-sitter-html parser"""
        from ..encoding_utils import read_file_safe

        try:
            # Read file content
            content, encoding = read_file_safe(file_path)

            # Use tree-sitter-html for parsing
            try:
                import tree_sitter
                import tree_sitter_html as ts_html

                # Get HTML language
                HTML_LANGUAGE = tree_sitter.Language(ts_html.language())

                # Create parser
                parser = tree_sitter.Parser()
                parser.language = HTML_LANGUAGE

                # Parse the HTML content
                tree = parser.parse(content.encode("utf-8"))

                # Extract elements using the extractor
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

            except ImportError:
                log_error(
                    "tree-sitter-html not available, falling back to basic parsing"
                )
                # Fallback to basic parsing
                lines = content.splitlines()
                line_count = len(lines)

                # Create basic MarkupElement for the HTML document
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
                elements = [html_element]

                return AnalysisResult(
                    file_path=file_path,
                    language="html",
                    line_count=line_count,
                    elements=elements,
                    node_count=len(elements),
                    query_results={},
                    source_code=content,
                    success=True,
                    error_message=None,
                )

        except Exception as e:
            log_error(f"Failed to analyze HTML file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language="html",
                line_count=0,
                elements=[],
                node_count=0,
                query_results={},
                source_code="",
                success=False,
                error_message=str(e),
            )
