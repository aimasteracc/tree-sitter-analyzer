#!/usr/bin/env python3
"""
Information Commands for CLI

Commands that display information without requiring file analysis.
"""

from abc import ABC, abstractmethod
from argparse import Namespace

from ..language_detector import detect_language_from_file, detector
from ..output_manager import (
    output_data,
    output_error,
    output_info,
    output_json,
    output_list,
)
from ..query_loader import query_loader


def _wants_json_output(args: Namespace) -> bool:
    """Return True when the caller asked for JSON via ``--format json``.

    r37ad (dogfood): info commands (--list-queries, --describe-query,
    --show-supported-*, --filter-help) previously ignored ``--format
    json`` and always emitted plain text. Agents that piped the output
    through ``json.loads`` failed with ``Expecting value: line 1 column 1``.
    """
    fmt = getattr(args, "format", None) or getattr(args, "output_format", None)
    return fmt == "json"


class InfoCommand(ABC):
    """Base class for information commands that don't require file analysis."""

    def __init__(self, args: Namespace):
        self.args = args

    @abstractmethod
    def execute(self) -> int:
        """Execute the information command."""
        pass


class ListQueriesCommand(InfoCommand):
    """Command to list available queries."""

    def execute(self) -> int:
        if self.args.language:
            language = self.args.language
        elif hasattr(self.args, "file_path") and self.args.file_path:
            language = detect_language_from_file(self.args.file_path)
        else:
            language = None

        if _wants_json_output(self.args):
            return self._emit_json(language)
        return self._emit_text(language)

    def _emit_text(self, language: str | None) -> int:
        """Legacy text output (preserves backward compatibility)."""
        if language is None:
            output_list("Supported languages:")
            for lang in query_loader.list_supported_languages():
                output_list(f"  {lang}")
                queries = query_loader.list_queries_for_language(lang)
                for query_key in queries:
                    description = (
                        query_loader.get_query_description(lang, query_key)
                        or "No description"
                    )
                    output_list(f"    {query_key:<20} - {description}")
            return 0

        output_list(f"Available query keys ({language}):")
        for query_key in query_loader.list_queries_for_language(language):
            description = (
                query_loader.get_query_description(language, query_key)
                or "No description"
            )
            output_list(f"  {query_key:<20} - {description}")
        return 0

    def _emit_json(self, language: str | None) -> int:
        """r37ad (dogfood): JSON envelope path.

        ``--list-queries --format json`` previously fell through to text
        output. Now emits a canonical envelope so agents can parse the
        response (``summary_line`` / ``verdict`` / ``agent_summary`` /
        ``queries`` / ``language``).
        """
        if language is None:
            languages: list[dict[str, object]] = []
            total = 0
            for lang in query_loader.list_supported_languages():
                lang_queries = self._collect_query_descriptions(lang)
                total += len(lang_queries)
                languages.append({"language": lang, "queries": lang_queries})
            summary_line = (
                f"list_queries: {len(languages)} languages, {total} queries total"
            )
            envelope = {
                "success": True,
                "scope": "all_languages",
                "language": None,
                "languages": languages,
                "language_count": len(languages),
                "query_count": total,
                "summary_line": summary_line,
                "verdict": "INFO",
                "agent_summary": {
                    "summary_line": summary_line,
                    "next_step": (
                        "Pass --language=<lang> to focus on one language, or "
                        "use --describe-query=<key> for details."
                    ),
                    "verdict": "INFO",
                },
            }
            output_json(envelope)
            return 0

        lang_queries = self._collect_query_descriptions(language)
        summary_line = f"list_queries ({language}): {len(lang_queries)} queries"
        envelope = {
            "success": True,
            "scope": "single_language",
            "language": language,
            "queries": lang_queries,
            "query_count": len(lang_queries),
            "summary_line": summary_line,
            "verdict": "INFO",
            "agent_summary": {
                "summary_line": summary_line,
                "next_step": (
                    f"Run `--query-key=<key> --language={language}` to execute "
                    "a query, or `--describe-query=<key>` for its tree-sitter source."
                ),
                "verdict": "INFO",
            },
        }
        output_json(envelope)
        return 0

    @staticmethod
    def _collect_query_descriptions(language: str) -> list[dict[str, str]]:
        """Return ``[{key, description}]`` for every query in ``language``."""
        return [
            {
                "key": query_key,
                "description": (
                    query_loader.get_query_description(language, query_key)
                    or "No description"
                ),
            }
            for query_key in query_loader.list_queries_for_language(language)
        ]


class DescribeQueryCommand(InfoCommand):
    """Command to describe a specific query."""

    def execute(self) -> int:
        if self.args.language:
            language = self.args.language
        elif hasattr(self.args, "file_path") and self.args.file_path:
            language = detect_language_from_file(self.args.file_path)
        else:
            if _wants_json_output(self.args):
                output_json(
                    _error_envelope(
                        "describe_query requires --language or target file",
                        error_type="validation",
                    )
                )
            else:
                output_error(
                    "ERROR: Query description display requires --language or target file specification"
                )
            return 1

        try:
            query_description = query_loader.get_query_description(
                language, self.args.describe_query
            )
            query_content = query_loader.get_query(language, self.args.describe_query)

            if query_description is None or query_content is None:
                msg = (
                    f"Query '{self.args.describe_query}' not found for language "
                    f"'{language}'"
                )
                if _wants_json_output(self.args):
                    output_json(
                        _error_envelope(
                            msg, error_type="not_found", verdict="NOT_FOUND"
                        )
                    )
                else:
                    output_error(msg)
                return 1

            if _wants_json_output(self.args):
                summary_line = (
                    f"describe_query ({language}/{self.args.describe_query}): "
                    f"{len(query_content.splitlines())} lines"
                )
                output_json(
                    {
                        "success": True,
                        "language": language,
                        "query_key": self.args.describe_query,
                        "description": query_description,
                        "query_content": query_content,
                        "summary_line": summary_line,
                        "verdict": "INFO",
                        "agent_summary": {
                            "summary_line": summary_line,
                            "next_step": (
                                f"Run `--query-key={self.args.describe_query} "
                                f"--language={language}` to execute this query."
                            ),
                            "verdict": "INFO",
                        },
                    }
                )
            else:
                output_info(
                    f"Query key '{self.args.describe_query}' ({language}): {query_description}"
                )
                output_data(f"Query content:\n{query_content}")
        except ValueError as e:
            if _wants_json_output(self.args):
                output_json(_error_envelope(str(e), error_type="validation"))
            else:
                output_error(f"{e}")
            return 1
        return 0


class ShowLanguagesCommand(InfoCommand):
    """Command to show supported languages."""

    def execute(self) -> int:
        languages_info = []
        for language in detector.get_supported_languages():
            info = detector.get_language_info(language)
            languages_info.append(
                {
                    "language": language,
                    "extensions": list(info["extensions"]),
                }
            )

        if _wants_json_output(self.args):
            summary_line = f"show_supported_languages: {len(languages_info)} languages"
            output_json(
                {
                    "success": True,
                    "languages": languages_info,
                    "language_count": len(languages_info),
                    "summary_line": summary_line,
                    "verdict": "INFO",
                    "agent_summary": {
                        "summary_line": summary_line,
                        "next_step": (
                            "Pass --language=<name> + --list-queries to see that "
                            "language's available query keys."
                        ),
                        "verdict": "INFO",
                    },
                }
            )
            return 0

        output_list("Supported languages:")
        for entry in languages_info:
            exts = entry["extensions"]
            extensions = ", ".join(exts[:5])
            if len(exts) > 5:
                extensions += f", ... ({len(exts) - 5} more)"
            output_list(f"  {entry['language']:<12} - Extensions: {extensions}")
        return 0


class ShowExtensionsCommand(InfoCommand):
    """Command to show supported extensions."""

    def execute(self) -> int:
        supported_extensions = list(detector.get_supported_extensions())

        if _wants_json_output(self.args):
            summary_line = (
                f"show_supported_extensions: {len(supported_extensions)} extensions"
            )
            output_json(
                {
                    "success": True,
                    "extensions": supported_extensions,
                    "extension_count": len(supported_extensions),
                    "summary_line": summary_line,
                    "verdict": "INFO",
                    "agent_summary": {
                        "summary_line": summary_line,
                        "next_step": (
                            "Use --show-supported-languages to map extensions back "
                            "to languages."
                        ),
                        "verdict": "INFO",
                    },
                }
            )
            return 0

        output_list("Supported file extensions:")
        # Use more efficient chunking with itertools.islice
        from itertools import islice

        chunk_size = 8
        for i in range(0, len(supported_extensions), chunk_size):
            chunk = list(islice(supported_extensions, i, i + chunk_size))
            line = "  " + "  ".join(f"{ext:<6}" for ext in chunk)
            output_list(line)
        output_info(f"\nTotal {len(supported_extensions)} extensions supported")
        return 0


def _error_envelope(
    message: str,
    *,
    error_type: str = "error",
    verdict: str = "ERROR",
) -> dict[str, object]:
    """r37ae: shared error envelope shape for JSON info commands.

    Matches the validation-error envelope used by file-path tools so
    agents can parse error responses with the same code path regardless
    of whether they hit ``--describe-query`` or ``--file-health``.
    """
    summary_line = f"error: {message}"
    return {
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
