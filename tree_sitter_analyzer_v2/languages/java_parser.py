"""
Java language parser - extracts classes, interfaces, methods, imports from Java source.

Uses tree-sitter for AST parsing and walks the tree to extract
structured information about Java code elements.
"""

from __future__ import annotations

from typing import Any

from tree_sitter_analyzer_v2.core.parser import TreeSitterParser


class JavaParser:
    """
    Java-specific parser that extracts structured code elements.

    Returns a dict with keys: ast, metadata, classes, interfaces, imports, package, errors.
    """

    def __init__(self) -> None:
        self._parser = TreeSitterParser("java")

    def parse(self, code: str, filename: str | None = None) -> dict[str, Any]:
        """Parse Java code and extract structured elements."""
        result = self._parser.parse(code, filename)
        source_bytes = code.encode("utf-8")

        classes: list[dict[str, Any]] = []
        interfaces: list[dict[str, Any]] = []
        imports: list[str] = []
        package: str | None = None

        self._parser._ensure_initialized()
        ts_tree = self._parser._ts_parser.parse(source_bytes)
        root = ts_tree.root_node

        for child in root.children:
            if child.type == "package_declaration":
                package = self._extract_package(child, source_bytes)
            elif child.type == "import_declaration":
                imports.append(self._extract_import(child, source_bytes))
            elif child.type == "class_declaration":
                classes.append(self._extract_class(child, source_bytes))
            elif child.type == "interface_declaration":
                interfaces.append(self._extract_interface(child, source_bytes))
            elif child.type == "record_declaration":
                classes.append(self._extract_record(child, source_bytes))

        metadata = {
            "total_classes": len(classes),
            "total_interfaces": len(interfaces),
            "total_imports": len(imports),
        }

        # Flatten nested classes into top-level list
        all_classes = []
        for cls in classes:
            all_classes.append(cls)
            self._flatten_nested_classes(cls, all_classes)

        metadata["total_classes"] = len(all_classes)

        parse_result: dict[str, Any] = {
            "ast": result.tree,
            "metadata": metadata,
            "classes": all_classes,
            "interfaces": interfaces,
            "imports": imports,
            "package": package,
            "errors": result.has_errors,
        }

        return parse_result

    def _flatten_nested_classes(self, cls: dict[str, Any], result: list[dict[str, Any]]) -> None:
        """Recursively flatten nested classes into a flat list."""
        for nested in cls.get("nested_classes", []):
            result.append(nested)
            self._flatten_nested_classes(nested, result)

    def _extract_package(self, node: Any, src: bytes) -> str:
        """Extract package name."""
        for child in node.children:
            if child.type == "scoped_identifier" or child.type == "identifier":
                return self._text(child, src)
        return ""

    def _extract_import(self, node: Any, src: bytes) -> str:
        """Extract import path including wildcards."""
        # Build the full import path from children
        parts: list[str] = []
        has_asterisk = False
        for child in node.children:
            if child.type in ("scoped_identifier", "identifier"):
                parts.append(self._text(child, src))
            elif child.type == "asterisk":
                has_asterisk = True
        
        if parts:
            result = parts[0]
            if has_asterisk:
                result += ".*"
            return result
        
        # Fallback - strip "import " and ";"
        text = self._text(node, src).strip()
        if text.startswith("import "):
            text = text[7:]
        if text.endswith(";"):
            text = text[:-1]
        return text.strip()

    def _extract_class(self, node: Any, src: bytes, parent_class: str | None = None) -> dict[str, Any]:
        """Extract class information."""
        name = ""
        modifiers: list[str] = []
        methods: list[dict[str, Any]] = []
        annotations: list[dict[str, Any]] = []
        nested_classes: list[dict[str, Any]] = []

        # Get modifiers from preceding siblings or parent
        modifiers = self._get_modifiers(node, src)

        for child in node.children:
            if child.type == "identifier":
                name = self._text(child, src)
            elif child.type == "class_body":
                for member in child.children:
                    if member.type == "method_declaration":
                        methods.append(self._extract_method(member, src))
                    elif member.type == "constructor_declaration":
                        methods.append(self._extract_constructor(member, src))
                    elif member.type == "class_declaration":
                        nested_cls = self._extract_class(member, src, parent_class=name)
                        nested_classes.append(nested_cls)
                        classes_to_add = nested_cls  # Will be flattened later

        # Check preceding annotations
        annotations = self._get_annotations(node, src)

        cls: dict[str, Any] = {
            "name": name,
            "modifiers": modifiers,
            "methods": methods,
            "annotations": annotations,
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
        }

        if parent_class:
            cls["metadata"] = {"is_nested": True, "parent_class": parent_class}
        else:
            cls["metadata"] = {"is_nested": False}

        # Detect framework type from annotations
        framework = self._detect_framework(annotations)
        if framework:
            cls["framework_type"] = framework

        # Include nested classes
        if nested_classes:
            cls["nested_classes"] = nested_classes

        return cls

    def _extract_interface(self, node: Any, src: bytes) -> dict[str, Any]:
        """Extract interface information."""
        name = ""
        modifiers = self._get_modifiers(node, src)
        methods: list[dict[str, Any]] = []

        for child in node.children:
            if child.type == "identifier":
                name = self._text(child, src)
            elif child.type == "interface_body":
                for member in child.children:
                    if member.type == "method_declaration":
                        methods.append(self._extract_method(member, src))

        return {
            "name": name,
            "modifiers": modifiers,
            "methods": methods,
        }

    def _extract_record(self, node: Any, src: bytes) -> dict[str, Any]:
        """Extract Java record information."""
        name = ""
        modifiers = self._get_modifiers(node, src)
        methods: list[dict[str, Any]] = []
        components: list[dict[str, Any]] = []

        for child in node.children:
            if child.type == "identifier":
                name = self._text(child, src)
            elif child.type == "formal_parameters":
                components = self._extract_record_components(child, src)
            elif child.type == "class_body":
                for member in child.children:
                    if member.type == "method_declaration":
                        methods.append(self._extract_method(member, src))

        return {
            "name": name,
            "modifiers": modifiers,
            "methods": methods,
            "annotations": self._get_annotations(node, src),
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
            "metadata": {
                "is_record": True,
                "record_components": components,
            },
        }

    def _extract_record_components(self, node: Any, src: bytes) -> list[dict[str, Any]]:
        """Extract record component parameters."""
        components: list[dict[str, Any]] = []
        for child in node.children:
            if child.type == "formal_parameter":
                comp = self._extract_parameter(child, src)
                if comp:
                    components.append(comp)
        return components

    def _extract_method(self, node: Any, src: bytes) -> dict[str, Any]:
        """Extract method information."""
        name = ""
        return_type = "void"
        params: list[dict[str, Any]] = []
        modifiers = self._get_modifiers(node, src)
        annotations = self._get_annotations(node, src)
        throws: list[str] = []

        for child in node.children:
            if child.type == "identifier":
                name = self._text(child, src)
            elif child.type in ("type_identifier", "void_type", "integral_type",
                               "floating_point_type", "boolean_type",
                               "generic_type", "array_type", "scoped_type_identifier"):
                return_type = self._text(child, src)
            elif child.type == "formal_parameters":
                params = self._extract_parameters(child, src)
            elif child.type == "throws":
                throws = self._extract_throws(child, src)

        method: dict[str, Any] = {
            "name": name,
            "return_type": return_type,
            "parameters": params,
            "modifiers": modifiers,
            "annotations": annotations,
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
        }

        if throws:
            method["throws"] = throws

        # Calculate complexity
        method["complexity"] = self._calculate_complexity(node, src)

        return method

    def _extract_constructor(self, node: Any, src: bytes) -> dict[str, Any]:
        """Extract constructor information."""
        name = ""
        params: list[dict[str, Any]] = []
        modifiers = self._get_modifiers(node, src)

        for child in node.children:
            if child.type == "identifier":
                name = self._text(child, src)
            elif child.type == "formal_parameters":
                params = self._extract_parameters(child, src)

        return {
            "name": name,
            "return_type": "void",
            "parameters": params,
            "modifiers": modifiers,
            "annotations": self._get_annotations(node, src),
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
            "complexity": 1,
        }

    def _extract_parameters(self, node: Any, src: bytes) -> list[dict[str, Any]]:
        """Extract method parameters."""
        params: list[dict[str, Any]] = []
        for child in node.children:
            if child.type in ("formal_parameter", "spread_parameter"):
                param = self._extract_parameter(child, src)
                if param:
                    params.append(param)
        return params

    def _extract_parameter(self, node: Any, src: bytes) -> dict[str, Any] | None:
        """Extract a single parameter."""
        param_type = ""
        param_name = ""
        for child in node.children:
            if child.type == "identifier":
                param_name = self._text(child, src)
            elif child.type in ("type_identifier", "integral_type", "floating_point_type",
                               "boolean_type", "void_type", "generic_type",
                               "array_type", "scoped_type_identifier"):
                param_type = self._text(child, src)
        if param_name:
            return {"name": param_name, "type": param_type}
        return None

    def _extract_throws(self, node: Any, src: bytes) -> list[str]:
        """Extract throws clause exceptions."""
        exceptions: list[str] = []
        for child in node.children:
            if child.type in ("type_identifier", "scoped_type_identifier"):
                exceptions.append(self._text(child, src))
        return exceptions

    def _get_modifiers(self, node: Any, src: bytes) -> list[str]:
        """Get modifiers for a declaration node."""
        modifiers: list[str] = []
        # Check modifiers child node
        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    if mod.type in ("public", "private", "protected", "static",
                                   "final", "abstract", "synchronized", "native",
                                   "transient", "volatile", "default"):
                        modifiers.append(self._text(mod, src))
                    elif mod.type == "marker_annotation" or mod.type == "annotation":
                        pass  # Handled separately
        return modifiers

    def _get_annotations(self, node: Any, src: bytes) -> list[dict[str, Any]]:
        """Get annotations for a declaration node."""
        annotations: list[dict[str, Any]] = []
        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    if mod.type == "marker_annotation":
                        ann = self._extract_annotation(mod, src)
                        if ann:
                            annotations.append(ann)
                    elif mod.type == "annotation":
                        ann = self._extract_annotation(mod, src)
                        if ann:
                            annotations.append(ann)
        return annotations

    def _extract_annotation(self, node: Any, src: bytes) -> dict[str, Any] | None:
        """Extract annotation information."""
        name = ""
        for child in node.children:
            if child.type == "identifier":
                name = self._text(child, src)
            elif child.type == "scoped_identifier":
                name = self._text(child, src)

        if not name:
            return None

        ann: dict[str, Any] = {"name": name}

        # Detect framework type
        framework = self._annotation_framework(name)
        if framework:
            ann["type"] = framework

        # Extract arguments if present
        for child in node.children:
            if child.type == "annotation_argument_list":
                args_text = self._text(child, src)
                if args_text.startswith("(") and args_text.endswith(")"):
                    args_text = args_text[1:-1].strip()
                ann["arguments"] = args_text

        return ann

    def _annotation_framework(self, name: str) -> str | None:
        """Detect framework from annotation name."""
        spring_web = {"RestController", "Controller", "RequestMapping",
                      "GetMapping", "PostMapping", "PutMapping", "DeleteMapping",
                      "PathVariable", "RequestBody", "RequestParam", "ResponseBody"}
        spring = {"Service", "Component", "Autowired", "Bean", "Configuration",
                  "Repository", "Scope", "Value", "Qualifier", "Primary"}
        jpa = {"Entity", "Table", "Column", "Id", "GeneratedValue",
               "OneToMany", "ManyToOne", "ManyToMany", "JoinColumn"}
        lombok = {"Data", "Getter", "Setter", "NoArgsConstructor",
                  "AllArgsConstructor", "Builder", "ToString", "EqualsAndHashCode"}

        if name in spring_web:
            return "spring-web"
        if name in spring:
            return "spring"
        if name in jpa:
            return "jpa"
        if name in lombok:
            return "lombok"
        return None

    def _detect_framework(self, annotations: list[dict[str, Any]]) -> str | None:
        """Detect framework type from annotations with priority."""
        frameworks = set()
        for ann in annotations:
            ft = ann.get("type")
            if ft:
                frameworks.add(ft)
        # Priority order
        for fw in ("spring-web", "spring", "jpa", "lombok"):
            if fw in frameworks:
                return fw
        return None

    def _calculate_complexity(self, node: Any, src: bytes) -> int:
        """Calculate cyclomatic complexity of a method."""
        complexity = 1
        complexity += self._count_complexity_nodes(node)
        return complexity

    def _count_complexity_nodes(self, node: Any) -> int:
        """Count complexity-adding nodes."""
        count = 0
        complexity_types = {"if_statement", "for_statement", "while_statement",
                           "do_statement", "switch_expression", "catch_clause",
                           "ternary_expression"}
        if node.type in complexity_types:
            count += 1
        elif node.type == "binary_expression":
            # Check for && and ||
            for child in node.children:
                if child.type in ("&&", "||"):
                    count += 1
        for child in node.children:
            count += self._count_complexity_nodes(child)
        return count

    def _text(self, node: Any, src: bytes) -> str:
        """Get text content of a node."""
        return src[node.start_byte:node.end_byte].decode("utf-8")
