#!/usr/bin/env python3
"""
C++ Language Queries

Tree-sitter queries specific to C++ language constructs.
Covers classes, functions, templates, namespaces, and other C++ specific elements.
"""

# C++-specific query library
CPP_QUERIES: dict[str, str] = {
    # --- Basic Structure ---
    "class": """
    (class_specifier) @class
    """,
    "struct": """
    (struct_specifier) @struct
    """,
    "union": """
    (union_specifier) @union
    """,
    "enum": """
    (enum_specifier) @enum
    """,
    # --- Functions and Methods ---
    "function": """
    (function_definition) @function
    """,
    "function_declaration": """
    (declaration
      declarator: (function_declarator)) @function_declaration
    """,
    "method": """
    (function_definition
      declarator: (function_declarator
        declarator: (field_identifier) @method.name)) @method
    """,
    "constructor": """
    (function_definition
      declarator: (function_declarator
        declarator: (identifier) @ctor.name)
      body: (compound_statement)) @constructor
    """,
    "destructor": """
    (function_definition
      declarator: (function_declarator
        declarator: (destructor_name) @dtor.name)) @destructor
    """,
    "virtual_function": """
    (function_definition
      (virtual)) @virtual_function
    """,
    # --- Templates ---
    "template": """
    (template_declaration) @template
    """,
    "template_function": """
    (template_declaration
      (function_definition) @template_function)
    """,
    "template_class": """
    (template_declaration
      (class_specifier) @template_class)
    """,
    "template_parameter": """
    (template_parameter_list
      (type_parameter_declaration) @template_parameter)
    """,
    # --- Namespaces ---
    "namespace": """
    (namespace_definition) @namespace
    """,
    "namespace_name": """
    (namespace_definition
      name: (identifier) @namespace_name)
    """,
    "using_declaration": """
    (using_declaration) @using_declaration
    """,
    "using_directive": """
    (using_directive) @using_directive
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
    "ifdef": """
    (preproc_ifdef) @ifdef
    """,
    "macro_function": """
    (preproc_function_def) @macro_function
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
    # --- Access Specifiers ---
    "public_access": """
    (access_specifier) @public_access
    (#eq? @public_access "public:")
    """,
    "private_access": """
    (access_specifier) @private_access
    (#eq? @private_access "private:")
    """,
    "protected_access": """
    (access_specifier) @protected_access
    (#eq? @protected_access "protected:")
    """,
    # --- Inheritance ---
    "base_class": """
    (base_class_clause
      (base_specifier) @base_class)
    """,
    "public_inheritance": """
    (base_class_clause
      (base_specifier
        (access_specifier) @access
        (#eq? @access "public")
        (type_identifier) @base_type)) @public_inheritance
    """,
    # --- Smart Pointers and Modern C++ ---
    "smart_pointer": """
    (template_type
      name: (type_identifier) @ptr_type
      (#match? @ptr_type "^(unique_ptr|shared_ptr|weak_ptr)$")) @smart_pointer
    """,
    "auto_type": """
    (declaration
      type: (auto)) @auto_type
    """,
    "lambda": """
    (lambda_expression) @lambda
    """,
    "range_for": """
    (for_range_loop) @range_for
    """,
    # --- Exception Handling ---
    "try_catch": """
    (try_statement) @try_catch
    """,
    "catch_clause": """
    (catch_clause) @catch_clause
    """,
    "throw_statement": """
    (throw_statement) @throw_statement
    """,
    # --- Name-only Extraction ---
    "class_name": """
    (class_specifier
      name: (type_identifier) @class_name)
    """,
    "function_name": """
    (function_definition
      declarator: (function_declarator
        declarator: (identifier) @function_name))
    """,
    "field_name": """
    (field_declaration
      declarator: (field_identifier) @field_name)
    """,
    # --- Comments ---
    "comment": """
    (comment) @comment
    """,
    "block_comment": """
    (comment) @block_comment
    (#match? @block_comment "^/\\*")
    """,
    # --- Operator Overloading ---
    "operator_overload": """
    (function_definition
      declarator: (function_declarator
        declarator: (operator_name) @operator_name)) @operator_overload
    """,
    # --- Friend Declaration ---
    "friend": """
    (friend_declaration) @friend
    """,
}

# Query descriptions
CPP_QUERY_DESCRIPTIONS: dict[str, str] = {
    "class": "Extract C++ class declarations",
    "struct": "Extract C++ struct declarations",
    "union": "Extract C++ union declarations",
    "enum": "Extract C++ enum declarations",
    "function": "Extract C++ function definitions",
    "function_declaration": "Extract C++ function declarations",
    "method": "Extract C++ class methods",
    "constructor": "Extract C++ constructors",
    "destructor": "Extract C++ destructors",
    "virtual_function": "Extract C++ virtual functions",
    "template": "Extract C++ template declarations",
    "template_function": "Extract C++ template functions",
    "template_class": "Extract C++ template classes",
    "template_parameter": "Extract C++ template parameters",
    "namespace": "Extract C++ namespace definitions",
    "namespace_name": "Extract C++ namespace names",
    "using_declaration": "Extract C++ using declarations",
    "using_directive": "Extract C++ using directives",
    "include": "Extract C++ include directives",
    "system_include": "Extract C++ system includes",
    "local_include": "Extract C++ local includes",
    "define": "Extract C++ preprocessor defines",
    "ifdef": "Extract C++ preprocessor ifdef blocks",
    "macro_function": "Extract C++ macro functions",
    "field": "Extract C++ class/struct fields",
    "variable": "Extract C++ variable declarations",
    "static_variable": "Extract C++ static variables",
    "const_variable": "Extract C++ const variables",
    "public_access": "Extract C++ public access specifiers",
    "private_access": "Extract C++ private access specifiers",
    "protected_access": "Extract C++ protected access specifiers",
    "base_class": "Extract C++ base class specifiers",
    "public_inheritance": "Extract C++ public inheritance",
    "smart_pointer": "Extract C++ smart pointer usage",
    "auto_type": "Extract C++ auto type declarations",
    "lambda": "Extract C++ lambda expressions",
    "range_for": "Extract C++ range-based for loops",
    "try_catch": "Extract C++ try-catch blocks",
    "catch_clause": "Extract C++ catch clauses",
    "throw_statement": "Extract C++ throw statements",
    "class_name": "Extract C++ class names only",
    "function_name": "Extract C++ function names only",
    "field_name": "Extract C++ field names only",
    "comment": "Extract C++ comments",
    "block_comment": "Extract C++ block comments",
    "operator_overload": "Extract C++ operator overloads",
    "friend": "Extract C++ friend declarations",
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
ALL_QUERIES = {}
for query_name, query_string in CPP_QUERIES.items():
    description = CPP_QUERY_DESCRIPTIONS.get(query_name, "No description")
    ALL_QUERIES[query_name] = {"query": query_string, "description": description}

# Add common query aliases for cross-language compatibility
ALL_QUERIES["functions"] = {
    "query": CPP_QUERIES["function"],
    "description": "Search all function definitions (alias for function)",
}

ALL_QUERIES["methods"] = {
    "query": CPP_QUERIES["method"],
    "description": "Search all method declarations (alias for method)",
}

ALL_QUERIES["classes"] = {
    "query": CPP_QUERIES["class"],
    "description": "Search all class declarations (alias for class)",
}

ALL_QUERIES["imports"] = {
    "query": CPP_QUERIES["include"],
    "description": "Search all include directives (alias for include)",
}

ALL_QUERIES["variables"] = {
    "query": CPP_QUERIES["variable"],
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


def get_available_cpp_queries() -> list[str]:
    """
    Get list of available C++ queries

    Returns:
        List of query names
    """
    return list(CPP_QUERIES.keys())
