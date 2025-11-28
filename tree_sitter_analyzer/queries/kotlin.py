#!/usr/bin/env python3
"""
Kotlin Language Queries

Tree-sitter queries specific to Kotlin language constructs.
Covers classes, functions, properties, interfaces, and other Kotlin-specific elements.
"""

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
    "interface": """
    (class_declaration
      (#match? @class "interface")) @interface
    """,
    # --- Functions ---
    "function": """
    (function_declaration) @function
    """,
    "lambda": """
    (lambda_literal) @lambda
    """,
    # --- Properties and Variables ---
    "property": """
    (property_declaration) @property
    """,
    "val": """
    (property_declaration
      (#match? @property "^val")) @val
    """,
    "var": """
    (property_declaration
      (#match? @property "^var")) @var
    """,
    # --- Annotations ---
    "annotation": """
    (annotation) @annotation
    """,
    # --- Detailed Queries ---
    "class_with_body": """
    (class_declaration
      (simple_identifier) @name
      (class_body) @body) @class_with_body
    """,
    "function_with_body": """
    (function_declaration
      (simple_identifier) @name
      (function_body) @body) @function_with_body
    """,
    # --- Modifiers ---
    "data_class": """
    (class_declaration
      (modifiers "data")
      (simple_identifier) @name) @data_class
    """,
    "sealed_class": """
    (class_declaration
      (modifiers "sealed")
      (simple_identifier) @name) @sealed_class
    """,
    "suspend_function": """
    (function_declaration
      (modifiers "suspend")
      (simple_identifier) @name) @suspend_function
    """,
    # --- Names ---
    "class_name": """
    (class_declaration
      (simple_identifier) @class_name)
    """,
    "function_name": """
    (function_declaration
      (simple_identifier) @function_name)
    """,
}

# Query descriptions
KOTLIN_QUERY_DESCRIPTIONS: dict[str, str] = {
    "package": "Extract Kotlin package header",
    "class": "Extract Kotlin class declarations",
    "object": "Extract Kotlin object declarations",
    "interface": "Extract Kotlin interface declarations",
    "function": "Extract Kotlin function declarations",
    "lambda": "Extract Kotlin lambda literals",
    "property": "Extract Kotlin property declarations",
    "val": "Extract Kotlin read-only properties (val)",
    "var": "Extract Kotlin mutable properties (var)",
    "annotation": "Extract Kotlin annotations",
    "class_with_body": "Extract class declarations with body",
    "function_with_body": "Extract function declarations with body",
    "data_class": "Extract data classes",
    "sealed_class": "Extract sealed classes",
    "suspend_function": "Extract suspend functions",
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


def get_available_kotlin_queries() -> list[str]:
    """
    Get list of available Kotlin queries

    Returns:
        List of query names
    """
    return list(KOTLIN_QUERIES.keys())
