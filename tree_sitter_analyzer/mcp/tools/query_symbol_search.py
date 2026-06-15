"""Symbol search helpers extracted from query_tool.py."""

import fnmatch
from pathlib import Path
from typing import Any

from ...ast_cache import ASTCache
from ...constants import EXCLUDE_DIRS
from ...utils import setup_logger

logger = setup_logger(__name__)

_TYPE_MAP = {
    "class": {"class_definition", "class_declaration", "class"},
    "function": {"function_definition", "function_declaration", "function"},
    "method": {"method_definition", "method_declaration", "method"},
    "variable": {
        "variable_definition",
        "variable_declaration",
        "variable",
        "assignment",
    },
    "import": {"import_statement", "import_from_statement", "import"},
}

_SYMBOL_SEARCH_EXTS = {
    ".py",
    ".java",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".go",
    ".rs",
    ".kt",
    ".cs",
    ".rb",
    ".php",
    ".c",
    ".cpp",
}
# r37bc: scan limits — module-level so the file collection helper +
# response envelope cap stay in sync (was a magic 500 / 50 in 2+ places).
_SYMBOL_SEARCH_MAX_FILES = 500
_SYMBOL_SEARCH_BATCH_SIZE = 50


def categorize_queries(query_names: list[str], language: str) -> dict[str, list[str]]:
    """Group query names into categories for better AI agent discoverability."""
    categories: dict[str, list[str]] = {
        "common": [],
        "declarations": [],
        "control_flow": [],
        "framework": [],
        "other": [],
    }
    common_keys = {"classes", "methods", "functions", "imports", "variables"}
    decl_keywords = {
        "class",
        "struct",
        "enum",
        "interface",
        "trait",
        "record",
        "type",
        "module",
        "namespace",
        "field",
        "property",
        "method",
        "function",
        "fn",
        "constructor",
    }
    flow_keywords = {"if", "for", "while", "switch", "try", "catch", "loop", "match"}
    framework_keywords = {
        "spring",
        "react",
        "jpa",
        "http",
        "authorize",
        "decorator",
        "annotation",
        "attribute",
        "async",
        "goroutine",
        "channel",
        "linq",
        "lambda",
    }

    for name in query_names:
        if name in common_keys:
            categories["common"].append(name)
        elif any(kw in name.lower() for kw in decl_keywords):
            categories["declarations"].append(name)
        elif any(kw in name.lower() for kw in flow_keywords):
            categories["control_flow"].append(name)
        elif any(kw in name.lower() for kw in framework_keywords):
            categories["framework"].append(name)
        else:
            categories["other"].append(name)

    return {k: v for k, v in categories.items() if v}


async def execute_symbol_search(
    project_root: str | None,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Search for a symbol definition across all project source files.

    r37bc (dogfood): tool flagged this at 108 lines. Split into argument
    validation + file collection + scatter + assembly. Behaviour
    preserved (max_files=500, batch_size=50, exact/wildcard/fuzzy
    matching, toon formatting).
    G1: FTS5 BM25 ranked fast-path tried first for plain symbol names >= 2 chars.
    """
    symbol, output_format, language, symbol_type = _parse_symbol_search_args(arguments)
    root = _resolve_project_root(project_root)

    # FTS5 fast path — only for plain names, not wildcards or fuzzy patterns
    if len(symbol) >= 2 and "*" not in symbol and not symbol.startswith("~"):
        fts_results = _try_fts_ranked_search(root, symbol, language)
        if fts_results:
            return _assemble_symbol_search_response(
                symbol,
                output_format,
                [],
                fts_results,
                ranked=True,
                ranking_method="fts5_bm25",
            )

    match_fn = _build_match_fn(symbol)
    type_filter = _build_type_filter(symbol_type)
    source_files = _collect_source_files(root)

    results = await _scatter_symbol_search(
        root, source_files, language, match_fn, type_filter
    )
    return _assemble_symbol_search_response(
        symbol, output_format, source_files, results
    )


def _parse_symbol_search_args(
    arguments: dict[str, Any],
) -> tuple[str, str, str | None, str | None]:
    """Validate + extract the 4 inputs ``execute_symbol_search`` needs."""
    symbol = arguments.get("symbol", "").strip()
    if not symbol:
        raise ValueError("symbol must be a non-empty string")
    output_format = arguments.get("output_format", "toon")
    language = arguments.get("language")
    symbol_type = arguments.get("symbol_type")
    return symbol, output_format, language, symbol_type


def _resolve_project_root(project_root: str | None) -> Path:
    """Validate ``project_root`` and return its resolved ``Path``."""
    if not project_root:
        raise ValueError("Project root not set. Call set_project_path first.")
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise ValueError(f"Project root is not a directory: {root}")
    return root


def _collect_source_files(root: Path) -> list[Path]:
    """Walk ``root`` for source files, applying excludes + the 500 cap.

    Uses the shared EXCLUDE_DIRS constant (single source of truth) and also
    skips any path component that starts with '.' (generic dotdir guard,
    e.g. .benchmark-repos, .vendored) so vendored/build/dot trees cannot
    consume the 500-file budget before real source is reached (#568).
    """
    source_files: list[Path] = []
    for ext in _SYMBOL_SEARCH_EXTS:
        for f in root.rglob(f"*{ext}"):
            # Codex P2 (#699): check only the parts BELOW the project root.
            # Using ``f.parts`` (absolute) wrongly excludes the whole project
            # when the root itself lives under a dotted/excluded-named ancestor
            # (e.g. a checkout at ``~/.local/share/proj`` or ``/build/proj``).
            try:
                parts = f.relative_to(root).parts
            except ValueError:  # pragma: no cover - rglob(root) only yields descendants
                parts = f.parts
            if any(part in EXCLUDE_DIRS for part in parts):
                continue
            if any(part.startswith(".") for part in parts):
                continue
            source_files.append(f)
    if len(source_files) > _SYMBOL_SEARCH_MAX_FILES:
        source_files = source_files[:_SYMBOL_SEARCH_MAX_FILES]
    return source_files


async def _scatter_symbol_search(
    root: Path,
    source_files: list[Path],
    language: str | None,
    match_fn: Any,
    type_filter: Any,
) -> list[dict[str, Any]]:
    """Run per-file symbol search in 50-file batches, return flat result list."""
    import asyncio

    from ...core.analysis_engine import AnalysisRequest, get_analysis_engine
    from ...language_detector import detect_language_from_file

    engine = get_analysis_engine(str(root))

    async def _search_file(fp: Path) -> list[dict[str, Any]]:
        return await _search_one_file_for_symbol(
            fp,
            root,
            engine,
            language,
            match_fn,
            type_filter,
            AnalysisRequest,
            detect_language_from_file,
        )

    results: list[dict[str, Any]] = []
    for i in range(0, len(source_files), _SYMBOL_SEARCH_BATCH_SIZE):
        batch = source_files[i : i + _SYMBOL_SEARCH_BATCH_SIZE]
        batch_results = await asyncio.gather(*[_search_file(fp) for fp in batch])
        for matches in batch_results:
            results.extend(matches)
    return results


async def _search_one_file_for_symbol(
    fp: Path,
    root: Path,
    engine: Any,
    language: str | None,
    match_fn: Any,
    type_filter: Any,
    AnalysisRequest: Any,
    detect_language_from_file: Any,
) -> list[dict[str, Any]]:
    """Per-file symbol search — analyze, filter by name + type, collect hits."""
    matches: list[dict[str, Any]] = []
    lang = language or detect_language_from_file(str(fp))
    if lang == "unknown":
        return matches
    try:
        req = AnalysisRequest(file_path=str(fp), language=lang, include_details=False)
        result = await engine.analyze(req)
        if not result or not result.success:
            return matches
        for e in result.elements:
            name = getattr(e, "name", "")
            etype = getattr(e, "element_type", "")
            if not match_fn(name):
                continue
            if type_filter and not type_filter(etype):
                continue
            matches.append(
                {
                    "name": name,
                    "type": etype,
                    "file": str(fp.relative_to(root)),
                    "start_line": getattr(e, "start_line", 0),
                    "end_line": getattr(e, "end_line", 0),
                }
            )
    except Exception:  # nosec B110
        pass
    return matches


def _fts_symbol_to_match(row: dict[str, Any], root: Path) -> dict[str, Any]:
    """Convert a fts_search_ranked row to the standard match dict shape."""
    return {
        "name": row["name"],
        "type": row["kind"],
        "file": row["file"],
        "start_line": row["line"],
        "end_line": row["end_line"],
        "relevance_score": row["relevance_score"],
    }


def _try_fts_ranked_search(
    root: Path,
    symbol: str,
    language: str | None,
) -> list[dict[str, Any]]:
    """Try the FTS5 BM25 fast path. Returns [] on any failure or miss."""
    try:
        cache = ASTCache(str(root))
        rows = cache.fts_search_ranked(symbol, language=language, limit=500)
        return [_fts_symbol_to_match(r, root) for r in rows]
    except Exception:
        return []


def _assemble_symbol_search_response(
    symbol: str,
    output_format: str,
    source_files: list[Path],
    results: list[dict[str, Any]],
    *,
    ranked: bool = False,
    ranking_method: str = "",
) -> dict[str, Any]:
    """Build the canonical ``execute_symbol_search`` envelope."""
    pattern_desc = symbol
    if "*" in symbol:
        pattern_desc = f"wildcard '{symbol}'"
    elif symbol.startswith("~"):
        pattern_desc = f"fuzzy '{symbol[1:]}'"

    response: dict[str, Any] = {
        "success": True,
        "symbol": symbol,
        "files_searched": min(len(source_files), _SYMBOL_SEARCH_MAX_FILES),
        "matches_found": len(results),
        "definitions": results[:50],
        "smart_workflow_hint": (
            (
                f"Found {len(results)} match(es) for {pattern_desc}. "
                "Use extract_code_section to read the implementation, "
                "or analyze_dependencies mode=blast_radius to see usage impact."
            )
            if results
            else f"No matches for {pattern_desc}. Try a different pattern."
        ),
    }
    if ranked:
        response["ranked"] = True
        response["ranking_method"] = ranking_method
    from ..utils.format_helper import apply_toon_format_to_response

    return apply_toon_format_to_response(response, output_format)


def _build_match_fn(symbol: str) -> Any:
    """Build a name-matching function based on the symbol pattern.

    - Plain name: exact match (backward compatible)
    - * wildcards: fnmatch (e.g., '*Service', 'handle_*', '*_test_*')
    - ~ prefix: fuzzy substring match (e.g., '~analyz' matches 'analyze_file')
    """
    if symbol.startswith("~"):
        substring = symbol[1:].lower()

        def fuzzy(name: str) -> bool:
            return substring in name.lower()

        return fuzzy

    if "*" in symbol:
        pattern = symbol.lower()

        def wildcard(name: str) -> bool:
            return fnmatch.fnmatch(name.lower(), pattern)

        return wildcard

    def exact(name: str) -> bool:
        return name == symbol

    return exact


def _build_type_filter(symbol_type: str | None) -> Any:
    """Build an element type filter function."""
    if not symbol_type:
        return None

    allowed = _TYPE_MAP.get(symbol_type)
    if not allowed:
        return None

    def type_check(etype: str) -> bool:
        etype_lower = etype.lower()
        return any(a in etype_lower for a in allowed)

    return type_check


async def execute_find_references(
    project_root: str | None,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Find all references (call sites / usages) of a symbol across the project.

    Unlike execute_symbol_search which finds definitions, this finds every
    location where the symbol is used — call expressions, attribute access,
    type annotations, decorators, etc.

    r37bc (dogfood): tool flagged this at 154 lines / nesting depth 9.
    Split into argument parse + scatter + assembly + per-element handler.
    Behaviour preserved (max_files=500, batch_size=50, role semantics).
    """
    symbol, output_format = _parse_find_references_args(arguments)
    root = _resolve_project_root(project_root)
    bare_name = symbol.split(".")[-1] if "." in symbol else symbol

    source_files = _collect_source_files(root)
    definitions, references = await _scatter_find_references(
        root, source_files, bare_name
    )
    return _assemble_find_references_response(
        symbol, output_format, source_files, definitions, references
    )


def _parse_find_references_args(arguments: dict[str, Any]) -> tuple[str, str]:
    """Validate + extract symbol + output_format from arguments."""
    symbol = arguments.get("symbol", "").strip()
    if not symbol:
        raise ValueError("symbol must be a non-empty string")
    output_format = arguments.get("output_format", "toon")
    return symbol, output_format


async def _scatter_find_references(
    root: Path,
    source_files: list[Path],
    bare_name: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run per-file reference scan in 50-file batches, return (defs, refs)."""
    import asyncio

    from ...core.analysis_engine import AnalysisRequest, get_analysis_engine
    from ...language_detector import detect_language_from_file

    engine = get_analysis_engine(str(root))
    references: list[dict[str, Any]] = []
    definitions: list[dict[str, Any]] = []
    seen_refs: set[tuple[str, int]] = set()

    async def _scan_one(
        fp: Path,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return await _scan_file_for_references(
            fp,
            root,
            engine,
            bare_name,
            seen_refs,
            AnalysisRequest,
            detect_language_from_file,
        )

    for i in range(0, len(source_files), _SYMBOL_SEARCH_BATCH_SIZE):
        batch = source_files[i : i + _SYMBOL_SEARCH_BATCH_SIZE]
        batch_results = await asyncio.gather(*[_scan_one(fp) for fp in batch])
        for file_refs, file_defs in batch_results:
            references.extend(file_refs)
            definitions.extend(file_defs)
    return definitions, references


async def _scan_file_for_references(
    fp: Path,
    root: Path,
    engine: Any,
    bare_name: str,
    seen_refs: set[tuple[str, int]],
    AnalysisRequest: Any,
    detect_language_from_file: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """One file's contribution to references + definitions."""
    refs: list[dict[str, Any]] = []
    defs: list[dict[str, Any]] = []
    lang = detect_language_from_file(str(fp))
    if lang == "unknown":
        return refs, defs
    try:
        req = AnalysisRequest(file_path=str(fp), language=lang, include_details=False)
        result = await engine.analyze(req)
        if not result or not result.success:
            return refs, defs
        rel = str(fp.relative_to(root))
        for e in result.elements:
            _classify_element_for_references(e, rel, bare_name, seen_refs, refs, defs)
    except Exception:  # nosec B110
        pass
    return refs, defs


def _classify_element_for_references(
    e: Any,
    rel: str,
    bare_name: str,
    seen_refs: set[tuple[str, int]],
    refs: list[dict[str, Any]],
    defs: list[dict[str, Any]],
) -> None:
    """Sort a single AST element into definitions / references / related buckets.

    r37bc: extracted from the inner-most level of ``_scan_file`` (nesting
    depth 9) — the body is now ≤3 levels deep.
    """
    name = getattr(e, "name", "")
    etype = getattr(e, "element_type", "")
    start = getattr(e, "start_line", 0)
    end = getattr(e, "end_line", 0)

    if name == bare_name:
        if _is_definition_element(etype):
            defs.append(_make_reference_row(name, etype, rel, start, end, "definition"))
        else:
            _record_unique_ref(
                rel, start, seen_refs, refs, name, etype, end, "reference"
            )
        return

    if name != bare_name and bare_name in name:
        for part in name.replace("_", " ").split():
            if part == bare_name:
                _record_unique_ref(
                    rel, start, seen_refs, refs, name, etype, end, "related"
                )
                break


def _is_definition_element(etype: str) -> bool:
    """Return True if an element type string represents a definition/declaration."""
    etype_lower = etype.lower()
    return any(
        kw in etype_lower for kw in ("definition", "declaration", "class", "struct")
    )


def _make_reference_row(
    name: str, etype: str, rel: str, start: int, end: int, role: str
) -> dict[str, Any]:
    """Canonical row shape for both definitions + references."""
    return {
        "name": name,
        "type": etype,
        "file": rel,
        "start_line": start,
        "end_line": end,
        "role": role,
    }


def _record_unique_ref(
    rel: str,
    start: int,
    seen_refs: set[tuple[str, int]],
    refs: list[dict[str, Any]],
    name: str,
    etype: str,
    end: int,
    role: str,
) -> None:
    """Append a reference row only if (rel, start) hasn't been seen yet."""
    key = (rel, start)
    if key in seen_refs:
        return
    seen_refs.add(key)
    refs.append(_make_reference_row(name, etype, rel, start, end, role))


def _assemble_find_references_response(
    symbol: str,
    output_format: str,
    source_files: list[Path],
    definitions: list[dict[str, Any]],
    references: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the canonical ``execute_find_references`` envelope."""
    total = len(references) + len(definitions)
    caller_refs = [r for r in references if r.get("role") == "reference"]

    if total > 0:
        hint = (
            f"Found {len(definitions)} definition(s) and {len(references)} "
            f"reference(s) for '{symbol}'. "
            "Use extract_code_section to read any reference in context, "
            "or analyze_dependencies mode=blast_radius for file-level impact."
        )
    else:
        hint = f"No usages found for '{symbol}'. Try a different name."

    response: dict[str, Any] = {
        "success": True,
        "symbol": symbol,
        "files_searched": min(len(source_files), _SYMBOL_SEARCH_MAX_FILES),
        "total_usages": total,
        "definitions": definitions[:20],
        "references": references[:50],
        "callers_count": len(caller_refs),
        "smart_workflow_hint": hint,
    }
    from ..utils.format_helper import apply_toon_format_to_response

    return apply_toon_format_to_response(response, output_format)
