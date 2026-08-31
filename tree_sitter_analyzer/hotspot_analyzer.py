"""Hotspot scorer: Ca x MaxCC ranking with alias-aware Ca."""
from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter_analyzer.complexity_heatmap import FileHeatmap
    from tree_sitter_analyzer.dependency_matrix import DependencyMatrix

from tree_sitter_analyzer.output_schema import (
    HotspotEntry,
    TestFocus,
)

SEVERITY_CRITICAL = 400
SEVERITY_REVIEW = 100
MAX_DEPTH_CAP = 5
SUGGESTION_BY_SEVERITY = {
    "CRITICAL": "test edge cases and error paths",
    "REVIEW": "test boundary values",
    "OK": "(low impact, skip)",
}


# ── Ca helpers ────────────────────────────────────────────────────────────────

def build_ca_raw_map(dm: DependencyMatrix) -> dict[str, int]:
    """Return {file: afferent_coupling} from DependencyMatrix module_stats.

    Reads dm._result.module_stats after dm.build() has been called.
    Does NOT call build() internally — caller must have called dm.build() first.
    """
    if dm._result is None:
        return {}
    return {s.file: s.afferent_coupling for s in dm._result.module_stats}


# ── Heatmap helpers ───────────────────────────────────────────────────────────

def build_heatmap_map(heatmap_files: list[FileHeatmap]) -> dict[str, FileHeatmap]:
    """Return {file: FileHeatmap} for O(1) lookup (forward-slash normalized)."""
    return {fh.file.replace("\\", "/"): fh for fh in heatmap_files}


# Directories that are clearly not the main source package
_NON_SOURCE_DIRS = frozenset({
    "tests", "test", "benchmarks", "bench", "docs", "doc", "examples",
    "example", "scripts", "script", "fixtures", "compatibility_test",
    "build", "dist", "e2e", "spec", "integration", "functional",
    "performance", "samples", "demo", "demos", "corpus",
})


def _detect_source_dir(project_root: str) -> str | None:
    """Return the Python source package directory directly under project_root.

    Tries pyproject.toml [tool.hatch.build.targets.wheel] packages first,
    then falls back to heuristic: first child dir with __init__.py that is
    not a well-known non-source directory (tests/, benchmarks/, etc.).
    """
    root = Path(project_root)

    # Try pyproject.toml (hatch, setuptools, flit)
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            try:
                import tomli as tomllib  # noqa: PLC0415
            except ImportError:
                tomllib = None
        if tomllib is not None:
            try:
                data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
                # hatch: [tool.hatch.build.targets.wheel] packages = ["mypkg"]
                pkgs = (
                    data.get("tool", {})
                    .get("hatch", {})
                    .get("build", {})
                    .get("targets", {})
                    .get("wheel", {})
                    .get("packages", [])
                )
                # setuptools: [tool.setuptools] packages = ["mypkg"] or find
                if not pkgs:
                    pkgs = (
                        data.get("tool", {})
                        .get("setuptools", {})
                        .get("packages", [])
                    )
                if pkgs and isinstance(pkgs, list):
                    pkg = pkgs[0]
                    if isinstance(pkg, str) and (root / pkg / "__init__.py").exists():
                        return pkg
            except Exception:
                pass

    # Heuristic fallback: first non-test package dir with __init__.py
    try:
        for child in sorted(root.iterdir()):
            name = child.name
            if (
                child.is_dir()
                and (child / "__init__.py").exists()
                and name not in _NON_SOURCE_DIRS
                and not name.startswith((".", "_"))
            ):
                return name
    except OSError:
        pass
    return None


def heatmaps_from_project_analysis(project_root: str, max_files: int = 200) -> list[FileHeatmap]:
    """Build FileHeatmap list using analyze_project_heatmap() result.

    Scopes to the main source package (via __init__.py detection) to avoid
    wasting file slots on tests/, benchmarks/, corpus/ that appear first
    alphabetically and would crowd out the actual source code.
    """
    from tree_sitter_analyzer.complexity_heatmap import (
        FileHeatmap as _FileHeatmap,
    )
    from tree_sitter_analyzer.complexity_heatmap import (
        FunctionComplexity,
        analyze_project_heatmap,
    )

    # Focus on the main source package to avoid alphabetical ordering issues.
    # Ca data comes from build_ca_from_source_imports separately, so this
    # scope restriction only affects complexity — not coupling measurement.
    directory_filter = _detect_source_dir(project_root)

    result = analyze_project_heatmap(
        project_root,
        directory_filter=directory_filter,
        max_files=max_files,
    )
    heatmaps: list[_FileHeatmap] = []
    for fh_dict in result.get("file_heatmaps", []):
        top_funcs = fh_dict.get("top_functions", [])
        funcs = [
            FunctionComplexity(
                name=f.get("name", ""),
                file=fh_dict.get("file", ""),
                line=f.get("line", 0),
                end_line=f.get("line", 0),
                complexity=f.get("complexity", 0),
                language=fh_dict.get("language", ""),
                class_name=None,
                decision_points={},
            )
            for f in top_funcs
        ]
        heatmaps.append(_FileHeatmap(
            file=fh_dict.get("file", ""),
            language=fh_dict.get("language", ""),
            functions=funcs,
            total_complexity=fh_dict.get("total_complexity", 0),
            avg_complexity=fh_dict.get("avg_complexity", 0.0),
            max_complexity=fh_dict.get("max_complexity", 0),
        ))
    return heatmaps


def _resolve_import_mod(
    raw_mod: str, current_rel: str, file_set: set[str]
) -> str | None:
    """Resolve an import module string to a canonical relative path.

    Handles both absolute imports (from tree_sitter_analyzer.foo import X)
    and relative imports (from .foo import X) by inferring the package prefix
    from the current file's path.

    Returns the resolved path (forward-slash) if it exists in file_set, else None.
    """
    # Count leading dots for relative imports
    leading_dots = len(raw_mod) - len(raw_mod.lstrip("."))
    mod = raw_mod.lstrip(".")

    if leading_dots > 0:
        # Relative import: resolve relative to current file's directory
        parts = current_rel.replace("\\", "/").split("/")
        pkg_parts = parts[:-1]  # directory of current file
        for _ in range(leading_dots - 1):
            if pkg_parts:
                pkg_parts = pkg_parts[:-1]
        if mod:
            mod_path = "/".join(pkg_parts + [mod.replace(".", "/")])
        else:
            # `from . import X` — package is the directory itself
            mod_path = "/".join(pkg_parts)
    else:
        if not mod:
            return None
        mod_path = mod.replace(".", "/")

    for suffix in (f"{mod_path}.py", f"{mod_path}/__init__.py"):
        if suffix in file_set:
            return suffix
    return None


def _iter_resolved_imports(
    text: str, rel_path: str, file_set: set[str]
) -> Iterator[str]:
    """Yield resolved import target paths from Python source text (no duplicates).

    Two-pass approach:
    - Pass 1: standard dotted imports  (from pkg.mod import X, from .mod import X)
    - Pass 2: bare relative imports    (from . import X, from .. import X, Y)
    Pass 1 skips bare-dot patterns so they are handled exclusively by pass 2.
    """
    import re as _re

    seen: set[str] = set()

    # Pass 1: "from X.y import Z" and "import X.y", including "from .mod import Z"
    for match in _re.finditer(
        r"^(?:from\s+(\.?[\w.]+)\s+import|import\s+([\w.]+))",
        text,
        _re.MULTILINE,
    ):
        raw_mod = match.group(1) or match.group(2) or ""
        leading_dots = len(raw_mod) - len(raw_mod.lstrip("."))
        mod = raw_mod.lstrip(".")
        # Skip bare-dot patterns (e.g. raw_mod == "." or ".."); pass 2 handles them.
        if leading_dots > 0 and not mod:
            continue
        resolved = _resolve_import_mod(raw_mod, rel_path, file_set)
        if resolved and resolved not in seen:
            seen.add(resolved)
            yield resolved

    # Pass 2: bare relative imports — "from . import X" / "from .. import X, Y"
    for match in _re.finditer(
        r"^from\s+(\.+)\s+import\s+([^\n#\\]+)",
        text,
        _re.MULTILINE,
    ):
        dots = match.group(1)
        names_str = match.group(2)
        for raw_name in _re.split(r"[\s,]+", names_str.strip()):
            # Strip "as alias" suffix and leading/trailing punctuation
            name = raw_name.split(" ")[0].split("(")[0].rstrip(",").strip()
            if not name or not name.isidentifier():
                continue
            resolved = _resolve_import_mod(dots + name, rel_path, file_set)
            if resolved and resolved not in seen:
                seen.add(resolved)
                yield resolved


def build_import_edges_from_source(
    project_root: str,
    scan_files: list[str],
) -> dict[str, dict[str, int]]:
    """Build import edge graph by parsing Python import statements from source.

    Returns {src_file: {tgt_file: count}} where src imports tgt.
    Paths are normalized to forward slashes for cross-platform consistency.
    Handles absolute, relative (from .foo), and bare relative (from . import foo).
    """
    root = Path(project_root)
    scan_norm = [p.replace("\\", "/") for p in scan_files]
    file_set = set(scan_norm)
    edges: dict[str, dict[str, int]] = {}

    for rel_path in scan_norm:
        if not rel_path.endswith(".py"):
            continue
        try:
            text = (root / rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for resolved in _iter_resolved_imports(text, rel_path, file_set):
            tgts = edges.setdefault(rel_path, {})
            tgts[resolved] = tgts.get(resolved, 0) + 1

    return edges


def build_ca_from_source_imports(
    project_root: str,
    scan_files: list[str],
    target_files: list[str] | None = None,
) -> dict[str, int]:
    """Build Ca map by parsing Python import statements directly from source files.

    Fallback for when DependencyMatrix has no cache data (cache not built yet).
    Handles all Python import forms including bare relative imports.

    scan_files: all project Python files to scan for import statements
    target_files: files to measure Ca FOR (defaults to scan_files when None)

    Paths are normalized to forward slashes for cross-platform matching.
    """
    root = Path(project_root)

    scan_norm = [p.replace("\\", "/") for p in scan_files]
    target_norm = [p.replace("\\", "/") for p in (target_files if target_files is not None else scan_files)]
    file_set = set(target_norm)
    ca_count: dict[str, int] = {}

    for rel_path in scan_norm:
        if not rel_path.endswith(".py"):
            continue
        try:
            text = (root / rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for resolved in _iter_resolved_imports(text, rel_path, file_set):
            ca_count[resolved] = ca_count.get(resolved, 0) + 1

    return ca_count


# ── Severity & test_focus ─────────────────────────────────────────────────────

def classify_severity(score: float) -> str:
    if score >= SEVERITY_CRITICAL:
        return "CRITICAL"
    if score >= SEVERITY_REVIEW:
        return "REVIEW"
    return "OK"


def build_test_focus(file_heatmap: FileHeatmap, severity: str) -> TestFocus:
    """Extract highest-CC function and attach severity-based suggestion."""
    funcs = sorted(file_heatmap.functions, key=lambda f: f.complexity, reverse=True)
    if funcs:
        top = funcs[0]
        return TestFocus(
            function=top.name,
            cc=top.complexity,
            suggestion=SUGGESTION_BY_SEVERITY[severity],
        )
    return TestFocus(
        function="(no functions)",
        cc=0,
        suggestion=SUGGESTION_BY_SEVERITY[severity],
    )


# ── Main scorer ───────────────────────────────────────────────────────────────

def compute_scores(
    ca_map: dict[str, int],          # {file: ca_raw}
    heatmap_map: dict[str, FileHeatmap],
    alias_ca_map: dict[str, int] | None = None,  # {file: ca_alias} — None = P2
    reachable: dict[str, int] | None = None,      # {file: hops}  — None = global mode
    top_n: int = 20,
    show_alias_diff: bool = False,
) -> list[HotspotEntry]:
    """Compute and rank HotspotEntry list.

    Returns entries sorted descending by score, limited to top_n.
    alias_ca_map: if None, ca_alias == ca_raw (P2 behaviour).
    reachable:    if not None, restrict to files in this map (P5 behaviour).
    """
    files = set(ca_map) | set(heatmap_map)
    if reachable is not None:
        files = files & set(reachable)

    entries: list[HotspotEntry] = []
    for f in files:
        ca_raw = ca_map.get(f, 0)
        ca_alias = alias_ca_map.get(f, ca_raw) if alias_ca_map is not None else ca_raw
        fh = heatmap_map.get(f)
        max_cc = fh.max_complexity if fh else 0
        score = float(ca_alias * max_cc)
        severity = classify_severity(score)
        test_focus = (
            build_test_focus(fh, severity) if fh
            else TestFocus("(unknown)", 0, SUGGESTION_BY_SEVERITY[severity])
        )
        hops = reachable[f] if reachable is not None else None
        entries.append(HotspotEntry(
            rank=0,  # assigned below
            file=f,
            severity=severity,
            score=score,
            ca_raw=ca_raw,
            ca_alias=ca_alias,
            max_cc=max_cc,
            test_focus=test_focus,
            hops=hops,
        ))

    entries.sort(key=lambda e: e.score, reverse=True)
    entries = entries[:max(0, top_n)]
    for i, e in enumerate(entries, 1):
        e.rank = i
    return entries


# ── P3: alias-aware Ca ────────────────────────────────────────────────────────

def _parse_python_reexports(init_path: Path) -> list[str]:
    """Return list of module names re-exported from __init__.py.

    Parses lines of the form:
      from .foo import Bar       -> adds "foo" (sibling module)
      from .subpkg.baz import X  -> adds "subpkg/baz"
    Dynamic imports and star imports are skipped.
    """
    results: list[str] = []
    try:
        text = init_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return results
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("from .") and " import " in line:
            after_from = line[len("from ."):].split(" import ")[0].strip()
            if after_from and "*" not in line:
                # convert dotted to path
                results.append(after_from.replace(".", "/"))
    return results


def _parse_ts_reexports(index_path: Path) -> list[str]:
    """Return list of relative module paths re-exported from index.ts/index.js.

    Parses: export { Foo } from './foo'  or  export * from './bar'
    """
    results: list[str] = []
    try:
        text = index_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return results
    for line in text.splitlines():
        m = re.search(r"from\s+['\"](\./[^'\"]+)['\"]", line)
        if m and line.strip().startswith("export"):
            rel = m.group(1).lstrip("./")
            results.append(rel)
    return results


def build_alias_ca_map(
    ca_raw_map: dict[str, int],
    import_edges: dict[str, dict[str, int]],
    project_root: str,
    known_files: list[str] | None = None,
) -> dict[str, int]:
    """Return {file: ca_alias} by augmenting ca_raw with alias-chain counts.

    Scans __init__.py (Python) and index.ts/index.js (TS/JS) in project_root.
    Files not seen in init/index re-exports keep ca_alias == ca_raw.

    known_files: pre-collected list of relative paths (forward-slash normalized).
      When provided, avoids expensive rglob walks for large repos on Windows.

    Short-circuits when import_edges is empty (no DM cache data) to avoid
    an expensive rglob walk that would produce no useful results anyway.
    """
    if not import_edges:
        return dict(ca_raw_map)

    root = Path(project_root)
    alias_extra: dict[str, int] = {}  # {canonical_file: extra_count}

    # Use pre-collected file list to avoid slow rglob on large directory trees
    if known_files is not None:
        _init_py_paths = [
            root / p for p in known_files if p.endswith("__init__.py")
        ]
    else:
        _init_py_paths = list(root.rglob("__init__.py"))

    # Find all __init__.py files
    for init_path in _init_py_paths:
        re_exported = _parse_python_reexports(init_path)
        try:
            init_rel = str(init_path.relative_to(root)).replace("\\", "/")
        except ValueError:
            continue
        # Count how many files import via this __init__.py
        importers_of_init = sum(
            1 for src in import_edges if init_rel in import_edges[src]
        )
        for mod in re_exported:
            # Candidate canonical paths
            for suffix in [f"{mod}.py", f"{mod}/__init__.py"]:
                if (root / suffix).exists():
                    alias_extra[suffix] = alias_extra.get(suffix, 0) + importers_of_init
                    break

    # Find all index.ts / index.js files
    for index_name in ("index.ts", "index.js"):
        if known_files is not None:
            _index_paths: list[Path] = [
                root / p for p in known_files
                if p.endswith(f"/{index_name}") or p == index_name
            ]
        else:
            _index_paths = list(root.rglob(index_name))
        for index_path in _index_paths:
            re_exported = _parse_ts_reexports(index_path)
            try:
                index_rel = str(index_path.relative_to(root)).replace("\\", "/")
            except ValueError:
                continue
            importers_of_index = sum(
                1 for src in import_edges if index_rel in import_edges[src]
            )
            for mod in re_exported:
                for suffix in [f"{mod}.ts", f"{mod}.js", f"{mod}/index.ts"]:
                    if (root / suffix).exists():
                        alias_extra[suffix] = alias_extra.get(suffix, 0) + importers_of_index
                        break

    result = dict(ca_raw_map)
    for f, extra in alias_extra.items():
        result[f] = result.get(f, 0) + extra
    return result
