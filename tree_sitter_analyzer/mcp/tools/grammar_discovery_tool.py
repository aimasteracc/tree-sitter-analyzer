"""
Grammar Discovery MCP Tool

Exposes grammar auto-discovery functionality as an MCP tool.
Allows runtime introspection of tree-sitter grammars.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from tree_sitter_analyzer.grammar_discovery.introspector import GrammarIntrospector
from tree_sitter_analyzer.grammar_discovery.path_enumerator import PathEnumerator
from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool
from tree_sitter_analyzer.plugins.registry import PluginRegistry
from tree_sitter_analyzer.utils import setup_logger

# Set up logging
logger = setup_logger(__name__)


class GrammarDiscoveryTool(BaseMCPTool):
    """
    Grammar Discovery MCP Tool.

    Provides runtime introspection of tree-sitter grammars:
    - Enumerate node types and fields
    - Detect wrapper node types
    - Discover syntactic paths
    """

    name = "grammar_discovery"

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize the grammar discovery tool."""
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        """Get the MCP tool definition."""
        return self.get_schema()

    def get_schema(self) -> dict[str, Any]:
        """Get the tool schema."""
        return {
            "name": self.name,
            "description": "Runtime introspection of tree-sitter grammars - discover node types, fields, wrappers, and syntactic paths",
            "type": "object",
            "properties": {
                "project_root": {
                    "type": "string",
                    "description": "Path to the project root directory",
                },
                "language": {
                    "type": "string",
                    "description": "Language to analyze (e.g., 'python', 'javascript')",
                },
                "operation": {
                    "type": "string",
                    "enum": ["summary", "node_types", "fields", "wrappers", "paths"],
                    "description": "Operation to perform",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["toon", "json"],
                    "description": "Output format (default: toon)",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum depth for path enumeration (default: 3)",
                },
            },
            "required": ["project_root", "language", "operation"],
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        Validate tool arguments.

        Args:
            arguments: Arguments to validate

        Returns:
            True if arguments are valid

        Raises:
            ValueError: If arguments are invalid
        """
        required = ["project_root", "language", "operation"]
        for arg in required:
            if arg not in arguments:
                raise ValueError(f"Missing required argument: {arg}")

        valid_operations = ["summary", "node_types", "fields", "wrappers", "paths"]
        if arguments.get("operation") not in valid_operations:
            raise ValueError(
                f"Invalid operation: {arguments.get('operation')}. "
                f"Must be one of {valid_operations}"
            )

        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the tool with the given arguments.

        Args:
            arguments: Tool arguments

        Returns:
            Dictionary containing execution results
        """
        # Validate arguments first
        self.validate_arguments(arguments)

        # Extract arguments
        project_root = arguments.get("project_root", "")
        language = arguments.get("language", "")
        operation = arguments.get("operation", "summary")
        output_format = arguments.get("output_format", "toon")
        max_depth = arguments.get("max_depth", 3)

        # Call the sync execute method
        return self._execute_sync(
            project_root=project_root,
            language=language,
            operation=operation,
            output_format=output_format,
            max_depth=max_depth,
        )

    def _execute_sync(
        self,
        project_root: str,
        language: str,
        operation: str,
        output_format: str = "toon",
        max_depth: int = 3,
    ) -> dict[str, Any]:
        """
        Execute the grammar discovery operation (sync implementation).

        Args:
            project_root: Path to the project root
            language: Language to analyze
            operation: Operation to perform
            output_format: Output format (toon or json)
            max_depth: Maximum depth for path enumeration

        Returns:
            Dictionary with operation results
        """
        logger.info(
            f"Grammar discovery: language={language}, operation={operation}"
        )

        # Get the language
        try:
            plugin_registry = PluginRegistry()
            plugin_registry.discover()
            plugin = plugin_registry.load(language)

            if plugin is None:
                return {
                    "success": False,
                    "error": f"Unsupported language: {language}",
                    "details": "Plugin not found",
                }

            # Get the tree-sitter Language object from the plugin
            if not hasattr(plugin, "get_tree_sitter_language"):
                return {
                    "success": False,
                    "error": f"Language plugin '{language}' does not support grammar introspection",
                    "details": "Plugin missing get_tree_sitter_language() method",
                }

            lang_instance = plugin.get_tree_sitter_language()  # type: ignore[attr-defined]
            if lang_instance is None:
                return {
                    "success": False,
                    "error": f"Failed to load tree-sitter language for: {language}",
                    "details": "get_tree_sitter_language() returned None",
                }

        except (ValueError, KeyError) as e:
            return {
                "success": False,
                "error": f"Unsupported language: {language}",
                "details": str(e),
            }

        # Execute operation
        result: dict[str, Any] = {"language": language, "operation": operation}

        if operation == "summary":
            introspector = GrammarIntrospector(lang_instance)
            summary = introspector.get_summary()
            result["summary"] = summary

        elif operation == "node_types":
            introspector = GrammarIntrospector(lang_instance)
            node_types = introspector.enumerate_node_types()
            result["node_types"] = [nt.to_dict() for nt in node_types]
            result["total_count"] = len(node_types)

        elif operation == "fields":
            introspector = GrammarIntrospector(lang_instance)
            fields = introspector.enumerate_fields()
            result["fields"] = [f.to_dict() for f in fields]
            result["total_count"] = len(fields)

        elif operation == "wrappers":
            introspector = GrammarIntrospector(lang_instance)
            wrappers = introspector.heuristic_wrapper_detection()
            result["wrappers"] = [w.to_dict() for w in wrappers]
            result["total_count"] = len(wrappers)

        elif operation == "paths":
            # Find code samples in project
            project_path = Path(project_root)
            code_files = self._find_code_files(project_path, language)

            if not code_files:
                return {
                    "success": False,
                    "error": f"No code files found for language: {language}",
                    "searched_path": str(project_path),
                }

            # Parse samples and enumerate paths
            from tree_sitter import Parser

            parser = Parser(lang_instance)
            enumerator = PathEnumerator(lang_instance, max_depth=max_depth)

            code_samples = []
            for file_path in code_files[:10]:  # Limit to 10 files for performance
                try:
                    with open(file_path, "rb") as f:
                        source_code = f.read()
                        tree = parser.parse(source_code)
                        code_samples.append(tree.root_node)
                except Exception as e:
                    logger.warning(f"Failed to parse {file_path}: {e}")
                    continue

            paths = enumerator.enumerate_paths_from_samples(code_samples)
            summary = enumerator.get_path_summary(paths)
            common = enumerator.find_common_patterns(paths, min_occurrences=2)

            result["paths_summary"] = summary
            result["common_patterns"] = [
                {"node_type": nt, "count": cnt, "sample_paths": len(paths)}
                for nt, cnt, paths in common[:20]  # Top 20 patterns
            ]

        result["success"] = True
        return result

    def _find_code_files(
        self,
        project_path: Path,
        language: str,
    ) -> list[Path]:
        """Find code files for the given language."""
        # File extensions by language
        extensions = {
            "python": [".py"],
            "javascript": [".js", ".jsx", ".mjs"],
            "typescript": [".ts", ".tsx"],
            "java": [".java"],
            "go": [".go"],
            "rust": [".rs"],
            "c": [".c", ".h"],
            "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".h"],
            "c_sharp": [".cs"],
            "ruby": [".rb"],
            "php": [".php"],
            "kotlin": [".kt", ".kts"],
        }

        exts = extensions.get(language, [])
        if not exts:
            return []

        code_files: list[Path] = []
        for ext in exts:
            code_files.extend(project_path.rglob(f"*{ext}"))

        return code_files

    def format_toon(self, result: dict[str, Any]) -> str:
        """Format result as TOON."""
        toon_parts = [
            f"# Grammar Discovery: {result.get('language', 'unknown')}",
            f"Operation: {result.get('operation', 'unknown')}",
            "",
        ]

        if "summary" in result:
            summary = result["summary"]
            toon_parts.extend([
                "## Grammar Summary",
                f"Node Types: {summary.get('total_node_types', 0)}",
                f"Named: {summary.get('named_node_types', 0)}",
                f"Anonymous: {summary.get('anonymous_node_types', 0)}",
                f"Fields: {summary.get('total_fields', 0)}",
                f"Wrapper Candidates: {summary.get('wrapper_candidates', 0)}",
                f"High Confidence: {summary.get('high_confidence_wrappers', 0)}",
                "",
            ])

        if "node_types" in result:
            toon_parts.extend([
                "## Node Types",
                f"Total: {result.get('total_count', 0)}",
                "",
            ])
            for nt in result["node_types"][:20]:  # First 20
                toon_parts.append(f"- {nt['kind_name']} (ID: {nt['kind_id']})")

        if "wrappers" in result:
            toon_parts.extend([
                "## Wrapper Candidates",
                f"Total: {result.get('total_count', 0)}",
                "",
            ])
            for wrapper in result["wrappers"][:20]:  # First 20
                toon_parts.append(
                    f"- {wrapper['node_type']} (confidence: {wrapper['confidence']})"
                )

        if "paths_summary" in result:
            summary = result["paths_summary"]
            toon_parts.extend([
                "## Syntactic Paths Summary",
                f"Total Paths: {summary.get('total_paths', 0)}",
                f"Unique Node Types: {summary.get('unique_node_types', 0)}",
                f"Max Depth: {summary.get('max_depth', 0)}",
                "",
            ])

        if "common_patterns" in result:
            toon_parts.extend([
                "## Common Patterns",
                "",
            ])
            for pattern in result["common_patterns"][:20]:
                toon_parts.append(
                    f"- {pattern['node_type']}: {pattern['count']} occurrences "
                    f"({pattern['sample_paths']} paths)"
                )

        if "error" in result:
            toon_parts.extend([
                "## Error",
                f"{result['error']}",
                "",
            ])
            if "details" in result:
                toon_parts.append(f"Details: {result['details']}")

        return "\n".join(toon_parts)
