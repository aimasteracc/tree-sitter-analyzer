"""Grammar Introspection System for Tree-sitter Languages.

使用 tree-sitter 内置 API 自动提取语言语法的所有节点类型，
并基于命名模式自动分类为"可提取"和"结构性"节点。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from ..utils import log_debug, log_error

# 语言到 tree-sitter 模块的映射
LANGUAGE_MODULE_MAP = {
    "python": "tree_sitter_python",
    "javascript": "tree_sitter_javascript",
    "typescript": "tree_sitter_typescript",
    "go": "tree_sitter_go",
    "rust": "tree_sitter_rust",
    "java": "tree_sitter_java",
    "cpp": "tree_sitter_cpp",
    "c": "tree_sitter_c",
    "csharp": "tree_sitter_c_sharp",
    "ruby": "tree_sitter_ruby",
    "php": "tree_sitter_php",
    "swift": "tree_sitter_swift",
    "kotlin": "tree_sitter_kotlin",
    "scala": "tree_sitter_scala",
    "bash": "tree_sitter_bash",
    "yaml": "tree_sitter_yaml",
    "json": "tree_sitter_json",
    "sql": "tree_sitter_sql",
}

# 可提取节点的后缀模式（表示语义实体）
EXTRACTABLE_SUFFIXES = (
    "_definition",  # function_definition, class_definition
    "_declaration",  # variable_declaration, field_declaration
    "_statement",  # import_statement, return_statement
    "_item",  # Rust: function_item, impl_item, struct_item
)

# 可提取节点的完整名称模式（Ruby 等语言使用简洁命名）
EXTRACTABLE_EXACT_NAMES = (
    "class",  # Ruby: class
    "method",  # Ruby: method
    "singleton_method",  # Ruby: singleton_method
    "function",  # 某些语言的 function 节点
)

# 结构性节点的模式（仅用于组织，不代表可提取实体）
STRUCTURAL_PATTERNS = (
    "block",  # code block
    "body",  # function body, class body
    "_list",  # parameter_list, argument_list
    "_clause",  # else_clause, except_clause
    "comment",  # 注释节点
    "identifier",  # 标识符
    "literal",  # 字面量
    "expression",  # 表达式
    "operator",  # 操作符
)


def _validate_language(language: str) -> str:
    """Validate ``language`` against ``LANGUAGE_MODULE_MAP``; return module name."""
    if language not in LANGUAGE_MODULE_MAP:
        supported = ", ".join(sorted(LANGUAGE_MODULE_MAP.keys()))
        raise ValueError(f"Unsupported language: {language}. Supported: {supported}")
    return LANGUAGE_MODULE_MAP[language]


def _import_ts_module(module_name: str) -> object:
    """Dynamically import the tree-sitter language module; raise ImportError if missing."""
    import importlib

    try:
        return importlib.import_module(module_name)
    except ImportError as e:
        log_error(f"Failed to import {module_name}: {e}")
        raise ImportError(
            f"Language module {module_name} not installed. "
            f"Install with: pip install {module_name}"
        ) from e


def _get_language_capsule(ts_module: object, language: str, module_name: str) -> object:
    """Probe the module for a known language-getter function and return its capsule.

    Tries ``language_{lang}()`` → ``language()`` → ``language_{lang}_only()`` in
    order (different tree-sitter language modules use different conventions).
    """
    possible_function_names = [
        f"language_{language}",  # tree_sitter_php.language_php()
        "language",  # 标准命名
        f"language_{language}_only",  # tree_sitter_php.language_php_only()
    ]
    for func_name in possible_function_names:
        if hasattr(ts_module, func_name):
            language_func = getattr(ts_module, func_name)
            log_debug(f"Using {func_name}() for {language}")
            return language_func()

    available_attrs = [attr for attr in dir(ts_module) if "language" in attr.lower()]
    raise AttributeError(
        f"{module_name} has no standard language function. Available: {available_attrs}"
    )


def _collect_named_node_types(lang_obj: object) -> list[str]:
    """Walk ``lang_obj.node_kind_count`` and return sorted named node types."""
    node_kind_count = lang_obj.node_kind_count  # type: ignore[attr-defined]
    named_types: list[str] = []
    for i in range(node_kind_count):
        if lang_obj.node_kind_is_named(i):  # type: ignore[attr-defined]
            node_type = lang_obj.node_kind_for_id(i)  # type: ignore[attr-defined]
            if node_type:  # 过滤 None 值（理论上不应出现）
                named_types.append(node_type)
    return sorted(named_types)


def get_all_node_types(language: str) -> list[str]:
    """获取指定语言的所有命名节点类型。

    使用 tree-sitter Language 对象的内置 API 提取语法中定义的所有节点类型。

    Args:
        language: 语言名称（如 "python", "javascript"）

    Returns:
        所有命名节点类型的列表，按字母顺序排序

    Raises:
        ImportError: 如果 tree-sitter 或对应语言的模块未安装
        ValueError: 如果语言不受支持

    r37e8 (dogfood): 82 lines → ~12 lines of orchestration. Per-phase helpers
    (``_validate_language`` / ``_import_ts_module`` / ``_get_language_capsule``
    / ``_collect_named_node_types``) own the individual steps.
    """
    import tree_sitter

    module_name = _validate_language(language)
    ts_module = _import_ts_module(module_name)
    try:
        language_capsule = _get_language_capsule(ts_module, language, module_name)
        lang_obj = tree_sitter.Language(language_capsule)
        named_types = _collect_named_node_types(lang_obj)
        log_debug(f"Extracted {len(named_types)} named node types for {language}")
        return named_types
    except Exception as e:
        log_error(f"Failed to extract node types for {language}: {e}")
        raise


def auto_detect_extractable_types(node_types: list[str]) -> list[str]:
    """基于命名模式自动检测可提取节点类型。

    可提取节点类型特征：
    - 以 *_definition 结尾（如 function_definition, class_definition）
    - 以 *_declaration 结尾（如 variable_declaration, field_declaration）
    - 以 *_statement 结尾（如 import_statement, return_statement）
    - 以 *_item 结尾（Rust: function_item, impl_item）
    - 完全匹配特定名称（Ruby: class, method, singleton_method）

    排除模式：
    - 包含 block, body, _list, _clause 等结构性关键字
    - 纯标识符、字面量、表达式、操作符等

    Args:
        node_types: 节点类型列表

    Returns:
        可提取节点类型列表，按字母顺序排序
    """
    extractable = []

    for node_type in node_types:
        # 检查是否匹配可提取后缀
        matches_suffix = any(
            node_type.endswith(suffix) for suffix in EXTRACTABLE_SUFFIXES
        )

        # 检查是否完全匹配特定名称
        matches_exact = node_type in EXTRACTABLE_EXACT_NAMES

        is_extractable = matches_suffix or matches_exact

        # 排除结构性模式
        is_structural = any(pattern in node_type for pattern in STRUCTURAL_PATTERNS)

        if is_extractable and not is_structural:
            extractable.append(node_type)

    log_debug(f"Auto-detected {len(extractable)} extractable types")
    return sorted(extractable)


def get_structural_types(node_types: list[str]) -> list[str]:
    """识别结构性节点类型（非可提取）。

    结构性节点特征：
    - 包含 block, body, _list, _clause 等关键字
    - 纯标识符、字面量、表达式、操作符
    - 不以 *_definition, *_declaration, *_statement 结尾

    Args:
        node_types: 节点类型列表

    Returns:
        结构性节点类型列表，按字母顺序排序
    """
    structural = []

    for node_type in node_types:
        # 检查是否匹配结构性模式
        is_structural = any(pattern in node_type for pattern in STRUCTURAL_PATTERNS)

        # 排除可提取后缀
        is_extractable = any(
            node_type.endswith(suffix) for suffix in EXTRACTABLE_SUFFIXES
        )

        if is_structural or not is_extractable:
            structural.append(node_type)

    log_debug(f"Identified {len(structural)} structural types")
    return sorted(structural)


def get_language_summary(language: str) -> dict[str, list[str] | int]:
    """获取指定语言的语法节点类型摘要。

    Args:
        language: 语言名称

    Returns:
        包含以下字段的字典：
        - all_types: 所有命名节点类型
        - extractable_types: 可提取节点类型
        - structural_types: 结构性节点类型
        - total_count: 总节点类型数
        - extractable_count: 可提取节点数
        - structural_count: 结构性节点数
    """
    all_types = get_all_node_types(language)
    extractable = auto_detect_extractable_types(all_types)
    structural = get_structural_types(all_types)

    return {
        "all_types": all_types,
        "extractable_types": extractable,
        "structural_types": structural,
        "total_count": len(all_types),
        "extractable_count": len(extractable),
        "structural_count": len(structural),
    }
