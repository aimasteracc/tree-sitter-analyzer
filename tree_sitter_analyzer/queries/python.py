#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python Tree-sitter queries for code analysis.
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

# All queries combined
ALL_QUERIES = {
    "functions": {
        "query": FUNCTIONS,
        "description": "すべての関数定義（async含む）を検索",
    },
    "classes": {"query": CLASSES, "description": "すべてのクラス定義を検索"},
    "imports": {"query": IMPORTS, "description": "すべてのインポート文を検索"},
    "variables": {"query": VARIABLES, "description": "すべての変数代入を検索"},
    "decorators": {"query": DECORATORS, "description": "すべてのデコレータを検索"},
    "methods": {
        "query": METHODS,
        "description": "クラス内のすべてのメソッド定義を検索",
    },
    "exceptions": {
        "query": EXCEPTIONS,
        "description": "例外処理とraise文を検索",
    },
    "comprehensions": {
        "query": COMPREHENSIONS,
        "description": "リスト、辞書、セット内包表記を検索",
    },
    "comments": {"query": COMMENTS, "description": "コメントとdocstringを検索"},
    "type_hints": {
        "query": TYPE_HINTS,
        "description": "型ヒントとアノテーションを検索",
    },
    "async_patterns": {
        "query": ASYNC_PATTERNS,
        "description": "async/awaitパターンを検索",
    },
    "string_formatting": {
        "query": STRING_FORMATTING,
        "description": "f文字列と文字列フォーマットを検索",
    },
    "context_managers": {
        "query": CONTEXT_MANAGERS,
        "description": "コンテキストマネージャー（with文）を検索",
    },
    "lambdas": {"query": LAMBDAS, "description": "ラムダ式を検索"},
    "modern_patterns": {
        "query": MODERN_PATTERNS,
        "description": "モダンなPythonパターン（match/case、セイウチ演算子）を検索",
    },
    # Convenience aliases
    "function_names": {
        "query": FUNCTIONS,
        "description": "関数のエイリアス - すべての関数定義を検索",
    },
    "class_names": {
        "query": CLASSES,
        "description": "クラスのエイリアス - すべてのクラス定義を検索",
    },
    "all_declarations": {
        "query": FUNCTIONS + "\n\n" + CLASSES + "\n\n" + VARIABLES,
        "description": "すべての関数、クラス、変数宣言を検索",
    },
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
