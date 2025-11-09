#!/usr/bin/env python3
"""
C# Language Queries

Comprehensive Tree-sitter queries for C# language constructs.
Covers classes, methods, properties, fields, and modern C# features.
"""

# C#-specific query library
CSHARP_QUERIES: dict[str, str] = {
    # --- Class Declarations ---
    "class": """
    (class_declaration
        name: (identifier) @class_name) @class
    """,
    "interface": """
    (interface_declaration
        name: (identifier) @interface_name) @interface
    """,
    "record": """
    (record_declaration
        name: (identifier) @record_name) @record
    """,
    "enum": """
    (enum_declaration
        name: (identifier) @enum_name) @enum
    """,
    "struct": """
    (struct_declaration
        name: (identifier) @struct_name) @struct
    """,
    # --- Methods ---
    "method": """
    (method_declaration
        name: (identifier) @method_name) @method
    """,
    "constructor": """
    (constructor_declaration
        name: (identifier) @constructor_name) @constructor
    """,
    "async_method": """
    (method_declaration
        (modifier)* @modifier
        (#match? @modifier "async")
        name: (identifier) @method_name) @async_method
    """,
    "public_method": """
    (method_declaration
        (modifier)* @modifier
        (#match? @modifier "public")
        name: (identifier) @method_name) @public_method
    """,
    "private_method": """
    (method_declaration
        (modifier)* @modifier
        (#match? @modifier "private")
        name: (identifier) @method_name) @private_method
    """,
    "static_method": """
    (method_declaration
        (modifier)* @modifier
        (#match? @modifier "static")
        name: (identifier) @method_name) @static_method
    """,
    # --- Properties ---
    "property": """
    (property_declaration
        name: (identifier) @property_name) @property
    """,
    "auto_property": """
    (property_declaration
        name: (identifier) @property_name
        (accessor_list)) @auto_property
    """,
    "computed_property": """
    (property_declaration
        name: (identifier) @property_name
        (arrow_expression_clause)) @computed_property
    """,
    # --- Fields ---
    "field": """
    (field_declaration) @field
    """,
    "const_field": """
    (field_declaration
        (modifier)* @modifier
        (#match? @modifier "const")) @const_field
    """,
    "readonly_field": """
    (field_declaration
        (modifier)* @modifier
        (#match? @modifier "readonly")) @readonly_field
    """,
    "event": """
    (event_field_declaration) @event
    """,
    # --- Using Directives ---
    "using": """
    (using_directive) @using
    """,
    "static_using": """
    (using_directive
        "static") @static_using
    """,
    # --- Namespaces ---
    "namespace": """
    (namespace_declaration
        name: (identifier) @namespace_name) @namespace
    """,
    # --- Attributes ---
    "attribute": """
    (attribute_list) @attribute
    """,
    "http_attribute": """
    (attribute_list
        (attribute
            name: (identifier) @attr_name
            (#match? @attr_name "^Http(Get|Post|Put|Delete|Patch)$"))) @http_attribute
    """,
    "authorize_attribute": """
    (attribute_list
        (attribute
            name: (identifier) @attr_name
            (#match? @attr_name "^Authorize$"))) @authorize_attribute
    """,
    # --- Generic Types ---
    "generic_class": """
    (class_declaration
        name: (identifier) @class_name
        type_parameters: (type_parameter_list)) @generic_class
    """,
    "generic_method": """
    (method_declaration
        name: (identifier) @method_name
        type_parameters: (type_parameter_list)) @generic_method
    """,
    # --- LINQ Queries ---
    "linq_query": """
    (query_expression) @linq_query
    """,
    "from_clause": """
    (from_clause) @from_clause
    """,
    "where_clause": """
    (where_clause) @where_clause
    """,
    "select_clause": """
    (select_clause) @select_clause
    """,
    # --- Lambda Expressions ---
    "lambda": """
    (lambda_expression) @lambda
    """,
    "arrow_function": """
    (arrow_expression_clause) @arrow_function
    """,
    # --- Control Flow ---
    "if_statement": """
    (if_statement) @if_statement
    """,
    "for_statement": """
    (for_statement) @for_statement
    """,
    "foreach_statement": """
    (foreach_statement) @foreach_statement
    """,
    "while_statement": """
    (while_statement) @while_statement
    """,
    "switch_statement": """
    (switch_statement) @switch_statement
    """,
    "try_statement": """
    (try_statement) @try_statement
    """,
    "catch_clause": """
    (catch_clause) @catch_clause
    """,
    # --- Nullable Reference Types ---
    "nullable_type": """
    (nullable_type) @nullable_type
    """,
    # --- Pattern Matching ---
    "switch_expression": """
    (switch_expression) @switch_expression
    """,
    "pattern": """
    (pattern) @pattern
    """,
    # --- Delegates ---
    "delegate": """
    (delegate_declaration
        name: (identifier) @delegate_name) @delegate
    """,
    # --- Comments ---
    "comment": """
    (comment) @comment
    """,
    "xml_documentation": """
    (comment
        (#match? @comment "^///")) @xml_documentation
    """,
    # --- All Declarations ---
    "all_declarations": """
    [
        (class_declaration)
        (interface_declaration)
        (record_declaration)
        (enum_declaration)
        (struct_declaration)
        (method_declaration)
        (property_declaration)
        (field_declaration)
    ] @declaration
    """,
}
