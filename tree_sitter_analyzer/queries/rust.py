#!/usr/bin/env python3
"""
Rust Language Queries

Tree-sitter queries specific to Rust language constructs.
Covers modules, functions, structs, enums, traits, impl blocks, and other Rust-specific elements.
"""

# Rust-specific query library
RUST_QUERIES: dict[str, str] = {
    # --- Basic Structure ---
    "mod": """
    (mod_item) @mod
    """,
    "struct": """
    (struct_item) @struct
    """,
    "enum": """
    (enum_item) @enum
    """,
    "trait": """
    (trait_item) @trait
    """,
    "impl": """
    (impl_item) @impl
    """,
    "macro": """
    (macro_definition) @macro
    """,
    # --- Functions ---
    "fn": """
    (function_item) @fn
    """,
    "async_fn": """
    (function_item
      (modifiers) @mod
      (#match? @mod "async")) @async_fn
    """,
    # --- Fields and Variants ---
    "field": """
    (field_declaration) @field
    """,
    "enum_variant": """
    (enum_variant) @enum_variant
    """,
    # --- Constants and Statics ---
    "const": """
    (const_item) @const
    """,
    "static": """
    (static_item) @static
    """,
    "type_alias": """
    (type_item) @type_alias
    """,
    # --- Attributes (Annotations) ---
    "attribute": """
    (attribute_item) @attribute
    """,
    "derive_attribute": """
    (attribute_item
      (meta_item
        (identifier) @name
        (#eq? @name "derive")
        (meta_arguments) @arguments)) @derive_attribute
    """,
    # --- Detailed Queries ---
    "struct_with_fields": """
    (struct_item
      name: (type_identifier) @name
      body: (field_declaration_list) @body) @struct_with_fields
    """,
    "fn_with_body": """
    (function_item
      name: (identifier) @name
      body: (block) @body) @fn_with_body
    """,
    "impl_trait": """
    (impl_item
      trait: (type_identifier) @trait
      type: (type_identifier) @type) @impl_trait
    """,
    # --- Name-only Extraction ---
    "mod_name": """
    (mod_item
      name: (identifier) @mod_name)
    """,
    "fn_name": """
    (function_item
      name: (identifier) @fn_name)
    """,
    "struct_name": """
    (struct_item
      name: (type_identifier) @struct_name)
    """,
    "trait_name": """
    (trait_item
      name: (type_identifier) @trait_name)
    """,
    # --- Visibility ---
    "pub_fn": """
    (function_item
      (visibility_modifier) @vis
      name: (identifier) @name) @pub_fn
    """,
    # --- Macros ---
    "macro_call": """
    (macro_invocation) @macro_call
    """,
}

# Query descriptions
RUST_QUERY_DESCRIPTIONS: dict[str, str] = {
    "mod": "Extract Rust module declarations",
    "struct": "Extract Rust struct definitions",
    "enum": "Extract Rust enum definitions",
    "trait": "Extract Rust trait definitions",
    "impl": "Extract Rust impl blocks",
    "macro": "Extract Rust macro definitions",
    "fn": "Extract Rust function declarations",
    "async_fn": "Extract Rust async function declarations",
    "field": "Extract Rust struct fields",
    "enum_variant": "Extract Rust enum variants",
    "const": "Extract Rust constants",
    "static": "Extract Rust static variables",
    "type_alias": "Extract Rust type aliases",
    "attribute": "Extract Rust attributes",
    "derive_attribute": "Extract Rust derive attributes",
    "struct_with_fields": "Extract struct definitions with fields",
    "fn_with_body": "Extract function declarations with body",
    "impl_trait": "Extract trait implementation blocks",
    "mod_name": "Extract module names only",
    "fn_name": "Extract function names only",
    "struct_name": "Extract struct names only",
    "trait_name": "Extract trait names only",
    "pub_fn": "Extract public functions",
    "macro_call": "Extract macro invocations",
}


def get_rust_query(name: str) -> str:
    """
    Get the specified Rust query

    Args:
        name: Query name

    Returns:
        Query string

    Raises:
        ValueError: When query is not found
    """
    if name not in RUST_QUERIES:
        available = list(RUST_QUERIES.keys())
        raise ValueError(f"Rust query '{name}' does not exist. Available: {available}")

    return RUST_QUERIES[name]


def get_rust_query_description(name: str) -> str:
    """
    Get the description of the specified Rust query

    Args:
        name: Query name

    Returns:
        Query description
    """
    return RUST_QUERY_DESCRIPTIONS.get(name, "No description")


# Convert to ALL_QUERIES format for dynamic loader compatibility
ALL_QUERIES = {}
for query_name, query_string in RUST_QUERIES.items():
    description = RUST_QUERY_DESCRIPTIONS.get(query_name, "No description")
    ALL_QUERIES[query_name] = {"query": query_string, "description": description}

# Add common query aliases for cross-language compatibility
ALL_QUERIES["functions"] = {
    "query": RUST_QUERIES["fn"],
    "description": "Search all function declarations (alias for fn)",
}

ALL_QUERIES["methods"] = {
    "query": RUST_QUERIES["fn"],
    "description": "Search all method declarations (alias for fn)",
}

ALL_QUERIES["classes"] = {
    "query": RUST_QUERIES["struct"],
    "description": "Search all struct definitions (alias for struct)",
}


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


def get_available_rust_queries() -> list[str]:
    """
    Get list of available Rust queries

    Returns:
        List of query names
    """
    return list(RUST_QUERIES.keys())
