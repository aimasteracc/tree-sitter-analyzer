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

from pathlib import Path
from typing import Any

from tree_sitter_analyzer.cache.fingerprint import _SOURCE_EXTS

from ...language_detector import LanguageDetector, detect_language_from_file
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool
from .fd_rg_utils import (
    build_rg_command,
    parse_rg_json_lines_to_matches,
    run_command_capture,
)
from .utils.trace_impact_formatter import (
    _TRACE_IMPACT_DESCRIPTION,
    _TRACE_IMPACT_INPUT_SCHEMA,
    _build_not_found_response,
    _build_trace_impact_result,
    _matches_to_usages,
    _truncate_for_display,
)
from .utils.trace_impact_graph_walker import (
    _build_trace_impact_globs,
    _c_like_non_code_lines,  # noqa: F401 — re-exported for test backward compatibility
    _classify_rg_error,
    _file_non_code_lines,  # noqa: F401 — re-exported for test backward compatibility
    _filter_comment_docstring_matches,
    _filter_source_matches,
    _get_impact_level,  # noqa: F401 — re-exported for test backward compatibility
    _is_source_file,  # noqa: F401 — re-exported for test backward compatibility
    _is_symbol_only_in_strings,  # noqa: F401 — re-exported for test backward compatibility
    _python_non_code_lines,  # noqa: F401 — re-exported for test backward compatibility
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

    def get_tool_schema(self) -> dict[str, Any]:
        return _TRACE_IMPACT_INPUT_SCHEMA

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
            "inputSchema": self.get_tool_schema(),
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
        # Coerce max_results to int before validate_arguments so string values
        # from the MCP boundary ("1000") are accepted rather than rejected.
        if "max_results" in arguments and arguments["max_results"] is not None:
            arguments = {**arguments, "max_results": int(arguments["max_results"])}
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
        # #655: pass symbol so import lines and inline string-literal
        # mentions are excluded from the caller count.
        source_matches = _filter_comment_docstring_matches(ext_filtered, symbol=symbol)

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
