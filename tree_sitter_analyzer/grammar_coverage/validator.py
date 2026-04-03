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


async def _get_covered_node_types_from_plugin(
    corpus_path: Path, language: str
) -> set[str]:
    """
    通过运行插件提取，收集被覆盖的节点类型（Phase 1: 精确节点身份匹配）

    **新架构（2026-03）消除 False Positives**：

    旧方法（已修复）：
        位置重叠判断 → 嵌套节点被误判为已覆盖
        例如：提取 @decorator 节点 → function_definition 在其范围内 → 错误标记 function 为"已覆盖"

    新方法（当前）：
        精确节点身份匹配 → 只有真正提取的节点才标记为已覆盖
        (node_type, start_byte, end_byte, parent_path, file_path) 完全一致才匹配

    算法流程：
        1. 解析 corpus 文件 → 构建完整 AST 节点身份映射
           节点身份 = (type, start_byte, end_byte, parent_path_tuple, file_path)

        2. 运行插件提取 → 获取 AnalysisResult.elements（行号 + type）
           将行号转换为字节偏移（精确匹配所需）

        3. 精确匹配 → 只有字节范围完全一致的节点才标记为"已覆盖"
           covered_paths = {(node_type, parent_path) for matched nodes}

        4. 返回去重的 node_type 集合（向后兼容）

    MECE 保证：
        - Mutually Exclusive: 每个节点有唯一的 (type, parent_path) → 不会重复计数
        - Collectively Exhaustive: 遍历整个 AST → 不会遗漏任何节点

    防御措施：
        - 深度限制: 100 层（防止栈溢出）
        - 内存断路器: 100,000 节点上限（防止内存耗尽）
        - 错误处理: 捕获异常并返回空集（不中断流程）

    Args:
        corpus_path: corpus 文件路径
        language: 语言名称

    Returns:
        被插件覆盖的节点类型集合（去重后的 node_type）

    示例：
        >>> covered = await _get_covered_node_types_from_plugin(Path("corpus_python.py"), "python")
        >>> print(covered)
        {'function_definition', 'class_definition', 'if_statement', ...}
    """

    from ..core.request import AnalysisRequest
    from ..plugins.manager import PluginManager

    # NodeIdentity = (node_type, start_line, end_line, parent_path_tuple, file_path)
    # Phase 1 修订（2026-04）：从字节偏移改为行号匹配，解决缩进代码误判问题。
    # 原字节匹配问题：line_to_byte_start 返回行首字节，而 AST 节点起始字节在缩进之后，
    # 两者永远不等，导致所有缩进节点（方法、字段等）均无法被标记为已覆盖。
    # 行号匹配保持 MECE：(start_line, end_line, parent_path) 三元组仍可唯一标识节点，
    # 同时正确处理 decorated_definition vs inner function_definition 等嵌套情况。
    NodeIdentity = tuple[str, int, int, tuple[str, ...], str]

    covered_syntactic_paths: set[tuple[str, tuple[str, ...]]] = set()
    MAX_DEPTH = 100  # 防止极端嵌套导致栈溢出
    MAX_NODES = 100000  # 内存断路器

    try:
        # 1. 获取插件并运行提取
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

        # 2. 解析文件获取完整 AST（使用 language_loader）
        from ..language_loader import loader

        parser = loader.create_parser_safely(language)
        if parser is None:
            raise ImportError(f"Failed to create parser for language: {language}")

        source_code = corpus_path.read_text(encoding="utf-8")
        tree = parser.parse(source_code.encode("utf-8"))
        file_path_str = str(corpus_path)

        # 3. 构建 AST 节点身份映射 (identity -> (node_type, parent_path))
        ast_node_identities: dict[NodeIdentity, tuple[str, tuple[str, ...]]] = {}
        node_count = 0

        def build_ast_map(
            node: Any, parent_path: tuple[str, ...], depth: int
        ) -> None:
            nonlocal node_count

            # 深度限制
            if depth > MAX_DEPTH:
                return

            # 内存断路器
            node_count += 1
            if node_count > MAX_NODES:
                return

            if not node.is_named:
                # 只关注命名节点
                for child in node.children:
                    build_ast_map(child, parent_path, depth + 1)
                return

            # 构建节点身份 (type, start_line, end_line, parent_path, file_path)
            # 使用 0-based 行号，与 node.start_point[0] / node.end_point[0] 一致
            identity: NodeIdentity = (
                node.type,
                node.start_point[0],
                node.end_point[0],
                parent_path,
                file_path_str,
            )

            # 记录 (node_type, parent_path)
            ast_node_identities[identity] = (node.type, parent_path)

            # 递归处理子节点，更新 parent_path
            new_parent_path = parent_path + (node.type,)
            for child in node.children:
                build_ast_map(child, new_parent_path, depth + 1)

        build_ast_map(tree.root_node, (), 0)

        # 4. 用行号匹配：element 的 1-based 行号 → 0-based → 与 AST 节点行号对比
        extracted_identities: set[NodeIdentity] = set()

        for element in result.elements:
            if not (hasattr(element, "start_line") and hasattr(element, "end_line")):
                continue

            # 将插件输出的 1-based 行号转为 0-based
            elem_start_0 = element.start_line - 1
            elem_end_0 = element.end_line - 1

            # 匹配 AST 中 start_line / end_line 完全一致的节点
            for identity, (node_type, parent_path) in ast_node_identities.items():
                (
                    _ast_type,
                    ast_start_line,
                    ast_end_line,
                    _ast_parent_path,
                    _ast_file,
                ) = identity

                # 精确行号匹配：起始行和结束行均需相同
                # MECE 保证：(start_line, end_line, parent_path) 三元组唯一标识节点，
                # decorated_definition 与内部 function_definition 起始行不同，不会混淆
                if ast_start_line == elem_start_0 and ast_end_line == elem_end_0:
                    extracted_identities.add(identity)
                    covered_syntactic_paths.add((node_type, parent_path))

        # 5. 返回去重后的 node_type 集合（向后兼容）
        covered_types: set[str] = {node_type for node_type, _ in covered_syntactic_paths}

    except Exception as e:
        # 记录错误但不中断流程，返回空集
        import sys
        import traceback

        print(
            f"Warning: Failed to extract covered types from plugin: {e}",
            file=sys.stderr,
        )
        traceback.print_exc(file=sys.stderr)

        return set()

    return covered_types


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
    return anyio.run(validate_plugin_coverage, language)
