"""按语言声明 tree-sitter 节点分类，并直接驱动缓存索引的遍历。

LANGUAGE_NODES[language][category] 返回不可变节点集合。分类涵盖函数、类、
枚举、导入、变量、常量、作用域边界及 Scala 延迟类型；未知分类返回空集合。
所有声明由真实语法验证，运行时测试同时验证各分类确实控制提取结果。

Scala 的 object/trait/enum/given/type 走延迟分支，函数体内不输出这些类型；
普通 class 原本已有成员归属。JS/TS 具名 function_expression 也进入函数索引。
迁移不承诺任意源码逐字节等价：上述行为变化由测试和提取版本显式跟踪。
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "LANGUAGE_NODES",
    "CATEGORIES",
    "SUPPORTED_LANGUAGES",
    "nodes_for",
    "is_a",
    "normalize_language",
]

CATEGORIES: Final = (
    "function_like",
    "class_like",
    "enum_like",
    "import_like",
    "var_decl_like",
    "scope_body",
    "const_like",
    "deferred_class_like",
)

# ``tsx``/``jsx`` are the TypeScript/JavaScript grammars under another name;
# the walker treats them identically to their base language.
_LANGUAGE_ALIASES: Final[dict[str, str]] = {
    "tsx": "typescript",
    "jsx": "javascript",
}


def normalize_language(language: str) -> str:
    """Fold grammar dialects onto the language whose rules they follow."""
    return _LANGUAGE_ALIASES.get(language, language)


# ``ERROR`` is tree-sitter's error-recovery pseudo-node, not a grammar rule.
# Declarations inside an error-recovered region have undecidable scope, so
# JS/TS, Java and C# treat it as a scope body: better unindexed than wrong.
_ERROR: Final = "ERROR"

LANGUAGE_NODES: Final[dict[str, dict[str, frozenset[str]]]] = {
    "python": {
        "function_like": frozenset({"function_definition"}),
        "const_like": frozenset({"assignment"}),
        # ``module`` is Python's ROOT node, not a type declaration. It is
        # listed because the previous flat set contained it (Ruby's module)
        # and the root therefore matched the class branch. It is harmless
        # only because the root has no ``name`` field — a coincidence, not a
        # design. Kept out deliberately; see test_python_root_is_not_a_class.
        "class_like": frozenset({"class_definition"}),
        "import_like": frozenset(
            {
                "import_statement",
                "import_from_statement",
                # tree-sitter emits a dedicated node for ``from __future__
                # import X``; omitting it cost 787 import rows repo-wide.
                "future_import_statement",
            }
        ),
        "scope_body": frozenset({"function_definition", "class_definition"}),
    },
    "javascript": {
        "function_like": frozenset(
            {
                "function_declaration",
                "function_expression",
                "arrow_function",
                "method_definition",
                "generator_function_declaration",
            }
        ),
        "class_like": frozenset({"class_declaration", "class"}),
        "import_like": frozenset({"import_statement"}),
        "var_decl_like": frozenset(
            {
                "variable_declarator",
                "lexical_declaration",
                "variable_declaration",
                "assignment_expression",
            }
        ),
        # ``statement_block`` is deliberately absent: module-level if/try
        # bodies are statement_blocks outside any function, and gating on
        # them would drop module-scope declarators.
        "scope_body": frozenset(
            {
                "function_declaration",
                "function_expression",
                "arrow_function",
                "method_definition",
                "generator_function",
                "generator_function_declaration",
                "class_static_block",
                _ERROR,
            }
        ),
    },
    "typescript": {
        "function_like": frozenset(
            {
                "function_declaration",
                "function_expression",
                "arrow_function",
                "method_definition",
                "generator_function_declaration",
            }
        ),
        "class_like": frozenset(
            {
                "class_declaration",
                "class",
                "abstract_class_declaration",
                "interface_declaration",
                "enum_declaration",
            }
        ),
        "enum_like": frozenset({"enum_declaration"}),
        "import_like": frozenset({"import_statement"}),
        "var_decl_like": frozenset(
            {
                "variable_declarator",
                "lexical_declaration",
                "variable_declaration",
                "assignment_expression",
            }
        ),
        "scope_body": frozenset(
            {
                "function_declaration",
                "function_expression",
                "arrow_function",
                "method_definition",
                "generator_function",
                "generator_function_declaration",
                "class_static_block",
                _ERROR,
            }
        ),
    },
    "java": {
        "function_like": frozenset(
            {
                "method_declaration",
                "constructor_declaration",
                "lambda_expression",
            }
        ),
        "class_like": frozenset(
            {
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
                "annotation_type_declaration",
                # Java 16+ records own their methods and constructors.
                "record_declaration",
            }
        ),
        "enum_like": frozenset({"enum_declaration"}),
        "import_like": frozenset({"import_declaration", "package_declaration"}),
        "var_decl_like": frozenset({"variable_declarator", "assignment_expression"}),
        # ``block`` is safe here: Java fields never sit inside a block, while
        # the instance initializer is a bare block child of class_body.
        "scope_body": frozenset(
            {
                "method_declaration",
                "constructor_declaration",
                "compact_constructor_declaration",
                "lambda_expression",
                "static_initializer",
                "block",
                _ERROR,
            }
        ),
    },
    "go": {
        "function_like": frozenset({"function_declaration", "method_declaration"}),
        "class_like": frozenset({"type_declaration", "type_spec"}),
        "import_like": frozenset({"import_declaration"}),
        "var_decl_like": frozenset({"const_declaration"}),
        "const_like": frozenset({"const_declaration", "var_declaration"}),
        "scope_body": frozenset(
            {"function_declaration", "method_declaration", "func_literal"}
        ),
    },
    "rust": {
        "function_like": frozenset({"function_item"}),
        "class_like": frozenset({"struct_item", "impl_item", "trait_item"}),
        "import_like": frozenset({"use_declaration"}),
        "var_decl_like": frozenset({"let_declaration", "assignment_expression"}),
        "const_like": frozenset({"const_item", "static_item"}),
        # ``block`` is needed for const-initializer block expressions; mod
        # and impl bodies are declaration_list, so module scope survives.
        "scope_body": frozenset({"function_item", "closure_expression", "block"}),
    },
    "c": {
        # C carries the identifier under function_declarator rather than a
        # ``name`` field; the walker recovers it explicitly.
        "function_like": frozenset(
            {
                "function_definition",
                "function_declarator",
                "declaration",
                "init_declarator",
            }
        ),
        "class_like": frozenset({"struct_specifier", "enum_specifier"}),
        "import_like": frozenset({"preproc_include"}),
        "enum_like": frozenset({"enum_specifier"}),
        "var_decl_like": frozenset({"assignment_expression"}),
    },
    "cpp": {
        "function_like": frozenset(
            {
                "function_definition",
                "function_declarator",
                "declaration",
                "init_declarator",
                "lambda_expression",
            }
        ),
        "class_like": frozenset(
            {"class_specifier", "struct_specifier", "enum_specifier"}
        ),
        "import_like": frozenset({"preproc_include"}),
        "enum_like": frozenset({"enum_specifier"}),
        "var_decl_like": frozenset({"assignment_expression"}),
    },
    "csharp": {
        "function_like": frozenset(
            {
                "method_declaration",
                "constructor_declaration",
                "lambda_expression",
            }
        ),
        "class_like": frozenset(
            {
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
                "struct_declaration",
                "record_declaration",
            }
        ),
        "enum_like": frozenset({"enum_declaration"}),
        "var_decl_like": frozenset(
            {"variable_declarator", "variable_declaration", "assignment_expression"}
        ),
        # ``block`` is deliberately absent: C# top-level statements put
        # blocks at compilation-unit level, so gating on them would drop
        # top-level declarators.
        "scope_body": frozenset(
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
                _ERROR,
            }
        ),
    },
    "ruby": {
        "function_like": frozenset({"method", "singleton_method"}),
        "class_like": frozenset({"class", "module"}),
    },
    "kotlin": {
        "function_like": frozenset({"function_declaration", "anonymous_function"}),
        # ``companion_object`` has no name field; the parent walk continues
        # through it so its members belong to the enclosing class.
        "class_like": frozenset({"class_declaration", "companion_object"}),
        "var_decl_like": frozenset({"variable_declaration"}),
    },
    "php": {
        "function_like": frozenset(
            {
                "function_definition",
                "method_declaration",
                "anonymous_function",
                "arrow_function",
            }
        ),
        "class_like": frozenset(
            {
                "class_declaration",
                "interface_declaration",
                "trait_declaration",
                "enum_declaration",
            }
        ),
        "enum_like": frozenset({"enum_declaration"}),
        "import_like": frozenset({"use_declaration"}),
        "var_decl_like": frozenset({"const_declaration", "assignment_expression"}),
        "const_like": frozenset({"const_declaration"}),
        "scope_body": frozenset(
            {
                "function_definition",
                "method_declaration",
                "anonymous_function",
                "arrow_function",
            }
        ),
    },
    "scala": {
        "function_like": frozenset(
            {"function_definition", "function_declaration", "lambda_expression"}
        ),
        "class_like": frozenset(
            {
                "class_definition",
                "object_definition",
                "trait_definition",
                "enum_definition",
                "given_definition",
                "type_definition",
            }
        ),
        # Reported through the deferred branch, and only when not enclosed by
        # a method body: a method-local ``given``/``type`` must not surface as
        # a top-level type. ``class_definition`` is deliberately absent — it
        # goes through the ordinary class branch like every other language.
        "deferred_class_like": frozenset(
            {
                "object_definition",
                "trait_definition",
                "enum_definition",
                "given_definition",
                "type_definition",
            }
        ),
        "enum_like": frozenset({"enum_definition"}),
        "import_like": frozenset({"import_declaration"}),
        "var_decl_like": frozenset({"assignment_expression"}),
        "scope_body": frozenset({"function_definition", "function_declaration"}),
    },
    "swift": {
        "function_like": frozenset({"function_declaration"}),
        "class_like": frozenset({"class_declaration"}),
        "import_like": frozenset({"import_declaration"}),
    },
    "lua": {
        "function_like": frozenset({"function_declaration", "function_definition"}),
        "var_decl_like": frozenset({"variable_declaration"}),
    },
    "bash": {
        "function_like": frozenset({"function_definition"}),
        "var_decl_like": frozenset({"variable_assignment"}),
    },
}

SUPPORTED_LANGUAGES: Final = frozenset(LANGUAGE_NODES)

_EMPTY: Final[frozenset[str]] = frozenset()


def nodes_for(language: str, category: str) -> frozenset[str]:
    """Node types in ``category`` for ``language``; empty when undeclared.

    Never raises: an unknown language or category simply contributes no
    node types, which degrades to "extract nothing" rather than crashing an
    index run over a repo containing an unexpected file type.
    """
    return LANGUAGE_NODES.get(normalize_language(language), {}).get(category, _EMPTY)


def is_a(language: str, category: str, node_type: str) -> bool:
    """Whether ``node_type`` belongs to ``category`` in ``language``."""
    return node_type in nodes_for(language, category)
