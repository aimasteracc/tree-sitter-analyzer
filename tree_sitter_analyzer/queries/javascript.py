#!/usr/bin/env python3
"""
JavaScript Language Queries

Comprehensive Tree-sitter queries for JavaScript language constructs.
Covers functions, classes, variables, imports, exports, and modern JavaScript features.
Equivalent to Java query coverage for consistent language support.
"""

# JavaScript-specific query library
JAVASCRIPT_QUERIES: dict[str, str] = {
    # --- Basic Structure ---
    "function": """
    (function_declaration) @function
    """,
    "function_declaration": """
    (function_declaration
        name: (identifier) @function_name
        parameters: (formal_parameters) @parameters
        body: (statement_block) @body) @function_declaration
    """,
    "function_expression": """
    (function_expression
        name: (identifier)? @function_name
        parameters: (formal_parameters) @parameters
        body: (statement_block) @body) @function_expression
    """,
    "arrow_function": """
    (arrow_function
        parameters: (formal_parameters) @parameters
        body: (_) @body) @arrow_function
    """,
    "method_definition": """
    (method_definition
        name: (property_identifier) @method_name
        parameters: (formal_parameters) @parameters
        body: (statement_block) @body) @method_definition
    """,
    "async_function": """
    (function_declaration
        "async" @async_keyword
        name: (identifier) @function_name
        parameters: (formal_parameters) @parameters
        body: (statement_block) @body) @async_function
    """,
    "generator_function": """
    (generator_function_declaration
        name: (identifier) @function_name
        parameters: (formal_parameters) @parameters
        body: (statement_block) @body) @generator_function
    """,
    # --- Classes ---
    "class": """
    (class_declaration) @class
    """,
    "class_declaration": """
    (class_declaration
        name: (identifier) @class_name
        superclass: (class_heritage)? @superclass
        body: (class_body) @body) @class_declaration
    """,
    "class_expression": """
    (class_expression
        name: (identifier)? @class_name
        superclass: (class_heritage)? @superclass
        body: (class_body) @body) @class_expression
    """,
    "class_method": """
    (class_body
        (method_definition
            name: (property_identifier) @method_name
            parameters: (formal_parameters) @parameters
            body: (statement_block) @body)) @class_method
    """,
    "constructor": """
    (method_definition
        name: (property_identifier) @constructor_name
        (#match? @constructor_name "constructor")
        parameters: (formal_parameters) @parameters
        body: (statement_block) @body) @constructor
    """,
    "getter": """
    (method_definition
        "get" @get_keyword
        name: (property_identifier) @getter_name
        body: (statement_block) @body) @getter
    """,
    "setter": """
    (method_definition
        "set" @set_keyword
        name: (property_identifier) @setter_name
        parameters: (formal_parameters) @parameters
        body: (statement_block) @body) @setter
    """,
    "static_method": """
    (method_definition
        "static" @static_keyword
        name: (property_identifier) @method_name
        parameters: (formal_parameters) @parameters
        body: (statement_block) @body) @static_method
    """,
    "private_method": """
    (method_definition
        name: (private_property_identifier) @method_name
        parameters: (formal_parameters) @parameters
        body: (statement_block) @body) @private_method
    """,
    # --- Variables ---
    "variable": """
    (variable_declaration) @variable
    """,
    "var_declaration": """
    (variable_declaration
        (variable_declarator
            name: (identifier) @variable_name
            value: (_)? @value)) @var_declaration
    """,
    "let_declaration": """
    (lexical_declaration
        "let" @let_keyword
        (variable_declarator
            name: (identifier) @variable_name
            value: (_)? @value)) @let_declaration
    """,
    "const_declaration": """
    (lexical_declaration
        "const" @const_keyword
        (variable_declarator
            name: (identifier) @variable_name
            value: (_) @value)) @const_declaration
    """,
    "destructuring_assignment": """
    (variable_declarator
        name: (array_pattern) @array_destructuring
        value: (_) @value) @destructuring_assignment
    """,
    "object_destructuring": """
    (variable_declarator
        name: (object_pattern) @object_destructuring
        value: (_) @value) @object_destructuring
    """,
    # --- Imports and Exports ---
    "import": """
    (import_statement) @import
    """,
    "import_statement": """
    (import_statement
        source: (string) @source) @import_statement
    """,
    "import_default": """
    (import_statement
        (import_clause
            (import_default_specifier
                (identifier) @default_name))
        source: (string) @source) @import_default
    """,
    "import_named": """
    (import_statement
        (import_clause
            (named_imports
                (import_specifier
                    name: (identifier) @import_name
                    alias: (identifier)? @alias)))
        source: (string) @source) @import_named
    """,
    "import_namespace": """
    (import_statement
        (import_clause
            (namespace_import
                (identifier) @namespace_name))
        source: (string) @source) @import_namespace
    """,
    "dynamic_import": """
    (call_expression
        function: (identifier) @import_function
        (#match? @import_function "import")
        arguments: (arguments (string) @source)) @dynamic_import
    """,
    "export": """
    (export_statement) @export
    """,
    "export_default": """
    (export_statement
        "default" @default_keyword
        declaration: (_) @declaration) @export_default
    """,
    "export_named": """
    (export_statement
        (export_clause
            (export_specifier
                name: (identifier) @export_name
                alias: (identifier)? @alias))) @export_named
    """,
    "export_all": """
    (export_statement
        "*" @star
        source: (string) @source) @export_all
    """,
    # --- Objects and Properties ---
    "object": """
    (object) @object
    """,
    "object_literal": """
    (object
        (pair
            key: (_) @key
            value: (_) @value)*) @object_literal
    """,
    "property_definition": """
    (property_definition
        property: (_) @property_name
        value: (_)? @value) @property_definition
    """,
    "computed_property": """
    (pair
        key: (computed_property_name) @computed_key
        value: (_) @value) @computed_property
    """,
    "shorthand_property": """
    (shorthand_property_identifier) @shorthand_property
    """,
    "method_property": """
    (pair
        key: (_) @method_name
        value: (function_expression) @method_function) @method_property
    """,
    # --- Control Flow ---
    "if_statement": """
    (if_statement
        condition: (_) @condition
        consequence: (_) @then_branch
        alternative: (_)? @else_branch) @if_statement
    """,
    "for_statement": """
    (for_statement
        initializer: (_)? @init
        condition: (_)? @condition
        increment: (_)? @update
        body: (_) @body) @for_statement
    """,
    "for_in_statement": """
    (for_in_statement
        left: (_) @variable
        right: (_) @object
        body: (_) @body) @for_in_statement
    """,
    "for_of_statement": """
    (for_of_statement
        left: (_) @variable
        right: (_) @iterable
        body: (_) @body) @for_of_statement
    """,
    "while_statement": """
    (while_statement
        condition: (_) @condition
        body: (_) @body) @while_statement
    """,
    "do_statement": """
    (do_statement
        body: (_) @body
        condition: (_) @condition) @do_statement
    """,
    "switch_statement": """
    (switch_statement
        discriminant: (_) @discriminant
        body: (switch_body) @body) @switch_statement
    """,
    "case_clause": """
    (switch_case
        value: (_) @case_value
        body: (_)* @case_body) @case_clause
    """,
    "default_clause": """
    (switch_default
        body: (_)* @default_body) @default_clause
    """,
    # --- Error Handling ---
    "try_statement": """
    (try_statement
        body: (statement_block) @try_body
        handler: (catch_clause)? @catch_handler
        finalizer: (finally_clause)? @finally_block) @try_statement
    """,
    "catch_clause": """
    (catch_clause
        parameter: (identifier)? @error_parameter
        body: (statement_block) @catch_body) @catch_clause
    """,
    "finally_clause": """
    (finally_clause
        body: (statement_block) @finally_body) @finally_clause
    """,
    "throw_statement": """
    (throw_statement
        argument: (_) @thrown_expression) @throw_statement
    """,
    # --- Modern JavaScript Features ---
    "template_literal": """
    (template_literal) @template_literal
    """,
    "template_substitution": """
    (template_substitution
        expression: (_) @substitution_expr) @template_substitution
    """,
    "spread_element": """
    (spread_element
        argument: (_) @spread_argument) @spread_element
    """,
    "rest_parameter": """
    (rest_parameter
        pattern: (identifier) @rest_name) @rest_parameter
    """,
    "await_expression": """
    (await_expression
        argument: (_) @awaited_expression) @await_expression
    """,
    "yield_expression": """
    (yield_expression
        argument: (_)? @yielded_value) @yield_expression
    """,
    # --- JSX (React) ---
    "jsx_element": """
    (jsx_element
        open_tag: (jsx_opening_element) @open_tag
        close_tag: (jsx_closing_element)? @close_tag) @jsx_element
    """,
    "jsx_self_closing": """
    (jsx_self_closing_element
        name: (_) @element_name) @jsx_self_closing
    """,
    "jsx_attribute": """
    (jsx_attribute
        name: (property_identifier) @attribute_name
        value: (_)? @attribute_value) @jsx_attribute
    """,
    "jsx_expression": """
    (jsx_expression
        expression: (_) @jsx_expression_content) @jsx_expression
    """,
    # --- Comments and Documentation ---
    "comment": """
    (comment) @comment
    """,
    "jsdoc_comment": """
    (comment) @jsdoc_comment
    (#match? @jsdoc_comment "^/\\*\\*")
    """,
    "line_comment": """
    (comment) @line_comment
    (#match? @line_comment "^//")
    """,
    "block_comment": """
    (comment) @block_comment
    (#match? @block_comment "^/\\*(?!\\*)")
    """,
    # --- Framework-specific Patterns ---
    "react_component": """
    (function_declaration
        name: (identifier) @component_name
        (#match? @component_name "^[A-Z]")
        body: (statement_block
            (return_statement
                argument: (jsx_element)))) @react_component
    """,
    "react_hook": """
    (call_expression
        function: (identifier) @hook_name
        (#match? @hook_name "^use[A-Z]")) @react_hook
    """,
    "node_require": """
    (call_expression
        function: (identifier) @require_function
        (#match? @require_function "require")
        arguments: (arguments (string) @module_path)) @node_require
    """,
    "module_exports": """
    (assignment_expression
        left: (member_expression
            object: (identifier) @module_object
            (#match? @module_object "module")
            property: (property_identifier) @exports_property
            (#match? @exports_property "exports"))
        right: (_) @exported_value) @module_exports
    """,
    # --- Name-only Extraction ---
    "function_name": """
    (function_declaration
        name: (identifier) @function_name)
    """,
    "class_name": """
    (class_declaration
        name: (identifier) @class_name)
    """,
    "variable_name": """
    (variable_declarator
        name: (identifier) @variable_name)
    """,
    # --- Advanced Patterns ---
    "closure": """
    (function_expression
        body: (statement_block
            (return_statement
                argument: (function_expression)))) @closure
    """,
    "callback_function": """
    (call_expression
        arguments: (arguments
            (function_expression) @callback_function)) @callback_call
    """,
    "promise_chain": """
    (call_expression
        function: (member_expression
            object: (_) @promise_object
            property: (property_identifier) @chain_method
            (#match? @chain_method "^(then|catch|finally)$"))) @promise_chain
    """,
    "event_listener": """
    (call_expression
        function: (member_expression
            property: (property_identifier) @listener_method
            (#match? @listener_method "^(addEventListener|on)$"))
        arguments: (arguments
            (string) @event_type
            (function_expression) @event_handler)) @event_listener
    """,
    "iife": """
    (call_expression
        function: (function_expression) @iife_function) @iife
    """,
    "module_pattern": """
    (variable_declarator
        name: (identifier) @module_name
        value: (call_expression
            function: (function_expression) @module_function)) @module_pattern
    """,
}

# Query descriptions
JAVASCRIPT_QUERY_DESCRIPTIONS: dict[str, str] = {
    "function": "Search JavaScript function declarations",
    "function_declaration": "Search function declarations with details",
    "function_expression": "Search function expressions",
    "arrow_function": "Search arrow functions",
    "method_definition": "Search method definitions",
    "async_function": "Search async function declarations",
    "generator_function": "Search generator functions",
    "class": "Search JavaScript class declarations",
    "class_declaration": "Search class declarations with details",
    "class_expression": "Search class expressions",
    "class_method": "Search class methods",
    "constructor": "Search class constructors",
    "getter": "Search getter methods",
    "setter": "Search setter methods",
    "static_method": "Search static methods",
    "private_method": "Search private methods",
    "variable": "Search variable declarations",
    "var_declaration": "Search var declarations",
    "let_declaration": "Search let declarations",
    "const_declaration": "Search const declarations",
    "destructuring_assignment": "Search destructuring assignments",
    "object_destructuring": "Search object destructuring",
    "import": "Search import statements",
    "import_statement": "Search import statements with details",
    "import_default": "Search default imports",
    "import_named": "Search named imports",
    "import_namespace": "Search namespace imports",
    "dynamic_import": "Search dynamic imports",
    "export": "Search export statements",
    "export_default": "Search default exports",
    "export_named": "Search named exports",
    "export_all": "Search export all statements",
    "object": "Search object literals",
    "object_literal": "Search object literals with properties",
    "property_definition": "Search property definitions",
    "computed_property": "Search computed properties",
    "shorthand_property": "Search shorthand properties",
    "method_property": "Search method properties",
    "if_statement": "Search if statements",
    "for_statement": "Search for loops",
    "for_in_statement": "Search for-in loops",
    "for_of_statement": "Search for-of loops",
    "while_statement": "Search while loops",
    "do_statement": "Search do-while loops",
    "switch_statement": "Search switch statements",
    "case_clause": "Search switch case clauses",
    "default_clause": "Search switch default clauses",
    "try_statement": "Search try-catch statements",
    "catch_clause": "Search catch clauses",
    "finally_clause": "Search finally clauses",
    "throw_statement": "Search throw statements",
    "template_literal": "Search template literals",
    "template_substitution": "Search template substitutions",
    "spread_element": "Search spread elements",
    "rest_parameter": "Search rest parameters",
    "await_expression": "Search await expressions",
    "yield_expression": "Search yield expressions",
    "jsx_element": "Search JSX elements",
    "jsx_self_closing": "Search self-closing JSX elements",
    "jsx_attribute": "Search JSX attributes",
    "jsx_expression": "Search JSX expressions",
    "comment": "Search all comments",
    "jsdoc_comment": "Search JSDoc comments",
    "line_comment": "Search line comments",
    "block_comment": "Search block comments",
    "react_component": "Search React components",
    "react_hook": "Search React hooks",
    "node_require": "Search Node.js require statements",
    "module_exports": "Search Node.js module exports",
    "function_name": "Search function names only",
    "class_name": "Search class names only",
    "variable_name": "Search variable names only",
    "closure": "Search closures",
    "callback_function": "Search callback functions passed as arguments",
    "promise_chain": "Search Promise chain patterns (.then, .catch, .finally)",
    "event_listener": "Search event listener registrations",
    "iife": "Search immediately invoked function expressions",
    "module_pattern": "Search module patterns",
}

# Legacy query definitions for backward compatibility
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

IMPORTS = """
(import_statement
    source: (string) @import.source) @import.statement

(import_statement
    (import_clause
        (named_imports
            (import_specifier
                name: (identifier) @import.name
                alias: (identifier)? @import.alias)))) @import.named

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

OBJECTS = """
(object
    (pair
        key: (_) @property.key
        value: (_) @property.value)) @object.literal

(property_definition
    property: (_) @property.name
    value: (_)? @property.value) @property.definition
"""

COMMENTS = """
(comment) @comment
"""

# Convert to ALL_QUERIES format for dynamic loader compatibility
ALL_QUERIES = {}
for query_name, query_string in JAVASCRIPT_QUERIES.items():
    description = JAVASCRIPT_QUERY_DESCRIPTIONS.get(query_name, "No description")
    ALL_QUERIES[query_name] = {"query": query_string, "description": description}

# Add legacy queries for backward compatibility
ALL_QUERIES["functions"] = {
    "query": FUNCTIONS,
    "description": "Search all function declarations, expressions, and methods",
}
ALL_QUERIES["classes"] = {
    "query": CLASSES,
    "description": "Search all class declarations and expressions",
}
ALL_QUERIES["variables"] = {
    "query": VARIABLES,
    "description": "Search all variable declarations (var, let, const)",
}
ALL_QUERIES["imports"] = {
    "query": IMPORTS,
    "description": "Search all import statements and clauses",
}
ALL_QUERIES["exports"] = {
    "query": EXPORTS,
    "description": "Search all export statements",
}
ALL_QUERIES["objects"] = {
    "query": OBJECTS,
    "description": "Search object literals and property definitions",
}
ALL_QUERIES["comments"] = {"query": COMMENTS, "description": "Search all comments"}

# Add missing method queries
ALL_QUERIES["method"] = {
    "query": """
(method_definition
    name: (property_identifier) @method_name
    parameters: (formal_parameters) @parameters
    body: (statement_block) @body) @method_definition
""",
    "description": "Search method definitions",
}
ALL_QUERIES["methods"] = {
    "query": """
(method_definition
    name: (property_identifier) @method_name
    parameters: (formal_parameters) @parameters
    body: (statement_block) @body) @method_definition
""",
    "description": "Search method definitions",
}


def get_javascript_query(name: str) -> str:
    """
    Get the specified JavaScript query

    Args:
        name: Query name

    Returns:
        Query string

    Raises:
        ValueError: When query is not found
    """
    if name not in JAVASCRIPT_QUERIES:
        available = list(JAVASCRIPT_QUERIES.keys())
        raise ValueError(
            f"JavaScript query '{name}' does not exist. Available: {available}"
        )

    return JAVASCRIPT_QUERIES[name]


def get_javascript_query_description(name: str) -> str:
    """
    Get the description of the specified JavaScript query

    Args:
        name: Query name

    Returns:
        Query description
    """
    return JAVASCRIPT_QUERY_DESCRIPTIONS.get(name, "No description")


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


def get_available_javascript_queries() -> list[str]:
    """
    Get list of available JavaScript queries

    Returns:
        List of query names
    """
    return list(JAVASCRIPT_QUERIES.keys())
