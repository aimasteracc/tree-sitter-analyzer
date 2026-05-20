"""Class and class-attribute extraction mixin for the Python extractor."""

from __future__ import annotations

from typing import Any

from ...models import Class, Variable
from ...utils import log_debug, log_warning
from ._extractor_helpers import (
    ClassBodyQueryRuntime,
    ClassBuildInput,
    _class_body_assignment_node,
    _extract_class_decorators,
    _extract_class_name_and_superclasses,
    build_class_element,
    node_line_range,
    query_class_body_nodes,
)


class PythonClassExtractionMixin:
    def extract_classes(self, tree: Any, source_code: str) -> list[Class]:
        """Extract Python class definitions with detailed information."""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        classes: list[Class] = []
        extractors = {
            "class_definition": self._extract_class_optimized,
        }

        if tree is not None and tree.root_node is not None:
            try:
                self._traverse_and_extract_iterative(
                    tree.root_node, extractors, classes, "class"
                )
                log_debug(f"Extracted {len(classes)} Python classes")
            except Exception as exc:
                log_debug(f"Error during class extraction: {exc}")
                return []

        return classes

    def extract_variables(self, tree: Any, source_code: str) -> list[Variable]:
        """Extract Python variable definitions (class attributes only)."""
        variables: list[Variable] = []

        try:
            class_query = """
        (class_definition
            body: (block) @class.body) @class.definition
        """

            class_bodies = query_class_body_nodes(
                ClassBodyQueryRuntime(
                    tree=tree,
                    class_query=class_query,
                    log_debug_fn=log_debug,
                    log_warning_fn=log_warning,
                )
            )

            for class_body in class_bodies:
                variables.extend(
                    self._extract_class_attributes(class_body, source_code)
                )

        except Exception as exc:
            log_warning(f"Could not extract Python class attributes: {exc}")

        return variables

    def _extract_class_optimized(self, node: Any) -> Class | None:
        """Extract class information with detailed metadata."""
        try:
            start_line, end_line = node_line_range(node)

            decorators = _extract_class_decorators(
                node.parent, self._get_node_text_optimized
            )
            class_name, superclasses = _extract_class_name_and_superclasses(node)

            if not class_name:
                return None

            docstring = self._extract_docstring_for_line(start_line)
            raw_text = self._get_node_text_optimized(node)

            return build_class_element(
                ClassBuildInput(
                    name=class_name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    superclasses=superclasses,
                    decorators=decorators,
                    docstring=docstring,
                    current_module=self.current_module,
                    framework_type=self.framework_type,
                )
            )
        except Exception as exc:
            log_debug(f"Failed to extract class info: {exc}")
            return None

    def _is_framework_class(self, node: Any, class_name: str) -> bool:
        """Check if class is a framework-specific class."""
        if self.framework_type == "django":
            node_text = self._get_node_text_optimized(node)
            return any(
                pattern in node_text
                for pattern in ["Model", "View", "Form", "Serializer", "TestCase"]
            )
        if self.framework_type == "flask":
            return "Flask" in self.source_code or "Blueprint" in self.source_code
        if self.framework_type == "fastapi":
            return "APIRouter" in self.source_code or "BaseModel" in self.source_code
        return False

    def _extract_class_attributes(
        self, class_body_node: Any, source_code: str
    ) -> list[Variable]:
        """Extract class-level attribute assignments."""
        attributes: list[Variable] = []

        try:
            for child in class_body_node.children:
                assignment = _class_body_assignment_node(child)
                if assignment is None:
                    continue
                attribute = self._extract_class_attribute_info(assignment, source_code)
                if attribute:
                    attributes.append(attribute)

        except Exception as exc:
            log_warning(f"Could not extract class attributes: {exc}")

        return attributes

    def _extract_detailed_class_info(self, node: Any, source_code: str) -> Class | None:
        """Extract comprehensive class information from AST node."""
        try:
            name = self._extract_name_from_node(node, source_code)
            if not name:
                return None

            superclasses = self._extract_superclasses_from_node(node, source_code)
            decorators = self._extract_decorators_from_node(node, source_code)
            full_qualified_name = (
                f"{self.current_module}.{name}" if self.current_module else name
            )

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

        except Exception as exc:
            log_warning(f"Could not extract detailed class info: {exc}")
            return None
