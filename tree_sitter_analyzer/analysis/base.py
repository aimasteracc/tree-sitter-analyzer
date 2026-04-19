"""Base class for tree-sitter-based analyzers.

Provides parser resolution via LanguageLoader (24 languages, cached, thread-safe),
extension-to-language mapping, and file eligibility checks. Subclasses only need
to implement analysis logic — no parser/extension boilerplate required.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from tree_sitter_analyzer.language_loader import get_loader
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

_EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".go": "go",
    ".c": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".h": "c",
    ".cs": "csharp",
    ".kt": "kotlin",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "bash",
    ".css": "css",
    ".html": "html",
    ".json": "json",
    ".jsonc": "json",
    ".json5": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".sql": "sql",
}

DEFAULT_SUPPORTED_EXTENSIONS: set[str] = set(_EXTENSION_TO_LANGUAGE.keys())


class BaseAnalyzer:
    """Base class for tree-sitter-based code analyzers.

    Subclasses should:
    - Override SUPPORTED_EXTENSIONS if they only support a subset of languages
    - Implement _analyze(path, extension, language, parser) with their detection logic
    - NOT reimplement _get_parser(), _LANGUAGE_MODULES, etc.
    """

    SUPPORTED_EXTENSIONS: set[str] = DEFAULT_SUPPORTED_EXTENSIONS

    def __init__(self) -> None:
        self._loader = get_loader()

    def _get_parser(
        self, extension: str
    ) -> tuple[Any | None, Any | None]:
        """Get a cached (Language, Parser) pair for the given file extension."""
        lang_name = _EXTENSION_TO_LANGUAGE.get(extension)
        if lang_name is None:
            return None, None
        language = self._loader.load_language(lang_name)
        if language is None:
            return None, None
        parser = self._loader.create_parser(lang_name)
        if parser is None:
            return None, None
        return language, parser

    def _get_parser_for_language(
        self, language: str
    ) -> tuple[Any | None, Any | None]:
        """Get a cached (Language, Parser) pair by language name."""
        language_obj = self._loader.load_language(language)
        if language_obj is None:
            return None, None
        parser = self._loader.create_parser(language)
        if parser is None:
            return None, None
        return language_obj, parser

    def is_file_supported(self, file_path: Path | str) -> bool:
        """Check if the file extension is supported by this analyzer."""
        path = Path(file_path)
        return path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def _check_file(self, file_path: Path | str) -> tuple[Path, str] | None:
        """Validate file exists and is supported. Returns (path, extension) or None."""
        path = Path(file_path)
        if not path.exists():
            return None
        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return None
        return path, ext
