"""Symbol search helpers extracted from query_tool.py."""

import fnmatch
from pathlib import Path
from typing import Any

from ...utils import setup_logger

logger = setup_logger(__name__)

_TYPE_MAP = {
    "class": {"class_definition", "class_declaration", "class"},
    "function": {"function_definition", "function_declaration", "function"},
    "method": {"method_definition", "method_declaration", "method"},
    "variable": {"variable_definition", "variable_declaration", "variable", "assignment"},
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
_SYMBOL_SEARCH_EXCLUDE = {
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
    ".claude",
}


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
    """Search for a symbol definition across all project source files."""
    symbol = arguments.get("symbol", "").strip()
    if not symbol:
        raise ValueError("symbol must be a non-empty string")

    output_format = arguments.get("output_format", "toon")
    language = arguments.get("language")
    symbol_type = arguments.get("symbol_type")

    if not project_root:
        raise ValueError("Project root not set. Call set_project_path first.")

    root = Path(project_root).resolve()
    if not root.is_dir():
        raise ValueError(f"Project root is not a directory: {root}")

    match_fn = _build_match_fn(symbol)
    type_filter = _build_type_filter(symbol_type)

    # Collect source files
    source_files: list[Path] = []
    for ext in _SYMBOL_SEARCH_EXTS:
        for f in root.rglob(f"*{ext}"):
            if any(part in _SYMBOL_SEARCH_EXCLUDE for part in f.parts):
                continue
            source_files.append(f)

    max_files = 500
    if len(source_files) > max_files:
        source_files = source_files[:max_files]

    import asyncio

    from ...core.analysis_engine import AnalysisRequest, get_analysis_engine
    from ...language_detector import detect_language_from_file

    engine = get_analysis_engine(str(root))
    results: list[dict[str, Any]] = []

    async def _search_file(fp: Path) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        lang = language or detect_language_from_file(str(fp))
        if lang == "unknown":
            return matches

        try:
            req = AnalysisRequest(
                file_path=str(fp), language=lang, include_details=False
            )
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

    batch_size = 50
    for i in range(0, len(source_files), batch_size):
        batch = source_files[i : i + batch_size]
        batch_results = await asyncio.gather(*[_search_file(fp) for fp in batch])
        for matches in batch_results:
            results.extend(matches)

    pattern_desc = symbol
    if "*" in symbol:
        pattern_desc = f"wildcard '{symbol}'"
    elif symbol.startswith("~"):
        pattern_desc = f"fuzzy '{symbol[1:]}'"

    response: dict[str, Any] = {
        "success": True,
        "symbol": symbol,
        "files_searched": min(len(source_files), max_files),
        "matches_found": len(results),
        "definitions": results[:50],
        "smart_workflow_hint": (
            f"Found {len(results)} match(es) for {pattern_desc}. "
            "Use extract_code_section to read the implementation, "
            "or analyze_dependencies mode=blast_radius to see usage impact."
        )
        if results
        else f"No matches for {pattern_desc}. Try a different pattern.",
    }

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
