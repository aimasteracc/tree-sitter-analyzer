"""Built-in code corpus for Phase 3 Auto-Discovery Engine.

每种语言提供覆盖主要语法结构的代码片段，用于：
1. Wrapper node 结构分析（解析 AST 提取特征）
2. 语法路径枚举（BFS 遍历发现节点类型组合）
3. 覆盖率缺口分析（对比 grammar 全量 vs corpus 中出现的）

注意：BUILTIN_CORPUS 存储 str（UTF-8 文本），但某些语言需要
BUILTIN_CORPUS_EXTRA 中额外的字节级 corpus（如 Python 2 语法片段）。
auto_discovery._collect_node_stats 会自动合并两者。

Per-language data lives in ``grammar_coverage/corpora/<lang>.py``.
This module re-exports the assembled dicts for backward compatibility.
"""

from .corpora import BUILTIN_CORPUS, BUILTIN_CORPUS_EXTRA

# 语言名到文件扩展名的映射（用于 CLI 显示）
LANGUAGE_EXTENSIONS: dict[str, str] = {
    "python": "py",
    "javascript": "js",
    "typescript": "ts",
    "java": "java",
    "go": "go",
    "rust": "rs",
    "c": "c",
    "cpp": "cpp",
    "csharp": "cs",
    "ruby": "rb",
    "php": "php",
    "kotlin": "kt",
    "yaml": "yaml",
    "sql": "sql",
}

# 分析目标语言列表（仅包含有 corpus 且有安装包的语言）
TARGET_LANGUAGES: list[str] = list(BUILTIN_CORPUS.keys())

__all__ = [
    "BUILTIN_CORPUS",
    "BUILTIN_CORPUS_EXTRA",
    "LANGUAGE_EXTENSIONS",
    "TARGET_LANGUAGES",
]
