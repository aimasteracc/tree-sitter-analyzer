"""
Code Graph MCP Tool - Expose Code Graph functionality via MCP

Provides tools for:
- analyze_code_graph: Analyze code structure and relationships
- query_call_chain: Find call paths between functions
- find_function_callers: Find who calls a function
"""

from pathlib import Path
from typing import Any

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
                "page": {
                    "type": "integer",
                    "description": "Page number for paginated results (1-based, for directory analysis)",
                    "default": 1,
                },
                "page_size": {
                    "type": "integer",
                    "description": "Number of files per page (for directory analysis)",
                    "default": 10,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 300s for large projects)",
                    "default": 300,
                },
            },
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute code graph analysis"""
        file_path = arguments.get("file_path")
        directory = arguments.get("directory")
        detail_level = arguments.get("detail_level", "summary")
        include_private = arguments.get("include_private", False)
        max_tokens = arguments.get("max_tokens", 4000)
        cross_file = arguments.get("cross_file", False)
        language = arguments.get("language", "auto")
        page = arguments.get("page", 1)
        page_size = arguments.get("page_size", 10)
        # timeout = arguments.get("timeout", 300)  # Reserved for future use

        # Validate mutually exclusive parameters
        if file_path and directory:
            return {
                "success": False,
                "error": "Cannot specify both file_path and directory. Choose one.",
            }

        if not file_path and not directory:
            return {"success": False, "error": "Must specify either file_path or directory"}

        try:
            # Auto-detect language from file extension if needed
            if language == "auto":
                if file_path:
                    ext = Path(file_path).suffix.lower()
                    if ext == ".java":
                        language = "java"
                    elif ext == ".py":
                        language = "python"
                    else:
                        language = "python"  # Default to Python
                else:
                    language = "python"  # Default for directory analysis

            # Create builder for detected language
            builder = CodeGraphBuilder(language=language)

            # Single file analysis
            if file_path:
                # Validate file exists
                if not Path(file_path).exists():
                    return {"success": False, "error": f"File not found: {file_path}"}

                graph = builder.build_from_file(file_path)
                # target = file_path  # Reserved for future use

            # Directory analysis
            else:
                # Validate directory exists
                if not Path(directory).exists():
                    return {"success": False, "error": f"Directory not found: {directory}"}

                pattern = arguments.get("pattern", "**/*.py")
                exclude_patterns = arguments.get("exclude_patterns", [])
                max_files = arguments.get("max_files")

                # Determine effective max_files:
                # 1. Explicit max_files from user takes highest priority
                # 2. Pagination (page > 1) applies if no explicit max_files
                # 3. Otherwise, no limit
                if max_files is not None:
                    effective_max_files = max_files
                    pagination_info = None
                elif page > 1:
                    # Apply pagination only when explicitly navigating pages
                    import fnmatch
                    all_files = []
                    dir_path = Path(directory)
                    for file in dir_path.rglob(pattern):
                        if file.is_file():
                            excluded = False
                            for exclude_pattern in exclude_patterns:
                                if fnmatch.fnmatch(str(file), exclude_pattern):
                                    excluded = True
                                    break
                            if not excluded:
                                all_files.append(str(file))

                    total_files = len(all_files)
                    total_pages = (total_files + page_size - 1) // page_size
                    start_idx = (page - 1) * page_size
                    end_idx = min(start_idx + page_size, total_files)

                    effective_max_files = end_idx

                    pagination_info = {
                        "page": page,
                        "page_size": page_size,
                        "total_files": total_files,
                        "total_pages": total_pages,
                        "files_in_page": end_idx - start_idx,
                        "has_next": page < total_pages,
                        "has_prev": page > 1,
                    }
                else:
                    effective_max_files = None
                    pagination_info = None

                graph = builder.build_from_directory(
                    directory,
                    pattern=pattern,
                    exclude_patterns=exclude_patterns,
                    max_files=effective_max_files,
                    cross_file=cross_file,
                )
                # target = directory  # Reserved for future use

            # Statistics
            nodes = graph.number_of_nodes()
            edges = graph.number_of_edges()
            functions = len([n for n, d in graph.nodes(data=True) if d["type"] == "FUNCTION"])
            classes = len([n for n, d in graph.nodes(data=True) if d["type"] == "CLASS"])
            modules = len([n for n, d in graph.nodes(data=True) if d["type"] == "MODULE"])

            # Calculate cross-file calls count (only when cross_file is enabled)
            cross_file_calls = 0
            if cross_file:
                cross_file_calls = len(
                    [
                        (u, v)
                        for u, v, d in graph.edges(data=True)
                        if d.get("type") == "CALLS" and d.get("cross_file") is True
                    ]
                )

            # Export as TOON
            toon_output = export_for_llm(
                graph,
                max_tokens=max_tokens,
                detail_level=detail_level,
                include_private=include_private,
            )

            result = {
                "success": True,
                "language": language,
                "statistics": {
                    "nodes": nodes,
                    "edges": edges,
                    "modules": modules,
                    "classes": classes,
                    "functions": functions,
                },
                "structure": toon_output,
                "format": "toon",
            }

            # Add cross_file_calls to statistics if cross_file is enabled
            if cross_file:
                result["statistics"]["cross_file_calls"] = cross_file_calls

            # Add source information
            if file_path:
                result["file_path"] = file_path
            else:
                result["directory"] = directory
                # Add pagination info for directory analysis if available
                if pagination_info:
                    result["pagination"] = pagination_info
                result["files_analyzed"] = graph.graph.get("files_analyzed", 0)
                if "pattern" in graph.graph:
                    result["pattern"] = graph.graph["pattern"]
                if "exclude_patterns" in graph.graph:
                    result["exclude_patterns"] = graph.graph["exclude_patterns"]

            return result

        except Exception as e:
            return {"success": False, "error": str(e)}


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
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            # Auto-detect language from file extension if needed
            if language == "auto":
                ext = Path(file_path).suffix.lower()
                if ext == ".java":
                    language = "java"
                elif ext == ".py":
                    language = "python"
                else:
                    language = "python"  # Default to Python

            # Build graph
            builder = CodeGraphBuilder(language=language)
            graph = builder.build_from_file(file_path)

            # Find function definition
            defs = find_definition(graph, function_name)

            if not defs:
                return {
                    "success": False,
                    "error": f"Function '{function_name}' not found in {file_path}",
                }

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
            return {"success": False, "error": str(e)}


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
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            # Auto-detect language from file extension if needed
            if language == "auto":
                ext = Path(file_path).suffix.lower()
                if ext == ".java":
                    language = "java"
                elif ext == ".py":
                    language = "python"
                else:
                    language = "python"  # Default to Python

            # Build graph
            builder = CodeGraphBuilder(language=language)
            graph = builder.build_from_file(file_path)

            # Find start and end functions
            start_defs = find_definition(graph, start_function)
            end_defs = find_definition(graph, end_function)

            if not start_defs:
                return {"success": False, "error": f"Start function '{start_function}' not found"}

            if not end_defs:
                return {"success": False, "error": f"End function '{end_function}' not found"}

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
            return {"success": False, "error": str(e)}


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
        """Execute code graph visualization"""
        file_path = arguments.get("file_path")
        directory = arguments.get("directory")
        viz_type = arguments.get("visualization_type", "flowchart")
        start_function = arguments.get("start_function")
        max_nodes = arguments.get("max_nodes", 50)
        max_depth = arguments.get("max_depth", 5)
        show_classes = arguments.get("show_classes", True)
        direction = arguments.get("direction", "TD")
        language = arguments.get("language", "auto")

        try:
            # Auto-detect language from file extension if needed
            if language == "auto":
                if file_path:
                    ext = Path(file_path).suffix.lower()
                    if ext == ".java":
                        language = "java"
                    elif ext == ".py":
                        language = "python"
                    else:
                        language = "python"  # Default to Python
                else:
                    language = "python"  # Default for directory analysis

            builder = CodeGraphBuilder(language=language)

            # Different visualization types have different requirements
            if viz_type == "flowchart":
                if not file_path and not directory:
                    return {"success": False, "error": "flowchart requires file_path or directory"}

                # Build graph
                if file_path:
                    if not Path(file_path).exists():
                        return {"success": False, "error": f"File not found: {file_path}"}
                    graph = builder.build_from_file(file_path)
                    source = file_path
                else:
                    if not Path(directory).exists():
                        return {"success": False, "error": f"Directory not found: {directory}"}
                    graph = builder.build_from_directory(directory)
                    source = directory

                # Generate Mermaid diagram
                mermaid = export_to_mermaid(
                    graph, max_nodes=max_nodes, show_classes=show_classes, direction=direction
                )

                return {
                    "success": True,
                    "visualization_type": "flowchart",
                    "source": source,
                    "mermaid": mermaid,
                    "format": "mermaid",
                }

            elif viz_type == "call_flow":
                if not file_path:
                    return {"success": False, "error": "call_flow requires file_path"}

                if not start_function:
                    return {"success": False, "error": "call_flow requires start_function"}

                if not Path(file_path).exists():
                    return {"success": False, "error": f"File not found: {file_path}"}

                # Build graph
                graph = builder.build_from_file(file_path)

                # Generate call flow diagram
                mermaid = export_to_call_flow(
                    graph, start_function=start_function, max_depth=max_depth
                )

                return {
                    "success": True,
                    "visualization_type": "call_flow",
                    "file_path": file_path,
                    "start_function": start_function,
                    "mermaid": mermaid,
                    "format": "mermaid",
                }

            elif viz_type == "dependency":
                if not directory:
                    return {"success": False, "error": "dependency requires directory"}

                if not Path(directory).exists():
                    return {"success": False, "error": f"Directory not found: {directory}"}

                # Build graph from directory
                graph = builder.build_from_directory(directory)

                # Generate dependency diagram
                mermaid = export_to_dependency_graph(graph, max_modules=max_nodes)

                return {
                    "success": True,
                    "visualization_type": "dependency",
                    "directory": directory,
                    "mermaid": mermaid,
                    "format": "mermaid",
                }

            else:
                return {"success": False, "error": f"Unknown visualization type: {viz_type}"}

        except Exception as e:
            return {"success": False, "error": str(e)}
