#!/usr/bin/env python3
"""
HTML Language Plugin

Provides HTML-specific parsing and element extraction functionality.
Supports comprehensive HTML analysis including elements, attributes, text content,
comments, and embedded scripts/styles. Designed to integrate seamlessly with 
the tree-sitter-analyzer framework.
"""

import re
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import tree_sitter

from ..encoding_utils import extract_text_slice, safe_encode
from ..models import Class, CodeElement, Function, Import, Package, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error, log_warning


class HTMLElementExtractor(ElementExtractor):
    """HTML-specific element extractor with comprehensive feature support"""

    def __init__(self) -> None:
        """Initialize the HTML element extractor."""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        
        # Performance optimization caches
        self._node_text_cache: dict[int, str] = {}
        self._processed_nodes: set[int] = set()
        self._element_cache: dict[tuple[int, str], Any] = {}
        self._file_encoding: str | None = None
        
        # HTML-specific caches
        self._attribute_cache: dict[int, list[dict[str, Any]]] = {}
        self._text_content_cache: dict[int, str] = {}
        
        # Extracted elements for cross-referencing
        self.html_elements: list[dict[str, Any]] = []
        self.attributes: list[dict[str, Any]] = []
        self.text_nodes: list[dict[str, Any]] = []
        self.comments: list[dict[str, Any]] = []

    def extract_elements_from_html(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[dict[str, Any]]:
        """Extract HTML elements using tree-sitter parsing"""
        self.source_code = source_code
        self.content_lines = source_code.splitlines()
        
        elements = []
        
        try:
            if hasattr(tree, "root_node"):
                self._traverse_html_nodes(tree.root_node, elements)
        except Exception as e:
            log_error(f"Error extracting HTML elements: {e}")
        
        return elements

    def _traverse_html_nodes(self, node: "tree_sitter.Node", elements: list[dict[str, Any]]) -> None:
        """Traverse HTML tree nodes and extract elements"""
        if not hasattr(node, 'type'):
            return
        
        node_id = id(node)
        if node_id in self._processed_nodes:
            return
        self._processed_nodes.add(node_id)
        
        node_type = node.type
        
        # Extract different types of HTML nodes
        if node_type == "element":
            self._extract_html_element(node, elements)
        elif node_type == "self_closing_tag":
            self._extract_self_closing_element(node, elements)
        elif node_type == "attribute":
            self._extract_attribute(node, elements)
        elif node_type == "text":
            self._extract_text_content(node, elements)
        elif node_type == "comment":
            self._extract_comment(node, elements)
        elif node_type == "doctype":
            self._extract_doctype(node, elements)
        elif node_type in ["script_element", "style_element"]:
            self._extract_embedded_content(node, elements)
        
        # Recursively process child nodes
        if hasattr(node, "children"):
            for child in node.children:
                self._traverse_html_nodes(child, elements)

    def _extract_html_element(self, node: "tree_sitter.Node", elements: list[dict[str, Any]]) -> None:
        """Extract regular HTML element"""
        try:
            # Find the start tag to get element name
            start_tag = None
            tag_name = "unknown"
            
            if hasattr(node, "children"):
                for child in node.children:
                    if hasattr(child, "type") and child.type == "start_tag":
                        start_tag = child
                        # Find tag name within start tag
                        if hasattr(child, "children"):
                            for grandchild in child.children:
                                if hasattr(grandchild, "type") and grandchild.type == "tag_name":
                                    tag_name = self._get_node_text(grandchild)
                                    break
                        break
            
            if start_tag:
                element_info = {
                    "type": "html_element",
                    "name": tag_name,
                    "start_line": node.start_point[0] + 1 if hasattr(node, "start_point") else 0,
                    "end_line": node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
                    "raw_text": self._get_node_text(node),
                    "node_type": "element",
                    "attributes": self._extract_element_attributes(start_tag),
                    "is_self_closing": False,
                }
                
                elements.append(element_info)
                self.html_elements.append(element_info)
                
        except Exception as e:
            log_debug(f"Failed to extract HTML element: {e}")

    def _extract_self_closing_element(self, node: "tree_sitter.Node", elements: list[dict[str, Any]]) -> None:
        """Extract self-closing HTML element"""
        try:
            tag_name = "unknown"
            
            # Find tag name
            if hasattr(node, "children"):
                for child in node.children:
                    if hasattr(child, "type") and child.type == "tag_name":
                        tag_name = self._get_node_text(child)
                        break
            
            element_info = {
                "type": "html_element",
                "name": tag_name,
                "start_line": node.start_point[0] + 1 if hasattr(node, "start_point") else 0,
                "end_line": node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
                "raw_text": self._get_node_text(node),
                "node_type": "self_closing_tag",
                "attributes": self._extract_element_attributes(node),
                "is_self_closing": True,
            }
            
            elements.append(element_info)
            self.html_elements.append(element_info)
            
        except Exception as e:
            log_debug(f"Failed to extract self-closing element: {e}")

    def _extract_attribute(self, node: "tree_sitter.Node", elements: list[dict[str, Any]]) -> None:
        """Extract HTML attribute"""
        try:
            attr_name = "unknown"
            attr_value = ""
            
            # Extract attribute name and value
            if hasattr(node, "children"):
                for child in node.children:
                    if hasattr(child, "type"):
                        if child.type == "attribute_name":
                            attr_name = self._get_node_text(child)
                        elif child.type == "quoted_attribute_value":
                            # Extract value from quoted attribute
                            if hasattr(child, "children"):
                                for grandchild in child.children:
                                    if hasattr(grandchild, "type") and grandchild.type == "attribute_value":
                                        attr_value = self._get_node_text(grandchild)
                                        break
            
            attribute_info = {
                "type": "html_attribute",
                "name": attr_name,
                "value": attr_value,
                "start_line": node.start_point[0] + 1 if hasattr(node, "start_point") else 0,
                "end_line": node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
                "raw_text": self._get_node_text(node),
                "node_type": "attribute",
            }
            
            elements.append(attribute_info)
            self.attributes.append(attribute_info)
            
        except Exception as e:
            log_debug(f"Failed to extract attribute: {e}")

    def _extract_text_content(self, node: "tree_sitter.Node", elements: list[dict[str, Any]]) -> None:
        """Extract text content"""
        try:
            text_content = self._get_node_text(node).strip()
            
            # Skip empty or whitespace-only text
            if not text_content or text_content.isspace():
                return
            
            text_info = {
                "type": "text_content",
                "name": f"text_{node.start_point[0]}_{node.start_point[1]}" if hasattr(node, "start_point") else "text",
                "content": text_content,
                "start_line": node.start_point[0] + 1 if hasattr(node, "start_point") else 0,
                "end_line": node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
                "raw_text": self._get_node_text(node),
                "node_type": "text",
            }
            
            elements.append(text_info)
            self.text_nodes.append(text_info)
            
        except Exception as e:
            log_debug(f"Failed to extract text content: {e}")

    def _extract_comment(self, node: "tree_sitter.Node", elements: list[dict[str, Any]]) -> None:
        """Extract HTML comment"""
        try:
            comment_text = self._get_node_text(node)
            
            # Extract content from <!-- content -->
            content = comment_text
            if comment_text.startswith("<!--") and comment_text.endswith("-->"):
                content = comment_text[4:-3].strip()
            
            comment_info = {
                "type": "html_comment",
                "name": f"comment_{node.start_point[0]}_{node.start_point[1]}" if hasattr(node, "start_point") else "comment",
                "content": content,
                "start_line": node.start_point[0] + 1 if hasattr(node, "start_point") else 0,
                "end_line": node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
                "raw_text": comment_text,
                "node_type": "comment",
            }
            
            elements.append(comment_info)
            self.comments.append(comment_info)
            
        except Exception as e:
            log_debug(f"Failed to extract comment: {e}")

    def _extract_doctype(self, node: "tree_sitter.Node", elements: list[dict[str, Any]]) -> None:
        """Extract HTML doctype declaration"""
        try:
            doctype_text = self._get_node_text(node)
            
            doctype_info = {
                "type": "html_doctype",
                "name": "doctype",
                "content": doctype_text,
                "start_line": node.start_point[0] + 1 if hasattr(node, "start_point") else 0,
                "end_line": node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
                "raw_text": doctype_text,
                "node_type": "doctype",
            }
            
            elements.append(doctype_info)
            
        except Exception as e:
            log_debug(f"Failed to extract doctype: {e}")

    def _extract_embedded_content(self, node: "tree_sitter.Node", elements: list[dict[str, Any]]) -> None:
        """Extract embedded script or style content"""
        try:
            content_type = "script" if node.type == "script_element" else "style"
            embedded_text = self._get_node_text(node)
            
            # Try to extract the actual content (not the whole tag)
            content = ""
            if hasattr(node, "children"):
                for child in node.children:
                    if hasattr(child, "type") and child.type == "raw_text":
                        content = self._get_node_text(child)
                        break
            
            embedded_info = {
                "type": f"html_{content_type}",
                "name": f"{content_type}_block",
                "content": content,
                "start_line": node.start_point[0] + 1 if hasattr(node, "start_point") else 0,
                "end_line": node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
                "raw_text": embedded_text,
                "node_type": node.type,
                "content_type": content_type,
            }
            
            elements.append(embedded_info)
            
        except Exception as e:
            log_debug(f"Failed to extract embedded content: {e}")

    def _extract_element_attributes(self, node: "tree_sitter.Node") -> list[dict[str, str]]:
        """Extract attributes from an element's start tag"""
        attributes = []
        
        try:
            if hasattr(node, "children"):
                for child in node.children:
                    if hasattr(child, "type") and child.type == "attribute":
                        attr_name = ""
                        attr_value = ""
                        
                        if hasattr(child, "children"):
                            for grandchild in child.children:
                                if hasattr(grandchild, "type"):
                                    if grandchild.type == "attribute_name":
                                        attr_name = self._get_node_text(grandchild)
                                    elif grandchild.type == "quoted_attribute_value":
                                        # Extract from quoted value
                                        if hasattr(grandchild, "children"):
                                            for ggchild in grandchild.children:
                                                if hasattr(ggchild, "type") and ggchild.type == "attribute_value":
                                                    attr_value = self._get_node_text(ggchild)
                                                    break
                        
                        if attr_name:
                            attributes.append({
                                "name": attr_name,
                                "value": attr_value
                            })
        except Exception as e:
            log_debug(f"Failed to extract element attributes: {e}")
        
        return attributes

    def _get_node_text(self, node: "tree_sitter.Node") -> str:
        """Get text content of a tree-sitter node with caching"""
        node_id = id(node)
        
        if node_id in self._node_text_cache:
            return self._node_text_cache[node_id]
        
        try:
            if hasattr(node, "start_byte") and hasattr(node, "end_byte"):
                text = extract_text_slice(
                    self.source_code, 
                    node.start_byte, 
                    node.end_byte,
                    self._file_encoding
                )
            else:
                text = ""
        except Exception as e:
            log_debug(f"Failed to extract node text: {e}")
            text = ""
        
        self._node_text_cache[node_id] = text
        return text

    # ElementExtractor interface implementation
    
    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract HTML elements as functions"""
        html_elements = self.extract_elements_from_html(tree, source_code)
        functions = []
        
        for element in html_elements:
            if element.get("type") == "html_element":
                func = Function(
                    name=element["name"],
                    start_line=element["start_line"],
                    end_line=element["end_line"],
                    raw_text=element["raw_text"],
                    language="html",
                    parameters=[],  # HTML elements don't have traditional parameters
                    return_type=None,
                    is_async=False,
                    is_static=False,
                    visibility="public",
                    complexity=0,  # HTML elements don't have complexity
                    docstring="",
                    decorators=[],
                    signature=f"<{element['name']}>",
                )
                functions.append(func)
        
        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """Extract embedded scripts/styles as classes"""
        html_elements = self.extract_elements_from_html(tree, source_code)
        classes = []
        
        for element in html_elements:
            if element.get("type") in ["html_script", "html_style"]:
                cls = Class(
                    name=element["name"],
                    start_line=element["start_line"],
                    end_line=element["end_line"],
                    raw_text=element["raw_text"],
                    language="html",
                    methods=[],
                    fields=[],
                    base_classes=[],
                    is_abstract=False,
                    visibility="public",
                    decorators=[],
                    docstring=f"{element['content_type'].upper()} embedded content",
                )
                classes.append(cls)
        
        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract HTML attributes as variables"""
        html_elements = self.extract_elements_from_html(tree, source_code)
        variables = []
        
        for element in html_elements:
            if element.get("type") == "html_attribute":
                var = Variable(
                    name=element["name"],
                    start_line=element["start_line"],
                    end_line=element["end_line"],
                    raw_text=element["raw_text"],
                    language="html",
                    var_type="string",  # HTML attributes are typically strings
                    value=element.get("value", ""),
                    is_constant=False,
                    visibility="public",
                    scope="element",
                )
                variables.append(var)
        
        return variables

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract HTML comments as imports (for consistency)"""
        html_elements = self.extract_elements_from_html(tree, source_code)
        imports = []
        
        for element in html_elements:
            if element.get("type") == "html_comment":
                imp = Import(
                    name=element["name"],
                    start_line=element["start_line"],
                    end_line=element["end_line"],
                    raw_text=element["raw_text"],
                    language="html",
                    module_name="",  # Comments don't have modules
                    imported_names=[element.get("content", "")],
                    alias=None,
                    is_from_import=False,
                )
                imports.append(imp)
        
        return imports


class HTMLLanguagePlugin(LanguagePlugin):
    """HTML language plugin for tree-sitter analyzer"""

    def get_language_name(self) -> str:
        return "html"

    def get_file_extensions(self) -> list[str]:
        return [".html", ".htm", ".xhtml", ".xml", ".svg"]

    def create_extractor(self) -> ElementExtractor:
        return HTMLElementExtractor()

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """
        Analyze an HTML file and return comprehensive analysis results.

        Args:
            file_path: Path to the HTML file to analyze
            request: Analysis request with configuration

        Returns:
            AnalysisResult containing extracted HTML information
        """
        from ..core.analysis_engine import UnifiedAnalysisEngine
        from ..models import AnalysisResult

        try:
            # Use the unified analysis engine with HTML-specific processing
            engine = UnifiedAnalysisEngine()
            result = await engine.analyze_file(file_path)
            
            # Enhance result with HTML-specific metrics
            if result.success:
                self._enhance_html_metrics(result)
            
            return result
            
        except Exception as e:
            log_error(f"Failed to analyze HTML file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                line_count=0,
                elements=[],
                node_count=0,
                query_results={},
                source_code="",
                success=False,
                error_message=str(e),
            )

    def _enhance_html_metrics(self, result: "AnalysisResult") -> None:
        """Enhance analysis result with HTML-specific metrics"""
        try:
            # Count different types of HTML elements
            html_elements = [e for e in result.elements if e.element_type == "function"]
            attributes = [e for e in result.elements if e.element_type == "variable"]
            comments = [e for e in result.elements if e.element_type == "import"]
            embedded = [e for e in result.elements if e.element_type == "class"]
            
            # Count specific element types
            semantic_elements = sum(1 for e in html_elements if e.name.lower() in 
                                  ["header", "footer", "main", "section", "article", "aside", "nav"])
            form_elements = sum(1 for e in html_elements if e.name.lower() in 
                              ["form", "input", "textarea", "select", "button", "label"])
            media_elements = sum(1 for e in html_elements if e.name.lower() in 
                               ["img", "video", "audio", "picture", "source", "track"])
            
            # Update metrics
            if hasattr(result, 'metrics') and result.metrics:
                if not hasattr(result.metrics, 'elements'):
                    result.metrics.elements = {}
                
                result.metrics.elements.update({
                    "elements": len(html_elements),
                    "attributes": len(attributes),
                    "text_nodes": 0,  # Will be calculated separately
                    "comments": len(comments),
                    "scripts": sum(1 for e in embedded if "script" in e.name.lower()),
                    "styles": sum(1 for e in embedded if "style" in e.name.lower()),
                    "semantic_elements": semantic_elements,
                    "form_elements": form_elements,
                    "media_elements": media_elements,
                })
            
        except Exception as e:
            log_debug(f"Failed to enhance HTML metrics: {e}")


# Plugin instance for registration
html_plugin = HTMLLanguagePlugin()