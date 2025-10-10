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
    body: (class_body) @class.body) @class.declaration

(abstract_class_declaration
    name: (type_identifier) @class.name
    type_parameters: (type_parameters)? @class.generics
    body: (class_body) @class.body) @class.abstract
"""

# Interface declarations
INTERFACES = """
(interface_declaration
    name: (type_identifier) @interface.name
    type_parameters: (type_parameters)? @interface.generics
    body: (interface_body) @interface.body) @interface.declaration
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
                alias: (identifier)? @import.alias)))) @import.named

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
        "description": "Search all functions: declarations, expressions, and methods with type annotations",
    },
    "classes": {
        "query": CLASSES,
        "description": "Search all class declarations including abstract classes",
    },
    "interfaces": {
        "query": INTERFACES,
        "description": "Search all interfaces declarations",
    },
    "type_aliases": {
        "query": TYPE_ALIASES,
        "description": "Search all type aliases declarations",
    },
    "enums": {"query": ENUMS, "description": "Search all enums declarations"},
    "variables": {
        "query": VARIABLES,
        "description": "Search all variables declarations with type annotations",
    },
    "imports": {
        "query": IMPORTS,
        "description": "Search all import statements including type imports",
    },
    "exports": {"query": EXPORTS, "description": "Search all export statements"},
    "decorators": {"query": DECORATORS, "description": "Search all decorators"},
    "generics": {
        "query": GENERICS,
        "description": "Search all generics type parameters",
    },
    "signatures": {
        "query": SIGNATURES,
        "description": "Search property signatures, method signatures, and constructor signatures",
    },
    "comments": {"query": COMMENTS, "description": "Search all comments"},
}

# Add common query aliases for cross-language compatibility
ALL_QUERIES["methods"] = {
    "query": FUNCTIONS,
    "description": "Search all methods declarations (alias for functions)",
}

# Add singular form aliases
ALL_QUERIES["function"] = {
    "query": FUNCTIONS,
    "description": "Search all functions (alias for functions)",
}
ALL_QUERIES["class"] = {
    "query": CLASSES,
    "description": "Search all classes (alias for classes)",
}
ALL_QUERIES["interface"] = {
    "query": INTERFACES,
    "description": "Search all interfaces (alias for interfaces)",
}
ALL_QUERIES["type"] = {
    "query": TYPE_ALIASES,
    "description": "Search all type aliases (alias for type_aliases)",
}
ALL_QUERIES["types"] = {
    "query": TYPE_ALIASES,
    "description": "Search all types (alias for type_aliases)",
}

# Add more specific function queries
ALL_QUERIES["function_declaration"] = {
    "query": """
(function_declaration
    name: (identifier) @function.name
    parameters: (formal_parameters) @function.params
    return_type: (type_annotation)? @function.return_type
    body: (statement_block) @function.body) @function.declaration
""",
    "description": "Search function declarations only",
}

ALL_QUERIES["arrow_function"] = {
    "query": """
(arrow_function
    parameters: (_) @function.params
    return_type: (type_annotation)? @function.return_type
    body: (_) @function.body) @function.arrow
""",
    "description": "Search arrow functions only",
}

ALL_QUERIES["method_definition"] = {
    "query": """
(method_definition
    name: (_) @function.name
    parameters: (formal_parameters) @function.params
    return_type: (type_annotation)? @function.return_type
    body: (statement_block) @function.body) @method.definition
""",
    "description": "Search method definitions only",
}

ALL_QUERIES["async_function"] = {
    "query": """
(function_declaration
    "async" @async_keyword
    name: (identifier) @function.name
    parameters: (formal_parameters) @function.params
    return_type: (type_annotation)? @function.return_type
    body: (statement_block) @function.body) @async_function
""",
    "description": "Search async function declarations",
}

# Add more specific class queries
ALL_QUERIES["class_declaration"] = {
    "query": """
(class_declaration
    name: (type_identifier) @class.name
    type_parameters: (type_parameters)? @class.generics
    body: (class_body) @class.body) @class.declaration
""",
    "description": "Search class declarations only",
}

ALL_QUERIES["abstract_class"] = {
    "query": """
(abstract_class_declaration
    name: (type_identifier) @class.name
    type_parameters: (type_parameters)? @class.generics
    body: (class_body) @class.body) @class.abstract
""",
    "description": "Search abstract class declarations",
}

# Add variable-specific queries
ALL_QUERIES["const_declaration"] = {
    "query": """
(lexical_declaration
    "const" @const_keyword
    (variable_declarator
        name: (identifier) @variable.name
        value: (_)? @variable.value)) @const_declaration
""",
    "description": "Search const declarations",
}

ALL_QUERIES["let_declaration"] = {
    "query": """
(lexical_declaration
    "let" @let_keyword
    (variable_declarator
        name: (identifier) @variable.name
        value: (_)? @variable.value)) @let_declaration
""",
    "description": "Search let declarations",
}

# Add import-specific queries
ALL_QUERIES["import_statement"] = {
    "query": """
(import_statement
    source: (string) @import.source) @import.statement
""",
    "description": "Search import statements with details",
}

ALL_QUERIES["type_import"] = {
    "query": """
(import_statement
    "type" @type_keyword
    (import_clause) @import.clause
    source: (string) @import.source) @type_import
""",
    "description": "Search type import statements",
}

# Add TypeScript-specific queries
ALL_QUERIES["namespace"] = {
    "query": """
(module
    name: (identifier) @namespace.name
    body: (statement_block) @namespace.body) @namespace.declaration
""",
    "description": "Search namespace declarations",
}

ALL_QUERIES["generic_type"] = {
    "query": """
(type_parameters
    (type_parameter
        name: (type_identifier) @generic.name
        constraint: (type_annotation)? @generic.constraint)) @generic.parameter
""",
    "description": "Search generic type parameters",
}

ALL_QUERIES["union_type"] = {
    "query": """
(union_type) @union.type
""",
    "description": "Search union types",
}

ALL_QUERIES["intersection_type"] = {
    "query": """
(intersection_type) @intersection.type
""",
    "description": "Search intersection types",
}

ALL_QUERIES["conditional_type"] = {
    "query": """
(conditional_type
    left: (_) @conditional.check
    right: (_) @conditional.extends
    consequence: (_) @conditional.true
    alternative: (_) @conditional.false) @conditional.type
""",
    "description": "Search conditional types",
}

ALL_QUERIES["mapped_type"] = {
    "query": """
(mapped_type_clause
    name: (type_identifier) @mapped.key
    type: (_) @mapped.value) @mapped.type
""",
    "description": "Search mapped types",
}

ALL_QUERIES["index_signature"] = {
    "query": """
(index_signature
    name: (identifier) @index.name
    type: (type_annotation) @index.type) @index.signature
""",
    "description": "Search index signatures",
}

ALL_QUERIES["call_signature"] = {
    "query": """
(call_signature
    parameters: (formal_parameters) @call.params
    return_type: (type_annotation)? @call.return) @call.signature
""",
    "description": "Search call signatures",
}

ALL_QUERIES["construct_signature"] = {
    "query": """
(construct_signature
    parameters: (formal_parameters) @construct.params
    return_type: (type_annotation)? @construct.return) @construct.signature
""",
    "description": "Search construct signatures",
}

ALL_QUERIES["getter_method"] = {
    "query": """
(method_definition
    "get" @getter_keyword
    name: (_) @getter.name
    body: (statement_block) @getter.body) @getter.method
""",
    "description": "Search getter methods",
}

ALL_QUERIES["setter_method"] = {
    "query": """
(method_definition
    "set" @setter_keyword
    name: (_) @setter.name
    parameters: (formal_parameters) @setter.params
    body: (statement_block) @setter.body) @setter.method
""",
    "description": "Search setter methods",
}

ALL_QUERIES["static_method"] = {
    "query": """
(method_definition
    "static" @static_keyword
    name: (_) @static.name
    parameters: (formal_parameters) @static.params
    body: (statement_block) @static.body) @static.method
""",
    "description": "Search static methods",
}

ALL_QUERIES["private_method"] = {
    "query": """
(method_definition
    (accessibility_modifier) @private_keyword
    name: (_) @private.name
    parameters: (formal_parameters) @private.params
    body: (statement_block) @private.body) @private.method
(#eq? @private_keyword "private")
""",
    "description": "Search private methods",
}

ALL_QUERIES["protected_method"] = {
    "query": """
(method_definition
    (accessibility_modifier) @protected_keyword
    name: (_) @protected.name
    parameters: (formal_parameters) @protected.params
    body: (statement_block) @protected.body) @protected.method
(#eq? @protected_keyword "protected")
""",
    "description": "Search protected methods",
}

ALL_QUERIES["public_method"] = {
    "query": """
(method_definition
    (accessibility_modifier) @public_keyword
    name: (_) @public.name
    parameters: (formal_parameters) @public.params
    body: (statement_block) @public.body) @public.method
(#eq? @public_keyword "public")
""",
    "description": "Search public methods",
}

ALL_QUERIES["readonly_property"] = {
    "query": """
(property_signature
    "readonly" @readonly_keyword
    name: (_) @readonly.name
    type: (type_annotation)? @readonly.type) @readonly.property
""",
    "description": "Search readonly property declarations",
}

ALL_QUERIES["optional_property"] = {
    "query": """
(property_signature
    name: (_) @optional.name
    "?" @optional_marker
    type: (type_annotation)? @optional.type) @optional.property
""",
    "description": "Search optional property declarations",
}

ALL_QUERIES["template_literal_type"] = {
    "query": """
(template_literal_type) @template.literal
""",
    "description": "Search template literal types",
}

ALL_QUERIES["keyof_type"] = {
    "query": """
(keyof_type_operator
    argument: (_) @keyof.argument) @keyof.type
""",
    "description": "Search keyof type operators",
}

ALL_QUERIES["typeof_type"] = {
    "query": """
(typeof_type
    argument: (_) @typeof.argument) @typeof.type
""",
    "description": "Search typeof type operators",
}

ALL_QUERIES["infer_type"] = {
    "query": """
(infer_type
    name: (type_identifier) @infer.name) @infer.type
""",
    "description": "Search infer types in conditional types",
}

ALL_QUERIES["tuple_type"] = {
    "query": """
(tuple_type) @tuple.type
""",
    "description": "Search tuple types",
}

ALL_QUERIES["array_type"] = {
    "query": """
(array_type) @array.type
""",
    "description": "Search array types",
}

ALL_QUERIES["function_type"] = {
    "query": """
(function_type
    parameters: (formal_parameters) @function_type.params
    return_type: (_) @function_type.return) @function_type.signature
""",
    "description": "Search function type signatures",
}

ALL_QUERIES["constructor_type"] = {
    "query": """
(constructor_type
    parameters: (formal_parameters) @constructor_type.params
    type: (_) @constructor_type.return) @constructor_type.signature
""",
    "description": "Search constructor type signatures",
}

ALL_QUERIES["object_type"] = {
    "query": """
(object_type) @object.type
""",
    "description": "Search object type literals",
}

ALL_QUERIES["literal_type"] = {
    "query": """
(literal_type) @literal.type
""",
    "description": "Search literal types",
}

ALL_QUERIES["predicate_type"] = {
    "query": """
(type_predicate
    parameter_name: (identifier) @predicate.param
    type: (_) @predicate.type) @predicate.signature
""",
    "description": "Search predicate type signatures",
}

ALL_QUERIES["asserts_type"] = {
    "query": """
(asserts
    parameter_name: (identifier) @asserts.param
    type: (_)? @asserts.type) @asserts.signature
""",
    "description": "Search asserts type signatures",
}

ALL_QUERIES["override_method"] = {
    "query": """
(method_definition
    "override" @override_keyword
    name: (_) @override.name
    parameters: (formal_parameters) @override.params
    body: (statement_block) @override.body) @override.method
""",
    "description": "Search override methods",
}

ALL_QUERIES["abstract_method"] = {
    "query": """
(method_definition
    "abstract" @abstract_keyword
    name: (_) @abstract.name
    parameters: (formal_parameters) @abstract.params) @abstract.method
""",
    "description": "Search abstract methods",
}

# Add more TypeScript-specific queries
ALL_QUERIES["jsx_element"] = {
    "query": """
(jsx_element
    open_tag: (jsx_opening_element
        name: (_) @jsx.tag_name) @jsx.open_tag
    close_tag: (jsx_closing_element)? @jsx.close_tag) @jsx.element
""",
    "description": "Search JSX elements",
}

ALL_QUERIES["jsx_self_closing"] = {
    "query": """
(jsx_self_closing_element
    name: (_) @jsx.tag_name) @jsx.self_closing
""",
    "description": "Search jsx self closing elements",
}

ALL_QUERIES["jsx_fragment"] = {
    "query": """
(jsx_fragment) @jsx.fragment
""",
    "description": "Search JSX fragments",
}

ALL_QUERIES["jsx_expression"] = {
    "query": """
(jsx_expression) @jsx.expression
""",
    "description": "Search JSX expressions",
}

ALL_QUERIES["as_expression"] = {
    "query": """
(as_expression) @as.assertion
""",
    "description": "Search as expression type assertions",
}

ALL_QUERIES["type_assertion"] = {
    "query": """
(type_assertion
    type: (_) @assertion.type
    expression: (_) @assertion.expression) @type.assertion
""",
    "description": "Search angle bracket type assertions",
}

ALL_QUERIES["satisfies_expression"] = {
    "query": """
(satisfies_expression
    expression: (_) @satisfies.expression
    type: (_) @satisfies.type) @satisfies.assertion
""",
    "description": "Search satisfies expression type checks",
}

ALL_QUERIES["non_null_expression"] = {
    "query": """
(non_null_expression
    expression: (_) @non_null.expression) @non_null.assertion
""",
    "description": "Search non null expression assertions (!)",
}

ALL_QUERIES["optional_chain"] = {
    "query": """
(optional_chain) @optional.chain
""",
    "description": "Search optional chaining expressions",
}

ALL_QUERIES["nullish_coalescing"] = {
    "query": """
(binary_expression
    left: (_) @nullish.left
    "??" @nullish.operator
    right: (_) @nullish.right) @nullish.coalescing
""",
    "description": "Search nullish coalescing expressions (??)",
}

ALL_QUERIES["rest_pattern"] = {
    "query": """
(rest_pattern) @rest.pattern
""",
    "description": "Search rest patterns (...args)",
}

ALL_QUERIES["spread_element"] = {
    "query": """
(spread_element) @spread.element
""",
    "description": "Search spread elements",
}

ALL_QUERIES["destructuring_pattern"] = {
    "query": """
(object_pattern) @destructuring.object
(array_pattern) @destructuring.array
""",
    "description": "Search destructuring patterns",
}

ALL_QUERIES["template_string"] = {
    "query": """
(template_string) @template.string
""",
    "description": "Search template strings",
}

ALL_QUERIES["regex_literal"] = {
    "query": """
(regex) @regex.literal
""",
    "description": "Search regex literal patterns",
}

ALL_QUERIES["this_type"] = {
    "query": """
(this_type) @this.type
""",
    "description": "Search this type references",
}

ALL_QUERIES["import_type"] = {
    "query": """
(import_statement
    "type" @import_type.keyword
    (import_clause) @import_type.clause
    source: (string) @import_type.source) @import_type.statement
""",
    "description": "Search import type statements",
}

ALL_QUERIES["export_type"] = {
    "query": """
(export_statement
    "type" @export_type.keyword) @export_type.statement
""",
    "description": "Search export type statements",
}

ALL_QUERIES["declare_statement"] = {
    "query": """
(ambient_declaration
    "declare" @declare.keyword) @declare.statement
""",
    "description": "Search declare statements",
}

ALL_QUERIES["module_declaration"] = {
    "query": """
(module
    "module" @module.keyword
    name: (_) @module.name
    body: (_) @module.body) @module.declaration
""",
    "description": "Search module declarations",
}

ALL_QUERIES["global_declaration"] = {
    "query": """
(module
    "global" @global.keyword
    body: (_) @global.body) @global.declaration
""",
    "description": "Search global declarations",
}

ALL_QUERIES["augmentation"] = {
    "query": """
(module
    name: (string) @augmentation.name
    body: (_) @augmentation.body) @module.augmentation
""",
    "description": "Search module augmentations",
}

ALL_QUERIES["triple_slash_directive"] = {
    "query": """
(comment) @directive.comment
(#match? @directive.comment "^///\\s*<")
""",
    "description": "Search triple slash directive comments",
}

ALL_QUERIES["readonly_modifier"] = {
    "query": """
"readonly" @readonly.modifier
""",
    "description": "Search readonly modifiers",
}

ALL_QUERIES["static_modifier"] = {
    "query": """
"static" @static.modifier
""",
    "description": "Search static modifiers",
}

ALL_QUERIES["async_modifier"] = {
    "query": """
"async" @async.modifier
""",
    "description": "Search async modifiers",
}

ALL_QUERIES["override_modifier"] = {
    "query": """
"override" @override.modifier
""",
    "description": "Search override modifiers",
}

ALL_QUERIES["abstract_modifier"] = {
    "query": """
"abstract" @abstract.modifier
""",
    "description": "Search abstract modifiers",
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
