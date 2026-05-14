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

# Query for Ruby methods
RUBY_METHOD_QUERY = """
(method
  name: (identifier) @method.name
  parameters: (method_parameters)? @method.parameters) @method.definition

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
    "method": {
        "query": RUBY_METHOD_QUERY,
        "description": "Extract Ruby methods and singleton methods",
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
