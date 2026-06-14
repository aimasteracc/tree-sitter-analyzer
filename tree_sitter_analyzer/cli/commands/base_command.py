#!/usr/bin/env python3
"""
Base Command Class

Abstract base class for all CLI commands implementing the Command Pattern.
"""

import asyncio
import json
from abc import ABC, abstractmethod
from argparse import Namespace
from collections.abc import Mapping
from typing import Any, Optional

from ...core.analysis_engine import AnalysisRequest, get_analysis_engine
from ...file_handler import read_file_partial
from ...language_detector import detect_language_from_file, is_language_supported
from ...models import AnalysisResult
from ...output_manager import output_error, output_info, output_json
from ...project_detector import detect_project_root
from ...security import SecurityValidator


class BaseCommand(ABC):
    """
    Base class for all CLI commands.

    Implements common functionality like file validation, language detection,
    and analysis engine interaction.
    """

    def __init__(self, args: Namespace):
        """Initialize command with parsed arguments."""
        self.args = args

        # Detect project root with priority handling
        file_path = getattr(args, "file_path", None)
        explicit_root = getattr(args, "project_root", None)
        self.project_root = detect_project_root(file_path, explicit_root)

        # Initialize components with project root
        self.analysis_engine = get_analysis_engine(self.project_root)
        self.security_validator = SecurityValidator(self.project_root)
        self._json_error_envelope_enabled = False

    @staticmethod
    def _classify_error_type(exc: BaseException) -> str:
        """Classify CLI failures into a stable machine-readable error_type."""
        return (
            "validation"
            if isinstance(exc, (ValueError, TypeError, KeyError))
            else "runtime"
        )

    def _emit_error_envelope(
        self,
        *,
        flag_name: str,
        message: str,
        error_type: str,
        verdict: str = "ERROR",
        echo_fields: Mapping[str, Any] | None = None,
    ) -> None:
        """Emit a canonical CLI error envelope for machine-readable flows."""
        if not self._should_emit_json_error_envelope():
            output_error(message)
            return

        summary_line = f"{flag_name}: {message}"
        envelope: dict[str, Any] = {
            "success": False,
            "error_type": error_type,
            "error": message,
            "summary_line": summary_line,
            "verdict": verdict,
            "agent_summary": {
                "summary_line": summary_line,
                "next_step": "Fix the input and retry.",
                "verdict": verdict,
            },
        }
        if echo_fields:
            for key, value in echo_fields.items():
                envelope[key] = value

        output_format = getattr(self.args, "output_format", "json")
        if output_format == "json":
            output_json(envelope)
            return

        output_error(message)

    def _should_emit_json_error_envelope(self) -> bool:
        """
        Determine whether failures should go to JSON envelope.

        Only commands opting in (currently --advanced and --structure) should
        emit JSON envelopes, and only when the user explicitly requested JSON
        output. This preserves the existing text-mode failure behavior for
        default CLI invocations while restoring machine-readable error output
        for the issue-triggering commands.
        """
        return (
            getattr(self, "_json_error_envelope_enabled", False)
            and bool(getattr(self.args, "output_format_explicit", False))
            and getattr(self.args, "output_format", "json") == "json"
        )

    def validate_file(self) -> bool:
        """Validate input file exists and is accessible."""
        if not hasattr(self.args, "file_path") or not self.args.file_path:
            self._emit_error_envelope(
                flag_name="validation",
                message="File path not specified.",
                error_type="validation",
            )
            return False

        # Security validation
        is_valid, error_msg = self.security_validator.validate_file_path(
            self.args.file_path
        )
        if not is_valid:
            self._emit_error_envelope(
                flag_name="file_validation",
                message=f"Invalid file path: {error_msg}",
                error_type="validation",
                echo_fields={"file_path": self.args.file_path},
            )
            if not self._should_emit_json_error_envelope():
                output_info("Use --project-root to set the project root directory.")
            return False

        from pathlib import Path

        if not Path(self.args.file_path).exists():
            self._emit_error_envelope(
                flag_name="file_validation",
                message=f"File not found: {self.args.file_path}",
                error_type="validation",
                echo_fields={"file_path": self.args.file_path},
            )
            if not self._should_emit_json_error_envelope():
                output_info("Check the file path and try again.")
            return False

        return True

    def detect_language(self) -> str | None:
        """Detect or validate the target language.

        Q2 (round-33 dogfood): the previous implementation silently rewrote
        the target to ``"java"`` whenever language detection produced an
        unsupported value, *and* it printed the "trying Java" diagnostic
        to ``stdout`` — which broke ``json.load()`` on the CLI output for
        any caller piping it. We now emit a canonical error envelope
        instead (matches MCP ``UniversalAnalyzeTool.execute`` at
        ``mcp/tools/universal_analyze_tool.py:226-227`` which raises
        ``ValueError`` for unsupported languages).
        """
        if hasattr(self.args, "language") and self.args.language:
            # Sanitize language input
            sanitized_language = self.security_validator.sanitize_input(
                self.args.language, max_length=50
            )
            target_language = sanitized_language.lower()
            if (not hasattr(self.args, "table") or not self.args.table) and (
                not hasattr(self.args, "quiet") or not self.args.quiet
            ):
                output_info(f"INFO: Language explicitly specified: {target_language}")
        else:
            target_language = detect_language_from_file(self.args.file_path)
            if target_language == "unknown":
                self._emit_unsupported_language_envelope(target_language)
                return None

        # Language support validation — no more silent Java fallback.
        if not is_language_supported(target_language):
            self._emit_unsupported_language_envelope(target_language)
            return None

        return str(target_language) if target_language else None

    def _emit_unsupported_language_envelope(self, detected_language: str) -> None:
        """Emit a canonical error envelope for an unsupported language.

        Matches the MCP ``ToolResponse`` shape: ``success=False``,
        ``error_type='validation'``, top-level ``summary_line`` mirrored
        in ``agent_summary``, and ``verdict='ERROR'``. JSON/TOON go to
        stdout so callers can ``json.loads(stdout)``; text mode falls
        back to ``output_error`` (stderr).
        """
        output_format = getattr(self.args, "output_format", "json")
        file_path = getattr(self.args, "file_path", "") or ""

        if detected_language == "unknown":
            error_message = (
                f"Could not detect language for file '{file_path}'. "
                "Run --show-supported-languages to see what's available, "
                "or pass --language explicitly."
            )
            summary_line = f"unknown language: {file_path}"
        else:
            error_message = (
                f"Language '{detected_language}' is not supported. "
                "Run --show-supported-languages to see what's available."
            )
            summary_line = f"unsupported language: {detected_language}"

        envelope: dict[str, object] = {
            "success": False,
            "error_type": "validation",
            "error": error_message,
            "file_path": file_path,
            "language": detected_language,
            "summary_line": summary_line,
            "agent_summary": {
                "summary_line": summary_line,
                "next_step": (
                    "Use a supported language or omit --language to auto-detect."
                ),
                "verdict": "ERROR",
            },
        }

        if output_format == "json":
            # stdout is the machine-readable channel — keep it parseable.
            print(json.dumps(envelope, ensure_ascii=False))
            return

        if output_format == "toon":
            try:
                from ...formatters.toon_formatter import ToonFormatter

                use_tabs = getattr(self.args, "toon_use_tabs", False)
                print(ToonFormatter(use_tabs=use_tabs).format(envelope))
                return
            except Exception:
                # If TOON formatter unavailable, fall back to JSON so the
                # caller still gets a parseable envelope.
                print(json.dumps(envelope, ensure_ascii=False))
                return

        # Text mode — emit to stderr like every other error.
        output_error(error_message)

    async def analyze_file(self, language: str) -> Optional["AnalysisResult"]:
        """Perform file analysis using the unified analysis engine.

        r37dy (dogfood): flatten partial-read precheck (depth 6) via
        ``_try_partial_read_precheck`` helper. The helper returns
        ``True`` when the precheck passes (or is disabled) and ``False``
        when caller should bail with ``None``.
        """
        try:
            if not self._try_partial_read_precheck():
                self._emit_error_envelope(
                    flag_name="partial_read",
                    message="Failed partial-read precheck.",
                    error_type="validation",
                )
                return None

            request = AnalysisRequest(
                file_path=self.args.file_path,
                language=language,
                include_complexity=True,
                include_details=True,
            )
            analysis_result = await self.analysis_engine.analyze(request)

            if not analysis_result or not analysis_result.success:
                error_msg = (
                    analysis_result.error_message
                    if analysis_result
                    else "Unknown error"
                )
                self._emit_error_envelope(
                    flag_name="analysis",
                    message=f"Analysis failed: {error_msg}",
                    error_type="runtime",
                )
                return None

            return analysis_result  # type: ignore[no-any-return]

        except Exception as e:
            self._emit_error_envelope(
                flag_name="analysis",
                message=f"An error occurred during analysis: {e}",
                error_type=self._classify_error_type(e),
            )
            return None

    def _try_partial_read_precheck(self) -> bool:
        """Run the partial-read precheck when ``--partial-read`` was passed.

        Returns ``True`` on the happy path (precheck disabled, or content
        was successfully read). Returns ``False`` only when partial read
        is enabled AND the read fails (caller should propagate ``None``
        back to the caller). The actual partial content is *not*
        captured here — ``analyze_file`` re-reads via the analysis
        engine anyway; this precheck just sanity-checks the range so a
        clearer error surfaces before the heavier pipeline runs.

        r37dy (dogfood): lifted from ``analyze_file`` to flatten the
        try/except-inside-if from depth 6 to 3.
        """
        if not hasattr(self.args, "partial_read") or not self.args.partial_read:
            return True
        try:
            partial_content = read_file_partial(
                self.args.file_path,
                start_line=self.args.start_line,
                end_line=getattr(self.args, "end_line", None),
                start_column=getattr(self.args, "start_column", None),
                end_column=getattr(self.args, "end_column", None),
            )
        except Exception as e:
            self._emit_error_envelope(
                flag_name="partial_read",
                message=f"Failed to read file partially: {e}",
                error_type=self._classify_error_type(e),
            )
            return False
        if partial_content is None:
            self._emit_error_envelope(
                flag_name="partial_read",
                message="Failed to read file partially",
                error_type="validation",
            )
            return False
        return True

    def execute(self) -> int:
        """
        Execute the command.

        Returns:
            int: Exit code (0 for success, 1 for failure)
        """
        # Validate inputs
        if not self.validate_file():
            return 1

        # Detect language
        language = self.detect_language()
        if not language:
            return 1

        # Execute the specific command
        try:
            return asyncio.run(self.execute_async(language))
        except Exception as e:
            self._emit_error_envelope(
                flag_name="command_execution",
                message=f"An error occurred during command execution: {e}",
                error_type=self._classify_error_type(e),
            )
            return 1

    @abstractmethod
    async def execute_async(self, language: str) -> int:
        """
        Execute the command asynchronously.

        Args:
            language: Detected/specified target language

        Returns:
            int: Exit code (0 for success, 1 for failure)
        """
        pass
