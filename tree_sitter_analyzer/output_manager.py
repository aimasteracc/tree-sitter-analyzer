#!/usr/bin/env python3
"""
Output Manager for CLI

Handles different types of outputs: user information, errors, and structured data.
"""

import json
import sys
from typing import Any

from .utils import log_error, log_warning


class OutputManager:
    """Manages different types of output for CLI"""

    def __init__(self, quiet: bool = False, json_output: bool = False):
        self.quiet = quiet
        self.json_output = json_output

    def info(self, message: str) -> None:
        """Output informational message to user"""
        if not self.quiet:
            print(message)

    def warning(self, message: str) -> None:
        """Output warning message"""
        if not self.quiet:
            print(f"WARNING: {message}", file=sys.stderr)
        log_warning(message)

    def error(self, message: str) -> None:
        """Output error message"""
        print(f"ERROR: {message}", file=sys.stderr)
        log_error(message)

    def success(self, message: str) -> None:
        """Output success message"""
        if not self.quiet:
            print(f"✓ {message}")

    def output_info(self, message: str) -> None:
        """Output info message (alias for info)"""
        self.info(message)

    def output_warning(self, message: str) -> None:
        """Output warning message (alias for warning)"""
        self.warning(message)

    def output_error(self, message: str) -> None:
        """Output error message (alias for error)"""
        self.error(message)

    def output_success(self, message: str) -> None:
        """Output success message (alias for success)"""
        self.success(message)

    def data(self, data: Any, format_type: str = "json") -> None:
        """Output structured data"""
        if self.json_output or format_type == "json":
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            self._format_data(data)

    def _format_data(self, data: Any) -> None:
        """Format data for human-readable output"""
        if isinstance(data, dict):
            for key, value in data.items():
                print(f"{key}: {value}")
        elif isinstance(data, list):
            for i, item in enumerate(data, 1):
                print(f"{i}. {item}")
        else:
            print(str(data))

    def results_header(self, title: str) -> None:
        """Output results section header"""
        if not self.quiet:
            print(f"\n--- {title} ---")

    def query_result(self, index: int, result: dict[str, Any]) -> None:
        """Output query result in formatted way"""
        if not self.quiet:
            print(
                f"\n{index}. {result.get('capture_name', 'Unknown')} ({result.get('node_type', 'Unknown')})"
            )
            print(
                f"   Position: Line {result.get('start_line', '?')}-{result.get('end_line', '?')}"
            )
            if "content" in result:
                print(f"   Content:\n{result['content']}")

    def analysis_summary(self, stats: dict[str, Any]) -> None:
        """Output analysis summary"""
        if self.json_output:
            self.data(stats)
        else:
            self.results_header("Statistics")
            for key, value in stats.items():
                print(f"{key}: {value}")

    def language_list(
        self, languages: list[str], title: str = "Supported Languages"
    ) -> None:
        """Output language list"""
        if not self.quiet:
            print(f"{title}:")
            for lang in languages:
                print(f"  {lang}")

    def query_list(self, queries: dict[str, str], language: str) -> None:
        """Output query list for a language"""
        if not self.quiet:
            print(f"Available query keys ({language}):")
            for query_key, description in queries.items():
                print(f"  {query_key:<20} - {description}")

    def extension_list(self, extensions: list[str]) -> None:
        """Output supported extensions"""
        if not self.quiet:
            print("Supported file extensions:")
        # Use more efficient chunking
        from itertools import islice

        chunk_size = 10
        for i in range(0, len(extensions), chunk_size):
            chunk = list(islice(extensions, i, i + chunk_size))
            print(f"  {' '.join(chunk)}")
            print(f"Total {len(extensions)} extensions supported")

    def output_json(self, data: Any) -> None:
        """Output JSON data"""
        print(json.dumps(data, indent=2, ensure_ascii=False))

    def output_list(self, items: str | list[Any], title: str | None = None) -> None:
        """Output a list of items"""
        if title and not self.quiet:
            print(f"{title}:")
        # 文字列が単一要素として渡された場合の処理
        if isinstance(items, str):
            items = [items]
        for item in items:
            if not self.quiet:
                print(f"  {item}")

    def output_section(self, title: str) -> None:
        """Output a section header"""
        if not self.quiet:
            print(f"\n--- {title} ---")

    def output_query_results(self, results: Any) -> None:
        """Output query results"""
        self.data(results)

    def output_statistics(self, stats: dict[str, Any]) -> None:
        """Output statistics"""
        self.analysis_summary(stats)

    def output_languages(self, languages: list[str]) -> None:
        """Output available languages"""
        self.language_list(languages)

    def output_queries(self, queries: list[str]) -> None:
        """Output available queries"""
        query_dict = {q: f"Query {q}" for q in queries}
        self.query_list(query_dict, "All")

    def output_extensions(self, extensions: list[str]) -> None:
        """Output file extensions"""
        self.extension_list(extensions)

    def output_data(self, data: Any, format_type: str = "json") -> None:
        """Output data (alias for data)"""
        self.data(data, format_type)


# Default instance for backward compatibility
_output_manager = OutputManager()


def set_output_mode(quiet: bool = False, json_output: bool = False) -> None:
    """Set global output mode"""
    global _output_manager
    _output_manager = OutputManager(quiet=quiet, json_output=json_output)


def get_output_manager() -> OutputManager:
    """Get current output manager"""
    return _output_manager


# Convenience functions
def output_info(message: str) -> None:
    """Output info message"""
    _output_manager.info(message)


def output_warning(message: str) -> None:
    """Output warning message"""
    _output_manager.warning(message)


def output_error(message: str) -> None:
    """Output error message using the global output manager"""
    _output_manager.error(message)


def output_success(message: str) -> None:
    """Output success message using the global output manager"""
    _output_manager.success(message)


def output_json(data: Any) -> None:
    """Output JSON data using the global output manager"""
    _output_manager.output_json(data)


def output_list(items: str | list[Any], title: str | None = None) -> None:
    """Output a list of items"""
    _output_manager.output_list(items, title)


def output_section(title: str) -> None:
    """Output a section header"""
    _output_manager.output_section(title)


def output_query_results(results: Any) -> None:
    """Output query results"""
    _output_manager.output_query_results(results)


def output_statistics(stats: dict[str, Any]) -> None:
    """Output statistics"""
    _output_manager.output_statistics(stats)


def output_languages(languages: list[str], title: str = "Supported Languages") -> None:
    """Output available languages"""
    _output_manager.language_list(languages, title)


def output_queries(queries: list[str], language: str = "All") -> None:
    """Output available queries"""
    query_dict = {q: f"Query {q}" for q in queries}
    _output_manager.query_list(query_dict, language)


def output_extensions(extensions: list[str]) -> None:
    """Output file extensions"""
    _output_manager.output_extensions(extensions)


def output_data(data: Any, format_type: str = "json") -> None:
    """Output structured data"""
    _output_manager.data(data, format_type)
