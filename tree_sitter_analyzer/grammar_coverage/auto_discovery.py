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
from typing import Any

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
# 注意："body" 被移除——几乎所有复合语句（for/if/while/with/try）都有 body 字段，
# 保留会导致近 100% 误报率，使 wrapper 检测结果无意义。
_WRAPPER_FIELDS = (
    "definition",
    "decorator",
    "attribute",
    "annotation",
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

    r37bh (dogfood): originally 101 行 inline (含 traverse closure +
    field-usage scan)。Refactor 把 traverse 提到 module-level
    (_collect_stats_walk), 把 field-usage 提到 _record_field_usage,
    并新增 _load_language_objects 集中校验。函数本体 ~25 行。
    """
    try:
        lang_obj, parser = _load_language_objects(language)
        if lang_obj is None or parser is None:
            return {}

        stats_map: dict[str, NodeStats] = defaultdict(lambda: NodeStats(node_type=""))

        tree = parser.parse(corpus_code.encode("utf-8"))
        _collect_stats_walk(tree.root_node, None, stats_map, lang_obj)

        # 解析额外的字节级 corpus (如 Python 2 遗留语法)
        for extra_bytes in BUILTIN_CORPUS_EXTRA.get(language, []):
            extra_tree = parser.parse(extra_bytes)
            _collect_stats_walk(extra_tree.root_node, None, stats_map, lang_obj)

        # 清理 defaultdict lambda 残留的空字符串 node_type
        result: dict[str, NodeStats] = {}
        for k, v in stats_map.items():
            v.node_type = k
            result[k] = v
        return result

    except Exception as e:
        log_error(f"Failed to collect node stats for '{language}': {e}")
        return {}


def _load_language_objects(language: str) -> tuple[Any | None, Any | None]:
    """Return (lang_obj, parser) for ``language``, both may be ``None``."""
    from ..language_loader import loader

    lang_obj = loader.load_language(language)
    if lang_obj is None:
        log_warning(f"Cannot load language '{language}' for structural analysis")
        return None, None
    parser = loader.create_parser_safely(language)
    if parser is None:
        log_warning(f"Cannot create parser for '{language}'")
        return lang_obj, None
    return lang_obj, parser


def _collect_stats_walk(
    node: Any,
    parent_type: str | None,
    stats_map: dict[str, NodeStats],
    lang_obj: Any,
) -> None:
    """Recursive walker — updates ``stats_map`` in place.

    r37bh: extracted from ``_collect_node_stats`` closure so the parent
    function reads as a linear setup-walk-cleanup pipeline.
    """
    if not node.is_named:
        for child in node.children:
            _collect_stats_walk(child, parent_type, stats_map, lang_obj)
        return

    ns = stats_map[node.type]
    if ns.node_type == "":
        ns.node_type = node.type

    ns.samples += 1
    named_children = [c for c in node.children if c.is_named]
    ns.total_children += len(named_children)

    if parent_type:
        ns.parent_types[parent_type] = ns.parent_types.get(parent_type, 0) + 1

    for child in named_children:
        ns.child_types[child.type] = ns.child_types.get(child.type, 0) + 1

    _record_field_usage(node, ns, lang_obj)

    for child in node.children:
        _collect_stats_walk(child, node.type, stats_map, lang_obj)


def _record_field_usage(node: Any, ns: NodeStats, lang_obj: Any) -> None:
    """Tally tree-sitter field usage (``_WRAPPER_FIELDS``) on a single node."""
    for field_name in _WRAPPER_FIELDS:
        try:
            field_id = lang_obj.field_id_for_name(field_name)
        except Exception:  # nosec B112 — best-effort field lookup; tree-sitter language
            # objects may raise on missing fields per grammar; we treat any failure as
            # "this field doesn't exist in this language" and move on.
            continue
        if field_id is None:
            continue
        field_nodes = node.children_by_field_id(field_id)
        if not field_nodes:
            continue
        ns.field_usage[field_name] = ns.field_usage.get(field_name, 0) + len(
            field_nodes
        )


def _empty_gap_report(language: str) -> CoverageGapReport:
    """Build a zeroed ``CoverageGapReport`` ready for in-place edits.

    Used by ``analyze_coverage_gap`` as the canvas for both error paths
    (grammar load failure, missing corpus) so the report shape is
    consistent across early returns.
    """
    return CoverageGapReport(
        language=language,
        total_node_types=0,
        discovered_node_types=[],
        missing_node_types=[],
        wrapper_candidates=[],
        coverage_rate=0.0,
        elapsed_ms=0.0,
    )


def _no_corpus_report(
    empty_report: CoverageGapReport,
    all_types: list[str],
    start: float,
) -> CoverageGapReport:
    """Populate ``empty_report`` for the "grammar loaded, corpus missing" branch."""
    log_warning(f"No corpus code for '{empty_report.language}', skipping discovery")
    empty_report.total_node_types = len(all_types)
    empty_report.missing_node_types = list(all_types)
    empty_report.elapsed_ms = (time.perf_counter() - start) * 1000
    return empty_report


def _append_wrapper_lines(
    lines: list[str], wrapper_candidates: list[WrapperCandidate]
) -> None:
    """Append the ``**Wrapper node candidates:**`` block (top-5) to ``lines``.

    No-op when ``wrapper_candidates`` is empty (the report section is
    optional). Each candidate shows ``- `node_type` (score=N, reasons:
    a, b, c)`` followed by a trailing blank line.

    r37dy (dogfood): lifted from ``generate_report`` to flatten the
    if/for/append chain from depth 6 to 4.
    """
    if not wrapper_candidates:
        return
    lines.append("**Wrapper node candidates:**")
    for wc in wrapper_candidates[:5]:
        lines.append(
            f"- `{wc.node_type}` (score={wc.score:.0f}, "
            f"reasons: {', '.join(wc.reasons)})"
        )
    lines.append("")


def _append_summary_rows(
    lines: list[str], results: dict[str, CoverageGapReport]
) -> tuple[int, int]:
    """Append summary-table rows to ``lines``; return ``(total_types, total_discovered)``.

    OK reports contribute to the totals via ``coverage_rate``-based
    back-calculation. Failed reports emit a single error row with em-dash
    placeholders so the table still tabulates the failure.

    r37eg (dogfood): lifted from ``generate_report`` to keep the main body
    a thin orchestrator.
    """
    total_types = 0
    total_discovered = 0
    for lang, report in sorted(results.items()):
        if not report.is_ok:
            lines.append(f"| {lang} | — | — | — | — | ❌ {report.error} |")
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
    return total_types, total_discovered


def _overall_totals_lines(total_discovered: int, total_types: int) -> list[str]:
    """Build the ``**Total**: discovered/total (X.X% overall coverage)`` line."""
    overall = total_discovered / total_types * 100 if total_types else 0
    return [
        "",
        f"**Total**: {total_discovered}/{total_types} types discovered "
        f"({overall:.1f}% overall coverage)",
        "",
    ]


def _append_language_detail(
    lines: list[str], lang: str, report: CoverageGapReport
) -> None:
    """Append the per-language ``### <lang>`` Markdown section.

    Caller is responsible for filtering failed reports (``report.is_ok``)
    before calling.
    """
    lines += [
        f"### {lang}",
        "",
        f"- **Node types in grammar**: {report.total_node_types}",
        f"- **Discovered in corpus**: {len(report.discovered_node_types)}",
        f"- **Coverage**: {report.coverage_rate:.1f}%",
        f"- **Analysis time**: {report.elapsed_ms:.1f}ms",
        "",
    ]
    # r37dy (dogfood): flatten nesting 6 → 4 via _append_wrapper_lines.
    _append_wrapper_lines(lines, report.wrapper_candidates)
    if report.missing_node_types:
        lines.append(
            f"**Missing from corpus** ({len(report.missing_node_types)} types):"
        )
        shown = report.missing_node_types[:10]
        lines.append(
            "```\n"
            + "\n".join(shown)
            + ("\n..." if len(report.missing_node_types) > 10 else "")
            + "\n```"
        )
        lines.append("")


def _safe_field_name_for_id(lang_obj: Any, field_id: int) -> str | None:
    """Return ``lang_obj.field_name_for_id(i)`` or None on lookup error.

    r37dq (dogfood): newer tree-sitter releases drop fields for some
    grammar IDs; this swallow-and-skip helper lets the caller iterate
    by index without nesting a try/except inside the loop body.
    """
    try:
        name = lang_obj.field_name_for_id(field_id)
        return name if name else None
    except Exception:  # nosec B110 — non-fatal, skip silently.
        return None


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
        # r37dq (dogfood): flattened nesting 6 → 3 via _collect_field_name helper.
        try:
            from ..language_loader import loader

            lang_obj = loader.load_language(language)
            if lang_obj is None:
                return []
            names: list[str] = []
            for i in range(lang_obj.field_count):
                name = _safe_field_name_for_id(lang_obj, i)
                if name:
                    names.append(name)
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
        # r37dq (dogfood): flattened nesting 6 → 4 via early-continue.
        stats_map = _collect_node_stats(language, corpus_code)
        candidates: list[WrapperCandidate] = []
        for node_type, stats in stats_map.items():
            score, reasons = _score_wrapper_node(node_type, stats)
            if score < self.wrapper_threshold:
                continue
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
                    path_str = parent_path[-1] + " > " + node.type
                    path_counts[path_str] += 1

                new_path = parent_path + (node.type,) if node.is_named else parent_path
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

        r37eh (dogfood): 79 → ~20 lines. ``_empty_gap_report`` builds the
        zeroed report; ``_load_node_types_or_empty`` handles the grammar
        load + error path; ``_no_corpus_report`` and
        ``_compute_corpus_coverage`` own the no-corpus / with-corpus paths.
        """
        start = time.perf_counter()
        if corpus_code is None:
            corpus_code = BUILTIN_CORPUS.get(language, "")

        empty_report = _empty_gap_report(language)
        all_types_or_error = self._load_node_types_or_empty(
            language, start, empty_report
        )
        if isinstance(all_types_or_error, CoverageGapReport):
            return all_types_or_error
        all_types = all_types_or_error

        if not corpus_code:
            return _no_corpus_report(empty_report, all_types, start)

        return self._compute_corpus_coverage(language, corpus_code, all_types, start)

    def _load_node_types_or_empty(
        self,
        language: str,
        start: float,
        empty_report: CoverageGapReport,
    ) -> list[str] | CoverageGapReport:
        """Return grammar node types or an early ``empty_report`` on failure."""
        try:
            return self.get_all_node_types(language)
        except (ValueError, ImportError) as e:
            log_warning(f"Skipping '{language}': {e}")
            empty_report.error = str(e)
            empty_report.elapsed_ms = (time.perf_counter() - start) * 1000
            return empty_report

    def _compute_corpus_coverage(
        self,
        language: str,
        corpus_code: str,
        all_types: list[str],
        start: float,
    ) -> CoverageGapReport:
        """Parse ``corpus_code``, collect node stats, and assemble the gap report."""
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

        r37eg (dogfood): 87 → ~15 lines of orchestration. Per-section
        helpers (``_summary_table_lines`` / ``_overall_totals_line`` /
        ``_language_detail_lines``) own each Markdown subsection.
        """
        lines: list[str] = [
            "# Phase 3 Auto-Discovery Report",
            "",
            "## Summary",
            "",
            "| Language | Total Types | Discovered | Coverage | Wrappers | Status |",
            "|----------|-------------|------------|----------|----------|--------|",
        ]
        total_types, total_discovered = _append_summary_rows(lines, results)
        lines += _overall_totals_lines(total_discovered, total_types)

        lines += ["## Details", ""]
        for lang, report in sorted(results.items()):
            if not report.is_ok:
                continue
            _append_language_detail(lines, lang, report)
        return "\n".join(lines)
