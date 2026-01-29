#!/usr/bin/env python3
"""
search_content MCP Tool (ripgrep wrapper)

Search content in files under roots or an explicit file list using ripgrep --json.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..utils.error_handler import handle_mcp_errors
from ..utils.file_output_manager import FileOutputManager
from ..utils.search_cache import get_default_cache
from .base_tool import BaseMCPTool
from .fd_rg import check_external_command
from .formatters.search_formatter import SearchResultFormatter
from .output_format_validator import get_default_validator
from .search_strategies.base import SearchContext
from .search_strategies.content_search import ContentSearchStrategy
from .validators.search_validator import SearchArgumentValidator

logger = logging.getLogger(__name__)


class SearchContentTool(BaseMCPTool):
    """MCP tool that wraps ripgrep to search content with safety limits."""

    def __init__(
        self, project_root: str | None = None, enable_cache: bool = True
    ) -> None:
        """
        Initialize the search content tool.

        Args:
            project_root: Optional project root directory
            enable_cache: Whether to enable search result caching (default: True)
        """
        super().__init__(project_root)
        self.cache = get_default_cache() if enable_cache else None
        self.file_output_manager = FileOutputManager.get_managed_instance(project_root)

        # Initialize new components
        self._validator = SearchArgumentValidator(
            project_root=self.project_root, path_resolver=self.path_resolver
        )
        self._strategy = ContentSearchStrategy(
            cache=self.cache,
            file_output_manager=self.file_output_manager,
            path_resolver=self.path_resolver,
        )
        self._formatter = SearchResultFormatter()

    def set_project_path(self, project_path: str) -> None:
        """
        Update the project path for all components.

        Args:
            project_path: New project root directory
        """
        super().set_project_path(project_path)
        self.file_output_manager = FileOutputManager.get_managed_instance(project_path)
        logger.info(f"SearchContentTool project path updated to: {project_path}")

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "search_content",
            "description": """Search text content inside files using ripgrep. Supports regex patterns, case sensitivity, context lines, and various output formats. Can search in directories or specific files.

⚡ IMPORTANT: Token Efficiency Guide
Choose output format parameters based on your needs to minimize token usage and maximize performance with efficient search strategies:

📋 RECOMMENDED WORKFLOW (Most Efficient Approach):
1. START with total_only=true parameter for initial count validation (~10 tokens)
2. IF more detail needed, use count_only_matches=true parameter for file distribution (~50-200 tokens)
3. IF context needed, use summary_only=true parameter for overview (~500-2000 tokens)
4. ONLY use full results when specific content review is required (~2000-50000+ tokens)

⚡ TOKEN EFFICIENCY COMPARISON:
- total_only: ~10 tokens (single number) - MOST EFFICIENT for count queries
- count_only_matches: ~50-200 tokens (file counts) - Good for file distribution analysis
- summary_only: ~500-2000 tokens (condensed overview) - initial investigation
- group_by_file: ~2000-10000 tokens (organized by file) - Context-aware review
- optimize_paths: 10-30% reduction (path compression) - Use with deep directory structures
- Full results: ~2000-50000+ tokens - Use sparingly for detailed analysis

⚠️ MUTUALLY EXCLUSIVE: Only one output format parameter can be true at a time. Cannot be combined with other format parameters.""",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "roots": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Directory paths to search in recursively. Alternative to 'files'. Example: ['.', 'src/', 'tests/']",
                    },
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific file paths to search in. Alternative to 'roots'. Example: ['main.py', 'config.json']",
                    },
                    "query": {
                        "type": "string",
                        "description": "Text pattern to search for. Can be literal text or regex depending on settings. Example: 'function', 'class\\s+\\w+', 'TODO:'",
                    },
                    "case": {
                        "type": "string",
                        "enum": ["smart", "insensitive", "sensitive"],
                        "default": "smart",
                        "description": "Case sensitivity mode. 'smart'=case-insensitive unless uppercase letters present, 'insensitive'=always ignore case, 'sensitive'=exact case match",
                    },
                    "fixed_strings": {
                        "type": "boolean",
                        "default": False,
                        "description": "Treat query as literal string instead of regex. True for exact text matching, False for regex patterns",
                    },
                    "word": {
                        "type": "boolean",
                        "default": False,
                        "description": "Match whole words only. True finds 'test' but not 'testing', False finds both",
                    },
                    "multiline": {
                        "type": "boolean",
                        "default": False,
                        "description": "Allow patterns to match across multiple lines. Useful for finding multi-line code blocks or comments",
                    },
                    "include_globs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "File patterns to include in search. Example: ['*.py', '*.js'] to search only Python and JavaScript files",
                    },
                    "exclude_globs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "File patterns to exclude from search. Example: ['*.log', '__pycache__/*'] to skip log files and cache directories",
                    },
                    "follow_symlinks": {
                        "type": "boolean",
                        "default": False,
                        "description": "Follow symbolic links during search. False=safer, True=may cause infinite loops",
                    },
                    "hidden": {
                        "type": "boolean",
                        "default": False,
                        "description": "Search in hidden files (starting with dot). False=skip .git, .env files, True=search all",
                    },
                    "no_ignore": {
                        "type": "boolean",
                        "default": False,
                        "description": "Ignore .gitignore and similar ignore files. False=respect ignore rules, True=search all files",
                    },
                    "max_filesize": {
                        "type": "string",
                        "description": "Maximum file size to search. Format: '10M'=10MB, '500K'=500KB, '1G'=1GB. Prevents searching huge files",
                    },
                    "context_before": {
                        "type": "integer",
                        "description": "Number of lines to show before each match. Useful for understanding match context. Example: 3 shows 3 lines before",
                    },
                    "context_after": {
                        "type": "integer",
                        "description": "Number of lines to show after each match. Useful for understanding match context. Example: 3 shows 3 lines after",
                    },
                    "encoding": {
                        "type": "string",
                        "description": "Text encoding to assume for files. Default is auto-detect. Example: 'utf-8', 'latin1', 'ascii'",
                    },
                    "max_count": {
                        "type": "integer",
                        "description": "Maximum number of matches per file. Useful to prevent overwhelming output from files with many matches",
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "description": "Search timeout in milliseconds. Prevents long-running searches. Example: 5000 for 5 second timeout",
                    },
                    "count_only_matches": {
                        "type": "boolean",
                        "default": False,
                        "description": "⚡ EXCLUSIVE: Return only match counts per file (~50-200 tokens). RECOMMENDED for: File distribution analysis, understanding match spread across files. Cannot be combined with other output formats.",
                    },
                    "summary_only": {
                        "type": "boolean",
                        "default": False,
                        "description": "⚡ EXCLUSIVE: Return condensed overview with top files and sample matches (~500-2000 tokens). RECOMMENDED for: Initial investigation, scope confirmation, pattern validation. Cannot be combined with other output formats.",
                    },
                    "optimize_paths": {
                        "type": "boolean",
                        "default": False,
                        "description": "⚡ EXCLUSIVE: Optimize file paths by removing common prefixes (10-30% token reduction). RECOMMENDED for: Deep directory structures, large codebases. Cannot be combined with other output formats.",
                    },
                    "group_by_file": {
                        "type": "boolean",
                        "default": False,
                        "description": "⚡ EXCLUSIVE: Group results by file, eliminating path duplication (~2000-10000 tokens). RECOMMENDED for: Context-aware review, analyzing matches within specific files. Cannot be combined with other output formats.",
                    },
                    "total_only": {
                        "type": "boolean",
                        "default": False,
                        "description": "⚡ EXCLUSIVE: Return only total match count as single number (~10 tokens - MOST EFFICIENT). RECOMMENDED for: Count validation, filtering decisions, existence checks. Takes priority over all other formats. Cannot be combined with other output formats.",
                    },
                    "output_file": {
                        "type": "string",
                        "description": "Optional filename to save output to file (extension auto-detected based on content)",
                    },
                    "suppress_output": {
                        "type": "boolean",
                        "description": "When true and output_file is specified, suppress detailed output in response to save tokens",
                        "default": False,
                    },
                    "enable_parallel": {
                        "type": "boolean",
                        "description": "Enable parallel processing for multiple root directories to improve performance. Default: True",
                        "default": True,
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["json", "toon"],
                        "description": "Output format: 'toon' (default, 50-70% token reduction) or 'json'",
                        "default": "toon",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        }

    def _validate_roots(self, roots: list[str]) -> list[str]:
        validated: list[str] = []
        for r in roots:
            try:
                resolved = self.resolve_and_validate_directory_path(r)
                validated.append(resolved)
            except ValueError as e:
                raise ValueError(f"Invalid root '{r}': {e}") from e
        return validated

    def _validate_files(self, files: list[str]) -> list[str]:
        validated: list[str] = []
        from ..utils.error_handler import AnalysisError

        for p in files:
            if not isinstance(p, str) or not p.strip():
                raise ValueError("files entries must be non-empty strings")
            try:
                resolved = self.resolve_and_validate_file_path(p)
                if not Path(resolved).exists() or not Path(resolved).is_file():
                    raise AnalysisError(
                        f"File not found: {p}", operation="search_content"
                    )
                validated.append(resolved)
            except ValueError as e:
                raise ValueError(f"Invalid file path '{p}': {e}") from e
        return validated

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        # Validate output format exclusion first
        validator = get_default_validator()
        validator.validate_output_format_exclusion(arguments)

        if (
            "query" not in arguments
            or not isinstance(arguments["query"], str)
            or not arguments["query"].strip()
        ):
            raise ValueError("query is required and must be a non-empty string")
        if "roots" not in arguments and "files" not in arguments:
            raise ValueError("Either roots or files must be provided")
        for key in [
            "case",
            "encoding",
            "max_filesize",
        ]:
            if key in arguments and not isinstance(arguments[key], str):
                raise ValueError(f"{key} must be a string")
        for key in [
            "fixed_strings",
            "word",
            "multiline",
            "follow_symlinks",
            "hidden",
            "no_ignore",
            "count_only_matches",
            "summary_only",
            "enable_parallel",
        ]:
            if key in arguments and not isinstance(arguments[key], bool):
                raise ValueError(f"{key} must be a boolean")
        for key in ["context_before", "context_after", "max_count", "timeout_ms"]:
            if key in arguments and not isinstance(arguments[key], int):
                raise ValueError(f"{key} must be an integer")
        for key in ["include_globs", "exclude_globs"]:
            if key in arguments:
                v = arguments[key]
                if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                    raise ValueError(f"{key} must be an array of strings")

        # Validate roots and files if provided
        if "roots" in arguments:
            self._validate_roots(arguments["roots"])
        if "files" in arguments:
            self._validate_files(arguments["files"])

        return True

    def _determine_requested_format(self, arguments: dict[str, Any]) -> str:
        """Determine the requested output format based on arguments."""
        if arguments.get("total_only", False):
            return "total_only"
        elif arguments.get("count_only_matches", False):
            return "count_only"
        elif arguments.get("summary_only", False):
            return "summary"
        elif arguments.get("group_by_file", False):
            return "group_by_file"
        else:
            return "normal"

    def _create_cache_key(self, context: SearchContext) -> str:
        """Create cache key from search context.

        Args:
            context: SearchContext containing search parameters

        Returns:
            Cache key string
        """
        if not self.cache:
            return ""

        # Extract cache parameters (exclude output-related params)
        cache_params = {
            k: v
            for k, v in context.arguments.items()
            if k not in ["query", "roots", "files", "output_file", "suppress_output"]
        }

        return self.cache.create_cache_key(
            query=context.query, roots=context.roots or [], **cache_params
        )

    def _create_count_only_cache_key(
        self, total_only_cache_key: str, arguments: dict[str, Any]
    ) -> str | None:
        """
        Create a count_only_matches cache key from a total_only cache key.

        This enables cross-format caching where total_only results can serve
        future count_only_matches queries.
        """
        if not self.cache:
            return None

        # Create modified arguments with count_only_matches instead of total_only
        count_only_args = arguments.copy()
        count_only_args.pop("total_only", None)
        count_only_args["count_only_matches"] = True

        # Generate cache key for count_only_matches version
        cache_params = {
            k: v
            for k, v in count_only_args.items()
            if k not in ["query", "roots", "files"]
        }

        roots = arguments.get("roots", [])
        return self.cache.create_cache_key(
            query=arguments["query"], roots=roots, **cache_params
        )

    @handle_mcp_errors("search_content")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any] | int:
        """Execute search operation (simplified version).

        Args:
            arguments: Search arguments dictionary

        Returns:
            Search results as dictionary or integer (for total_only mode)
        """
        # 1. Check if ripgrep command is available
        if not check_external_command("rg"):
            return {
                "success": False,
                "error": "rg (ripgrep) command not found. Please install ripgrep (https://github.com/BurntSushi/ripgrep) to use this tool.",
                "install_instructions": "https://github.com/BurntSushi/ripgrep#installation",
            }

        try:
            # 2. Validate arguments and create context
            context = self._validator.validate(arguments)

            # 3. Create cache key
            context.cache_key = self._create_cache_key(context)

            # 4. Execute strategy
            result = await self._strategy.execute(context)

            # 5. Format result
            return self._formatter.format(
                result,
                output_format=context.output_format,
                suppress_output=context.suppress_output,
            )

        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error in search_content: {e}", exc_info=True)
            return {"success": False, "error": f"Unexpected error: {str(e)}"}
