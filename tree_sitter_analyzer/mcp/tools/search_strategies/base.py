"""Base classes for search strategies.

This module defines the abstract base class for search strategies and
the search context dataclass.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SearchContext:
    """Context object containing all information needed for a search operation.

    This dataclass encapsulates all the parameters and state needed to execute
    a search operation, making it easier to pass around and test.

    Attributes:
        arguments: Original arguments dictionary from the tool call
        project_root: Root directory of the project
        roots: List of root directories to search in (optional)
        files: List of specific files to search in (optional)
        query: Search query string
        total_only: Whether to return only the total count
        count_only_matches: Whether to return only match counts per file
        summary_only: Whether to return only a summary
        group_by_file: Whether to group results by file
        optimize_paths: Whether to optimize file paths in results
        output_format: Output format ('toon' or 'json')
        output_file: Optional file to save results to
        suppress_output: Whether to suppress detailed output
        cache_key: Optional cache key for this search
    """

    arguments: dict[str, Any]
    project_root: Path
    roots: list[str] | None = None
    files: list[str] | None = None
    query: str = ""
    total_only: bool = False
    count_only_matches: bool = False
    summary_only: bool = False
    group_by_file: bool = False
    optimize_paths: bool = False
    output_format: str = "toon"
    output_file: str | None = None
    suppress_output: bool = False
    cache_key: str | None = None

    # Additional search parameters
    case: str = "smart"
    fixed_strings: bool = False
    word: bool = False
    multiline: bool = False
    include_globs: list[str] | None = None
    exclude_globs: list[str] | None = None
    follow_symlinks: bool = False
    hidden: bool = False
    no_ignore: bool = False
    max_filesize: str | None = None
    context_before: int | None = None
    context_after: int | None = None
    encoding: str | None = None
    max_count: int | None = None
    timeout_ms: int | None = None
    enable_parallel: bool = True

    def __post_init__(self):
        """Extract common parameters from arguments dict."""
        # Extract search parameters from arguments
        self.query = self.arguments.get("query", "")
        self.roots = self.arguments.get("roots")
        self.files = self.arguments.get("files")

        # Extract output mode flags
        self.total_only = bool(self.arguments.get("total_only", False))
        self.count_only_matches = bool(self.arguments.get("count_only_matches", False))
        self.summary_only = bool(self.arguments.get("summary_only", False))
        self.group_by_file = bool(self.arguments.get("group_by_file", False))
        self.optimize_paths = bool(self.arguments.get("optimize_paths", False))

        # Extract output parameters
        self.output_format = self.arguments.get("output_format", "toon")
        self.output_file = self.arguments.get("output_file")
        self.suppress_output = bool(self.arguments.get("suppress_output", False))

        # Extract search parameters
        self.case = self.arguments.get("case", "smart")
        self.fixed_strings = bool(self.arguments.get("fixed_strings", False))
        self.word = bool(self.arguments.get("word", False))
        self.multiline = bool(self.arguments.get("multiline", False))
        self.include_globs = self.arguments.get("include_globs")
        self.exclude_globs = self.arguments.get("exclude_globs")
        self.follow_symlinks = bool(self.arguments.get("follow_symlinks", False))
        self.hidden = bool(self.arguments.get("hidden", False))
        self.no_ignore = bool(self.arguments.get("no_ignore", False))
        self.max_filesize = self.arguments.get("max_filesize")
        self.context_before = self.arguments.get("context_before")
        self.context_after = self.arguments.get("context_after")
        self.encoding = self.arguments.get("encoding")
        self.max_count = self.arguments.get("max_count")
        self.timeout_ms = self.arguments.get("timeout_ms")
        self.enable_parallel = bool(self.arguments.get("enable_parallel", True))


class SearchStrategy(ABC):
    """Abstract base class for search strategies.

    This class defines the interface that all search strategies must implement.
    Each strategy represents a different way of executing a search operation.

    The Strategy pattern allows us to:
    1. Separate the search algorithm from the tool that uses it
    2. Make it easy to add new search modes without modifying existing code
    3. Test each strategy independently
    4. Reduce the complexity of the main execute() method
    """

    @abstractmethod
    async def execute(self, context: SearchContext) -> dict[str, Any] | int:
        """Execute the search strategy.

        Args:
            context: SearchContext containing all search parameters

        Returns:
            Search results as a dictionary, or an integer for total_only mode

        Raises:
            ValueError: If required parameters are missing or invalid
            RuntimeError: If the search operation fails
        """
        pass

    def _should_use_parallel(self, context: SearchContext) -> bool:
        """Determine if parallel processing should be used.

        Args:
            context: SearchContext containing search parameters

        Returns:
            True if parallel processing should be used, False otherwise
        """
        return (
            context.roots is not None
            and len(context.roots) > 1
            and context.enable_parallel
        )
