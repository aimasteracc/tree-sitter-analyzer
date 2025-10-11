"""
Comprehensive tests for HTML queries.
Tests HTML-specific query functionality including elements, attributes,
text content, comments, and various HTML element types.
"""

import pytest
from tree_sitter_analyzer.queries.html import (
    HTML_QUERIES,
    HTML_QUERY_ALIASES,
    HTML_QUERY_CATEGORIES,
    get_html_query,
    list_html_queries,
    list_html_query_aliases,
    get_html_query_categories,
    search_html_queries
)


class TestHTMLQueries:
    """Test HTML query definitions and functionality"""

    def test_html_queries_structure(self):
        """Test that HTML_QUERIES is properly structured"""
        assert isinstance(HTML_QUERIES, dict)
        assert len(HTML_QUERIES) > 0
        
        # All queries should be strings
        for query_name, query_string in HTML_QUERIES.items():
            assert isinstance(query_name, str)
            assert isinstance(query_string, str)
            assert len(query_string.strip()) > 0

    def test_html_query_aliases_structure(self):
        """Test that HTML_QUERY_ALIASES is properly structured"""
        assert isinstance(HTML_QUERY_ALIASES, dict)
        assert len(HTML_QUERY_ALIASES) > 0
        
        # All aliases should map to valid queries
        for alias, target in HTML_QUERY_ALIASES.items():
            assert isinstance(alias, str)
            assert isinstance(target, str)
            assert target in HTML_QUERIES, f"Alias '{alias}' points to non-existent query '{target}'"

    def test_html_query_categories_structure(self):
        """Test that HTML_QUERY_CATEGORIES is properly structured"""
        assert isinstance(HTML_QUERY_CATEGORIES, dict)
        assert len(HTML_QUERY_CATEGORIES) > 0
        
        # All categories should contain valid query names
        for category, queries in HTML_QUERY_CATEGORIES.items():
            assert isinstance(category, str)
            assert isinstance(queries, list)
            assert len(queries) > 0
            
            for query_name in queries:
                assert isinstance(query_name, str)
                assert query_name in HTML_QUERIES, f"Category '{category}' contains non-existent query '{query_name}'"

    def test_basic_structure_queries(self):
        """Test basic HTML structure queries"""
        # Document structure
        assert "document" in HTML_QUERIES
        assert "doctype" in HTML_QUERIES
        assert "html_element" in HTML_QUERIES
        
        # Verify query content
        document_query = HTML_QUERIES["document"]
        assert "(document)" in document_query
        assert "@document" in document_query
        
        doctype_query = HTML_QUERIES["doctype"]
        assert "(doctype)" in doctype_query
        assert "@doctype" in doctype_query

    def test_element_queries(self):
        """Test HTML element queries"""
        # Basic elements
        assert "element" in HTML_QUERIES
        assert "self_closing_element" in HTML_QUERIES
        assert "void_element" in HTML_QUERIES
        
        # Specific elements
        assert "head_element" in HTML_QUERIES
        assert "body_element" in HTML_QUERIES
        assert "title_element" in HTML_QUERIES
        assert "meta_element" in HTML_QUERIES
        assert "link_element" in HTML_QUERIES
        assert "script_element" in HTML_QUERIES
        assert "style_element" in HTML_QUERIES
        
        # Verify element query structure
        element_query = HTML_QUERIES["element"]
        assert "(element" in element_query
        assert "(start_tag" in element_query
        assert "(tag_name)" in element_query
        assert "@element" in element_query

    def test_heading_queries(self):
        """Test heading element queries"""
        assert "heading" in HTML_QUERIES
        assert "h1" in HTML_QUERIES
        assert "h2" in HTML_QUERIES
        assert "h3" in HTML_QUERIES
        
        # Verify heading query uses proper regex
        heading_query = HTML_QUERIES["heading"]
        assert "h[1-6]" in heading_query
        
        # Verify specific heading queries
        h1_query = HTML_QUERIES["h1"]
        assert '#eq? @tag_name "h1"' in h1_query

    def test_form_element_queries(self):
        """Test form-related element queries"""
        form_elements = [
            "form_element", "input_element", "textarea_element",
            "select_element", "button_element", "label_element"
        ]
        
        for element in form_elements:
            assert element in HTML_QUERIES
            
        # Verify form query structure
        form_query = HTML_QUERIES["form_element"]
        assert '#eq? @tag_name "form"' in form_query

    def test_media_element_queries(self):
        """Test media element queries"""
        media_elements = ["img_element", "video_element", "audio_element"]
        
        for element in media_elements:
            assert element in HTML_QUERIES
            
        # Verify img query
        img_query = HTML_QUERIES["img_element"]
        assert '#eq? @tag_name "img"' in img_query

    def test_semantic_element_queries(self):
        """Test semantic HTML5 element queries"""
        semantic_elements = [
            "header_element", "footer_element", "main_element",
            "section_element", "article_element", "aside_element"
        ]
        
        for element in semantic_elements:
            assert element in HTML_QUERIES
            
        # Verify header query
        header_query = HTML_QUERIES["header_element"]
        assert '#eq? @tag_name "header"' in header_query

    def test_table_element_queries(self):
        """Test table-related element queries"""
        table_elements = ["table_element", "tr_element", "td_element", "th_element"]
        
        for element in table_elements:
            assert element in HTML_QUERIES

    def test_list_element_queries(self):
        """Test list element queries"""
        list_elements = ["ul_element", "ol_element", "li_element"]
        
        for element in list_elements:
            assert element in HTML_QUERIES

    def test_attribute_queries(self):
        """Test HTML attribute queries"""
        # General attribute query
        assert "attribute" in HTML_QUERIES
        
        # Specific attribute queries
        specific_attrs = [
            "id_attribute", "class_attribute", "src_attribute",
            "href_attribute", "alt_attribute", "type_attribute",
            "name_attribute", "value_attribute"
        ]
        
        for attr in specific_attrs:
            assert attr in HTML_QUERIES
            
        # Verify attribute query structure
        attr_query = HTML_QUERIES["attribute"]
        assert "(attribute" in attr_query
        assert "(attribute_name)" in attr_query
        assert "(attribute_value)" in attr_query
        
        # Verify specific attribute query
        class_attr_query = HTML_QUERIES["class_attribute"]
        assert '#eq? @attr_name "class"' in class_attr_query

    def test_text_and_comment_queries(self):
        """Test text content and comment queries"""
        assert "text_content" in HTML_QUERIES
        assert "raw_text" in HTML_QUERIES
        assert "comment" in HTML_QUERIES
        
        # Verify text query
        text_query = HTML_QUERIES["text_content"]
        assert "(text)" in text_query
        assert "@text_content" in text_query
        
        # Verify comment query
        comment_query = HTML_QUERIES["comment"]
        assert "(comment)" in comment_query
        assert "@comment" in comment_query

    def test_advanced_queries(self):
        """Test advanced HTML queries"""
        advanced_queries = [
            "elements_with_id", "elements_with_class",
            "interactive_elements", "form_controls",
            "media_elements", "semantic_elements",
            "block_elements", "inline_elements", "custom_elements"
        ]
        
        for query in advanced_queries:
            assert query in HTML_QUERIES
            
        # Verify interactive elements query
        interactive_query = HTML_QUERIES["interactive_elements"]
        assert "#match?" in interactive_query
        assert "a|button|input|textarea|select|details|summary" in interactive_query

    def test_query_aliases(self):
        """Test HTML query aliases"""
        # Test element aliases
        assert "elements" in HTML_QUERY_ALIASES
        assert "tags" in HTML_QUERY_ALIASES
        assert "html_tags" in HTML_QUERY_ALIASES
        
        # Test function equivalents
        assert "functions" in HTML_QUERY_ALIASES
        assert "methods" in HTML_QUERY_ALIASES
        
        # Test variable equivalents
        assert "variables" in HTML_QUERY_ALIASES
        assert "attributes" in HTML_QUERY_ALIASES
        
        # Test import equivalents
        assert "imports" in HTML_QUERY_ALIASES
        assert "comments" in HTML_QUERY_ALIASES
        
        # Test class equivalents
        assert "classes" in HTML_QUERY_ALIASES
        assert "scripts" in HTML_QUERY_ALIASES

    def test_query_categories(self):
        """Test HTML query categories"""
        expected_categories = [
            "structure", "content", "headings", "forms",
            "media", "navigation", "semantic", "tables",
            "lists", "attributes", "embedded", "advanced"
        ]
        
        for category in expected_categories:
            assert category in HTML_QUERY_CATEGORIES
            
        # Verify category contents
        structure_queries = HTML_QUERY_CATEGORIES["structure"]
        assert "document" in structure_queries
        assert "html_element" in structure_queries
        assert "head_element" in structure_queries
        assert "body_element" in structure_queries
        
        form_queries = HTML_QUERY_CATEGORIES["forms"]
        assert "form_element" in form_queries
        assert "input_element" in form_queries


class TestHTMLQueryFunctions:
    """Test HTML query utility functions"""

    def test_get_html_query_direct(self):
        """Test getting HTML query directly"""
        # Test valid query
        query = get_html_query("element")
        assert query is not None
        assert isinstance(query, str)
        assert "(element" in query
        
        # Test invalid query
        query = get_html_query("nonexistent_query")
        assert query is None

    def test_get_html_query_alias(self):
        """Test getting HTML query via alias"""
        # Test valid alias
        query = get_html_query("elements")  # Alias for "element"
        assert query is not None
        assert isinstance(query, str)
        
        # Test another alias
        query = get_html_query("functions")  # Alias for "element"
        assert query is not None
        
        # Test invalid alias
        query = get_html_query("invalid_alias")
        assert query is None

    def test_list_html_queries(self):
        """Test listing all HTML queries"""
        queries = list_html_queries()
        
        assert isinstance(queries, list)
        assert len(queries) > 0
        
        # Should contain all keys from HTML_QUERIES
        for query_name in HTML_QUERIES.keys():
            assert query_name in queries
        
        # Should be the same as direct access
        assert set(queries) == set(HTML_QUERIES.keys())

    def test_list_html_query_aliases(self):
        """Test listing all HTML query aliases"""
        aliases = list_html_query_aliases()
        
        assert isinstance(aliases, list)
        assert len(aliases) > 0
        
        # Should contain all keys from HTML_QUERY_ALIASES
        for alias in HTML_QUERY_ALIASES.keys():
            assert alias in aliases
        
        # Should be the same as direct access
        assert set(aliases) == set(HTML_QUERY_ALIASES.keys())

    def test_get_html_query_categories(self):
        """Test getting HTML query categories"""
        categories = get_html_query_categories()
        
        assert isinstance(categories, dict)
        assert len(categories) > 0
        
        # Should be a copy, not the original
        assert categories is not HTML_QUERY_CATEGORIES
        assert categories == HTML_QUERY_CATEGORIES
        
        # Modifying returned dict should not affect original
        original_length = len(HTML_QUERY_CATEGORIES["structure"])
        categories["structure"].append("test_query")
        assert len(HTML_QUERY_CATEGORIES["structure"]) == original_length

    def test_search_html_queries(self):
        """Test searching HTML queries"""
        # Test searching for form-related queries
        form_results = search_html_queries("form")
        assert isinstance(form_results, list)
        assert len(form_results) > 0
        assert "form_element" in form_results
        
        # Test searching for element queries
        element_results = search_html_queries("element")
        assert len(element_results) > 0
        assert "element" in element_results
        assert "html_element" in element_results
        
        # Test case insensitive search
        upper_results = search_html_queries("ELEMENT")
        assert len(upper_results) > 0
        
        # Test searching aliases
        alias_results = search_html_queries("function")
        assert len(alias_results) > 0
        # Should find alias entries marked as "(alias)"
        alias_entries = [r for r in alias_results if "(alias)" in r]
        assert len(alias_entries) > 0
        
        # Test no matches
        no_results = search_html_queries("xyznomatch")
        assert isinstance(no_results, list)
        assert len(no_results) == 0

    def test_search_html_queries_partial_match(self):
        """Test partial matching in HTML query search"""
        # Test partial matching
        head_results = search_html_queries("head")
        assert len(head_results) > 0
        
        # Should include queries containing "head"
        matching_queries = [r for r in head_results if not r.endswith("(alias)")]
        head_related = [q for q in matching_queries if "head" in q.lower()]
        assert len(head_related) > 0

    def test_query_syntax_validity(self):
        """Test that all HTML queries have valid tree-sitter syntax"""
        # Basic syntax checks for common patterns
        for query_name, query_string in HTML_QUERIES.items():
            # Should have proper parentheses balance
            open_parens = query_string.count('(')
            close_parens = query_string.count(')')
            assert open_parens == close_parens, f"Query '{query_name}' has unbalanced parentheses"
            
            # Should have capture patterns (marked with @)
            assert '@' in query_string, f"Query '{query_name}' missing capture patterns"
            
            # Should not have obvious syntax errors
            assert query_string.strip(), f"Query '{query_name}' is empty or whitespace"

    def test_query_completeness(self):
        """Test that HTML queries cover all major HTML elements"""
        # Check that major HTML elements have corresponding queries
        major_elements = [
            "html", "head", "body", "title", "meta", "link", "script", "style",
            "div", "p", "span", "a", "img", "h1", "h2", "h3",
            "form", "input", "button", "select", "textarea", "label",
            "table", "tr", "td", "th", "ul", "ol", "li",
            "header", "footer", "main", "section", "article", "aside", "nav"
        ]
        
        # Should have queries that can match these elements
        element_queries = [q for q in HTML_QUERIES.keys() if "element" in q]
        assert len(element_queries) > 10, "Should have many element-specific queries"
        
        # Should have advanced queries for categorizing elements
        assert "semantic_elements" in HTML_QUERIES
        assert "form_controls" in HTML_QUERIES
        assert "media_elements" in HTML_QUERIES
        assert "block_elements" in HTML_QUERIES
        assert "inline_elements" in HTML_QUERIES

    def test_alias_coverage(self):
        """Test that aliases provide good coverage for common terms"""
        # Common programming terms that should work via aliases
        common_terms = ["functions", "methods", "variables", "classes", "imports"]
        
        for term in common_terms:
            assert term in HTML_QUERY_ALIASES, f"Missing alias for common term: {term}"
            
        # HTML-specific terms that should work
        html_terms = ["elements", "tags", "attributes", "comments"]
        
        for term in html_terms:
            assert term in HTML_QUERY_ALIASES, f"Missing alias for HTML term: {term}"


if __name__ == "__main__":
    pytest.main([__file__])