"""
ProjectCodeMap — One-shot project analysis engine for LLM consumption.

Extracted from __init__.py to follow SRP (Fowler P0 #1).
This module contains the scanning engine that discovers, parses, and indexes
project source files into a CodeMapResult.
"""

from __future__ import annotations

import logging
import os
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.core.code_map.call_index import extract_call_sites
from tree_sitter_analyzer_v2.core.code_map.constants import PUBLIC_API_PATTERNS
from tree_sitter_analyzer_v2.core.code_map.decorators import extract_decorated_entries
from tree_sitter_analyzer_v2.core.code_map.parallel import parse_file_standalone
from tree_sitter_analyzer_v2.core.code_map.result import CodeMapResult
from tree_sitter_analyzer_v2.core.code_map.types import ModuleInfo, SymbolInfo, _FileCache
from tree_sitter_analyzer_v2.core.detector import LanguageDetector
from tree_sitter_analyzer_v2.core.parser_registry import (
    get_all_parsers,
    get_ext_lang_map,
)

# Maximum entries in the file-level parse cache (LRU eviction)
_FILE_CACHE_MAX_SIZE = 2000

logger = logging.getLogger(__name__)


class ProjectCodeMap:
    """One-shot project analysis engine for LLM consumption."""

    def __init__(self) -> None:
        self._detector = LanguageDetector()
        # Resolved from ParserRegistry (DIP: core doesn't import languages directly)
        self._parsers: dict[str, Any] = get_all_parsers()
        self._EXT_LANG_MAP: dict[str, str] = get_ext_lang_map()
        # Incremental scan: mtime-based file-level cache with LRU eviction
        self._file_cache: OrderedDict[str, _FileCache] = OrderedDict()
        self._file_cache_max_size: int = _FILE_CACHE_MAX_SIZE
        self._last_project_dir: str | None = None

    def scan(
        self,
        project_dir: str,
        extensions: list[str] | None = None,
        exclude_dirs: list[str] | None = None,
    ) -> CodeMapResult:
        """Scan entire project and build comprehensive code map.

        Uses mtime-based file-level caching: unchanged files are not re-parsed.

        Returns:
            CodeMapResult with scan_duration_ms set for observability.
        """
        t_start = time.perf_counter()
        if extensions is None:
            extensions = [".py", ".java", ".ts", ".js", ".tsx", ".jsx"]
        if exclude_dirs is None:
            exclude_dirs = [
                "__pycache__", "node_modules", ".git", ".venv", "venv",
                "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
                "htmlcov", ".eggs", "*.egg-info",
            ]

        root = Path(project_dir)

        # Invalidate cache if project changed
        if project_dir != self._last_project_dir:
            self._file_cache.clear()
            self._last_project_dir = project_dir

        # 1. Discover all source files
        files = self._discover_files(root, extensions, exclude_dirs)

        # 2. Build set of discovered relative paths (for deletion detection)
        file_by_rel = _compute_file_map(files, root)

        # 3. Remove cache entries for deleted files
        for cached_path in list(self._file_cache.keys()):
            if cached_path not in file_by_rel:
                del self._file_cache[cached_path]

        # 4. Separate cache hits from misses
        result = CodeMapResult(project_dir=project_dir)
        to_parse: list[tuple[str, Path, int]] = []

        for rel_path in sorted(file_by_rel):
            file_path = file_by_rel[rel_path]
            try:
                current_mtime = file_path.stat().st_mtime_ns
            except OSError:
                continue

            cached = self._file_cache.get(rel_path)
            if cached is not None and cached.mtime_ns == current_mtime:
                result.modules.append(cached.module)
            else:
                to_parse.append((rel_path, file_path, current_mtime))

        # 5. Parse cache-miss files in parallel (ThreadPool)
        cache_hits = len(result.modules)
        if to_parse:
            logger.info("Parsing %d files (%d cached)", len(to_parse), cache_hits)
            self._parse_files_parallel(root, to_parse, result)
        else:
            logger.info("All %d files cached, no parsing needed", cache_hits)

        # 6. Rebuild derived data
        self._build_symbol_index(result)
        self._build_dependencies(result)
        self._detect_entry_points(result)
        self._detect_dead_code(result)
        self._compute_hot_spots(result)

        scan_duration_ms = (time.perf_counter() - t_start) * 1000
        result.scan_duration_ms = scan_duration_ms
        logger.info(
            "Scan complete in %.1fms: %d files, %d symbols, %d deps, %d dead, %d hot",
            scan_duration_ms,
            result.total_files, result.total_symbols,
            len(result.module_dependencies), len(result.dead_code),
            len(result.hot_spots),
        )
        return result

    # Thread pool size: configurable via TSA_MAX_WORKERS env var, default min(8, cpu_count)
    _MAX_WORKERS: int = int(os.environ.get(
        "TSA_MAX_WORKERS", str(min(8, os.cpu_count() or 4))
    ))

    def _cache_put(self, key: str, entry: _FileCache) -> None:
        """Insert into file cache with LRU eviction."""
        if key in self._file_cache:
            self._file_cache.move_to_end(key)
        self._file_cache[key] = entry
        # Evict oldest entries if over capacity
        while len(self._file_cache) > self._file_cache_max_size:
            self._file_cache.popitem(last=False)

    def _parse_files_parallel(
        self,
        root: Path,
        to_parse: list[tuple[str, Path, int]],
        result: CodeMapResult,
    ) -> None:
        """Parse multiple files in parallel using ThreadPoolExecutor."""
        if len(to_parse) <= 2:
            for rel_path, file_path, mtime_ns in to_parse:
                module = self._parse_file(root, file_path)
                if module:
                    self._cache_put(rel_path, _FileCache(mtime_ns=mtime_ns, module=module))
                    result.modules.append(module)
            return

        workers = min(self._MAX_WORKERS, len(to_parse))

        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_info = {
                pool.submit(
                    parse_file_standalone,
                    str(root),
                    str(file_path),
                    rel_path,
                    self._EXT_LANG_MAP,
                ): (rel_path, mtime_ns)
                for rel_path, file_path, mtime_ns in to_parse
            }
            for future in as_completed(future_to_info):
                rel_path, mtime_ns = future_to_info[future]
                try:
                    module = future.result()
                    if module:
                        self._cache_put(rel_path, _FileCache(mtime_ns=mtime_ns, module=module))
                        result.modules.append(module)
                except Exception as e:
                    logger.warning("Parallel parse failed for %s: %s", rel_path, e)

    def _discover_files(
        self, root: Path, extensions: list[str], exclude_dirs: list[str]
    ) -> list[Path]:
        """Discover all source files in the project.

        Performance: Single directory traversal using os.walk instead of
        N separate rglob calls (one per extension). This reduces I/O by
        a factor of len(extensions).
        """
        ext_set = frozenset(e.lower() for e in extensions)
        # Exact-match set for O(1) dir exclusion (T-1 perf fix)
        exclude_exact = frozenset(excl.rstrip("*").rstrip(".") for excl in exclude_dirs)

        files: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune excluded child directories in-place — O(D) with frozenset lookup
            dirnames[:] = [d for d in dirnames if d not in exclude_exact]

            for filename in filenames:
                if os.path.splitext(filename)[1].lower() in ext_set:
                    files.append(Path(dirpath) / filename)

        return sorted(files)

    def _parse_file(self, root: Path, file_path: Path) -> ModuleInfo | None:
        """Parse a single file and extract structure + AST call sites."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            rel_path = str(file_path.relative_to(root)).replace("\\", "/")

            language = self._EXT_LANG_MAP.get(file_path.suffix.lower())

            if not language:
                detection = self._detector.detect_from_content(
                    content, filename=file_path.name
                )
                if not detection or not detection.get("language"):
                    return None
                language = detection["language"].lower()

            if language not in self._parsers:
                return None

            parsed = self._parsers[language].parse(content, str(file_path))
            lines = len(content.splitlines())
            functions = parsed.get("functions", [])
            classes = parsed.get("classes", [])

            # Shared call-site extraction (single source of truth in call_index)
            call_sites = extract_call_sites(
                parsed.get("ast"), language, functions, classes
            )

            decorated_entries = extract_decorated_entries(
                functions, classes, ast_node=parsed.get("ast")
            )

            return ModuleInfo(
                path=rel_path,
                language=language,
                lines=lines,
                classes=classes,
                functions=functions,
                imports=parsed.get("imports", []),
                call_sites=call_sites,
                decorated_entries=decorated_entries,
            )
        except Exception as e:
            logger.warning("Failed to parse file %s: %s", file_path, e)
            return None

    def _build_symbol_index(self, result: CodeMapResult) -> None:
        """Build global symbol index from all parsed modules."""
        for module in result.modules:
            for func in module.functions:
                result.symbols.append(SymbolInfo(
                    name=func.get("name", ""),
                    kind="function",
                    file=module.path,
                    line_start=func.get("line_start", 0),
                    line_end=func.get("line_end", 0),
                    params=_join_params(func.get("parameters", [])),
                    return_type=func.get("return_type", "") or "",
                ))
            for cls in module.classes:
                bases_raw: list[str] = (
                    cls.get("bases", [])
                    or cls.get("implements", [])
                    or cls.get("extends", [])
                )
                if cls.get("extends") and cls.get("implements"):
                    bases_raw = list(cls.get("extends", [])) + list(cls.get("implements", []))
                result.symbols.append(SymbolInfo(
                    name=cls.get("name", ""),
                    kind="class",
                    file=module.path,
                    line_start=cls.get("line_start", 0),
                    line_end=cls.get("line_end", 0),
                    bases=bases_raw,
                ))
                for method in cls.get("methods", []):
                    result.symbols.append(SymbolInfo(
                        name=method.get("name", ""),
                        kind="method",
                        file=module.path,
                        line_start=method.get("line_start", 0),
                        line_end=method.get("line_end", 0),
                        params=_join_params(method.get("parameters", [])),
                        return_type=method.get("return_type", "") or "",
                        parent_class=cls.get("name", ""),
                    ))

    def _build_dependencies(self, result: CodeMapResult) -> None:
        """Build module dependency graph from imports."""
        module_paths = {m.path for m in result.modules}
        for module in result.modules:
            for imp in module.imports:
                # Defensive: skip non-dict import entries
                if not isinstance(imp, dict):
                    continue
                target = self._resolve_import(imp, module.path, module_paths)
                if target and target != module.path:
                    result.module_dependencies.append((module.path, target))

    def _resolve_import(
        self, imp: dict[str, Any], source: str, known_modules: set[str]
    ) -> str | None:
        """Resolve an import to a known module path.

        Resolution strategy (ordered by precision):
        1. Exact path match: 'foo.bar' -> 'foo/bar.py' or 'foo/bar/__init__.py'
        2. Suffix match: 'foo.bar' matches 'src/foo/bar.py' (dotted-suffix)
        """
        module_name: str = str(imp.get("module", ""))
        if not module_name:
            return None

        # Strategy 1: Exact path candidates
        candidates: list[str] = [
            module_name.replace(".", "/") + ".py",
            module_name.replace(".", "/") + "/__init__.py",
            module_name + ".py",
        ]
        for candidate in candidates:
            if candidate in known_modules:
                return candidate

        # Strategy 2: Suffix match — known module's dotted path ends with module_name
        # e.g., module_name='core.parser' matches 'tree_sitter_analyzer_v2/core/parser.py'
        # But NOT: module_name='parser' matching 'tree_sitter_analyzer_v2/core/my_parser.py'
        dotted_suffix = "." + module_name  # e.g., '.core.parser'
        for known in known_modules:
            base = known.replace("/", ".").removesuffix(".py").removesuffix(".__init__")
            if base == module_name or base.endswith(dotted_suffix):
                return known

        return None

    def _detect_entry_points(self, result: CodeMapResult) -> None:
        """Detect entry points: main(), __main__, CLI commands, etc."""
        seen_fqns: set[str] = set()
        for sym in result.symbols:
            if (
                sym.kind == "function"
                and sym.name in ("main", "cli", "run", "app")
                and sym.fqn not in seen_fqns
            ):
                result.entry_points.append(sym)
                seen_fqns.add(sym.fqn)

    def _detect_dead_code(self, result: CodeMapResult) -> None:
        """Detect internal functions that are never called or referenced."""
        caller_map, _ = result._get_call_index()

        externally_imported: set[str] = set()
        for module in result.modules:
            for imp in module.imports:
                if not isinstance(imp, dict):
                    continue
                for name in imp.get("names", []):
                    externally_imported.add(name)

        public_api_files: set[str] = set()
        for module in result.modules:
            basename = module.path.rsplit("/", 1)[-1] if "/" in module.path else module.path
            if basename in PUBLIC_API_PATTERNS:
                public_api_files.add(module.path)

        all_decorated: set[str] = set()
        for module in result.modules:
            all_decorated |= module.decorated_entries

        entry_fqns = {ep.fqn for ep in result.entry_points}
        called_fqns = set(caller_map.keys())

        for sym in result.symbols:
            if sym.kind not in ("function", "method"):
                continue
            if sym.name.startswith("_"):
                continue
            if sym.fqn in entry_fqns:
                continue
            if sym.name in externally_imported:
                continue
            if sym.file in public_api_files:
                continue
            if sym.name in all_decorated:
                continue
            if sym.fqn in called_fqns:
                continue
            result.dead_code.append(sym)

    def _compute_hot_spots(self, result: CodeMapResult) -> None:
        """Compute symbols with most callers (highest impact if changed)."""
        caller_map, _ = result._get_call_index()

        fqn_call_count: dict[str, int] = {}
        for callee_fqn, callers in caller_map.items():
            fqn_call_count[callee_fqn] = len(callers)

        name_import_count: dict[str, int] = {}
        for module in result.modules:
            for imp in module.imports:
                if not isinstance(imp, dict):
                    continue
                for name in imp.get("names", []):
                    name_import_count[name] = name_import_count.get(name, 0) + 1

        scored: list[tuple[SymbolInfo, int]] = []
        for sym in result.symbols:
            call_refs = fqn_call_count.get(sym.fqn, 0)
            import_refs = 0
            if sym.kind in ("function", "class"):
                import_refs = name_import_count.get(sym.name, 0)
            total = call_refs + import_refs
            if total > 0:
                scored.append((sym, total))
        scored.sort(key=lambda x: x[1], reverse=True)
        result.hot_spots = scored[:20]


# ──────────────── Module-level helpers ────────────────


def _join_params(params: list[Any]) -> str:
    """Join parameter list into a comma-separated string.

    Handles two formats returned by different language parsers:
    - Python: ['x', 'y'] (list of str)
    - Java:   [{'name': 'x', 'type': 'int'}] (list of dict)

    Filters out 'self' parameter.
    """
    parts: list[str] = []
    for p in params:
        if isinstance(p, str):
            if p != "self":
                parts.append(p)
        elif isinstance(p, dict):
            name = p.get("name", "")
            if name and name != "self":
                parts.append(name)
        else:
            parts.append(str(p))
    return ",".join(parts)


# ── Pure functions (Functional Core) ──
# These contain no I/O or mutable state, making them easy to test.


def _compute_file_map(files: list[Path], root: Path) -> dict[str, Path]:
    """Build a relative-path → absolute-path mapping from discovered files.

    Pure function: no I/O, no side-effects.
    """
    result: dict[str, Path] = {}
    for file_path in files:
        rel = str(file_path.relative_to(root)).replace("\\", "/")
        result[rel] = file_path
    return result
