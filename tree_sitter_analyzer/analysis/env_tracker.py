#!/usr/bin/env python3
"""
Environment Variable Tracking Engine.

Tracks environment variable usage across codebases to help developers
understand configuration requirements and avoid missing deployment configs.

Detects environment variable references in:
- Python: os.getenv(), os.environ[], os.environ.get()
- JavaScript/TypeScript: process.env.VAR, process.env["VAR"]
- Java: System.getenv(), System.getProperty()
- Go: os.Getenv()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter

from tree_sitter_analyzer.utils import setup_logger

if TYPE_CHECKING:
    from tree_sitter import Parser, Tree

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}


class AccessType(Enum):
    """Type of environment variable access."""

    GETENV_CALL = "getenv_call"  # os.getenv("VAR")
    ENVIRON_INDEX = "environ_index"  # os.environ["VAR"]
    ENVIRON_GET = "environ_get"  # os.environ.get("VAR")
    PROPERTY_ACCESS = "property_access"  # process.env.VAR
    SYSTEM_GETENV = "system_getenv"  # System.getenv()
    SYSTEM_GETPROPERTY = "system_getproperty"  # System.getProperty()
    GO_GETENV = "go_getenv"  # os.Getenv()


@dataclass(frozen=True)
class EnvVarReference:
    """A single environment variable reference."""

    var_name: str
    file_path: str
    line: int
    column: int
    access_type: str
    context: str  # Surrounding code snippet
    has_default: bool = False


@dataclass
class EnvVarUsage:
    """Aggregated usage information for a single environment variable."""

    var_name: str
    references: list[EnvVarReference] = field(default_factory=list)
    file_count: int = 0
    total_references: int = 0
    has_default_count: int = 0  # How many refs have default values
    access_types: dict[str, int] = field(default_factory=dict)

    def add_reference(self, ref: EnvVarReference) -> None:
        """Add a reference and update counts."""
        self.references.append(ref)
        self.total_references += 1
        if ref.has_default:
            self.has_default_count += 1

        # Update file count
        files = {r.file_path for r in self.references}
        self.file_count = len(files)

        # Update access type counts
        self.access_types[ref.access_type] = (
            self.access_types.get(ref.access_type, 0) + 1
        )


@dataclass
class EnvTrackingResult:
    """Result of environment variable tracking on a file or project."""

    total_references: int = 0
    unique_vars: int = 0
    by_file: dict[str, int] = field(default_factory=dict)
    by_var: dict[str, EnvVarUsage] = field(default_factory=dict)

    def add_reference(self, ref: EnvVarReference) -> None:
        """Add a reference and update aggregations."""
        self.total_references += 1

        # Update file count
        self.by_file[ref.file_path] = (
            self.by_file.get(ref.file_path, 0) + 1
        )

        # Update variable usage
        if ref.var_name not in self.by_var:
            self.by_var[ref.var_name] = EnvVarUsage(var_name=ref.var_name)
            self.unique_vars += 1
        self.by_var[ref.var_name].add_reference(ref)


class EnvVarTracker:
    """Track environment variable usage in code."""

    # Mapping of file extensions to tree-sitter language modules
    _LANGUAGE_MODULES: dict[str, str] = {
        ".py": "tree_sitter_python",
        ".js": "tree_sitter_javascript",
        ".ts": "tree_sitter_typescript",
        ".tsx": "tree_sitter_typescript",
        ".jsx": "tree_sitter_javascript",
        ".java": "tree_sitter_java",
        ".go": "tree_sitter_go",
    }

    def __init__(
        self,
        project_root: str | Path,
        include_defaults: bool = True,
    ) -> None:
        """Initialize the tracker.

        Args:
            project_root: Root directory of the project.
            include_defaults: Whether to include calls with default values.
        """
        self.project_root = Path(project_root).resolve()
        self.include_defaults = include_defaults
        self._languages: dict[str, tree_sitter.Language] = {}
        self._parsers: dict[str, tree_sitter.Parser] = {}

    def _get_parser(self, extension: str) -> tuple[tree_sitter.Language | None, tree_sitter.Parser | None]:
        """Get tree-sitter Language and Parser for a file extension.

        Args:
            extension: File extension (e.g., ".py").

        Returns:
            Tuple of (Language, Parser) or (None, None) if not found.
        """
        if extension not in self._LANGUAGE_MODULES:
            return None, None

        if extension not in self._parsers:
            module_name = self._LANGUAGE_MODULES[extension]
            try:
                # Import the language module
                lang_module = __import__(module_name)
                # Get the language() function
                language_func = getattr(lang_module, "language")
                # Create the language object
                language = tree_sitter.Language(language_func())
                self._languages[extension] = language
                # Create the parser with the language
                parser = tree_sitter.Parser(language)
                self._parsers[extension] = parser
            except Exception as e:
                logger.error(f"Failed to load language for {extension}: {e}")
                return None, None

        return self._languages.get(extension), self._parsers.get(extension)

    def track_file(self, file_path: str | Path) -> EnvTrackingResult:
        """Track environment variables in a single file.

        Args:
            file_path: Path to the file to analyze.

        Returns:
            EnvTrackingResult with all found references.
        """
        file_path = Path(file_path).resolve()
        result = EnvTrackingResult()

        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return result

        if file_path.suffix not in SUPPORTED_EXTENSIONS:
            logger.debug(f"Unsupported file type: {file_path.suffix}")
            return result

        # Get language-specific parser
        language, parser = self._get_parser(file_path.suffix)
        if language is None or parser is None:
            logger.debug(f"No language found for extension: {file_path.suffix}")
            return result

        try:
            content = file_path.read_text(encoding="utf-8")
            tree = parser.parse(content.encode("utf-8"))

            # Language-specific detection
            if file_path.suffix == ".py":
                refs = self._track_python(file_path, tree, content, language)
            elif file_path.suffix in (".js", ".ts", ".tsx", ".jsx"):
                refs = self._track_javascript(file_path, tree, content, language)
            elif file_path.suffix == ".java":
                refs = self._track_java(file_path, tree, content, language)
            elif file_path.suffix == ".go":
                refs = self._track_go(file_path, tree, content, language)
            else:
                refs = []

            # Add all references to result
            for ref in refs:
                if not ref.has_default or self.include_defaults:
                    result.add_reference(ref)

        except Exception as e:
            logger.error(f"Error tracking file {file_path}: {e}")

        return result

    def _track_python(
        self,
        file_path: Path,
        tree: Tree,
        content: str,
        language: tree_sitter.Language,
    ) -> list[EnvVarReference]:
        """Track env vars in Python code."""
        refs = []

        # Pattern 1: os.getenv("VAR") or os.getenv("VAR", "default")
        query = language.query(
        for node, tag in captures:
            if tag == "var_name":
                var_name = node.text.decode("utf-8").strip('"\'')
                line = node.start_point[0] + 1
                col = node.start_point[1] + 1
                context = self._get_context(content, line, col)

                # Check for default value
                has_default = any(
                    t == "default" for n, t in captures if n.start_point == node.start_point
                )

                refs.append(EnvVarReference(
                    var_name=var_name,
                    file_path=str(file_path),
                    line=line,
                    column=col,
                    access_type=AccessType.GETENV_CALL.value,
                    context=context,
                    has_default=has_default,
                ))

        # Pattern 2: os.environ["VAR"] or os.environ.get("VAR")
        query2 = language.query(
            """
            (subscript
                object: (attribute
                    object: (identifier) @obj
                    attribute: (identifier) @attr
                    (#eq? @obj "os")
                    (#eq? @attr "environ"))
                subscript: (string (string_content) @var_name)) @ref
            """
        )

        captures2 = query2.captures(tree.root_node)
        for node, tag in captures2:
            if tag == "var_name":
                var_name = node.text.decode("utf-8").strip('"\'')
                line = node.start_point[0] + 1
                col = node.start_point[1] + 1
                context = self._get_context(content, line, col)

                refs.append(EnvVarReference(
                    var_name=var_name,
                    file_path=str(file_path),
                    line=line,
                    column=col,
                    access_type=AccessType.ENVIRON_INDEX.value,
                    context=context,
                    has_default=False,
                ))

        # Pattern 3: os.environ.get("VAR") or os.environ.get("VAR", "default")
        query3 = language.query(
            """
            (call
                function: (attribute
                    object: (attribute
                        object: (identifier) @obj
                        attribute: (identifier) @attr1
                        (#eq? @obj "os")
                        (#eq? @attr1 "environ"))
                    attribute: (identifier) @attr2
                    (#eq? @attr2 "get"))
                arguments: (argument_list
                    (string (string_content) @var_name)
                    (_)? @default) @ref
            """
        )

        captures3 = query3.captures(tree.root_node)
        for node, tag in captures3:
            if tag == "var_name":
                var_name = node.text.decode("utf-8").strip('"\'')
                line = node.start_point[0] + 1
                col = node.start_point[1] + 1
                context = self._get_context(content, line, col)

                has_default = any(
                    t == "default" for n, t in captures3
                    if abs(n.start_point[0] - node.start_point[0]) <= 2
                )

                refs.append(EnvVarReference(
                    var_name=var_name,
                    file_path=str(file_path),
                    line=line,
                    column=col,
                    access_type=AccessType.ENVIRON_GET.value,
                    context=context,
                    has_default=has_default,
                ))

        return refs

    def _track_javascript(
        self,
        file_path: Path,
        tree: Tree,
        content: str,
        language: tree_sitter.Language,
    ) -> list[EnvVarReference]:
        """Track env vars in JavaScript/TypeScript code."""
        refs = []

        # Pattern 1: process.env.VAR_NAME
        query = language.query(
            """
            (member_expression
                object: (member_expression
                    object: (identifier) @obj
                    property: (property_identifier) @prop
                    (#eq? @obj "process")
                    (#eq? @prop "env"))
                property: (property_identifier) @var_name) @ref
            """
        )

        query_cursor = tree_sitter.QueryCursor(query, tree.root_node)
        captures = query_cursor.captures()
        for node, tag in captures:
            if tag == "var_name":
                var_name = node.text.decode("utf-8")
                line = node.start_point[0] + 1
                col = node.start_point[1] + 1
                context = self._get_context(content, line, col)

                refs.append(EnvVarReference(
                    var_name=var_name,
                    file_path=str(file_path),
                    line=line,
                    column=col,
                    access_type=AccessType.PROPERTY_ACCESS.value,
                    context=context,
                    has_default=False,
                ))

        # Pattern 2: process.env["VAR_NAME"]
        query2 = language.query(
            """
            (subscript
                object: (member_expression
                    object: (identifier) @obj
                    property: (property_identifier) @prop
                    (#eq? @obj "process")
                    (#eq? @prop "env"))
                subscript: (string (string_content) @var_name)) @ref
            """
        )

        captures2 = query2.captures(tree.root_node)
        for node, tag in captures2:
            if tag == "var_name":
                var_name = node.text.decode("utf-8").strip('"\'')
                line = node.start_point[0] + 1
                col = node.start_point[1] + 1
                context = self._get_context(content, line, col)

                refs.append(EnvVarReference(
                    var_name=var_name,
                    file_path=str(file_path),
                    line=line,
                    column=col,
                    access_type=AccessType.ENVIRON_INDEX.value,
                    context=context,
                    has_default=False,
                ))

        return refs

    def _track_java(
        self,
        file_path: Path,
        tree: Tree,
        content: str,
        language: tree_sitter.Language,
    ) -> list[EnvVarReference]:
        """Track env vars in Java code."""
        refs = []

        # Pattern 1: System.getenv("VAR")
        query = language.query(
            """
            (method_invocation
                object: (identifier) @obj
                name: (identifier) @method
                (#eq? @obj "System")
                (#match? @method "getenv|getProperty")
                arguments: (argument_list
                    (string_literal
                        (string_content) @var_name))) @ref
            """
        )

        query_cursor = tree_sitter.QueryCursor(query, tree.root_node)
        captures = query_cursor.captures()
        for node, tag in captures:
            if tag == "var_name":
                var_name = node.text.decode("utf-8").strip('"\'')
                line = node.start_point[0] + 1
                col = node.start_point[1] + 1
                context = self._get_context(content, line, col)

                access_type = (
                    AccessType.SYSTEM_GETENV.value
                    if "getenv" in content[node.start_point[0]:node.end_point[0]]
                    else AccessType.SYSTEM_GETPROPERTY.value
                )

                refs.append(EnvVarReference(
                    var_name=var_name,
                    file_path=str(file_path),
                    line=line,
                    column=col,
                    access_type=access_type,
                    context=context,
                    has_default=False,
                ))

        return refs

    def _track_go(
        self,
        file_path: Path,
        tree: Tree,
        content: str,
        language: tree_sitter.Language,
    ) -> list[EnvVarReference]:
        """Track env vars in Go code."""
        refs = []

        # Pattern: os.Getenv("VAR")
        query = language.query(
            """
            (call_expression
                function: (selector_expression
                    operand: (identifier) @obj
                    field: (identifier) @method
                    (#eq? @obj "os")
                    (#eq? @method "Getenv"))
                arguments: (argument_list
                    (interpreted_string_literal
                        (interpreted_string_content) @var_name))) @ref
            """
        )

        query_cursor = tree_sitter.QueryCursor(query, tree.root_node)
        captures = query_cursor.captures()
        for node, tag in captures:
            if tag == "var_name":
                var_name = node.text.decode("utf-8").strip('"\'')
                line = node.start_point[0] + 1
                col = node.start_point[1] + 1
                context = self._get_context(content, line, col)

                refs.append(EnvVarReference(
                    var_name=var_name,
                    file_path=str(file_path),
                    line=line,
                    column=col,
                    access_type=AccessType.GO_GETENV.value,
                    context=context,
                    has_default=False,
                ))

        return refs

    def _get_context(
        self,
        content: str,
        line: int,
        col: int,
        context_lines: int = 2,
    ) -> str:
        """Get surrounding code context for a reference."""
        lines = content.split("\n")
        start = max(0, line - context_lines - 1)
        end = min(len(lines), line + context_lines)
        context_lines_list = lines[start:end]
        return "\n".join(f"{i + start + 1}: {line_content}" for i, line_content in enumerate(context_lines_list))


def track_env_vars(
    file_path: str | Path,
    project_root: str | Path | None = None,
    include_defaults: bool = True,
) -> EnvTrackingResult:
    """Convenience function to track environment variables in a file.

    Args:
        file_path: Path to the file to analyze.
        project_root: Root directory of the project.
        include_defaults: Whether to include calls with default values.

    Returns:
        EnvTrackingResult with all found references.
    """
    if project_root is None:
        project_root = Path(file_path).parent
    tracker = EnvVarTracker(project_root, include_defaults)
    return tracker.track_file(file_path)


def group_by_var_name(
    references: list[EnvVarReference],
) -> dict[str, EnvVarUsage]:
    """Group references by variable name.

    Args:
        references: List of environment variable references.

    Returns:
        Dictionary mapping variable names to EnvVarUsage objects.
    """
    by_var: dict[str, EnvVarUsage] = {}
    for ref in references:
        if ref.var_name not in by_var:
            by_var[ref.var_name] = EnvVarUsage(var_name=ref.var_name)
        by_var[ref.var_name].add_reference(ref)
    return by_var
