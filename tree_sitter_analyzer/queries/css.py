#!/usr/bin/env python3
"""
CSS Language Queries

Comprehensive Tree-sitter queries for CSS language constructs.
Covers selectors, properties, rules, at-rules, and CSS features.
"""

# CSS-specific query library
CSS_QUERIES: dict[str, str] = {
    # --- Basic Rules ---
    "rule_set": """
    (rule_set) @rule_set
    """,
    "rule": """
    (rule_set
        selectors: (selectors) @selectors
        block: (block) @block) @rule
    """,
    "declaration": """
    (declaration
        property: (property_name) @property_name
        value: (_) @property_value) @declaration
    """,
    "property": """
    (property_name) @property
    """,
    "property_name": """
    (property_name) @property_name
    """,
    "property_value": """
    (declaration
        value: (_) @property_value)
    """,
    # --- Selectors ---
    "selector": """
    (selectors
        (selector) @selector)
    """,
    "selectors": """
    (selectors) @selectors
    """,
    "class_selector": """
    (class_selector) @class_selector
    """,
    "id_selector": """
    (id_selector) @id_selector
    """,
    "tag_selector": """
    (tag_name) @tag_selector
    """,
    "universal_selector": """
    (universal_selector) @universal_selector
    """,
    "attribute_selector": """
    (attribute_selector) @attribute_selector
    """,
    "pseudo_class_selector": """
    (pseudo_class_selector) @pseudo_class_selector
    """,
    "pseudo_element_selector": """
    (pseudo_element_selector) @pseudo_element_selector
    """,
    "descendant_selector": """
    (descendant_selector) @descendant_selector
    """,
    "child_selector": """
    (child_selector) @child_selector
    """,
    "sibling_selector": """
    (sibling_selector) @sibling_selector
    """,
    "adjacent_sibling_selector": """
    (adjacent_sibling_selector) @adjacent_sibling_selector
    """,
    # --- At-Rules ---
    "at_rule": """
    (at_rule) @at_rule
    """,
    "import_statement": """
    (import_statement) @import_statement
    """,
    "media_statement": """
    (media_statement) @media_statement
    """,
    "charset_statement": """
    (charset_statement) @charset_statement
    """,
    "namespace_statement": """
    (namespace_statement) @namespace_statement
    """,
    "keyframes_statement": """
    (keyframes_statement) @keyframes_statement
    """,
    "supports_statement": """
    (supports_statement) @supports_statement
    """,
    "page_statement": """
    (page_statement) @page_statement
    """,
    "font_face_statement": """
    (font_face_statement) @font_face_statement
    """,
    # --- Media Queries ---
    "media_query": """
    (media_query) @media_query
    """,
    "media_feature": """
    (media_feature) @media_feature
    """,
    "media_type": """
    (media_type) @media_type
    """,
    # --- Values ---
    "string_value": """
    (string_value) @string_value
    """,
    "integer_value": """
    (integer_value) @integer_value
    """,
    "float_value": """
    (float_value) @float_value
    """,
    "color_value": """
    (color_value) @color_value
    """,
    "call_expression": """
    (call_expression) @call_expression
    """,
    "function_name": """
    (call_expression
        function: (function_name) @function_name)
    """,
    "arguments": """
    (call_expression
        arguments: (arguments) @arguments)
    """,
    "url": """
    (call_expression
        function: (function_name) @func_name
        (#match? @func_name "^url$")
        arguments: (arguments) @url_args) @url
    """,
    "calc": """
    (call_expression
        function: (function_name) @func_name
        (#match? @func_name "^calc$")
        arguments: (arguments) @calc_args) @calc
    """,
    "var": """
    (call_expression
        function: (function_name) @func_name
        (#match? @func_name "^var$")
        arguments: (arguments) @var_args) @var
    """,
    "rgb": """
    (call_expression
        function: (function_name) @func_name
        (#match? @func_name "^rgb$")
        arguments: (arguments) @rgb_args) @rgb
    """,
    "rgba": """
    (call_expression
        function: (function_name) @func_name
        (#match? @func_name "^rgba$")
        arguments: (arguments) @rgba_args) @rgba
    """,
    "hsl": """
    (call_expression
        function: (function_name) @func_name
        (#match? @func_name "^hsl$")
        arguments: (arguments) @hsl_args) @hsl
    """,
    "hsla": """
    (call_expression
        function: (function_name) @func_name
        (#match? @func_name "^hsla$")
        arguments: (arguments) @hsla_args) @hsla
    """,
    # --- Units ---
    "dimension": """
    (dimension) @dimension
    """,
    "percentage": """
    (percentage) @percentage
    """,
    "unit": """
    (dimension
        unit: (unit) @unit)
    """,
    # --- Layout Properties ---
    "display": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^display$")
        value: (_) @display_value) @display
    """,
    "position": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^position$")
        value: (_) @position_value) @position
    """,
    "float": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^float$")
        value: (_) @float_value) @float
    """,
    "clear": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^clear$")
        value: (_) @clear_value) @clear
    """,
    "overflow": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^overflow$")
        value: (_) @overflow_value) @overflow
    """,
    "visibility": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^visibility$")
        value: (_) @visibility_value) @visibility
    """,
    "z_index": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^z-index$")
        value: (_) @z_index_value) @z_index
    """,
    # --- Box Model Properties ---
    "width": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^width$")
        value: (_) @width_value) @width
    """,
    "height": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^height$")
        value: (_) @height_value) @height
    """,
    "margin": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^margin")
        value: (_) @margin_value) @margin
    """,
    "padding": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^padding")
        value: (_) @padding_value) @padding
    """,
    "border": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^border")
        value: (_) @border_value) @border
    """,
    "box_sizing": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^box-sizing$")
        value: (_) @box_sizing_value) @box_sizing
    """,
    # --- Typography Properties ---
    "font": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^font")
        value: (_) @font_value) @font
    """,
    "color": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^color$")
        value: (_) @color_value) @color
    """,
    "text": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^text-")
        value: (_) @text_value) @text
    """,
    "line_height": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^line-height$")
        value: (_) @line_height_value) @line_height
    """,
    "letter_spacing": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^letter-spacing$")
        value: (_) @letter_spacing_value) @letter_spacing
    """,
    "word_spacing": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^word-spacing$")
        value: (_) @word_spacing_value) @word_spacing
    """,
    # --- Background Properties ---
    "background": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^background")
        value: (_) @background_value) @background
    """,
    # --- Flexbox Properties ---
    "flex": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^flex")
        value: (_) @flex_value) @flex
    """,
    "justify_content": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^justify-content$")
        value: (_) @justify_content_value) @justify_content
    """,
    "align_items": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^align-items$")
        value: (_) @align_items_value) @align_items
    """,
    "align_content": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^align-content$")
        value: (_) @align_content_value) @align_content
    """,
    # --- Grid Properties ---
    "grid": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^grid")
        value: (_) @grid_value) @grid
    """,
    # --- Animation Properties ---
    "animation": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^animation")
        value: (_) @animation_value) @animation
    """,
    "transition": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^transition")
        value: (_) @transition_value) @transition
    """,
    "transform": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^transform")
        value: (_) @transform_value) @transform
    """,
    # --- Comments ---
    "comment": """
    (comment) @comment
    """,
    # --- Custom Properties (CSS Variables) ---
    "custom_property": """
    (declaration
        property: (property_name) @prop_name
        (#match? @prop_name "^--")
        value: (_) @custom_value) @custom_property
    """,
    # --- Important Declarations ---
    "important": """
    (declaration
        value: (_)
        "!" @important_mark
        "important" @important_keyword) @important
    """,
    # --- Keyframe Rules ---
    "keyframe_block": """
    (keyframe_block) @keyframe_block
    """,
    "keyframe_block_list": """
    (keyframe_block_list) @keyframe_block_list
    """,
    "from": """
    (from) @from
    """,
    "to": """
    (to) @to
    """,
    # --- Name-only Extraction ---
    "class_name": """
    (class_selector
        name: (class_name) @class_name)
    """,
    "id_name": """
    (id_selector
        name: (id_name) @id_name)
    """,
    "tag_name": """
    (tag_name) @tag_name
    """,
}

# Query descriptions
CSS_QUERY_DESCRIPTIONS: dict[str, str] = {
    "rule_set": "Search CSS rule sets",
    "rule": "Search CSS rules with selectors and blocks",
    "declaration": "Search CSS property declarations",
    "property": "Search CSS properties",
    "property_name": "Search CSS property names",
    "property_value": "Search CSS property values",
    "selector": "Search CSS selectors",
    "selectors": "Search CSS selector lists",
    "class_selector": "Search class selectors",
    "id_selector": "Search ID selectors",
    "tag_selector": "Search tag selectors",
    "universal_selector": "Search universal selectors",
    "attribute_selector": "Search attribute selectors",
    "pseudo_class_selector": "Search pseudo-class selectors",
    "pseudo_element_selector": "Search pseudo-element selectors",
    "descendant_selector": "Search descendant selectors",
    "child_selector": "Search child selectors",
    "sibling_selector": "Search sibling selectors",
    "adjacent_sibling_selector": "Search adjacent sibling selectors",
    "at_rule": "Search at-rules",
    "import_statement": "Search @import statements",
    "media_statement": "Search @media statements",
    "charset_statement": "Search @charset statements",
    "namespace_statement": "Search @namespace statements",
    "keyframes_statement": "Search @keyframes statements",
    "supports_statement": "Search @supports statements",
    "page_statement": "Search @page statements",
    "font_face_statement": "Search @font-face statements",
    "media_query": "Search media queries",
    "media_feature": "Search media features",
    "media_type": "Search media types",
    "string_value": "Search string values",
    "integer_value": "Search integer values",
    "float_value": "Search float values",
    "color_value": "Search color values",
    "call_expression": "Search function calls",
    "function_name": "Search function names",
    "arguments": "Search function arguments",
    "url": "Search url() functions",
    "calc": "Search calc() functions",
    "var": "Search var() functions",
    "rgb": "Search rgb() functions",
    "rgba": "Search rgba() functions",
    "hsl": "Search hsl() functions",
    "hsla": "Search hsla() functions",
    "dimension": "Search dimension values",
    "percentage": "Search percentage values",
    "unit": "Search units",
    "display": "Search display properties",
    "position": "Search position properties",
    "float": "Search float properties",
    "clear": "Search clear properties",
    "overflow": "Search overflow properties",
    "visibility": "Search visibility properties",
    "z_index": "Search z-index properties",
    "width": "Search width properties",
    "height": "Search height properties",
    "margin": "Search margin properties",
    "padding": "Search padding properties",
    "border": "Search border properties",
    "box_sizing": "Search box-sizing properties",
    "font": "Search font properties",
    "color": "Search color properties",
    "text": "Search text properties",
    "line_height": "Search line-height properties",
    "letter_spacing": "Search letter-spacing properties",
    "word_spacing": "Search word-spacing properties",
    "background": "Search background properties",
    "flex": "Search flex properties",
    "justify_content": "Search justify-content properties",
    "align_items": "Search align-items properties",
    "align_content": "Search align-content properties",
    "grid": "Search grid properties",
    "animation": "Search animation properties",
    "transition": "Search transition properties",
    "transform": "Search transform properties",
    "comment": "Search CSS comments",
    "custom_property": "Search CSS custom properties (variables)",
    "important": "Search !important declarations",
    "keyframe_block": "Search keyframe blocks",
    "keyframe_block_list": "Search keyframe block lists",
    "from": "Search from keyframes",
    "to": "Search to keyframes",
    "class_name": "Search class names only",
    "id_name": "Search ID names only",
    "tag_name": "Search tag names only",
}

# Legacy query definitions for backward compatibility
RULES = """
(rule_set
    selectors: (selectors) @rule.selectors
    block: (block) @rule.block) @rule.set
"""

SELECTORS = """
(selectors
    (selector) @selector) @selectors
"""

DECLARATIONS = """
(declaration
    property: (property_name) @declaration.property
    value: (_) @declaration.value) @declaration.full
"""

COMMENTS = """
(comment) @comment
"""

AT_RULES = """
(at_rule) @at_rule
"""

# Convert to ALL_QUERIES format for dynamic loader compatibility
ALL_QUERIES = {}
for query_name, query_string in CSS_QUERIES.items():
    description = CSS_QUERY_DESCRIPTIONS.get(query_name, "No description")
    ALL_QUERIES[query_name] = {"query": query_string, "description": description}

# Add legacy queries for backward compatibility
ALL_QUERIES["rules"] = {
    "query": RULES,
    "description": "Search all CSS rules with selectors and blocks",
}
ALL_QUERIES["selectors"] = {
    "query": SELECTORS,
    "description": "Search all CSS selectors",
}
ALL_QUERIES["declarations"] = {
    "query": DECLARATIONS,
    "description": "Search all CSS declarations",
}
ALL_QUERIES["comments"] = {
    "query": COMMENTS,
    "description": "Search all CSS comments",
}
ALL_QUERIES["at_rules"] = {
    "query": AT_RULES,
    "description": "Search all CSS at-rules",
}


def get_css_query(name: str) -> str:
    """
    Get the specified CSS query

    Args:
        name: Query name

    Returns:
        Query string

    Raises:
        ValueError: When query is not found
    """
    if name not in CSS_QUERIES:
        available = list(CSS_QUERIES.keys())
        raise ValueError(f"CSS query '{name}' does not exist. Available: {available}")

    return CSS_QUERIES[name]


def get_css_query_description(name: str) -> str:
    """
    Get the description of the specified CSS query

    Args:
        name: Query name

    Returns:
        Query description
    """
    return CSS_QUERY_DESCRIPTIONS.get(name, "No description")


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


def get_available_css_queries() -> list[str]:
    """
    Get list of available CSS queries

    Returns:
        List of query names
    """
    return list(CSS_QUERIES.keys())
