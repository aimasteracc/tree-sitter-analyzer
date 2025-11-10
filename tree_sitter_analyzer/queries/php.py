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
    name: (name) @constant.name)) @constant.definition
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
      name: (name) @attribute.name))) @attribute.definition
"""

# Query for PHP magic methods
PHP_MAGIC_METHOD_QUERY = """
(method_declaration
  name: (name) @magic.method.name
  (#match? @magic.method.name "^__")) @magic.method.definition
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
