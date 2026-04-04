"""Phase 3 Auto-Discovery Engine.

通过 tree-sitter 运行时反射 API 自动发现所有语法节点，彻底告别手工维护。

核心能力：
1. Grammar 内省  — 无需 grammar.json，通过 Language API 枚举所有节点类型
2. Wrapper 节点检测 — 多特征评分，识别装饰器/注解包裹型节点
3. 语法路径枚举 — BFS 遍历 AST，发现节点类型组合
4. 覆盖率缺口分析 — 对比 grammar 全量 vs corpus 中实际出现的节点

设计原则：
- 复用 language_loader 统一加载语言（处理 TypeScript 特殊情况、缓存等）
- 复用 introspector.get_all_node_types 枚举 named node types
- 优雅降级：语言不可用时跳过而不崩溃
- 类型安全：严格类型注解，通过 mypy strict
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ..utils import log_debug, log_error, log_warning
from .discovery_corpus import BUILTIN_CORPUS, BUILTIN_CORPUS_EXTRA, TARGET_LANGUAGES
from .introspector import get_all_node_types


@dataclass
class NodeStats:
    """单个节点类型的结构统计信息."""

    node_type: str
    samples: int = 0
    total_children: int = 0
    child_types: dict[str, int] = field(default_factory=dict)
    parent_types: dict[str, int] = field(default_factory=dict)
    field_usage: dict[str, int] = field(default_factory=dict)

    @property
    def avg_children(self) -> float:
        if self.samples == 0:
            return 0.0
        return self.total_children / self.samples


@dataclass
class WrapperCandidate:
    """Wrapper 节点候选项及其置信度评分."""

    node_type: str
    score: float
    reasons: list[str]
    stats: NodeStats


@dataclass
class CoverageGapReport:
    """单个语言的覆盖率缺口分析结果."""

    language: str
    total_node_types: int
    discovered_node_types: list[str]
    missing_node_types: list[str]
    wrapper_candidates: list[WrapperCandidate]
    coverage_rate: float
    elapsed_ms: float
    error: str | None = None

    @property
    def is_ok(self) -> bool:
        return self.error is None


# Wrapper 检测使用的字段名（覆盖多种语言的装饰性字段）
_WRAPPER_FIELDS = (
    "definition",
    "decorator",
    "attribute",
    "annotation",
    "body",
    "expression",
)

# Wrapper 名称模式（辅助加分，不作为主要判据）
_WRAPPER_NAME_PATTERNS = (
    "decorated",
    "annotated",
    "attributed",
    "modified",
    "with_clause",
)


def _collect_node_stats(
    language: str,
    corpus_code: str,
) -> dict[str, NodeStats]:
    """解析 corpus 代码，统计每种节点类型的结构特征.

    Args:
        language: 语言名称
        corpus_code: 源代码字符串

    Returns:
        {node_type: NodeStats}，未出现则为空字典
    """
    try:
        import tree_sitter

        from ..language_loader import loader

        lang_obj = loader.load_language(language)
        if lang_obj is None:
            log_warning(f"Cannot load language '{language}' for structural analysis")
            return {}

        parser = loader.create_parser_safely(language)
        if parser is None:
            log_warning(f"Cannot create parser for '{language}'")
            return {}

        tree = parser.parse(corpus_code.encode("utf-8"))

        stats_map: dict[str, NodeStats] = defaultdict(
            lambda: NodeStats(node_type="")
        )

        def traverse(
            node: tree_sitter.Node,
            parent_type: str | None,
        ) -> None:
            if not node.is_named:
                for child in node.children:
                    traverse(child, parent_type)
                return

            ns = stats_map[node.type]
            if ns.node_type == "":
                ns.node_type = node.type

            ns.samples += 1
            named_children = [c for c in node.children if c.is_named]
            ns.total_children += len(named_children)

            if parent_type:
                ns.parent_types[parent_type] = (
                    ns.parent_types.get(parent_type, 0) + 1
                )

            for child in named_children:
                ns.child_types[child.type] = (
                    ns.child_types.get(child.type, 0) + 1
                )

            # 记录字段使用情况
            for field_name in _WRAPPER_FIELDS:
                try:
                    field_id = lang_obj.field_id_for_name(field_name)
                    if field_id is not None:
                        field_nodes = node.children_by_field_id(field_id)
                        if field_nodes:
                            ns.field_usage[field_name] = (
                                ns.field_usage.get(field_name, 0)
                                + len(field_nodes)
                            )
                except Exception:
                    pass

            for child in node.children:
                traverse(child, node.type)

        traverse(tree.root_node, None)

        # 解析额外的字节级 corpus（如 Python 2 遗留语法）
        for extra_bytes in BUILTIN_CORPUS_EXTRA.get(language, []):
            extra_tree = parser.parse(extra_bytes)
            traverse(extra_tree.root_node, None)

        # 清理 defaultdict lambda 残留的空字符串 node_type
        result: dict[str, NodeStats] = {}
        for k, v in stats_map.items():
            v.node_type = k
            result[k] = v
        return result

    except Exception as e:
        log_error(f"Failed to collect node stats for '{language}': {e}")
        return {}


def _score_wrapper_node(
    node_type: str,
    stats: NodeStats,
) -> tuple[float, list[str]]:
    """计算 wrapper 节点置信度评分.

    评分规则（满分 100）：
    - 使用 definition/decorator/annotation/attribute 字段 → +30
    - 使用 decorator/annotation/attribute 字段（装饰性） → +30（可叠加）
    - 子节点类型种数 >= 2 → +20
    - 平均子节点数 >= 2 → +10
    - 名称模式匹配 → +10

    Returns:
        (score, reasons)
    """
    score: float = 0.0
    reasons: list[str] = []

    has_def_field = (
        stats.field_usage.get("definition", 0) > 0
        or stats.field_usage.get("body", 0) > 0
    )
    has_deco_field = (
        stats.field_usage.get("decorator", 0) > 0
        or stats.field_usage.get("annotation", 0) > 0
        or stats.field_usage.get("attribute", 0) > 0
    )

    if has_def_field:
        score += 30.0
        reasons.append("definition_field")

    if has_deco_field:
        score += 30.0
        reasons.append("decorator_field")

    if len(stats.child_types) >= 2:
        score += 20.0
        reasons.append(f"child_diversity({len(stats.child_types)})")

    if stats.avg_children >= 2.0:
        score += 10.0
        reasons.append(f"avg_children({stats.avg_children:.1f})")

    if any(pat in node_type for pat in _WRAPPER_NAME_PATTERNS):
        score += 10.0
        reasons.append("name_pattern")

    return score, reasons


class AutoDiscoveryEngine:
    """Phase 3 Auto-Discovery Engine.

    无需 grammar.json，通过 tree-sitter 运行时 API 自动发现语法节点。

    Example:
        engine = AutoDiscoveryEngine()
        report = engine.analyze_coverage_gap("python")
        print(f"Coverage: {report.coverage_rate:.1f}%")
        print(f"Missing: {report.missing_node_types}")

        all_reports = engine.analyze_all_languages()
        print(engine.generate_report(all_reports))
    """

    def __init__(self, wrapper_threshold: float = 30.0) -> None:
        """初始化引擎.

        Args:
            wrapper_threshold: Wrapper 节点置信度阈值（0-100），默认 30.0
        """
        self.wrapper_threshold = wrapper_threshold

    def get_all_node_types(self, language: str) -> list[str]:
        """通过 Language API 枚举所有 named node 类型.

        Args:
            language: 语言名称（如 "python", "typescript"）

        Returns:
            按字母排序的 named node 类型列表

        Raises:
            ValueError: 如果语言不受支持
            ImportError: 如果语言包未安装
        """
        return get_all_node_types(language)

    def get_all_field_names(self, language: str) -> list[str]:
        """通过 Language API 枚举所有字段名称.

        Args:
            language: 语言名称

        Returns:
            字段名称列表，字母排序；语言不可用时返回空列表
        """
        try:
            from ..language_loader import loader

            lang_obj = loader.load_language(language)
            if lang_obj is None:
                return []

            names: list[str] = []
            for i in range(lang_obj.field_count):
                try:
                    name = lang_obj.field_name_for_id(i)
                    if name:
                        names.append(name)
                except Exception:
                    pass
            return sorted(set(names))
        except Exception as e:
            log_error(f"Failed to get field names for '{language}': {e}")
            return []

    def detect_wrapper_nodes(
        self,
        language: str,
        corpus_code: str,
    ) -> list[WrapperCandidate]:
        """基于结构特征检测 Wrapper 节点.

        Args:
            language: 语言名称
            corpus_code: 用于分析的源代码

        Returns:
            按置信度降序排列的 WrapperCandidate 列表
        """
        stats_map = _collect_node_stats(language, corpus_code)
        candidates: list[WrapperCandidate] = []

        for node_type, stats in stats_map.items():
            score, reasons = _score_wrapper_node(node_type, stats)
            if score >= self.wrapper_threshold:
                candidates.append(
                    WrapperCandidate(
                        node_type=node_type,
                        score=score,
                        reasons=reasons,
                        stats=stats,
                    )
                )

        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def enumerate_syntax_paths(
        self,
        language: str,
        corpus_code: str,
        max_depth: int = 3,
    ) -> list[str]:
        """BFS 遍历 AST，枚举所有唯一节点类型路径.

        Args:
            language: 语言名称
            corpus_code: 源代码
            max_depth: 最大遍历深度

        Returns:
            路径字符串列表，格式 "parent > child"，按出现频率降序
        """
        try:
            import tree_sitter

            from ..language_loader import loader

            parser = loader.create_parser_safely(language)
            if parser is None:
                return []

            tree = parser.parse(corpus_code.encode("utf-8"))
            path_counts: Counter[str] = Counter()

            def traverse(
                node: tree_sitter.Node,
                parent_path: tuple[str, ...],
            ) -> None:
                if len(parent_path) > max_depth:
                    return

                if node.is_named and parent_path:
                    path_str = " > ".join(parent_path[-1:]) + " > " + node.type
                    path_counts[path_str] += 1

                new_path = (
                    parent_path + (node.type,) if node.is_named else parent_path
                )
                for child in node.children:
                    traverse(child, new_path)

            traverse(tree.root_node, ())
            return [p for p, _ in path_counts.most_common()]

        except Exception as e:
            log_error(f"Failed to enumerate paths for '{language}': {e}")
            return []

    def analyze_coverage_gap(
        self,
        language: str,
        corpus_code: str | None = None,
    ) -> CoverageGapReport:
        """分析 grammar 全量节点 vs corpus 中实际出现节点的覆盖差距.

        Args:
            language: 语言名称
            corpus_code: 自定义代码；为 None 时使用内置 corpus

        Returns:
            CoverageGapReport 实例
        """
        start = time.perf_counter()

        if corpus_code is None:
            corpus_code = BUILTIN_CORPUS.get(language, "")

        empty_report = CoverageGapReport(
            language=language,
            total_node_types=0,
            discovered_node_types=[],
            missing_node_types=[],
            wrapper_candidates=[],
            coverage_rate=0.0,
            elapsed_ms=0.0,
        )

        # 获取语法定义的全量 named node types
        try:
            all_types = self.get_all_node_types(language)
        except (ValueError, ImportError) as e:
            log_warning(f"Skipping '{language}': {e}")
            elapsed = (time.perf_counter() - start) * 1000
            empty_report.error = str(e)
            empty_report.elapsed_ms = elapsed
            return empty_report

        if not corpus_code:
            log_warning(f"No corpus code for '{language}', skipping discovery")
            elapsed = (time.perf_counter() - start) * 1000
            empty_report.total_node_types = len(all_types)
            empty_report.missing_node_types = list(all_types)
            empty_report.elapsed_ms = elapsed
            return empty_report

        # 解析 corpus，统计出现的节点类型
        stats_map = _collect_node_stats(language, corpus_code)
        discovered = sorted(stats_map.keys())

        all_types_set = set(all_types)
        discovered_set = set(discovered)
        missing = sorted(all_types_set - discovered_set)

        coverage = (
            len(discovered_set & all_types_set) / len(all_types_set) * 100
            if all_types_set
            else 0.0
        )

        # 检测 wrapper 节点
        wrappers = self.detect_wrapper_nodes(language, corpus_code)

        elapsed = (time.perf_counter() - start) * 1000
        log_debug(
            f"[{language}] {len(discovered)}/{len(all_types)} types discovered "
            f"({coverage:.1f}%) in {elapsed:.1f}ms"
        )

        return CoverageGapReport(
            language=language,
            total_node_types=len(all_types),
            discovered_node_types=discovered,
            missing_node_types=missing,
            wrapper_candidates=wrappers,
            coverage_rate=coverage,
            elapsed_ms=elapsed,
        )

    def analyze_all_languages(
        self,
        languages: list[str] | None = None,
    ) -> dict[str, CoverageGapReport]:
        """对所有目标语言运行覆盖率缺口分析.

        Args:
            languages: 指定语言列表；为 None 时使用所有内置 corpus 语言

        Returns:
            {language: CoverageGapReport}
        """
        target = languages if languages is not None else TARGET_LANGUAGES
        results: dict[str, CoverageGapReport] = {}

        for lang in target:
            results[lang] = self.analyze_coverage_gap(lang)

        return results

    def generate_report(
        self,
        results: dict[str, CoverageGapReport],
    ) -> str:
        """生成 Markdown 格式的覆盖率报告.

        Args:
            results: analyze_all_languages() 的返回值

        Returns:
            Markdown 字符串
        """
        lines: list[str] = [
            "# Phase 3 Auto-Discovery Report",
            "",
            "## Summary",
            "",
            "| Language | Total Types | Discovered | Coverage | Wrappers | Status |",
            "|----------|-------------|------------|----------|----------|--------|",
        ]

        total_types = 0
        total_discovered = 0

        for lang, report in sorted(results.items()):
            if not report.is_ok:
                lines.append(
                    f"| {lang} | — | — | — | — | ❌ {report.error} |"
                )
                continue

            # Use coverage_rate to back-calculate discovered count in grammar
            discovered_in_grammar = round(
                report.coverage_rate / 100 * report.total_node_types
            )
            wrapper_count = len(report.wrapper_candidates)
            status = "✅" if report.coverage_rate >= 80 else "⚠️"

            lines.append(
                f"| {lang} "
                f"| {report.total_node_types} "
                f"| {discovered_in_grammar} "
                f"| {report.coverage_rate:.1f}% "
                f"| {wrapper_count} "
                f"| {status} |"
            )
            total_types += report.total_node_types
            total_discovered += discovered_in_grammar

        overall = total_discovered / total_types * 100 if total_types else 0
        lines += [
            "",
            f"**Total**: {total_discovered}/{total_types} types discovered "
            f"({overall:.1f}% overall coverage)",
            "",
        ]

        # 每语言详情
        lines += ["## Details", ""]
        for lang, report in sorted(results.items()):
            if not report.is_ok:
                continue
            lines += [
                f"### {lang}",
                "",
                f"- **Node types in grammar**: {report.total_node_types}",
                f"- **Discovered in corpus**: {len(report.discovered_node_types)}",
                f"- **Coverage**: {report.coverage_rate:.1f}%",
                f"- **Analysis time**: {report.elapsed_ms:.1f}ms",
                "",
            ]

            if report.wrapper_candidates:
                lines.append("**Wrapper node candidates:**")
                for wc in report.wrapper_candidates[:5]:
                    lines.append(
                        f"- `{wc.node_type}` (score={wc.score:.0f}, "
                        f"reasons: {', '.join(wc.reasons)})"
                    )
                lines.append("")

            if report.missing_node_types:
                lines.append(
                    f"**Missing from corpus** "
                    f"({len(report.missing_node_types)} types):"
                )
                shown = report.missing_node_types[:10]
                lines.append(
                    "```\n" + "\n".join(shown)
                    + ("\n..." if len(report.missing_node_types) > 10 else "")
                    + "\n```"
                )
                lines.append("")

        return "\n".join(lines)
