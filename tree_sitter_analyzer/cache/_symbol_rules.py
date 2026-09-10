"""提供语法分类的兼容导出，以及复杂度与命名规则。"""

from __future__ import annotations

import re

from .node_taxonomy import LANGUAGE_NODES, nodes_for


def _category_union(category: str) -> frozenset[str]:
    """旧调用方保留联合视图；运行时遍历直接读取按语言分类。"""
    return frozenset(
        node for rules in LANGUAGE_NODES.values() for node in rules.get(category, ())
    )


_FUNCTION_LIKE = _category_union("function_like")
_CLASS_LIKE = _category_union("class_like")
_ENUM_LIKE = _category_union("enum_like")
_IMPORT_LIKE = _category_union("import_like")
_VAR_DECL_LIKE = _category_union("var_decl_like")
_SCALA_CLASS_LIKE = nodes_for("scala", "deferred_class_like")
_GO_CONST_LIKE = nodes_for("go", "const_like")
_RUST_CONST_LIKE = nodes_for("rust", "const_like")
_SCOPE_BODY_NODES = {
    language: rules.get("scope_body", frozenset())
    for language, rules in LANGUAGE_NODES.items()
}
_PY_SCOPE_BODY_NODES = nodes_for("python", "scope_body")
_GO_SCOPE_BODY_NODES = nodes_for("go", "scope_body")
_RUST_SCOPE_BODY_NODES = nodes_for("rust", "scope_body")
_PHP_SCOPE_BODY_NODES = nodes_for("php", "scope_body")
_JSTS_SCOPE_BODY_NODES = nodes_for("javascript", "scope_body")
_JAVA_SCOPE_BODY_NODES = nodes_for("java", "scope_body")
_CSHARP_SCOPE_BODY_NODES = nodes_for("csharp", "scope_body")
_SCALA_SCOPE_BODY_NODES = nodes_for("scala", "scope_body")
_CONST_STYLE_NAME = re.compile(r"^_?[A-Z][A-Z0-9_]+$")
_PY_CONST_STYLE_NAME = re.compile(r"^_?[A-Z][A-Z0-9_]*$")
_PY_DUNDER_NAME = re.compile(r"^__\w+__$")


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
