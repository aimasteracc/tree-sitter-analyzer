#!/usr/bin/env python3
"""
Markdown Query Definitions

Tree-sitter queries for extracting Markdown elements including headers,
links, code blocks, lists, and other structural elements.
"""

from typing import Dict, List

# Markdown element extraction queries
MARKDOWN_QUERIES: Dict[str, str] = {
    # Headers (H1-H6)
    "headers": """
    (atx_heading
        (atx_h1_marker) @h1.marker
        heading_content: (inline) @h1.content) @h1.heading
    
    (atx_heading
        (atx_h2_marker) @h2.marker
        heading_content: (inline) @h2.content) @h2.heading
    
    (atx_heading
        (atx_h3_marker) @h3.marker
        heading_content: (inline) @h3.content) @h3.heading
    
    (atx_heading
        (atx_h4_marker) @h4.marker
        heading_content: (inline) @h4.content) @h4.heading
    
    (atx_heading
        (atx_h5_marker) @h5.marker
        heading_content: (inline) @h5.content) @h5.heading
    
    (atx_heading
        (atx_h6_marker) @h6.marker
        heading_content: (inline) @h6.content) @h6.heading
    
    (setext_heading
        heading_content: (paragraph) @setext.content
        (setext_h1_underline) @setext.h1) @setext.h1.heading
    
    (setext_heading
        heading_content: (paragraph) @setext.content
        (setext_h2_underline) @setext.h2) @setext.h2.heading
    """,
    
    # Code blocks
    "code_blocks": """
    (fenced_code_block
        (fenced_code_block_delimiter) @code.start
        (info_string)? @code.language
        (code_fence_content) @code.content
        (fenced_code_block_delimiter) @code.end) @code.block
    
    (indented_code_block
        (code_fence_content) @indented_code.content) @indented_code.block
    """,
    
    # Inline code
    "inline_code": """
    (code_span
        (code_span_delimiter) @inline_code.start
        (code_span_content) @inline_code.content
        (code_span_delimiter) @inline_code.end) @inline_code.span
    """,
    
    # Links
    "links": """
    (link
        (link_text) @link.text
        (link_destination) @link.url
        (link_title)? @link.title) @link.element
    
    (autolink
        (uri_autolink) @autolink.uri) @autolink.element
    
    (autolink
        (email_autolink) @autolink.email) @autolink.element
    
    (reference_link
        (link_text) @ref_link.text
        (link_label) @ref_link.label) @ref_link.element
    
    (link_reference_definition
        (link_label) @link_def.label
        (link_destination) @link_def.url
        (link_title)? @link_def.title) @link_def.element
    """,
    
    # Images
    "images": """
    (image
        (image_description) @image.alt
        (link_destination) @image.url
        (link_title)? @image.title) @image.element
    
    (reference_image
        (image_description) @ref_image.alt
        (link_label) @ref_image.label) @ref_image.element
    """,
    
    # Lists
    "lists": """
    (list
        (list_item
            (list_marker) @list_item.marker
            (paragraph)? @list_item.content) @list_item.element) @list.element
    
    (tight_list
        (list_item
            (list_marker) @tight_list_item.marker
            (paragraph)? @tight_list_item.content) @tight_list_item.element) @tight_list.element
    """,
    
    # Emphasis and strong
    "emphasis": """
    (emphasis
        (emphasis_delimiter) @emphasis.start
        (inline) @emphasis.content
        (emphasis_delimiter) @emphasis.end) @emphasis.element
    
    (strong_emphasis
        (strong_emphasis_delimiter) @strong.start
        (inline) @strong.content
        (strong_emphasis_delimiter) @strong.end) @strong.element
    """,
    
    # Blockquotes
    "blockquotes": """
    (block_quote
        (block_quote_marker) @blockquote.marker
        (paragraph) @blockquote.content) @blockquote.element
    """,
    
    # Tables
    "tables": """
    (pipe_table
        (pipe_table_header
            (pipe_table_cell) @table_header.cell) @table.header
        (pipe_table_delimiter_row) @table.delimiter
        (pipe_table_row
            (pipe_table_cell) @table_row.cell) @table.row) @table.element
    """,
    
    # Horizontal rules
    "horizontal_rules": """
    (thematic_break) @hr.element
    """,
    
    # HTML blocks
    "html_blocks": """
    (html_block) @html.block
    """,
    
    # Inline HTML
    "inline_html": """
    (html_tag) @html.inline
    """,
    
    # Strikethrough (if supported)
    "strikethrough": """
    (strikethrough
        (strikethrough_delimiter) @strike.start
        (inline) @strike.content
        (strikethrough_delimiter) @strike.end) @strike.element
    """,
    
    # Task lists (if supported)
    "task_lists": """
    (list_item
        (list_marker) @task.marker
        (task_list_marker_checked) @task.checked) @task.checked_item
    
    (list_item
        (list_marker) @task.marker
        (task_list_marker_unchecked) @task.unchecked) @task.unchecked_item
    """,
    
    # Footnotes
    "footnotes": """
    (footnote_reference
        (footnote_label) @footnote.ref_label) @footnote.reference
    
    (footnote_definition
        (footnote_label) @footnote.def_label
        (paragraph) @footnote.content) @footnote.definition
    """,
    
    # All text content
    "text_content": """
    (paragraph
        (inline) @text.content) @text.paragraph
    
    (inline) @text.inline
    """,
    
    # Document structure
    "document": """
    (document) @document.root
    """,
    
    # All elements (comprehensive)
    "all_elements": """
    (atx_heading) @element.heading
    (setext_heading) @element.heading
    (fenced_code_block) @element.code_block
    (indented_code_block) @element.code_block
    (code_span) @element.inline_code
    (link) @element.link
    (autolink) @element.autolink
    (reference_link) @element.ref_link
    (image) @element.image
    (reference_image) @element.ref_image
    (list) @element.list
    (tight_list) @element.list
    (emphasis) @element.emphasis
    (strong_emphasis) @element.strong
    (strikethrough) @element.strikethrough
    (block_quote) @element.blockquote
    (pipe_table) @element.table
    (thematic_break) @element.hr
    (html_block) @element.html_block
    (html_tag) @element.html_inline
    (footnote_reference) @element.footnote_ref
    (footnote_definition) @element.footnote_def
    (paragraph) @element.paragraph
    """,
}

# Query aliases for convenience
QUERY_ALIASES: Dict[str, str] = {
    "heading": "headers",
    "h1": "headers",
    "h2": "headers", 
    "h3": "headers",
    "h4": "headers",
    "h5": "headers",
    "h6": "headers",
    "code": "code_blocks",
    "fenced_code": "code_blocks",
    "code_span": "inline_code",
    "link": "links",
    "url": "links",
    "image": "images",
    "img": "images",
    "list": "lists",
    "ul": "lists",
    "ol": "lists",
    "em": "emphasis",
    "strong": "emphasis",
    "bold": "emphasis",
    "italic": "emphasis",
    "quote": "blockquotes",
    "blockquote": "blockquotes",
    "table": "tables",
    "hr": "horizontal_rules",
    "html": "html_blocks",
    "strike": "strikethrough",
    "task": "task_lists",
    "todo": "task_lists",
    "footnote": "footnotes",
    "note": "footnotes",
    "text": "text_content",
    "paragraph": "text_content",
    "all": "all_elements",
    "everything": "all_elements",
}

def get_query(query_name: str) -> str:
    """
    Get a query by name, supporting aliases
    
    Args:
        query_name: Name of the query or alias
        
    Returns:
        Query string
        
    Raises:
        KeyError: If query name is not found
    """
    # Check direct queries first
    if query_name in MARKDOWN_QUERIES:
        return MARKDOWN_QUERIES[query_name]
    
    # Check aliases
    if query_name in QUERY_ALIASES:
        actual_query = QUERY_ALIASES[query_name]
        return MARKDOWN_QUERIES[actual_query]
    
    raise KeyError(f"Unknown query: {query_name}")

def get_available_queries() -> List[str]:
    """
    Get list of all available query names including aliases
    
    Returns:
        List of query names
    """
    queries = list(MARKDOWN_QUERIES.keys())
    aliases = list(QUERY_ALIASES.keys())
    return sorted(queries + aliases)

def get_query_info(query_name: str) -> Dict[str, str]:
    """
    Get information about a query
    
    Args:
        query_name: Name of the query
        
    Returns:
        Dictionary with query information
    """
    try:
        query_string = get_query(query_name)
        is_alias = query_name in QUERY_ALIASES
        actual_name = QUERY_ALIASES.get(query_name, query_name) if is_alias else query_name
        
        return {
            "name": query_name,
            "actual_name": actual_name,
            "is_alias": is_alias,
            "query": query_string,
            "description": _get_query_description(actual_name)
        }
    except KeyError:
        return {"error": f"Query '{query_name}' not found"}

def _get_query_description(query_name: str) -> str:
    """Get description for a query"""
    descriptions = {
        "headers": "Extract all heading elements (H1-H6, both ATX and Setext styles)",
        "code_blocks": "Extract fenced and indented code blocks",
        "inline_code": "Extract inline code spans",
        "links": "Extract all types of links (inline, reference, autolinks)",
        "images": "Extract image elements (inline and reference)",
        "lists": "Extract ordered and unordered lists",
        "emphasis": "Extract emphasis and strong emphasis elements",
        "blockquotes": "Extract blockquote elements",
        "tables": "Extract pipe table elements",
        "horizontal_rules": "Extract horizontal rule elements",
        "html_blocks": "Extract HTML block elements",
        "inline_html": "Extract inline HTML elements",
        "strikethrough": "Extract strikethrough elements",
        "task_lists": "Extract task list items (checkboxes)",
        "footnotes": "Extract footnote references and definitions",
        "text_content": "Extract all text content",
        "document": "Extract document root",
        "all_elements": "Extract all Markdown elements"
    }
    return descriptions.get(query_name, "No description available")

def get_all_queries() -> dict[str, str]:
    """
    Get all queries for the query loader
    
    Returns:
        Dictionary mapping query names to query strings
    """
    # Combine direct queries and aliases
    all_queries = MARKDOWN_QUERIES.copy()
    
    # Add aliases that point to actual queries
    for alias, target in QUERY_ALIASES.items():
        if target in MARKDOWN_QUERIES:
            all_queries[alias] = MARKDOWN_QUERIES[target]
    
    return all_queries

# Export main functions and constants
__all__ = [
    "MARKDOWN_QUERIES",
    "QUERY_ALIASES",
    "get_query",
    "get_available_queries",
    "get_query_info",
    "get_all_queries"
]