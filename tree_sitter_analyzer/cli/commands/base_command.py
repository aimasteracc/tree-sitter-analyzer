#!/usr/bin/env python3
"""
Base Command Class

Abstract base class for all CLI commands implementing the Command Pattern.
"""

import asyncio
from abc import ABC, abstractmethod
from argparse import Namespace
from typing import Optional

from ...core.analysis_engine import AnalysisRequest, get_analysis_engine
from ...file_handler import read_file_partial
from ...language_detector import detect_language_from_file, is_language_supported
from ...models import AnalysisResult
from ...output_manager import output_error, output_info
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

    def validate_file(self) -> bool:
        """Validate input file exists and is accessible."""
        if not hasattr(self.args, "file_path") or not self.args.file_path:
            output_error("File path not specified.")
            return False

        # Security validation
        is_valid, error_msg = self.security_validator.validate_file_path(
            self.args.file_path
        )
        if not is_valid:
            output_error(f"Invalid file path: {error_msg}")
            return False

        from pathlib import Path

        if not Path(self.args.file_path).exists():
            output_error("Invalid file path: file does not exist")
            return False

        return True

    def detect_language(self) -> str | None:
        """Detect or validate the target language."""
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
                output_error(
                    f"ERROR: Could not determine language for file '{self.args.file_path}'."
                )
                return None
            else:
                if (not hasattr(self.args, "table") or not self.args.table) and (
                    not hasattr(self.args, "quiet") or not self.args.quiet
                ):
                    # Language auto-detected - only show in verbose mode
                    pass

        # Language support validation
        if not is_language_supported(target_language):
            if target_language != "java":
                if (not hasattr(self.args, "table") or not self.args.table) and (
                    not hasattr(self.args, "quiet") or not self.args.quiet
                ):
                    output_info(
                        "INFO: Trying with Java analysis engine. May not work correctly."
                    )
                target_language = "java"  # Fallback

        return str(target_language) if target_language else None

    async def analyze_file(self, language: str) -> Optional["AnalysisResult"]:
        """Perform file analysis using the unified analysis engine."""
        try:
            # Handle partial read if enabled
            if hasattr(self.args, "partial_read") and self.args.partial_read:
                try:
                    partial_content = read_file_partial(
                        self.args.file_path,
                        start_line=self.args.start_line,
                        end_line=getattr(self.args, "end_line", None),
                        start_column=getattr(self.args, "start_column", None),
                        end_column=getattr(self.args, "end_column", None),
                    )
                    if partial_content is None:
                        output_error("Failed to read file partially")
                        return None
                except Exception as e:
                    output_error(f"Failed to read file partially: {e}")
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
                output_error(f"Analysis failed: {error_msg}")
                return None

            return analysis_result

        except Exception as e:
            output_error(f"An error occurred during analysis: {e}")
            return None

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
            output_error(f"An error occurred during command execution: {e}")
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
