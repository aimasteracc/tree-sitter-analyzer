#!/usr/bin/env python3
"""
CLI Adapter for tree-sitter-analyzer

Adapter that uses the new unified analysis engine while maintaining compatibility with existing CLI API.

Roo Code compliance:
- Type hints: Required for all functions
- MCP logging: Log output at each step
- docstring: Google Style docstring
- Error handling: Proper exception handling
- Performance: Optimization through unified engine
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from ..core.analysis_engine import AnalysisRequest, UnifiedAnalysisEngine
from ..models import AnalysisResult

logger = logging.getLogger(__name__)


class CLIAdapter:
    """
    CLI Adapter

    Uses the new unified analysis engine while maintaining compatibility with existing CLI API.
    Provides synchronous API and internally calls asynchronous engine.

    Features:
        - Maintaining existing API compatibility
        - Utilizing unified analysis engine
        - Sync/async conversion
        - Performance monitoring
        - Error handling

    Example:
        >>> adapter = CLIAdapter()
        >>> result = adapter.analyze_file("example.java")
        >>> print(result.classes)
    """

    def __init__(self) -> None:
        """
        Initialize CLI adapter

        Raises:
            Exception: If unified analysis engine initialization fails
        """
        try:
            self._engine = UnifiedAnalysisEngine()
            logger.debug("CLIAdapter initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize CLIAdapter: {e}")
            raise

    def analyze_file(self, file_path: str, **kwargs: Any) -> AnalysisResult:
        """
        Analyze file (synchronous version)

        Provides synchronous interface to maintain compatibility with existing CLI API.
        Internally calls asynchronous methods of unified analysis engine.

        Args:
            file_path: Path to file to analyze
            **kwargs: Analysis options
                - language: Language specification (auto-detection possible)
                - include_complexity: Include complexity calculation
                - include_details: Include detailed information
                - format_type: Output format ("standard", "structure", "summary")

        Returns:
            AnalysisResult: Analysis result

        Raises:
            ValueError: For invalid file path
            FileNotFoundError: If file does not exist
            UnsupportedLanguageError: For unsupported language

        Example:
            >>> adapter = CLIAdapter()
            >>> result = adapter.analyze_file("example.java", include_complexity=True)
            >>> print(f"Classes: {len(result.classes)}")
        """
        start_time = time.time()

        # Input validation
        if not file_path or not file_path.strip():
            raise ValueError("File path cannot be empty")

        # File existence check
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            # Create AnalysisRequest
            request = AnalysisRequest(
                file_path=file_path,
                language=kwargs.get("language"),
                include_complexity=kwargs.get("include_complexity", False),
                include_details=kwargs.get("include_details", True),
                format_type=kwargs.get("format_type", "standard"),
            )

            # Run async engine synchronously
            result = asyncio.run(self._engine.analyze(request))

            # パフォーマンスログ
            elapsed_time = time.time() - start_time
            logger.debug(f"CLI analysis completed: {file_path} in {elapsed_time:.3f}s")

            return result

        except Exception as e:
            logger.error(f"CLI analysis failed for {file_path}: {e}")
            raise

    def analyze_structure(self, file_path: str, **kwargs: Any) -> dict[str, Any]:
        """
        Structure analysis (legacy API compatible)

        Returns structure info as a dictionary to keep compatibility with
        existing CLI API.

        Args:
            file_path: Path to the file to analyze
            **kwargs: Analysis options

        Returns:
            Dict[str, Any]: Structure dictionary
                - file_path
                - classes
                - methods
                - fields
                - imports

        Example:
            >>> adapter = CLIAdapter()
            >>> structure = adapter.analyze_structure("example.java")
            >>> print(structure["classes"])
        """
        # 詳細情報を含めて解析
        kwargs["include_details"] = True
        kwargs["format_type"] = "structure"

        result = self.analyze_file(file_path, **kwargs)

        # 構造情報を辞書形式に変換
        return {
            "file_path": result.file_path,
            "language": result.language,
            "package": result.package,
            "imports": [
                {"name": imp.name, "type": str(type(imp).__name__)}
                for imp in result.imports
            ],
            "classes": [
                {"name": cls.name, "type": str(type(cls).__name__)}
                for cls in result.classes
            ],
            "methods": [
                {"name": method.name, "type": str(type(method).__name__)}
                for method in result.methods
            ],
            "fields": [
                {"name": field.name, "type": str(type(field).__name__)}
                for field in result.fields
            ],
            "annotations": [
                {
                    "name": getattr(ann, "name", str(ann)),
                    "type": str(type(ann).__name__),
                }
                for ann in getattr(result, "annotations", [])
            ],
            "analysis_time": result.analysis_time,
            "elements": [
                {"name": elem.name, "type": str(type(elem).__name__)}
                for elem in result.elements
            ],
            "success": result.success,
        }

    def analyze_batch(
        self, file_paths: list[str], **kwargs: Any
    ) -> list[AnalysisResult]:
        """
        Analyze multiple files in batch

        Args:
            file_paths: List of file paths
            **kwargs: Analysis options

        Returns:
            list[AnalysisResult]: List of results

        Example:
            >>> adapter = CLIAdapter()
            >>> results = adapter.analyze_batch(["file1.java", "file2.java"])
            >>> print(f"Analyzed {len(results)} files")
        """
        results = []

        for file_path in file_paths:
            try:
                result = self.analyze_file(file_path, **kwargs)
                results.append(result)
            except Exception as e:
                logger.warning(f"Failed to analyze {file_path}: {e}")
                # Include failed item with error message
                error_result = AnalysisResult(
                    file_path=file_path,
                    package=None,
                    imports=[],
                    classes=[],
                    methods=[],
                    fields=[],
                    annotations=[],
                    analysis_time=0.0,
                    success=False,
                    error_message=str(e),
                )
                results.append(error_result)

        return results

    def get_supported_languages(self) -> list[str]:
        """
        Get list of supported languages

        Returns:
            list[str]

        Example:
            >>> adapter = CLIAdapter()
            >>> languages = adapter.get_supported_languages()
            >>> print(languages)
        """
        return self._engine.get_supported_languages()

    def clear_cache(self) -> None:
        """
        Clear cache

        Example:
            >>> adapter = CLIAdapter()
            >>> adapter.clear_cache()
        """
        self._engine.clear_cache()
        logger.debug("CLI adapter cache cleared")

    def get_cache_stats(self) -> dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Dict[str, Any]

        Example:
            >>> adapter = CLIAdapter()
            >>> stats = adapter.get_cache_stats()
            >>> print(f"Cache hit rate: {stats['hit_rate']:.2%}")
        """
        return self._engine.get_cache_stats()

    def validate_file(self, file_path: str) -> bool:
        """
        Validate whether a file is analyzable

        Args:
            file_path: File path to validate

        Returns:
            bool

        Example:
            >>> adapter = CLIAdapter()
            >>> if adapter.validate_file("example.java"):
            ...     result = adapter.analyze_file("example.java")
        """
        try:
            # ファイル存在チェック
            if not Path(file_path).exists():
                return False

            # 言語サポートチェック
            supported_languages = self.get_supported_languages()
            file_extension = Path(file_path).suffix.lower()

            # 拡張子から言語を推定
            extension_map = {
                ".java": "java",
                ".py": "python",
                ".js": "javascript",
                ".ts": "typescript",
                ".cpp": "cpp",
                ".c": "c",
                ".cs": "csharp",
                ".go": "go",
                ".rs": "rust",
                ".php": "php",
                ".rb": "ruby",
            }

            language = extension_map.get(file_extension)
            return language in supported_languages if language else False

        except Exception as e:
            logger.warning(f"File validation failed for {file_path}: {e}")
            return False

    def get_engine_info(self) -> dict[str, Any]:
        """
        Get engine information

        Returns:
            Dict[str, Any]

        Example:
            >>> adapter = CLIAdapter()
            >>> info = adapter.get_engine_info()
            >>> print(f"Engine version: {info['version']}")
        """
        return {
            "adapter_type": "CLI",
            "engine_type": "UnifiedAnalysisEngine",
            "supported_languages": self.get_supported_languages(),
            "cache_enabled": True,
            "async_support": True,
        }


# Legacy AdvancedAnalyzerAdapter removed - use UnifiedAnalysisEngine directly


def get_analysis_engine() -> "UnifiedAnalysisEngine":
    """Get analysis engine instance for testing compatibility."""
    from ..core.analysis_engine import UnifiedAnalysisEngine

    return UnifiedAnalysisEngine()
