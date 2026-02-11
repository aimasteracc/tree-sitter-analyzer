"""Test architecture audit analyzer."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from tree_sitter_analyzer_v2.core.code_map.types import (
        ArchitectureTestReport,
        ModuleInfo,
        SymbolInfo,
    )

# Standard test layer directories
_TEST_LAYERS = ("unit", "integration", "system", "e2e")
# Patterns for tool/API/CLI source files
_TOOL_PATTERNS = ("mcp/tools/", "mcp/server", "cli/", "api/", "api.")


def audit_test_architecture(
    project_dir: str,
    modules: list[ModuleInfo],
    symbols: list[SymbolInfo],
    hot_spots: list[tuple[SymbolInfo, int]],
    test_roots: list[str] | None = None,
) -> ArchitectureTestReport:
    """Audit project test architecture using import-based matching.

    Uses three signals to match tests to source (in priority order):
    1. Import analysis: test file imports from source module (most precise)
    2. File name convention: test_foo.py tests foo.py (fallback)
    3. Symbol reference: test calls functions/classes defined in source
    """
    from tree_sitter_analyzer_v2.core.code_map.types import ArchitectureTestReport

    project_root = Path(project_dir)

    # 1. Classify source files
    source_files: list[str] = []
    source_module_map: dict[str, str] = {}

    for m in modules:
        p = m.path
        basename = Path(p).name
        if basename.startswith("test_") or basename.endswith("_test.py"):
            continue
        if basename == "__init__.py":
            continue
        if "/testing/" in p or "/tests/" in p or "/test/" in p:
            continue
        source_files.append(p)
        mod_name = p.replace("/", ".").replace("\\", ".").removesuffix(".py")
        source_module_map[mod_name] = p
        source_module_map[Path(p).stem] = p

    # 2. Discover & parse test files
    test_files: list[str] = []
    test_imports: dict[str, list[str]] = {}
    test_func_counts: dict[str, int] = {}
    test_symbols_referenced: dict[str, set[str]] = {}

    def _scan_test_dir(root: Path, rel_prefix: str = "") -> None:
        for pattern in ("test_*.py", "*_test.py"):
            for tf in sorted(root.rglob(pattern)):
                if "__pycache__" in str(tf):
                    continue
                rel = str(tf.relative_to(root)).replace("\\", "/")
                full_rel = f"{rel_prefix}{rel}" if rel_prefix else rel
                if full_rel in test_files:
                    continue
                test_files.append(full_rel)

                try:
                    content = tf.read_text(encoding="utf-8", errors="replace")
                    func_count = sum(
                        1 for line in content.splitlines()
                        if line.strip().startswith("def test_")
                        or line.strip().startswith("async def test_")
                    )
                    test_func_counts[full_rel] = func_count

                    imports: list[str] = []
                    referenced_names: set[str] = set()
                    for line in content.splitlines():
                        m = re.match(r"from\s+([\w.]+)\s+import\s+(.+)", line.strip())
                        if m:
                            imports.append(m.group(1))
                            for name in m.group(2).split(","):
                                name = name.strip().split(" as ")[0].strip()
                                if name and name != "*":
                                    referenced_names.add(name)
                        m2 = re.match(r"import\s+([\w.]+)", line.strip())
                        if m2:
                            imports.append(m2.group(1))
                    test_imports[full_rel] = imports
                    test_symbols_referenced[full_rel] = referenced_names
                except Exception as e:
                    _logger.warning("Failed to scan test file %s: %s", full_rel, e)
                    test_func_counts[full_rel] = 0
                    test_imports[full_rel] = []
                    test_symbols_referenced[full_rel] = set()

    _scan_test_dir(project_root)
    if test_roots:
        for tr in test_roots:
            tr_path = Path(tr)
            if tr_path.exists():
                _scan_test_dir(tr_path, rel_prefix="[ext] ")

    # 3. Match source to tests (import-based + name-based)
    import_matched: dict[str, list[str]] = {}

    for tf, imports in test_imports.items():
        for imp_module in imports:
            parts = imp_module.split(".")
            for i in range(len(parts)):
                suffix = ".".join(parts[i:])
                if suffix in source_module_map:
                    src_path = source_module_map[suffix]
                    import_matched.setdefault(src_path, []).append(tf)
                    break

    name_matched: dict[str, list[str]] = {}
    for tf in test_files:
        tf_stem = Path(tf.split("/")[-1]).stem
        tested_name = tf_stem.replace("test_", "", 1).replace("_test", "")
        if tested_name in source_module_map:
            src_path = source_module_map[tested_name]
            name_matched.setdefault(src_path, []).append(tf)

    all_matched: dict[str, list[str]] = {}
    for src in source_files:
        tests = set()
        tests.update(import_matched.get(src, []))
        tests.update(name_matched.get(src, []))
        if tests:
            all_matched[src] = sorted(tests)

    tested_files = sorted(all_matched.keys())
    untested_files_set = set(source_files) - set(tested_files)

    # 4. Symbol-level coverage
    source_file_set = set(source_files)
    source_symbol_names: set[str] = set()
    for sym in symbols:
        if sym.file in source_file_set:
            source_symbol_names.add(sym.name)

    all_test_refs: set[str] = set()
    for refs in test_symbols_referenced.values():
        all_test_refs |= refs

    tested_symbol_names = source_symbol_names & all_test_refs
    total_source_syms = len(source_symbol_names)
    sym_coverage = (len(tested_symbol_names) / total_source_syms * 100) if total_source_syms > 0 else 0

    # 5. Risk-sort untested files (hot spots first)
    hot_files: dict[str, int] = {}
    for sym, refs in hot_spots:
        hot_files[sym.file] = hot_files.get(sym.file, 0) + refs

    untested_list = sorted(
        untested_files_set,
        key=lambda f: hot_files.get(f, 0),
        reverse=True,
    )

    # 6. Detect test layers
    test_layers: dict[str, list[str]] = {}
    for tf in test_files:
        for layer in _TEST_LAYERS:
            if f"/{layer}/" in tf or tf.startswith(f"{layer}/") or f"[ext] {layer}/" in tf:
                test_layers.setdefault(layer, []).append(tf)
                break
        else:
            test_layers.setdefault("uncategorized", []).append(tf)

    missing_layers = [lay for lay in _TEST_LAYERS if lay not in test_layers]

    # 7. Detect untested tools
    untested_tools: list[str] = [
        src for src in untested_list
        if any(pat in src for pat in _TOOL_PATTERNS)
    ]

    # 8. Detect duplicate coverage
    duplicate_coverage: list[tuple[str, list[str]]] = [
        (src, tests) for src, tests in all_matched.items() if len(tests) > 1
    ]

    # 9. Compute file coverage
    total_source = len(source_files)
    coverage_pct = (len(tested_files) / total_source * 100) if total_source > 0 else 0
    total_test_funcs = sum(test_func_counts.values())

    return ArchitectureTestReport(
        source_files=source_files,
        test_files=test_files,
        untested_files=untested_list,
        tested_files=tested_files,
        test_layers=test_layers,
        missing_layers=missing_layers,
        untested_tools=untested_tools,
        duplicate_coverage=duplicate_coverage,
        coverage_percent=coverage_pct,
        total_source_symbols=total_source_syms,
        tested_symbols=len(tested_symbol_names),
        symbol_coverage_percent=sym_coverage,
        total_test_functions=total_test_funcs,
        test_quality=test_func_counts,
        import_matched=import_matched,
    )
