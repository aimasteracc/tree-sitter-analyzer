"""
Code Graph MCP Tool - Expose Code Graph functionality via MCP

Provides tools for:
- analyze_code_graph: Analyze code structure and relationships
- query_call_chain: Find call paths between functions
- find_function_callers: Find who calls a function
"""

from pathlib import Path
from typing import Any

import networkx as nx

from tree_sitter_analyzer_v2.graph import (
    CodeGraphBuilder,
    export_for_llm,
    export_to_call_flow,
    export_to_dependency_graph,
    export_to_mermaid,
    find_definition,
    get_call_chain,
    get_callers,
)
from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class AnalyzeCodeGraphTool(BaseTool):
    """
    Analyze Python code structure and call relationships using Code Graph.

    Returns a TOON-formatted overview of modules, classes, functions, and their
    calling relationships. Optimized for LLM consumption with 50-70% token reduction.
    """

    def get_name(self) -> str:
        return "analyze_code_graph"

    def get_description(self) -> str:
        return """Analyze Python or Java code structure and call relationships.

**NEW: Java language support!**
**NEW: Multi-file analysis support!**
**NEW: Cross-file call resolution!**

Supports both single file and directory analysis:
- Single file: Analyze one Python (.py) or Java (.java) file
- Directory: Analyze entire codebase with glob patterns and exclusions
- Cross-file: Resolve function calls across file boundaries (set cross_file=true)
- Auto-detects language from file extension (.py → Python, .java → Java)

Returns a structured overview showing:
- Module/Class/Function hierarchy (or Package/Class/Method for Java)
- Function call relationships (who calls whom)
- Cross-file calls (when cross_file=true)
- TOON format optimized for AI consumption (50-70% fewer tokens)

Use this to quickly understand code structure, find dependencies,
and trace execution flow across multiple files.

Best for: Understanding unfamiliar code, impact analysis before refactoring,
generating documentation, analyzing entire projects."""

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to Python (.py) or Java (.java) file to analyze (mutually exclusive with directory)",
                },
                "directory": {
                    "type": "string",
                    "description": "Directory to analyze (mutually exclusive with file_path)",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern for file matching (default: **/*.py for Python, **/*.java for Java)",
                    "default": "**/*.py",
                },
                "language": {
                    "type": "string",
                    "enum": ["python", "java", "auto"],
                    "description": "Language to analyze (auto-detects from file extension if not specified)",
                    "default": "auto",
                },
                "exclude_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of glob patterns to exclude (e.g., ['**/test_*.py'])",
                    "default": [],
                },
                "max_files": {
                    "type": "integer",
                    "description": "Maximum number of files to process (only used with directory)",
                    "default": None,
                },
                "detail_level": {
                    "type": "string",
                    "enum": ["summary", "detailed"],
                    "description": "Summary (functions only) or Detailed (includes params/return types)",
                    "default": "summary",
                },
                "include_private": {
                    "type": "boolean",
                    "description": "Include private functions (starting with _)",
                    "default": False,
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Maximum tokens in output (approximate)",
                    "default": 4000,
                },
                "cross_file": {
                    "type": "boolean",
                    "description": "Enable cross-file call resolution (resolves calls across file boundaries)",
                    "default": False,
                },
            },
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute code graph analysis."""
        file_path: str | None = arguments.get("file_path")
        directory: str | None = arguments.get("directory")

        if file_path and directory:
            return self._error(
                "Cannot specify both file_path and directory. Choose one.",
                error_code="INVALID_ARGUMENT",
            )
        if not file_path and not directory:
            return self._error("Must specify either file_path or directory", error_code="INVALID_ARGUMENT")

        try:
            language = arguments.get("language", "auto")
            if language == "auto":
                language = self._detect_language_from_path(file_path)

            graph = self._build_graph(arguments, language, file_path, directory)
            return self._build_result(graph, arguments, language, file_path, directory)
        except Exception as e:
            return self._error(str(e), error_code="GRAPH_ERROR")

    def _build_graph(
        self, arguments: dict[str, Any], language: str,
        file_path: str | None, directory: str | None,
    ) -> nx.DiGraph:
        """Build the code graph from file or directory."""
        builder = CodeGraphBuilder(language=language)

        if file_path:
            if not Path(file_path).exists():
                raise FileNotFoundError(f"File not found: {file_path}")
            return builder.build_from_file(file_path)

        if directory is None:
            raise ValueError("Either file_path or directory must be provided")
        if not Path(directory).exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        return builder.build_from_directory(
            directory,
            pattern=arguments.get("pattern", "**/*.py"),
            exclude_patterns=arguments.get("exclude_patterns", []),
            max_files=arguments.get("max_files"),
            cross_file=arguments.get("cross_file", False),
        )

    def _build_result(
        self, graph: nx.DiGraph, arguments: dict[str, Any], language: str,
        file_path: str | None, directory: str | None,
    ) -> dict[str, Any]:
        """Build the result dict from a completed graph."""
        cross_file = arguments.get("cross_file", False)

        stats = self._graph_statistics(graph, cross_file)
        toon_output = export_for_llm(
            graph,
            max_tokens=arguments.get("max_tokens", 4000),
            detail_level=arguments.get("detail_level", "summary"),
            include_private=arguments.get("include_private", False),
        )

        result: dict[str, Any] = {
            "success": True,
            "language": language,
            "statistics": stats,
            "structure": toon_output,
            "format": "toon",
        }

        if file_path:
            result["file_path"] = file_path
        else:
            result["directory"] = directory
            result["files_analyzed"] = graph.graph.get("files_analyzed", 0)
            if "pattern" in graph.graph:
                result["pattern"] = graph.graph["pattern"]
            if "exclude_patterns" in graph.graph:
                result["exclude_patterns"] = graph.graph["exclude_patterns"]

        return result

    @staticmethod
    def _graph_statistics(graph: nx.DiGraph, cross_file: bool) -> dict[str, Any]:
        """Extract statistics from a built graph."""
        stats: dict[str, Any] = {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "modules": len([n for n, d in graph.nodes(data=True) if d["type"] == "MODULE"]),
            "classes": len([n for n, d in graph.nodes(data=True) if d["type"] == "CLASS"]),
            "functions": len([n for n, d in graph.nodes(data=True) if d["type"] == "FUNCTION"]),
        }
        if cross_file:
            stats["cross_file_calls"] = len([
                (u, v) for u, v, d in graph.edges(data=True)
                if d.get("type") == "CALLS" and d.get("cross_file") is True
            ])
        return stats


class FindFunctionCallersTool(BaseTool):
    """
    Find all functions that call a specific function.

    Useful for impact analysis before refactoring - shows what code
    depends on the target function.
    """

    def get_name(self) -> str:
        return "find_function_callers"

    def get_description(self) -> str:
        return """Find all functions that call a specific function (supports Python and Java).

Use this before refactoring to understand impact - shows which code
depends on the target function.

**NEW: Java language support!** Auto-detects from file extension.
**NEW: Cross-file support!** Set cross_file=true to resolve calls across
file boundaries (note: currently only single-file analysis is supported,
cross_file parameter is reserved for future directory analysis).

Returns: List of caller functions with their names and types."""

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to Python (.py) or Java (.java) file containing the function",
                },
                "function_name": {
                    "type": "string",
                    "description": "Name of the function/method to find callers for",
                },
                "cross_file": {
                    "type": "boolean",
                    "description": "Enable cross-file call resolution (default: False)",
                    "default": False,
                },
                "language": {
                    "type": "string",
                    "enum": ["python", "java", "auto"],
                    "description": "Language (auto-detects from file extension if not specified)",
                    "default": "auto",
                },
            },
            "required": ["file_path", "function_name"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Find callers of a function"""
        file_path = arguments["file_path"]
        function_name = arguments["function_name"]
        language = arguments.get("language", "auto")

        # Validate file exists
        if not Path(file_path).exists():
            return self._error(f"File not found: {file_path}", error_code="FILE_NOT_FOUND")

        try:
            # Auto-detect language from file extension if needed
            if language == "auto":
                language = self._detect_language_from_path(file_path)

            # Build graph
            builder = CodeGraphBuilder(language=language)
            graph = builder.build_from_file(file_path)

            # Find function definition
            defs = find_definition(graph, function_name)

            if not defs:
                return self._error(
                    f"Function '{function_name}' not found in {file_path}",
                    error_code="NOT_FOUND",
                )

            results = []
            for func_id in defs:
                # Get function info
                func_data = graph.nodes[func_id]

                # Find callers
                caller_ids = get_callers(graph, func_id)

                callers_info = []
                for caller_id in caller_ids:
                    caller_data = graph.nodes[caller_id]
                    callers_info.append(
                        {
                            "name": caller_data.get("name", "unknown"),
                            "type": caller_data.get("type", "unknown"),
                            "line_start": caller_data.get("start_line"),
                            "line_end": caller_data.get("end_line"),
                        }
                    )

                results.append(
                    {
                        "function_id": func_id,
                        "function_name": func_data.get("name"),
                        "caller_count": len(callers_info),
                        "callers": callers_info,
                    }
                )

            return {
                "success": True,
                "file_path": file_path,
                "function_name": function_name,
                "results": results,
            }

        except Exception as e:
            return self._error(str(e), error_code="GRAPH_ERROR")


class QueryCallChainTool(BaseTool):
    """
    Find call paths between two functions.

    Traces execution flow from start function to end function,
    showing all intermediate calls.
    """

    def get_name(self) -> str:
        return "query_call_chain"

    def get_description(self) -> str:
        return """Find call paths between two functions (supports Python and Java).

Traces execution flow from start function to end function,
showing all intermediate function calls.

**NEW: Java language support!** Auto-detects from file extension.
**NEW: Cross-file support!** Set cross_file=true to resolve calls across
file boundaries (note: currently only single-file analysis is supported,
cross_file parameter is reserved for future directory analysis).

Use for: Debugging deep call stacks, understanding execution flow,
performance analysis."""

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to Python (.py) or Java (.java) file to analyze",
                },
                "start_function": {
                    "type": "string",
                    "description": "Name of the starting function/method",
                },
                "end_function": {
                    "type": "string",
                    "description": "Name of the ending function/method",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum call chain depth to search",
                    "default": 10,
                },
                "cross_file": {
                    "type": "boolean",
                    "description": "Enable cross-file call resolution (default: False)",
                    "default": False,
                },
                "language": {
                    "type": "string",
                    "enum": ["python", "java", "auto"],
                    "description": "Language (auto-detects from file extension if not specified)",
                    "default": "auto",
                },
            },
            "required": ["file_path", "start_function", "end_function"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Find call chains between functions"""
        file_path = arguments["file_path"]
        start_function = arguments["start_function"]
        end_function = arguments["end_function"]
        max_depth = arguments.get("max_depth", 10)
        language = arguments.get("language", "auto")

        # Validate file exists
        if not Path(file_path).exists():
            return self._error(f"File not found: {file_path}", error_code="FILE_NOT_FOUND")

        try:
            # Auto-detect language from file extension if needed
            if language == "auto":
                language = self._detect_language_from_path(file_path)

            # Build graph
            builder = CodeGraphBuilder(language=language)
            graph = builder.build_from_file(file_path)

            # Find start and end functions
            start_defs = find_definition(graph, start_function)
            end_defs = find_definition(graph, end_function)

            if not start_defs:
                return self._error(f"Start function '{start_function}' not found", error_code="NOT_FOUND")

            if not end_defs:
                return self._error(f"End function '{end_function}' not found", error_code="NOT_FOUND")

            # Find call chains
            all_chains = []
            for start_id in start_defs:
                for end_id in end_defs:
                    chains = get_call_chain(graph, start_id, end_id, max_depth=max_depth)

                    for chain in chains:
                        # Convert node IDs to names
                        chain_names = [graph.nodes[n]["name"] for n in chain]
                        all_chains.append(
                            {"path": chain_names, "length": len(chain_names), "node_ids": chain}
                        )

            return {
                "success": True,
                "file_path": file_path,
                "start_function": start_function,
                "end_function": end_function,
                "chains_found": len(all_chains),
                "chains": all_chains,
            }

        except Exception as e:
            return self._error(str(e), error_code="GRAPH_ERROR")


class VisualizeCodeGraphTool(BaseTool):
    """
    Visualize Python or Java code structure and call relationships as Mermaid diagrams.

    Creates visual diagrams that Claude can render directly in conversations,
    making code structure instantly understandable.
    """

    def get_name(self) -> str:
        return "visualize_code_graph"

    def get_description(self) -> str:
        return """Visualize Python or Java code structure as Mermaid diagrams.

**NEW: Java language support!** Auto-detects from file extension.

Creates visual flowcharts showing:
- Function/method call relationships
- Call flow from a specific function
- Module dependency graph

**NEW: Visual diagrams for instant understanding!**

Supports multiple visualization types:
- "flowchart": General code structure with call relationships
- "call_flow": Execution flow starting from a function
- "dependency": Module dependencies

Claude can render these diagrams directly in the conversation,
making code structure immediately visible.

Best for: Understanding code flow, explaining architecture,
documentation generation, debugging call paths."""

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to Python file to visualize (for flowchart/call_flow)",
                },
                "directory": {
                    "type": "string",
                    "description": "Directory to analyze (for dependency graph)",
                },
                "visualization_type": {
                    "type": "string",
                    "enum": ["flowchart", "call_flow", "dependency"],
                    "description": "Type of visualization",
                    "default": "flowchart",
                },
                "start_function": {
                    "type": "string",
                    "description": "Starting function name (required for call_flow type)",
                },
                "max_nodes": {
                    "type": "integer",
                    "description": "Maximum nodes to show (prevents huge diagrams)",
                    "default": 50,
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum depth for call_flow",
                    "default": 5,
                },
                "show_classes": {
                    "type": "boolean",
                    "description": "Show class containers in flowchart",
                    "default": True,
                },
                "direction": {
                    "type": "string",
                    "enum": ["TD", "LR"],
                    "description": "Diagram direction (TD=top-down, LR=left-right)",
                    "default": "TD",
                },
            },
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute code graph visualization."""
        viz_type = arguments.get("visualization_type", "flowchart")
        language = arguments.get("language", "auto")

        try:
            if language == "auto":
                language = self._detect_language_from_path(arguments.get("file_path"))
            builder = CodeGraphBuilder(language=language)

            if viz_type == "flowchart":
                return self._viz_flowchart(arguments, builder)
            elif viz_type == "call_flow":
                return self._viz_call_flow(arguments, builder)
            elif viz_type == "dependency":
                return self._viz_dependency(arguments, builder)
            else:
                return self._error(f"Unknown visualization type: {viz_type}", error_code="INVALID_ARGUMENT")
        except Exception as e:
            return self._error(str(e), error_code="GRAPH_ERROR")

    def _viz_flowchart(self, args: dict[str, Any], builder: CodeGraphBuilder) -> dict[str, Any]:
        """Generate flowchart visualization."""
        file_path = args.get("file_path")
        directory = args.get("directory")
        if not file_path and not directory:
            return self._error("flowchart requires file_path or directory", error_code="INVALID_ARGUMENT")

        if file_path:
            if not Path(file_path).exists():
                return self._error(f"File not found: {file_path}", error_code="FILE_NOT_FOUND")
            graph = builder.build_from_file(file_path)
            source = file_path
        else:
            if directory is None:
                return self._error("Either file_path or directory must be provided", error_code="INVALID_ARGUMENT")
            if not Path(directory).exists():
                return self._error(f"Directory not found: {directory}", error_code="FILE_NOT_FOUND")
            graph = builder.build_from_directory(directory)
            source = directory

        mermaid = export_to_mermaid(
            graph, max_nodes=args.get("max_nodes", 50),
            show_classes=args.get("show_classes", True),
            direction=args.get("direction", "TD"),
        )
        return {"success": True, "visualization_type": "flowchart", "source": source,
                "mermaid": mermaid, "format": "mermaid"}

    def _viz_call_flow(self, args: dict[str, Any], builder: CodeGraphBuilder) -> dict[str, Any]:
        """Generate call flow visualization."""
        file_path = args.get("file_path")
        start_function = args.get("start_function")
        if not file_path:
            return self._error("call_flow requires file_path", error_code="INVALID_ARGUMENT")
        if not start_function:
            return self._error("call_flow requires start_function", error_code="INVALID_ARGUMENT")
        if not Path(file_path).exists():
            return self._error(f"File not found: {file_path}", error_code="FILE_NOT_FOUND")

        graph = builder.build_from_file(file_path)
        mermaid = export_to_call_flow(
            graph, start_function=start_function, max_depth=args.get("max_depth", 5),
        )
        return {"success": True, "visualization_type": "call_flow", "file_path": file_path,
                "start_function": start_function, "mermaid": mermaid, "format": "mermaid"}

    def _viz_dependency(self, args: dict[str, Any], builder: CodeGraphBuilder) -> dict[str, Any]:
        """Generate dependency visualization."""
        directory = args.get("directory")
        if not directory:
            return self._error("dependency requires directory", error_code="INVALID_ARGUMENT")
        if not Path(directory).exists():
            return self._error(f"Directory not found: {directory}", error_code="FILE_NOT_FOUND")

        graph = builder.build_from_directory(directory)
        mermaid = export_to_dependency_graph(graph, max_modules=args.get("max_nodes", 50))
        return {"success": True, "visualization_type": "dependency", "directory": directory,
                "mermaid": mermaid, "format": "mermaid"}
