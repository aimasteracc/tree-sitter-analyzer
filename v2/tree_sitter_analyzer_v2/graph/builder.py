"""
Code Graph Builder - Milestone 1: Basic Graph Construction.

Builds a NetworkX graph representing code structure:
- Module nodes (file-level)
- Class nodes
- Function nodes (module-level and class methods)
- CONTAINS edges (Module → Class, Module → Function, Class → Function)
"""

import pickle
from pathlib import Path
from typing import Any

import networkx as nx

from tree_sitter_analyzer_v2.languages.python_parser import PythonParser


class CodeGraphBuilder:
    """Builds code graphs from source files (multi-language support)."""

    def __init__(self, language: str = "python") -> None:
        """
        Initialize code graph builder for specified language.

        Args:
            language: Programming language ('python' or 'java', default: 'python')

        Raises:
            ValueError: If language is not supported
        """
        self.language = language.lower()

        # Initialize language-specific parser and call extractor
        if self.language == "python":
            from tree_sitter_analyzer_v2.graph.extractors import PythonCallExtractor

            self.parser = PythonParser()
            self.call_extractor = PythonCallExtractor()
        elif self.language == "java":
            from tree_sitter_analyzer_v2.graph.extractors import JavaCallExtractor
            from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

            self.parser = JavaParser()
            self.call_extractor = JavaCallExtractor()  # Will implement in T2.1
        else:
            raise ValueError(f"Unsupported language: {language}. Supported languages: python, java")

    def build_from_file(self, file_path: str) -> nx.DiGraph:
        """
        Build a code graph from a single Python file.

        Args:
            file_path: Path to Python file to analyze

        Returns:
            NetworkX directed graph with nodes and CONTAINS edges
        """
        path = Path(file_path)
        graph = nx.DiGraph()

        # Parse the file using PythonParser
        result = self.parser.parse(path.read_text(encoding="utf-8"), str(path))

        # Extract module node
        module_id = self._extract_module_node(graph, path, result)

        # Extract class nodes
        if "classes" in result and result["classes"]:
            for cls in result["classes"]:
                class_id = self._extract_class_node(graph, cls, module_id, result)

                # Add CONTAINS edge: Module → Class
                graph.add_edge(module_id, class_id, type="CONTAINS")

                # Extract methods of this class
                if "methods" in cls and cls["methods"]:
                    for method in cls["methods"]:
                        method_id = self._extract_function_node(graph, method, class_id, module_id)
                        # Add CONTAINS edge: Class → Method
                        graph.add_edge(class_id, method_id, type="CONTAINS")

        # Extract module-level functions
        if "functions" in result and result["functions"]:
            for func in result["functions"]:
                func_id = self._extract_function_node(graph, func, None, module_id)
                # Add CONTAINS edge: Module → Function
                graph.add_edge(module_id, func_id, type="CONTAINS")

        # Build CALLS edges (Milestone 2)
        self._build_calls_edges(graph, result)

        return graph

    def build_from_directory(
        self,
        directory: str,
        pattern: str = "**/*.py",
        exclude_patterns: list[str] | None = None,
        max_files: int | None = None,
        cross_file: bool = False,
    ) -> nx.DiGraph:
        """
        Build a unified code graph from multiple Python files in a directory.

        Args:
            directory: Root directory to search for Python files
            pattern: Glob pattern for file matching (default: **/*.py)
            exclude_patterns: List of glob patterns to exclude (e.g., ['**/test_*.py', '**/__pycache__/**'])
            max_files: Maximum number of files to process (for testing/debugging)
            cross_file: Enable cross-file call resolution (default: False).
                       When True, resolves function calls across file boundaries using
                       import information. When False, only intra-file calls are tracked.

        Returns:
            NetworkX directed graph combining all analyzed files.
            If cross_file=True, includes cross-file CALLS edges marked with cross_file=True attribute.

        Example:
            >>> builder = CodeGraphBuilder()
            >>> # Basic usage (intra-file only)
            >>> graph = builder.build_from_directory(
            ...     "src",
            ...     pattern="**/*.py",
            ...     exclude_patterns=["**/tests/**", "**/__pycache__/**"]
            ... )
            >>> # With cross-file resolution
            >>> graph = builder.build_from_directory(
            ...     "src",
            ...     cross_file=True
            ... )
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        directory_path = Path(directory)
        if not directory_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        if not directory_path.is_dir():
            raise ValueError(f"Not a directory: {directory}")

        # Find all matching files
        all_files = list(directory_path.glob(pattern))

        # Apply exclusion patterns
        if exclude_patterns:
            for exclude_pattern in exclude_patterns:
                exclude_files = set(directory_path.glob(exclude_pattern))
                all_files = [f for f in all_files if f not in exclude_files]

        # Apply max_files limit if specified
        if max_files is not None and max_files > 0:
            all_files = all_files[:max_files]

        if not all_files:
            # Return empty graph with metadata
            graph = nx.DiGraph()
            graph.graph["files_analyzed"] = 0
            graph.graph["directory"] = str(directory_path)
            return graph

        # Build unified graph using parallel processing
        unified_graph = nx.DiGraph()

        # Process files in parallel
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Submit all file processing tasks
            future_to_file = {
                executor.submit(self._safe_build_from_file, str(file_path)): file_path
                for file_path in all_files
            }

            # Collect results as they complete
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    file_graph = future.result()
                    if file_graph is not None:
                        # Merge file graph into unified graph
                        unified_graph = nx.compose(unified_graph, file_graph)
                except Exception as e:
                    # Log error but continue processing other files
                    print(f"Error processing {file_path}: {e}")

        # Add graph metadata
        unified_graph.graph["files_analyzed"] = len(all_files)
        unified_graph.graph["directory"] = str(directory_path)
        unified_graph.graph["pattern"] = pattern
        if exclude_patterns:
            unified_graph.graph["exclude_patterns"] = exclude_patterns

        # Cross-file call resolution (if enabled)
        if cross_file:
            unified_graph = self._build_with_cross_file(unified_graph, all_files, directory_path)

        return unified_graph

    def _safe_build_from_file(self, file_path: str) -> nx.DiGraph | None:
        """
        Safely build graph from file, catching exceptions.

        Args:
            file_path: Path to file

        Returns:
            Graph or None if error occurred
        """
        try:
            return self.build_from_file(file_path)
        except Exception:
            # Return None on error (will be filtered out)
            return None

    def _extract_module_node(self, graph: nx.DiGraph, path: Path, result: dict[str, Any]) -> str:
        """
        Extract module node and add to graph.

        Args:
            graph: NetworkX graph to add node to
            path: File path
            result: Parser result

        Returns:
            Module node ID
        """
        module_id = f"module:{path.stem}"

        # Extract imports (handle both Python dicts and Java strings)
        imports: list[str] = []
        if "imports" in result and result["imports"]:
            for imp in result["imports"]:
                # Java imports are simple strings
                if isinstance(imp, str):
                    imports.append(imp)
                # Python imports are dictionaries
                elif isinstance(imp, dict):
                    if imp.get("type") == "import" and "module" in imp:
                        # Simple import: import pathlib
                        imports.append(imp["module"])
                    elif imp.get("type") == "from_import" and "names" in imp:
                        # From import: from typing import Dict
                        module = imp.get("module", "")
                        for name in imp["names"]:
                            # names is a list of strings
                            if module:
                                imports.append(f"{module}.{name}")
                            else:
                                imports.append(name)

        node_data = {
            "type": "MODULE",
            "name": path.stem,
            "file_path": str(path),
            "mtime": path.stat().st_mtime if path.exists() else 0.0,
            "imports": imports,
        }

        graph.add_node(module_id, **node_data)
        return module_id

    def _extract_class_node(
        self,
        graph: nx.DiGraph,
        cls: dict[str, Any],
        module_id: str,
        result: dict[str, Any],
    ) -> str:
        """
        Extract class node and add to graph.

        Args:
            graph: NetworkX graph to add node to
            cls: Class data from parser
            module_id: Parent module ID
            result: Full parser result

        Returns:
            Class node ID
        """
        class_name = cls.get("name", "UnknownClass")
        class_id = f"{module_id}:class:{class_name}"

        # Extract method names
        method_names = []
        if "methods" in cls and cls["methods"]:
            method_names = [m.get("name", "") for m in cls["methods"]]

        node_data = {
            "type": "CLASS",
            "name": class_name,
            "module_id": module_id,
            "start_line": cls.get("line_start", cls.get("start_line", 0)),
            "end_line": cls.get("line_end", cls.get("end_line", 0)),
            "methods": method_names,
        }

        graph.add_node(class_id, **node_data)
        return class_id

    def _extract_function_node(
        self,
        graph: nx.DiGraph,
        func: dict[str, Any],
        class_id: str | None,
        module_id: str,
    ) -> str:
        """
        Extract function/method node and add to graph.

        Args:
            graph: NetworkX graph to add node to
            func: Function data from parser
            class_id: Parent class ID (None for module-level functions)
            module_id: Parent module ID

        Returns:
            Function node ID
        """
        func_name = func.get("name", "unknown_function")

        if class_id:
            func_id = f"{class_id}:method:{func_name}"
        else:
            func_id = f"{module_id}:function:{func_name}"

        # Extract parameters
        params = func.get("parameters", [])
        if isinstance(params, list):
            param_names = [p.get("name", "") if isinstance(p, dict) else str(p) for p in params]
        else:
            param_names = []

        node_data = {
            "type": "FUNCTION",
            "name": func_name,
            "class_id": class_id,
            "module_id": module_id,
            "start_line": func.get("line_start", func.get("start_line", 0)),
            "end_line": func.get("line_end", func.get("end_line", 0)),
            "params": param_names,
            "return_type": func.get("return_type", "None"),
            "is_async": func.get("is_async", False),
        }

        graph.add_node(func_id, **node_data)
        return func_id

    def save_graph(self, graph: nx.DiGraph, output_path: str) -> None:
        """
        Save graph to a pickle file.

        Args:
            graph: NetworkX graph to save
            output_path: Path to save .gpickle file
        """
        with open(output_path, "wb") as f:
            pickle.dump(graph, f, protocol=pickle.HIGHEST_PROTOCOL)

    def load_graph(self, input_path: str) -> nx.DiGraph:
        """
        Load graph from a pickle file.

        Args:
            input_path: Path to .gpickle file

        Returns:
            NetworkX directed graph
        """
        with open(input_path, "rb") as f:
            graph = pickle.load(f)
        return graph

    def _build_calls_edges(self, graph: nx.DiGraph, result: dict[str, Any]) -> None:
        """
        Build CALLS edges by extracting function calls from AST using language-specific extractor.

        Args:
            graph: NetworkX graph to add edges to
            result: Parser result with AST
        """
        if "ast" not in result or not result["ast"]:
            return

        # Extract all function calls from AST using language-specific extractor
        function_calls = self.call_extractor.extract_calls(result["ast"])

        # Build mapping of function names to node IDs for quick lookup
        func_name_to_id: dict[str, list[str]] = {}
        for node_id, node_data in graph.nodes(data=True):
            if node_data["type"] == "FUNCTION":
                name = node_data.get("name", "")
                if name not in func_name_to_id:
                    func_name_to_id[name] = []
                func_name_to_id[name].append(node_id)

        # For each function call, try to resolve it to a function definition
        for call in function_calls:
            call_name = call.get("name", "")
            caller_context = call.get("context", "")  # Which function contains this call

            # Find the caller function node
            caller_nodes = [
                node_id
                for node_id, data in graph.nodes(data=True)
                if data["type"] == "FUNCTION"
                and data.get("start_line", 0) <= call.get("line", 0) <= data.get("end_line", 0)
            ]

            if not caller_nodes:
                continue

            caller_id = caller_nodes[0]  # Take first matching function

            # Resolve call target
            # Simple resolution: match by function name
            if call_name in func_name_to_id:
                for target_id in func_name_to_id[call_name]:
                    # Avoid self-calls (for now, we'll add them in future iterations)
                    if target_id != caller_id:
                        # Add CALLS edge: caller → callee
                        if not graph.has_edge(caller_id, target_id):
                            graph.add_edge(caller_id, target_id, type="CALLS")

    def _extract_function_calls_from_ast(self, ast_node: Any) -> list[dict[str, Any]]:
        """
        Extract all function call nodes from AST tree.

        Args:
            ast_node: Root AST node

        Returns:
            List of function call dictionaries with name and line number
        """
        calls: list[dict[str, Any]] = []

        def traverse(node: Any) -> None:
            """Recursively traverse AST to find call nodes."""
            if not node or not hasattr(node, "type"):
                return

            # Check if this is a call node
            if node.type == "call":
                # Extract function name from call
                func_name = self._extract_call_name(node)
                if func_name:
                    # Add 1 to convert from 0-indexed to 1-indexed line numbers
                    line_num = node.start_point[0] + 1 if hasattr(node, "start_point") else 0
                    calls.append(
                        {
                            "name": func_name,
                            "line": line_num,
                        }
                    )

            # Traverse children
            if hasattr(node, "children"):
                for child in node.children:
                    traverse(child)

        traverse(ast_node)
        return calls

    def _extract_call_name(self, call_node: Any) -> str | None:
        """
        Extract function name from a call node.

        Handles:
        - Simple calls: func()
        - Method calls: obj.method()
        - Module calls: Module.function()

        Args:
            call_node: AST node of type 'call'

        Returns:
            Function name or None if cannot extract
        """
        if not hasattr(call_node, "children") or len(call_node.children) == 0:
            return None

        # The first child of call is usually the function expression
        func_expr = call_node.children[0]

        # Simple function call: helper()
        if func_expr.type == "identifier":
            return self._get_node_text(func_expr)

        # Attribute access: obj.method() or Module.function()
        if func_expr.type == "attribute":
            # Get the attribute name (method/function name)
            if hasattr(func_expr, "children"):
                for child in func_expr.children:
                    if child.type == "identifier" and child != func_expr.children[0]:
                        return self._get_node_text(child)

        return None

    def _get_node_text(self, node: Any) -> str:
        """
        Get text content of an AST node.

        Args:
            node: AST node

        Returns:
            Text content or empty string
        """
        if hasattr(node, "text"):
            text = node.text
            if isinstance(text, bytes):
                return text.decode("utf-8")
            return str(text)
        return ""

    def _build_with_cross_file(
        self, unified_graph: nx.DiGraph, all_files: list[Path], project_root: Path
    ) -> nx.DiGraph:
        """
        Add cross-file call resolution to the unified graph.

        This method:
        1. Parses imports from all files using ImportResolver
        2. Builds project-wide symbol table using SymbolTableBuilder
        3. Resolves cross-file calls using CrossFileCallResolver
        4. Returns unified graph with cross-file CALLS edges

        Args:
            unified_graph: Combined graph from all files (intra-file only)
            all_files: List of all analyzed Python files
            project_root: Root directory of the project

        Returns:
            Enhanced graph with cross-file CALLS edges marked with cross_file=True

        Example:
            >>> graph = builder._build_with_cross_file(graph, files, Path("src"))
        """
        from tree_sitter_analyzer_v2.graph.cross_file import CrossFileCallResolver
        from tree_sitter_analyzer_v2.graph.imports import ImportResolver
        from tree_sitter_analyzer_v2.graph.symbols import SymbolTableBuilder

        # Create mapping from module name to file path
        module_to_file = {}
        for file_path in all_files:
            module_name = file_path.stem  # "main.py" -> "main"
            module_to_file[module_name] = str(file_path)

        # Step 1: Extract ALL function calls from each file (including unresolved)
        # This is needed because basic builder only adds CALLS edges for same-file calls
        for file_path in all_files:
            module_name = file_path.stem
            source_code = file_path.read_text(encoding="utf-8")
            result = self.parser.parse(source_code, str(file_path))

            if "ast" in result and result["ast"]:
                all_calls = self._extract_function_calls_from_ast(result["ast"])

                # Add these calls as metadata to function nodes in unified_graph
                for call in all_calls:
                    call_name = call.get("name", "")
                    call_line = call.get("line", 0)

                    # Find which function contains this call
                    for node_id in unified_graph.nodes():
                        node_data = unified_graph.nodes[node_id]
                        if (
                            node_data.get("type") == "FUNCTION"
                            and module_name in node_id
                            and node_data.get("start_line", 0)
                            <= call_line
                            <= node_data.get("end_line", 0)
                        ):
                            # Store unresolved calls in node data
                            if "unresolved_calls" not in node_data:
                                node_data["unresolved_calls"] = []
                            node_data["unresolved_calls"].append(call_name)
                            break

        # Step 2: Build import graph using actual file paths
        import_resolver = ImportResolver(project_root)
        import_graph = import_resolver.build_import_graph(all_files)

        # Step 3: Build symbol table from unified graph
        # Group nodes by file to create file_graphs dict
        # Use file paths as keys (to match import graph)
        file_graphs: dict[str, nx.DiGraph] = {}
        file_to_module: dict[str, str] = {}  # Reverse mapping

        for node_id in unified_graph.nodes():
            # Extract file/module name from node ID
            # Node format: "module:main:function:helper" -> module is "main"
            parts = node_id.split(":")
            if len(parts) >= 2:
                module_name = parts[1]  # "main" or "utils"
                file_path = module_to_file.get(module_name)

                if file_path:
                    file_to_module[file_path] = module_name

                    if file_path not in file_graphs:
                        file_graphs[file_path] = nx.DiGraph()

                    # Add node and its attributes to file graph (including unresolved_calls)
                    file_graphs[file_path].add_node(node_id, **unified_graph.nodes[node_id])

                    # Add edges
                    for successor in unified_graph.successors(node_id):
                        file_graphs[file_path].add_edge(
                            node_id, successor, **unified_graph[node_id][successor]
                        )

        # Step 4: Build symbol table
        symbol_builder = SymbolTableBuilder()
        symbol_table = symbol_builder.build(file_graphs)

        # Step 5: Resolve cross-file calls
        cross_file_resolver = CrossFileCallResolver(import_graph, symbol_table)
        enhanced_graph = cross_file_resolver.resolve(file_graphs)

        # Log unresolved calls (if any)
        unresolved = cross_file_resolver.get_unresolved_calls()
        if unresolved:
            print(f"Warning: {len(unresolved)} unresolved calls detected:")
            for warning in unresolved[:10]:  # Show first 10
                print(f"  {warning}")

        return enhanced_graph
