#!/usr/bin/env python3
"""
Advanced Command

Handles advanced analysis functionality.
"""

from typing import TYPE_CHECKING

from ...constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_VARIABLE,
    get_element_type,
)
from ...formatters.language_formatter_factory import create_language_formatter
from ...output_manager import output_data, output_json, output_section
from .base_command import BaseCommand

if TYPE_CHECKING:
    from ...models import AnalysisResult


class AdvancedCommand(BaseCommand):
    """Command for advanced analysis."""

    async def execute_async(self, language: str) -> int:
        analysis_result = await self.analyze_file(language)
        if not analysis_result:
            return 1

        if hasattr(self.args, "statistics") and self.args.statistics:
            self._output_statistics(analysis_result)
        else:
            self._output_full_analysis(analysis_result)

        return 0

    def _calculate_file_metrics(self, file_path: str, language: str) -> dict[str, int]:
        """
        Calculate accurate file metrics including line counts.

        Args:
            file_path: Path to the file to analyze
            language: Programming language

        Returns:
            Dictionary containing file metrics
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            lines = content.split("\n")
            total_lines = len(lines)

            # Remove empty line at the end if file ends with newline
            if lines and not lines[-1]:
                total_lines -= 1

            # Count different types of lines
            code_lines = 0
            comment_lines = 0
            blank_lines = 0
            in_multiline_comment = False

            for line in lines:
                stripped = line.strip()

                # Check for blank lines first
                if not stripped:
                    blank_lines += 1
                    continue

                # Check if we're in a multi-line comment
                if in_multiline_comment:
                    comment_lines += 1
                    # Check if this line ends the multi-line comment
                    if "*/" in stripped:
                        in_multiline_comment = False
                    continue

                # Check for multi-line comment start
                if stripped.startswith("/**") or stripped.startswith("/*"):
                    comment_lines += 1
                    # Check if this line also ends the comment
                    if "*/" not in stripped:
                        in_multiline_comment = True
                    continue

                # Check for single-line comments
                if stripped.startswith("//"):
                    comment_lines += 1
                    continue

                # Check for JavaDoc continuation lines (lines starting with * but not */)
                if stripped.startswith("*") and not stripped.startswith("*/"):
                    comment_lines += 1
                    continue

                # Check for other comment types based on language
                if language == "python" and stripped.startswith("#"):
                    comment_lines += 1
                    continue
                elif language == "sql" and stripped.startswith("--"):
                    comment_lines += 1
                    continue
                elif language in ["html", "xml"] and stripped.startswith("<!--"):
                    comment_lines += 1
                    if "-->" not in stripped:
                        in_multiline_comment = True
                    continue
                elif in_multiline_comment and "-->" in stripped:
                    comment_lines += 1
                    in_multiline_comment = False
                    continue

                # If not a comment, it's code
                code_lines += 1

            # Ensure the sum equals total_lines (handle any rounding errors)
            calculated_total = code_lines + comment_lines + blank_lines
            if calculated_total != total_lines:
                # Adjust blank_lines to match total (since it's most likely to be off by 1)
                blank_lines = total_lines - code_lines - comment_lines
                # Ensure blank_lines is not negative
                blank_lines = max(0, blank_lines)

            return {
                "total_lines": total_lines,
                "code_lines": code_lines,
                "comment_lines": comment_lines,
                "blank_lines": blank_lines,
            }
        except Exception:
            # Fallback to basic counting if file read fails
            return {
                "total_lines": 0,
                "code_lines": 0,
                "comment_lines": 0,
                "blank_lines": 0,
            }

    def _output_statistics(self, analysis_result: "AnalysisResult") -> None:
        """Output statistics only."""
        stats = {
            "line_count": analysis_result.line_count,
            "element_count": len(analysis_result.elements),
            "node_count": analysis_result.node_count,
            "language": analysis_result.language,
        }
        output_section("Statistics")
        if self.args.output_format == "json":
            output_json(stats)
        else:
            for key, value in stats.items():
                output_data(f"{key}: {value}")

    def _output_full_analysis(self, analysis_result: "AnalysisResult") -> None:
        """Output full analysis results."""
        # Check if we have a language-specific formatter
        formatter = create_language_formatter(analysis_result.language)
        if formatter:
            # Use language-specific formatter
            output_format = getattr(self.args, "output_format", "json")
            formatted_output = formatter.format_advanced(
                self._convert_to_formatter_format(analysis_result), output_format
            )
            print(formatted_output)
            return

        # Fallback to original implementation for unsupported languages
        output_section("Advanced Analysis Results")
        if self.args.output_format == "json":
            result_dict = {
                "file_path": analysis_result.file_path,
                "language": analysis_result.language,
                "line_count": analysis_result.line_count,
                "element_count": len(analysis_result.elements),
                "node_count": analysis_result.node_count,
                "elements": [
                    {
                        "name": getattr(element, "name", str(element)),
                        "type": get_element_type(element),
                        "start_line": getattr(element, "start_line", 0),
                        "end_line": getattr(element, "end_line", 0),
                    }
                    for element in analysis_result.elements
                ],
                "success": analysis_result.success,
                "analysis_time": analysis_result.analysis_time,
            }
            output_json(result_dict)
        else:
            self._output_text_analysis(analysis_result)

    def _convert_to_formatter_format(self, analysis_result: "AnalysisResult") -> dict:
        """Convert AnalysisResult to format expected by formatters."""
        return {
            "file_path": analysis_result.file_path,
            "language": analysis_result.language,
            "line_count": analysis_result.line_count,
            "element_count": len(analysis_result.elements),
            "node_count": getattr(analysis_result, "node_count", 0),
            "elements": [
                {
                    "name": getattr(element, "name", str(element)),
                    "type": get_element_type(element),
                    "start_line": getattr(element, "start_line", 0),
                    "end_line": getattr(element, "end_line", 0),
                    "text": getattr(element, "text", ""),
                    "level": getattr(element, "level", 1),
                    "url": getattr(element, "url", ""),
                    "alt": getattr(element, "alt", ""),
                    "language": getattr(element, "language", ""),
                    "line_count": getattr(element, "line_count", 0),
                    "list_type": getattr(element, "list_type", ""),
                    "item_count": getattr(element, "item_count", 0),
                    "column_count": getattr(element, "column_count", 0),
                    "row_count": getattr(element, "row_count", 0),
                    "line_range": {
                        "start": getattr(element, "start_line", 0),
                        "end": getattr(element, "end_line", 0),
                    },
                }
                for element in analysis_result.elements
            ],
            "success": getattr(analysis_result, "success", True),
            "analysis_time": getattr(analysis_result, "analysis_time", 0.0),
            "analysis_metadata": {
                "analysis_time": getattr(analysis_result, "analysis_time", 0.0),
                "language": analysis_result.language,
                "file_path": analysis_result.file_path,
                "analyzer_version": "2.0.0",
            },
        }

    def _output_text_analysis(self, analysis_result: "AnalysisResult") -> None:
        """Output analysis in text format."""
        output_data(f"File: {analysis_result.file_path}")
        output_data("Package: (default)")
        output_data(f"Lines: {analysis_result.line_count}")

        element_counts: dict[str, int] = {}
        complexity_scores: list[int] = []

        for element in analysis_result.elements:
            element_type = get_element_type(element)
            element_counts[element_type] = element_counts.get(element_type, 0) + 1

            # Collect complexity scores for methods
            if element_type == ELEMENT_TYPE_FUNCTION:
                complexity = getattr(element, "complexity_score", 1)
                complexity_scores.append(complexity)

        # Calculate accurate file metrics
        file_metrics = self._calculate_file_metrics(
            analysis_result.file_path, analysis_result.language
        )

        # Calculate complexity statistics
        total_complexity = sum(complexity_scores) if complexity_scores else 0
        avg_complexity = (
            total_complexity / len(complexity_scores) if complexity_scores else 0
        )
        max_complexity = max(complexity_scores) if complexity_scores else 0

        output_data(f"Classes: {element_counts.get(ELEMENT_TYPE_CLASS, 0)}")
        output_data(f"Methods: {element_counts.get(ELEMENT_TYPE_FUNCTION, 0)}")
        output_data(f"Fields: {element_counts.get(ELEMENT_TYPE_VARIABLE, 0)}")
        output_data(f"Imports: {element_counts.get(ELEMENT_TYPE_IMPORT, 0)}")
        output_data("Annotations: 0")

        # Add detailed metrics using accurate calculations
        output_data(f"Code Lines: {file_metrics['code_lines']}")
        output_data(f"Comment Lines: {file_metrics['comment_lines']}")
        output_data(f"Blank Lines: {file_metrics['blank_lines']}")
        output_data(f"Total Complexity: {total_complexity}")
        output_data(f"Average Complexity: {avg_complexity:.2f}")
        output_data(f"Max Complexity: {max_complexity}")
