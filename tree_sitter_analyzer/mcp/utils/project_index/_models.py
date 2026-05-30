"""
Data models and module-level constants for project_index.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Path segments that should be excluded from the language-distribution
# count. They contain valid source files (fixtures, golden masters,
# internal audit docs, generated reports) but those files are NOT part
# of the project's "actual source mix" — counting them inflates
# secondary languages and misleads the headline number.
_LANGUAGE_COUNT_EXCLUDED_SEGMENTS: frozenset[str] = frozenset(
    {
        "tests/golden_masters",
        "tests/fixtures",
        "tests/test_data",
        "tests/golden",
        "docs/internal",
        "compatibility_test/results",
        "corpus",
        "examples",
        ".tree-sitter-cache",
        ".ast-cache",
        # Build artefacts + dev-tooling caches (see project_overview_tool
        # for the same rationale — keep these two lists in sync).
        "comprehensive_test_results",
        "openspec",
        ".claude",
        ".agents",
        ".swarm",
        ".kiro",
        ".roo",
        ".autonomous-runtime",
        ".claude-flow",
    }
)

# Names that look like classes to the AST-based edge extractor but are
# actually Python typing / stdlib helpers — they should never surface
# as "critical architectural nodes". TYPE_CHECKING is the worst case:
# every type-annotated module imports it, so PageRank ranks it #3 on
# any large project, where it conveys zero architectural meaning.
_PAGERANK_STDLIB_BLOCKLIST: frozenset[str] = frozenset(
    {
        # typing
        "TYPE_CHECKING",
        "Any",
        "Optional",
        "Union",
        "Literal",
        "ClassVar",
        "Final",
        "Annotated",
        "Generic",
        "Protocol",
        "TypeVar",
        "TypedDict",
        "NamedTuple",
        "Iterator",
        "Iterable",
        "Sequence",
        "Mapping",
        "Callable",
        "Awaitable",
        "AsyncIterator",
        "Coroutine",
        # common stdlib namespaces masquerading as classes
        "Path",
        "Exception",
        "ValueError",
        "TypeError",
        "RuntimeError",
        "OSError",
        # tree-sitter internal node types that aren't user classes
        "Node",
        "Tree",
        "Parser",
        "Language",
        "Query",
    }
)

# Map file extensions to canonical language names
_EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".m": "objc",
    ".mm": "objc",
    ".scala": "scala",
    ".hs": "haskell",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".clj": "clojure",
    ".lua": "lua",
    ".r": "r",
    ".R": "r",
    ".jl": "julia",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".fish": "shell",
    ".ps1": "powershell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".xml": "xml",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".md": "markdown",
    ".mdx": "markdown",
    ".rst": "rst",
    ".tex": "latex",
    ".sql": "sql",
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".tf": "terraform",
    ".hcl": "hcl",
    ".dockerfile": "dockerfile",
    ".nix": "nix",
    ".vim": "vim",
}

# Key config / documentation files to identify
_KEY_FILE_NAMES: set[str] = {
    "readme",
    "readme.md",
    "readme.rst",
    "readme.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "cargo.toml",
    "go.mod",
    "makefile",
    "rakefile",
    "gemfile",
    "build.gradle",
    "pom.xml",
    "cmakeLists.txt",
    "dockerfile",
    ".claude",
    "claude.md",
    ".env.example",
    ".envrc",
    "justfile",
    "taskfile.yml",
    "taskfile.yaml",
}

# Entry-point file names to identify
_ENTRY_POINT_NAMES: set[str] = {
    "main.py",
    "__main__.py",
    "app.py",
    "run.py",
    "server.py",
    "index.ts",
    "index.js",
    "index.mjs",
    "main.ts",
    "main.js",
    "main.go",
    "main.rs",
    "main.c",
    "main.cpp",
    "main.java",
    "app.ts",
    "app.js",
    "app.rb",
    "application.rb",
    "manage.py",
    "cli.py",
    "cmd/main.go",
}

# Fallback descriptions for well-known directory names
_DIR_CONVENTIONS: dict[str, str] = {
    "tests": "Test suite",
    "test": "Test suite",
    "unit": "Unit tests",
    "integration": "Integration tests",
    "golden": "Golden master test fixtures",
    "golden_masters": "Golden master test fixtures",
    "fixtures": "Test fixtures",
    "docs": "Documentation",
    "doc": "Documentation",
    "examples": "Example code files",
    "scripts": "Build and utility scripts",
    "tools": "Tool implementations",
    "utils": "Shared utilities",
    "core": "Core implementation",
    "cli": "Command-line interface",
    "api": "API layer",
    "models": "Data models",
    "config": "Configuration",
    "resources": "Resource files",
    "assets": "Static assets",
    "security": "Security and validation",
    "formatters": "Output formatters",
    "languages": "Language-specific configurations",
    "queries": "Query definitions",
    "plugins": "Plugin system",
    "platform_compat": "Platform compatibility",
}


@dataclass
class ProjectIndex:
    """Persistent snapshot of a project's architecture."""

    project_root: str
    created_at: float
    updated_at: float
    file_count: int
    language_distribution: dict[str, int]
    top_level_structure: list[dict[str, Any]]
    key_files: list[str]
    entry_points: list[str]
    custom_notes: str
    schema_version: str
    readme_excerpt: str
    module_descriptions: dict[str, str]
    critical_nodes: list[dict[str, Any]] = field(default_factory=list)
    module_dependency_order: list[str] = field(default_factory=list)
