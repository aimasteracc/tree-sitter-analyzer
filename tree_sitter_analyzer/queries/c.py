#!/usr/bin/env python3
"""
C Language Queries

Tree-sitter queries specific to C language constructs.
Covers functions, structs, unions, enums, and preprocessor directives.
"""

# C-specific query library
C_QUERIES: dict[str, str] = {
    # --- Functions ---
    "function": """
    (function_definition) @function
    """,
    "function_declaration": """
    (declaration
      declarator: (function_declarator)) @function_declaration
    """,
    "function_name": """
    (function_definition
      declarator: (function_declarator
        declarator: (identifier) @function_name))
    """,
    "static_function": """
    (function_definition
      (storage_class_specifier) @storage
      (#eq? @storage "static")) @static_function
    """,
    "inline_function": """
    (function_definition
      (storage_class_specifier) @storage
      (#eq? @storage "inline")) @inline_function
    """,
    # --- Structs and Unions ---
    "struct": """
    (struct_specifier) @struct
    """,
    "union": """
    (union_specifier) @union
    """,
    "struct_name": """
    (struct_specifier
      name: (type_identifier) @struct_name)
    """,
    "union_name": """
    (union_specifier
      name: (type_identifier) @union_name)
    """,
    "typedef_struct": """
    (type_definition
      type: (struct_specifier) @struct_type
      declarator: (type_identifier) @typedef_name) @typedef_struct
    """,
    # --- Enums ---
    "enum": """
    (enum_specifier) @enum
    """,
    "enum_name": """
    (enum_specifier
      name: (type_identifier) @enum_name)
    """,
    "enum_constant": """
    (enumerator) @enum_constant
    """,
    # --- Variables and Fields ---
    "field": """
    (field_declaration) @field
    """,
    "variable": """
    (declaration) @variable
    """,
    "static_variable": """
    (declaration
      (storage_class_specifier) @storage
      (#eq? @storage "static")) @static_variable
    """,
    "const_variable": """
    (declaration
      (type_qualifier) @qualifier
      (#eq? @qualifier "const")) @const_variable
    """,
    "extern_variable": """
    (declaration
      (storage_class_specifier) @storage
      (#eq? @storage "extern")) @extern_variable
    """,
    "global_variable": """
    (translation_unit
      (declaration) @global_variable)
    """,
    # --- Includes and Preprocessor ---
    "include": """
    (preproc_include) @include
    """,
    "system_include": """
    (preproc_include
      path: (system_lib_string) @system_include)
    """,
    "local_include": """
    (preproc_include
      path: (string_literal) @local_include)
    """,
    "define": """
    (preproc_def) @define
    """,
    "define_name": """
    (preproc_def
      name: (identifier) @define_name)
    """,
    "ifdef": """
    (preproc_ifdef) @ifdef
    """,
    "ifndef": """
    (preproc_ifdef) @ifndef
    (#match? @ifndef "ifndef")
    """,
    "macro_function": """
    (preproc_function_def) @macro_function
    """,
    "pragma": """
    (preproc_call) @pragma
    (#match? @pragma "^#pragma")
    """,
    # --- Type Definitions ---
    "typedef": """
    (type_definition) @typedef
    """,
    "typedef_name": """
    (type_definition
      declarator: (type_identifier) @typedef_name)
    """,
    # --- Pointer Types ---
    "pointer_type": """
    (pointer_declarator) @pointer_type
    """,
    "array_type": """
    (array_declarator) @array_type
    """,
    # --- Control Flow ---
    "if_statement": """
    (if_statement) @if_statement
    """,
    "for_statement": """
    (for_statement) @for_statement
    """,
    "while_statement": """
    (while_statement) @while_statement
    """,
    "do_statement": """
    (do_statement) @do_statement
    """,
    "switch_statement": """
    (switch_statement) @switch_statement
    """,
    "case_statement": """
    (case_statement) @case_statement
    """,
    "goto_statement": """
    (goto_statement) @goto_statement
    """,
    "return_statement": """
    (return_statement) @return_statement
    """,
    # --- Labels ---
    "label": """
    (labeled_statement) @label
    """,
    # --- Comments ---
    "comment": """
    (comment) @comment
    """,
    "block_comment": """
    (comment) @block_comment
    (#match? @block_comment "^/\\*")
    """,
    "line_comment": """
    (comment) @line_comment
    (#match? @line_comment "^//")
    """,
    # --- String Literals ---
    "string_literal": """
    (string_literal) @string_literal
    """,
    # --- Function Calls ---
    "function_call": """
    (call_expression) @function_call
    """,
    "function_call_name": """
    (call_expression
      function: (identifier) @function_call_name)
    """,
    # --- Sizeof and Alignof ---
    "sizeof": """
    (sizeof_expression) @sizeof
    """,
    # --- Cast Expressions ---
    "cast": """
    (cast_expression) @cast
    """,
}

# Query descriptions
C_QUERY_DESCRIPTIONS: dict[str, str] = {
    "function": "Extract C function definitions",
    "function_declaration": "Extract C function declarations",
    "function_name": "Extract C function names only",
    "static_function": "Extract C static functions",
    "inline_function": "Extract C inline functions",
    "struct": "Extract C struct declarations",
    "union": "Extract C union declarations",
    "struct_name": "Extract C struct names only",
    "union_name": "Extract C union names only",
    "typedef_struct": "Extract C typedef struct patterns",
    "enum": "Extract C enum declarations",
    "enum_name": "Extract C enum names only",
    "enum_constant": "Extract C enum constants",
    "field": "Extract C struct/union fields",
    "variable": "Extract C variable declarations",
    "static_variable": "Extract C static variables",
    "const_variable": "Extract C const variables",
    "extern_variable": "Extract C extern variables",
    "global_variable": "Extract C global variables",
    "include": "Extract C include directives",
    "system_include": "Extract C system includes",
    "local_include": "Extract C local includes",
    "define": "Extract C preprocessor defines",
    "define_name": "Extract C define names only",
    "ifdef": "Extract C preprocessor ifdef blocks",
    "ifndef": "Extract C preprocessor ifndef blocks",
    "macro_function": "Extract C macro functions",
    "pragma": "Extract C pragma directives",
    "typedef": "Extract C typedef declarations",
    "typedef_name": "Extract C typedef names only",
    "pointer_type": "Extract C pointer types",
    "array_type": "Extract C array types",
    "if_statement": "Extract C if statements",
    "for_statement": "Extract C for loops",
    "while_statement": "Extract C while loops",
    "do_statement": "Extract C do-while loops",
    "switch_statement": "Extract C switch statements",
    "case_statement": "Extract C case statements",
    "goto_statement": "Extract C goto statements",
    "return_statement": "Extract C return statements",
    "label": "Extract C labeled statements",
    "comment": "Extract C comments",
    "block_comment": "Extract C block comments",
    "line_comment": "Extract C line comments",
    "string_literal": "Extract C string literals",
    "function_call": "Extract C function calls",
    "function_call_name": "Extract C function call names only",
    "sizeof": "Extract C sizeof expressions",
    "cast": "Extract C cast expressions",
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
ALL_QUERIES = {}
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
    "description": "Search all struct declarations (alias for struct in C)",
}

ALL_QUERIES["imports"] = {
    "query": C_QUERIES["include"],
    "description": "Search all include directives (alias for include)",
}

ALL_QUERIES["variables"] = {
    "query": C_QUERIES["variable"],
    "description": "Search all variable declarations (alias for variable)",
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


def get_available_c_queries() -> list[str]:
    """
    Get list of available C queries

    Returns:
        List of query names
    """
    return list(C_QUERIES.keys())
