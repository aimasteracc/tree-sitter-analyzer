#!/usr/bin/env python3
"""
Tests for Extended Data Models

Tests for new HTML/CSS-specific models including MarkupElement and StyleElement,
and their integration with the existing CodeElement hierarchy.
"""

import pytest

from tree_sitter_analyzer.models import (
    AnalysisResult,
    CodeElement,
    MarkupElement,
    StyleElement,
)


class TestMarkupElement:
    """Test MarkupElement data model"""

    def test_markup_element_creation(self):
        """Test basic MarkupElement creation"""
        element = MarkupElement(
            name="div",
            start_line=1,
            end_line=5,
            raw_text="<div class='container'>content</div>",
            language="html",
            tag_name="div",
            attributes={"class": "container", "id": "main"},
            element_class="structure"
        )

        assert element.name == "div"
        assert element.tag_name == "div"
        assert element.element_class == "structure"
        assert element.element_type == "html_element"
        assert element.attributes == {"class": "container", "id": "main"}
        assert element.parent is None
        assert element.children == []

    def test_markup_element_inheritance(self):
        """Test MarkupElement inherits from CodeElement"""
        element = MarkupElement(
            name="span",
            start_line=2,
            end_line=2,
            tag_name="span"
        )

        assert isinstance(element, CodeElement)
        assert isinstance(element, MarkupElement)

    def test_markup_element_hierarchy(self):
        """Test parent-child relationships"""
        parent = MarkupElement(
            name="div",
            start_line=1,
            end_line=10,
            tag_name="div",
            element_class="structure"
        )

        child1 = MarkupElement(
            name="p",
            start_line=2,
            end_line=4,
            tag_name="p",
            parent=parent,
            element_class="text"
        )

        child2 = MarkupElement(
            name="span",
            start_line=5,
            end_line=7,
            tag_name="span",
            parent=parent,
            element_class="text"
        )

        parent.children = [child1, child2]

        assert child1.parent == parent
        assert child2.parent == parent
        assert len(parent.children) == 2
        assert parent.children[0] == child1
        assert parent.children[1] == child2

    def test_markup_element_to_summary_item(self):
        """Test to_summary_item method"""
        element = MarkupElement(
            name="button",
            start_line=5,
            end_line=7,
            tag_name="button",
            attributes={"type": "submit", "class": "btn"},
            element_class="form"
        )

        summary = element.to_summary_item()

        expected = {
            "name": "button",
            "tag_name": "button",
            "type": "html_element",
            "element_class": "form",
            "lines": {"start": 5, "end": 7}
        }

        assert summary == expected

    def test_markup_element_default_values(self):
        """Test MarkupElement with default values"""
        element = MarkupElement(
            name="img",
            start_line=1,
            end_line=1
        )

        assert element.tag_name == ""
        assert element.attributes == {}
        assert element.parent is None
        assert element.children == []
        assert element.element_class == ""
        assert element.element_type == "html_element"

    def test_markup_element_complex_attributes(self):
        """Test MarkupElement with complex attributes"""
        element = MarkupElement(
            name="input",
            start_line=1,
            end_line=1,
            tag_name="input",
            attributes={
                "type": "text",
                "name": "username",
                "placeholder": "Enter username",
                "required": "",
                "data-validation": "required"
            },
            element_class="form"
        )

        assert element.attributes["type"] == "text"
        assert element.attributes["required"] == ""
        assert element.attributes["data-validation"] == "required"


class TestStyleElement:
    """Test StyleElement data model"""

    def test_style_element_creation(self):
        """Test basic StyleElement creation"""
        element = StyleElement(
            name=".container",
            start_line=1,
            end_line=5,
            raw_text=".container { width: 100%; margin: 0 auto; }",
            language="css",
            selector=".container",
            properties={"width": "100%", "margin": "0 auto"},
            element_class="layout"
        )

        assert element.name == ".container"
        assert element.selector == ".container"
        assert element.element_class == "layout"
        assert element.element_type == "css_rule"
        assert element.properties == {"width": "100%", "margin": "0 auto"}

    def test_style_element_inheritance(self):
        """Test StyleElement inherits from CodeElement"""
        element = StyleElement(
            name="h1",
            start_line=1,
            end_line=3,
            selector="h1"
        )

        assert isinstance(element, CodeElement)
        assert isinstance(element, StyleElement)

    def test_style_element_to_summary_item(self):
        """Test to_summary_item method"""
        element = StyleElement(
            name="#header",
            start_line=10,
            end_line=15,
            selector="#header",
            properties={"background": "blue", "height": "60px"},
            element_class="layout"
        )

        summary = element.to_summary_item()

        expected = {
            "name": "#header",
            "selector": "#header",
            "type": "css_rule",
            "element_class": "layout",
            "lines": {"start": 10, "end": 15}
        }

        assert summary == expected

    def test_style_element_default_values(self):
        """Test StyleElement with default values"""
        element = StyleElement(
            name="body",
            start_line=1,
            end_line=5
        )

        assert element.selector == ""
        assert element.properties == {}
        assert element.element_class == ""
        assert element.element_type == "css_rule"

    def test_style_element_complex_properties(self):
        """Test StyleElement with complex CSS properties"""
        element = StyleElement(
            name=".card",
            start_line=20,
            end_line=35,
            selector=".card",
            properties={
                "display": "flex",
                "flex-direction": "column",
                "border": "1px solid #ccc",
                "border-radius": "8px",
                "box-shadow": "0 2px 4px rgba(0,0,0,0.1)",
                "padding": "16px",
                "margin": "8px 0"
            },
            element_class="layout"
        )

        assert element.properties["display"] == "flex"
        assert element.properties["border-radius"] == "8px"
        assert "box-shadow" in element.properties


class TestExtendedModelsIntegration:
    """Test integration of extended models with existing system"""

    def test_analysis_result_with_markup_elements(self):
        """Test AnalysisResult with MarkupElement objects"""
        markup_elements = [
            MarkupElement(
                name="html",
                start_line=1,
                end_line=20,
                tag_name="html",
                element_class="structure"
            ),
            MarkupElement(
                name="body",
                start_line=5,
                end_line=18,
                tag_name="body",
                element_class="structure"
            )
        ]

        result = AnalysisResult(
            file_path="test.html",
            language="html",
            line_count=20,
            elements=markup_elements,
            node_count=2,
            query_results={},
            source_code="<html><body>content</body></html>",
            success=True
        )

        assert len(result.elements) == 2
        assert all(isinstance(e, MarkupElement) for e in result.elements)
        assert result.language == "html"

    def test_analysis_result_with_style_elements(self):
        """Test AnalysisResult with StyleElement objects"""
        style_elements = [
            StyleElement(
                name="body",
                start_line=1,
                end_line=3,
                selector="body",
                properties={"margin": "0", "padding": "0"},
                element_class="layout"
            ),
            StyleElement(
                name=".header",
                start_line=5,
                end_line=8,
                selector=".header",
                properties={"background": "blue", "color": "white"},
                element_class="layout"
            )
        ]

        result = AnalysisResult(
            file_path="styles.css",
            language="css",
            line_count=10,
            elements=style_elements,
            node_count=2,
            query_results={},
            source_code="body { margin: 0; } .header { background: blue; }",
            success=True
        )

        assert len(result.elements) == 2
        assert all(isinstance(e, StyleElement) for e in result.elements)
        assert result.language == "css"

    def test_mixed_elements_in_analysis_result(self):
        """Test AnalysisResult with mixed element types"""
        from tree_sitter_analyzer.models import Function, Variable

        mixed_elements = [
            MarkupElement(
                name="div",
                start_line=1,
                end_line=5,
                tag_name="div",
                element_class="structure"
            ),
            StyleElement(
                name=".container",
                start_line=10,
                end_line=15,
                selector=".container",
                element_class="layout"
            ),
            Function(
                name="init",
                start_line=20,
                end_line=25,
                language="javascript"
            ),
            Variable(
                name="config",
                start_line=30,
                end_line=30,
                language="javascript"
            )
        ]

        result = AnalysisResult(
            file_path="mixed.html",
            language="html",
            line_count=35,
            elements=mixed_elements,
            node_count=4,
            query_results={},
            source_code="mixed content",
            success=True
        )

        assert len(result.elements) == 4
        
        # Check element types
        markup_elements = [e for e in result.elements if isinstance(e, MarkupElement)]
        style_elements = [e for e in result.elements if isinstance(e, StyleElement)]
        function_elements = [e for e in result.elements if isinstance(e, Function)]
        variable_elements = [e for e in result.elements if isinstance(e, Variable)]

        assert len(markup_elements) == 1
        assert len(style_elements) == 1
        assert len(function_elements) == 1
        assert len(variable_elements) == 1

    def test_element_classification_system(self):
        """Test element classification system for HTML/CSS"""
        # HTML element classifications
        html_elements = [
            MarkupElement(name="div", start_line=1, end_line=1, tag_name="div", element_class="structure"),
            MarkupElement(name="h1", start_line=2, end_line=2, tag_name="h1", element_class="heading"),
            MarkupElement(name="p", start_line=3, end_line=3, tag_name="p", element_class="text"),
            MarkupElement(name="img", start_line=4, end_line=4, tag_name="img", element_class="media"),
            MarkupElement(name="form", start_line=5, end_line=5, tag_name="form", element_class="form"),
            MarkupElement(name="table", start_line=6, end_line=6, tag_name="table", element_class="table"),
        ]

        # CSS element classifications
        css_elements = [
            StyleElement(name="body", start_line=1, end_line=1, selector="body", element_class="layout"),
            StyleElement(name="h1", start_line=2, end_line=2, selector="h1", element_class="typography"),
            StyleElement(name=".red", start_line=3, end_line=3, selector=".red", element_class="color"),
        ]

        # Verify classifications
        assert html_elements[0].element_class == "structure"
        assert html_elements[1].element_class == "heading"
        assert html_elements[2].element_class == "text"
        assert html_elements[3].element_class == "media"
        assert html_elements[4].element_class == "form"
        assert html_elements[5].element_class == "table"

        assert css_elements[0].element_class == "layout"
        assert css_elements[1].element_class == "typography"
        assert css_elements[2].element_class == "color"

    def test_element_serialization_compatibility(self):
        """Test that new elements work with existing serialization methods"""
        markup_element = MarkupElement(
            name="article",
            start_line=1,
            end_line=10,
            tag_name="article",
            attributes={"class": "post", "id": "post-1"},
            element_class="structure"
        )

        style_element = StyleElement(
            name=".post",
            start_line=15,
            end_line=20,
            selector=".post",
            properties={"margin": "20px", "padding": "15px"},
            element_class="layout"
        )

        result = AnalysisResult(
            file_path="blog.html",
            language="html",
            line_count=25,
            elements=[markup_element, style_element],
            node_count=2,
            query_results={},
            source_code="<article>content</article>",
            success=True
        )

        # Test serialization methods
        dict_result = result.to_dict()
        assert isinstance(dict_result, dict)
        assert "file_path" in dict_result

        summary_result = result.to_summary_dict()
        assert isinstance(summary_result, dict)
        assert "summary_elements" in summary_result

        mcp_result = result.to_mcp_format()
        assert isinstance(mcp_result, dict)
        assert "structure" in mcp_result

        json_result = result.to_json()
        assert isinstance(json_result, dict)


class TestElementTypeConstants:
    """Test element type constants and utilities"""

    def test_element_type_detection(self):
        """Test element type detection for new models"""
        markup_element = MarkupElement(
            name="div",
            start_line=1,
            end_line=1,
            tag_name="div"
        )

        style_element = StyleElement(
            name=".container",
            start_line=1,
            end_line=1,
            selector=".container"
        )

        assert markup_element.element_type == "html_element"
        assert style_element.element_type == "css_rule"

    def test_element_summary_items(self):
        """Test summary item generation for new elements"""
        markup_element = MarkupElement(
            name="nav",
            start_line=5,
            end_line=15,
            tag_name="nav",
            element_class="structure"
        )

        style_element = StyleElement(
            name="nav",
            start_line=20,
            end_line=25,
            selector="nav",
            element_class="layout"
        )

        markup_summary = markup_element.to_summary_item()
        style_summary = style_element.to_summary_item()

        # Verify markup summary structure
        assert markup_summary["name"] == "nav"
        assert markup_summary["tag_name"] == "nav"
        assert markup_summary["type"] == "html_element"
        assert markup_summary["element_class"] == "structure"
        assert markup_summary["lines"]["start"] == 5
        assert markup_summary["lines"]["end"] == 15

        # Verify style summary structure
        assert style_summary["name"] == "nav"
        assert style_summary["selector"] == "nav"
        assert style_summary["type"] == "css_rule"
        assert style_summary["element_class"] == "layout"
        assert style_summary["lines"]["start"] == 20
        assert style_summary["lines"]["end"] == 25


class TestEdgeCases:
    """Test edge cases and error conditions for extended models"""

    def test_markup_element_empty_attributes(self):
        """Test MarkupElement with empty attributes"""
        element = MarkupElement(
            name="br",
            start_line=1,
            end_line=1,
            tag_name="br",
            attributes={}
        )

        assert element.attributes == {}
        summary = element.to_summary_item()
        assert "tag_name" in summary

    def test_style_element_empty_properties(self):
        """Test StyleElement with empty properties"""
        element = StyleElement(
            name="*",
            start_line=1,
            end_line=1,
            selector="*",
            properties={}
        )

        assert element.properties == {}
        summary = element.to_summary_item()
        assert "selector" in summary

    def test_circular_reference_prevention(self):
        """Test that circular references are handled properly"""
        parent = MarkupElement(
            name="div",
            start_line=1,
            end_line=10,
            tag_name="div"
        )

        child = MarkupElement(
            name="span",
            start_line=2,
            end_line=5,
            tag_name="span",
            parent=parent
        )

        parent.children = [child]

        # Verify parent-child relationship
        assert child.parent == parent
        assert parent.children[0] == child

        # Ensure no circular reference in parent
        assert parent.parent is None

    def test_deep_nesting_hierarchy(self):
        """Test deeply nested element hierarchy"""
        root = MarkupElement(name="html", start_line=1, end_line=100, tag_name="html")
        body = MarkupElement(name="body", start_line=5, end_line=95, tag_name="body", parent=root)
        div = MarkupElement(name="div", start_line=10, end_line=90, tag_name="div", parent=body)
        section = MarkupElement(name="section", start_line=15, end_line=85, tag_name="section", parent=div)
        article = MarkupElement(name="article", start_line=20, end_line=80, tag_name="article", parent=section)

        root.children = [body]
        body.children = [div]
        div.children = [section]
        section.children = [article]

        # Verify hierarchy
        assert article.parent == section
        assert section.parent == div
        assert div.parent == body
        assert body.parent == root
        assert root.parent is None

        # Verify children
        assert len(root.children) == 1
        assert len(body.children) == 1
        assert len(div.children) == 1
        assert len(section.children) == 1
        assert len(article.children) == 0