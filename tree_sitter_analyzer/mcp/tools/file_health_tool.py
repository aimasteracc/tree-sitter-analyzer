#!/usr/bin/env python3
"""
File Health MCP Tool

Exposes health_scorer.py to AI agents via MCP protocol.
Returns A-F grades, dimension scores, and specific code smells for single files.

Uses tree-sitter for cross-language element extraction (all 15 languages).
"""

from pathlib import Path
from typing import Any

from ...health_scorer import HealthScorer
from ...utils import setup_logger
from .base_tool import BaseMCPTool
from .utils.element_extractor import extract_elements
from .utils.file_health_response import (
    _build_signal as _build_signal,
)
from .utils.file_health_response import (
    build_file_health_result,
)
from .utils.file_health_smells import detect_code_smells

logger = setup_logger(__name__)

# H7 fix: extensions that are not code and therefore must not be graded
# A-F. The health scorer reads them as ``language=None`` and silently
# falls through to a generic file-size + line-count score, producing
# grade C "moderate technical debt" for a README.md. The list mirrors
# the common documentation / configuration extensions an agent will
# encounter alongside source code.
_NON_CODE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".md",
        ".txt",
        ".yaml",
        ".yml",
        ".toml",
        ".json",
        ".html",
        ".xml",
        ".csv",
        ".rst",
        ".ini",
    }
)

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "Path to the source file to score",
        },
        "language": {
            "type": "string",
            "description": "Programming language (optional, auto-detected)",
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "description": "Output format: 'toon' (default, token-efficient) or 'json'",
            "default": "toon",
        },
    },
    "required": ["file_path"],
    "additionalProperties": False,
}


class FileHealthTool(BaseMCPTool):
    """MCP Tool for file-level code health scoring with code smell detection."""

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize with optional project root for path resolution."""
        self._scorer: HealthScorer | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._scorer = None

    # Get or create the HealthScorer instance
    def _get_scorer(self) -> HealthScorer:
        """Get or create the HealthScorer instance."""
        if self._scorer is None:
            self._scorer = HealthScorer()
        return self._scorer

    # MCP tool metadata - name, description, schema
    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "check_file_health",
            "description": (
                "File health A-F grade with code smells + security scan. "
                "NOT reading code — gives risk assessment. "
                "Returns: 7 dimension scores, smells, fix suggestions."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    # JSON schema for input validation
    @staticmethod
    def get_tool_schema() -> dict[str, Any]:
        """Return the JSON schema for tool input validation."""
        return TOOL_SCHEMA

    # Input validation - fail fast with clear error messages
    @staticmethod
    def validate_arguments(arguments: dict[str, Any]) -> bool:
        """Validate file_path argument."""
        if "file_path" not in arguments:
            raise ValueError("file_path is required")
        fp = arguments["file_path"]
        if not isinstance(fp, str) or not fp.strip():
            raise ValueError("file_path must be a non-empty string")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute health scoring and code smell detection."""
        self.validate_arguments(arguments)

        file_path = arguments["file_path"]
        output_format = arguments.get("output_format", "toon")
        language = arguments.get("language")

        resolved = self.resolve_and_validate_file_path(file_path)
        if not Path(resolved).exists():
            raise ValueError(f"File not found: {file_path}")

        from ..utils.format_helper import apply_toon_format_to_response

        # H7 fix: non-code files (Markdown, YAML, JSON, …) must not be
        # graded A-F. Without this guard ``HealthScorer`` falls through
        # to a size + line-count heuristic and produces grade C
        # "moderate technical debt" for a README.md.
        non_code_response = _non_code_file_response(resolved, file_path)
        if non_code_response is not None:
            return apply_toon_format_to_response(non_code_response, output_format)

        # Bug M7: 0-byte files have no signal. Health scoring would assign a
        # bogus "large_file" reading from empty dimensions — return a clear
        # n/a envelope instead. H9 extends this to whitespace-only files —
        # ``\n\n   \n`` is operationally empty even though ``getsize > 0``.
        empty_response = _empty_file_response(resolved, file_path)
        if empty_response is not None:
            return apply_toon_format_to_response(empty_response, output_format)

        if not language:
            from ...language_detector import detect_language_from_file

            language = detect_language_from_file(
                resolved, project_root=self.project_root
            )
            if language == "unknown":
                language = None

        # Bug M6: refuse binaries early. ``language is None`` or unparseable
        # tree-sitter output combined with a NUL-byte/utf-8-decode failure
        # is the clearest signal a file is non-source. Returning ``grade F``
        # from the scorer and recommending refactor on a ``.pyc`` is worse
        # than a clean error.
        analysis = extract_elements(resolved, self.project_root)
        if _looks_binary(resolved, language, analysis):
            return apply_toon_format_to_response(
                _binary_file_response(file_path, resolved), output_format
            )

        scorer = self._get_scorer()
        health = scorer.score_file(resolved)

        smells = detect_code_smells(resolved, health.dimensions, analysis, language)

        result = build_file_health_result(
            file_path,
            health,
            smells,
            resolved,
            analysis,
        )

        return apply_toon_format_to_response(result, output_format)


def _empty_file_response(resolved: str, file_path: str) -> dict[str, Any] | None:
    """Return an n/a envelope when ``resolved`` is empty or whitespace-only.

    Returning ``None`` means the caller should continue with normal scoring.

    H9 extends the original M7 fix: a file containing only spaces and
    newlines (``"   \\n   \\n"``) has ``st_size > 0`` but no analyzable
    content. The scorer would happily grade it ``A`` because nothing
    triggers a complexity / structure penalty — misleading because the
    file really has zero signal.
    """
    detail = "empty (0 bytes)"
    try:
        size = Path(resolved).stat().st_size
    except OSError:
        return None
    if size == 0:
        pass  # fall through to the n/a envelope below
    else:
        # H9: defer to content inspection when the file is non-empty
        # but might be whitespace-only.
        try:
            text = Path(resolved).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        if text.strip():
            return None
        detail = f"whitespace-only ({size} bytes)"
    # J14 (round-22): align ``verdict`` casing across tools. Every other
    # safety verdict in the codebase (SAFE / CAUTION / UNSAFE / CLEAN /
    # WARN / N/A in code_patterns) is uppercase; the file_health empty
    # branch was emitting lowercase ``n/a`` and forcing agents to do
    # case-insensitive comparisons. Switching to ``N/A`` matches
    # code_patterns' empty-file response so the two tools agree on the
    # same input both byte-for-byte and structurally.
    return {
        "success": True,
        "file_path": file_path,
        "grade": "N/A",
        "verdict": "N/A",
        "signal": "empty_file",
        "recommendation": "File is empty; nothing to analyze.",
        "code_smells": [],
        "smell_count": 0,
        "dimensions": {},
        "agent_summary": {
            "summary_line": f"{file_path} is {detail}",
            "next_step": "skip",
            "verdict": "N/A",
        },
        "agent_next_action": {
            "priority": "none",
            "reason": "file is empty",
            "mcp_command": "",
            "cli_command": "",
            "post_edit_commands": [],
        },
    }


def _non_code_file_response(resolved: str, file_path: str) -> dict[str, Any] | None:
    """Return an n/a envelope when ``resolved`` is a non-code file.

    Returning ``None`` means the caller should continue with normal scoring.
    H7 fix: Markdown / config files are not graded A-F — code-quality
    metrics do not apply.
    """
    suffix = Path(resolved).suffix.lower()
    if suffix not in _NON_CODE_EXTENSIONS:
        return None
    summary_line = f"{file_path} signal=non_code_file"
    return {
        "success": True,
        "file_path": file_path,
        "grade": "N/A",
        # ``verdict`` mirrors safe_to_edit / modification_guard. Use
        # ``N/A`` first; downstream code that requires one of the
        # safety vocab strings should treat this as ``SAFE`` (nothing
        # to break by skipping the analysis).
        "verdict": "N/A",
        "signal": "non_code_file",
        "recommendation": ("Markdown/config files are not code-quality scored."),
        "code_smells": [],
        "smell_count": 0,
        "dimensions": {},
        "summary_line": summary_line,
        "agent_summary": {
            "summary_line": summary_line,
            "next_step": ("Markdown/config files are not code-quality scored."),
            "verdict": "N/A",
        },
        "agent_next_action": {
            "priority": "none",
            "reason": "non-code file",
            "mcp_command": "",
            "cli_command": "",
            "post_edit_commands": [],
        },
    }


def _looks_binary(resolved: str, language: str | None, analysis: Any) -> bool:
    """Heuristic: is ``resolved`` a non-source / binary file?

    Trigger when (a) language detection failed *or* (b) tree-sitter found no
    elements, *and* the first 1024 bytes contain a NUL byte or fail to
    decode as utf-8. Either signal alone is too noisy — well-formed text
    files with no detected language (e.g. exotic suffixes) shouldn't be
    rejected, and zero-element results can legitimately happen for tiny
    valid files.
    """
    if language and analysis is not None:
        return False

    try:
        with open(resolved, "rb") as handle:
            head = handle.read(1024)
    except OSError:
        return False

    if not head:
        return False
    if b"\x00" in head:
        return True
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def _binary_file_response(file_path: str, resolved: str) -> dict[str, Any]:
    """Return an error envelope refusing to analyze a binary file."""
    return {
        "success": False,
        "error_type": "binary_file",
        "error": "Cannot analyze binary file",
        "file_path": file_path,
        "agent_summary": {
            "summary_line": f"{file_path} appears to be binary/non-source",
            "next_step": "skip",
            "verdict": "ERROR",
        },
    }
