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
        (type_parameter_list)) @generic_class
    """,
    "generic_method": """
    (method_declaration
        name: (identifier) @method_name
        (type_parameter_list)) @generic_method
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
    (comment) @xml_documentation
    (#match? @xml_documentation "^///")
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

# Query descriptions
CSHARP_QUERY_DESCRIPTIONS: dict[str, str] = {
    "class": "Extract class declarations",
    "interface": "Extract interface declarations",
    "record": "Extract record declarations (C# 9+)",
    "enum": "Extract enum declarations",
    "struct": "Extract struct declarations",
    "method": "Extract method declarations",
    "constructor": "Extract constructor declarations",
    "async_method": "Extract async method declarations",
    "public_method": "Extract public method declarations",
    "private_method": "Extract private method declarations",
    "static_method": "Extract static method declarations",
    "property": "Extract property declarations",
    "auto_property": "Extract auto-implemented properties",
    "computed_property": "Extract computed properties (arrow expression)",
    "field": "Extract field declarations",
    "const_field": "Extract const field declarations",
    "readonly_field": "Extract readonly field declarations",
    "event": "Extract event declarations",
    "using": "Extract using directives",
    "static_using": "Extract static using directives",
    "namespace": "Extract namespace declarations",
    "attribute": "Extract attribute lists",
    "http_attribute": "Extract HTTP method attributes (HttpGet, HttpPost, etc.)",
    "authorize_attribute": "Extract Authorize attributes",
    "generic_class": "Extract generic class declarations",
    "generic_method": "Extract generic method declarations",
    "linq_query": "Extract LINQ query expressions",
    "from_clause": "Extract LINQ from clauses",
    "where_clause": "Extract LINQ where clauses",
    "select_clause": "Extract LINQ select clauses",
    "lambda": "Extract lambda expressions",
    "arrow_function": "Extract arrow expression clauses",
    "if_statement": "Extract if statements",
    "for_statement": "Extract for statements",
    "foreach_statement": "Extract foreach statements",
    "while_statement": "Extract while statements",
    "switch_statement": "Extract switch statements",
    "try_statement": "Extract try statements",
    "catch_clause": "Extract catch clauses",
    "nullable_type": "Extract nullable type references",
    "switch_expression": "Extract switch expressions (C# 8+)",
    "pattern": "Extract pattern matching patterns",
    "delegate": "Extract delegate declarations",
    "comment": "Extract comments",
    "xml_documentation": "Extract XML documentation comments (///)",
    "all_declarations": "Extract all type and member declarations",
}

# Structured query registry for dynamic loader compatibility
ALL_QUERIES: dict[str, dict[str, str]] = {}
for query_name, query_string in CSHARP_QUERIES.items():
    description = CSHARP_QUERY_DESCRIPTIONS.get(
        query_name, f"Query '{query_name}' for C#"
    )
    ALL_QUERIES[query_name] = {"query": query_string, "description": description}

# Cross-language aliases
ALL_QUERIES["classes"] = ALL_QUERIES["class"]
ALL_QUERIES["functions"] = ALL_QUERIES["method"]
ALL_QUERIES["methods"] = ALL_QUERIES["method"]
ALL_QUERIES["imports"] = ALL_QUERIES["using"]
ALL_QUERIES["variables"] = ALL_QUERIES["field"]


def get_all_queries() -> dict:
    return ALL_QUERIES


def get_query(name: str) -> str:
    if name in ALL_QUERIES:
        q = ALL_QUERIES[name]
        return q["query"] if isinstance(q, dict) else q
    raise ValueError(f"Query '{name}' not found. Available: {list(ALL_QUERIES.keys())}")


def list_queries() -> list:
    return list(ALL_QUERIES.keys())
