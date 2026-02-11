"""
Python API interface for tree-sitter-analyzer v2.

Provides clean, type-safe API for programmatic use in:
- Agent skills
- Python scripts
- Integration with other tools
"""

from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.core.detector import LanguageDetector
from tree_sitter_analyzer_v2.core.parser_registry import get_all_parsers
from tree_sitter_analyzer_v2.formatters import get_default_registry
from tree_sitter_analyzer_v2.search import SearchEngine
from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector


class TreeSitterAnalyzerAPI:
    """
    Python API for tree-sitter code analysis.

    Provides methods for:
    - File analysis (classes, functions, imports)
    - File search (fd-based)
    - Content search (ripgrep-based)

    Example:
        >>> from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI
        >>> api = TreeSitterAnalyzerAPI()
        >>> result = api.analyze_file("example.py")
        >>> print(result["data"])
    """

    def __init__(self) -> None:
        """Initialize API with parsers and search engine."""
        # Resolve parsers via registry (DIP: no hardcoded language imports)
        self._parsers: dict[str, Any] = get_all_parsers()

        # Initialize detector and formatters
        self._detector = LanguageDetector()
        self._formatter_registry = get_default_registry()

        # Initialize search engine
        self._search_engine = SearchEngine()

    def analyze_file(self, file_path: str, output_format: str = "toon") -> dict[str, Any]:
        """
        Analyze code structure of a file.

        Args:
            file_path: Path to file to analyze
            output_format: Output format ("toon" or "markdown", default: "toon")

        Returns:
            Dictionary with keys:
                - success: bool
                - language: str (if successful)
                - output_format: str (if successful)
                - data: str (formatted output, if successful)
                - error: str (if failed)

        Example:
            >>> api = TreeSitterAnalyzerAPI()
            >>> result = api.analyze_file("example.py", output_format="toon")
            >>> if result["success"]:
            ...     print(result["data"])
        """
        path = Path(file_path)

        # Check file exists
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            # Detect language
            content = path.read_text(encoding="utf-8")
            detection = self._detector.detect_from_content(content, filename=path.name)

            if not detection or detection["language"] is None:
                return {
                    "success": False,
                    "error": f"Unsupported or undetected language: {file_path}",
                }

            language = detection["language"].lower()

            # Get appropriate parser
            if language not in self._parsers:
                return {"success": False, "error": f"Language '{language}' not supported yet"}

            parser = self._parsers[language]

            # Parse file
            result = parser.parse(content, str(path))

            # Format output
            formatter = self._formatter_registry.get(output_format)
            formatted_data = formatter.format(result)

            return {
                "success": True,
                "language": language,
                "output_format": output_format,
                "data": formatted_data,
            }

        except Exception as e:
            return {"success": False, "error": f"Error analyzing file: {str(e)}"}

    def analyze_file_raw(self, file_path: str) -> dict[str, Any]:
        """
        Analyze code structure and return raw parsed data (no formatting).

        Args:
            file_path: Path to file to analyze

        Returns:
            Dictionary with parsed elements:
                - classes: List of class definitions
                - functions: List of function definitions
                - imports: List of import statements
                - metadata: File metadata

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If language is unsupported or undetected
            RuntimeError: If parsing fails

        Example:
            >>> api = TreeSitterAnalyzerAPI()
            >>> result = api.analyze_file_raw("example.py")
            >>> print(result["classes"])
        """
        path = Path(file_path)

        # Check file exists
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Detect language
        content = path.read_text(encoding="utf-8")
        detection = self._detector.detect_from_content(content, filename=path.name)

        if not detection or detection["language"] is None:
            raise ValueError(f"Unsupported or undetected language: {file_path}")

        language = detection["language"].lower()

        # Get appropriate parser
        if language not in self._parsers:
            raise ValueError(f"Language '{language}' not supported yet")

        parser = self._parsers[language]

        # Parse and return raw result
        result: dict[str, Any] = parser.parse(content, str(path))
        return result

    def search_files(
        self, root_dir: str, pattern: str = "*", file_type: str | None = None
    ) -> dict[str, Any]:
        """
        Search for files using fd (fast file finder).

        Args:
            root_dir: Root directory to search in
            pattern: Glob pattern (default: "*")
            file_type: Optional file type filter (e.g., "py", "ts", "java")

        Returns:
            Dictionary with keys:
                - success: bool
                - files: list[str] (absolute paths, if successful)
                - count: int (number of files found, if successful)
                - error: str (if failed)

        Example:
            >>> api = TreeSitterAnalyzerAPI()
            >>> result = api.search_files(".", pattern="*.py")
            >>> if result["success"]:
            ...     for file in result["files"]:
            ...         print(file)
        """
        root_path = Path(root_dir)

        # Check directory exists
        if not root_path.exists():
            return {"success": False, "error": f"Directory not found: {root_dir}"}

        try:
            files = self._search_engine.find_files(
                root_dir=str(root_path), pattern=pattern, file_type=file_type
            )

            return {"success": True, "files": files, "count": len(files)}

        except Exception as e:
            return {"success": False, "error": f"Error searching files: {str(e)}"}

    def search_content(
        self,
        root_dir: str,
        pattern: str,
        file_type: str | None = None,
        case_sensitive: bool = True,
        is_regex: bool = False,
    ) -> dict[str, Any]:
        """
        Search file content using ripgrep (fast content search).

        Args:
            root_dir: Root directory to search in
            pattern: Search pattern
            file_type: Optional file type filter (e.g., "py", "ts", "java")
            case_sensitive: Whether search is case-sensitive (default: True)
            is_regex: Whether pattern is a regex (default: False)

        Returns:
            Dictionary with keys:
                - success: bool
                - matches: list[dict] with file, line_number, line_content (if successful)
                - count: int (number of matches, if successful)
                - error: str (if failed)

        Example:
            >>> api = TreeSitterAnalyzerAPI()
            >>> result = api.search_content(".", pattern="class")
            >>> if result["success"]:
            ...     for match in result["matches"]:
            ...         print(f"{match['file']}:{match['line_number']}")
        """
        root_path = Path(root_dir)

        # Check directory exists
        if not root_path.exists():
            return {"success": False, "error": f"Directory not found: {root_dir}"}

        try:
            matches = self._search_engine.search_content(
                root_dir=str(root_path),
                pattern=pattern,
                file_type=file_type,
                case_sensitive=case_sensitive,
                is_regex=is_regex,
            )

            return {"success": True, "matches": matches, "count": len(matches)}

        except Exception as e:
            return {"success": False, "error": f"Error searching content: {str(e)}"}

    def extract_code_section(
        self,
        file_path: str,
        start_line: int,
        end_line: int | None = None,
        output_format: str = "toon",
    ) -> dict[str, Any]:
        """
        Extract a specific code section by line range.

        Args:
            file_path: Path to the code file
            start_line: Starting line number (1-based)
            end_line: Ending line number (1-based, optional - reads to end if not specified)
            output_format: Output format ("toon" or "markdown", default: "toon")

        Returns:
            Dictionary with keys:
                - success: bool
                - content: str (extracted code, if success and output_format="toon")
                - data: str (formatted output, if success and output_format="markdown")
                - range: dict (start_line, end_line)
                - lines_extracted: int
                - error: str (if failed)

        Example:
            >>> api = TreeSitterAnalyzerAPI()
            >>> result = api.extract_code_section(
            ...     "tree_sitter_analyzer_v2/graph/symbols.py",
            ...     start_line=212,
            ...     end_line=289,
            ...     output_format="markdown"
            ... )
            >>> if result["success"]:
            ...     print(result["data"])
        """
        path = Path(file_path).resolve()

        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        if not path.is_file():
            return {"success": False, "error": f"Not a file: {file_path}"}

        try:
            # Detect encoding and read
            detector = EncodingDetector()
            encoding = detector.detect_encoding(path)
            with open(path, encoding=encoding, errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            if start_line > total_lines:
                return {
                    "success": False,
                    "error": f"start_line {start_line} exceeds file length {total_lines}",
                }

            start_idx = start_line - 1
            end_idx = total_lines if end_line is None else min(end_line, total_lines)
            actual_end_line = end_idx

            extracted = "".join(lines[start_idx:end_idx])
            lines_extracted = end_idx - start_idx

            if output_format == "markdown":
                ext = path.suffix.lstrip(".")
                lang_map = {
                    "py": "python", "js": "javascript", "ts": "typescript",
                    "java": "java", "cpp": "cpp", "c": "c", "rs": "rust",
                    "go": "go", "rb": "ruby", "php": "php", "cs": "csharp",
                }
                lang = lang_map.get(ext, ext or "text")
                data = f"""# Code Section Extract

**File**: `{file_path}`
**Range**: Line {start_line}-{actual_end_line}
**Lines**: {lines_extracted}
**Size**: {len(extracted)} characters

```{lang}
{extracted}```
"""
                return {
                    "success": True,
                    "data": data,
                    "output_format": "markdown",
                    "range": {"start_line": start_line, "end_line": actual_end_line},
                    "lines_extracted": lines_extracted,
                }

            return {
                "success": True,
                "content": extracted,
                "file_path": file_path,
                "range": {"start_line": start_line, "end_line": actual_end_line},
                "lines_extracted": lines_extracted,
                "content_length": len(extracted),
                "output_format": output_format,
            }

        except Exception as e:
            return {"success": False, "error": f"Failed to extract code: {str(e)}"}


def extract_code_section(
    file_path: str,
    start_line: int,
    end_line: int | None = None,
    output_format: str = "toon",
) -> dict[str, Any]:
    """
    Extract a specific code section by line range (convenience function).

    Args:
        file_path: Path to the code file
        start_line: Starting line number (1-based)
        end_line: Ending line number (1-based, optional)
        output_format: "toon" or "markdown"

    Returns:
        Dictionary with success, content/data, and metadata.

    Example:
        >>> from tree_sitter_analyzer_v2.api.interface import extract_code_section
        >>> result = extract_code_section("symbols.py", 212, 289, output_format="markdown")
    """
    api = TreeSitterAnalyzerAPI()
    return api.extract_code_section(
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        output_format=output_format,
    )
