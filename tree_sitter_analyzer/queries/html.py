#!/usr/bin/env python3
"""
HTML Language Queries

Comprehensive Tree-sitter queries for HTML language constructs.
Covers HTML elements, attributes, text content, comments, and embedded scripts/styles.
Designed to provide complete HTML parsing support for the tree-sitter analyzer.
"""

# HTML-specific query library
HTML_QUERIES: dict[str, str] = {
    # --- HTML Document Structure ---
    "document": """
    (document) @document
    """,
    
    "doctype": """
    (doctype) @doctype
    """,
    
    "html_element": """
    (element) @html_element
    """,
    
    # --- HTML Elements (as Functions) ---
    "element": """
    (element
        (start_tag
            (tag_name) @tag_name) @start_tag
        (end_tag)? @end_tag) @element
    """,
    
    "self_closing_element": """
    (self_closing_tag
        (tag_name) @tag_name) @self_closing_element
    """,
    
    "void_element": """
    (element
        (start_tag
            (tag_name) @tag_name) @start_tag
        (#match? @tag_name "^(area|base|br|col|embed|hr|img|input|link|meta|param|source|track|wbr)$")) @void_element
    """,
    
    # --- Specific HTML Elements ---
    "head_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "head")) @start_tag) @head_element
    """,
    
    "body_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "body")) @start_tag) @body_element
    """,
    
    "title_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "title")) @start_tag
        (text)? @title_text) @title_element
    """,
    
    "meta_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "meta")
            (attribute)*) @start_tag) @meta_element
    """,
    
    "link_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "link")
            (attribute)*) @start_tag) @link_element
    """,
    
    "script_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "script")
            (attribute)*) @start_tag
        (raw_text)? @script_content) @script_element
    """,
    
    "style_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "style")
            (attribute)*) @start_tag
        (raw_text)? @style_content) @style_element
    """,
    
    # --- Heading Elements ---
    "heading": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#match? @tag_name "^h[1-6]$")) @start_tag
        (text)? @heading_text) @heading
    """,
    
    "h1": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "h1")) @start_tag
        (text)? @heading_text) @h1
    """,
    
    "h2": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "h2")) @start_tag
        (text)? @heading_text) @h2
    """,
    
    "h3": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "h3")) @start_tag
        (text)? @heading_text) @h3
    """,
    
    # --- Form Elements ---
    "form_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "form")
            (attribute)*) @start_tag) @form_element
    """,
    
    "input_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "input")
            (attribute)*) @start_tag) @input_element
    """,
    
    "textarea_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "textarea")
            (attribute)*) @start_tag
        (text)? @textarea_text) @textarea_element
    """,
    
    "select_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "select")
            (attribute)*) @start_tag) @select_element
    """,
    
    "button_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "button")
            (attribute)*) @start_tag
        (text)? @button_text) @button_element
    """,
    
    "label_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "label")
            (attribute)*) @start_tag
        (text)? @label_text) @label_element
    """,
    
    # --- Media Elements ---
    "img_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "img")
            (attribute)*) @start_tag) @img_element
    """,
    
    "video_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "video")
            (attribute)*) @start_tag) @video_element
    """,
    
    "audio_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "audio")
            (attribute)*) @start_tag) @audio_element
    """,
    
    # --- Link and Navigation ---
    "anchor_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "a")
            (attribute)*) @start_tag
        (text)? @link_text) @anchor_element
    """,
    
    "nav_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "nav")) @start_tag) @nav_element
    """,
    
    # --- Semantic Elements ---
    "header_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "header")) @start_tag) @header_element
    """,
    
    "footer_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "footer")) @start_tag) @footer_element
    """,
    
    "main_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "main")) @start_tag) @main_element
    """,
    
    "section_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "section")) @start_tag) @section_element
    """,
    
    "article_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "article")) @start_tag) @article_element
    """,
    
    "aside_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "aside")) @start_tag) @aside_element
    """,
    
    # --- Table Elements ---
    "table_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "table")) @start_tag) @table_element
    """,
    
    "tr_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "tr")) @start_tag) @tr_element
    """,
    
    "td_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "td")
            (attribute)*) @start_tag
        (text)? @cell_text) @td_element
    """,
    
    "th_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "th")
            (attribute)*) @start_tag
        (text)? @header_text) @th_element
    """,
    
    # --- List Elements ---
    "ul_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "ul")) @start_tag) @ul_element
    """,
    
    "ol_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "ol")) @start_tag) @ol_element
    """,
    
    "li_element": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#eq? @tag_name "li")) @start_tag
        (text)? @list_text) @li_element
    """,
    
    # --- HTML Attributes (as Variables) ---
    "attribute": """
    (attribute
        (attribute_name) @attr_name
        (quoted_attribute_value
            (attribute_value) @attr_value)?) @attribute
    """,
    
    "id_attribute": """
    (attribute
        (attribute_name) @attr_name
        (#eq? @attr_name "id")
        (quoted_attribute_value
            (attribute_value) @id_value)) @id_attribute
    """,
    
    "class_attribute": """
    (attribute
        (attribute_name) @attr_name
        (#eq? @attr_name "class")
        (quoted_attribute_value
            (attribute_value) @class_value)) @class_attribute
    """,
    
    "src_attribute": """
    (attribute
        (attribute_name) @attr_name
        (#eq? @attr_name "src")
        (quoted_attribute_value
            (attribute_value) @src_value)) @src_attribute
    """,
    
    "href_attribute": """
    (attribute
        (attribute_name) @attr_name
        (#eq? @attr_name "href")
        (quoted_attribute_value
            (attribute_value) @href_value)) @href_attribute
    """,
    
    "alt_attribute": """
    (attribute
        (attribute_name) @attr_name
        (#eq? @attr_name "alt")
        (quoted_attribute_value
            (attribute_value) @alt_value)) @alt_attribute
    """,
    
    "type_attribute": """
    (attribute
        (attribute_name) @attr_name
        (#eq? @attr_name "type")
        (quoted_attribute_value
            (attribute_value) @type_value)) @type_attribute
    """,
    
    "name_attribute": """
    (attribute
        (attribute_name) @attr_name
        (#eq? @attr_name "name")
        (quoted_attribute_value
            (attribute_value) @name_value)) @name_attribute
    """,
    
    "value_attribute": """
    (attribute
        (attribute_name) @attr_name
        (#eq? @attr_name "value")
        (quoted_attribute_value
            (attribute_value) @value_value)) @value_attribute
    """,
    
    # --- Text Content ---
    "text_content": """
    (text) @text_content
    """,
    
    "raw_text": """
    (raw_text) @raw_text
    """,
    
    # --- Comments (as Imports for uniformity) ---
    "comment": """
    (comment) @comment
    """,
    
    # --- Error Recovery ---
    "erroneous_end_tag": """
    (erroneous_end_tag) @error_tag
    """,
    
    # --- Advanced Queries ---
    
    # All elements with specific attributes
    "elements_with_id": """
    (element
        (start_tag
            (attribute
                (attribute_name) @attr_name
                (#eq? @attr_name "id")))) @element_with_id
    """,
    
    "elements_with_class": """
    (element
        (start_tag
            (attribute
                (attribute_name) @attr_name
                (#eq? @attr_name "class")))) @element_with_class
    """,
    
    # Interactive elements
    "interactive_elements": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#match? @tag_name "^(a|button|input|textarea|select|details|summary)$"))) @interactive_element
    """,
    
    # Form controls
    "form_controls": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#match? @tag_name "^(input|textarea|select|button)$"))) @form_control
    """,
    
    # Media elements
    "media_elements": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#match? @tag_name "^(img|video|audio|picture|source|track)$"))) @media_element
    """,
    
    # Semantic elements
    "semantic_elements": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#match? @tag_name "^(header|footer|main|section|article|aside|nav|figure|figcaption)$"))) @semantic_element
    """,
    
    # Block level elements
    "block_elements": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#match? @tag_name "^(div|p|h[1-6]|ul|ol|li|table|form|fieldset|blockquote|pre|address)$"))) @block_element
    """,
    
    # Inline elements
    "inline_elements": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#match? @tag_name "^(span|a|strong|em|b|i|u|small|mark|del|ins|sub|sup|code|kbd|samp|var|abbr|dfn|time|data)$"))) @inline_element
    """,
    
    # Custom elements (web components)
    "custom_elements": """
    (element
        (start_tag
            (tag_name) @tag_name
            (#match? @tag_name "^[a-z]+-[a-z-]+$"))) @custom_element
    """,
}

# HTML query aliases for compatibility
HTML_QUERY_ALIASES: dict[str, str] = {
    # Element type aliases
    "elements": "element",
    "tags": "element",
    "html_tags": "element",
    
    # Function equivalents (elements as functions)
    "functions": "element",
    "methods": "element",
    "function": "element",
    "method": "element",
    
    # Variable equivalents (attributes as variables)
    "variables": "attribute",
    "attrs": "attribute",
    "attributes": "attribute",
    "fields": "attribute",
    "properties": "attribute",
    
    # Import equivalents (comments and external resources)
    "imports": "comment",
    "comments": "comment",
    "includes": "link_element",
    
    # Class equivalents (embedded content)
    "classes": "script_element",
    "scripts": "script_element",
    "styles": "style_element",
    
    # Content aliases
    "text": "text_content",
    "content": "text_content",
    
    # Specific element type shortcuts
    "headings": "heading",
    "forms": "form_element",
    "images": "img_element",
    "links": "anchor_element",
    "tables": "table_element",
    "lists": "ul_element",
    
    # Semantic shortcuts
    "semantic": "semantic_elements",
    "interactive": "interactive_elements",
    "media": "media_elements",
    "blocks": "block_elements",
    "inline": "inline_elements",
}

# Define query categories for easier navigation
HTML_QUERY_CATEGORIES: dict[str, list[str]] = {
    "structure": [
        "document", "doctype", "html_element", "head_element", "body_element"
    ],
    "content": [
        "element", "text_content", "raw_text", "comment"
    ],
    "headings": [
        "heading", "h1", "h2", "h3"
    ],
    "forms": [
        "form_element", "input_element", "textarea_element", "select_element", 
        "button_element", "label_element"
    ],
    "media": [
        "img_element", "video_element", "audio_element"
    ],
    "navigation": [
        "anchor_element", "nav_element"
    ],
    "semantic": [
        "header_element", "footer_element", "main_element", "section_element",
        "article_element", "aside_element"
    ],
    "tables": [
        "table_element", "tr_element", "td_element", "th_element"
    ],
    "lists": [
        "ul_element", "ol_element", "li_element"
    ],
    "attributes": [
        "attribute", "id_attribute", "class_attribute", "src_attribute",
        "href_attribute", "alt_attribute", "type_attribute", "name_attribute", "value_attribute"
    ],
    "embedded": [
        "script_element", "style_element", "link_element", "meta_element"
    ],
    "advanced": [
        "elements_with_id", "elements_with_class", "interactive_elements",
        "form_controls", "media_elements", "semantic_elements", 
        "block_elements", "inline_elements", "custom_elements"
    ]
}

def get_html_query(query_name: str) -> str | None:
    """
    Get HTML query by name, supporting both direct queries and aliases.
    
    Args:
        query_name: Name of the query or alias
        
    Returns:
        Query string if found, None otherwise
    """
    # Check direct queries first
    if query_name in HTML_QUERIES:
        return HTML_QUERIES[query_name]
    
    # Check aliases
    if query_name in HTML_QUERY_ALIASES:
        actual_query = HTML_QUERY_ALIASES[query_name]
        return HTML_QUERIES.get(actual_query)
    
    return None

def list_html_queries() -> list[str]:
    """
    Get list of all available HTML queries.
    
    Returns:
        List of query names
    """
    return list(HTML_QUERIES.keys())

def list_html_query_aliases() -> list[str]:
    """
    Get list of all available HTML query aliases.
    
    Returns:
        List of alias names
    """
    return list(HTML_QUERY_ALIASES.keys())

def get_html_query_categories() -> dict[str, list[str]]:
    """
    Get HTML queries organized by categories.
    
    Returns:
        Dictionary mapping category names to lists of query names
    """
    return HTML_QUERY_CATEGORIES.copy()

def search_html_queries(pattern: str) -> list[str]:
    """
    Search for HTML queries matching a pattern.
    
    Args:
        pattern: Pattern to search for in query names
        
    Returns:
        List of matching query names
    """
    pattern_lower = pattern.lower()
    matches = []
    
    # Search in direct queries
    for query_name in HTML_QUERIES:
        if pattern_lower in query_name.lower():
            matches.append(query_name)
    
    # Search in aliases
    for alias_name in HTML_QUERY_ALIASES:
        if pattern_lower in alias_name.lower():
            matches.append(f"{alias_name} (alias)")
    
    return matches