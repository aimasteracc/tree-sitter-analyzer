"""SQL language plugin — composable mixin architecture."""
from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...core.request import AnalysisRequest
    from ...models import AnalysisResult

from ...platform_compat.adapter import CompatibilityAdapter
from ...platform_compat.detector import PlatformDetector
from ...platform_compat.profiles import BehaviorProfile
from ...plugins.base import ElementExtractor, LanguagePlugin
from ...utils import log_debug, log_error
from ._core import CoreMixin
from ._dml import DmlMixin
from ._functions import FunctionsMixin
from ._indexes import IndexesMixin
from ._procedures import ProceduresMixin
from ._tables import TablesMixin
from ._triggers import TriggersMixin
from ._views import ViewsMixin

TREE_SITTER_AVAILABLE = importlib.util.find_spec("tree_sitter") is not None

__all__ = ["SQLElementExtractor", "SQLPlugin"]


class SQLElementExtractor(
    TablesMixin,
    ViewsMixin,
    ProceduresMixin,
    FunctionsMixin,
    TriggersMixin,
    IndexesMixin,
    DmlMixin,
    CoreMixin,
):
    """SQL element extractor composed from language-specific mixins."""


class SQLPlugin(LanguagePlugin):
    """
    SQL language plugin implementation.

    Provides SQL language support for tree-sitter-analyzer, enabling analysis
    of SQL files including database schema definitions, stored procedures,
    functions, triggers, and indexes.

    The plugin follows the standard LanguagePlugin interface and integrates
    with the plugin manager for automatic discovery. It requires the
    tree-sitter-sql package to be installed (available as optional dependency).
    """

    def __init__(self, diagnostic_mode: bool = False) -> None:
        """
        Initialize the SQL language plugin.

        Sets up the extractor instance and caches for tree-sitter language
        loading. The plugin supports .sql file extensions.
        """
        super().__init__()
        self.diagnostic_mode = diagnostic_mode
        self.extractor = SQLElementExtractor(diagnostic_mode=diagnostic_mode)
        self.language = "sql"
        self.supported_extensions = self.get_file_extensions()
        self._cached_language: Any | None = None

        # Platform compatibility initialization
        self.platform_info = None
        try:
            self.platform_info = PlatformDetector.detect()
            from ...plugins.base import ElementExtractor

            if isinstance(self.extractor, ElementExtractor):
                self.extractor.platform_info = self.platform_info

            platform_info = self.platform_info
            profile = BehaviorProfile.load(platform_info.platform_key)

            if self.diagnostic_mode:
                log_debug(f"Diagnostic: Platform detected: {platform_info}")
                if profile:
                    log_debug(
                        f"Diagnostic: Loaded SQL behavior profile for {platform_info.platform_key}"
                    )
                    log_debug(f"Diagnostic: Profile rules: {profile.adaptation_rules}")
                else:
                    log_debug(
                        f"Diagnostic: No SQL behavior profile found for {platform_info.platform_key}"
                    )
            elif profile:
                log_debug(
                    f"Loaded SQL behavior profile for {platform_info.platform_key}"
                )
            else:
                log_debug(
                    f"No SQL behavior profile found for {platform_info.platform_key}, using defaults"
                )

            self.adapter = CompatibilityAdapter(profile)
            self.extractor.set_adapter(self.adapter)
        except Exception as e:
            log_error(f"Failed to initialize SQL platform compatibility: {e}")
            self.adapter = CompatibilityAdapter(None)
            self.extractor.set_adapter(self.adapter)

    def get_tree_sitter_language(self) -> Any:
        """
        Get the tree-sitter language object for SQL.

        Returns:
            The tree-sitter language object.

        Raises:
            RuntimeError: If tree-sitter-sql is not installed.
        """
        if self._cached_language:
            return self._cached_language

        try:
            import tree_sitter
            import tree_sitter_sql

            self._cached_language = tree_sitter.Language(tree_sitter_sql.language())
            return self._cached_language
        except ImportError as e:
            raise RuntimeError(
                "tree-sitter-sql is required for SQL analysis but not installed."
            ) from e

    def get_language_name(self) -> str:
        """Get the language name."""
        return "sql"

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".sql"]

    def create_extractor(self) -> ElementExtractor:
        """Create a new element extractor instance."""
        return SQLElementExtractor()

    def extract_elements(self, tree: Any, source_code: str) -> dict[str, list[Any]]:
        """
        Legacy method for extracting elements.
        Maintained for backward compatibility and testing.

        Args:
            tree: Tree-sitter AST tree
            source_code: Source code string

        Returns:
            Dictionary with keys 'functions', 'classes', 'variables', 'imports'
        """
        elements = self.extractor.extract_sql_elements(tree, source_code)

        result: dict[str, Any] = {
            "functions": [],
            "classes": [],
            "variables": [],
            "imports": [],
        }

        for element in elements:
            if element.element_type in ["function", "procedure", "trigger"]:
                result["functions"].append(element)
            elif element.element_type in ["class", "table", "view"]:
                result["classes"].append(element)
            elif element.element_type in ["variable", "index"]:
                result["variables"].append(element)
            elif element.element_type == "import":
                result["imports"].append(element)

        return result

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """
        Analyze SQL file and return structured results.

        Parses the SQL file using tree-sitter-sql, extracts database elements
        (tables, views, procedures, functions, triggers, indexes), and returns
        an AnalysisResult with all extracted information.

        Args:
            file_path: Path to the file to analyze
            request: Analysis request object

        Returns:
            AnalysisResult object containing extracted elements
        """
        from ...core.parser import Parser
        from ...models import AnalysisResult

        try:
            with open(file_path, encoding="utf-8") as f:
                source_code = f.read()

            parser = Parser()
            parse_result = parser.parse_code(source_code, "sql", file_path)

            if not parse_result.success:
                return AnalysisResult(
                    file_path=file_path,
                    language="sql",
                    line_count=len(source_code.splitlines()),
                    elements=[],
                    node_count=0,
                    query_results={},
                    source_code=source_code,
                    success=False,
                    error_message=parse_result.error_message,
                )

            elements = []
            if parse_result.tree:
                elements = self.extractor.extract_sql_elements(
                    parse_result.tree, source_code
                )

            return AnalysisResult(
                file_path=file_path,
                language="sql",
                line_count=len(source_code.splitlines()),
                elements=elements,
                node_count=(
                    parse_result.tree.root_node.end_byte if parse_result.tree else 0
                ),
                query_results={},
                source_code=source_code,
                success=True,
                error_message=None,
            )

        except Exception as e:
            log_error(f"Failed to analyze SQL file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                line_count=0,
                elements=[],
                node_count=0,
                query_results={},
                source_code="",
                success=False,
                error_message=str(e),
            )
