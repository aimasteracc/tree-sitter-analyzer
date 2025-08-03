#!/usr/bin/env python3
"""
Updated Engine module for tree_sitter_analyzer.core.

This module provides the AnalysisEngine class which is the core component
of the new architecture responsible for file analysis workflow.
"""

import logging
from pathlib import Path
from typing import Any

from tree_sitter import Tree

from ..language_detector import LanguageDetector
from ..models import AnalysisResult, CodeElement
from ..plugins.manager import PluginManager
from .parser import Parser, ParseResult
from .query import QueryExecutor

# Configure logging
logger = logging.getLogger(__name__)


class AnalysisEngine:
    """
    Core analysis engine for the new architecture.

    This class orchestrates the analysis workflow by coordinating
    parsing, query execution, and element extraction through plugins.
    """

    def __init__(self) -> None:
        """Initialize the AnalysisEngine with core components."""
        try:
            self.parser = Parser()
            self.query_executor = QueryExecutor()
            self.language_detector = LanguageDetector()

            # Initialize plugin system
            self.plugin_manager = PluginManager()
            self._initialize_plugins()

            logger.info("AnalysisEngine initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize AnalysisEngine: {e}")
            raise

    def analyze_file(
        self, file_path: str | Path, language: str | None = None
    ) -> AnalysisResult:
        """
        Analyze a source code file.

        Args:
            file_path: Path to the file to analyze
            language: Optional language override

        Returns:
            AnalysisResult containing analysis results
        """
        file_path_obj = Path(file_path)
        file_path_str = str(file_path_obj)

        try:
            # Check if file exists
            if not file_path_obj.exists():
                raise FileNotFoundError(f"File not found: {file_path_str}")

            # Determine language
            detected_language = self._determine_language(file_path_obj, language)

            # Parse the file
            parse_result = self.parser.parse_file(file_path_str, detected_language)

            if not parse_result.success:
                logger.warning(
                    f"Parsing failed for {file_path_str}: {parse_result.error_message}"
                )
                return self._create_empty_result(
                    file_path_str, detected_language, error=parse_result.error_message
                )

            # Perform analysis
            return self._perform_analysis(parse_result)

        except FileNotFoundError:
            raise
        except PermissionError:
            raise
        except Exception as e:
            logger.error(f"Error analyzing file {file_path_str}: {e}")
            return self._create_empty_result(
                file_path_str, language or "unknown", error=str(e)
            )

    def analyze_code(
        self,
        source_code: str,
        language: str | None = None,
        filename: str | None = None,
    ) -> AnalysisResult:
        """
        Analyze source code string.

        Args:
            source_code: Source code to analyze
            language: Programming language (required if no filename)
            filename: Optional filename for language detection

        Returns:
            AnalysisResult containing analysis results
        """
        try:
            # Determine language
            if language is None and filename is not None:
                language = self.language_detector.detect_from_extension(filename)
            elif language is None:
                language = "unknown"

            # Parse the code
            parse_result = self.parser.parse_code(source_code, language, filename)

            if not parse_result.success:
                logger.warning(
                    f"Parsing failed for {language} code: {parse_result.error_message}"
                )
                return self._create_empty_result(
                    filename, language, error=parse_result.error_message
                )

            # Perform analysis
            return self._perform_analysis(parse_result)

        except Exception as e:
            logger.error(f"Error analyzing {language} code: {e}")
            return self._create_empty_result(
                filename, language or "unknown", error=str(e)
            )

    def _determine_language(
        self, file_path: Path, language_override: str | None
    ) -> str:
        """
        Determine the programming language for a file.

        Args:
            file_path: Path to the file
            language_override: Optional language override

        Returns:
            Detected or overridden language
        """
        if language_override:
            return language_override

        try:
            return self.language_detector.detect_from_extension(str(file_path))
        except Exception as e:
            logger.warning(f"Language detection failed for {file_path}: {e}")
            return "unknown"

    def _perform_analysis(self, parse_result: ParseResult) -> AnalysisResult:
        """
        Perform comprehensive analysis on parsed code.

        Args:
            parse_result: Result from parsing operation

        Returns:
            AnalysisResult containing analysis results
        """
        try:
            # Get plugin for the language
            plugin = self._get_language_plugin(parse_result.language)

            # Execute queries
            query_results = self._execute_queries(parse_result.tree, plugin)

            # Extract elements
            elements = self._extract_elements(parse_result, plugin)

            # Count nodes
            node_count = self._count_nodes(parse_result.tree)

            # Create analysis result using existing AnalysisResult structure
            return AnalysisResult(
                file_path=parse_result.file_path or "",
                language=parse_result.language,
                elements=elements,
                node_count=node_count,
                query_results=query_results,
                source_code=parse_result.source_code,
                line_count=(
                    len(parse_result.source_code.splitlines())
                    if parse_result.source_code
                    else 0
                ),
                success=True,
                error_message=None,
                analysis_time=0.0,
                # Initialize empty collections for now
                classes=[],
                methods=[],
                fields=[],
                imports=[],
                annotations=[],
                package=None,
            )

        except Exception as e:
            logger.error(f"Error performing analysis: {e}")
            return self._create_empty_result(
                parse_result.file_path, parse_result.language, error=str(e)
            )

    def _get_language_plugin(self, language: str) -> Any | None:
        """
        Get the appropriate language plugin.

        Args:
            language: Programming language name

        Returns:
            Language plugin instance or None
        """
        if self.plugin_manager is not None:
            try:
                return self.plugin_manager.get_plugin(language)
            except Exception as e:
                logger.error(f"Error getting plugin for {language}: {e}")

        return None

    def _execute_queries(self, tree: Tree | None, plugin: Any | None) -> dict[str, Any]:
        """
        Execute queries on the parsed tree.

        Args:
            tree: Parsed Tree-sitter tree
            plugin: Language plugin

        Returns:
            Dictionary of query results
        """
        if tree is None:
            return {}

        try:
            # If plugin is available, use its supported queries
            if plugin and hasattr(plugin, "get_supported_queries"):
                query_names = plugin.get_supported_queries()
            else:
                # Fallback to common queries that exist in the system
                query_names = ["class", "method", "field"]  # Use actual query names

            # Get language object for query execution
            language_obj = self._get_language_object(tree)
            if language_obj is None:
                return {}

            # Execute queries
            results = {}
            for query_name in query_names:
                try:
                    result = self.query_executor.execute_query(
                        tree,
                        language_obj,
                        query_name,
                        "",  # Source code would be passed here
                    )
                    results[query_name] = result
                except Exception as e:
                    logger.error(f"Error executing query {query_name}: {e}")
                    results[query_name] = {"error": str(e), "captures": []}

            return results

        except Exception as e:
            logger.error(f"Error executing queries: {e}")
            return {}

    def _extract_elements(
        self, parse_result: ParseResult, plugin: Any | None
    ) -> list[CodeElement]:
        """
        Extract code elements using the language plugin.

        Args:
            parse_result: Result from parsing operation
            plugin: Language plugin

        Returns:
            List of extracted code elements
        """
        try:
            if plugin and hasattr(plugin, "create_extractor"):
                extractor = plugin.create_extractor()
                if extractor:
                    # Extract different types of elements
                    elements = []

                    # Extract packages first (needed for proper class package resolution)
                    if hasattr(extractor, "extract_packages"):
                        packages = extractor.extract_packages(
                            parse_result.tree, parse_result.source_code
                        )
                        elements.extend(packages)

                    # Extract functions/methods
                    if hasattr(extractor, "extract_functions"):
                        functions = extractor.extract_functions(
                            parse_result.tree, parse_result.source_code
                        )
                        elements.extend(functions)

                    # Extract classes
                    if hasattr(extractor, "extract_classes"):
                        classes = extractor.extract_classes(
                            parse_result.tree, parse_result.source_code
                        )
                        elements.extend(classes)

                    # Extract variables/fields
                    if hasattr(extractor, "extract_variables"):
                        variables = extractor.extract_variables(
                            parse_result.tree, parse_result.source_code
                        )
                        elements.extend(variables)

                    # Extract imports
                    if hasattr(extractor, "extract_imports"):
                        imports = extractor.extract_imports(
                            parse_result.tree, parse_result.source_code
                        )
                        elements.extend(imports)

                    return elements

            # Fallback: create basic elements from query results
            return self._create_basic_elements(parse_result)

        except Exception as e:
            logger.error(f"Error extracting elements: {e}")
            return []

    def _create_basic_elements(self, parse_result: ParseResult) -> list[CodeElement]:
        """
        Create basic code elements as fallback.

        Args:
            parse_result: Result from parsing operation

        Returns:
            List of basic code elements
        """
        # This is a basic fallback implementation
        # Real implementation would extract meaningful elements
        elements: list[Any] = []

        try:
            if parse_result.tree and parse_result.tree.root_node:
                # Create a basic element representing the file

                # Note: CodeElement is abstract, so we'd need a concrete implementation
                # For now, return empty list until concrete element types are available
                pass

        except Exception as e:
            logger.error(f"Error creating basic elements: {e}")

        return elements

    def _count_nodes(self, tree: Tree | None) -> int:
        """
        Count nodes in the AST tree.

        Args:
            tree: Tree-sitter tree

        Returns:
            Number of nodes in the tree
        """
        if tree is None or tree.root_node is None:
            return 0

        try:

            def count_recursive(node: Any) -> int:
                """Recursively count nodes."""
                count = 1  # Count current node
                if hasattr(node, "children"):
                    for child in node.children:
                        count += count_recursive(child)
                return count

            return count_recursive(tree.root_node)

        except Exception as e:
            logger.error(f"Error counting nodes: {e}")
            return 0

    def _get_language_object(self, tree: Tree) -> Any | None:
        """
        Get the language object associated with a tree.

        Args:
            tree: Tree-sitter tree

        Returns:
            Language object or None
        """
        try:
            # Tree-sitter trees have a language property
            if hasattr(tree, "language"):
                return tree.language
            return None
        except Exception as e:
            logger.error(f"Error getting language object: {e}")
            return None

    def _initialize_plugins(self) -> None:
        """Initialize the plugin system."""
        try:
            if self.plugin_manager:
                plugins = self.plugin_manager.load_plugins()
                logger.info(f"Loaded {len(plugins)} plugins successfully")
            else:
                logger.warning("Plugin manager not available")
        except Exception as e:
            logger.error(f"Plugin initialization failed: {e}")
            # Don't raise here to allow engine to work without plugins
            logger.warning("Continuing without plugins")

    def _create_empty_result(
        self, file_path: str | None, language: str, error: str | None = None
    ) -> AnalysisResult:
        """
        Create an empty analysis result.

        Args:
            file_path: File path
            language: Programming language
            error: Optional error message

        Returns:
            Empty AnalysisResult
        """
        return AnalysisResult(
            file_path=file_path or "",
            language=language,
            line_count=0,
            success=error is None,
            elements=[],
            node_count=0,
            query_results={},
            source_code="",
            error_message=error,
            analysis_time=0.0,
            # Initialize empty collections
            classes=[],
            methods=[],
            fields=[],
            imports=[],
            annotations=[],
            package=None,
        )

    def get_supported_languages(self) -> list[str]:
        """
        Get list of supported programming languages.

        Returns:
            List of supported language names
        """
        try:
            if self.plugin_manager:
                return list(self.plugin_manager.get_supported_languages())
            return []
        except Exception as e:
            logger.error(f"Error getting supported languages: {e}")
            return []

    def get_available_queries(self, language: str) -> list[str]:
        """
        Get available queries for a specific language.

        Args:
            language: Programming language name

        Returns:
            List of available query names
        """
        try:
            plugin = self._get_language_plugin(language)
            if plugin and hasattr(plugin, "get_supported_queries"):
                queries = plugin.get_supported_queries()
                return list(queries) if queries else []
            else:
                # Return default queries
                return ["class", "method", "field"]
        except Exception as e:
            logger.error(f"Error getting available queries for {language}: {e}")
            return []

    # Add compatibility methods for API layer
    @property
    def language_registry(self) -> "AnalysisEngine":
        """Provide compatibility with API layer expecting language_registry"""
        return self

    def detect_language_from_file(self, file_path: Path) -> str | None:
        """
        Detect language from file path (compatibility method)

        Args:
            file_path: Path to the file

        Returns:
            Detected language name or None
        """
        try:
            return self.language_detector.detect_from_extension(str(file_path))
        except Exception as e:
            logger.error(f"Error detecting language for {file_path}: {e}")
            return None

    def get_extensions_for_language(self, language: str) -> list[str]:
        """
        Get file extensions for a language (compatibility method)

        Args:
            language: Programming language name

        Returns:
            List of file extensions
        """
        try:
            # Get extensions from language detector
            extensions = []
            for ext, lang in self.language_detector.EXTENSION_MAPPING.items():
                if lang == language:
                    extensions.append(ext)
            return extensions
        except Exception as e:
            logger.error(f"Error getting extensions for {language}: {e}")
            return []

    def get_registry_info(self) -> dict:
        """
        Get registry information (compatibility method)

        Returns:
            Registry information dictionary
        """
        try:
            return {
                "supported_languages": self.get_supported_languages(),
                "total_languages": len(self.get_supported_languages()),
                "language_detector_available": self.language_detector is not None,
                "plugin_manager_available": self.plugin_manager is not None,
            }
        except Exception as e:
            logger.error(f"Error getting registry info: {e}")
            return {}
