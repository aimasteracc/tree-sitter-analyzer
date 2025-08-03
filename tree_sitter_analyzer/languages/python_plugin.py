#!/usr/bin/env python3
"""
Python Language Plugin

Provides Python-specific parsing and element extraction functionality.
Migrated to the new plugin architecture with enhanced query integration.
"""

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

from ..models import Class, CodeElement, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_error, log_warning


class PythonElementExtractor(ElementExtractor):
    """Python-specific element extractor with comprehensive analysis"""

    def __init__(self) -> None:
        """Initialize the Python element extractor."""
        self.current_module: str = ""
        self.current_file: str = ""
        self.source_code: str = ""
        self.imports: list[str] = []

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract Python function definitions with comprehensive analysis"""
        self.source_code = source_code
        functions: list[Function] = []

        # Function definition queries
        function_queries = [
            # Regular function definitions
            """
            (function_definition
                name: (identifier) @function.name
                parameters: (parameters) @function.params
                body: (block) @function.body) @function.definition
            """,
            # Async function definitions
            """
            (function_definition
                "async"
                name: (identifier) @async_function.name
                parameters: (parameters) @async_function.params
                body: (block) @async_function.body) @async_function.definition
            """,
        ]

        try:
            language = tree.language if hasattr(tree, "language") else None
            if language:
                for query_string in function_queries:
                    query = language.query(query_string)
                    captures = query.captures(tree.root_node)

                    if isinstance(captures, dict):
                        # Process regular functions
                        function_nodes = captures.get("function.definition", [])
                        for node in function_nodes:
                            function = self._extract_detailed_function_info(
                                node, source_code, is_async=False
                            )
                            if function:
                                functions.append(function)

                        # Process async functions
                        async_nodes = captures.get("async_function.definition", [])
                        for node in async_nodes:
                            function = self._extract_detailed_function_info(
                                node, source_code, is_async=True
                            )
                            if function:
                                functions.append(function)

        except Exception as e:
            log_warning(f"Could not extract Python functions: {e}")

        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """Extract Python class definitions with comprehensive analysis"""
        self.source_code = source_code
        classes: list[Class] = []

        # Class definition query
        query_string = """
        (class_definition
            name: (identifier) @class.name
            superclasses: (argument_list)? @class.superclasses
            body: (block) @class.body) @class.definition
        """

        try:
            language = tree.language if hasattr(tree, "language") else None
            if language:
                query = language.query(query_string)
                captures = query.captures(tree.root_node)

                if isinstance(captures, dict):
                    class_nodes = captures.get("class.definition", [])
                    for node in class_nodes:
                        cls = self._extract_detailed_class_info(node, source_code)
                        if cls:
                            classes.append(cls)

        except Exception as e:
            log_warning(f"Could not extract Python classes: {e}")

        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract Python variable definitions (class attributes only)"""
        variables: list[Variable] = []

        # Only extract class-level attributes, not function-level variables
        try:
            # Find class declarations
            class_query = """
            (class_definition
                body: (block) @class.body) @class.definition
            """

            language = tree.language if hasattr(tree, "language") else None
            if language:
                query = language.query(class_query)
                captures = query.captures(tree.root_node)

                if isinstance(captures, dict):
                    class_bodies = captures.get("class.body", [])

                    # For each class body, extract attribute assignments
                    for class_body in class_bodies:
                        variables.extend(
                            self._extract_class_attributes(class_body, source_code)
                        )

        except Exception as e:
            log_warning(f"Could not extract Python class attributes: {e}")

        return variables

    def _extract_class_attributes(
        self, class_body_node: "tree_sitter.Node", source_code: str
    ) -> list[Variable]:
        """Extract class-level attribute assignments"""
        attributes: list[Variable] = []

        try:
            # Look for assignments directly under class body
            for child in class_body_node.children:
                if child.type == "expression_statement":
                    # Check if it's an assignment
                    for grandchild in child.children:
                        if grandchild.type == "assignment":
                            attribute = self._extract_class_attribute_info(
                                grandchild, source_code
                            )
                            if attribute:
                                attributes.append(attribute)
                elif child.type == "assignment":
                    attribute = self._extract_class_attribute_info(child, source_code)
                    if attribute:
                        attributes.append(attribute)

        except Exception as e:
            log_warning(f"Could not extract class attributes: {e}")

        return attributes

    def _extract_class_attribute_info(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Variable | None:
        """Extract class attribute information from assignment node"""
        try:
            # Get the full assignment text
            assignment_text = source_code[node.start_byte : node.end_byte]

            # Extract attribute name and type annotation
            if "=" in assignment_text:
                left_part = assignment_text.split("=")[0].strip()

                # Handle type annotations (e.g., "name: str = ...")
                if ":" in left_part:
                    name_part, type_part = left_part.split(":", 1)
                    attr_name = name_part.strip()
                    attr_type = type_part.strip()
                else:
                    attr_name = left_part
                    attr_type = None

                return Variable(
                    name=attr_name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    raw_text=assignment_text,
                    language="python",
                    variable_type=attr_type,
                )

        except Exception as e:
            log_warning(f"Could not extract class attribute info: {e}")

        return None

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract Python import statements"""
        imports: list[Import] = []

        # Import statement queries
        import_queries = [
            # Regular import statements
            """
            (import_statement
                name: (dotted_name) @import.name) @import.statement
            """,
            # From import statements
            """
            (import_from_statement
                module_name: (dotted_name) @from_import.module
                name: (dotted_name) @from_import.name) @from_import.statement
            """,
            # Aliased imports
            """
            (aliased_import
                name: (dotted_name) @aliased_import.name
                alias: (identifier) @aliased_import.alias) @aliased_import.statement
            """,
        ]

        try:
            language = tree.language if hasattr(tree, "language") else None
            if language:
                for query_string in import_queries:
                    query = language.query(query_string)
                    captures = query.captures(tree.root_node)

                    if isinstance(captures, dict):
                        # Process different types of imports
                        for key, nodes in captures.items():
                            if key.endswith("statement"):
                                import_type = key.split(".")[0]
                                for node in nodes:
                                    imp = self._extract_import_info(
                                        node, source_code, import_type
                                    )
                                    if imp:
                                        imports.append(imp)

        except Exception as e:
            log_warning(f"Could not extract Python imports: {e}")

        return imports

    def _extract_detailed_function_info(
        self, node: "tree_sitter.Node", source_code: str, is_async: bool = False
    ) -> Function | None:
        """Extract comprehensive function information from AST node"""
        try:
            # Extract basic information
            name = self._extract_name_from_node(node, source_code)
            if not name:
                return None

            # Extract parameters
            parameters = self._extract_parameters_from_node(node, source_code)

            # Extract decorators
            decorators = self._extract_decorators_from_node(node, source_code)

            # Extract return type hint
            return_type = self._extract_return_type_from_node(node, source_code)

            # Extract docstring
            # docstring = self._extract_docstring_from_node(node, source_code)  # Not used currently

            # Extract function body
            # body = self._extract_function_body(node, source_code)  # Not used currently

            # Calculate complexity (simplified)
            # complexity_score = self._calculate_complexity(body)  # Not used currently

            # Determine visibility (Python conventions)
            visibility = "public"
            if name.startswith("__") and name.endswith("__"):
                visibility = "magic"  # Magic methods
            elif name.startswith("_"):
                visibility = "private"

            # Safely extract raw text, avoiding index out of bounds
            start_byte = min(node.start_byte, len(source_code))
            end_byte = min(node.end_byte, len(source_code))
            raw_text = (
                source_code[start_byte:end_byte]
                if start_byte < end_byte
                else source_code
            )

            return Function(
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=raw_text,
                language="python",
                parameters=parameters,
                return_type=return_type or "Any",
                modifiers=decorators,
                is_static="staticmethod" in decorators,
                is_private=visibility == "private",
                is_public=visibility == "public",
            )

        except Exception as e:
            log_warning(f"Could not extract detailed function info: {e}")
            return None

    def _extract_detailed_class_info(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Class | None:
        """Extract comprehensive class information from AST node"""
        try:
            # Extract basic information
            name = self._extract_name_from_node(node, source_code)
            if not name:
                return None

            # Extract superclasses
            superclasses = self._extract_superclasses_from_node(node, source_code)

            # Extract decorators
            decorators = self._extract_decorators_from_node(node, source_code)

            # Extract docstring
            # docstring = self._extract_docstring_from_node(node, source_code)  # Not used currently

            # Generate fully qualified name
            full_qualified_name = (
                f"{self.current_module}.{name}" if self.current_module else name
            )

            # Determine visibility
            # visibility = "public"
            # if name.startswith("_"):
            #     visibility = "private"  # Not used currently

            return Class(
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=source_code[node.start_byte : node.end_byte],
                language="python",
                class_type="class",
                full_qualified_name=full_qualified_name,
                package_name=self.current_module,
                superclass=superclasses[0] if superclasses else None,
                interfaces=superclasses[1:] if len(superclasses) > 1 else [],
                modifiers=decorators,
            )

        except Exception as e:
            log_warning(f"Could not extract detailed class info: {e}")
            return None

    def _extract_variable_info(
        self, node: "tree_sitter.Node", source_code: str, assignment_type: str
    ) -> Variable | None:
        """Extract detailed variable information from AST node"""
        try:
            if not self._validate_node(node):
                return None

            # Extract variable text
            variable_text = source_code[node.start_byte : node.end_byte]

            # Extract variable name (simplified)
            if "=" in variable_text:
                name_part = variable_text.split("=")[0].strip()
                if assignment_type == "multiple_assignment" and "," in name_part:
                    name = name_part.split(",")[0].strip()
                else:
                    name = name_part
            else:
                name = "variable"

            return Variable(
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=variable_text,
                language="python",
                variable_type=assignment_type,
            )

        except Exception as e:
            log_warning(f"Could not extract variable info: {e}")
            return None

    def _extract_import_info(
        self, node: "tree_sitter.Node", source_code: str, import_type: str
    ) -> Import | None:
        """Extract detailed import information from AST node"""
        try:
            if not self._validate_node(node):
                return None

            # Safely extract import text, avoiding index out of bounds
            start_byte = min(node.start_byte, len(source_code))
            end_byte = min(node.end_byte, len(source_code))
            import_text = (
                source_code[start_byte:end_byte]
                if start_byte < end_byte
                else source_code
            )

            # Extract import name and module name (simplified)
            if import_type == "from_import":
                if "from" in import_text and "import" in import_text:
                    parts = import_text.split("import")
                    module_name = parts[0].replace("from", "").strip()
                    import_name = parts[1].strip()
                else:
                    module_name = ""
                    import_name = import_text
            elif import_type == "aliased_import":
                module_name = ""
                import_name = import_text
            else:
                module_name = ""
                import_name = import_text.replace("import", "").strip()

            return Import(
                name=import_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=import_text,
                language="python",
                module_name=module_name,
            )

        except Exception as e:
            log_warning(f"Could not extract import info: {e}")
            return None

    # Helper methods
    def _validate_node(self, node: "tree_sitter.Node") -> bool:
        """Validate that a node has required attributes"""
        required_attrs = ["start_byte", "end_byte", "start_point", "end_point"]
        for attr in required_attrs:
            if not hasattr(node, attr) or getattr(node, attr) is None:
                return False
        return True

    def _extract_name_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> str | None:
        """Extract name from AST node"""
        for child in node.children:
            if child.type == "identifier":
                return source_code[child.start_byte : child.end_byte]
        return None

    def _extract_parameters_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> list[str]:
        """Extract parameters from function node"""
        parameters: list[str] = []
        for child in node.children:
            if child.type == "parameters":
                for param_child in child.children:
                    if param_child.type in [
                        "identifier",
                        "typed_parameter",
                        "default_parameter",
                    ]:
                        param_text = source_code[
                            param_child.start_byte : param_child.end_byte
                        ]
                        parameters.append(param_text)
        return parameters

    def _extract_decorators_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> list[str]:
        """Extract decorators from node"""
        decorators: list[str] = []

        # Decorators are before function/class definitions
        if hasattr(node, "parent") and node.parent:
            for sibling in node.parent.children:
                if (
                    sibling.type == "decorator"
                    and sibling.end_point[0] < node.start_point[0]
                ):
                    decorator_text = source_code[sibling.start_byte : sibling.end_byte]
                    # Remove @
                    if decorator_text.startswith("@"):
                        decorator_text = decorator_text[1:].strip()
                    decorators.append(decorator_text)

        return decorators

    def _extract_return_type_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> str | None:
        """Extract return type annotation from function node"""
        for child in node.children:
            if child.type == "type":
                return source_code[child.start_byte : child.end_byte]
        return None

    def _extract_docstring_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> str | None:
        """Extract docstring from function/class node"""
        for child in node.children:
            if child.type == "block":
                # Check if the first statement in the block is a docstring
                for stmt in child.children:
                    if stmt.type == "expression_statement":
                        for expr in stmt.children:
                            if expr.type == "string":
                                if self._validate_node(expr):
                                    docstring = source_code[
                                        expr.start_byte : expr.end_byte
                                    ]
                                    # Remove quotes
                                    if docstring.startswith(
                                        '"""'
                                    ) or docstring.startswith("'''"):
                                        return docstring[3:-3].strip()
                                    elif docstring.startswith(
                                        '"'
                                    ) or docstring.startswith("'"):
                                        return docstring[1:-1].strip()
                                    return docstring
                        break
                break
        return None

    def _extract_function_body(self, node: "tree_sitter.Node", source_code: str) -> str:
        """Extract function body"""
        for child in node.children:
            if child.type == "block":
                return source_code[child.start_byte : child.end_byte]
        return ""

    def _extract_superclasses_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> list[str]:
        """Extract superclasses from class node"""
        superclasses: list[str] = []
        for child in node.children:
            if child.type == "argument_list":
                for arg in child.children:
                    if arg.type == "identifier":
                        superclasses.append(source_code[arg.start_byte : arg.end_byte])
        return superclasses

    def _calculate_complexity(self, body: str) -> int:
        """Calculate cyclomatic complexity (simplified)"""
        complexity = 1  # Base complexity
        keywords = ["if", "elif", "for", "while", "try", "except", "with", "and", "or"]
        for keyword in keywords:
            complexity += body.count(f" {keyword} ") + body.count(f"\n{keyword} ")
        return complexity


class PythonPlugin(LanguagePlugin):
    """Python language plugin for the new architecture"""

    def __init__(self) -> None:
        """Initialize the Python plugin"""
        super().__init__()
        self._language_cache: tree_sitter.Language | None = None
        self._extractor: PythonElementExtractor | None = None

    def get_language_name(self) -> str:
        """Return the name of the programming language this plugin supports"""
        return "python"

    def get_file_extensions(self) -> list[str]:
        """Return list of file extensions this plugin supports"""
        return [".py", ".pyw", ".pyi"]

    def create_extractor(self) -> ElementExtractor:
        """Create and return an element extractor for this language"""
        return PythonElementExtractor()

    def get_extractor(self) -> ElementExtractor:
        """Get the cached extractor instance, creating it if necessary"""
        if self._extractor is None:
            self._extractor = PythonElementExtractor()
        return self._extractor

    def get_tree_sitter_language(self) -> Optional["tree_sitter.Language"]:
        """Get the Tree-sitter language object for Python"""
        if self._language_cache is None:
            try:
                import tree_sitter
                import tree_sitter_python as tspython

                # PyCapsuleオブジェクトをLanguageオブジェクトに変換
                language_capsule = tspython.language()
                self._language_cache = tree_sitter.Language(language_capsule)
            except ImportError:
                log_error("tree-sitter-python not available")
                return None
            except Exception as e:
                log_error(f"Failed to load Python language: {e}")
                return None
        return self._language_cache

    def get_supported_queries(self) -> list[str]:
        """Get list of supported query names for this language"""
        return ["class", "function", "variable", "import"]

    def is_applicable(self, file_path: str) -> bool:
        """Check if this plugin is applicable for the given file"""
        return any(
            file_path.lower().endswith(ext.lower())
            for ext in self.get_file_extensions()
        )

    def get_plugin_info(self) -> dict:
        """Get information about this plugin"""
        return {
            "name": "Python Plugin",
            "language": self.get_language_name(),
            "extensions": self.get_file_extensions(),
            "version": "2.0.0",
            "supported_queries": self.get_supported_queries(),
        }

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """
        Analyze a Python file and return analysis results.

        Args:
            file_path: Path to the Python file to analyze
            request: Analysis request object

        Returns:
            AnalysisResult object containing the analysis results
        """
        try:
            from ..core.parser import Parser
            from ..models import AnalysisResult

            # Read file content
            with open(file_path, encoding="utf-8") as f:
                source_code = f.read()

            # Parse the file
            parser = Parser()
            parse_result = parser.parse_code(source_code, "python")

            if not parse_result.success:
                return AnalysisResult(
                    file_path=file_path,
                    language="python",
                    line_count=len(source_code.splitlines()),
                    elements=[],
                    node_count=0,
                    query_results={},
                    source_code=source_code,
                    success=False,
                    error_message=parse_result.error_message,
                )

            # Extract elements
            extractor = self.create_extractor()
            if parse_result.tree:
                functions = extractor.extract_functions(parse_result.tree, source_code)
                classes = extractor.extract_classes(parse_result.tree, source_code)
                variables = extractor.extract_variables(parse_result.tree, source_code)
                imports = extractor.extract_imports(parse_result.tree, source_code)
            else:
                functions = []
                classes = []
                variables = []
                imports = []

            # Combine all elements
            all_elements: list[CodeElement] = []
            all_elements.extend(functions)
            all_elements.extend(classes)
            all_elements.extend(variables)
            all_elements.extend(imports)

            return AnalysisResult(
                file_path=file_path,
                language="python",
                line_count=len(source_code.splitlines()),
                elements=all_elements,
                node_count=(
                    parse_result.tree.root_node.child_count if parse_result.tree else 0
                ),
                query_results={},
                source_code=source_code,
                success=True,
                error_message=None,
            )

        except Exception as e:
            log_error(f"Failed to analyze Python file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language="python",
                line_count=0,
                elements=[],
                node_count=0,
                query_results={},
                source_code="",
                success=False,
                error_message=str(e),
            )

    def execute_query(self, tree: "tree_sitter.Tree", query_name: str) -> dict:
        """Execute a specific query on the tree"""
        try:
            language = self.get_tree_sitter_language()
            if not language:
                return {"error": "Language not available"}

            # Simple query execution for testing
            if query_name == "function":
                query_string = "(function_definition) @function"
            elif query_name == "class":
                query_string = "(class_definition) @class"
            else:
                return {"error": f"Unknown query: {query_name}"}

            query = language.query(query_string)
            captures = query.captures(tree.root_node)
            return {"captures": captures, "query": query_string}

        except Exception as e:
            log_error(f"Query execution failed: {e}")
            return {"error": str(e)}
