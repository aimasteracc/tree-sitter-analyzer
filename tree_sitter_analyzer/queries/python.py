#!/usr/bin/env python3
"""
Python Language Queries

Comprehensive Tree-sitter queries for Python language constructs.
Covers functions, classes, variables, imports, decorators, async/await,
type hints, and modern Python features.
Equivalent to JavaScript query coverage for consistent language support.
"""

# Function definitions
FUNCTIONS = """
(function_definition
    name: (identifier) @function.name
    parameters: (parameters) @function.params
    body: (block) @function.body) @function.definition

(function_definition
    name: (identifier) @function.name
    parameters: (parameters) @function.params
    body: (block) @function.body) @function.async
"""

# Class definitions
CLASSES = """
(class_definition
    name: (identifier) @class.name
    superclasses: (argument_list)? @class.superclasses
    body: (block) @class.body) @class.definition
"""

# Import statements
IMPORTS = """
(import_statement
    name: (dotted_name) @import.name) @import.statement

(import_from_statement
    module_name: (dotted_name)? @import.module
    name: (dotted_name) @import.name) @import.from

(import_from_statement
    module_name: (dotted_name)? @import.module
    name: (import_list) @import.list) @import.from_list

(aliased_import
    name: (dotted_name) @import.name
    alias: (identifier) @import.alias) @import.aliased
"""

# Variable assignments
VARIABLES = """
(assignment
    left: (identifier) @variable.name
    right: (_) @variable.value) @variable.assignment

(assignment
    left: (pattern_list) @variable.pattern
    right: (_) @variable.value) @variable.multiple

(augmented_assignment
    left: (identifier) @variable.name
    right: (_) @variable.value) @variable.augmented
"""

# Decorators
DECORATORS = """
(decorator
    (identifier) @decorator.name) @decorator.simple

(decorator
    (call
        function: (identifier) @decorator.name
        arguments: (argument_list) @decorator.args)) @decorator.call

(decorator
    (attribute
        object: (identifier) @decorator.object
        attribute: (identifier) @decorator.name)) @decorator.attribute
"""

# Method definitions
METHODS = """
(function_definition
    name: (identifier) @method.name
    parameters: (parameters
        (identifier) @method.self
        . (_)*) @method.params
    body: (block) @method.body) @method.definition
"""

# Exception handling
EXCEPTIONS = """
(try_statement
    body: (block) @try.body
    (except_clause
        type: (_)? @except.type
        name: (identifier)? @except.name
        body: (block) @except.body)*
    (else_clause
        body: (block) @else.body)?
    (finally_clause
        body: (block) @finally.body)?) @try.statement

(raise_statement
    (call
        function: (identifier) @exception.name
        arguments: (argument_list)? @exception.args)) @raise.statement
"""

# Comprehensions
COMPREHENSIONS = """
(list_comprehension
    body: (_) @comprehension.body
    (for_in_clause
        left: (_) @comprehension.var
        right: (_) @comprehension.iter)) @list.comprehension

(dictionary_comprehension
    body: (pair
        key: (_) @comprehension.key
        value: (_) @comprehension.value)
    (for_in_clause
        left: (_) @comprehension.var
        right: (_) @comprehension.iter)) @dict.comprehension

(set_comprehension
    body: (_) @comprehension.body
    (for_in_clause
        left: (_) @comprehension.var
        right: (_) @comprehension.iter)) @set.comprehension
"""

# Comments and docstrings
COMMENTS = """
(comment) @comment

(expression_statement
    (string) @docstring)
"""

# Type hints and annotations
TYPE_HINTS = """
(function_definition
    parameters: (parameters
        (typed_parameter
            type: (_) @type.param)) @type.function_param)

(function_definition
    return_type: (_) @type.return) @type.function_return

(assignment
    type: (_) @type.variable) @type.variable_annotation
"""

# Async/await patterns
ASYNC_PATTERNS = """
(function_definition) @async.function

(await
    (call) @async.await_call) @async.await

(async_for_statement) @async.for

(async_with_statement) @async.with
"""

# F-strings and string formatting
STRING_FORMATTING = """
(formatted_string
    (interpolation) @string.interpolation) @string.fstring

(call
    function: (attribute
        object: (_)
        attribute: (identifier) @string.format_method))
"""

# Context managers
CONTEXT_MANAGERS = """
(with_statement
    (with_clause
        (with_item
            value: (_) @context.manager)) @context.clause) @context.with

(async_with_statement
    (with_clause
        (with_item
            value: (_) @context.manager)) @context.clause) @context.async_with
"""

# Lambda expressions
LAMBDAS = """
(lambda
    parameters: (lambda_parameters)? @lambda.params
    body: (_) @lambda.body) @lambda.expression
"""

# Modern Python patterns
MODERN_PATTERNS = """
(match_statement
    subject: (_) @match.subject
    body: (case_clause)+ @match.cases) @pattern.match

(case_clause
    pattern: (_) @case.pattern
    guard: (_)? @case.guard
    consequence: (block) @case.body) @pattern.case

(walrus_operator
    left: (_) @walrus.target
    right: (_) @walrus.value) @assignment.walrus
"""

# Python-specific comprehensive query library
PYTHON_QUERIES: dict[str, str] = {
    # --- Basic Structure ---
    "function": """
    (function_definition) @function
    """,
    "function_definition": """
    (function_definition
        name: (identifier) @function_name
        parameters: (parameters) @parameters
        body: (block) @body) @function_definition
    """,
    "async_function": """
    (function_definition
        "async" @async_keyword
        name: (identifier) @function_name
        parameters: (parameters) @parameters
        body: (block) @body) @async_function
    """,
    "method": """
    (function_definition
        name: (identifier) @method_name
        parameters: (parameters
            (identifier) @self_param
            . (_)*) @method_params
        body: (block) @method_body) @method_definition
    """,
    "lambda": """
    (lambda
        parameters: (lambda_parameters)? @lambda_params
        body: (_) @lambda_body) @lambda_expression
    """,
    # --- Classes ---
    "class": """
    (class_definition) @class
    """,
    "class_definition": """
    (class_definition
        name: (identifier) @class_name
        superclasses: (argument_list)? @superclasses
        body: (block) @body) @class_definition
    """,
    "class_method": """
    (class_definition
        body: (block
            (function_definition
                name: (identifier) @method_name
                parameters: (parameters) @parameters
                body: (block) @method_body))) @class_method
    """,
    "constructor": """
    (function_definition
        name: (identifier) @constructor_name
        (#match? @constructor_name "__init__")
        parameters: (parameters) @parameters
        body: (block) @body) @constructor
    """,
    "property": """
    (decorated_definition
        (decorator
            (identifier) @decorator_name
            (#match? @decorator_name "property"))
        (function_definition
            name: (identifier) @property_name)) @property_definition
    """,
    "staticmethod": """
    (decorated_definition
        (decorator
            (identifier) @decorator_name
            (#match? @decorator_name "staticmethod"))
        (function_definition
            name: (identifier) @method_name)) @static_method
    """,
    "classmethod": """
    (decorated_definition
        (decorator
            (identifier) @decorator_name
            (#match? @decorator_name "classmethod"))
        (function_definition
            name: (identifier) @method_name)) @class_method_decorator
    """,
    # --- Variables and Assignments ---
    "variable": """
    (assignment) @variable
    """,
    "assignment": """
    (assignment
        left: (identifier) @variable_name
        right: (_) @value) @assignment
    """,
    "multiple_assignment": """
    (assignment
        left: (pattern_list) @variables
        right: (_) @value) @multiple_assignment
    """,
    "augmented_assignment": """
    (augmented_assignment
        left: (identifier) @variable_name
        right: (_) @value) @augmented_assignment
    """,
    "global_statement": """
    (global_statement
        (identifier) @global_var) @global_declaration
    """,
    "nonlocal_statement": """
    (nonlocal_statement
        (identifier) @nonlocal_var) @nonlocal_declaration
    """,
    # --- Imports ---
    "import": """
    (import_statement) @import
    """,
    "import_statement": """
    (import_statement
        name: (dotted_name) @import_name) @import_statement
    """,
    "import_from": """
    (import_from_statement
        module_name: (dotted_name)? @module_name
        name: (dotted_name) @import_name) @import_from
    """,
    "import_from_list": """
    (import_from_statement
        module_name: (dotted_name)? @module_name
        name: (import_list) @import_list) @import_from_list
    """,
    "aliased_import": """
    (aliased_import
        name: (dotted_name) @import_name
        alias: (identifier) @alias) @aliased_import
    """,
    "import_star": """
    (import_from_statement
        module_name: (dotted_name) @module_name
        name: (wildcard_import) @star_import) @import_star
    """,
    # --- Decorators ---
    "decorator": """
    (decorator) @decorator
    """,
    "decorator_simple": """
    (decorator
        (identifier) @decorator_name) @decorator_simple
    """,
    "decorator_call": """
    (decorator
        (call
            function: (identifier) @decorator_name
            arguments: (argument_list) @decorator_args)) @decorator_call
    """,
    "decorator_attribute": """
    (decorator
        (attribute
            object: (identifier) @decorator_object
            attribute: (identifier) @decorator_name)) @decorator_attribute
    """,
    "decorated_function": """
    (decorated_definition
        (decorator)+ @decorators
        (function_definition
            name: (identifier) @function_name)) @decorated_function
    """,
    "decorated_class": """
    (decorated_definition
        (decorator)+ @decorators
        (class_definition
            name: (identifier) @class_name)) @decorated_class
    """,
    # --- Control Flow ---
    "if_statement": """
    (if_statement
        condition: (_) @condition
        consequence: (block) @then_branch
        alternative: (_)? @else_branch) @if_statement
    """,
    "for_statement": """
    (for_statement
        left: (_) @loop_var
        right: (_) @iterable
        body: (block) @body) @for_statement
    """,
    "while_statement": """
    (while_statement
        condition: (_) @condition
        body: (block) @body) @while_statement
    """,
    "with_statement": """
    (with_statement
        (with_clause
            (with_item
                value: (_) @context_manager)) @with_clause
        body: (block) @body) @with_statement
    """,
    "async_with": """
    (async_with_statement
        (with_clause
            (with_item
                value: (_) @context_manager)) @with_clause
        body: (block) @body) @async_with_statement
    """,
    "async_for": """
    (async_for_statement
        left: (_) @loop_var
        right: (_) @async_iterable
        body: (block) @body) @async_for_statement
    """,
    # --- Exception Handling ---
    "try_statement": """
    (try_statement
        body: (block) @try_body
        (except_clause)* @except_clauses
        (else_clause)? @else_clause
        (finally_clause)? @finally_clause) @try_statement
    """,
    "except_clause": """
    (except_clause
        type: (_)? @exception_type
        name: (identifier)? @exception_name
        body: (block) @except_body) @except_clause
    """,
    "raise_statement": """
    (raise_statement
        (call
            function: (identifier) @exception_name
            arguments: (argument_list)? @exception_args)) @raise_statement
    """,
    "assert_statement": """
    (assert_statement
        (_) @assertion
        (_)? @message) @assert_statement
    """,
    # --- Comprehensions ---
    "list_comprehension": """
    (list_comprehension
        body: (_) @comprehension_body
        (for_in_clause
            left: (_) @comprehension_var
            right: (_) @comprehension_iter)) @list_comprehension
    """,
    "dict_comprehension": """
    (dictionary_comprehension
        body: (pair
            key: (_) @comprehension_key
            value: (_) @comprehension_value)
        (for_in_clause
            left: (_) @comprehension_var
            right: (_) @comprehension_iter)) @dict_comprehension
    """,
    "set_comprehension": """
    (set_comprehension
        body: (_) @comprehension_body
        (for_in_clause
            left: (_) @comprehension_var
            right: (_) @comprehension_iter)) @set_comprehension
    """,
    "generator_expression": """
    (generator_expression
        body: (_) @generator_body
        (for_in_clause
            left: (_) @generator_var
            right: (_) @generator_iter)) @generator_expression
    """,
    # --- Type Hints and Annotations ---
    "type_hint": """
    (typed_parameter
        type: (_) @parameter_type) @typed_parameter
    """,
    "return_type": """
    (function_definition
        return_type: (_) @return_type) @function_with_return_type
    """,
    "variable_annotation": """
    (assignment
        type: (_) @variable_type) @annotated_assignment
    """,
    "type_alias": """
    (type_alias_statement
        name: (identifier) @alias_name
        value: (_) @alias_type) @type_alias
    """,
    # --- Modern Python Features ---
    "match_statement": """
    (match_statement
        subject: (_) @match_subject
        body: (case_clause)+ @match_cases) @match_statement
    """,
    "case_clause": """
    (case_clause
        pattern: (_) @case_pattern
        guard: (_)? @case_guard
        consequence: (block) @case_body) @case_clause
    """,
    "walrus_operator": """
    (named_expression
        name: (identifier) @walrus_target
        value: (_) @walrus_value) @walrus_operator
    """,
    "f_string": """
    (formatted_string
        (interpolation) @f_string_interpolation) @f_string
    """,
    "yield_expression": """
    (yield
        (_)? @yielded_value) @yield_expression
    """,
    "yield_from": """
    (yield
        "from" @yield_from_keyword
        (_) @yielded_iterable) @yield_from_expression
    """,
    "await_expression": """
    (await
        (_) @awaited_expression) @await_expression
    """,
    # --- Comments and Docstrings ---
    "comment": """
    (comment) @comment
    """,
    "docstring": """
    (expression_statement
        (string) @docstring)
    """,
    "module_docstring": """
    (module
        (expression_statement
            (string) @module_docstring))
    """,
    # --- Framework-specific Patterns ---
    "django_model": """
    (class_definition
        name: (identifier) @model_name
        superclasses: (argument_list
            (identifier) @superclass
            (#match? @superclass "Model|models.Model"))
        body: (block) @model_body) @django_model
    """,
    "django_view": """
    (class_definition
        name: (identifier) @view_name
        superclasses: (argument_list
            (identifier) @superclass
            (#match? @superclass "View|TemplateView|ListView|DetailView"))
        body: (block) @view_body) @django_view
    """,
    "flask_route": """
    (decorated_definition
        (decorator
            (call
                function: (attribute
                    object: (identifier) @app_object
                    attribute: (identifier) @route_decorator
                    (#match? @route_decorator "route"))
                arguments: (argument_list
                    (string) @route_path))) @flask_route_decorator
        (function_definition
            name: (identifier) @handler_name)) @flask_route
    """,
    "fastapi_endpoint": """
    (decorated_definition
        (decorator
            (call
                function: (attribute
                    object: (identifier) @app_object
                    attribute: (identifier) @http_method
                    (#match? @http_method "get|post|put|delete|patch"))
                arguments: (argument_list
                    (string) @endpoint_path))) @fastapi_decorator
        (function_definition
            name: (identifier) @endpoint_name)) @fastapi_endpoint
    """,
    "dataclass": """
    (decorated_definition
        (decorator
            (identifier) @decorator_name
            (#match? @decorator_name "dataclass"))
        (class_definition
            name: (identifier) @dataclass_name)) @dataclass_definition
    """,
    # --- Name-only Extraction ---
    "function_name": """
    (function_definition
        name: (identifier) @function_name)
    """,
    "class_name": """
    (class_definition
        name: (identifier) @class_name)
    """,
    "variable_name": """
    (assignment
        left: (identifier) @variable_name)
    """,
    # --- Advanced Patterns ---
    "context_manager": """
    (class_definition
        body: (block
            (function_definition
                name: (identifier) @enter_method
                (#match? @enter_method "__enter__"))
            (function_definition
                name: (identifier) @exit_method
                (#match? @exit_method "__exit__")))) @context_manager_class
    """,
    "iterator": """
    (class_definition
        body: (block
            (function_definition
                name: (identifier) @iter_method
                (#match? @iter_method "__iter__"))
            (function_definition
                name: (identifier) @next_method
                (#match? @next_method "__next__")))) @iterator_class
    """,
    "metaclass": """
    (class_definition
        name: (identifier) @metaclass_name
        superclasses: (argument_list
            (identifier) @superclass
            (#match? @superclass "type"))
        body: (block) @metaclass_body) @metaclass_definition
    """,
    "abstract_method": """
    (decorated_definition
        (decorator
            (identifier) @decorator_name
            (#match? @decorator_name "abstractmethod"))
        (function_definition
            name: (identifier) @abstract_method_name)) @abstract_method
    """,
}

# Query descriptions
PYTHON_QUERY_DESCRIPTIONS: dict[str, str] = {
    "function": "Search Python function definitions",
    "function_definition": "Search function definitions with details",
    "async_function": "Search async function definitions",
    "method": "Search method definitions within classes",
    "lambda": "Search lambda expressions",
    "class": "Search Python class definitions",
    "class_definition": "Search class definitions with details",
    "class_method": "Search class methods",
    "constructor": "Search class constructors (__init__)",
    "property": "Search property decorators",
    "staticmethod": "Search static methods",
    "classmethod": "Search class methods",
    "variable": "Search variable assignments",
    "assignment": "Search variable assignments",
    "multiple_assignment": "Search multiple variable assignments",
    "augmented_assignment": "Search augmented assignments (+=, -=, etc.)",
    "global_statement": "Search global variable declarations",
    "nonlocal_statement": "Search nonlocal variable declarations",
    "import": "Search import statements",
    "import_statement": "Search import statements with details",
    "import_from": "Search from-import statements",
    "import_from_list": "Search from-import with multiple names",
    "aliased_import": "Search aliased imports (as keyword)",
    "import_star": "Search star imports (from module import *)",
    "decorator": "Search all decorators",
    "decorator_simple": "Search simple decorators",
    "decorator_call": "Search decorator calls with arguments",
    "decorator_attribute": "Search attribute decorators",
    "decorated_function": "Search decorated functions",
    "decorated_class": "Search decorated classes",
    "if_statement": "Search if statements",
    "for_statement": "Search for loops",
    "while_statement": "Search while loops",
    "with_statement": "Search with statements (context managers)",
    "async_with": "Search async with statements",
    "async_for": "Search async for loops",
    "try_statement": "Search try-except statements",
    "except_clause": "Search except clauses",
    "raise_statement": "Search raise statements",
    "assert_statement": "Search assert statements",
    "list_comprehension": "Search list comprehensions",
    "dict_comprehension": "Search dictionary comprehensions",
    "set_comprehension": "Search set comprehensions",
    "generator_expression": "Search generator expressions",
    "type_hint": "Search type hints on parameters",
    "return_type": "Search function return type annotations",
    "variable_annotation": "Search variable type annotations",
    "type_alias": "Search type alias statements",
    "match_statement": "Search match statements (Python 3.10+)",
    "case_clause": "Search case clauses in match statements",
    "walrus_operator": "Search walrus operator (:=)",
    "f_string": "Search f-string literals",
    "yield_expression": "Search yield expressions",
    "yield_from": "Search yield from expressions",
    "await_expression": "Search await expressions",
    "comment": "Search all comments",
    "docstring": "Search docstrings",
    "module_docstring": "Search module-level docstrings",
    "django_model": "Search Django model classes",
    "django_view": "Search Django view classes",
    "flask_route": "Search Flask route decorators",
    "fastapi_endpoint": "Search FastAPI endpoint decorators",
    "dataclass": "Search dataclass definitions",
    "function_name": "Search function names only",
    "class_name": "Search class names only",
    "variable_name": "Search variable names only",
    "context_manager": "Search context manager classes",
    "iterator": "Search iterator classes",
    "metaclass": "Search metaclass definitions",
    "abstract_method": "Search abstract methods",
}

# Convert to ALL_QUERIES format for dynamic loader compatibility
ALL_QUERIES = {}
for query_name, query_string in PYTHON_QUERIES.items():
    description = PYTHON_QUERY_DESCRIPTIONS.get(query_name, "No description")
    ALL_QUERIES[query_name] = {"query": query_string, "description": description}

# Add legacy queries for backward compatibility
ALL_QUERIES["functions"] = {
    "query": FUNCTIONS,
    "description": "Search all function definitions (including async)",
}
ALL_QUERIES["classes"] = {
    "query": CLASSES,
    "description": "Search all class definitions",
}
ALL_QUERIES["imports"] = {
    "query": IMPORTS,
    "description": "Search all import statements",
}
ALL_QUERIES["variables"] = {
    "query": VARIABLES,
    "description": "Search all variable assignments",
}
ALL_QUERIES["decorators"] = {
    "query": DECORATORS,
    "description": "Search all decorators",
}
ALL_QUERIES["methods"] = {
    "query": METHODS,
    "description": "Search all method definitions within classes",
}
ALL_QUERIES["exceptions"] = {
    "query": EXCEPTIONS,
    "description": "Search exception handling and raise statements",
}
ALL_QUERIES["comprehensions"] = {
    "query": COMPREHENSIONS,
    "description": "Search list, dictionary, and set comprehensions",
}
ALL_QUERIES["comments"] = {
    "query": COMMENTS,
    "description": "Search comments and docstrings",
}
ALL_QUERIES["type_hints"] = {
    "query": TYPE_HINTS,
    "description": "Search type hints and annotations",
}
ALL_QUERIES["async_patterns"] = {
    "query": ASYNC_PATTERNS,
    "description": "Search async/await patterns",
}
ALL_QUERIES["string_formatting"] = {
    "query": STRING_FORMATTING,
    "description": "Search f-strings and string formatting",
}
ALL_QUERIES["context_managers"] = {
    "query": CONTEXT_MANAGERS,
    "description": "Search context managers (with statements)",
}
ALL_QUERIES["lambdas"] = {"query": LAMBDAS, "description": "Search lambda expressions"}
ALL_QUERIES["modern_patterns"] = {
    "query": MODERN_PATTERNS,
    "description": "Search modern Python patterns (match/case, walrus operator)",
}

# Convenience aliases
ALL_QUERIES["function_names"] = {
    "query": FUNCTIONS,
    "description": "Function alias - search all function definitions",
}
ALL_QUERIES["class_names"] = {
    "query": CLASSES,
    "description": "Class alias - search all class definitions",
}
ALL_QUERIES["all_declarations"] = {
    "query": FUNCTIONS + "\n\n" + CLASSES + "\n\n" + VARIABLES,
    "description": "Search all function, class, and variable declarations",
}


def get_python_query(name: str) -> str:
    """
    Get the specified Python query

    Args:
        name: Query name

    Returns:
        Query string

    Raises:
        ValueError: When query is not found
    """
    if name not in PYTHON_QUERIES:
        available = list(PYTHON_QUERIES.keys())
        raise ValueError(
            f"Python query '{name}' does not exist. Available: {available}"
        )

    return PYTHON_QUERIES[name]


def get_python_query_description(name: str) -> str:
    """
    Get the description of the specified Python query

    Args:
        name: Query name

    Returns:
        Query description
    """
    return PYTHON_QUERY_DESCRIPTIONS.get(name, "No description")


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


def get_available_python_queries() -> list[str]:
    """
    Get list of available Python queries

    Returns:
        List of query names
    """
    return list(PYTHON_QUERIES.keys())
