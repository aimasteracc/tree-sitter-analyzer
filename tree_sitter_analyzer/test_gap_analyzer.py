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

import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

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
                    kind="function",
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
    results: list[tuple[str, str, bool]] = []
    for dirpath, dirnames, filenames in os.walk(project_root):
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
            is_test = _is_test_file(full)
            results.append((full, lang, is_test))
            if len(results) >= max_files:
                return results
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


def analyze_coverage_gaps(
    project_root: str,
    *,
    language_filter: str | None = None,
    max_files: int = 1000,
    max_gaps: int = 50,
    include_covered: bool = False,
) -> CoverageGapResult:
    all_files = _collect_files(project_root, language_filter, max_files)
    prod_files = [(f, lang) for f, lang, t in all_files if not t]
    test_files = [(f, lang) for f, lang, t in all_files if t]

    prod_symbols: list[ProductionSymbol] = []
    for fpath, lang in prod_files:
        prod_symbols.extend(_scan_file(fpath, lang))

    test_symbols, covered_test_names = _build_test_symbols(test_files)
    file_class_map = _build_file_class_map(prod_symbols, project_root)

    parser_cache: dict[str, Any] = {}
    for sym in prod_symbols:
        if sym.kind == "function":
            sym.complexity = _get_complexity_cached(sym, parser_cache)
            sym.risk = _risk_band(sym.complexity)

    gaps, covered = _classify_gaps(
        prod_symbols, covered_test_names, file_class_map, project_root
    )
    gaps.sort(key=lambda g: _priority_score(g.symbol), reverse=True)

    stats = _build_coverage_summary(
        prod_symbols, gaps, project_root, prod_files, test_files
    )

    return CoverageGapResult(
        total_production_symbols=stats["total"],
        total_test_symbols=len(test_symbols),
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
        },
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
