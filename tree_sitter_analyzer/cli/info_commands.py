#!/usr/bin/env python3
"""
Information Commands for CLI

Commands that display information without requiring file analysis.
"""

from abc import ABC, abstractmethod
from argparse import Namespace

from ..language_detector import detect_language_from_file, detector
from ..output_manager import output_data, output_error, output_info, output_list
from ..query_loader import query_loader


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


class DescribeQueryCommand(InfoCommand):
    """Command to describe a specific query."""

    def execute(self) -> int:
        if self.args.language:
            language = self.args.language
        elif hasattr(self.args, "file_path") and self.args.file_path:
            language = detect_language_from_file(self.args.file_path)
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
                output_error(
                    f"Query '{self.args.describe_query}' not found for language '{language}'"
                )
                return 1

            output_info(
                f"Query key '{self.args.describe_query}' ({language}): {query_description}"
            )
            output_data(f"Query content:\n{query_content}")
        except ValueError as e:
            output_error(f"{e}")
            return 1
        return 0


class ShowLanguagesCommand(InfoCommand):
    """Command to show supported languages."""

    def execute(self) -> int:
        output_list("Supported languages:")
        for language in detector.get_supported_languages():
            info = detector.get_language_info(language)
            extensions = ", ".join(info["extensions"][:5])
            if len(info["extensions"]) > 5:
                extensions += f", ... ({len(info['extensions'])-5} more)"
            output_list(f"  {language:<12} - Extensions: {extensions}")
        return 0


class ShowExtensionsCommand(InfoCommand):
    """Command to show supported extensions."""

    def execute(self) -> int:
        output_list("Supported file extensions:")
        supported_extensions = detector.get_supported_extensions()
        # Use more efficient chunking with itertools.islice
        from itertools import islice

        chunk_size = 8
        for i in range(0, len(supported_extensions), chunk_size):
            chunk = list(islice(supported_extensions, i, i + chunk_size))
            line = "  " + "  ".join(f"{ext:<6}" for ext in chunk)
            output_list(line)
        output_info(f"\nTotal {len(supported_extensions)} extensions supported")
        return 0
