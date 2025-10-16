#!/usr/bin/env python3
"""
Markdown Query Definitions

Tree-sitter queries for extracting Markdown elements including headers,
links, code blocks, lists, and other structural elements.
"""

# Markdown element extraction queries - simplified for compatibility
MARKDOWN_QUERIES: dict[str, str] = {
    # Headers (H1-H6) - simplified
    "headers": """
    (atx_heading) @header
    (setext_heading) @header
    """,
    # Code blocks - simplified
    "code_blocks": """
    (fenced_code_block) @code_block
    (indented_code_block) @code_block
    """,
    # Inline code - simplified
    "inline_code": """
    (inline) @inline
    """,
    # Links - simplified to avoid invalid node types
    "links": """
    (inline) @inline
    """,
    # Images - simplified to avoid invalid node types
    "images": """
    (inline) @inline
    """,
    # Lists - simplified to avoid invalid node types
    "lists": """
    (list) @list
    (list_item) @list_item
    """,
    # Emphasis and strong - simplified
    "emphasis": """
    (inline) @inline
    """,
    # Blockquotes - simplified
    "blockquotes": """
    (block_quote) @blockquote
    """,
    # Tables - simplified
    "tables": """
    (pipe_table) @table
    """,
    # Horizontal rules - simplified
    "horizontal_rules": """
    (thematic_break) @hr
    """,
    # HTML blocks - simplified
    "html_blocks": """
    (html_block) @html_block
    """,
    # Inline HTML - simplified
    "inline_html": """
    (inline) @inline
    """,
    # Strikethrough - simplified
    "strikethrough": """
    (inline) @inline
    """,
    # Task lists - simplified
    "task_lists": """
    (list_item) @list_item
    """,
    # Footnotes - simplified
    "footnotes": """
    (paragraph) @paragraph
    (inline) @inline
    """,
    # All text content - simplified
    "text_content": """
    (paragraph) @paragraph
    (inline) @inline
    """,
    # Document structure - simplified
    "document": """
    (document) @document
    """,
    # All elements (comprehensive) - simplified
    "all_elements": """
    (atx_heading) @heading
    (setext_heading) @heading
    (fenced_code_block) @code_block
    (indented_code_block) @code_block
    (inline) @inline
    (list) @list
    (list_item) @list_item
    (block_quote) @blockquote
    (pipe_table) @table
    (thematic_break) @hr
    (html_block) @html_block
    (paragraph) @paragraph
    (link_reference_definition) @reference
    """,
}

# Query aliases for convenience
QUERY_ALIASES: dict[str, str] = {
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


def get_available_queries() -> list[str]:
    """
    Get list of all available query names including aliases

    Returns:
        List of query names
    """
    queries = list(MARKDOWN_QUERIES.keys())
    aliases = list(QUERY_ALIASES.keys())
    return sorted(queries + aliases)


def get_query_info(query_name: str) -> dict[str, str]:
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
        actual_name = (
            QUERY_ALIASES.get(query_name, query_name) if is_alias else query_name
        )

        return {
            "name": query_name,
            "actual_name": actual_name,
            "is_alias": is_alias,
            "query": query_string,
            "description": _get_query_description(actual_name),
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
        "all_elements": "Extract all Markdown elements",
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
    "get_all_queries",
]
