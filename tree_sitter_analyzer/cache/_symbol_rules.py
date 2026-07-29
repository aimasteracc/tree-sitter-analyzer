"""Declarative node-type rules for cache symbol extraction."""

from __future__ import annotations

import re

_FUNCTION_LIKE = frozenset(
    {
        "function_definition",
        "function_declaration",
        "method_definition",
        "arrow_function",
        "generator_function_declaration",
        "function_item",
        "method_declaration",
        "constructor_declaration",
        "lambda_expression",
        "anonymous_function",
        "class_method",
        "member_function",
        "function_declarator",
        "declaration",
        "init_declarator",
        "method",
        "singleton_method",
    }
)

_ENUM_LIKE = frozenset({"enum_declaration", "enum", "enum_specifier"})

_CLASS_LIKE = frozenset(
    {
        "class_definition",
        "class_declaration",
        "class",
        "interface_declaration",
        "struct_item",
        "trait_declaration",
        "impl_item",
        "struct_declaration",
        "type_declaration",
        "struct_specifier",
        "class_specifier",
        "type_spec",
        "annotation_type_declaration",
        "companion_object",
        "module",
        "trait_item",
        "abstract_class_declaration",
    }
    | _ENUM_LIKE
)

_SCALA_CLASS_LIKE = frozenset(
    {
        "object_definition",
        "trait_definition",
        "enum_definition",
        "given_definition",
        "type_definition",
    }
)

_IMPORT_LIKE = frozenset(
    {
        "import_statement",
        "import_from_statement",
        "import_declaration",
        "require_statement",
        "use_declaration",
        "extern_crate_item",
        "package_declaration",
        "include_directive",
    }
)

_VAR_DECL_LIKE = frozenset(
    {
        "variable_declarator",
        "assignment_expression",
        "lexical_declaration",
        "variable_declaration",
        "const_declaration",
        "let_declaration",
        "variable_assignment",
    }
)

_CONST_STYLE_NAME = re.compile(r"^_?[A-Z][A-Z0-9_]+$")
_PY_CONST_STYLE_NAME = re.compile(r"^_?[A-Z][A-Z0-9_]*$")
_PY_DUNDER_NAME = re.compile(r"^__\w+__$")

_PY_SCOPE_BODY_NODES = frozenset({"function_definition", "class_definition"})
_GO_CONST_LIKE = frozenset({"const_declaration", "var_declaration"})
_GO_SCOPE_BODY_NODES = frozenset(
    {"function_declaration", "method_declaration", "func_literal"}
)
_RUST_CONST_LIKE = frozenset({"const_item", "static_item"})
_RUST_SCOPE_BODY_NODES = frozenset({"function_item", "closure_expression", "block"})
_PHP_SCOPE_BODY_NODES = frozenset(
    {
        "function_definition",
        "method_declaration",
        "anonymous_function",
        "arrow_function",
    }
)
_JSTS_SCOPE_BODY_NODES = frozenset(
    {
        "function_declaration",
        "function_expression",
        "function",
        "arrow_function",
        "method_definition",
        "generator_function",
        "generator_function_declaration",
        "class_static_block",
        "ERROR",
    }
)
_JAVA_SCOPE_BODY_NODES = frozenset(
    {
        "method_declaration",
        "constructor_declaration",
        "compact_constructor_declaration",
        "lambda_expression",
        "static_initializer",
        "block",
        "ERROR",
    }
)
_CSHARP_SCOPE_BODY_NODES = frozenset(
    {
        "method_declaration",
        "constructor_declaration",
        "destructor_declaration",
        "operator_declaration",
        "conversion_operator_declaration",
        "local_function_statement",
        "accessor_declaration",
        "lambda_expression",
        "anonymous_method_expression",
        "ERROR",
    }
)
_SCALA_SCOPE_BODY_NODES = frozenset({"function_definition", "function_declaration"})

_SCOPE_BODY_NODES: dict[str, frozenset[str]] = {
    "python": _PY_SCOPE_BODY_NODES,
    "go": _GO_SCOPE_BODY_NODES,
    "rust": _RUST_SCOPE_BODY_NODES,
    "php": _PHP_SCOPE_BODY_NODES,
    "javascript": _JSTS_SCOPE_BODY_NODES,
    "typescript": _JSTS_SCOPE_BODY_NODES,
    "java": _JAVA_SCOPE_BODY_NODES,
    "csharp": _CSHARP_SCOPE_BODY_NODES,
    "scala": _SCALA_SCOPE_BODY_NODES,
}

_COMPLEXITY_NODE_TYPES: dict[str, set[str]] = {
    "python": {
        "if_statement",
        "elif_clause",
        "for_statement",
        "while_statement",
        "except_clause",
        "boolean_operator",
        "conditional_expression",
        "list_comprehension",
        "set_comprehension",
        "dict_comprehension",
        "generator_expression",
        "match_statement",
        "case_clause",
    },
    "javascript": {
        "if_statement",
        "else_clause",
        "for_statement",
        "for_in_statement",
        "for_of_statement",
        "while_statement",
        "do_statement",
        "catch_clause",
        "ternary_expression",
        "switch_case",
        "switch_default",
        "logical_expression",
        "conditional_expression",
    },
    "typescript": {
        "if_statement",
        "else_clause",
        "for_statement",
        "for_in_statement",
        "for_of_statement",
        "while_statement",
        "do_statement",
        "catch_clause",
        "ternary_expression",
        "switch_case",
        "switch_default",
        "logical_expression",
        "conditional_expression",
    },
    "java": {
        "if_statement",
        "else_clause",
        "for_statement",
        "enhanced_for_statement",
        "while_statement",
        "do_statement",
        "catch_clause",
        "ternary_expression",
        "switch_block_statement_group",
        "logical_expression",
        "conditional_expression",
    },
    "go": {
        "if_statement",
        "else_clause",
        "for_statement",
        "expression_switch_case",
        "type_switch_case",
        "select_case",
        "binary_expression",
    },
    "rust": {
        "if_expression",
        "else_clause",
        "for_expression",
        "while_expression",
        "loop_expression",
        "match_arm",
        "binary_expression",
    },
    "c": {
        "if_statement",
        "else_clause",
        "for_statement",
        "while_statement",
        "do_statement",
        "switch_case",
        "binary_expression",
        "conditional_expression",
    },
    "cpp": {
        "if_statement",
        "else_clause",
        "for_statement",
        "while_statement",
        "do_statement",
        "switch_case",
        "binary_expression",
        "conditional_expression",
        "range_based_for_statement",
        "catch_clause",
    },
}

_WALK_MAX_DEPTH = 100
