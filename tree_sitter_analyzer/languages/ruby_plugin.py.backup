#!/usr/bin/env python3
"""
Ruby Language Plugin

Provides Ruby-specific parsing and element extraction functionality.
Supports extraction of classes, modules, methods, constants, variables, and require statements.
"""

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ..models import Class, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_error


class RubyElementExtractor(ElementExtractor):
    """
    Ruby-specific element extractor.

    This extractor parses Ruby AST and extracts code elements, mapping them
    to the unified element model:
    - Classes, Modules → Class elements
    - Methods (instance and class methods) → Function elements
    - Constants, Instance variables, Class variables → Variable elements
    - Require statements → Import elements

    The extractor handles modern Ruby syntax including:
    - Ruby 3+ features
    - Blocks, procs, and lambdas
    - attr_accessor, attr_reader, attr_writer
    - Symbols and string interpolation
    """

    def __init__(self) -> None:
        """
        Initialize the Ruby element extractor.

        Sets up internal state for source code processing and performance
        optimization caches for node text extraction.
        """
        super().__init__()
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self.current_module: str = ""

        # Performance optimization caches - use position-based keys for deterministic caching
        self._node_text_cache: dict[tuple[int, int], str] = {}
        self._processed_nodes: set[tuple[int, int]] = set()
        self._element_cache: dict[tuple[tuple[int, int], str], Any] = {}
        self._file_encoding: str | None = None

    def _reset_caches(self) -> None:
        """Reset all internal caches for a new file analysis."""
        self._node_text_cache.clear()
        self._processed_nodes.clear()
        self._element_cache.clear()
        self.current_module = ""

    def _get_node_text_optimized(self, node: "tree_sitter.Node") -> str:
        """
        Get text content of a node with caching for performance.

        Args:
            node: Tree-sitter node to extract text from

        Returns:
            Text content of the node as string
        """
        # Use node position as cache key instead of object id for deterministic behavior
        cache_key = (node.start_byte, node.end_byte)
        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]

        # Extract text directly from source code string
        text = self.source_code[node.start_byte : node.end_byte]
        self._node_text_cache[cache_key] = text
        return text

    def _determine_visibility(self, node: "tree_sitter.Node") -> str:
        """
        Determine visibility of a method.

        In Ruby, visibility is typically set using private, protected, public keywords.
        Default is public for methods.

        Args:
            node: Method node

        Returns:
            Visibility string ("public", "private", "protected")
        """
        # TODO: Implement visibility detection by looking for visibility modifiers
        # For now, default to public
        return "public"

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """
        Extract Ruby classes and modules.

        Args:
            tree: Parsed tree-sitter tree
            source_code: Source code string

        Returns:
            List of Class elements
        """
        self.source_code = source_code
        self.content_lines = source_code.splitlines()
        self._reset_caches()

        classes: list[Class] = []

        # Iterative traversal to avoid stack overflow
        stack: list[tree_sitter.Node] = [tree.root_node]

        while stack:
            node = stack.pop()

            if node.type in ("class", "module"):
                class_elem = self._extract_class_element(node)
                if class_elem:
                    classes.append(class_elem)

            # Add children to stack for traversal
            for child in reversed(node.children):
                stack.append(child)

        return classes

    def _extract_class_element(self, node: "tree_sitter.Node") -> Class | None:
        """
        Extract a single class or module element.

        Args:
            node: Class/module node

        Returns:
            Class element or None if extraction fails
        """
        try:
            # Extract name
            name_node = None
            for child in node.children:
                if child.type in ("constant", "scope_resolution"):
                    name_node = child
                    break

            if not name_node:
                return None

            name = self._get_node_text_optimized(name_node)
            is_module = node.type == "module"

            # Extract superclass for classes
            base_classes: list[str] = []
            for child in node.children:
                if child.type == "superclass":
                    superclass_node = child.children[0] if child.children else None
                    if superclass_node:
                        base_classes.append(
                            self._get_node_text_optimized(superclass_node)
                        )

            return Class(
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                visibility="public",
                is_abstract=False,
                full_qualified_name=name,
                superclass=base_classes[0] if base_classes else None,
                interfaces=[],
                modifiers=[],
                annotations=[],
                class_type="module" if is_module else "class",
            )
        except Exception as e:
            log_error(f"Error extracting class element: {e}")
            return None

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """
        Extract Ruby methods.

        Args:
            tree: Parsed tree-sitter tree
            source_code: Source code string

        Returns:
            List of Function elements
        """
        self.source_code = source_code
        self.content_lines = source_code.splitlines()

        functions: list[Function] = []

        # Iterative traversal
        stack: list[tuple[tree_sitter.Node, str]] = [(tree.root_node, "")]

        while stack:
            node, parent_class = stack.pop()

            if node.type == "method":
                func_elem = self._extract_method_element(node, parent_class)
                if func_elem:
                    functions.append(func_elem)
            elif node.type == "singleton_method":
                func_elem = self._extract_singleton_method_element(node, parent_class)
                if func_elem:
                    functions.append(func_elem)
            elif node.type == "call":
                # Check for attr_accessor, attr_reader, attr_writer
                func_elems = self._extract_attr_methods(node, parent_class)
                functions.extend(func_elems)

            # Track parent class for methods
            new_parent = parent_class
            if node.type in ("class", "module"):
                for child in node.children:
                    if child.type in ("constant", "scope_resolution"):
                        new_parent = self._get_node_text_optimized(child)
                        break

            # Add children to stack
            for child in reversed(node.children):
                stack.append((child, new_parent))

        return functions

    def _extract_method_element(
        self, node: "tree_sitter.Node", parent_class: str
    ) -> Function | None:
        """
        Extract a method element.

        Args:
            node: Method node
            parent_class: Name of the parent class

        Returns:
            Function element or None if extraction fails
        """
        try:
            # Extract method name
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text_optimized(name_node)
            visibility = self._determine_visibility(node)

            # Extract parameters
            parameters: list[str] = []
            params_node = node.child_by_field_name("parameters")
            if params_node:
                for param in params_node.children:
                    if param.type in (
                        "identifier",
                        "optional_parameter",
                        "splat_parameter",
                        "hash_splat_parameter",
                        "block_parameter",
                    ):
                        param_text = self._get_node_text_optimized(param)
                        parameters.append(param_text)

            return Function(
                name=f"{parent_class}#{name}" if parent_class else name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                visibility=visibility,
                is_static=False,
                is_async=False,
                is_abstract=False,
                parameters=parameters,
                return_type="",
                modifiers=[],
                annotations=[],
            )
        except Exception as e:
            log_error(f"Error extracting method element: {e}")
            return None

    def _extract_singleton_method_element(
        self, node: "tree_sitter.Node", parent_class: str
    ) -> Function | None:
        """
        Extract a singleton (class) method element.

        Args:
            node: Singleton method node
            parent_class: Name of the parent class

        Returns:
            Function element or None if extraction fails
        """
        try:
            # Extract method name
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text_optimized(name_node)
            visibility = self._determine_visibility(node)

            # Extract parameters
            parameters: list[str] = []
            params_node = node.child_by_field_name("parameters")
            if params_node:
                for param in params_node.children:
                    if param.type in (
                        "identifier",
                        "optional_parameter",
                        "splat_parameter",
                        "hash_splat_parameter",
                        "block_parameter",
                    ):
                        param_text = self._get_node_text_optimized(param)
                        parameters.append(param_text)

            return Function(
                name=f"{parent_class}.{name}" if parent_class else name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                visibility=visibility,
                is_static=True,  # Singleton methods are class methods
                is_async=False,
                is_abstract=False,
                parameters=parameters,
                return_type="",
                modifiers=[],
                annotations=[],
            )
        except Exception as e:
            log_error(f"Error extracting singleton method element: {e}")
            return None

    def _extract_attr_methods(
        self, node: "tree_sitter.Node", parent_class: str
    ) -> list[Function]:
        """
        Extract attr_accessor, attr_reader, attr_writer methods.

        Args:
            node: Call node
            parent_class: Name of the parent class

        Returns:
            List of Function elements
        """
        functions: list[Function] = []

        try:
            # Check if this is an attr_* call
            method_node = node.child_by_field_name("method")
            if not method_node:
                return functions

            method_name = self._get_node_text_optimized(method_node)
            if method_name not in ("attr_accessor", "attr_reader", "attr_writer"):
                return functions

            # Extract attribute names
            args_node = node.child_by_field_name("arguments")
            if not args_node:
                return functions

            for arg in args_node.children:
                if arg.type == "simple_symbol":
                    attr_name = self._get_node_text_optimized(arg).lstrip(":")

                    # Determine read/write permissions
                    is_reader = method_name in ("attr_accessor", "attr_reader")
                    is_writer = method_name in ("attr_accessor", "attr_writer")

                    # metadata = {  # Reserved for future use
                    #     "parent_class": parent_class,
                    #     "attr_type": method_name,
                    #     "is_reader": is_reader,
                    #     "is_writer": is_writer,
                    # }
                    _ = (is_reader, is_writer)  # Mark as used

                    functions.append(
                        Function(
                            name=(
                                f"{parent_class}#{attr_name}"
                                if parent_class
                                else attr_name
                            ),
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            visibility="public",
                            is_static=False,
                            is_async=False,
                            is_abstract=False,
                            parameters=[],
                            return_type="",
                            modifiers=[],
                            annotations=[],
                            is_property=True,
                        )
                    )
        except Exception as e:
            log_error(f"Error extracting attr methods: {e}")

        return functions

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """
        Extract Ruby constants and variables.

        Args:
            tree: Parsed tree-sitter tree
            source_code: Source code string

        Returns:
            List of Variable elements
        """
        self.source_code = source_code
        self.content_lines = source_code.splitlines()

        variables: list[Variable] = []

        # Iterative traversal
        stack: list[tuple[tree_sitter.Node, str]] = [(tree.root_node, "")]

        while stack:
            node, parent_class = stack.pop()

            if node.type == "assignment":
                var_elem = self._extract_assignment_variable(node, parent_class)
                if var_elem:
                    variables.append(var_elem)

            # Track parent class
            new_parent = parent_class
            if node.type in ("class", "module"):
                for child in node.children:
                    if child.type in ("constant", "scope_resolution"):
                        new_parent = self._get_node_text_optimized(child)
                        break

            # Add children to stack
            for child in reversed(node.children):
                stack.append((child, new_parent))

        return variables

    def _extract_assignment_variable(
        self, node: "tree_sitter.Node", parent_class: str
    ) -> Variable | None:
        """
        Extract variable from assignment.

        Args:
            node: Assignment node
            parent_class: Name of the parent class

        Returns:
            Variable element or None if extraction fails
        """
        try:
            # Extract left side (variable name)
            left_node = node.child_by_field_name("left")
            if not left_node:
                return None

            var_text = self._get_node_text_optimized(left_node)

            # Determine variable type
            is_constant = left_node.type == "constant"
            # is_instance_var = var_text.startswith("@") and not var_text.startswith("@@")  # Reserved for future use
            is_class_var = var_text.startswith("@@")
            # is_global = var_text.startswith("$")  # Reserved for future use

            # Clean variable name
            name = var_text.lstrip("@$")
            full_name = (
                f"{parent_class}::{name}" if parent_class and is_constant else name
            )

            return Variable(
                name=full_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                visibility="public" if is_constant else "private",
                is_static=is_class_var or is_constant,
                is_constant=is_constant,
                is_final=is_constant,
                variable_type="",
                modifiers=[],
            )
        except Exception as e:
            log_error(f"Error extracting variable: {e}")
            return None

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """
        Extract Ruby require statements.

        Args:
            tree: Parsed tree-sitter tree
            source_code: Source code string

        Returns:
            List of Import elements
        """
        self.source_code = source_code
        self.content_lines = source_code.splitlines()

        imports: list[Import] = []

        # Iterative traversal
        stack: list[tree_sitter.Node] = [tree.root_node]

        while stack:
            node = stack.pop()

            if node.type == "call":
                import_elem = self._extract_require_statement(node)
                if import_elem:
                    imports.append(import_elem)

            # Add children to stack
            for child in reversed(node.children):
                stack.append(child)

        return imports

    def _extract_require_statement(self, node: "tree_sitter.Node") -> Import | None:
        """
        Extract require statement.

        Args:
            node: Call node

        Returns:
            Import element or None if not a require statement
        """
        try:
            # Check if this is a require call
            method_node = node.child_by_field_name("method")
            if not method_node:
                return None

            method_name = self._get_node_text_optimized(method_node)
            if method_name not in ("require", "require_relative", "load"):
                return None

            # Extract required module name
            args_node = node.child_by_field_name("arguments")
            if not args_node or not args_node.children:
                return None

            # Get first argument (the module name)
            first_arg = args_node.children[0]
            if first_arg.type == "string":
                # Extract string content
                import_name = self._get_node_text_optimized(first_arg).strip("\"'")

                return Import(
                    name=import_name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    alias=None,
                    is_wildcard=False,
                )
        except Exception as e:
            log_error(f"Error extracting require statement: {e}")

        return None


class RubyPlugin(LanguagePlugin):
    """
    Ruby language plugin.

    Provides Ruby-specific parsing and element extraction using tree-sitter-ruby.
    Supports modern Ruby features including Ruby 3+ syntax.
    """

    _language_instance: Optional["tree_sitter.Language"] = None

    def get_language_name(self) -> str:
        """
        Get the name of the language.

        Returns:
            Language name string
        """
        return "ruby"

    def get_file_extensions(self) -> list[str]:
        """
        Get supported file extensions.

        Returns:
            List of file extensions
        """
        return [".rb"]

    def get_tree_sitter_language(self) -> "tree_sitter.Language":
        """
        Get the tree-sitter language instance for Ruby.

        Returns:
            tree-sitter Language instance

        Raises:
            ImportError: If tree-sitter-ruby is not installed
        """
        if not TREE_SITTER_AVAILABLE:
            raise ImportError(
                "tree-sitter is not installed. Install it with: pip install tree-sitter"
            )

        if RubyPlugin._language_instance is None:
            try:
                import tree_sitter_ruby

                RubyPlugin._language_instance = tree_sitter.Language(
                    tree_sitter_ruby.language()
                )
            except ImportError as e:
                raise ImportError(
                    "tree-sitter-ruby is not installed. Install it with: pip install tree-sitter-ruby"
                ) from e

        return RubyPlugin._language_instance

    def create_extractor(self) -> ElementExtractor:
        """
        Create a Ruby element extractor.

        Returns:
            RubyElementExtractor instance
        """
        return RubyElementExtractor()

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """
        Analyze a Ruby file.

        Args:
            file_path: Path to the Ruby file
            request: Analysis request configuration

        Returns:
            AnalysisResult containing extracted elements
        """
        from ..models import AnalysisResult

        try:
            # Load file content
            content = await self._load_file_safe(file_path)

            # Parse with tree-sitter
            language = self.get_tree_sitter_language()
            parser = tree_sitter.Parser(language)
            tree = parser.parse(content.encode("utf-8"))

            # Extract elements
            extractor = self.create_extractor()
            classes = extractor.extract_classes(tree, content)
            functions = extractor.extract_functions(tree, content)
            variables = extractor.extract_variables(tree, content)
            imports = extractor.extract_imports(tree, content)

            # Combine all elements
            all_elements = classes + functions + variables + imports

            return AnalysisResult(
                language=self.get_language_name(),
                file_path=file_path,
                success=True,
                elements=all_elements,
                node_count=self._count_nodes(tree.root_node),
            )
        except Exception as e:
            log_error(f"Error analyzing Ruby file {file_path}: {e}")
            return AnalysisResult(
                language=self.get_language_name(),
                file_path=file_path,
                success=False,
                error_message=str(e),
                elements=[],
                node_count=0,
            )

    def _count_nodes(self, node: "tree_sitter.Node") -> int:
        """
        Count total nodes in the AST.

        Args:
            node: Root node to count from

        Returns:
            Total node count
        """
        count = 1
        for child in node.children:
            count += self._count_nodes(child)
        return count

    async def _load_file_safe(self, file_path: str) -> str:
        """
        Load file content with encoding detection.

        Args:
            file_path: Path to the file

        Returns:
            File content as string

        Raises:
            IOError: If file cannot be read
        """
        import chardet

        try:
            # Read file in binary mode
            with open(file_path, "rb") as f:
                raw_content = f.read()

            # Detect encoding
            detected = chardet.detect(raw_content)
            encoding = detected.get("encoding", "utf-8")

            # Decode with detected encoding
            return raw_content.decode(encoding or "utf-8")
        except Exception as e:
            log_error(f"Error loading file {file_path}: {e}")
            raise OSError(f"Failed to load file {file_path}: {e}") from e
