#!/usr/bin/env python3
"""
JavaScript Tree-sitter queries for code analysis.
"""

# Function declarations and expressions
FUNCTIONS = """
(function_declaration
    name: (identifier) @function.name
    parameters: (formal_parameters) @function.params
    body: (statement_block) @function.body) @function.declaration

(function_expression
    name: (identifier)? @function.name
    parameters: (formal_parameters) @function.params
    body: (statement_block) @function.body) @function.expression

(arrow_function
    parameters: (formal_parameters) @function.params
    body: (_) @function.body) @function.arrow

(method_definition
    name: (property_identifier) @function.name
    parameters: (formal_parameters) @function.params
    body: (statement_block) @function.body) @method.definition
"""

# Class declarations
CLASSES = """
(class_declaration
    name: (identifier) @class.name
    superclass: (class_heritage)? @class.superclass
    body: (class_body) @class.body) @class.declaration

(class_expression
    name: (identifier)? @class.name
    superclass: (class_heritage)? @class.superclass
    body: (class_body) @class.body) @class.expression
"""

# Variable declarations
VARIABLES = """
(variable_declaration
    (variable_declarator
        name: (identifier) @variable.name
        value: (_)? @variable.value)) @variable.declaration

(lexical_declaration
    (variable_declarator
        name: (identifier) @variable.name
        value: (_)? @variable.value)) @variable.lexical
"""

# Import and export statements
IMPORTS = """
(import_statement
    source: (string) @import.source) @import.statement

(import_statement
    (import_clause
        (named_imports
            (import_specifier
                name: (identifier) @import.name
                alias: (identifier)? @import.alias))) @import.named

(import_statement
    (import_clause
        (import_default_specifier
            (identifier) @import.default))) @import.default

(import_statement
    (import_clause
        (namespace_import
            (identifier) @import.namespace))) @import.namespace
"""

EXPORTS = """
(export_statement
    declaration: (_) @export.declaration) @export.statement

(export_statement
    (export_clause
        (export_specifier
            name: (identifier) @export.name
            alias: (identifier)? @export.alias))) @export.named
"""

# Object and property definitions
OBJECTS = """
(object
    (pair
        key: (_) @property.key
        value: (_) @property.value)) @object.literal

(property_definition
    property: (_) @property.name
    value: (_)? @property.value) @property.definition
"""

# Comments
COMMENTS = """
(comment) @comment
"""

# All queries combined
ALL_QUERIES = {
    "functions": {
        "query": FUNCTIONS,
        "description": "Search all function declarations, expressions, and methods",
    },
    "classes": {
        "query": CLASSES,
        "description": "Search all class declarations and expressions",
    },
    "variables": {
        "query": VARIABLES,
        "description": "Search all variable declarations (var, let, const)",
    },
    "imports": {
        "query": IMPORTS,
        "description": "Search all import statements and clauses",
    },
    "exports": {"query": EXPORTS, "description": "Search all export statements"},
    "objects": {
        "query": OBJECTS,
        "description": "Search object literals and property definitions",
    },
    "comments": {"query": COMMENTS, "description": "Search all comments"},
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
