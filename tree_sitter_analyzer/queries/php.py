"""
PHP Tree-sitter Queries

Defines tree-sitter queries for efficient PHP element extraction.
"""

# Query for PHP classes, interfaces, traits, and enums
PHP_CLASS_QUERY = """
(class_declaration
  name: (name) @class.name) @class.definition

(interface_declaration
  name: (name) @interface.name) @interface.definition

(trait_declaration
  name: (name) @trait.name) @trait.definition

(enum_declaration
  name: (name) @enum.name) @enum.definition
"""

# Query for PHP interfaces only
PHP_INTERFACE_QUERY = """
(interface_declaration
  name: (name) @interface.name) @interface.definition
"""

# Query for PHP traits only
PHP_TRAIT_QUERY = """
(trait_declaration
  name: (name) @trait.name) @trait.definition
"""

# Query for PHP enums only
PHP_ENUM_QUERY = """
(enum_declaration
  name: (name) @enum.name) @enum.definition
"""

# Query for PHP abstract classes
PHP_ABSTRACT_CLASS_QUERY = """
(class_declaration
  (abstract_modifier)
  name: (name) @abstract.class.name) @abstract.class.definition
"""

# Query for PHP class with inheritance
PHP_INHERITANCE_QUERY = """
(class_declaration
  name: (name) @class.name
  (base_clause
    (name) @class.parent)) @class.with_inheritance
"""

# Query for PHP methods
PHP_METHOD_QUERY = """
(method_declaration
  name: (name) @method.name
  parameters: (formal_parameters) @method.parameters) @method.definition
"""

# Query for PHP functions
PHP_FUNCTION_QUERY = """
(function_definition
  name: (name) @function.name
  parameters: (formal_parameters) @function.parameters) @function.definition
"""

# Query for PHP anonymous functions (closures)
PHP_CLOSURE_QUERY = """
(closure_expression) @closure.definition

(arrow_function) @arrow_function.definition
"""

# Query for PHP properties
PHP_PROPERTY_QUERY = """
(property_declaration
  (property_element
    (variable_name) @property.name)) @property.definition
"""

# Query for PHP constants
PHP_CONSTANT_QUERY = """
(const_declaration
  (const_element
    (name) @constant.name)) @constant.definition
"""

# Query for PHP use statements
PHP_USE_QUERY = """
(namespace_use_declaration
  (namespace_use_clause
    (qualified_name) @import.name)) @import.definition
"""

# Query for PHP namespaces
PHP_NAMESPACE_QUERY = """
(namespace_definition
  name: (namespace_name) @namespace.name) @namespace.definition
"""

# Query for PHP attributes (PHP 8+)
PHP_ATTRIBUTE_QUERY = """
(attribute_list
  (attribute_group
    (attribute
      (name) @attribute.name))) @attribute.definition
"""

# Query for PHP magic methods
PHP_MAGIC_METHOD_QUERY = """
(method_declaration
  name: (name) @magic.method.name
  (#match? @magic.method.name "^__")) @magic.method.definition
"""

# Query for PHP static methods
PHP_STATIC_METHOD_QUERY = """
(method_declaration
  (static_modifier)
  name: (name) @static.method.name) @static.method.definition
"""

# Query for PHP abstract methods
PHP_ABSTRACT_METHOD_QUERY = """
(method_declaration
  (abstract_modifier)
  name: (name) @abstract.method.name) @abstract.method.definition
"""

# Query for PHP try/catch
PHP_TRY_CATCH_QUERY = """
(try_statement
  (catch_clause
    (name) @exception.type
    (variable_name) @exception.var)?) @try.definition
"""

# Combined query for all PHP elements
PHP_ALL_ELEMENTS_QUERY = f"""
{PHP_CLASS_QUERY}

{PHP_METHOD_QUERY}

{PHP_FUNCTION_QUERY}

{PHP_PROPERTY_QUERY}

{PHP_CONSTANT_QUERY}

{PHP_USE_QUERY}

{PHP_NAMESPACE_QUERY}

{PHP_ATTRIBUTE_QUERY}
"""

# Structured query registry for dynamic loader compatibility
ALL_QUERIES = {
    "class": {
        "query": PHP_CLASS_QUERY,
        "description": "Extract PHP classes, interfaces, traits, and enums",
    },
    "interface": {
        "query": PHP_INTERFACE_QUERY,
        "description": "Extract PHP interface declarations",
    },
    "trait": {
        "query": PHP_TRAIT_QUERY,
        "description": "Extract PHP trait declarations",
    },
    "enum": {
        "query": PHP_ENUM_QUERY,
        "description": "Extract PHP enum declarations",
    },
    "abstract_class": {
        "query": PHP_ABSTRACT_CLASS_QUERY,
        "description": "Extract PHP abstract class declarations",
    },
    "inheritance": {
        "query": PHP_INHERITANCE_QUERY,
        "description": "Extract PHP classes with extends (inheritance)",
    },
    "method": {"query": PHP_METHOD_QUERY, "description": "Extract PHP methods"},
    "function": {"query": PHP_FUNCTION_QUERY, "description": "Extract PHP functions"},
    "closure": {
        "query": PHP_CLOSURE_QUERY,
        "description": "Extract PHP closures and arrow functions",
    },
    "property": {"query": PHP_PROPERTY_QUERY, "description": "Extract PHP properties"},
    "constant": {"query": PHP_CONSTANT_QUERY, "description": "Extract PHP constants"},
    "use": {"query": PHP_USE_QUERY, "description": "Extract PHP use/import statements"},
    "namespace": {
        "query": PHP_NAMESPACE_QUERY,
        "description": "Extract PHP namespace declarations",
    },
    "attribute": {
        "query": PHP_ATTRIBUTE_QUERY,
        "description": "Extract PHP 8+ attributes",
    },
    "magic_method": {
        "query": PHP_MAGIC_METHOD_QUERY,
        "description": "Extract PHP magic methods (__construct, etc.)",
    },
    "static_method": {
        "query": PHP_STATIC_METHOD_QUERY,
        "description": "Extract PHP static methods",
    },
    "abstract_method": {
        "query": PHP_ABSTRACT_METHOD_QUERY,
        "description": "Extract PHP abstract methods",
    },
    "try_catch": {
        "query": PHP_TRY_CATCH_QUERY,
        "description": "Extract PHP try/catch exception handling",
    },
}

# Cross-language aliases
ALL_QUERIES["classes"] = ALL_QUERIES["class"]
ALL_QUERIES["functions"] = ALL_QUERIES["function"]
ALL_QUERIES["methods"] = ALL_QUERIES["method"]
ALL_QUERIES["imports"] = ALL_QUERIES["use"]
ALL_QUERIES["variables"] = ALL_QUERIES["property"]


def get_all_queries() -> dict:
    return ALL_QUERIES


def get_query(name: str) -> str:
    if name in ALL_QUERIES:
        q = ALL_QUERIES[name]
        return q["query"] if isinstance(q, dict) else q
    raise ValueError(f"Query '{name}' not found. Available: {list(ALL_QUERIES.keys())}")


def list_queries() -> list:
    return list(ALL_QUERIES.keys())
