#!/usr/bin/env python3
"""
Grammar Coverage Validator

验证 tree-sitter 语言插件对语法节点的覆盖度。
通过解析 golden corpus 文件，比较插件提取的元素与所有可能的节点类型。

Coverage Validation Logic:
1. 解析 golden corpus 文件（使用 tree-sitter 直接解析）
2. 提取所有 named node types 作为"全集"
3. 运行插件提取，收集被提取的 node types
4. 计算覆盖率：covered_types / total_types * 100%
5. 列出未覆盖的 node types

设计决策：
- 100% 覆盖阈值（无例外）
- 使用 golden corpus 而非语法定义（避免 grammar.json 解析复杂度）
- 异步 API（与 analyze_file 保持一致）
"""

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio


@dataclass
class CoverageReport:
    """
    Grammar coverage 报告数据结构

    Fields:
        language: 语言名称（如 "python", "javascript"）
        total_node_types: 语法中的总节点类型数（从 golden corpus 提取）
        covered_node_types: 插件覆盖的节点类型数
        coverage_percentage: 覆盖率百分比（0-100）
        uncovered_types: 未覆盖的节点类型列表
        corpus_file: 使用的 corpus 文件路径
        expected_node_types: 预期的节点类型及其计数（从 expected.json）
        actual_node_types: 实际解析到的节点类型及其计数
    """

    language: str
    total_node_types: int
    covered_node_types: int
    coverage_percentage: float
    uncovered_types: list[str]
    corpus_file: str
    expected_node_types: dict[str, int]
    actual_node_types: dict[str, int]


def _count_node_types(node: Any) -> Counter[str]:
    """
    递归统计树中所有命名节点类型的数量

    Args:
        node: tree-sitter Node 对象

    Returns:
        Counter 对象，映射 node type → count
    """
    counts: Counter[str] = Counter()
    if node.is_named:
        counts[node.type] += 1
    for child in node.children:
        counts.update(_count_node_types(child))
    return counts


def _get_tree_sitter_module(language: str) -> Any:
    """
    动态导入对应语言的 tree-sitter 模块

    Args:
        language: 语言名称

    Returns:
        tree-sitter 语言模块

    Raises:
        ImportError: 如果语言模块不存在
    """
    language_modules = {
        "python": "tree_sitter_python",
        "javascript": "tree_sitter_javascript",
        "typescript": "tree_sitter_typescript",
        "java": "tree_sitter_java",
        "c": "tree_sitter_c",
        "cpp": "tree_sitter_cpp",
        "go": "tree_sitter_go",
        "ruby": "tree_sitter_ruby",
        "rust": "tree_sitter_rust",
        "php": "tree_sitter_php",
        "kotlin": "tree_sitter_kotlin",
        "swift": "tree_sitter_swift",
        "scala": "tree_sitter_scala",
        "bash": "tree_sitter_bash",
        "yaml": "tree_sitter_yaml",
        "json": "tree_sitter_json",
        "sql": "tree_sitter_sql",
    }

    module_name = language_modules.get(language)
    if not module_name:
        raise ImportError(f"No tree-sitter module found for language: {language}")

    try:
        return __import__(module_name)
    except ImportError as e:
        raise ImportError(
            f"Failed to import {module_name} for language {language}: {e}"
        ) from e


def _get_language_extension(language: str) -> str:
    """
    获取语言对应的文件扩展名

    Args:
        language: 语言名称

    Returns:
        文件扩展名（不含点号）

    Raises:
        ValueError: 如果语言不支持
    """
    extensions = {
        "python": "py",
        "javascript": "js",
        "typescript": "ts",
        "java": "java",
        "c": "c",
        "cpp": "cpp",
        "go": "go",
        "ruby": "rb",
        "rust": "rs",
        "php": "php",
        "kotlin": "kt",
        "swift": "swift",
        "scala": "scala",
        "bash": "sh",
        "yaml": "yaml",
        "json": "json",
        "sql": "sql",
    }

    if language not in extensions:
        raise ValueError(f"Unsupported language: {language}")

    return extensions[language]


def _parse_corpus_file(corpus_path: Path, language: str) -> dict[str, int]:
    """
    使用 tree-sitter 解析 corpus 文件并统计节点类型

    Args:
        corpus_path: corpus 文件路径
        language: 语言名称

    Returns:
        Dictionary mapping node type → count

    Raises:
        FileNotFoundError: 如果 corpus 文件不存在
        ImportError: 如果语言模块不存在
    """
    if not corpus_path.exists():
        raise FileNotFoundError(f"Corpus file not found: {corpus_path}")

    # 导入 tree-sitter 和语言模块
    import tree_sitter

    ts_module = _get_tree_sitter_module(language)
    lang = tree_sitter.Language(ts_module.language())
    parser = tree_sitter.Parser(lang)

    # 解析文件
    source_code = corpus_path.read_text(encoding="utf-8")
    tree = parser.parse(source_code.encode("utf-8"))

    # 统计节点类型
    counts = _count_node_types(tree.root_node)
    return dict(counts)


def _load_expected_json(expected_path: Path) -> dict[str, Any]:
    """
    加载 corpus_*_expected.json 文件

    Args:
        expected_path: expected.json 文件路径

    Returns:
        解析后的 JSON 数据

    Raises:
        FileNotFoundError: 如果文件不存在
        json.JSONDecodeError: 如果 JSON 格式错误
    """
    if not expected_path.exists():
        raise FileNotFoundError(f"Expected file not found: {expected_path}")

    with open(expected_path, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
        return data


def _get_covered_node_types_from_plugin(
    corpus_path: Path, language: str
) -> set[str]:
    """
    通过运行插件提取，收集被覆盖的节点类型

    Args:
        corpus_path: corpus 文件路径
        language: 语言名称

    Returns:
        被插件覆盖的节点类型集合

    Note:
        此函数通过以下步骤实现：
        1. 调用 analyze_file(corpus_path) 获取提取的元素
        2. 收集所有元素的 node_type 字段
        3. 返回 node type 集合
    """
    from ..core.analysis_engine import AnalysisRequest
    from ..plugins.manager import PluginManager

    covered_types: set[str] = set()

    try:
        # 获取插件管理器和分析引擎
        plugin_manager = PluginManager()
        plugin = plugin_manager.get_plugin(language)

        if not plugin:
            raise ImportError(f"No plugin available for language: {language}")

        # 创建分析请求
        request = AnalysisRequest(
            file_path=str(corpus_path),
            language=language,
            include_complexity=False,
            include_details=True,
        )

        # 同步调用异步的 analyze_file 方法
        result = anyio.run(plugin.analyze_file, str(corpus_path), request)

        # 收集所有元素的 node_type 字段
        if result and hasattr(result, "elements"):
            for element in result.elements:
                if hasattr(element, "node_type") and element.node_type:
                    covered_types.add(element.node_type)

    except Exception as e:
        # 记录错误但不中断流程，返回空集
        import sys

        print(
            f"Warning: Failed to extract covered types from plugin: {e}",
            file=sys.stderr,
        )

    return covered_types


async def validate_plugin_coverage(language: str) -> CoverageReport:
    """
    验证指定语言插件的 grammar coverage

    Workflow:
    1. 定位 golden corpus 文件和 expected.json
    2. 解析 corpus 文件，提取所有 node types（全集）
    3. 运行插件提取，收集被覆盖的 node types
    4. 计算覆盖率并生成报告

    Args:
        language: 语言名称（如 "python", "javascript"）

    Returns:
        CoverageReport 包含覆盖率数据

    Raises:
        FileNotFoundError: 如果 corpus 或 expected 文件不存在
        ValueError: 如果语言不支持
        ImportError: 如果 tree-sitter 模块不存在
    """
    # 定位文件
    project_root = Path(__file__).parent.parent.parent
    golden_dir = project_root / "tests" / "golden"

    ext = _get_language_extension(language)
    corpus_path = golden_dir / f"corpus_{language}.{ext}"
    expected_path = golden_dir / f"corpus_{language}_expected.json"

    # 解析 corpus 文件（全集）
    actual_node_types = _parse_corpus_file(corpus_path, language)
    total_types = len(actual_node_types)

    # 加载 expected.json（用于验证）
    expected_data = _load_expected_json(expected_path)
    expected_node_types = expected_data.get("node_types", {})

    # 获取插件覆盖的 node types
    # TODO: Phase 1.2 - 实现插件覆盖检测
    covered_types_set = _get_covered_node_types_from_plugin(corpus_path, language)
    covered_count = len(covered_types_set)

    # 计算未覆盖的类型
    all_types_set = set(actual_node_types.keys())
    uncovered_types = sorted(all_types_set - covered_types_set)

    # 计算覆盖率
    coverage_percentage = (
        (covered_count / total_types * 100.0) if total_types > 0 else 0.0
    )

    return CoverageReport(
        language=language,
        total_node_types=total_types,
        covered_node_types=covered_count,
        coverage_percentage=coverage_percentage,
        uncovered_types=uncovered_types,
        corpus_file=str(corpus_path),
        expected_node_types=expected_node_types,
        actual_node_types=actual_node_types,
    )


def generate_coverage_report(report: CoverageReport) -> str:
    """
    生成人类可读的覆盖度报告

    Format:
        Python: 95.7% (44/46 node types covered)

        Uncovered node types (2):
        - async_for_statement
        - match_statement

    Args:
        report: CoverageReport 对象

    Returns:
        格式化的覆盖度报告字符串
    """
    lines = []

    # Header
    language_title = report.language.capitalize()
    coverage_summary = (
        f"{language_title}: {report.coverage_percentage:.1f}% "
        f"({report.covered_node_types}/{report.total_node_types} node types covered)"
    )
    lines.append(coverage_summary)

    # Uncovered types section
    if report.uncovered_types:
        lines.append("")
        lines.append(f"Uncovered node types ({len(report.uncovered_types)}):")
        for node_type in report.uncovered_types:
            lines.append(f"- {node_type}")
    else:
        lines.append("")
        lines.append("All node types covered!")

    # Corpus file info
    lines.append("")
    lines.append(f"Corpus file: {report.corpus_file}")

    return "\n".join(lines)


def check_coverage_threshold(
    coverage_percentage: float, threshold: float = 100.0
) -> bool:
    """
    检查覆盖率是否达到阈值（用于 CI 集成）

    Args:
        coverage_percentage: 实际覆盖率（0-100）
        threshold: 要求的最低覆盖率（默认 100.0）

    Returns:
        True 如果达标，False 如果未达标
    """
    return coverage_percentage >= threshold


# Synchronous wrappers for testing convenience
def validate_plugin_coverage_sync(language: str) -> CoverageReport:
    """同步版本的 validate_plugin_coverage（用于测试）"""
    return anyio.run(validate_plugin_coverage, language)
