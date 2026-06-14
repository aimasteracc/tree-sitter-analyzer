#!/usr/bin/env python3
"""
Test Coverage Gap Analyzer — Maps production symbols to test files and identifies untested code.

Scans a project to:
- Discover all production functions/classes across languages
- Discover all test symbols (test functions, test classes, test methods)
- Match test symbols to production symbols by naming convention
- Identify gaps: production symbols with no corresponding test
- Prioritize gaps by cyclomatic complexity (untested + complex = high priority)

Uses the pre-indexed AST cache when available; falls back to on-demand parsing.
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal

from .core.parser import Parser
from .project_graph import _language_from_ext
from .utils import setup_logger

logger = setup_logger(__name__)

_EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "htmlcov",
    ".cache",
    ".eggs",
    ".idea",
    ".vscode",
    ".claude",
    ".hg",
    ".svn",
    "site-packages",
    "egg-info",
    "assets",
    "static",
    "templates",
    "migrations",
}

# Directories that are never production source code: test suites, corpora,
# fixture/golden-master collections, example code, and benchmark harnesses.
# Walking these wastes the max_files budget and pollutes the production-symbol
# count with non-product code.
_NON_PROD_DIRS = {
    "tests",
    "test",
    "testing",
    "corpus",
    "fixtures",
    "fixture",
    "golden_masters",
    "examples",
    "example",
    "benchmarks",
    "benchmark",
    "compatibility_test",
    "compatibility_tests",
    "scripts",
    "spec",
    "specs",
    "e2e",
}

_SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".go",
    ".c",
    ".cpp",
    ".rs",
    ".rb",
    ".swift",
    ".kt",
    ".scala",
}

_TEST_FILE_PATTERNS = re.compile(
    r"(?:^test_|_test\.|\.test\.|\.spec\.|_spec\.|tests?/|/tests?/|Test\.py$)",
    re.IGNORECASE,
)

_FUNCTION_NODE_TYPES: dict[str, set[str]] = {
    "python": {"function_definition"},
    "javascript": {
        "function_declaration",
        "arrow_function",
        "method_definition",
        "generator_function_declaration",
    },
    "typescript": {
        "function_declaration",
        "arrow_function",
        "method_definition",
        "generator_function_declaration",
    },
    "java": {"method_declaration", "constructor_declaration"},
    "go": {"function_declaration", "method_declaration"},
    "c": {"function_definition"},
    "cpp": {"function_definition", "declaration"},
    "rust": {"function_item"},
}

_CLASS_NODE_TYPES: dict[str, set[str]] = {
    "python": {"class_definition"},
    "javascript": {"class_declaration"},
    "typescript": {
        "class_declaration",
        "interface_declaration",
        "type_alias_declaration",
    },
    "java": {"class_declaration", "interface_declaration", "enum_declaration"},
    "go": {"type_declaration"},
    "c": {"struct_specifier"},
    "cpp": {"class_specifier", "struct_specifier"},
    "rust": {"struct_item", "enum_item", "impl_item"},
}

_NAME_CHILD_TYPES = {
    "identifier",
    "name",
    "property_identifier",
    "field_identifier",
    "type_identifier",
    "word",
}


@dataclass
class ProductionSymbol:
    name: str
    kind: str
    file_path: str
    language: str
    line: int
    end_line: int
    class_name: str | None = None
    complexity: int = 0
    risk: str = "low"


@dataclass
class TestSymbol:
    name: str
    file_path: str
    language: str
    line: int
    likely_targets: list[str] = field(default_factory=list)


@dataclass
class CoverageGap:
    symbol: ProductionSymbol
    priority: str
    reason: str
    suggestion: str
    # RFC-0003 criterion 6: static-graph enrichment
    who_should_test: list[str] = field(
        default_factory=list
    )  # test files that import the module
    blast_radius: int = 0  # number of downstream callers (impact if untested)


@dataclass
class CoverageGapResult:
    total_production_symbols: int
    total_test_symbols: int
    covered_count: int
    gap_count: int
    coverage_pct: float
    gaps: list[CoverageGap]
    covered: list[ProductionSymbol]
    summary: dict[str, Any] = field(default_factory=dict)
    source: Literal["coverage", "naming"] = "naming"


def _is_test_file(file_path: str) -> bool:
    return bool(_TEST_FILE_PATTERNS.search(file_path))


def _extract_name(node: Any) -> str:
    for child in node.children:
        if child.type in _NAME_CHILD_TYPES:
            text = child.text
            return text.decode("utf-8") if isinstance(text, bytes) else str(text)
    return "<unknown>"


def _extract_symbols_from_tree(
    tree: Any, language: str, file_path: str
) -> list[ProductionSymbol]:
    func_types = _FUNCTION_NODE_TYPES.get(language, set())
    class_types = _CLASS_NODE_TYPES.get(language, set())
    if not func_types and not class_types:
        return []

    results: list[ProductionSymbol] = []
    root = tree.root_node
    stack: list[tuple[Any, str | None]] = [(root, None)]

    while stack:
        node, parent_class = stack.pop()
        ntype = node.type

        current_class = parent_class
        if ntype in class_types:
            current_class = _extract_name(node)
            results.append(
                ProductionSymbol(
                    name=current_class,
                    kind="class",
                    file_path=file_path,
                    language=language,
                    line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                )
            )

        if ntype in func_types:
            fname = _extract_name(node)
            results.append(
                ProductionSymbol(
                    name=fname,
                    kind="method" if current_class else "function",
                    file_path=file_path,
                    language=language,
                    line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    class_name=current_class,
                )
            )

        for child in node.children:
            stack.append((child, current_class))

    return results


def _scan_file(file_path: str, language: str) -> list[ProductionSymbol]:
    parser = Parser()
    result = parser.parse_file(file_path, language)
    if not result.success or result.tree is None:
        return []
    return _extract_symbols_from_tree(result.tree, language, file_path)


def _collect_files(
    project_root: str,
    language_filter: str | None = None,
    max_files: int = 1000,
) -> list[tuple[str, str, bool]]:
    """Collect source files under *project_root*.

    Scope rule: all source files found by os.walk, excluding dirs in
    ``_EXCLUDE_DIRS`` (tooling/build).  Directories listed in
    ``_NON_PROD_DIRS`` (tests, corpus, fixtures, examples, benchmarks,
    scripts, …) are still walked so that test files inside them are collected
    for naming-convention matching, but every file found inside a
    ``_NON_PROD_DIRS`` subtree is treated as a test/non-production file
    regardless of its individual name.

    The ``max_files`` cap applies to **production files only** so that test
    files cannot exhaust the budget and prevent the main package from being
    scanned.  Test files are never capped — they are all collected regardless
    of count.
    """
    results: list[tuple[str, str, bool]] = []
    prod_count = 0
    for dirpath, dirnames, filenames in os.walk(project_root):
        # Determine whether the current directory is inside a non-production
        # subtree by checking whether any path component from project_root
        # downward matches _NON_PROD_DIRS.
        rel_dir = os.path.relpath(dirpath, project_root)
        parts = rel_dir.split(os.sep) if rel_dir != "." else []
        in_non_prod = any(p in _NON_PROD_DIRS for p in parts)

        dirnames[:] = [
            d for d in dirnames if d not in _EXCLUDE_DIRS and not d.startswith(".")
        ]
        for fname in sorted(filenames):
            ext = os.path.splitext(fname)[1]
            if ext not in _SOURCE_EXTENSIONS:
                continue
            full = os.path.join(dirpath, fname)
            lang = _language_from_ext(full) or ""
            if language_filter and lang != language_filter:
                continue
            # Files inside a non-production directory are always test/non-prod,
            # regardless of their individual filename.
            is_test = in_non_prod or _is_test_file(full)
            if not is_test:
                # Production budget exhausted: keep walking so that test files
                # appearing later in os.walk order (e.g. app/ before tests/)
                # are still collected for naming-convention matching — an
                # early return here would misreport covered symbols as gaps.
                if prod_count >= max_files:
                    continue
                prod_count += 1
            results.append((full, lang, is_test))
    return results


_TEST_PREFIXES = ["test_", "test", "should_", "should", "it_", "it", "given_", "given"]
_KW_SEPARATORS = (
    "_returns_",
    "_raises_",
    "_handles_",
    "_when_",
    "_with_",
    "_and_",
    "_or_",
    "_but_",
)


def _strip_prefix(name: str) -> str | None:
    """Remove a test prefix from *name*; return stripped remainder, or None if no match."""
    for p in _TEST_PREFIXES:
        if name.lower().startswith(p) and len(name) > len(p):
            rem = name[len(p) :]
            return rem[1:] if rem.startswith("_") else rem
    return None


def _extract_test_targets(test_name: str) -> list[str]:
    targets: list[str] = []
    name = test_name

    rem = _strip_prefix(name)
    if rem:
        targets.extend([rem.lower(), rem])

    for kw in _KW_SEPARATORS:
        if kw in name.lower():
            base = name.lower().split(kw)[0]
            stripped = _strip_prefix(base)
            if stripped is not None:
                base = stripped
            if base:
                targets.append(base)
            break

    if "test" in name.lower():
        parts = re.split(r"[Tt]est", name)
        for part in parts:
            cleaned = part.strip("_")
            if cleaned and len(cleaned) > 1:
                targets.append(cleaned.lower())

    return list(dict.fromkeys(targets))


def _compute_complexity(node: Any, language: str) -> int:
    complexity_nodes = {
        "if_statement",
        "elif_clause",
        "for_statement",
        "while_statement",
        "except_clause",
        "boolean_operator",
        "conditional_expression",
        "match_statement",
        "case_clause",
        "else_clause",
        "for_in_statement",
        "for_of_statement",
        "do_statement",
        "catch_clause",
        "ternary_expression",
        "switch_case",
        "logical_expression",
        "enhanced_for_statement",
        "switch_block_statement_group",
        "expression_switch_case",
        "if_expression",
        "expression_case",
    }
    count = 0
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type in complexity_nodes:
            count += 1
        for child in current.children:
            stack.append(child)
    return max(count + 1, 1)


def _risk_band(complexity: int) -> str:
    if complexity <= 5:
        return "low"
    if complexity <= 10:
        return "medium"
    if complexity <= 20:
        return "high"
    return "critical"


def _priority_score(symbol: ProductionSymbol) -> int:
    score = 0
    if symbol.kind == "class":
        score += 5
    if symbol.risk == "critical":
        score += 10
    elif symbol.risk == "high":
        score += 7
    elif symbol.risk == "medium":
        score += 3
    if symbol.class_name:
        score += 2
    if symbol.complexity > 1:
        score += symbol.complexity
    return score


def _build_test_symbols(
    test_files: list[tuple[str, str]],
) -> tuple[list[TestSymbol], set[str]]:
    """Scan test files and return (test_symbols, covered_test_names)."""
    test_symbols: list[TestSymbol] = []
    for fpath, lang in test_files:
        for s in _scan_file(fpath, lang):
            targets = _extract_test_targets(s.name)
            test_symbols.append(
                TestSymbol(
                    name=s.name,
                    file_path=s.file_path,
                    language=s.language,
                    line=s.line,
                    likely_targets=targets,
                )
            )
    covered: set[str] = {target for ts in test_symbols for target in ts.likely_targets}
    return test_symbols, covered


def _build_file_class_map(
    prod_symbols: list[ProductionSymbol],
    project_root: str,
) -> dict[str, set[str]]:
    """Build map: rel_path -> set of class names (lowercased)."""
    result: dict[str, set[str]] = defaultdict(set)
    for s in prod_symbols:
        if s.kind == "class":
            rel = os.path.relpath(s.file_path, project_root)
            result[rel].add(s.name.lower())
    return result


def _is_covered(
    sym: ProductionSymbol,
    covered_test_names: set[str],
    file_class_map: dict[str, set[str]],
    project_root: str,
) -> bool:
    """Return True if *sym* has matching test coverage."""
    if sym.name.lower() in covered_test_names:
        return True
    if sym.class_name and sym.class_name.lower() in covered_test_names:
        return True
    rel = os.path.relpath(sym.file_path, project_root)
    rel_stem = os.path.splitext(os.path.basename(rel))[0].lower()
    if rel_stem in covered_test_names:
        return True
    return any(cls in covered_test_names for cls in file_class_map.get(rel, set()))


def _get_complexity_cached(
    sym: ProductionSymbol,
    parser_cache: dict[str, Any],
) -> int:
    """Return cyclomatic complexity of *sym*, using *parser_cache* to avoid re-parsing."""
    if sym.complexity > 0:
        return sym.complexity
    fpath = sym.file_path
    if fpath not in parser_cache:
        r = Parser().parse_file(fpath, sym.language)
        parser_cache[fpath] = r.tree if r.success else None
    tree = parser_cache[fpath]
    if tree is None:
        return 1
    func_types = _FUNCTION_NODE_TYPES.get(sym.language, set())
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type in func_types:
            if (
                _extract_name(node) == sym.name
                and (node.start_point[0] + 1) == sym.line
            ):
                return _compute_complexity(node, sym.language)
        stack.extend(node.children)
    return 1


def _classify_priority(score: int) -> str:
    """Map a numeric priority score to a band label."""
    if score >= 10:
        return "critical"
    if score >= 7:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def _classify_gaps(
    prod_symbols: list[ProductionSymbol],
    covered_test_names: set[str],
    file_class_map: dict[str, set[str]],
    project_root: str,
) -> tuple[list[CoverageGap], list[ProductionSymbol]]:
    """Partition *prod_symbols* into gaps and covered lists."""
    gaps: list[CoverageGap] = []
    covered: list[ProductionSymbol] = []
    for sym in prod_symbols:
        if _is_covered(sym, covered_test_names, file_class_map, project_root):
            covered.append(sym)
        else:
            priority = _classify_priority(_priority_score(sym))
            gaps.append(
                CoverageGap(
                    symbol=sym,
                    priority=priority,
                    reason=_make_reason(sym),
                    suggestion=_make_suggestion(sym),
                )
            )
    return gaps, covered


def _build_coverage_summary(
    prod_symbols: list[ProductionSymbol],
    gaps: list[CoverageGap],
    project_root: str,
    prod_files: list[tuple[str, str]],
    test_files: list[tuple[str, str]],
) -> dict[str, Any]:
    """Compute summary statistics for *CoverageGapResult*."""
    total = len(prod_symbols)
    gap_count = len(gaps)
    covered_count = total - gap_count
    coverage_pct = round((covered_count / total) * 100, 1) if total else 0.0

    priority_dist: dict[str, int] = defaultdict(int)
    by_file: dict[str, int] = defaultdict(int)
    for g in gaps:
        priority_dist[g.priority] += 1
        by_file[os.path.relpath(g.symbol.file_path, project_root)] += 1

    worst_files = sorted(by_file.items(), key=lambda x: x[1], reverse=True)[:10]

    by_language: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "gaps": 0}
    )
    for sym in prod_symbols:
        by_language[sym.language]["total"] += 1
    for g in gaps:
        by_language[g.symbol.language]["gaps"] += 1

    return {
        "total": total,
        "gap_count": gap_count,
        "covered_count": covered_count,
        "coverage_pct": coverage_pct,
        "priority_dist": dict(priority_dist),
        "worst_files": worst_files,
        "by_language": dict(by_language),
    }


def _enrich_gaps_with_static_graph(
    gaps: list[CoverageGap],
    project_root: str,
    test_files: list[tuple[str, str]],
) -> None:
    """RFC-0003 criterion 6: attach static-graph context to each gap.

    Adds:
    - ``who_should_test``: test files that already import the gap's module
      (heuristic: the test's file name suggests coverage of this module).
    - ``blast_radius``: count of distinct callers of the gap's symbol from
      the AST cache (requires the cache to be indexed; degrades gracefully).
    """
    try:
        from .ast_cache import ASTCache

        cache = ASTCache(project_root)
        try:
            _enrich_blast_radius(gaps, cache)
        finally:
            cache.close()
    except Exception:
        pass

    _enrich_who_should_test(gaps, test_files, project_root)


def _enrich_blast_radius(gaps: list[CoverageGap], cache: Any) -> None:
    """Populate blast_radius from the AST cache's call edges."""
    try:
        conn = cache.get_conn()
        for gap in gaps:
            name = gap.symbol.name
            try:
                row = conn.execute(
                    "SELECT COUNT(DISTINCT file_path) AS c FROM edges "
                    "WHERE kind='calls' AND callee_name=? AND callee_resolution != 'unknown'",
                    (name,),
                ).fetchone()
                gap.blast_radius = int(row["c"]) if row else 0
            except Exception:
                gap.blast_radius = 0
    except Exception:
        pass


def _enrich_who_should_test(
    gaps: list[CoverageGap],
    test_files: list[tuple[str, str]],
    project_root: str,
) -> None:
    """Suggest test files that are likely responsible for testing each gap.

    Heuristic: test files whose name contains the module name of the gap's file
    (e.g. test_ast_cache.py → ast_cache.py) or that are co-located.
    """
    for gap in gaps:
        sym_file = os.path.basename(gap.symbol.file_path)
        module_name = os.path.splitext(sym_file)[0]  # e.g. "ast_cache"
        candidates: list[str] = []
        for tfile, _lang in test_files:
            tname = os.path.basename(tfile)
            if module_name in tname or tname in (
                f"test_{module_name}.py",
                f"{module_name}_test.py",
            ):
                rel = os.path.relpath(tfile, project_root)
                candidates.append(rel)
        gap.who_should_test = candidates[:5]  # cap at 5 suggestions


def _load_coverage_json(path: str) -> dict[str, Any] | None:
    """Load and parse a coverage.py JSON report. Returns None on failure."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "files" not in data:
            logger.debug("coverage.json at %s has no 'files' key — ignoring", path)
            return None
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("could not load coverage.json at %s: %s", path, exc)
        return None


def _discover_coverage_json(project_root: str) -> str | None:
    """Auto-discover coverage.json at the project root. Returns path or None."""
    candidate = os.path.join(project_root, "coverage.json")
    return candidate if os.path.isfile(candidate) else None


def _build_executed_lines_index(
    coverage_data: dict[str, Any], project_root: str
) -> dict[str, frozenset[int]]:
    """Build {relative_file_path: frozenset(executed_line_numbers)} from coverage.json.

    coverage.py stores paths relative to the working directory (usually the
    project root). We normalise both sides to a common relative form so lookups
    work regardless of how the coverage was recorded.
    """
    index: dict[str, frozenset[int]] = {}
    abs_root = os.path.realpath(project_root)
    for raw_path, file_info in coverage_data.get("files", {}).items():
        executed: list[int] = file_info.get("executed_lines", [])
        # Normalise to a path relative to the project root
        if os.path.isabs(raw_path):
            try:
                rel = os.path.relpath(os.path.realpath(raw_path), abs_root)
            except ValueError:
                rel = raw_path
        else:
            rel = raw_path
        index[rel] = frozenset(executed)
        # Also index the final path component for short-form lookups
        index[os.path.basename(raw_path)] = frozenset(executed)
    return index


def _symbol_covered_by_coverage(
    sym: ProductionSymbol,
    executed_index: dict[str, frozenset[int]],
    project_root: str,
) -> bool:
    """True when at least one **body** line of the symbol is in executed_lines.

    RFC-0003 criterion 2: the declaration/decorator line alone is not enough —
    at least one statement inside the function body must have been executed.
    A function whose first line is the ``def`` statement is not counted as
    covered if only that line executed (it means the function was defined but
    never called).
    """
    if sym.end_line <= sym.line:
        return False
    rel = os.path.relpath(sym.file_path, project_root)
    executed = executed_index.get(rel) or executed_index.get(
        os.path.basename(sym.file_path)
    )
    if not executed:
        return False
    # Body starts at line+1 (first line is the def/class declaration)
    body_start = sym.line + 1
    return any(ln in executed for ln in range(body_start, sym.end_line + 1))


def analyze_coverage_gaps(
    project_root: str,
    *,
    coverage_json: str | None = None,
    language_filter: str | None = None,
    max_files: int = 1000,
    max_gaps: int = 50,
    include_covered: bool = False,
    target_file: str | None = None,
) -> CoverageGapResult:
    """Analyse test coverage gaps.

    When *coverage_json* is provided (or auto-discovered at the project root),
    the function uses runtime coverage data as the ground truth for whether a
    symbol is covered. Falls back to naming-convention matching when coverage
    data is absent or malformed (RFC-0003 criteria 1,2,3,4,5).

    When *target_file* is given, the production-symbol scope is filtered to
    files whose path contains it (substring match), BEFORE the ``max_gaps``
    cap — so ``total_production_symbols``/``coverage_pct``/``gaps`` all reflect
    just that file. Test files stay unfiltered so naming-convention coverage
    still matches across the suite (#693: ``file_path`` must not be a no-op).
    """
    # RFC-0003 criterion 4: auto-discover coverage.json at project root
    if coverage_json is None:
        coverage_json = _discover_coverage_json(project_root)

    # RFC-0003 criterion 5: graceful fallback — try to load, fall back on failure
    coverage_data: dict[str, Any] | None = None
    if coverage_json:
        coverage_data = _load_coverage_json(coverage_json)
        if coverage_data is None:
            logger.debug("coverage.json unavailable; falling back to naming convention")

    source: Literal["coverage", "naming"] = "coverage" if coverage_data else "naming"
    executed_index = (
        _build_executed_lines_index(coverage_data, project_root)
        if coverage_data
        else {}
    )

    all_files = _collect_files(project_root, language_filter, max_files)
    prod_files = [(f, lang) for f, lang, t in all_files if not t]
    test_files = [(f, lang) for f, lang, t in all_files if t]

    # #693: scope production analysis to a single file when requested, BEFORE
    # complexity scoring, gap classification, and the max_gaps cap — so every
    # reported number (total_production_symbols / coverage_pct / production_files
    # / gaps) reflects just that file, not a project-wide figure with the
    # requested path silently ignored. Substring match mirrors the tool's
    # mode=file filter. Test files stay unfiltered so naming-convention coverage
    # still matches across the whole suite.
    if target_file:
        prod_files = [(f, lang) for f, lang in prod_files if target_file in f]

    prod_symbols: list[ProductionSymbol] = []
    for fpath, lang in prod_files:
        prod_symbols.extend(_scan_file(fpath, lang))

    parser_cache: dict[str, Any] = {}
    for sym in prod_symbols:
        if sym.kind in ("function", "method"):
            sym.complexity = _get_complexity_cached(sym, parser_cache)
            sym.risk = _risk_band(sym.complexity)

    if coverage_data:
        # RFC-0003 criterion 1+2: coverage.json is ground truth.
        # A symbol is covered when ≥1 body line was executed (criterion 2).
        gaps = []
        covered = []
        for sym in prod_symbols:
            if _symbol_covered_by_coverage(sym, executed_index, project_root):
                covered.append(sym)
            else:
                gap = CoverageGap(
                    symbol=sym,
                    priority=sym.risk or "low",
                    reason="No body line executed per coverage.json",
                    suggestion=f"Add a test that invokes {sym.name}",
                )
                gaps.append(gap)
    else:
        test_symbols, covered_test_names = _build_test_symbols(test_files)
        file_class_map = _build_file_class_map(prod_symbols, project_root)
        gaps, covered = _classify_gaps(
            prod_symbols, covered_test_names, file_class_map, project_root
        )

    test_symbols_count = (
        len(_build_test_symbols(test_files)[0]) if not coverage_data else 0
    )
    gaps.sort(key=lambda g: _priority_score(g.symbol), reverse=True)

    # RFC-0003 criterion 6: enrich gaps with static-graph context
    _enrich_gaps_with_static_graph(gaps, project_root, test_files)

    stats = _build_coverage_summary(
        prod_symbols, gaps, project_root, prod_files, test_files
    )

    return CoverageGapResult(
        total_production_symbols=stats["total"],
        total_test_symbols=test_symbols_count,
        covered_count=stats["covered_count"],
        gap_count=stats["gap_count"],
        coverage_pct=stats["coverage_pct"],
        gaps=gaps[:max_gaps],
        covered=covered if include_covered else [],
        summary={
            "priority_distribution": stats["priority_dist"],
            "worst_files": stats["worst_files"],
            "by_language": stats["by_language"],
            "production_files": len(prod_files),
            "test_files": len(test_files),
            "coverage_source": source,
        },
        source=source,
    )


def _make_reason(sym: ProductionSymbol) -> str:
    parts = []
    if sym.kind == "class":
        parts.append(f"class '{sym.name}' has no test class")
    else:
        prefix = (
            f"method '{sym.name}' in class '{sym.class_name}'"
            if sym.class_name
            else f"function '{sym.name}'"
        )
        parts.append(f"{prefix} has no matching test")
    if sym.risk in ("high", "critical"):
        parts.append(f"complexity={sym.complexity} ({sym.risk} risk)")
    return "; ".join(parts)


def _make_suggestion(sym: ProductionSymbol) -> str:
    if sym.kind == "class":
        return f"Add test class Test{sym.name} covering its public methods"
    if sym.class_name:
        return f"Add test_{sym.name} in Test{sym.class_name} test class"
    return f"Add test_{sym.name}() testing normal path and edge cases"
