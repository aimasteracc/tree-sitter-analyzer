#!/usr/bin/env python3
"""
TypeScript Tree-sitter queries for code analysis.
"""

# Function declarations and expressions
FUNCTIONS = """
(function_declaration
    name: (identifier) @function.name
    parameters: (formal_parameters) @function.params
    return_type: (type_annotation)? @function.return_type
    body: (statement_block) @function.body) @function.declaration

(function_expression
    name: (identifier)? @function.name
    parameters: (formal_parameters) @function.params
    return_type: (type_annotation)? @function.return_type
    body: (statement_block) @function.body) @function.expression

(arrow_function
    parameters: (_) @function.params
    return_type: (type_annotation)? @function.return_type
    body: (_) @function.body) @function.arrow

(method_definition
    name: (_) @function.name
    parameters: (formal_parameters) @function.params
    return_type: (type_annotation)? @function.return_type
    body: (statement_block) @function.body) @method.definition
"""

# Class declarations
CLASSES = """
(class_declaration
    name: (type_identifier) @class.name
    type_parameters: (type_parameters)? @class.generics
    superclass: (class_heritage)? @class.superclass
    body: (class_body) @class.body) @class.declaration

(abstract_class_declaration
    name: (type_identifier) @class.name
    type_parameters: (type_parameters)? @class.generics
    superclass: (class_heritage)? @class.superclass
    body: (class_body) @class.body) @class.abstract
"""

# Interface declarations
INTERFACES = """
(interface_declaration
    name: (type_identifier) @interface.name
    type_parameters: (type_parameters)? @interface.generics
    body: (object_type) @interface.body) @interface.declaration
"""

# Type aliases
TYPE_ALIASES = """
(type_alias_declaration
    name: (type_identifier) @type.name
    type_parameters: (type_parameters)? @type.generics
    value: (_) @type.value) @type.alias
"""

# Enum declarations
ENUMS = """
(enum_declaration
    name: (identifier) @enum.name
    body: (enum_body) @enum.body) @enum.declaration
"""

# Variable declarations with types
VARIABLES = """
(variable_declaration
    (variable_declarator
        name: (identifier) @variable.name
        type: (type_annotation)? @variable.type
        value: (_)? @variable.value)) @variable.declaration

(lexical_declaration
    (variable_declarator
        name: (identifier) @variable.name
        type: (type_annotation)? @variable.type
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

(type_import
    (import_clause
        (named_imports
            (import_specifier
                name: (identifier) @import.type.name
                alias: (identifier)? @import.type.alias)))) @import.type
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

# Decorators (TypeScript specific)
DECORATORS = """
(decorator
    (identifier) @decorator.name) @decorator.simple

(decorator
    (call_expression
        function: (identifier) @decorator.name
        arguments: (arguments) @decorator.args)) @decorator.call

(decorator
    (member_expression
        object: (identifier) @decorator.object
        property: (property_identifier) @decorator.name)) @decorator.member
"""

# Generic type parameters
GENERICS = """
(type_parameters
    (type_parameter
        name: (type_identifier) @generic.name
        constraint: (type_annotation)? @generic.constraint
        default: (type_annotation)? @generic.default)) @generic.parameter
"""

# Property signatures and method signatures
SIGNATURES = """
(property_signature
    name: (_) @property.name
    type: (type_annotation) @property.type) @property.signature

(method_signature
    name: (_) @method.name
    parameters: (formal_parameters) @method.params
    return_type: (type_annotation)? @method.return_type) @method.signature

(construct_signature
    parameters: (formal_parameters) @constructor.params
    return_type: (type_annotation)? @constructor.return_type) @constructor.signature
"""

# Comments
COMMENTS = """
(comment) @comment
"""

# All queries combined
ALL_QUERIES = {
    "functions": {
        "query": FUNCTIONS,
        "description": "Search all function declarations, expressions, and methods with type annotations",
    },
    "classes": {
        "query": CLASSES,
        "description": "Search all class declarations including abstract classes",
    },
    "interfaces": {
        "query": INTERFACES,
        "description": "Search all interface declarations",
    },
    "type_aliases": {
        "query": TYPE_ALIASES,
        "description": "Search all type alias declarations",
    },
    "enums": {"query": ENUMS, "description": "Search all enum declarations"},
    "variables": {
        "query": VARIABLES,
        "description": "Search all variable declarations with type annotations",
    },
    "imports": {
        "query": IMPORTS,
        "description": "Search all import statements including type imports",
    },
    "exports": {"query": EXPORTS, "description": "Search all export statements"},
    "decorators": {"query": DECORATORS, "description": "Search all decorators"},
    "generics": {
        "query": GENERICS,
        "description": "Search all generic type parameters",
    },
    "signatures": {
        "query": SIGNATURES,
        "description": "Search property signatures, method signatures, and constructor signatures",
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
