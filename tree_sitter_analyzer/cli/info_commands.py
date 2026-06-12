#!/usr/bin/env python3
"""
Information Commands for CLI

Commands that display information without requiring file analysis.
"""

import importlib.util
from abc import ABC, abstractmethod
from argparse import Namespace

from ..language_detector import detect_language_from_file, detector
from ..language_loader import grammar_install_hint
from ..output_manager import (
    output_data,
    output_error,
    output_info,
    output_json,
    output_list,
)
from ..query_loader import query_loader
from .output_format import wants_json_output as _wants_json_output  # noqa: F401


def _grammar_install_state(language: str) -> tuple[bool, str | None]:
    """Probe grammar availability without importing it.

    Returns ``(installed, hint)``. Languages with no loader mapping at all
    (e.g. ``json``) are reported NOT installed — the parser surface rejects
    them (``Unsupported language``), so claiming ``installed: true`` would
    be the same false advertising this command is being fixed for
    (Codex P2 on #559).
    """
    from ..language_loader import LanguageLoader

    module_name = LanguageLoader.LANGUAGE_MODULES.get(language)
    if module_name is None:
        return False, "no grammar loader mapping — parser surface unavailable"
    if importlib.util.find_spec(module_name) is not None:
        return True, None
    return False, grammar_install_hint(language)


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
        """Legacy text output (preserves backward compatibility).

        r37ao (dogfood): flattened depth-6 nesting into ``_emit_text_all``
        + ``_emit_text_one`` helpers. The tool flagged the previous shape
        as ``deep_nesting`` after the JSON refactor took out the bigger
        warnings — finish the smell cleanup in one go.
        """
        if language is None:
            self._emit_text_all_languages()
        else:
            self._emit_text_single_language(language)
        return 0

    def _emit_text_all_languages(self) -> None:
        """Print every supported language and its queries in text form."""
        output_list("Supported languages:")
        for lang in query_loader.list_supported_languages():
            output_list(f"  {lang}")
            self._emit_text_query_block(lang, indent="    ")

    def _emit_text_single_language(self, language: str) -> None:
        """Print the queries for a single language in text form."""
        output_list(f"Available query keys ({language}):")
        self._emit_text_query_block(language, indent="  ")

    @staticmethod
    def _emit_text_query_block(language: str, *, indent: str) -> None:
        """Emit ``"{indent}{key:<20} - {description}"`` for every query."""
        for query_key in query_loader.list_queries_for_language(language):
            description = (
                query_loader.get_query_description(language, query_key)
                or "No description"
            )
            output_list(f"{indent}{query_key:<20} - {description}")

    def _emit_json(self, language: str | None) -> int:
        """r37ad (dogfood): JSON envelope path.

        ``--list-queries --format json`` previously fell through to text
        output. Now emits a canonical envelope so agents can parse the
        response (``summary_line`` / ``verdict`` / ``agent_summary`` /
        ``queries`` / ``language``).

        r37ao (dogfood): extracted ``_build_all_languages_envelope`` and
        ``_build_single_language_envelope`` to drop method length from
        60 → ~10 lines and flatten nesting (the tool flagged this as a
        long-method smell).
        """
        if language is None:
            envelope = self._build_all_languages_envelope()
        else:
            envelope = self._build_single_language_envelope(language)
        output_json(envelope)
        return 0

    def _build_all_languages_envelope(self) -> dict[str, object]:
        """Construct the ``--list-queries`` envelope for *all* languages."""
        languages: list[dict[str, object]] = []
        total = 0
        for lang in query_loader.list_supported_languages():
            lang_queries = self._collect_query_descriptions(lang)
            total += len(lang_queries)
            languages.append({"language": lang, "queries": lang_queries})
        summary_line = (
            f"list_queries: {len(languages)} languages, {total} queries total"
        )
        return {
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

    def _build_single_language_envelope(self, language: str) -> dict[str, object]:
        """Construct the ``--list-queries`` envelope for a single language."""
        lang_queries = self._collect_query_descriptions(language)
        summary_line = f"list_queries ({language}): {len(lang_queries)} queries"
        return {
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
    """Command to describe a specific query.

    r37ao (dogfood): refactored ``execute`` from 76 lines / nesting-depth 8
    into a 3-step early-return pipeline. The tool flagged the previous
    shape as a ``deep_nesting`` (critical) + ``long_method`` (warning)
    smell — same dogfood loop as r37am/r37an: tool finds smell, fix lands,
    tool re-runs clean.
    """

    def execute(self) -> int:
        language = self._resolve_language()
        if language is None:
            return self._emit_missing_language_error()

        try:
            query_description = query_loader.get_query_description(
                language, self.args.describe_query
            )
            query_content = query_loader.get_query(language, self.args.describe_query)
        except ValueError as exc:
            return self._emit_value_error(exc)

        if query_description is None or query_content is None:
            return self._emit_not_found_error(language)

        return self._emit_describe_query_response(
            language=language,
            query_description=query_description,
            query_content=query_content,
        )

    def _resolve_language(self) -> str | None:
        """Return the language to describe, or ``None`` when it cannot be inferred."""
        explicit: str | None = self.args.language
        if explicit:
            return explicit
        if hasattr(self.args, "file_path") and self.args.file_path:
            detected: str | None = detect_language_from_file(self.args.file_path)
            return detected
        return None

    def _emit_missing_language_error(self) -> int:
        """``--describe-query`` invoked without ``--language`` or a file path."""
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

    def _emit_not_found_error(self, language: str) -> int:
        """Selected query key is unknown for ``language``."""
        msg = f"Query '{self.args.describe_query}' not found for language '{language}'"
        if _wants_json_output(self.args):
            output_json(
                _error_envelope(msg, error_type="not_found", verdict="NOT_FOUND")
            )
        else:
            output_error(msg)
        return 1

    def _emit_value_error(self, exc: ValueError) -> int:
        """The query loader raised — surface its message in the active format."""
        if _wants_json_output(self.args):
            output_json(_error_envelope(str(exc), error_type="validation"))
        else:
            output_error(f"{exc}")
        return 1

    def _emit_describe_query_response(
        self,
        *,
        language: str,
        query_description: str,
        query_content: str,
    ) -> int:
        """Emit the success response in JSON-envelope or legacy-text form."""
        if _wants_json_output(self.args):
            output_json(
                self._build_describe_query_envelope(
                    language=language,
                    query_description=query_description,
                    query_content=query_content,
                )
            )
        else:
            output_info(
                f"Query key '{self.args.describe_query}' ({language}): {query_description}"
            )
            output_data(f"Query content:\n{query_content}")
        return 0

    def _build_describe_query_envelope(
        self,
        *,
        language: str,
        query_description: str,
        query_content: str,
    ) -> dict[str, object]:
        """Construct the canonical ``--describe-query`` success envelope."""
        summary_line = (
            f"describe_query ({language}/{self.args.describe_query}): "
            f"{len(query_content.splitlines())} lines"
        )
        return {
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


class ShowLanguagesCommand(InfoCommand):
    """Command to show supported languages."""

    def execute(self) -> int:
        languages_info = [
            self._build_language_entry(language)
            for language in detector.get_supported_languages()
        ]
        if _wants_json_output(self.args):
            return self._emit_json(languages_info)
        return self._emit_text(languages_info)

    @staticmethod
    def _build_language_entry(language: str) -> dict:
        info = detector.get_language_info(language)
        installed, hint = _grammar_install_state(language)
        entry: dict = {
            "language": language,
            "extensions": list(info["extensions"]),
            "installed": installed,
        }
        if hint:
            entry["install_hint"] = hint
        return entry

    @staticmethod
    def _emit_json(languages_info: list[dict]) -> int:
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

    @staticmethod
    def _emit_text(languages_info: list[dict]) -> int:
        output_list("Supported languages:")
        for entry in languages_info:
            exts = entry["extensions"]
            extensions = ", ".join(exts[:5])
            if len(exts) > 5:
                extensions += f", ... ({len(exts) - 5} more)"
            if entry["installed"]:
                output_list(f"  {entry['language']:<12} - Extensions: {extensions}")
            else:
                hint = entry.get("install_hint", "")
                output_list(
                    f"  {entry['language']:<12} - Extensions: {extensions}"
                    f"  [not installed — {hint}]"
                )
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
