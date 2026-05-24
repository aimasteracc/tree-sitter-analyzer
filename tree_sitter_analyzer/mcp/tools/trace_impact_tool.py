#!/usr/bin/env python3
"""
Trace Impact Tool

Lightweight impact analysis tool that finds all call sites of a symbol (method/class/function)
using ripgrep. Unlike full call graph solutions, this provides fast "usage tracing" without
requiring a graph database.

This tool is inspired by GitNexus's impact analysis but optimized for tree-sitter-analyzer's
architecture, reusing existing ripgrep infrastructure.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from ...language_detector import LanguageDetector, detect_language_from_file
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from ._graph_cache_fingerprint import _SOURCE_EXTS
from .base_tool import BaseMCPTool
from .fd_rg_utils import (
    build_rg_command,
    parse_rg_json_lines_to_matches,
    run_command_capture,
)

# Set up logging
logger = setup_logger(__name__)

# H4 fix: restrict trace_impact to source-code extensions so the "CALLERS"
# count is not inflated by CHANGELOG.md / design.md / comment matches.
# Mirrors the SOURCE_EXTS list used for graph fingerprinting so the call
# count, the dependency graph, and the impact badge all describe the same
# universe of files. Globs are rooted at any depth (``**/*.py`` style) so
# ripgrep ``-g`` accepts them without translation.
_SOURCE_EXT_GLOBS: tuple[str, ...] = tuple(f"**/*{ext}" for ext in _SOURCE_EXTS)


def _filter_source_matches(
    matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """H4 fix: drop hits whose file extension is not in ``_SOURCE_EXTS``.

    The ``-g`` flag passed to ripgrep already restricts the search at the
    boundary; this is a belt-and-braces filter so that ``call_count`` is
    honest even when ``-g`` is bypassed (e.g. a future change adds
    ``--no-ignore`` or a custom glob). The cost is O(n) over hits that
    have already been parsed once.
    """
    if not matches:
        return matches
    return [match for match in matches if _is_source_file(match.get("file", ""))]


def _is_source_file(file_path: str) -> bool:
    """Return ``True`` if ``file_path`` ends with a known source extension."""
    if not file_path:
        return False
    lower = file_path.lower()
    return any(lower.endswith(ext) for ext in _SOURCE_EXTS)


# J7 (round-22): even after H4's extension filter, docstring and comment
# hits inside ``.py``/``.ts``/etc still inflate ``source_call_count`` — a
# line like ``"""ARCH-A4 regression: BaseMCPTool.set_project_path..."""``
# is counted as a caller. Heuristic-based classification (regex + triple-
# quote state) is good enough: full AST lookup per hit is too expensive
# for trace_impact, which runs on many matches at once.
_PY_LIKE_EXTS = (".py",)
_C_LIKE_EXTS = (
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".cc",
    ".cxx",
    ".h",
    ".hpp",
    ".hxx",
)

# Match either a triple-double-quote or triple-single-quote token at any
# position on the line. We don't try to handle prefix strings (``r"""``,
# ``f"""``) specially — the leading prefix is fine, we just look at the
# triple-quote run itself.
_PY_TRIPLE_QUOTE_RE = re.compile(r'(?:"""|\'\'\')')


def _python_non_code_lines(text: str) -> set[int]:
    # Heuristic Python-comment / docstring detector. Returns 1-based line
    # numbers that are comment-only OR inside a triple-quoted string.
    #
    # Rules:
    # * Lines whose first non-whitespace character is ``#`` count as comments.
    # * Lines fully inside a triple-quoted string count as docstring text.
    # * The line that opens a triple-quote AND the line that closes it
    #   are both flagged — even if the opener has code before the triple
    #   quote, we err on the side of dropping the hit. False negatives
    #   (treating a real call site as a docstring) are visible to the
    #   caller via the ``raw_match_count`` field, and a slight over-filter
    #   is acceptable per the brief.
    #
    # Doesn't track escape sequences inside the string — a triple-quote
    # inside a docstring is impossible to write in pure-string form
    # anyway, so a naive token count works.
    non_code: set[int] = set()
    in_triple = False
    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        # Count how many triple-quote tokens appear on this line. The
        # state-machine: each triple-quote run toggles the inside-string
        # flag. Open-and-close on the same line cancels out.
        toggles = len(_PY_TRIPLE_QUOTE_RE.findall(line))
        if in_triple:
            # Already inside a docstring → this line is docstring text.
            non_code.add(idx)
            if toggles % 2 == 1:
                in_triple = False
            continue
        if toggles >= 1:
            # Opening (and possibly closing on the same line) — treat
            # the line itself as docstring so opener content like an
            # ARCH-A4 regression docstring header is dropped.
            non_code.add(idx)
            if toggles % 2 == 1:
                in_triple = True
            continue
        # Plain comment line.
        if stripped.startswith("#"):
            non_code.add(idx)
    return non_code


def _c_like_non_code_lines(text: str) -> set[int]:
    """Return 1-based line numbers that are ``//`` comments or inside ``/* */`` blocks.

    Tracks ``/* ... */`` state across lines. Doesn't try to honour string
    literals (``"http://example.com"`` will look like ``//`` to this
    scanner) — acceptable per the J7 brief, which prefers a heuristic
    over per-hit AST lookups.
    """
    non_code: set[int] = set()
    in_block = False
    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if in_block:
            non_code.add(idx)
            if "*/" in line:
                in_block = False
                # If after closing the block there's only whitespace,
                # the line stays purely comment. If real code follows
                # ``*/``, treating the line as non-code is a small
                # over-filter — acceptable.
            continue
        if stripped.startswith("//"):
            non_code.add(idx)
            continue
        if "/*" in line:
            non_code.add(idx)
            # Check whether the block also closes on the same line.
            close_idx = line.find("*/", line.find("/*") + 2)
            if close_idx == -1:
                in_block = True
    return non_code


@lru_cache(maxsize=512)
def _file_non_code_lines(file_path: str) -> frozenset[int]:
    """Read ``file_path`` once and compute the set of comment/docstring lines.

    Cached so a single ``trace_impact`` call with N hits across M files
    pays the file-read cost M times, not N times. The cache is process-
    local; in MCP-server mode the same files get read again on a fresh
    invocation, which is fine — they're typically already in the OS page
    cache.
    """
    lower = file_path.lower()
    try:
        text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        # File disappeared / unreadable → assume nothing is non-code so
        # we don't accidentally hide every hit.
        return frozenset()
    if lower.endswith(_PY_LIKE_EXTS):
        return frozenset(_python_non_code_lines(text))
    if lower.endswith(_C_LIKE_EXTS):
        return frozenset(_c_like_non_code_lines(text))
    return frozenset()


def _filter_comment_docstring_matches(
    matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop hits whose line is inside a comment or docstring.

    Called AFTER ``_filter_source_matches`` so we only pay the file-read
    cost for hits that survived the extension filter. The pair of filters
    together gives an honest ``source_call_count``:

    * Extension filter (H4): drops markdown / CHANGELOG hits.
    * Comment/docstring filter (J7): drops hits inside ``#`` / ``//`` /
      ``/* */`` / Python triple-quoted strings.
    """
    if not matches:
        return matches
    kept: list[dict[str, Any]] = []
    for match in matches:
        file_path = match.get("file", "")
        line_no = match.get("line")
        if not file_path or not isinstance(line_no, int):
            kept.append(match)
            continue
        non_code = _file_non_code_lines(file_path)
        if line_no in non_code:
            continue
        kept.append(match)
    return kept


def _get_impact_level(count: int) -> dict[str, str]:
    """
    Return a severity dict for a given caller count.

    Args:
        count: Number of callers found for a symbol

    Returns:
        Dictionary with level, badge, and guidance keys
    """
    if count == 0:
        return {
            "level": "none",
            "badge": "✅ NO CALLERS",
            "guidance": "Safe to modify or delete.",
        }
    elif count <= 5:
        # r37s (dogfood): hardcoded ``caller(s)`` is a placeholder for
        # unknown plurality. We already KNOW count here (1-5), so render
        # proper singular/plural English ("1 caller" / "3 callers").
        caller_word = "caller" if count == 1 else "callers"
        return {
            "level": "low",
            "badge": "⚠️ LOW IMPACT",
            "guidance": f"{count} {caller_word} found. Review before modifying.",
        }
    elif count <= 20:
        return {
            "level": "medium",
            "badge": "🔶 MEDIUM IMPACT",
            "guidance": (
                f"{count} callers found. "
                "Check all call sites before changing the signature."
            ),
        }
    else:
        return {
            "level": "high",
            "badge": f"🚨 HIGH IMPACT — {count} CALLERS",
            "guidance": (
                f"{count} callers across the codebase. "
                "Do NOT modify signature without updating all callers. "
                "Consider deprecation strategy."
            ),
        }


def _build_trace_impact_globs(
    language_extensions: list[str],
    exclude_patterns: list[str],
) -> tuple[list[str], list[str]]:
    """Build (include_globs, exclude_globs) for ripgrep.

    r37bw: extracted from ``execute``. Adds common exclude patterns
    (node_modules, .git, vendor, __pycache__, *.min.{js,css}) and either
    language-specific extensions or the project-wide source extension
    set (H4 fix).
    """
    exclude_globs = list(exclude_patterns)
    exclude_globs.extend(
        [
            "**/node_modules/**",
            "**/.git/**",
            "**/vendor/**",
            "**/__pycache__/**",
            "**/*.min.js",
            "**/*.min.css",
        ]
    )
    include_globs: list[str] = []
    if language_extensions:
        for ext in language_extensions:
            include_globs.append(f"**/*{ext}")
    else:
        # H4: restrict to source extensions even without language detection.
        include_globs.extend(_SOURCE_EXT_GLOBS)
    return include_globs, exclude_globs


def _classify_rg_error(rc: int, stderr: bytes | None) -> dict[str, Any] | None:
    """Map ripgrep exit code to an error envelope, or ``None`` on success/no-match.

    r37bw: extracted from ``execute``. rc=127 means rg missing, rc=124
    means timeout, anything other than 0/1 is a real failure. rc=0/1
    return ``None`` so the caller continues to result parsing.
    """
    if rc == 127:
        return {
            "success": False,
            "error": (
                "ripgrep (rg) is not installed. Please install ripgrep "
                "to use trace_impact."
            ),
            "usages": [],
            "call_count": 0,
        }
    if rc == 124:
        return {
            "success": False,
            "error": (
                "Search timed out. Try narrowing the search scope or "
                "excluding more directories."
            ),
            "usages": [],
            "call_count": 0,
        }
    if rc not in (0, 1):
        error_msg = (
            stderr.decode("utf-8", errors="replace") if stderr else "Unknown error"
        )
        return {
            "success": False,
            "error": f"Search failed: {error_msg}",
            "usages": [],
            "call_count": 0,
        }
    return None


def _build_not_found_response(symbol: str, language: str | None) -> dict[str, Any]:
    """M11: ripgrep returned zero matches → NOT_FOUND envelope.

    The typo-vs-real-zero-caller ambiguity is resolved as "verify
    spelling first" to match symbol_lineage's behaviour. ``impact_verdict``
    stays at the magnitude vocab (``NONE`` for zero callers) while
    top-level ``verdict`` flips to ``NOT_FOUND`` so cross-tool readers
    can branch on a single field.
    """
    impact = _get_impact_level(0)
    summary_line = f"trace_impact symbol={symbol} not_found"
    return {
        "success": True,
        "symbol": symbol,
        "language": language,
        "usages": [],
        "call_count": 0,
        "count": 0,
        "results": [],
        "impact_level": impact["level"],
        "impact_verdict": impact["level"].upper(),
        "verdict": "NOT_FOUND",
        "found": False,
        "impact_badge": impact["badge"],
        "impact_guidance": impact["guidance"],
        "message": (
            f"No usages of '{symbol}' found in the project. "
            "Verify symbol name — no definitions or references "
            "exist anywhere in the source tree."
        ),
        "summary_line": summary_line,
        "agent_summary": {
            "summary_line": summary_line,
            "next_step": ("verify symbol name — no definitions or references found"),
            "verdict": "NOT_FOUND",
            "risk": "unknown",
        },
    }


def _truncate_for_display(
    source_matches: list[Any], max_results: int
) -> tuple[list[Any], bool]:
    """Display-cap source matches without affecting impact-level count."""
    if len(source_matches) > max_results:
        return source_matches[:max_results], True
    return source_matches, False


def _matches_to_usages(matches: list[Any]) -> list[dict[str, Any]]:
    """Convert rg matches to usage dicts with both ``file``/``file_path`` aliases."""
    usages: list[dict[str, Any]] = []
    for match in matches:
        line_no = match["line"]
        file_path_val = match["file"]
        usages.append(
            {
                "file": file_path_val,
                "file_path": file_path_val,
                "line": line_no,
                "line_number": line_no,
                "context": match["text"],
            }
        )
    return usages


def _verdict_and_next_step_for_impact(level: str, total_count: int) -> tuple[str, str]:
    """K5: map impact level (magnitude vocab) → (verdict, next_step) (safety vocab)."""
    if level == "high":
        return "UNSAFE", (
            f"batch_search to enumerate all {total_count} call sites before "
            "changing signature"
        )
    if level == "medium":
        return "CAUTION", (
            f"batch_search to enumerate all {total_count} call sites before "
            "changing signature"
        )
    if level == "low":
        return "CAUTION", "review the few callers, then proceed with the change"
    return "SAFE", "no callers — safe to refactor"


def _trace_impact_base_envelope(
    *,
    symbol: str,
    impact: dict[str, Any],
    source_total: int,
    true_total: int,
    usages: list[dict[str, Any]],
    summary_line: str,
    verdict: str,
    next_step: str,
) -> dict[str, Any]:
    """Build the always-present canonical fields of the trace_impact envelope.

    Caller layers conditional fields (``warning`` / ``language`` /
    ``source_file`` / ``truncated`` / ``non_source_match_count``) on top
    via ``_trace_impact_apply_conditional_fields``.
    """
    return {
        "success": True,
        "symbol": symbol,
        "call_count": source_total,
        "count": source_total,
        "source_call_count": source_total,
        "usage_count": len(usages),
        "raw_match_count": true_total,
        "impact_level": impact["level"],
        "impact_verdict": impact["level"].upper(),
        "verdict": verdict,
        "impact_badge": impact["badge"],
        "impact_guidance": impact["guidance"],
        "usages": usages,
        "results": usages,
        "summary_line": summary_line,
        "agent_summary": {
            "summary_line": summary_line,
            "next_step": next_step,
            "verdict": verdict,
        },
    }


def _trace_impact_apply_conditional_fields(
    result: dict[str, Any],
    *,
    impact_level: str,
    source_total: int,
    true_total: int,
    language: str | None,
    file_path: str | None,
    truncated: bool,
    max_results: int,
) -> None:
    """Mutate ``result`` with optional fields based on signal flags.

    Adds in-place:
    - ``warning`` when impact_level == "high" (advises batch_search)
    - ``language`` + ``filtered_by_language`` when a language was inferred
    - ``source_file`` when ``file_path`` was provided
    - ``truncated`` + ``message`` when results overflowed ``max_results``
    - ``non_source_match_count`` when raw matches exceeded source matches
    """
    if impact_level == "high":
        result["warning"] = (
            f"🚨 HIGH IMPACT: This symbol has {source_total} callers. "
            f"Modifying its signature requires updating all call sites. "
            f"Use batch_search to locate all callers before proceeding."
        )
    if language:
        result["language"] = language
        result["filtered_by_language"] = True
    if file_path:
        result["source_file"] = file_path
    if truncated:
        result["truncated"] = True
        result["message"] = (
            f"Results truncated to {max_results} usages. "
            f"Consider narrowing the search scope or increasing max_results."
        )
    if true_total > source_total:
        result["non_source_match_count"] = true_total - source_total


def _build_trace_impact_result(
    *,
    symbol: str,
    language: str | None,
    file_path: str | None,
    usages: list[dict[str, Any]],
    source_total: int,
    true_total: int,
    truncated: bool,
    max_results: int,
) -> dict[str, Any]:
    """Compose the canonical trace_impact success envelope.

    r37bw: extracted from ``execute``. K5 verdict alias, H4 source-only
    counts, optional ``warning`` / ``language`` / ``source_file`` /
    ``truncated`` / ``non_source_match_count`` fields all preserved.

    r37f6 (dogfood): 64 → ~15 lines. Base envelope moved to
    ``_trace_impact_base_envelope``; conditional fields applied via
    ``_trace_impact_apply_conditional_fields``.
    """
    impact = _get_impact_level(source_total)
    summary_line = f"{symbol} callers={source_total} impact={impact['level']}"
    verdict, next_step = _verdict_and_next_step_for_impact(
        impact["level"], source_total
    )
    result = _trace_impact_base_envelope(
        symbol=symbol,
        impact=impact,
        source_total=source_total,
        true_total=true_total,
        usages=usages,
        summary_line=summary_line,
        verdict=verdict,
        next_step=next_step,
    )
    _trace_impact_apply_conditional_fields(
        result,
        impact_level=impact["level"],
        source_total=source_total,
        true_total=true_total,
        language=language,
        file_path=file_path,
        truncated=truncated,
        max_results=max_results,
    )
    return result


# r37f5 (dogfood): static MCP definition lifted out of ``TraceImpactTool``
# so introspection calls don't reconstruct the same 80-line dict every time.
_TRACE_IMPACT_DESCRIPTION: str = (
    "Find every caller and usage site of a symbol across the entire project. "
    "\n\n"
    "REQUIRED before modifying any public function, class, or variable. "
    "Without this, you are editing blindly — you do not know what breaks. "
    "This tool answers: 'if I change X, what else changes?' "
    "\n\n"
    "WHEN TO USE:\n"
    "- ALWAYS call this before renaming, removing, or changing the signature of any "
    "public method, class, or exported variable\n"
    "- Before refactoring code used across multiple files\n"
    "- To understand the blast radius of a deprecation\n"
    "- To verify that a symbol is truly unused before deletion\n"
    "\n"
    "WHEN NOT TO USE:\n"
    "- Private/internal methods (single-underscore prefix) within the same file — "
    "the impact is local and visible in context\n"
    "- Pure comment or docstring edits — no callers are affected\n"
    "- Adding a brand-new symbol that has no existing usages\n"
    "\n"
    "IMPORTANT: Provide file_path when available — this filters results to the same "
    "language, eliminating cross-language false positives. "
    "Set word_match=true (the default) to avoid substring noise."
)


_TRACE_IMPACT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "symbol": {
            "type": "string",
            "description": (
                "Symbol name to trace (method, class, function, or variable name). "
                "Example: 'processPayment', 'UserService', 'calculateTotal'"
            ),
        },
        "file_path": {
            "type": "string",
            "description": (
                "Optional: Source file where the symbol is defined. "
                "If provided, filters results to the same language. "
                "Example: 'src/services/PaymentService.java'"
            ),
        },
        "project_root": {
            "type": "string",
            "description": (
                "Optional: Project root directory to search. "
                "Defaults to the tool's configured project root. "
                "Can provide multiple roots as comma-separated paths."
            ),
        },
        "case_sensitive": {
            "type": "boolean",
            "description": (
                "Whether to perform case-sensitive search. "
                "Default: false (smart case - case-sensitive if symbol has uppercase)"
            ),
        },
        "word_match": {
            "type": "boolean",
            "description": (
                "Whether to match whole words only (not substrings). "
                "Default: true (recommended to avoid false positives)"
            ),
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of results to return. Default: 1000",
        },
        "exclude_patterns": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Optional: Glob patterns to exclude from search. "
                "Example: ['**/test/**', '**/node_modules/**', '**/*.min.js']"
            ),
        },
    },
    "required": ["symbol"],
    # F5: refuse unknown keys; central enforcement is in
    # BaseMCPTool.__init_subclass__.
    "additionalProperties": False,
}


class TraceImpactTool(BaseMCPTool):
    """
    MCP tool for tracing the impact of code changes by finding all usage sites of a symbol.

    This tool uses ripgrep to efficiently search for occurrences of a method, class, or
    function name across the project, optionally filtering by language to reduce noise.
    """

    def __init__(self, project_root: str | None = None) -> None:
        """
        Initialize the trace impact tool.

        Args:
            project_root: Optional project root directory
        """
        super().__init__(project_root)
        self.language_detector = LanguageDetector()

    def get_tool_definition(self) -> dict[str, Any]:
        """Get the MCP tool definition for trace_impact.

        r37f5 (dogfood): 92→5 lines. The 30-line description and 50-line
        inputSchema are now module-level constants
        (``_TRACE_IMPACT_DESCRIPTION`` / ``_TRACE_IMPACT_INPUT_SCHEMA``)
        — they're static and were reconstructed on every introspection
        call by MCP clients.
        """
        return {
            "name": "trace_impact",
            "description": _TRACE_IMPACT_DESCRIPTION,
            "inputSchema": _TRACE_IMPACT_INPUT_SCHEMA,
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        Validate input arguments.

        Args:
            arguments: Tool arguments to validate

        Returns:
            True if arguments are valid

        Raises:
            ValueError: If arguments are invalid
        """
        # 验证 symbol
        symbol = arguments.get("symbol")
        if not symbol or not isinstance(symbol, str) or not symbol.strip():
            raise ValueError(
                "symbol parameter is required and must be a non-empty string"
            )

        # 验证 file_path（如果提供）
        file_path = arguments.get("file_path")
        if file_path is not None and not isinstance(file_path, str):
            raise ValueError("file_path must be a string")

        # 验证 project_root（如果提供）
        project_root = arguments.get("project_root")
        if project_root is not None and not isinstance(project_root, str):
            raise ValueError("project_root must be a string")

        # 验证布尔参数
        for param in ["case_sensitive", "word_match"]:
            value = arguments.get(param)
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"{param} must be a boolean")

        # 验证整数参数
        max_results = arguments.get("max_results")
        if max_results is not None:
            if not isinstance(max_results, int) or max_results <= 0:
                raise ValueError("max_results must be a positive integer")

        # 验证 exclude_patterns
        exclude_patterns = arguments.get("exclude_patterns")
        if exclude_patterns is not None:
            if not isinstance(exclude_patterns, list):
                raise ValueError("exclude_patterns must be an array")
            for pattern in exclude_patterns:
                if not isinstance(pattern, str):
                    raise ValueError("exclude_patterns must contain only strings")

        return True

    @handle_mcp_errors("trace_impact")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute the trace impact tool.

        r37bw (dogfood): tool flagged this at 350 lines. Refactor splits
        the body into focused helpers (arg parse / language detect /
        glob build / rg run / rc-classify / not-found / filter / build).
        Behaviour preserved (M11 NOT_FOUND, H4 source-ext + J7 comment
        filters, K5 verdict alias, agent_summary).
        """
        self.validate_arguments(arguments)

        symbol = arguments["symbol"].strip()
        file_path = arguments.get("file_path")
        case_sensitive = arguments.get("case_sensitive", False)
        word_match = arguments.get("word_match", True)
        max_results = arguments.get("max_results", 1000)
        exclude_patterns = arguments.get("exclude_patterns", [])

        roots = self._resolve_search_roots(arguments.get("project_root"))
        language, language_extensions = self._detect_language_filter(file_path)
        include_globs, exclude_globs = _build_trace_impact_globs(
            language_extensions, exclude_patterns
        )

        cmd = build_rg_command(
            query=symbol,
            case="sensitive" if case_sensitive else "smart",
            fixed_strings=True,
            word=word_match,
            multiline=False,
            include_globs=include_globs if include_globs else None,
            exclude_globs=exclude_globs,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize="10M",
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=5000,
            roots=roots,
            files_from=None,
            count_only_matches=False,
        )
        logger.debug(f"Executing ripgrep command: {' '.join(cmd)}")
        rc, stdout, stderr = await run_command_capture(cmd, timeout_ms=5000)

        rg_error = _classify_rg_error(rc, stderr)
        if rg_error is not None:
            return rg_error

        if rc == 1:
            # M11: ripgrep zero-match → NOT_FOUND envelope (typo vs zero-caller
            # ambiguity resolved as "verify spelling first" per symbol_lineage).
            return _build_not_found_response(symbol, language)

        matches = parse_rg_json_lines_to_matches(stdout)
        ext_filtered = _filter_source_matches(matches)
        source_matches = _filter_comment_docstring_matches(ext_filtered)

        true_total = len(matches)
        source_total = len(source_matches)

        display_matches, truncated = _truncate_for_display(source_matches, max_results)
        usages = _matches_to_usages(display_matches)

        return _build_trace_impact_result(
            symbol=symbol,
            language=language,
            file_path=file_path,
            usages=usages,
            source_total=source_total,
            true_total=true_total,
            truncated=truncated,
            max_results=max_results,
        )

    def _resolve_search_roots(self, project_root_arg: str | None) -> list[str]:
        """Compute the project root list for ripgrep.

        Order: explicit ``project_root_arg`` (comma-split) → tool default
        → cwd. r37bw extracted from execute.
        """
        if project_root_arg:
            return [root.strip() for root in project_root_arg.split(",")]
        if self.project_root:
            return [self.project_root]
        from pathlib import Path

        return [str(Path.cwd())]

    def _detect_language_filter(
        self, file_path: str | None
    ) -> tuple[str | None, list[str]]:
        """Detect language from ``file_path`` and return (language, extensions).

        Returns ``(None, [])`` when ``file_path`` is missing or language
        detection produces ``unknown``. r37bw extracted from execute.
        """
        if not file_path:
            return None, []
        language = detect_language_from_file(file_path, project_root=self.project_root)
        if not language or language == "unknown":
            return language, []
        extensions = self._get_extensions_for_language(language)
        logger.debug(
            f"Detected language '{language}' from file '{file_path}', "
            f"will filter by extensions: {extensions}"
        )
        return language, extensions

    def _get_extensions_for_language(self, language: str) -> list[str]:
        """
        Get file extensions for a given language.

        Args:
            language: Language name (e.g., 'java', 'python', 'javascript')

        Returns:
            List of file extensions (with dots, e.g., ['.java', '.jsp'])
        """
        extensions = []
        for ext, lang in self.language_detector.EXTENSION_MAPPING.items():
            if lang == language:
                extensions.append(ext)
        return extensions
