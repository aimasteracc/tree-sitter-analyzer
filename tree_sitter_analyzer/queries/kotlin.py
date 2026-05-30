#!/usr/bin/env python3
"""
Kotlin Language Queries

Tree-sitter queries specific to Kotlin language constructs.
Covers classes, functions, properties, interfaces, and other Kotlin-specific elements.
"""

from ._base import make_query_accessors as _make_query_accessors

# Kotlin-specific query library
KOTLIN_QUERIES: dict[str, str] = {
    # --- Basic Structure ---
    "package": """
    (package_header) @package
    """,
    "class": """
    (class_declaration) @class
    """,
    "object": """
    (object_declaration) @object
    """,
    "companion_object": """
    (object_declaration
      (companion_modifier)) @companion_object
    """,
    "interface": """
    (class_declaration
      name: (identifier) @interface_name
      (class_body)) @interface
    """,
    "enum_class": """
    (class_declaration
      (class_modifier "enum")
      name: (identifier) @name) @enum_class
    """,
    "annotation_class": """
    (class_declaration
      (class_modifier "annotation")
      name: (identifier) @name) @annotation_class
    """,
    # --- Functions ---
    "function": """
    (function_declaration) @function
    """,
    "lambda": """
    (lambda_literal) @lambda
    """,
    "constructor": """
    (secondary_constructor) @secondary_constructor

    (class_declaration
      (primary_constructor)) @primary_constructor
    """,
    "extension_function": """
    (function_declaration
      name: (identifier) @name
      (receiver_type) @receiver) @extension_function
    """,
    # --- Properties and Variables ---
    "property": """
    (property_declaration) @property
    """,
    "val": """
    (property_declaration
      "val" (_)) @val
    """,
    "var": """
    (property_declaration
      "var" (_)) @var
    """,
    # --- Annotations ---
    "annotation": """
    (annotation) @annotation
    """,
    # --- Control Flow ---
    "when_expression": """
    (when_expression) @when_expression
    """,
    "try_expression": """
    (try_expression) @try_expression
    """,
    # --- Type Aliases ---
    "type_alias": """
    (type_alias) @type_alias
    """,
    # --- Detailed Queries ---
    "class_with_body": """
    (class_declaration
      name: (identifier) @name
      (class_body) @body) @class_with_body
    """,
    "function_with_body": """
    (function_declaration
      name: (identifier) @name
      (function_body) @body) @function_with_body
    """,
    # --- Modifiers ---
    "data_class": """
    (class_declaration
      (modifiers (class_modifier "data"))
      name: (identifier) @name) @data_class
    """,
    "sealed_class": """
    (class_declaration
      (modifiers (class_modifier "sealed"))
      name: (identifier) @name) @sealed_class
    """,
    "abstract_class": """
    (class_declaration
      (modifiers (class_modifier "abstract"))
      name: (identifier) @name) @abstract_class
    """,
    "open_class": """
    (class_declaration
      (modifiers (class_modifier "open"))
      name: (identifier) @name) @open_class
    """,
    "suspend_function": """
    (function_declaration
      (modifiers (function_modifier "suspend"))
      name: (identifier) @name) @suspend_function
    """,
    "inline_function": """
    (function_declaration
      (modifiers (function_modifier "inline"))
      name: (identifier) @name) @inline_function
    """,
    # --- Names ---
    "class_name": """
    (class_declaration
      name: (identifier) @class_name)
    """,
    "function_name": """
    (function_declaration
      name: (identifier) @function_name)
    """,
}

# Query descriptions
KOTLIN_QUERY_DESCRIPTIONS: dict[str, str] = {
    "package": "Extract Kotlin package header",
    "class": "Extract Kotlin class declarations",
    "object": "Extract Kotlin object declarations",
    "companion_object": "Extract Kotlin companion object declarations",
    "interface": "Extract Kotlin interface declarations",
    "enum_class": "Extract Kotlin enum class declarations",
    "annotation_class": "Extract Kotlin annotation class declarations",
    "function": "Extract Kotlin function declarations",
    "lambda": "Extract Kotlin lambda literals",
    "constructor": "Extract Kotlin primary and secondary constructors",
    "extension_function": "Extract Kotlin extension functions",
    "property": "Extract Kotlin property declarations",
    "val": "Extract Kotlin read-only properties (val)",
    "var": "Extract Kotlin mutable properties (var)",
    "annotation": "Extract Kotlin annotations",
    "when_expression": "Extract Kotlin when expressions",
    "try_expression": "Extract Kotlin try/catch expressions",
    "type_alias": "Extract Kotlin type aliases",
    "class_with_body": "Extract class declarations with body",
    "function_with_body": "Extract function declarations with body",
    "data_class": "Extract data classes",
    "sealed_class": "Extract sealed classes",
    "abstract_class": "Extract abstract class declarations",
    "open_class": "Extract open class declarations",
    "suspend_function": "Extract suspend functions",
    "inline_function": "Extract inline function declarations",
    "class_name": "Extract class names only",
    "function_name": "Extract function names only",
}


def get_kotlin_query(name: str) -> str:
    """
    Get the specified Kotlin query

    Args:
        name: Query name

    Returns:
        Query string

    Raises:
        ValueError: When query is not found
    """
    if name not in KOTLIN_QUERIES:
        available = list(KOTLIN_QUERIES.keys())
        raise ValueError(
            f"Kotlin query '{name}' does not exist. Available: {available}"
        )

    return KOTLIN_QUERIES[name]


def get_kotlin_query_description(name: str) -> str:
    """
    Get the description of the specified Kotlin query

    Args:
        name: Query name

    Returns:
        Query description
    """
    return KOTLIN_QUERY_DESCRIPTIONS.get(name, "No description")


# Convert to ALL_QUERIES format for dynamic loader compatibility
ALL_QUERIES = {}
for query_name, query_string in KOTLIN_QUERIES.items():
    description = KOTLIN_QUERY_DESCRIPTIONS.get(query_name, "No description")
    ALL_QUERIES[query_name] = {"query": query_string, "description": description}

# Add common query aliases for cross-language compatibility
ALL_QUERIES["functions"] = {
    "query": KOTLIN_QUERIES["function"],
    "description": "Search all function declarations (alias for function)",
}

ALL_QUERIES["methods"] = {
    "query": KOTLIN_QUERIES["function"],
    "description": "Search all function declarations (alias for function)",
}

ALL_QUERIES["classes"] = {
    "query": KOTLIN_QUERIES["class"],
    "description": "Search all class declarations (alias for class)",
}

ALL_QUERIES["functions"] = ALL_QUERIES["function"]
ALL_QUERIES["methods"] = ALL_QUERIES["function"]
ALL_QUERIES["variables"] = ALL_QUERIES["var"]
ALL_QUERIES["imports"] = ALL_QUERIES["package"]


get_query, get_all_queries, list_queries = _make_query_accessors(ALL_QUERIES)


def get_available_kotlin_queries() -> list[str]:
    """
    Get list of available Kotlin queries

    Returns:
        List of query names
    """
    return list(KOTLIN_QUERIES.keys())
