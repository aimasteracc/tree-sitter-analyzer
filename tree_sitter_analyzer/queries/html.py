#!/usr/bin/env python3
"""
HTML Language Queries

Comprehensive Tree-sitter queries for HTML language constructs.
Covers elements, attributes, text content, and document structure.
"""

# HTML-specific query library
HTML_QUERIES: dict[str, str] = {
    # --- Basic Elements ---
    "element": """
    (element) @element
    """,
    "start_tag": """
    (start_tag
        name: (tag_name) @tag_name) @start_tag
    """,
    "end_tag": """
    (end_tag
        name: (tag_name) @tag_name) @end_tag
    """,
    "self_closing_tag": """
    (self_closing_tag
        name: (tag_name) @tag_name) @self_closing_tag
    """,
    "void_element": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^(area|base|br|col|embed|hr|img|input|link|meta|param|source|track|wbr)$"))) @void_element
    """,
    # --- Attributes ---
    "attribute": """
    (attribute
        name: (attribute_name) @attribute_name
        value: (quoted_attribute_value)? @attribute_value) @attribute
    """,
    "attribute_name": """
    (attribute_name) @attribute_name
    """,
    "attribute_value": """
    (quoted_attribute_value) @attribute_value
    """,
    "class_attribute": """
    (attribute
        name: (attribute_name) @attr_name
        (#match? @attr_name "^class$")
        value: (quoted_attribute_value) @class_value) @class_attribute
    """,
    "id_attribute": """
    (attribute
        name: (attribute_name) @attr_name
        (#match? @attr_name "^id$")
        value: (quoted_attribute_value) @id_value) @id_attribute
    """,
    "src_attribute": """
    (attribute
        name: (attribute_name) @attr_name
        (#match? @attr_name "^src$")
        value: (quoted_attribute_value) @src_value) @src_attribute
    """,
    "href_attribute": """
    (attribute
        name: (attribute_name) @attr_name
        (#match? @attr_name "^href$")
        value: (quoted_attribute_value) @href_value) @href_attribute
    """,
    # --- Text Content ---
    "text": """
    (text) @text
    """,
    "raw_text": """
    (raw_text) @raw_text
    """,
    # --- Comments ---
    "comment": """
    (comment) @comment
    """,
    # --- Document Structure ---
    "doctype": """
    (doctype) @doctype
    """,
    "document": """
    (document) @document
    """,
    # --- Semantic Elements ---
    "heading": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^h[1-6]$"))) @heading
    """,
    "paragraph": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^p$"))) @paragraph
    """,
    "link": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^a$"))) @link
    """,
    "image": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^img$"))) @image
    """,
    "list": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^(ul|ol|dl)$"))) @list
    """,
    "list_item": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^(li|dt|dd)$"))) @list_item
    """,
    "table": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^table$"))) @table
    """,
    "table_row": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^tr$"))) @table_row
    """,
    "table_cell": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^(td|th)$"))) @table_cell
    """,
    # --- Structure Elements ---
    "html": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^html$"))) @html
    """,
    "head": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^head$"))) @head
    """,
    "body": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^body$"))) @body
    """,
    "header": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^header$"))) @header
    """,
    "footer": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^footer$"))) @footer
    """,
    "main": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^main$"))) @main
    """,
    "section": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^section$"))) @section
    """,
    "article": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^article$"))) @article
    """,
    "aside": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^aside$"))) @aside
    """,
    "nav": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^nav$"))) @nav
    """,
    "div": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^div$"))) @div
    """,
    "span": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^span$"))) @span
    """,
    # --- Form Elements ---
    "form": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^form$"))) @form
    """,
    "input": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^input$"))) @input
    """,
    "button": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^button$"))) @button
    """,
    "textarea": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^textarea$"))) @textarea
    """,
    "select": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^select$"))) @select
    """,
    "option": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^option$"))) @option
    """,
    "label": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^label$"))) @label
    """,
    "fieldset": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^fieldset$"))) @fieldset
    """,
    "legend": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^legend$"))) @legend
    """,
    # --- Media Elements ---
    "video": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^video$"))) @video
    """,
    "audio": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^audio$"))) @audio
    """,
    "source": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^source$"))) @source
    """,
    "track": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^track$"))) @track
    """,
    "canvas": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^canvas$"))) @canvas
    """,
    "svg": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^svg$"))) @svg
    """,
    # --- Meta Elements ---
    "meta": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^meta$"))) @meta
    """,
    "title": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^title$"))) @title
    """,
    "link_tag": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^link$"))) @link_tag
    """,
    "style": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^style$"))) @style
    """,
    "script": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^script$"))) @script
    """,
    "noscript": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^noscript$"))) @noscript
    """,
    "base": """
    (element
        (start_tag
            name: (tag_name) @tag_name
            (#match? @tag_name "^base$"))) @base
    """,
    # --- Script and Style Elements ---
    "script_element": """
    (script_element) @script_element
    """,
    "style_element": """
    (style_element) @style_element
    """,
    # --- Name-only Extraction ---
    "tag_name": """
    (tag_name) @tag_name
    """,
    "element_name": """
    (element
        (start_tag
            name: (tag_name) @element_name))
    """,
}

# Query descriptions
HTML_QUERY_DESCRIPTIONS: dict[str, str] = {
    "element": "Search all HTML elements",
    "start_tag": "Search start tags",
    "end_tag": "Search end tags",
    "self_closing_tag": "Search self-closing tags",
    "void_element": "Search void elements (br, img, input, etc.)",
    "attribute": "Search all attributes",
    "attribute_name": "Search attribute names",
    "attribute_value": "Search attribute values",
    "class_attribute": "Search class attributes",
    "id_attribute": "Search id attributes",
    "src_attribute": "Search src attributes",
    "href_attribute": "Search href attributes",
    "text": "Search text content",
    "raw_text": "Search raw text content",
    "comment": "Search HTML comments",
    "doctype": "Search DOCTYPE declarations",
    "document": "Search document root",
    "heading": "Search heading elements (h1-h6)",
    "paragraph": "Search paragraph elements",
    "link": "Search anchor elements",
    "image": "Search image elements",
    "list": "Search list elements (ul, ol, dl)",
    "list_item": "Search list item elements (li, dt, dd)",
    "table": "Search table elements",
    "table_row": "Search table row elements",
    "table_cell": "Search table cell elements (td, th)",
    "html": "Search html elements",
    "head": "Search head elements",
    "body": "Search body elements",
    "header": "Search header elements",
    "footer": "Search footer elements",
    "main": "Search main elements",
    "section": "Search section elements",
    "article": "Search article elements",
    "aside": "Search aside elements",
    "nav": "Search nav elements",
    "div": "Search div elements",
    "span": "Search span elements",
    "form": "Search form elements",
    "input": "Search input elements",
    "button": "Search button elements",
    "textarea": "Search textarea elements",
    "select": "Search select elements",
    "option": "Search option elements",
    "label": "Search label elements",
    "fieldset": "Search fieldset elements",
    "legend": "Search legend elements",
    "video": "Search video elements",
    "audio": "Search audio elements",
    "source": "Search source elements",
    "track": "Search track elements",
    "canvas": "Search canvas elements",
    "svg": "Search svg elements",
    "meta": "Search meta elements",
    "title": "Search title elements",
    "link_tag": "Search link elements",
    "style": "Search style elements",
    "script": "Search script elements",
    "noscript": "Search noscript elements",
    "base": "Search base elements",
    "script_element": "Search script elements with content",
    "style_element": "Search style elements with content",
    "tag_name": "Search tag names only",
    "element_name": "Search element names only",
}

# Legacy query definitions for backward compatibility
ELEMENTS = """
(element
    (start_tag
        name: (tag_name) @element.name)
    (text)? @element.text
    (end_tag)?) @element.full
"""

ATTRIBUTES = """
(attribute
    name: (attribute_name) @attribute.name
    value: (quoted_attribute_value)? @attribute.value) @attribute.full
"""

COMMENTS = """
(comment) @comment
"""

TEXT_CONTENT = """
(text) @text
"""

# Convert to ALL_QUERIES format for dynamic loader compatibility
ALL_QUERIES = {}
for query_name, query_string in HTML_QUERIES.items():
    description = HTML_QUERY_DESCRIPTIONS.get(query_name, "No description")
    ALL_QUERIES[query_name] = {"query": query_string, "description": description}

# Add legacy queries for backward compatibility
ALL_QUERIES["elements"] = {
    "query": ELEMENTS,
    "description": "Search all HTML elements with names and text",
}
ALL_QUERIES["attributes"] = {
    "query": ATTRIBUTES,
    "description": "Search all HTML attributes",
}
ALL_QUERIES["comments"] = {
    "query": COMMENTS,
    "description": "Search all HTML comments",
}
ALL_QUERIES["text_content"] = {
    "query": TEXT_CONTENT,
    "description": "Search all text content",
}


def get_html_query(name: str) -> str:
    """
    Get the specified HTML query

    Args:
        name: Query name

    Returns:
        Query string

    Raises:
        ValueError: When query is not found
    """
    if name not in HTML_QUERIES:
        available = list(HTML_QUERIES.keys())
        raise ValueError(f"HTML query '{name}' does not exist. Available: {available}")

    return HTML_QUERIES[name]


def get_html_query_description(name: str) -> str:
    """
    Get the description of the specified HTML query

    Args:
        name: Query name

    Returns:
        Query description
    """
    return HTML_QUERY_DESCRIPTIONS.get(name, "No description")


def get_query(name: str) -> str:
    """Get a specific query by name."""
    if name in ALL_QUERIES:
        return ALL_QUERIES[name]["query"]
    raise ValueError(
        f"Query '{name}' not found. Available queries: {list(ALL_QUERIES.keys())}"
    )


def get_all_queries() -> dict:
    """Get all available queries."""
    return ALL_QUERIES


def list_queries() -> list:
    """List all available query names."""
    return list(ALL_QUERIES.keys())


def get_available_html_queries() -> list[str]:
    """
    Get list of available HTML queries

    Returns:
        List of query names
    """
    return list(HTML_QUERIES.keys())
