#!/usr/bin/env python3
"""Test governance auditor.

Goals:
1. Build source function/method -> test mapping.
2. Detect duplicate tests (AST fingerprint based).
3. Detect potentially invalid tests (no assertion / no raises / no mock assertions).
4. Detect possible coverage gaps by symbol-level heuristic matching.
5. Detect language test sharding imbalance (e.g., YAML overly fragmented).

This is a static analysis auditor; it does not execute tests.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUPPORTED_LANGUAGES = {
    "java",
    "python",
    "typescript",
    "javascript",
    "c",
    "cpp",
    "csharp",
    "sql",
    "html",
    "css",
    "go",
    "rust",
    "kotlin",
    "php",
    "ruby",
    "yaml",
    "markdown",
}


@dataclass
class SourceSymbol:
    module: str
    symbol: str
    kind: str  # function | method
    file_path: str
    line: int


@dataclass
class TestCase:
    test_name: str
    file_path: str
    line: int
    referenced_names: set[str]
    has_assertion: bool
    fingerprint: str


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def extract_source_symbols(root: Path) -> list[SourceSymbol]:
    src_root = root / "tree_sitter_analyzer"
    symbols: list[SourceSymbol] = []

    for py_file in src_root.rglob("*.py"):
        if py_file.name.startswith("__"):
            continue

        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        module = rel(py_file, src_root).replace("/", ".")[:-3]

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(
                    SourceSymbol(
                        module=module,
                        symbol=node.name,
                        kind="function",
                        file_path=rel(py_file, root),
                        line=node.lineno,
                    )
                )
            elif isinstance(node, ast.ClassDef):
                class_name = node.name
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.append(
                            SourceSymbol(
                                module=module,
                                symbol=f"{class_name}.{item.name}",
                                kind="method",
                                file_path=rel(py_file, root),
                                line=item.lineno,
                            )
                        )

    return symbols


def _is_assert_call(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Attribute):
        attr = node.func.attr
        if attr.startswith("assert"):
            return True
    return False


def _collect_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


def _is_pytest_call(node: ast.Call, name: str) -> bool:
    """Check if call is pytest.<name>() or just <name>()."""
    fn = node.func
    if isinstance(fn, ast.Attribute) and fn.attr == name:
        return True
    if isinstance(fn, ast.Name) and fn.id == name:
        return True
    return False


def _has_assertion_or_equivalent(test_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(test_node):
        if isinstance(node, ast.Assert):
            return True
        if isinstance(node, ast.With):
            for item in node.items:
                ctx = item.context_expr
                if isinstance(ctx, ast.Call):
                    fn = ctx.func
                    if isinstance(fn, ast.Attribute) and fn.attr in ("raises", "warns"):
                        return True
                    if isinstance(fn, ast.Name) and fn.id in ("raises", "warns"):
                        return True
        if isinstance(node, ast.Call):
            if _is_assert_call(node):
                return True
            # pytest.fail() inside try-except counts as an assertion mechanism
            if _is_pytest_call(node, "fail"):
                return True
            # pytest.skip() / pytest.mark.skip means the test is intentionally skipped
            if _is_pytest_call(node, "skip"):
                return True
    return False


def _fingerprint_test(test_node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    clone = ast.FunctionDef(
        name="_",
        args=test_node.args,
        body=test_node.body,
        decorator_list=[],
        returns=None,
        type_comment=None,
    )
    normalized = ast.dump(clone, include_attributes=False)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def extract_tests(root: Path) -> list[TestCase]:
    tests_root = root / "tests" / "unit"
    cases: list[TestCase] = []

    for test_file in tests_root.rglob("test_*.py"):
        try:
            tree = ast.parse(test_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                cases.append(
                    TestCase(
                        test_name=node.name,
                        file_path=rel(test_file, root),
                        line=node.lineno,
                        referenced_names=_collect_names(node),
                        has_assertion=_has_assertion_or_equivalent(node),
                        fingerprint=_fingerprint_test(node),
                    )
                )
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test_"):
                        cases.append(
                            TestCase(
                                test_name=f"{node.name}.{item.name}",
                                file_path=rel(test_file, root),
                                line=item.lineno,
                                referenced_names=_collect_names(item),
                                has_assertion=_has_assertion_or_equivalent(item),
                                fingerprint=_fingerprint_test(item),
                            )
                        )

    return cases


def build_symbol_coverage(
    symbols: list[SourceSymbol],
    tests: list[TestCase],
    uncovered_symbols_allowlist: list[str] | None = None,
) -> dict[str, Any]:
    allowlisted: set[str] = set(uncovered_symbols_allowlist or [])
    coverage: dict[str, list[str]] = {}

    test_names_map: dict[str, list[TestCase]] = {}
    for test in tests:
        for name in test.referenced_names:
            test_names_map.setdefault(name, []).append(test)

    uncovered: list[dict[str, Any]] = []

    for symbol in symbols:
        simple_name = symbol.symbol.split(".")[-1]
        matched_tests = test_names_map.get(simple_name, [])
        key = f"{symbol.module}:{symbol.symbol}"
        coverage[key] = [f"{t.file_path}:{t.line}" for t in matched_tests]
        if not matched_tests and not simple_name.startswith("_") and key not in allowlisted:
            uncovered.append(
                {
                    "symbol": key,
                    "kind": symbol.kind,
                    "file": symbol.file_path,
                    "line": symbol.line,
                }
            )

    return {
        "symbol_to_tests": coverage,
        "possibly_uncovered_symbols": uncovered,
    }


def _load_allowlist(root: Path) -> dict[str, list[str]]:
    """Load governance allowlist from tests/governance_allowlist.json if it exists."""
    allowlist_path = root / "tests" / "governance_allowlist.json"
    if allowlist_path.exists():
        try:
            data = json.loads(allowlist_path.read_text(encoding="utf-8"))
            return {
                "invalid_tests_allowlist": data.get("invalid_tests_allowlist", []),
                "duplicate_clusters_allowlist": data.get("duplicate_clusters_allowlist", []),
                "uncovered_symbols_allowlist": data.get("uncovered_symbols_allowlist", []),
            }
        except Exception:
            pass
    return {"invalid_tests_allowlist": [], "duplicate_clusters_allowlist": [], "uncovered_symbols_allowlist": []}


def detect_duplicate_tests(
    tests: list[TestCase],
    duplicate_clusters_allowlist: list[str] | None = None,
) -> list[dict[str, Any]]:
    allowlisted: set[str] = set(duplicate_clusters_allowlist or [])
    by_fp: dict[str, list[TestCase]] = {}
    for test in tests:
        by_fp.setdefault(test.fingerprint, []).append(test)

    duplicates: list[dict[str, Any]] = []
    for fp, members in by_fp.items():
        if len(members) <= 1:
            continue
        test_keys = [f"{m.file_path}:{m.line}:{m.test_name}" for m in members]
        # Skip if any member is in the allowlist
        if any(k in allowlisted for k in test_keys):
            continue
        duplicates.append(
            {
                "fingerprint": fp,
                "count": len(members),
                "tests": test_keys,
            }
        )

    duplicates.sort(key=lambda item: item["count"], reverse=True)
    return duplicates


def detect_invalid_tests(
    tests: list[TestCase],
    invalid_tests_allowlist: list[str] | None = None,
) -> list[dict[str, Any]]:
    allowlisted: set[str] = set(invalid_tests_allowlist or [])
    invalid: list[dict[str, Any]] = []
    for test in tests:
        if not test.has_assertion:
            key = f"{test.file_path}:{test.line}:{test.test_name}"
            if key in allowlisted:
                continue
            invalid.append(
                {
                    "test": key,
                    "reason": "No assert/pytest.raises/mock assertion detected",
                }
            )
    return invalid


def language_sharding(root: Path) -> dict[str, Any]:
    lang_tests_root = root / "tests" / "unit" / "languages"
    counts: dict[str, int] = {lang: 0 for lang in SUPPORTED_LANGUAGES}
    property_counts: dict[str, int] = {lang: 0 for lang in SUPPORTED_LANGUAGES}

    for test_file in lang_tests_root.glob("test_*.py"):
        stem = test_file.stem  # test_yaml_... etc
        tokens = stem.split("_")
        if len(tokens) < 2:
            continue
        lang = tokens[1]
        if lang not in counts:
            continue
        counts[lang] += 1
        if "properties" in stem:
            property_counts[lang] += 1

    non_zero = [value for value in counts.values() if value > 0]
    median = statistics.median(non_zero) if non_zero else 0

    outliers = []
    for lang, value in counts.items():
        if median > 0 and value >= median * 2:
            outliers.append(
                {
                    "language": lang,
                    "test_files": value,
                    "property_files": property_counts[lang],
                    "median": median,
                    "signal": "over-sharded",
                }
            )

    return {
        "counts": counts,
        "property_counts": property_counts,
        "median_files_per_language": median,
        "outliers": sorted(outliers, key=lambda item: item["test_files"], reverse=True),
    }


def write_markdown_report(report: dict[str, Any], output_path: Path) -> None:
    lines: list[str] = []
    summary = report["summary"]

    lines.append("# Test Governance Audit Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Source symbols: {summary['source_symbols']}")
    lines.append(f"- Test cases: {summary['test_cases']}")
    lines.append(f"- Possibly uncovered symbols: {summary['possibly_uncovered_symbols']}")
    lines.append(f"- Duplicate clusters: {summary['duplicate_clusters']}")
    lines.append(f"- Potentially invalid tests: {summary['invalid_tests']}")
    lines.append("")

    lines.append("## Language Sharding Outliers")
    lines.append("")
    outliers = report["language_sharding"]["outliers"]
    if not outliers:
        lines.append("- None")
    else:
        for outlier in outliers:
            lines.append(
                f"- {outlier['language']}: files={outlier['test_files']}, property_files={outlier['property_files']}, median={outlier['median']}"
            )

    lines.append("")
    lines.append("## Top Duplicate Clusters")
    lines.append("")
    duplicates = report["duplicates"][:20]
    if not duplicates:
        lines.append("- None")
    else:
        for cluster in duplicates:
            lines.append(f"- cluster(size={cluster['count']})")
            for entry in cluster["tests"][:8]:
                lines.append(f"  - {entry}")

    lines.append("")
    lines.append("## Top Possibly Uncovered Symbols")
    lines.append("")
    for item in report["coverage"]["possibly_uncovered_symbols"][:40]:
        lines.append(f"- {item['symbol']} ({item['file']}:{item['line']})")

    lines.append("")
    lines.append("## Potentially Invalid Tests")
    lines.append("")
    for item in report["invalid_tests"][:60]:
        lines.append(f"- {item['test']} :: {item['reason']}")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit test quality and structure.")
    parser.add_argument(
        "--root",
        default=".",
        help="Project root path (default: current directory)",
    )
    parser.add_argument(
        "--json-out",
        default="comprehensive_test_results/test_governance_audit.json",
        help="Path for JSON report",
    )
    parser.add_argument(
        "--md-out",
        default="comprehensive_test_results/test_governance_audit.md",
        help="Path for markdown report",
    )
    parser.add_argument(
        "--fail-on-duplicates",
        type=int,
        default=0,
        help="Fail if duplicate cluster count exceeds threshold",
    )
    parser.add_argument(
        "--fail-on-invalid",
        type=int,
        default=0,
        help="Fail if invalid test count exceeds threshold",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    allowlist = _load_allowlist(root)
    symbols = extract_source_symbols(root)
    tests = extract_tests(root)

    coverage = build_symbol_coverage(symbols, tests, allowlist["uncovered_symbols_allowlist"])
    duplicates = detect_duplicate_tests(tests, allowlist["duplicate_clusters_allowlist"])
    invalid = detect_invalid_tests(tests, allowlist["invalid_tests_allowlist"])
    sharding = language_sharding(root)

    report = {
        "summary": {
            "source_symbols": len(symbols),
            "test_cases": len(tests),
            "possibly_uncovered_symbols": len(coverage["possibly_uncovered_symbols"]),
            "duplicate_clusters": len(duplicates),
            "invalid_tests": len(invalid),
        },
        "coverage": coverage,
        "duplicates": duplicates,
        "invalid_tests": invalid,
        "language_sharding": sharding,
    }

    json_out = (root / args.json_out).resolve()
    md_out = (root / args.md_out).resolve()
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)

    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_report(report, md_out)

    print(f"[audit] JSON report: {json_out}")
    print(f"[audit] Markdown report: {md_out}")
    print(
        "[audit] summary: "
        f"symbols={report['summary']['source_symbols']} "
        f"tests={report['summary']['test_cases']} "
        f"uncovered={report['summary']['possibly_uncovered_symbols']} "
        f"duplicates={report['summary']['duplicate_clusters']} "
        f"invalid={report['summary']['invalid_tests']}"
    )

    if args.fail_on_duplicates and len(duplicates) > args.fail_on_duplicates:
        print(
            f"[audit] FAIL: duplicate cluster count {len(duplicates)} > {args.fail_on_duplicates}"
        )
        return 2

    if args.fail_on_invalid and len(invalid) > args.fail_on_invalid:
        print(f"[audit] FAIL: invalid test count {len(invalid)} > {args.fail_on_invalid}")
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
