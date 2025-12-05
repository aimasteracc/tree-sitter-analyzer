#!/usr/bin/env python3
"""
C Language Queries

Tree-sitter queries specific to C language constructs.
Covers functions, structs, unions, enums, variables, and preprocessor directives.
"""

# C-specific query library
C_QUERIES: dict[str, str] = {
    # --- Preprocessor ---
    "include": """
    (preproc_include) @include
    """,
    "define": """
    (preproc_def) @define
    """,
    "ifdef": """
    (preproc_ifdef) @ifdef
    """,
    "ifndef": """
    (preproc_ifdef
      name: (identifier) @name
      (#match? @name ".*")) @ifndef
    """,
    # --- Functions ---
    "function": """
    (function_definition) @function
    """,
    "function_declaration": """
    (declaration
      declarator: (function_declarator)) @function_declaration
    """,
    # --- Types ---
    "struct": """
    (struct_specifier
      body: (field_declaration_list)) @struct
    """,
    "union": """
    (union_specifier
      body: (field_declaration_list)) @union
    """,
    "enum": """
    (enum_specifier
      body: (enumerator_list)) @enum
    """,
    "typedef": """
    (type_definition) @typedef
    """,
    # --- Variables ---
    "global_var": """
    (translation_unit
      (declaration) @global_var)
    """,
    "field": """
    (field_declaration) @field
    """,
    # --- Name-only Extraction ---
    "function_name": """
    (function_definition
      declarator: (function_declarator
        declarator: (identifier) @function_name))
    """,
    "struct_name": """
    (struct_specifier
      name: (type_identifier) @struct_name)
    """,
    "union_name": """
    (union_specifier
      name: (type_identifier) @union_name)
    """,
    "enum_name": """
    (enum_specifier
      name: (type_identifier) @enum_name)
    """,
    # --- Detailed Queries ---
    "function_with_params": """
    (function_definition
      declarator: (function_declarator
        declarator: (identifier) @name
        parameters: (parameter_list) @params)
      body: (compound_statement) @body) @function_with_params
    """,
    "struct_with_fields": """
    (struct_specifier
      name: (type_identifier) @name
      body: (field_declaration_list) @fields) @struct_with_fields
    """,
    # --- Control Flow ---
    "if": """
    (if_statement) @if
    """,
    "for": """
    (for_statement) @for
    """,
    "while": """
    (while_statement) @while
    """,
    "switch": """
    (switch_statement) @switch
    """,
    # --- Comments ---
    "comment": """
    (comment) @comment
    """,
}

# Query descriptions
C_QUERY_DESCRIPTIONS: dict[str, str] = {
    "include": "Extract #include preprocessor directives",
    "define": "Extract #define preprocessor macros",
    "ifdef": "Extract #ifdef preprocessor conditionals",
    "ifndef": "Extract #ifndef preprocessor conditionals",
    "function": "Extract C function definitions",
    "function_declaration": "Extract C function declarations",
    "struct": "Extract C struct definitions",
    "union": "Extract C union definitions",
    "enum": "Extract C enum definitions",
    "typedef": "Extract C typedef declarations",
    "global_var": "Extract global variable declarations",
    "field": "Extract struct/union field declarations",
    "function_name": "Extract function names only",
    "struct_name": "Extract struct names only",
    "union_name": "Extract union names only",
    "enum_name": "Extract enum names only",
    "function_with_params": "Extract function definitions with parameters",
    "struct_with_fields": "Extract struct definitions with fields",
    "if": "Extract if statements",
    "for": "Extract for statements",
    "while": "Extract while statements",
    "switch": "Extract switch statements",
    "comment": "Extract comments",
}


def get_c_query(name: str) -> str:
    """
    Get the specified C query

    Args:
        name: Query name

    Returns:
        Query string

    Raises:
        ValueError: When query is not found
    """
    if name not in C_QUERIES:
        available = list(C_QUERIES.keys())
        raise ValueError(f"C query '{name}' does not exist. Available: {available}")

    return C_QUERIES[name]


def get_c_query_description(name: str) -> str:
    """
    Get the description of the specified C query

    Args:
        name: Query name

    Returns:
        Query description
    """
    return C_QUERY_DESCRIPTIONS.get(name, "No description")


# Convert to ALL_QUERIES format for dynamic loader compatibility
ALL_QUERIES: dict[str, dict[str, str]] = {}
for query_name, query_string in C_QUERIES.items():
    description = C_QUERY_DESCRIPTIONS.get(query_name, "No description")
    ALL_QUERIES[query_name] = {"query": query_string, "description": description}

# Add common query aliases for cross-language compatibility
ALL_QUERIES["functions"] = {
    "query": C_QUERIES["function"],
    "description": "Search all function definitions (alias for function)",
}

ALL_QUERIES["classes"] = {
    "query": C_QUERIES["struct"],
    "description": "Search all struct definitions (alias for struct)",
}

ALL_QUERIES["structs"] = {
    "query": C_QUERIES["struct"],
    "description": "Search all struct definitions (alias for struct)",
}

ALL_QUERIES["unions"] = {
    "query": C_QUERIES["union"],
    "description": "Search all union definitions (alias for union)",
}

ALL_QUERIES["enums"] = {
    "query": C_QUERIES["enum"],
    "description": "Search all enum definitions (alias for enum)",
}


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


def get_available_c_queries() -> list[str]:
    """
    Get list of available C queries

    Returns:
        List of query names
    """
    return list(C_QUERIES.keys())
