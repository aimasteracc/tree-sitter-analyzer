#!/usr/bin/env python3
"""
YAML Language Queries

Comprehensive Tree-sitter queries for YAML language constructs.
Covers documents, mappings, sequences, scalars, anchors, aliases, and comments.
"""

# YAML-specific query library
YAML_QUERIES: dict[str, str] = {
    # --- Document Structure ---
    "document": """
    (document) @document
    """,
    "stream": """
    (stream) @stream
    """,
    # --- Block Style Mappings ---
    "block_mapping": """
    (block_mapping) @block_mapping
    """,
    "block_mapping_pair": """
    (block_mapping_pair) @block_mapping_pair
    """,
    "block_node": """
    (block_node) @block_node
    """,
    # --- Block Style Sequences ---
    "block_sequence": """
    (block_sequence) @block_sequence
    """,
    "block_sequence_item": """
    (block_sequence_item) @block_sequence_item
    """,
    # --- Flow Style Mappings ---
    "flow_mapping": """
    (flow_mapping) @flow_mapping
    """,
    "flow_pair": """
    (flow_pair) @flow_pair
    """,
    "flow_node": """
    (flow_node) @flow_node
    """,
    # --- Flow Style Sequences ---
    "flow_sequence": """
    (flow_sequence) @flow_sequence
    """,
    # --- Scalars ---
    "plain_scalar": """
    (plain_scalar) @plain_scalar
    """,
    "double_quote_scalar": """
    (double_quote_scalar) @double_quote_scalar
    """,
    "single_quote_scalar": """
    (single_quote_scalar) @single_quote_scalar
    """,
    "block_scalar": """
    (block_scalar) @block_scalar
    """,
    "string_scalar": """
    (string_scalar) @string_scalar
    """,
    "integer_scalar": """
    (integer_scalar) @integer_scalar
    """,
    "float_scalar": """
    (float_scalar) @float_scalar
    """,
    "boolean_scalar": """
    (boolean_scalar) @boolean_scalar
    """,
    "null_scalar": """
    (null_scalar) @null_scalar
    """,
    # --- Anchors and Aliases ---
    "anchor": """
    (anchor) @anchor
    """,
    "alias": """
    (alias) @alias
    """,
    # --- Tags ---
    "tag": """
    (tag) @tag
    """,
    # --- Comments ---
    "comment": """
    (comment) @comment
    """,
    # --- Keys ---
    "key": """
    (block_mapping_pair
        key: (_) @key)
    """,
    "flow_key": """
    (flow_pair
        key: (_) @flow_key)
    """,
    # --- Values ---
    "value": """
    (block_mapping_pair
        value: (_) @value)
    """,
    "flow_value": """
    (flow_pair
        value: (_) @flow_value)
    """,
    # --- All Mappings (Block + Flow) ---
    "all_mappings": """
    [
        (block_mapping)
        (flow_mapping)
    ] @mapping
    """,
    # --- All Sequences (Block + Flow) ---
    "all_sequences": """
    [
        (block_sequence)
        (flow_sequence)
    ] @sequence
    """,
    # --- All Scalars ---
    "all_scalars": """
    [
        (plain_scalar)
        (double_quote_scalar)
        (single_quote_scalar)
        (block_scalar)
    ] @scalar
    """,
}

# Query descriptions
YAML_QUERY_DESCRIPTIONS: dict[str, str] = {
    "document": "Search YAML documents",
    "stream": "Search YAML streams",
    "block_mapping": "Search block-style mappings",
    "block_mapping_pair": "Search block-style key-value pairs",
    "block_node": "Search block nodes",
    "block_sequence": "Search block-style sequences",
    "block_sequence_item": "Search block-style sequence items",
    "flow_mapping": "Search flow-style mappings",
    "flow_pair": "Search flow-style key-value pairs",
    "flow_node": "Search flow nodes",
    "flow_sequence": "Search flow-style sequences",
    "plain_scalar": "Search plain scalars",
    "double_quote_scalar": "Search double-quoted scalars",
    "single_quote_scalar": "Search single-quoted scalars",
    "block_scalar": "Search block scalars (literal/folded)",
    "string_scalar": "Search string scalars",
    "integer_scalar": "Search integer scalars",
    "float_scalar": "Search float scalars",
    "boolean_scalar": "Search boolean scalars",
    "null_scalar": "Search null scalars",
    "anchor": "Search anchors (&name)",
    "alias": "Search aliases (*name)",
    "tag": "Search tags (!tag)",
    "comment": "Search comments",
    "key": "Search mapping keys",
    "flow_key": "Search flow mapping keys",
    "value": "Search mapping values",
    "flow_value": "Search flow mapping values",
    "all_mappings": "Search all mappings (block and flow)",
    "all_sequences": "Search all sequences (block and flow)",
    "all_scalars": "Search all scalars",
}

# Convert to ALL_QUERIES format for dynamic loader compatibility
ALL_QUERIES: dict[str, dict[str, str]] = {}
for query_name, query_string in YAML_QUERIES.items():
    description = YAML_QUERY_DESCRIPTIONS.get(query_name, "No description")
    ALL_QUERIES[query_name] = {"query": query_string, "description": description}


def get_yaml_query(name: str) -> str:
    """
    Get the specified YAML query.

    Args:
        name: Query name

    Returns:
        Query string

    Raises:
        ValueError: When query is not found
    """
    if name not in YAML_QUERIES:
        available = list(YAML_QUERIES.keys())
        raise ValueError(f"YAML query '{name}' does not exist. Available: {available}")

    return YAML_QUERIES[name]


def get_yaml_query_description(name: str) -> str:
    """
    Get the description of the specified YAML query.

    Args:
        name: Query name

    Returns:
        Query description
    """
    return YAML_QUERY_DESCRIPTIONS.get(name, "No description")


def get_query(name: str) -> str:
    """Get a specific query by name."""
    if name in ALL_QUERIES:
        return ALL_QUERIES[name]["query"]
    raise ValueError(
        f"Query '{name}' not found. Available queries: {list(ALL_QUERIES.keys())}"
    )


def get_all_queries() -> dict[str, dict[str, str]]:
    """Get all available queries."""
    return ALL_QUERIES


def list_queries() -> list[str]:
    """List all available query names."""
    return list(ALL_QUERIES.keys())


def get_available_yaml_queries() -> list[str]:
    """
    Get list of available YAML queries.

    Returns:
        List of query names
    """
    return list(YAML_QUERIES.keys())
