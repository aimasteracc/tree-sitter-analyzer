"""Golden Corpus Generator for Grammar Coverage MECE Framework.

自动生成用于语法覆盖验证的黄金语料库（golden corpus）。
针对每种语言的节点类型，生成最小化的、可解析的代码示例。

设计理念：
- 模板驱动生成（template-based generation）
- 按分类组织（category-based organization）
- 多个小文件而非单个大文件
- 优先支持 Python、JavaScript、Java（proof-of-concept）

目录结构：
corpus/
  python/
    functions/basic_functions.py    # function_definition, async_function_definition
    classes/basic_classes.py        # class_definition
    statements/control_flow.py      # if_statement, for_statement, while_statement
  javascript/
    functions/functions.js          # function_declaration, arrow_function
    classes/classes.js              # class_declaration
  java/
    functions/Methods.java          # method_declaration
    classes/Classes.java            # class_declaration
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from ..utils import log_debug, log_error, log_warning

# 语言到文件扩展名的映射
LANGUAGE_EXTENSIONS = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "java": ".java",
    "go": ".go",
    "rust": ".rs",
    "c": ".c",
    "cpp": ".cpp",
    "csharp": ".cs",
    "ruby": ".rb",
    "php": ".php",
    "swift": ".swift",
    "kotlin": ".kt",
    "scala": ".scala",
    "bash": ".sh",
    "yaml": ".yaml",
    "json": ".json",
}

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
}

# Python 代码模板
PYTHON_TEMPLATES = {
    "function_definition": "def foo():\n    pass\n",
    "async_function": "async def async_foo():\n    pass\n",
    "class_definition": "class Foo:\n    pass\n",
    "if_statement": "if True:\n    pass\n",
    "for_statement": "for i in range(10):\n    pass\n",
    "while_statement": "while False:\n    pass\n",
    "try_statement": "try:\n    pass\nexcept Exception:\n    pass\n",
    "with_statement": "with open('file.txt') as f:\n    pass\n",
    "import_statement": "import os\n",
    "import_from_statement": "from typing import Any\n",
    "expression_statement": "x = 1\n",
    "assignment": "x = 42\n",
    "return_statement": "def f():\n    return 1\n",
    "decorated_definition": "@decorator\ndef foo():\n    pass\n",
    "lambda": "lambda x: x + 1\n",
    "list_comprehension": "[x for x in range(10)]\n",
    "dictionary_comprehension": "{x: x*2 for x in range(10)}\n",
    "assert_statement": "assert True\n",
    "raise_statement": "raise ValueError('error')\n",
    "pass_statement": "pass\n",
    "break_statement": "while True:\n    break\n",
    "continue_statement": "for i in range(10):\n    continue\n",
    "global_statement": "global x\n",
    "nonlocal_statement": "def outer():\n    x = 1\n    def inner():\n        nonlocal x\n",
    "delete_statement": "x = 1\ndel x\n",
}

# JavaScript 代码模板
JAVASCRIPT_TEMPLATES = {
    "function_declaration": "function foo() {}\n",
    "arrow_function": "const f = () => {};\n",
    "class_declaration": "class Foo {}\n",
    "if_statement": "if (true) {}\n",
    "for_statement": "for (let i = 0; i < 10; i++) {}\n",
    "while_statement": "while (false) {}\n",
    "try_statement": "try {} catch (e) {}\n",
    "switch_statement": "switch (x) { case 1: break; }\n",
    "return_statement": "function f() { return 1; }\n",
    "throw_statement": "throw new Error('error');\n",
    "import_statement": "import fs from 'fs';\n",
    "export_statement": "export const x = 1;\n",
    "variable_declaration": "const x = 1;\n",
    "expression_statement": "x = 1;\n",
    "method_definition": "class Foo { bar() {} }\n",
    "do_statement": "do {} while (false);\n",
    "break_statement": "while (true) { break; }\n",
    "continue_statement": "for (;;) { continue; }\n",
    "lexical_declaration": "let x = 1;\n",
    "labeled_statement": "label: while (true) { break label; }\n",
    "debugger_statement": "debugger;\n",
}

# Java 代码模板
JAVA_TEMPLATES = {
    "method_declaration": "class Foo { void bar() {} }\n",
    "class_declaration": "class Foo {}\n",
    "interface_declaration": "interface Foo {}\n",
    "field_declaration": "class Foo { int x; }\n",
    "local_variable_declaration": "class Foo { void bar() { int x = 1; } }\n",
    "if_statement": "class Foo { void bar() { if (true) {} } }\n",
    "for_statement": "class Foo { void bar() { for (int i = 0; i < 10; i++) {} } }\n",
    "while_statement": "class Foo { void bar() { while (false) {} } }\n",
    "try_statement": "class Foo { void bar() { try {} catch (Exception e) {} } }\n",
    "return_statement": "class Foo { int bar() { return 1; } }\n",
    "throw_statement": "class Foo { void bar() { throw new Exception(); } }\n",
    "import_declaration": "import java.util.List;\n",
    "package_declaration": "package com.example;\n",
    "constructor_declaration": "class Foo { Foo() {} }\n",
    "enum_declaration": "enum Foo { A, B, C }\n",
    "annotation_type_declaration": "@interface Foo {}\n",
    "switch_statement": "class Foo { void bar() { switch (x) { case 1: break; } } }\n",
    "do_statement": "class Foo { void bar() { do {} while (false); } }\n",
    "break_statement": "class Foo { void bar() { while (true) { break; } } }\n",
    "continue_statement": "class Foo { void bar() { for (;;) { continue; } } }\n",
    "synchronized_statement": "class Foo { void bar() { synchronized (this) {} } }\n",
}

# 代码模板注册表（所有语言的集合）
CODE_TEMPLATES: dict[str, dict[str, str]] = {
    "python": PYTHON_TEMPLATES,
    "javascript": JAVASCRIPT_TEMPLATES,
    "java": JAVA_TEMPLATES,
}

# 节点类型到分类的映射（用于组织文件结构）
NODE_TYPE_CATEGORIES = {
    "python": {
        "functions": [
            "function_definition",
            "async_function",
            "lambda",
            "decorated_definition",
        ],
        "classes": ["class_definition"],
        "statements": [
            "if_statement",
            "for_statement",
            "while_statement",
            "try_statement",
            "with_statement",
            "return_statement",
            "raise_statement",
            "assert_statement",
            "pass_statement",
            "break_statement",
            "continue_statement",
            "delete_statement",
            "global_statement",
            "nonlocal_statement",
        ],
        "imports": ["import_statement", "import_from_statement"],
        "expressions": [
            "expression_statement",
            "assignment",
            "list_comprehension",
            "dictionary_comprehension",
        ],
    },
    "javascript": {
        "functions": [
            "function_declaration",
            "arrow_function",
            "method_definition",
        ],
        "classes": ["class_declaration"],
        "statements": [
            "if_statement",
            "for_statement",
            "while_statement",
            "do_statement",
            "switch_statement",
            "try_statement",
            "return_statement",
            "throw_statement",
            "break_statement",
            "continue_statement",
            "debugger_statement",
            "labeled_statement",
        ],
        "imports": ["import_statement", "export_statement"],
        "declarations": ["variable_declaration", "lexical_declaration"],
        "expressions": ["expression_statement"],
    },
    "java": {
        "methods": ["method_declaration", "constructor_declaration"],
        "classes": [
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
            "annotation_type_declaration",
        ],
        "statements": [
            "if_statement",
            "for_statement",
            "while_statement",
            "do_statement",
            "switch_statement",
            "try_statement",
            "return_statement",
            "throw_statement",
            "break_statement",
            "continue_statement",
            "synchronized_statement",
        ],
        "declarations": [
            "field_declaration",
            "local_variable_declaration",
            "import_declaration",
            "package_declaration",
        ],
    },
}


def generate_minimal_code_for_node_type(language: str, node_type: str) -> str:
    """生成指定节点类型的最小化代码示例。

    Args:
        language: 语言名称（如 "python", "javascript"）
        node_type: 节点类型名称（如 "function_definition", "class_declaration"）

    Returns:
        最小化的代码字符串，如果无法生成则返回空字符串

    Examples:
        >>> generate_minimal_code_for_node_type("python", "function_definition")
        'def foo():\\n    pass\\n'
        >>> generate_minimal_code_for_node_type("javascript", "arrow_function")
        'const f = () => {};\\n'
        >>> generate_minimal_code_for_node_type("java", "class_declaration")
        'class Foo {}\\n'
    """
    if language not in CODE_TEMPLATES:
        log_warning(f"No templates available for language: {language}")
        return ""

    templates = CODE_TEMPLATES[language]
    if node_type not in templates:
        log_debug(f"No template for node type: {node_type} in {language}")
        return ""

    return templates[node_type]


def generate_corpus_by_category(language: str) -> dict[str, str]:
    """生成按分类组织的完整语料库。

    将相关的节点类型组合到同一个文件中，按照 category 进行分组。

    Args:
        language: 语言名称

    Returns:
        字典映射：{相对路径: 代码内容}
        例如：{"functions/basic.py": "def foo():\\n    pass\\n", ...}

    Examples:
        >>> corpus = generate_corpus_by_category("python")
        >>> "functions/basic_functions.py" in corpus
        True
        >>> "classes/basic_classes.py" in corpus
        True
    """
    if language not in NODE_TYPE_CATEGORIES:
        log_warning(f"No category mapping for language: {language}")
        return {}

    if language not in LANGUAGE_EXTENSIONS:
        log_error(f"No file extension mapping for language: {language}")
        return {}

    # 确定注释语法
    comment_prefix = _get_comment_prefix(language)

    ext = LANGUAGE_EXTENSIONS[language]
    categories = NODE_TYPE_CATEGORIES[language]
    corpus: dict[str, str] = {}

    for category, node_types in categories.items():
        # 收集该分类下的所有代码片段
        code_snippets: list[str] = []

        for node_type in node_types:
            code = generate_minimal_code_for_node_type(language, node_type)
            if code:
                # 添加注释标记节点类型（使用正确的注释语法）
                code_snippets.append(f"{comment_prefix} Node type: {node_type}\n{code}\n")

        if code_snippets:
            # 组合成一个文件
            filename = f"{category}/basic_{category}{ext}"
            full_code = "".join(code_snippets)
            corpus[filename] = full_code

    log_debug(f"Generated corpus for {language}: {len(corpus)} files")
    return corpus


def _get_comment_prefix(language: str) -> str:
    """获取语言的注释前缀。

    Args:
        language: 语言名称

    Returns:
        注释前缀字符串（如 "#", "//" 等）
    """
    # Python, Ruby, Bash, YAML 使用 #
    if language in ["python", "ruby", "bash", "yaml"]:
        return "#"
    # C-style languages 使用 //
    elif language in [
        "javascript",
        "typescript",
        "java",
        "go",
        "rust",
        "c",
        "cpp",
        "csharp",
        "php",
        "swift",
        "kotlin",
        "scala",
    ]:
        return "//"
    else:
        return "#"  # 默认使用 #


def validate_generated_code(language: str, code: str) -> bool:
    """验证生成的代码是否可被 tree-sitter 成功解析。

    Args:
        language: 语言名称
        code: 待验证的代码字符串

    Returns:
        True 如果代码可解析且无语法错误，否则 False

    Examples:
        >>> validate_generated_code("python", "def foo():\\n    pass\\n")
        True
        >>> validate_generated_code("python", "def foo():\\n  invalid syntax")
        False
    """
    if language not in LANGUAGE_MODULE_MAP:
        log_error(f"Unsupported language for validation: {language}")
        return False

    try:
        import tree_sitter

        module_name = LANGUAGE_MODULE_MAP[language]
        ts_module = importlib.import_module(module_name)

        # 获取 Language 对象
        language_capsule = None
        possible_function_names = [
            f"language_{language}",
            "language",
            f"language_{language}_only",
        ]

        for func_name in possible_function_names:
            if hasattr(ts_module, func_name):
                language_func = getattr(ts_module, func_name)
                language_capsule = language_func()
                break

        if language_capsule is None:
            log_error(f"Cannot find language function in {module_name}")
            return False

        lang_obj = tree_sitter.Language(language_capsule)
        parser = tree_sitter.Parser(lang_obj)

        # 解析代码
        tree = parser.parse(bytes(code, "utf-8"))

        # 检查是否有语法错误（通过 ERROR 节点检测）
        def has_error_node(node: tree_sitter.Node) -> bool:
            if node.type == "ERROR" or node.is_missing:
                return True
            return any(has_error_node(child) for child in node.children)

        is_valid = not has_error_node(tree.root_node)

        if not is_valid:
            log_warning(f"Validation failed for {language} code:\n{code}")

        return is_valid

    except ImportError as e:
        log_error(f"Cannot import tree-sitter module for {language}: {e}")
        return False
    except Exception as e:
        log_error(f"Validation error for {language}: {e}")
        return False


def save_corpus_files(
    language: str,
    corpus: dict[str, str],
    base_dir: str = "corpus/",
) -> list[Path]:
    """将语料库文件保存到磁盘。

    Args:
        language: 语言名称
        corpus: 语料库字典（相对路径 → 代码内容）
        base_dir: 基础目录路径（默认 "corpus/"）

    Returns:
        已保存的文件路径列表

    Examples:
        >>> corpus = {"functions/basic.py": "def foo():\\n    pass\\n"}
        >>> paths = save_corpus_files("python", corpus, "test_corpus/")
        >>> len(paths) > 0
        True
    """
    base_path = Path(base_dir)
    language_path = base_path / language
    saved_paths: list[Path] = []

    try:
        for relative_path, code in corpus.items():
            file_path = language_path / relative_path

            # 创建父目录
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入文件（UTF-8 编码）
            file_path.write_text(code, encoding="utf-8")
            saved_paths.append(file_path)
            log_debug(f"Saved corpus file: {file_path}")

        log_debug(f"Saved {len(saved_paths)} corpus files for {language}")
        return saved_paths

    except Exception as e:
        log_error(f"Failed to save corpus files for {language}: {e}")
        return saved_paths


def generate_and_save_corpus(
    language: str,
    base_dir: str = "corpus/",
    validate: bool = True,
) -> tuple[list[Path], int, int]:
    """生成并保存完整的语料库（便捷函数）。

    Args:
        language: 语言名称
        base_dir: 基础目录路径
        validate: 是否验证生成的代码

    Returns:
        元组 (已保存的文件路径列表, 成功验证的文件数, 验证失败的文件数)

    Examples:
        >>> paths, success, failed = generate_and_save_corpus("python", "test_corpus/")
        >>> len(paths) > 0
        True
        >>> success > 0
        True
    """
    corpus = generate_corpus_by_category(language)

    if not corpus:
        log_warning(f"No corpus generated for {language}")
        return [], 0, 0

    # 验证所有生成的代码
    validation_success = 0
    validation_failed = 0

    if validate:
        for relative_path, code in corpus.items():
            if validate_generated_code(language, code):
                validation_success += 1
            else:
                validation_failed += 1
                log_warning(f"Validation failed for: {relative_path}")

    # 保存到磁盘
    saved_paths = save_corpus_files(language, corpus, base_dir)

    return saved_paths, validation_success, validation_failed
