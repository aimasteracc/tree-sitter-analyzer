"""
Ruby Tree-sitter Queries

Defines tree-sitter queries for efficient Ruby element extraction.
"""

# Query for Ruby classes and modules
RUBY_CLASS_QUERY = """
(class
  name: (constant) @class.name) @class.definition

(module
  name: (constant) @module.name) @module.definition
"""

# Query for Ruby modules only
RUBY_MODULE_QUERY = """
(module
  name: (constant) @module.name) @module.definition
"""

# Query for Ruby methods
RUBY_METHOD_QUERY = """
(method
  name: (identifier) @method.name
  parameters: (method_parameters)? @method.parameters) @method.definition

(singleton_method
  name: (identifier) @singleton.method.name
  parameters: (method_parameters)? @singleton.method.parameters) @singleton.method.definition
"""

# Query for Ruby singleton methods only
RUBY_SINGLETON_METHOD_QUERY = """
(singleton_method
  name: (identifier) @singleton.method.name
  parameters: (method_parameters)? @singleton.method.parameters) @singleton.method.definition
"""

# Query for Ruby constants
RUBY_CONSTANT_QUERY = """
(assignment
  left: (constant) @constant.name) @constant.definition
"""

# Query for Ruby instance variables
RUBY_INSTANCE_VAR_QUERY = """
(assignment
  left: (instance_variable) @instance.var.name) @instance.var.definition
"""

# Query for Ruby class variables
RUBY_CLASS_VAR_QUERY = """
(assignment
  left: (class_variable) @class.var.name) @class.var.definition
"""

# Query for Ruby require statements
RUBY_REQUIRE_QUERY = """
(call
  method: (identifier) @require.method
  (#match? @require.method "^(require|require_relative|load)$")
  arguments: (argument_list
    (string) @require.module)) @require.definition
"""

# Query for Ruby include/extend/prepend
RUBY_MIXIN_QUERY = """
(call
  method: (identifier) @mixin.method
  (#match? @mixin.method "^(include|extend|prepend)$")
  arguments: (argument_list
    (constant) @mixin.name)) @mixin.definition
"""

# Query for Ruby attr_accessor, attr_reader, attr_writer
RUBY_ATTR_QUERY = """
(call
  method: (identifier) @attr.method
  (#match? @attr.method "^(attr_accessor|attr_reader|attr_writer)$")
  arguments: (argument_list
    (simple_symbol) @attr.name)) @attr.definition
"""

# Query for Ruby blocks
RUBY_BLOCK_QUERY = """
(block) @block.definition

(do_block) @do.block.definition
"""

# Query for Ruby procs and lambdas
RUBY_PROC_LAMBDA_QUERY = """
(call
  method: (identifier) @proc.method
  (#match? @proc.method "^(lambda|proc)$")) @proc.definition
"""

# Query for Ruby begin/rescue exception handling
RUBY_RESCUE_QUERY = """
(begin
  (rescue
    (rescue_clause
      (constant) @exception.type)? @exception.handler) @rescue.block) @begin.block
"""

# Query for Ruby alias
RUBY_ALIAS_QUERY = """
(alias
  (symbol) @alias.new_name
  (symbol) @alias.old_name) @alias.definition

(alias_method
  arguments: (argument_list
    (symbol) @alias.new_name
    (symbol) @alias.old_name)) @alias_method.definition
"""

# Query for Ruby yield statements
RUBY_YIELD_QUERY = """
(yield) @yield.statement
"""

# Query for Ruby if/unless modifiers and conditionals
RUBY_CONDITIONAL_QUERY = """
(if
  condition: (_) @if.condition) @if.definition

(unless
  condition: (_) @unless.condition) @unless.definition
"""

# Query for Ruby class with inheritance
RUBY_INHERITANCE_QUERY = """
(class
  name: (constant) @class.name
  superclass: (constant) @class.superclass) @class.with_inheritance
"""

# Query for Ruby global variables
RUBY_GLOBAL_VAR_QUERY = """
(global_variable) @global.var.reference
"""

# Query for Ruby heredoc strings
RUBY_HEREDOC_QUERY = """
(heredoc_string) @heredoc.definition
"""

# Combined query for all Ruby elements
RUBY_ALL_ELEMENTS_QUERY = f"""
{RUBY_CLASS_QUERY}

{RUBY_METHOD_QUERY}

{RUBY_CONSTANT_QUERY}

{RUBY_INSTANCE_VAR_QUERY}

{RUBY_CLASS_VAR_QUERY}

{RUBY_REQUIRE_QUERY}

{RUBY_ATTR_QUERY}
"""

# Structured query registry for dynamic loader compatibility
ALL_QUERIES = {
    "class": {
        "query": RUBY_CLASS_QUERY,
        "description": "Extract Ruby classes and modules",
    },
    "module": {
        "query": RUBY_MODULE_QUERY,
        "description": "Extract Ruby module declarations",
    },
    "method": {
        "query": RUBY_METHOD_QUERY,
        "description": "Extract Ruby methods and singleton methods",
    },
    "singleton_method": {
        "query": RUBY_SINGLETON_METHOD_QUERY,
        "description": "Extract Ruby singleton (class) methods",
    },
    "constant": {
        "query": RUBY_CONSTANT_QUERY,
        "description": "Extract Ruby constant assignments",
    },
    "instance_variable": {
        "query": RUBY_INSTANCE_VAR_QUERY,
        "description": "Extract Ruby instance variable assignments",
    },
    "class_variable": {
        "query": RUBY_CLASS_VAR_QUERY,
        "description": "Extract Ruby class variable assignments",
    },
    "require": {
        "query": RUBY_REQUIRE_QUERY,
        "description": "Extract Ruby require/load statements",
    },
    "mixin": {
        "query": RUBY_MIXIN_QUERY,
        "description": "Extract Ruby include/extend/prepend calls",
    },
    "attr": {
        "query": RUBY_ATTR_QUERY,
        "description": "Extract Ruby attr_accessor/attr_reader/attr_writer",
    },
    "block": {
        "query": RUBY_BLOCK_QUERY,
        "description": "Extract Ruby blocks (block and do_block)",
    },
    "proc_lambda": {
        "query": RUBY_PROC_LAMBDA_QUERY,
        "description": "Extract Ruby proc and lambda calls",
    },
    "rescue": {
        "query": RUBY_RESCUE_QUERY,
        "description": "Extract Ruby begin/rescue exception handling",
    },
    "alias": {
        "query": RUBY_ALIAS_QUERY,
        "description": "Extract Ruby alias and alias_method",
    },
    "yield": {
        "query": RUBY_YIELD_QUERY,
        "description": "Extract Ruby yield statements",
    },
    "conditional": {
        "query": RUBY_CONDITIONAL_QUERY,
        "description": "Extract Ruby if/unless conditionals",
    },
    "inheritance": {
        "query": RUBY_INHERITANCE_QUERY,
        "description": "Extract Ruby classes with inheritance (superclass)",
    },
    "global_variable": {
        "query": RUBY_GLOBAL_VAR_QUERY,
        "description": "Extract Ruby global variable references",
    },
    "heredoc": {
        "query": RUBY_HEREDOC_QUERY,
        "description": "Extract Ruby heredoc strings",
    },
}

# Cross-language aliases
ALL_QUERIES["classes"] = ALL_QUERIES["class"]
ALL_QUERIES["functions"] = ALL_QUERIES["method"]
ALL_QUERIES["methods"] = ALL_QUERIES["method"]
ALL_QUERIES["imports"] = ALL_QUERIES["require"]
ALL_QUERIES["variables"] = ALL_QUERIES["instance_variable"]


def get_all_queries() -> dict:
    return ALL_QUERIES


def get_query(name: str) -> str:
    if name in ALL_QUERIES:
        q = ALL_QUERIES[name]
        return q["query"] if isinstance(q, dict) else q
    raise ValueError(f"Query '{name}' not found. Available: {list(ALL_QUERIES.keys())}")


def list_queries() -> list:
    return list(ALL_QUERIES.keys())
