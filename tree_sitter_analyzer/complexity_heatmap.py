#!/usr/bin/env python3
"""
Complexity Heatmap Engine — Cyclomatic complexity per function + project heatmap.

Computes McCabe-style cyclomatic complexity by walking AST nodes that create
decision points: if/elif/else, for, while, except, boolean operators (and/or),
conditional expressions (ternary), list comprehensions with filters, match/case.

Produces per-function scores and aggregates into a project-wide heatmap with
risk bands: low (1-5), medium (6-10), high (11-20), critical (20+).

Uses the pre-indexed AST cache when available; falls back to on-demand parsing.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .core.parser import Parser
from .project_graph import _language_from_ext
from .utils import setup_logger

logger = setup_logger(__name__)

_COMPLEXITY_NODES: dict[str, set[str]] = {
    "python": {
        "if_statement",
        "elif_clause",
        "for_statement",
        "while_statement",
        "except_clause",
        "boolean_operator",
        "conditional_expression",
        "list_comprehension",
        "set_comprehension",
        "dict_comprehension",
        "generator_expression",
        "match_statement",
        "case_clause",
    },
    "javascript": {
        "if_statement",
        "else_clause",
        "for_statement",
        "for_in_statement",
        "for_of_statement",
        "while_statement",
        "do_statement",
        "catch_clause",
        "ternary_expression",
        "switch_case",
        "switch_default",
        "logical_expression",
        "conditional_expression",
    },
    "typescript": {
        "if_statement",
        "else_clause",
        "for_statement",
        "for_in_statement",
        "for_of_statement",
        "while_statement",
        "do_statement",
        "catch_clause",
        "ternary_expression",
        "switch_case",
        "switch_default",
        "logical_expression",
        "conditional_expression",
    },
    "java": {
        "if_statement",
        "else_clause",
        "for_statement",
        "enhanced_for_statement",
        "while_statement",
        "do_statement",
        "catch_clause",
        "ternary_expression",
        "switch_block_statement_group",
        "logical_expression",
        "conditional_expression",
    },
    "go": {
        "if_statement",
        "else_clause",
        "for_statement",
        "expression_switch_case",
        "type_switch_case",
        "select_case",
        "binary_expression",
    },
    "rust": {
        "if_expression",
        "else_clause",
        "for_expression",
        "while_expression",
        "loop_expression",
        "match_arm",
        "binary_expression",
    },
    "c": {
        "if_statement",
        "else_clause",
        "for_statement",
        "while_statement",
        "do_statement",
        "switch_case",
        "binary_expression",
        "conditional_expression",
    },
    "cpp": {
        "if_statement",
        "else_clause",
        "for_statement",
        "while_statement",
        "do_statement",
        "switch_case",
        "binary_expression",
        "conditional_expression",
        "range_based_for_statement",
        "catch_clause",
    },
}

_FUNCTION_NODES: dict[str, str] = {
    "python": "function_definition",
    "javascript": "function_declaration",
    "typescript": "function_declaration",
    "java": "method_declaration",
    "go": "function_declaration",
    "rust": "function_item",
    "c": "function_definition",
    "cpp": "function_definition",
}

_METHOD_NODES: dict[str, set[str]] = {
    "python": {"function_definition"},
    "javascript": {"method_definition", "function_declaration", "arrow_function"},
    "typescript": {"method_definition", "function_declaration", "arrow_function"},
    "java": {"method_declaration"},
    "go": {"method_declaration", "function_declaration"},
    "rust": {"function_item"},
    "c": {"function_definition"},
    "cpp": {"function_definition"},
}

_CLASS_NODES: dict[str, str] = {
    "python": "class_definition",
    "javascript": "class_declaration",
    "typescript": "class_declaration",
    "java": "class_declaration",
    "go": "type_declaration",
    "rust": "impl_item",
    "c": "struct_specifier",
    "cpp": "class_specifier",
}


@dataclass
class FunctionComplexity:
    name: str
    file: str
    line: int
    end_line: int
    complexity: int
    language: str
    class_name: str | None = None
    decision_points: dict[str, int] = field(default_factory=dict)


@dataclass
class FileHeatmap:
    file: str
    language: str
    functions: list[FunctionComplexity] = field(default_factory=list)
    total_complexity: int = 0
    avg_complexity: float = 0.0
    max_complexity: int = 0


RISK_BANDS = {
    "low": (1, 5),
    "medium": (6, 10),
    "high": (11, 20),
    "critical": (21, 999),
}


def _risk_band(score: int) -> str:
    for band, (lo, hi) in RISK_BANDS.items():
        if lo <= score <= hi:
            return band
    return "critical" if score > 20 else "low"


def _get_nodes_for_language(language: str) -> set[str]:
    lang = language.lower()
    if lang in ("tsx", "jsx"):
        lang = "typescript"
    return _COMPLEXITY_NODES.get(lang, set())


def _count_complexity_in_node(node: Any, language: str) -> tuple[int, dict[str, int]]:
    complexity_nodes = _get_nodes_for_language(language)
    counts: dict[str, int] = defaultdict(int)
    total = 0
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type in complexity_nodes:
            counts[current.type] += 1
            total += 1
        for child in current.children:
            stack.append(child)
    return total, dict(counts)


def _find_class_name(node: Any, language: str) -> str | None:
    class_node_type = _CLASS_NODES.get(language)
    if not class_node_type:
        return None
    parent = node.parent
    while parent:
        if parent.type == class_node_type:
            for child in parent.children:
                if child.type in ("identifier", "name", "property_identifier"):
                    return (
                        child.text.decode("utf-8")
                        if isinstance(child.text, bytes)
                        else str(child.text)
                    )
        parent = parent.parent
    return None


_NAME_CHILD_TYPES = frozenset(
    {"identifier", "name", "property_identifier", "field_identifier"}
)
_ARROW_PARENT_TYPES = frozenset({"variable_declarator", "assignment_expression"})


def _node_text(node: Any) -> str:
    """Decode a node's text field to ``str``."""
    text = node.text
    return text.decode("utf-8") if isinstance(text, bytes) else str(text)


def _name_from_children(node: Any) -> str:
    """Return the first name-like child's text, or ``""``."""
    for child in node.children:
        if child.type in _NAME_CHILD_TYPES:
            return _node_text(child)
    return ""


def _arrow_function_name(node: Any) -> str:
    """Return the variable name an arrow function is assigned to, or ``""``."""
    parent = node.parent
    if parent and parent.type in _ARROW_PARENT_TYPES:
        for child in parent.children:
            if child.type in ("identifier", "property_identifier"):
                return _node_text(child)
    return ""


def _get_function_name(node: Any) -> str:
    """Extract the name from any function / method definition node."""
    name = _name_from_children(node)
    if not name and node.type == "arrow_function":
        name = _arrow_function_name(node)
    return name


def _extract_functions(
    tree: Any, source: str, language: str, file_path: str
) -> list[FunctionComplexity]:
    method_nodes = _METHOD_NODES.get(language, set())
    if method_nodes:
        return _extract_functions_from_ast(
            tree, source, language, file_path, method_nodes
        )
    return _extract_functions_via_plugin(tree, source, language, file_path)


def _extract_functions_from_ast(
    tree: Any, source: str, language: str, file_path: str, method_nodes: set[str]
) -> list[FunctionComplexity]:
    """AST-walk path for the 8 hardcoded languages.

    The cyclomatic count comes from the language plugin's
    ``element.complexity_score`` — the single source of truth (RFC-0019 / #1094)
    that ``--table`` and the golden masters use — so the heatmap can no longer
    disagree with the extractor (the old ``_count_complexity_in_node`` walk
    counted switch per-arm, counted ``else``, and used stale operator nodes).
    The per-type ``decision_points`` breakdown is still derived from the walk.
    """
    extractor_cx = _extractor_complexity_by_line(tree, source, language)
    results: list[FunctionComplexity] = []
    stack = [tree.root_node]

    while stack:
        node = stack.pop()
        if node.type in method_nodes:
            name = _get_function_name(node)
            cc, decision_points = _count_complexity_in_node(node, language)
            line = node.start_point[0] + 1
            complexity = extractor_cx.get(line, cc + 1)
            results.append(
                FunctionComplexity(
                    name=name or "<anonymous>",
                    file=file_path,
                    line=line,
                    end_line=node.end_point[0] + 1,
                    complexity=max(complexity, 1),
                    language=language,
                    class_name=_find_class_name(node, language),
                    decision_points=decision_points,
                )
            )
        stack.extend(node.children)

    return results


def _extractor_complexity_by_line(
    tree: Any, source: str, language: str
) -> dict[int, int]:
    """Map function start-line → the plugin extractor's ``complexity_score``.

    The canonical cyclomatic value (RFC-0019 / #1094), keyed by start line so a
    node walk can look each function up.
    """
    try:
        from .plugins.manager import PluginManager

        plugin = PluginManager().get_plugin(language)
        if plugin is None:
            return {}
        elements = plugin.create_extractor().extract_functions(tree, source)
    except Exception as exc:
        logger.debug("extractor complexity unavailable for %s: %s", language, exc)
        return {}

    by_line: dict[int, int] = {}
    for elem in elements:
        start = getattr(elem, "start_line", None)
        if start is not None:
            by_line[start] = max(getattr(elem, "complexity_score", 1) or 1, 1)
    return by_line


def _extract_functions_via_plugin(
    tree: Any, source: str, language: str, file_path: str
) -> list[FunctionComplexity]:
    """Fallback path for languages not in _METHOD_NODES.

    Uses the language plugin's synchronous extract_functions() which already
    computes complexity_score for all 13 supported languages.
    """
    try:
        from .plugins.manager import PluginManager

        pm = PluginManager()
        plugin = pm.get_plugin(language)
        if plugin is None:
            logger.debug(
                "No plugin available for language %r — skipping %s", language, file_path
            )
            return []

        extractor = plugin.create_extractor()
        elements = extractor.extract_functions(tree, source)
    except Exception as exc:
        logger.debug(
            "Plugin extraction failed for %s (%s): %s", file_path, language, exc
        )
        return []

    results: list[FunctionComplexity] = []
    for elem in elements:
        results.append(
            FunctionComplexity(
                name=elem.name or "<anonymous>",
                file=file_path,
                line=elem.start_line,
                end_line=elem.end_line,
                complexity=max(getattr(elem, "complexity_score", 1), 1),
                language=language,
                class_name=getattr(elem, "receiver_type", None)
                or getattr(elem, "parent_class", None),
                decision_points={},
            )
        )
    return results


def analyze_file_complexity(file_path: str, language: str) -> list[FunctionComplexity]:
    parser = Parser()
    result = parser.parse_file(file_path, language)
    if not result.success or result.tree is None:
        return []
    source = result.source_code
    return _extract_functions(result.tree, source, language, file_path)


def analyze_file_complexity_from_cache(
    cache: Any,
    file_path: str,
) -> list[FunctionComplexity]:
    """Compute complexity from a pre-indexed AST cache entry (no re-parse).

    Falls back to :func:`analyze_file_complexity` when the cache has no
    stored symbols for *file_path* or when the stored symbols lack the
    ``decision_points`` payload (v1 cache rows).
    """
    row = cache.lookup(file_path)
    if row is None:
        return analyze_file_complexity(
            file_path, _language_from_ext(file_path) or "python"
        )

    symbols = row.get("symbols", {})
    sym_list = symbols.get("symbols", []) if isinstance(symbols, dict) else []
    if not sym_list:
        return analyze_file_complexity(file_path, row.get("language", "python"))

    lang = row.get("language", "python")
    results: list[FunctionComplexity] = []
    for sym in sym_list:
        if sym.get("kind") not in ("function", "method"):
            continue
        dp: dict[str, int] = sym.get("decision_points", {})
        # Prefer the canonical extractor complexity stored at index time
        # (v14, #1094). An older row without it is re-parsed via the live path
        # rather than re-derived from the per-arm `decision_points` sum (which
        # over-counts switch/etc. and would disagree with `--table`).
        canonical = sym.get("complexity")
        if canonical is None:
            return analyze_file_complexity(file_path, lang)
        cc = max(int(canonical), 1)
        results.append(
            FunctionComplexity(
                name=sym.get("name", "<unknown>"),
                file=file_path,
                line=sym.get("line", 0),
                end_line=sym.get("end_line", sym.get("line", 0)),
                complexity=cc,
                language=lang,
                class_name=sym.get("class"),
                decision_points=dp,
            )
        )
    return results


def analyze_project_heatmap(
    project_root: str,
    language_filter: str | None = None,
    directory_filter: str | None = None,
    max_files: int = 500,
    cache: Any | None = None,
) -> dict[str, Any]:
    file_heatmaps: list[FileHeatmap] = []
    all_functions: list[FunctionComplexity] = []

    source_files = _collect_source_files(
        project_root, language_filter, directory_filter, max_files
    )

    for fpath, lang in source_files:
        if cache is not None:
            funcs = analyze_file_complexity_from_cache(cache, fpath)
        else:
            funcs = analyze_file_complexity(fpath, lang)
        if not funcs:
            continue

        total_cc = sum(fc.complexity for fc in funcs)
        max_cc = max(fc.complexity for fc in funcs)
        avg_cc = total_cc / len(funcs) if funcs else 0.0
        rel_path = os.path.relpath(fpath, project_root)

        fh = FileHeatmap(
            file=rel_path,
            language=lang,
            functions=funcs,
            total_complexity=total_cc,
            avg_complexity=round(avg_cc, 2),
            max_complexity=max_cc,
        )
        file_heatmaps.append(fh)
        all_functions.extend(funcs)

    file_heatmaps.sort(key=lambda h: h.max_complexity, reverse=True)

    risk_distribution: dict[str, int] = {
        "low": 0,
        "medium": 0,
        "high": 0,
        "critical": 0,
    }
    for fc in all_functions:
        risk_distribution[_risk_band(fc.complexity)] += 1

    top_hotspots = sorted(all_functions, key=lambda f: f.complexity, reverse=True)[:20]

    total_cc = sum(fc.complexity for fc in all_functions)
    total_funcs = len(all_functions)
    project_avg = round(total_cc / total_funcs, 2) if total_funcs else 0.0

    result: dict[str, Any] = {
        "project_root": project_root,
        "total_files_analyzed": len(file_heatmaps),
        "total_functions": total_funcs,
        "total_cyclomatic_complexity": total_cc,
        "average_complexity": project_avg,
        "risk_distribution": risk_distribution,
        "top_hotspots": [
            {
                "name": f.name,
                "file": f.file,
                "line": f.line,
                "complexity": f.complexity,
                "risk": _risk_band(f.complexity),
                "class": f.class_name,
                "language": f.language,
                "decision_points": f.decision_points,
            }
            for f in top_hotspots
        ],
        "file_heatmaps": [
            {
                "file": fh.file,
                "language": fh.language,
                "function_count": len(fh.functions),
                "total_complexity": fh.total_complexity,
                "avg_complexity": fh.avg_complexity,
                "max_complexity": fh.max_complexity,
                "top_functions": [
                    {
                        "name": fc.name,
                        "line": fc.line,
                        "complexity": fc.complexity,
                        "risk": _risk_band(fc.complexity),
                    }
                    for fc in sorted(
                        fh.functions, key=lambda x: x.complexity, reverse=True
                    )[:5]
                ],
            }
            for fh in file_heatmaps
        ],
    }
    if total_funcs == 0:
        result["note"] = (
            "No functions extracted. The project may contain only languages "
            "without parser support, or all files may be empty."
        )
    return result


def _collect_source_files(
    project_root: str,
    language_filter: str | None,
    directory_filter: str | None,
    max_files: int,
) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    skip_dirs = {
        ".git",
        "__pycache__",
        "node_modules",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "venv",
        ".eggs",
        "dist",
        "build",
        ".ast-cache",
        ".tree-sitter-cache",
        ".swarm",
        ".claude-flow",
        ".claude",
    }

    base = project_root
    if directory_filter:
        base = os.path.join(project_root, directory_filter)

    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            fpath = os.path.join(root, fname)
            lang = _language_from_ext(fpath)
            if not lang:
                continue
            if language_filter and lang != language_filter:
                continue
            results.append((fpath, lang))
            if len(results) >= max_files:
                return results

    return results
