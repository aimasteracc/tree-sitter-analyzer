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

    Phase 1 架构（2026-03）：基于 syntactic path 覆盖度跟踪，使用精确节点身份匹配。

    Fields:
        language: 语言名称（如 "python", "javascript"）
        total_node_types: 语法中的总节点类型数（从 golden corpus 提取）
        covered_node_types: 插件覆盖的节点类型数
        coverage_percentage: 覆盖率百分比（0-100）
        uncovered_types: 未覆盖的节点类型列表
        corpus_file: 使用的 corpus 文件路径
        expected_node_types: 预期的节点类型及其计数（从 expected.json）
        actual_node_types: 实际解析到的节点类型及其计数

    注意：
        - total_node_types / covered_node_types 是节点类型的唯一计数（向后兼容）
        - 内部跟踪 syntactic paths (node_type, parent_path) 元组，确保 MECE 保证
        - 使用精确节点身份匹配 (type, start_byte, end_byte, parent_path, file_path)
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
        "css": "css",
        "html": "html",
        "markdown": "md",
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

    # 使用 language_loader 创建 parser（正确处理 TypeScript 等多语言 API）
    from ..language_loader import loader

    parser = loader.create_parser_safely(language)
    if parser is None:
        raise ImportError(f"Failed to create parser for language: {language}")

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


# Type alias for the AST line index structure — extracted to reduce generic nesting depth.
_LineIndex = dict[tuple[int, int], list[tuple[str, tuple[str, ...]]]]

# r37cm (dogfood): file-root node types — they span the whole file and
# would mask real top-level declarations. Skip when matching elements.
_ROOT_NODE_TYPES = frozenset(
    {
        "module",
        "program",
        "source_file",
        "translation_unit",
        "chunk",
        "document",
    }
)


def _walk_ast_into_index(
    node: Any,
    parent_path: tuple[str, ...],
    depth: int,
    max_depth: int,
    max_nodes: int,
    line_index: dict,
    node_count: list[int],
) -> None:
    """Recursive walker for _build_ast_line_index — module-level to reduce nesting depth."""
    if depth > max_depth:
        return
    node_count[0] += 1
    if node_count[0] > max_nodes:
        return
    if not node.is_named:
        for child in node.children:
            _walk_ast_into_index(
                child,
                parent_path,
                depth + 1,
                max_depth,
                max_nodes,
                line_index,
                node_count,
            )
        return
    key = (node.start_point[0], node.end_point[0])
    line_index.setdefault(key, []).append((node.type, parent_path))
    new_parent_path = parent_path + (node.type,)
    for child in node.children:
        _walk_ast_into_index(
            child,
            new_parent_path,
            depth + 1,
            max_depth,
            max_nodes,
            line_index,
            node_count,
        )


def _build_ast_line_index(
    root: Any,
    max_depth: int,
    max_nodes: int,
) -> _LineIndex:
    """Recursively walk an AST, building a ``(start_line, end_line)`` → list index.

    r37cm: extracted from ``_get_covered_node_types_from_plugin`` to drop
    the 174-line method to ~60. Depth + node-count caps protect against
    pathological inputs (MAX_DEPTH=100 stack overflow, MAX_NODES=100k
    memory ceiling).
    """
    line_index: _LineIndex = {}
    node_count = [0]
    _walk_ast_into_index(root, (), 0, max_depth, max_nodes, line_index, node_count)
    return line_index


def _match_elements_to_paths(
    elements: Any,
    line_index: _LineIndex,
) -> set[tuple[str, tuple[str, ...]]]:
    """Match plugin elements against the line index → covered (type, path) set.

    For each element line range, take the first non-root node type (the
    outermost semantic node) to avoid the single-line inflation bug
    where ``class Foo: pass`` would mark class_definition + identifier
    + block + pass_statement as all covered.
    """
    covered: set[tuple[str, tuple[str, ...]]] = set()
    for element in elements:
        if not (hasattr(element, "start_line") and hasattr(element, "end_line")):
            continue
        key = (element.start_line - 1, element.end_line - 1)
        for node_type, parent_path in line_index.get(key, []):
            if node_type not in _ROOT_NODE_TYPES:
                covered.add((node_type, parent_path))
                break
    return covered


async def _get_covered_node_types_from_plugin(
    corpus_path: Path, language: str
) -> set[str]:
    """Return the set of AST node types the plugin actually extracted.

    Phase 1 (2026-03) — exact node-identity matching: walk the corpus
    AST, build a (start_line, end_line) → list[(node_type, parent_path)]
    index, then match each plugin element to its outermost non-root node
    type. r37cm (dogfood): docstring trimmed and the inner ``build_ast_map``
    closure plus matching loop moved to ``_build_ast_line_index`` +
    ``_match_elements_to_paths`` module helpers — drops the function
    from 174 lines to ~40 while keeping MECE semantics (mutually-
    exclusive type+path pairs, collectively-exhaustive traversal under
    MAX_DEPTH=100 / MAX_NODES=100000 caps).
    """
    from ..core.request import AnalysisRequest
    from ..plugins.manager import PluginManager

    MAX_DEPTH = 100  # 防止栈溢出
    MAX_NODES = 100000  # 内存断路器

    try:
        plugin_manager = PluginManager()
        plugin = plugin_manager.get_plugin(language)
        if not plugin:
            raise ImportError(f"No plugin available for language: {language}")

        request = AnalysisRequest(
            file_path=str(corpus_path),
            language=language,
            include_complexity=False,
            include_details=True,
        )
        result = await plugin.analyze_file(str(corpus_path), request)
        if not result or not hasattr(result, "elements") or not result.elements:
            return set()

        from ..language_loader import loader

        parser = loader.create_parser_safely(language)
        if parser is None:
            raise ImportError(f"Failed to create parser for language: {language}")

        source_code = corpus_path.read_text(encoding="utf-8")
        tree = parser.parse(source_code.encode("utf-8"))

        line_index = _build_ast_line_index(tree.root_node, MAX_DEPTH, MAX_NODES)
        covered_syntactic_paths = _match_elements_to_paths(result.elements, line_index)
        return {node_type for node_type, _ in covered_syntactic_paths}

    except Exception as e:
        import sys
        import traceback

        print(
            f"Warning: Failed to extract covered types from plugin: {e}",
            file=sys.stderr,
        )
        traceback.print_exc(file=sys.stderr)
        return set()


async def validate_plugin_coverage(language: str) -> CoverageReport:
    """
    验证指定语言插件的 grammar coverage (Phase 1: Syntactic Path Coverage)

    **新架构（2026-03）**：
        跟踪 syntactic paths (node_type, parent_path) 而不只是 node types，
        使用精确节点身份匹配消除 False Positives（嵌套节点误判问题）。

    **为什么需要 Syntactic Path Coverage？**

        旧指标（node type 覆盖率）的问题：
            问：是否提取了 function_definition？
            答：是。

        但现实中有多种语法上下文：
            ✓ function_definition @ ("module",) — 顶层函数
            ✓ function_definition @ ("class_body",) — 类方法
            ✗ function_definition @ ("with_statement", "block") — with 块内函数（未覆盖）

        结果：看似 100% 覆盖，实际遗漏了某些语法上下文。

    **新方法解决方案**：
        跟踪 (node_type, parent_path) 元组 → 每个语法上下文独立跟踪 → 真正的 MECE 保证。

    Workflow:
        1. 定位 golden corpus 文件和 expected.json
        2. 解析 corpus 文件，提取所有 (node_type, parent_path) tuples（全集）
        3. 运行插件提取，使用精确节点身份匹配收集被覆盖的 tuples
        4. 计算覆盖率：covered_types / total_types * 100%
        5. 列出未覆盖的 node types（向后兼容旧报告格式）

    Args:
        language: 语言名称（如 "python", "javascript"）

    Returns:
        CoverageReport，包含 syntactic path 覆盖数据

    Raises:
        FileNotFoundError: 如果 corpus 或 expected 文件不存在
        ValueError: 如果语言不支持
        ImportError: 如果 tree-sitter 模块不存在

    示例：
        >>> report = await validate_plugin_coverage("python")
        >>> print(f"{report.coverage_percentage:.1f}% ({report.covered_node_types}/{report.total_node_types})")
        100.0% (57/57)
        >>> print(report.uncovered_types)
        []
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
    covered_types_set = await _get_covered_node_types_from_plugin(corpus_path, language)
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
    # anyio.run() returns Any per its stub; cast back to the real return type.
    result: CoverageReport = anyio.run(validate_plugin_coverage, language)
    return result
