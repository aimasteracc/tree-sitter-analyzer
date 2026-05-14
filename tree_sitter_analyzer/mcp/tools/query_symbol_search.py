"""Symbol search helpers extracted from query_tool.py."""

from pathlib import Path
from typing import Any

from ...utils import setup_logger

logger = setup_logger(__name__)

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

    if not project_root:
        raise ValueError("Project root not set. Call set_project_path first.")

    root = Path(project_root).resolve()
    if not root.is_dir():
        raise ValueError(f"Project root is not a directory: {root}")

    # Collect source files
    source_files: list[Path] = []
    for ext in _SYMBOL_SEARCH_EXTS:
        for f in root.rglob(f"*{ext}"):
            if any(part in _SYMBOL_SEARCH_EXCLUDE for part in f.parts):
                continue
            source_files.append(f)

    # Limit to prevent memory issues
    max_files = 500
    if len(source_files) > max_files:
        source_files = source_files[:max_files]

    # Search using the analysis engine
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
                if name == symbol:
                    etype = getattr(e, "element_type", "")
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

    # Process in batches to control memory
    batch_size = 50
    for i in range(0, len(source_files), batch_size):
        batch = source_files[i : i + batch_size]
        batch_results = await asyncio.gather(*[_search_file(fp) for fp in batch])
        for matches in batch_results:
            results.extend(matches)

    response: dict[str, Any] = {
        "success": True,
        "symbol": symbol,
        "files_searched": min(len(source_files), max_files),
        "matches_found": len(results),
        "definitions": results[:50],
        "smart_workflow_hint": (
            f"Found {len(results)} definition(s) for '{symbol}'. "
            "Use extract_code_section to read the implementation, "
            "or analyze_dependencies mode=blast_radius to see usage impact."
        )
        if results
        else f"No definitions found for '{symbol}'. Try a different name or check spelling.",
    }

    from ..utils.format_helper import apply_toon_format_to_response

    return apply_toon_format_to_response(response, output_format)
