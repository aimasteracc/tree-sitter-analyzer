#!/usr/bin/env python3
"""
C++ Language Queries

Tree-sitter queries specific to C++ language constructs.
Covers classes, functions, methods, namespaces, templates, and other C++-specific elements.
"""

# C++-specific query library
CPP_QUERIES: dict[str, str] = {
    # --- Preprocessor ---
    "include": """
    (preproc_include) @include
    """,
    "define": """
    (preproc_def) @define
    """,
    # --- Namespaces ---
    "namespace": """
    (namespace_definition) @namespace
    """,
    "using": """
    (using_declaration) @using
    """,
    "using_directive": """
    (using_declaration
      (identifier)) @using_directive
    """,
    # --- Functions ---
    "function": """
    (function_definition) @function
    """,
    "function_declaration": """
    (declaration
      declarator: (function_declarator)) @function_declaration
    """,
    # --- Classes and Structs ---
    "class": """
    (class_specifier
      body: (field_declaration_list)) @class
    """,
    "struct": """
    (struct_specifier
      body: (field_declaration_list)) @struct
    """,
    # --- Templates ---
    "template": """
    (template_declaration) @template
    """,
    "template_function": """
    (template_declaration
      (function_definition)) @template_function
    """,
    "template_class": """
    (template_declaration
      (class_specifier)) @template_class
    """,
    # --- Access Specifiers ---
    "public": """
    (access_specifier) @public
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
    "class_name": """
    (class_specifier
      name: (type_identifier) @class_name)
    """,
    "struct_name": """
    (struct_specifier
      name: (type_identifier) @struct_name)
    """,
    "namespace_name": """
    (namespace_definition
      name: (identifier) @namespace_name)
    """,
    # --- Detailed Queries ---
    "function_with_params": """
    (function_definition
      declarator: (function_declarator
        declarator: (identifier) @name
        parameters: (parameter_list) @params)
      body: (compound_statement) @body) @function_with_params
    """,
    "class_with_members": """
    (class_specifier
      name: (type_identifier) @name
      body: (field_declaration_list) @members) @class_with_members
    """,
    "method_definition": """
    (function_definition
      declarator: (function_declarator
        declarator: (field_identifier) @method_name)) @method_definition
    """,
    # --- Control Flow ---
    "if": """
    (if_statement) @if
    """,
    "for": """
    (for_statement) @for
    """,
    "range_for": """
    (for_range_loop) @range_for
    """,
    "while": """
    (while_statement) @while
    """,
    "switch": """
    (switch_statement) @switch
    """,
    "try_catch": """
    (try_statement) @try_catch
    """,
    # --- Comments ---
    "comment": """
    (comment) @comment
    """,
}

# Query descriptions
CPP_QUERY_DESCRIPTIONS: dict[str, str] = {
    "include": "Extract #include preprocessor directives",
    "define": "Extract #define preprocessor macros",
    "namespace": "Extract namespace definitions",
    "using": "Extract using declarations",
    "using_directive": "Extract using directives",
    "function": "Extract C++ function definitions",
    "function_declaration": "Extract C++ function declarations",
    "class": "Extract C++ class definitions",
    "struct": "Extract C++ struct definitions",
    "template": "Extract template declarations",
    "template_function": "Extract template function declarations",
    "template_class": "Extract template class declarations",
    "public": "Extract access specifiers",
    "global_var": "Extract global variable declarations",
    "field": "Extract class/struct field declarations",
    "function_name": "Extract function names only",
    "class_name": "Extract class names only",
    "struct_name": "Extract struct names only",
    "namespace_name": "Extract namespace names only",
    "function_with_params": "Extract function definitions with parameters",
    "class_with_members": "Extract class definitions with members",
    "method_definition": "Extract method definitions inside classes",
    "if": "Extract if statements",
    "for": "Extract for statements",
    "range_for": "Extract range-based for loops",
    "while": "Extract while statements",
    "switch": "Extract switch statements",
    "try_catch": "Extract try-catch blocks",
    "comment": "Extract comments",
}


def get_cpp_query(name: str) -> str:
    """
    Get the specified C++ query

    Args:
        name: Query name

    Returns:
        Query string

    Raises:
        ValueError: When query is not found
    """
    if name not in CPP_QUERIES:
        available = list(CPP_QUERIES.keys())
        raise ValueError(f"C++ query '{name}' does not exist. Available: {available}")

    return CPP_QUERIES[name]


def get_cpp_query_description(name: str) -> str:
    """
    Get the description of the specified C++ query

    Args:
        name: Query name

    Returns:
        Query description
    """
    return CPP_QUERY_DESCRIPTIONS.get(name, "No description")


# Convert to ALL_QUERIES format for dynamic loader compatibility
ALL_QUERIES: dict[str, dict[str, str]] = {}
for query_name, query_string in CPP_QUERIES.items():
    description = CPP_QUERY_DESCRIPTIONS.get(query_name, "No description")
    ALL_QUERIES[query_name] = {"query": query_string, "description": description}

# Add common query aliases for cross-language compatibility
ALL_QUERIES["functions"] = {
    "query": CPP_QUERIES["function"],
    "description": "Search all function definitions (alias for function)",
}

ALL_QUERIES["methods"] = {
    "query": CPP_QUERIES["method_definition"],
    "description": "Search all method definitions (alias for method_definition)",
}

ALL_QUERIES["classes"] = {
    "query": CPP_QUERIES["class"],
    "description": "Search all class definitions (alias for class)",
}

ALL_QUERIES["structs"] = {
    "query": CPP_QUERIES["struct"],
    "description": "Search all struct definitions (alias for struct)",
}

ALL_QUERIES["namespaces"] = {
    "query": CPP_QUERIES["namespace"],
    "description": "Search all namespace definitions (alias for namespace)",
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


def get_available_cpp_queries() -> list[str]:
    """
    Get list of available C++ queries

    Returns:
        List of query names
    """
    return list(CPP_QUERIES.keys())
