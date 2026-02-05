"""
Java language parser for extracting structured information.

This module provides high-level parsing for Java code, extracting:
- Classes (with modifiers, methods, annotations)
- Interfaces (with method signatures)
- Methods (with modifiers, parameters, return types)
- Packages and imports
- Annotations (Spring, JPA, Lombok framework detection)
- Metadata (line numbers, counts)
"""

from typing import Any

from tree_sitter_analyzer_v2.core.parser import TreeSitterParser
from tree_sitter_analyzer_v2.core.types import ASTNode

# Framework-specific annotation sets
SPRING_ANNOTATIONS = {
    "RestController",
    "Controller",
    "Service",
    "Repository",
    "Component",
    "Configuration",
    "Bean",
    "Autowired",
    "RequestMapping",
    "GetMapping",
    "PostMapping",
    "PutMapping",
    "DeleteMapping",
    "PatchMapping",
}

JPA_ANNOTATIONS = {
    "Entity",
    "Table",
    "Id",
    "GeneratedValue",
    "Column",
    "OneToMany",
    "ManyToOne",
    "ManyToMany",
    "OneToOne",
}

LOMBOK_ANNOTATIONS = {
    "Data",
    "Getter",
    "Setter",
    "Builder",
    "Value",
    "NoArgsConstructor",
    "AllArgsConstructor",
    "RequiredArgsConstructor",
}

# Spring web-specific annotations (subset of SPRING_ANNOTATIONS)
SPRING_WEB_ANNOTATIONS = {
    "RestController",
    "Controller",
    "RequestMapping",
    "GetMapping",
    "PostMapping",
    "PutMapping",
    "DeleteMapping",
    "PatchMapping",
}


class JavaParser:
    """
    High-level parser for Java code.

    Extracts structured information from Java source code using tree-sitter.
    """

    def __init__(self) -> None:
        """Initialize Java parser."""
        self._parser = TreeSitterParser("java")

    def parse(self, source_code: str, file_path: str | None = None) -> dict[str, Any]:
        """
        Parse Java source code and extract structured information.

        Args:
            source_code: Java source code to parse
            file_path: Optional file path for metadata

        Returns:
            Dict containing:
            - ast: Raw AST from tree-sitter
            - package: Package declaration (if any)
            - imports: List of import statements
            - classes: List of class definitions
            - interfaces: List of interface definitions
            - metadata: File metadata
            - errors: Whether parsing had errors
        """
        # Parse with tree-sitter
        parse_result = self._parser.parse(source_code, file_path)

        # Initialize result structure
        result: dict[str, Any] = {
            "ast": parse_result.tree,
            "package": None,
            "imports": [],
            "classes": [],
            "interfaces": [],
            "metadata": {
                "total_classes": 0,
                "total_interfaces": 0,
                "total_imports": 0,
            },
            "errors": parse_result.has_errors,
        }

        # Extract structured information if parsing succeeded
        if parse_result.tree:
            self._extract_all(parse_result.tree, result)

            # Update metadata counts
            result["metadata"]["total_classes"] = len(result["classes"])
            result["metadata"]["total_interfaces"] = len(result["interfaces"])
            result["metadata"]["total_imports"] = len(result["imports"])

        return result

    def _extract_all(self, root: ASTNode, result: dict[str, Any]) -> None:
        """Extract all Java constructs from AST."""
        self._traverse(root, result, parent_class=None)

    def _traverse(
        self, node: ASTNode, result: dict[str, Any], parent_class: str | None = None
    ) -> None:
        """
        Recursively traverse AST to extract all constructs.

        Args:
            node: Current AST node
            result: Result dictionary to populate
            parent_class: Name of enclosing class (for nested classes)
        """
        # Check node type and extract accordingly
        if node.type == "package_declaration":
            package_name = self._extract_package(node)
            if package_name:
                result["package"] = package_name

        elif node.type == "import_declaration":
            import_info = self._extract_import(node)
            if import_info:
                result["imports"].append(import_info)

        elif node.type == "class_declaration":
            class_info = self._extract_class(node, parent_class)
            if class_info:
                result["classes"].append(class_info)
                # Traverse children with this class as parent
                for child in node.children:
                    if child.type == "class_body":
                        self._traverse(child, result, parent_class=class_info["name"])
                return  # Don't traverse children again

        elif node.type == "record_declaration":
            # Java 14+ record support
            record_info = self._extract_record(node)
            if record_info:
                result["classes"].append(record_info)

        elif node.type == "interface_declaration":
            interface_info = self._extract_interface(node)
            if interface_info:
                result["interfaces"].append(interface_info)

        # Recursively traverse children
        for child in node.children:
            self._traverse(child, result, parent_class)

    def _extract_package(self, node: ASTNode) -> str | None:
        """Extract package declaration."""
        for child in node.children:
            if child.type == "scoped_identifier" or child.type == "identifier":
                return child.text
        return None

    def _extract_import(self, node: ASTNode) -> str | None:
        """Extract import statement."""
        import_path = None
        has_asterisk = False

        for child in node.children:
            if child.type in ["scoped_identifier", "identifier"]:
                import_path = child.text
            elif child.type == "asterisk":
                has_asterisk = True

        if import_path:
            return f"{import_path}.*" if has_asterisk else import_path

        return None

    def _extract_class(
        self, node: ASTNode, parent_class: str | None = None
    ) -> dict[str, Any] | None:
        """
        Extract class declaration with framework and nesting detection.

        Args:
            node: Class declaration node
            parent_class: Name of enclosing class (if nested)
        """
        class_info: dict[str, Any] = {
            "name": "",
            "modifiers": [],
            "annotations": [],
            "methods": [],
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
            "metadata": {},  # Add metadata field for all classes
        }

        # Extract modifiers and annotations from parent modifiers node
        for child in node.children:
            if child.type == "modifiers":
                class_info["modifiers"] = self._extract_modifiers(child)
                class_info["annotations"] = self._extract_annotations(child)
            elif child.type == "identifier":
                class_info["name"] = child.text or ""
            elif child.type == "class_body":
                # Extract methods
                class_info["methods"] = self._extract_class_methods(child)

        # Detect framework type from annotations
        if class_info["annotations"]:
            framework_type = self._detect_framework_type(class_info["annotations"])
            if framework_type:
                class_info["framework_type"] = framework_type

        # Detect nested class using parent_class parameter
        if parent_class:
            class_info["metadata"]["is_nested"] = True
            class_info["metadata"]["parent_class"] = parent_class
        else:
            class_info["metadata"]["is_nested"] = False

        return class_info if class_info["name"] else None

    def _extract_interface(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract interface declaration."""
        interface_info: dict[str, Any] = {
            "name": "",
            "modifiers": [],
            "annotations": [],
            "methods": [],
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
        }

        for child in node.children:
            if child.type == "modifiers":
                interface_info["modifiers"] = self._extract_modifiers(child)
                interface_info["annotations"] = self._extract_annotations(child)
            elif child.type == "identifier":
                interface_info["name"] = child.text or ""
            elif child.type == "interface_body":
                # Extract method signatures
                interface_info["methods"] = self._extract_interface_methods(child)

        return interface_info if interface_info["name"] else None

    def _extract_record(self, node: ASTNode) -> dict[str, Any] | None:
        """
        Extract record declaration (Java 14+).

        Example:
            public record Point(int x, int y) {}
            ->
            {
                "name": "Point",
                "modifiers": ["public"],
                "metadata": {
                    "is_record": True,
                    "record_components": [
                        {"name": "x", "type": "int"},
                        {"name": "y", "type": "int"}
                    ]
                },
                "methods": []
            }
        """
        record_info: dict[str, Any] = {
            "name": "",
            "modifiers": [],
            "annotations": [],
            "methods": [],
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
            "metadata": {"is_record": True, "record_components": []},
        }

        for child in node.children:
            if child.type == "modifiers":
                record_info["modifiers"] = self._extract_modifiers(child)
                record_info["annotations"] = self._extract_annotations(child)
            elif child.type == "identifier":
                record_info["name"] = child.text or ""
            elif child.type == "formal_parameters":
                # Record components are declared like parameters
                record_info["metadata"]["record_components"] = self._extract_record_components(
                    child
                )
            elif child.type == "class_body":
                # Records can have methods
                record_info["methods"] = self._extract_class_methods(child)

        return record_info if record_info["name"] else None

    def _extract_record_components(self, params_node: ASTNode) -> list[dict[str, str]]:
        """
        Extract record components (immutable fields).

        Examples:
            record Point(int x, int y) -> [{"name": "x", "type": "int"}, {"name": "y", "type": "int"}]
            record User(String name, int age) -> [{"name": "name", "type": "String"}, ...]
        """
        components: list[dict[str, str]] = []

        for child in params_node.children:
            if child.type == "formal_parameter":
                component = self._extract_record_component(child)
                if component:
                    components.append(component)

        return components

    def _extract_record_component(self, node: ASTNode) -> dict[str, str] | None:
        """Extract single record component (similar to formal parameter)."""
        component_info: dict[str, str] = {"name": "", "type": ""}

        for child in node.children:
            if child.type in [
                "integral_type",
                "floating_point_type",
                "boolean_type",
                "type_identifier",
                "generic_type",
                "array_type",
                "scoped_type_identifier",
            ]:
                # Use enhanced type extraction (supports generics and arrays)
                component_type = self._extract_type(child)
                if component_type:
                    component_info["type"] = component_type

            elif child.type == "identifier":
                component_info["name"] = child.text or ""

        return component_info if component_info["name"] and component_info["type"] else None

    def _extract_modifiers(self, modifiers_node: ASTNode) -> list[str]:
        """Extract modifiers (public, private, static, etc.)."""
        modifiers: list[str] = []

        for child in modifiers_node.children:
            if child.type in [
                "public",
                "private",
                "protected",
                "static",
                "final",
                "abstract",
                "synchronized",
                "volatile",
            ]:
                modifiers.append(child.type)

        return modifiers

    def _extract_annotations(self, modifiers_node: ASTNode) -> list[dict[str, Any]]:
        """
        Extract annotations with framework detection.

        Returns:
            List of dicts with:
            - name: Annotation name (without @)
            - type: Framework type (spring, spring-web, jpa, lombok, custom)
            - arguments: Dict of annotation arguments (if any)
        """
        annotations: list[dict[str, Any]] = []

        for child in modifiers_node.children:
            if child.type == "marker_annotation":
                # Simple annotation without arguments (e.g., @Override, @Entity)
                name = self._get_annotation_name(child)
                if name:
                    annotations.append(
                        {
                            "name": name,
                            "type": self._detect_annotation_type(name),
                        }
                    )

            elif child.type == "annotation":
                # Annotation with arguments (e.g., @RequestMapping("/api"))
                name, args = self._parse_annotation_with_args(child)
                if name:
                    ann_info: dict[str, Any] = {
                        "name": name,
                        "type": self._detect_annotation_type(name),
                    }
                    if args:
                        ann_info["arguments"] = args
                    annotations.append(ann_info)

        return annotations

    def _get_annotation_name(self, annotation_node: ASTNode) -> str | None:
        """Extract annotation name from marker_annotation node."""
        for child in annotation_node.children:
            if child.type == "identifier" or child.type == "scoped_identifier":
                # Handle both @Override and @javax.annotation.Override
                text = child.text or ""
                # Get simple name (last part after dot)
                return text.split(".")[-1] if text else None
        return None

    def _parse_annotation_with_args(
        self, annotation_node: ASTNode
    ) -> tuple[str | None, dict[str, Any]]:
        """
        Parse annotation with arguments.

        Returns:
            Tuple of (annotation_name, arguments_dict)
        """
        name = None
        args: dict[str, Any] = {}

        for child in annotation_node.children:
            if child.type == "identifier" or child.type == "scoped_identifier":
                text = child.text or ""
                name = text.split(".")[-1] if text else None

            elif child.type == "annotation_argument_list":
                # Extract arguments from argument list
                args = self._extract_annotation_arguments(child)

        return name, args

    def _extract_annotation_arguments(self, args_node: ASTNode) -> dict[str, Any]:
        """
        Extract annotation arguments.

        Simplified extraction - stores raw text values.
        For complex scenarios, could be enhanced to parse expressions.
        """
        arguments: dict[str, Any] = {}

        for child in args_node.children:
            if child.type == "element_value_pair":
                # Named argument: key = value
                key = None
                value = None

                for grandchild in child.children:
                    if grandchild.type == "identifier":
                        key = grandchild.text
                    elif grandchild.type in [
                        "string_literal",
                        "integer_literal",
                        "boolean_literal",
                    ]:
                        value = grandchild.text

                if key and value:
                    arguments[key] = value

            elif child.type in ["string_literal", "integer_literal", "boolean_literal"]:
                # Single unnamed argument (default to "value" key)
                arguments["value"] = child.text

        return arguments

    def _detect_annotation_type(self, name: str) -> str:
        """
        Detect framework type from annotation name.

        Returns:
            Framework type: spring-web, spring, jpa, lombok, custom
        """
        if name in SPRING_WEB_ANNOTATIONS:
            return "spring-web"
        elif name in SPRING_ANNOTATIONS:
            return "spring"
        elif name in JPA_ANNOTATIONS:
            return "jpa"
        elif name in LOMBOK_ANNOTATIONS:
            return "lombok"
        else:
            return "custom"

    def _detect_framework_type(self, annotations: list[dict[str, Any]]) -> str | None:
        """
        Detect primary framework from annotations.

        Priority: spring-web > spring > jpa > lombok

        Args:
            annotations: List of annotation dicts with "type" field

        Returns:
            Primary framework type or None
        """
        types = {ann["type"] for ann in annotations}

        if "spring-web" in types:
            return "spring-web"
        elif "spring" in types:
            return "spring"
        elif "jpa" in types:
            return "jpa"
        elif "lombok" in types:
            return "lombok"

        return None

    def _extract_type(self, type_node: ASTNode) -> str | None:
        """
        Extract type information including generics and arrays.

        Handles:
        - Simple types: int, String, boolean
        - Generic types: List<String>, Map<K,V>
        - Array types: int[], String[][]
        - Combinations: List<String>[]
        """
        if not type_node:
            return None

        node_type = type_node.type

        # Simple types
        if node_type in [
            "void_type",
            "integral_type",
            "floating_point_type",
            "boolean_type",
            "type_identifier",
        ]:
            return type_node.text

        # Generic types (List<String>, Map<K,V>)
        elif node_type == "generic_type":
            return self._extract_generic_type(type_node)

        # Array types (int[], String[][])
        elif node_type == "array_type":
            return self._extract_array_type(type_node)

        # Scoped types (java.util.List)
        elif node_type == "scoped_type_identifier":
            return type_node.text

        return None

    def _extract_generic_type(self, type_node: ASTNode) -> str:
        """
        Extract generic type information.

        Examples:
            List<String> -> "List<String>"
            Map<String, Integer> -> "Map<String, Integer>"
            List<Map<K, V>> -> "List<Map<K, V>>"
        """
        base_type = None
        type_args = []

        for child in type_node.children:
            if child.type in ["type_identifier", "scoped_type_identifier"]:
                base_type = child.text

            elif child.type == "type_arguments":
                # Extract type arguments from <...>
                for arg_child in child.children:
                    if arg_child.type in [
                        "type_identifier",
                        "scoped_type_identifier",
                        "generic_type",
                        "wildcard",
                    ]:
                        if arg_child.type == "generic_type":
                            # Nested generic (e.g., Map<K, V> inside List<Map<K,V>>)
                            type_args.append(self._extract_generic_type(arg_child))
                        else:
                            type_args.append(arg_child.text or "")

        if base_type and type_args:
            return f"{base_type}<{', '.join(type_args)}>"

        return base_type or ""

    def _extract_array_type(self, type_node: ASTNode) -> str:
        """
        Extract array type information.

        Examples:
            int[] -> "int[]"
            String[][] -> "String[][]"
            List<String>[] -> "List<String>[]"
        """
        element_type = None
        dimensions = 0

        for child in type_node.children:
            if child.type in [
                "integral_type",
                "floating_point_type",
                "boolean_type",
                "type_identifier",
                "scoped_type_identifier",
                "generic_type",
            ]:
                if child.type == "generic_type":
                    element_type = self._extract_generic_type(child)
                else:
                    element_type = child.text

            elif child.type == "dimensions":
                # Count [] pairs
                dimensions = child.text.count("[")

        if element_type:
            return element_type + "[]" * dimensions

        return ""

    def _extract_throws(self, method_node: ASTNode) -> list[str]:
        """
        Extract throws clause from method declaration.

        Example:
            throws IOException, SQLException -> ["IOException", "SQLException"]
        """
        exceptions = []

        for child in method_node.children:
            if child.type == "throws":
                # Extract exception types from throws clause
                for exception_child in child.children:
                    if exception_child.type in ["type_identifier", "scoped_type_identifier"]:
                        exceptions.append(exception_child.text or "")

        return exceptions

    def _calculate_complexity(self, node: ASTNode) -> int:
        """
        Calculate cyclomatic complexity for a method.

        Formula: 1 + number of decision points

        Decision points:
        - if_statement
        - while_statement
        - for_statement
        - enhanced_for_statement
        - do_statement
        - switch_expression
        - catch_clause
        - ternary_expression
        - binary_expression with && or ||
        """
        decision_nodes = {
            "if_statement",
            "while_statement",
            "for_statement",
            "enhanced_for_statement",
            "do_statement",
            "switch_expression",
            "catch_clause",
            "ternary_expression",
        }

        complexity = 1  # Base complexity

        # Recursively count decision points
        def count_decisions(n: ASTNode) -> int:
            count = 0

            # Check if this node is a decision point
            if n.type in decision_nodes:
                count += 1
            elif n.type == "binary_expression":
                # Check for && or || operators
                for child in n.children:
                    if child.type in ["&&", "||"] or (child.text and child.text in ["&&", "||"]):
                        count += 1
                        break

            # Recursively check children
            for child in n.children:
                count += count_decisions(child)

            return count

        complexity += count_decisions(node)
        return complexity

    def _extract_class_methods(self, class_body_node: ASTNode) -> list[dict[str, Any]]:
        """Extract methods from class body."""
        methods: list[dict[str, Any]] = []

        for child in class_body_node.children:
            if child.type == "method_declaration":
                method_info = self._extract_method_declaration(child)
                if method_info:
                    methods.append(method_info)

        return methods

    def _extract_interface_methods(self, interface_body_node: ASTNode) -> list[dict[str, Any]]:
        """Extract method signatures from interface body."""
        methods: list[dict[str, Any]] = []

        for child in interface_body_node.children:
            if child.type == "method_declaration":
                method_info = self._extract_method_declaration(child)
                if method_info:
                    methods.append(method_info)

        return methods

    def _extract_method_declaration(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract method declaration with generics, arrays, throws, and complexity."""
        method_info: dict[str, Any] = {
            "name": "",
            "modifiers": [],
            "annotations": [],
            "parameters": [],
            "return_type": None,
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
        }

        for child in node.children:
            if child.type == "modifiers":
                method_info["modifiers"] = self._extract_modifiers(child)
                method_info["annotations"] = self._extract_annotations(child)
            elif child.type == "identifier":
                method_info["name"] = child.text or ""
            elif child.type == "formal_parameters":
                method_info["parameters"] = self._extract_parameters(child)
            elif child.type in [
                "void_type",
                "integral_type",
                "floating_point_type",
                "boolean_type",
                "type_identifier",
                "generic_type",
                "array_type",
                "scoped_type_identifier",
            ]:
                # Use enhanced type extraction
                method_info["return_type"] = self._extract_type(child)

        # Extract throws clause
        throws = self._extract_throws(node)
        if throws:
            method_info["throws"] = throws
        else:
            method_info["throws"] = []

        # Calculate cyclomatic complexity
        method_info["complexity"] = self._calculate_complexity(node)

        return method_info if method_info["name"] else None

    def _extract_parameters(self, params_node: ASTNode) -> list[dict[str, str]]:
        """Extract parameter names and types from formal parameters."""
        params: list[dict[str, str]] = []

        for child in params_node.children:
            if child.type == "formal_parameter":
                param_info = self._extract_formal_parameter(child)
                if param_info:
                    params.append(param_info)

        return params

    def _extract_formal_parameter(self, node: ASTNode) -> dict[str, str] | None:
        """Extract single formal parameter with generic and array support."""
        param_info: dict[str, str] = {"name": "", "type": ""}

        for child in node.children:
            if child.type in [
                "integral_type",
                "floating_point_type",
                "boolean_type",
                "type_identifier",
                "generic_type",
                "array_type",
                "scoped_type_identifier",
            ]:
                # Use enhanced type extraction
                param_type = self._extract_type(child)
                if param_type:
                    param_info["type"] = param_type

            elif child.type == "identifier":
                param_info["name"] = child.text or ""

        return param_info if param_info["name"] and param_info["type"] else None
