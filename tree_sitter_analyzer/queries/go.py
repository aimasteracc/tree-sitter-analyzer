#!/usr/bin/env python3
"""
Go Language Queries

Tree-sitter queries specific to Go language constructs.
Covers packages, functions, methods, structs, interfaces, and other Go-specific elements.
"""

# Go-specific query library
GO_QUERIES: dict[str, str] = {
    # --- Basic Structure ---
    "package": """
    (package_clause) @package
    """,
    "import": """
    (import_declaration) @import
    """,
    "import_spec": """
    (import_spec) @import_spec
    """,
    # --- Functions and Methods ---
    "function": """
    (function_declaration) @function
    """,
    "method": """
    (method_declaration) @method
    """,
    # --- Types ---
    "struct": """
    (type_declaration
      (type_spec
        type: (struct_type))) @struct
    """,
    "interface": """
    (type_declaration
      (type_spec
        type: (interface_type))) @interface
    """,
    "type_alias": """
    (type_declaration
      (type_spec
        type: (_))) @type_alias
    """,
    # --- Variables and Constants ---
    "const": """
    (const_declaration) @const
    """,
    "var": """
    (var_declaration) @var
    """,
    "const_spec": """
    (const_spec) @const_spec
    """,
    "var_spec": """
    (var_spec) @var_spec
    """,
    # --- Concurrency ---
    "goroutine": """
    (go_statement) @goroutine
    """,
    "channel_send": """
    (send_statement) @channel_send
    """,
    "channel_receive": """
    (receive_statement) @channel_receive
    """,
    "select": """
    (select_statement) @select
    """,
    # --- Control Flow ---
    "defer": """
    (defer_statement) @defer
    """,
    "if": """
    (if_statement) @if
    """,
    "for": """
    (for_statement) @for
    """,
    "switch": """
    (expression_switch_statement) @switch
    """,
    "type_switch": """
    (type_switch_statement) @type_switch
    """,
    # --- Name-only Extraction ---
    "function_name": """
    (function_declaration
      name: (identifier) @function_name)
    """,
    "method_name": """
    (method_declaration
      name: (field_identifier) @method_name)
    """,
    "struct_name": """
    (type_declaration
      (type_spec
        name: (type_identifier) @struct_name
        type: (struct_type)))
    """,
    "interface_name": """
    (type_declaration
      (type_spec
        name: (type_identifier) @interface_name
        type: (interface_type)))
    """,
    # --- Detailed Queries ---
    "function_with_body": """
    (function_declaration
      name: (identifier) @name
      body: (block) @body) @function_with_body
    """,
    "method_with_receiver": """
    (method_declaration
      receiver: (parameter_list) @receiver
      name: (field_identifier) @name
      body: (block) @body) @method_with_receiver
    """,
    "struct_with_fields": """
    (type_declaration
      (type_spec
        name: (type_identifier) @name
        type: (struct_type
          (field_declaration_list) @fields))) @struct_with_fields
    """,
    "interface_with_methods": """
    (type_declaration
      (type_spec
        name: (type_identifier) @name
        type: (interface_type) @methods)) @interface_with_methods
    """,
    # --- Comments ---
    "comment": """
    (comment) @comment
    """,
    # --- Error Handling ---
    "error_check": """
    (if_statement
      condition: (binary_expression
        left: (identifier) @err
        (#eq? @err "err")
        operator: "!="
        right: (nil))) @error_check
    """,
}

# Query descriptions
GO_QUERY_DESCRIPTIONS: dict[str, str] = {
    "package": "Extract Go package declarations",
    "import": "Extract Go import declarations",
    "import_spec": "Extract individual import specifications",
    "function": "Extract Go function declarations",
    "method": "Extract Go method declarations",
    "struct": "Extract Go struct type declarations",
    "interface": "Extract Go interface type declarations",
    "type_alias": "Extract Go type alias declarations",
    "const": "Extract Go const declarations",
    "var": "Extract Go var declarations",
    "const_spec": "Extract individual const specifications",
    "var_spec": "Extract individual var specifications",
    "goroutine": "Extract goroutine (go statement) invocations",
    "channel_send": "Extract channel send operations",
    "channel_receive": "Extract channel receive operations",
    "select": "Extract select statements",
    "defer": "Extract defer statements",
    "if": "Extract if statements",
    "for": "Extract for statements",
    "switch": "Extract switch statements",
    "type_switch": "Extract type switch statements",
    "function_name": "Extract function names only",
    "method_name": "Extract method names only",
    "struct_name": "Extract struct names only",
    "interface_name": "Extract interface names only",
    "function_with_body": "Extract function declarations with body",
    "method_with_receiver": "Extract method declarations with receiver",
    "struct_with_fields": "Extract struct declarations with fields",
    "interface_with_methods": "Extract interface declarations with methods",
    "comment": "Extract comments",
    "error_check": "Extract error checking patterns",
}


def get_go_query(name: str) -> str:
    """
    Get the specified Go query

    Args:
        name: Query name

    Returns:
        Query string

    Raises:
        ValueError: When query is not found
    """
    if name not in GO_QUERIES:
        available = list(GO_QUERIES.keys())
        raise ValueError(f"Go query '{name}' does not exist. Available: {available}")

    return GO_QUERIES[name]


def get_go_query_description(name: str) -> str:
    """
    Get the description of the specified Go query

    Args:
        name: Query name

    Returns:
        Query description
    """
    return GO_QUERY_DESCRIPTIONS.get(name, "No description")


# Convert to ALL_QUERIES format for dynamic loader compatibility
ALL_QUERIES = {}
for query_name, query_string in GO_QUERIES.items():
    description = GO_QUERY_DESCRIPTIONS.get(query_name, "No description")
    ALL_QUERIES[query_name] = {"query": query_string, "description": description}

# Add common query aliases for cross-language compatibility
ALL_QUERIES["functions"] = {
    "query": GO_QUERIES["function"],
    "description": "Search all function declarations (alias for function)",
}

ALL_QUERIES["methods"] = {
    "query": GO_QUERIES["method"],
    "description": "Search all method declarations (alias for method)",
}

ALL_QUERIES["classes"] = {
    "query": GO_QUERIES["struct"],
    "description": "Search all struct declarations (alias for struct)",
}

ALL_QUERIES["structs"] = {
    "query": GO_QUERIES["struct"],
    "description": "Search all struct declarations (alias for struct)",
}

ALL_QUERIES["interfaces"] = {
    "query": GO_QUERIES["interface"],
    "description": "Search all interface declarations (alias for interface)",
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


def get_available_go_queries() -> list[str]:
    """
    Get list of available Go queries

    Returns:
        List of query names
    """
    return list(GO_QUERIES.keys())
