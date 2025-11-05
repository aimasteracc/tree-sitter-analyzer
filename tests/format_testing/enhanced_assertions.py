"""
Enhanced Format Assertions

Provides highly specific and detailed assertion capabilities for format validation.
Includes semantic validation, structural analysis, and content-aware assertions.
"""

import ast
import csv
import io
import re
from dataclasses import dataclass
from typing import Any

from .format_assertions import FormatComplianceAssertions


@dataclass
class AssertionResult:
    """Result of an assertion with detailed information"""

    passed: bool
    message: str
    details: dict[str, Any]
    severity: str = "error"  # error, warning, info
    location: tuple[int, int] | None = None  # line, column
    suggestion: str | None = None


@dataclass
class FormatElement:
    """Represents a format element with metadata"""

    element_type: str
    name: str
    content: str
    line_number: int
    column_number: int
    attributes: dict[str, Any]


class SemanticFormatValidator:
    """Validates semantic correctness of format output"""

    def __init__(self):
        self.language_keywords = {
            "python": {
                "def",
                "class",
                "import",
                "from",
                "if",
                "else",
                "for",
                "while",
                "try",
                "except",
            },
            "java": {
                "public",
                "private",
                "protected",
                "class",
                "interface",
                "extends",
                "implements",
            },
            "javascript": {
                "function",
                "class",
                "const",
                "let",
                "var",
                "if",
                "else",
                "for",
                "while",
            },
            "typescript": {
                "function",
                "class",
                "interface",
                "type",
                "const",
                "let",
                "var",
                "public",
                "private",
            },
        }

    def validate_semantic_consistency(
        self, format_output: str, format_type: str, language: str
    ) -> list[AssertionResult]:
        """Validate semantic consistency of format output"""
        results = []

        # Parse format elements
        elements = self._parse_format_elements(format_output, format_type)

        # Validate element relationships
        results.extend(self._validate_element_relationships(elements, language))

        # Validate naming conventions
        results.extend(self._validate_naming_conventions(elements, language))

        # Validate type consistency
        results.extend(self._validate_type_consistency(elements, language))

        # Validate access modifiers
        results.extend(self._validate_access_modifiers(elements, language))

        return results

    def _parse_format_elements(
        self, output: str, format_type: str
    ) -> list[FormatElement]:
        """Parse format output into structured elements"""
        elements = []

        if format_type == "csv":
            elements.extend(self._parse_csv_elements(output))
        else:
            elements.extend(self._parse_markdown_elements(output))

        return elements

    def _parse_csv_elements(self, output: str) -> list[FormatElement]:
        """Parse CSV format elements"""
        elements = []

        try:
            reader = csv.DictReader(io.StringIO(output))
            for line_num, row in enumerate(
                reader, start=2
            ):  # Start at 2 (after header)
                element = FormatElement(
                    element_type=row.get("Type", ""),
                    name=row.get("Name", ""),
                    content=str(row),
                    line_number=line_num,
                    column_number=1,
                    attributes={
                        "return_type": row.get("ReturnType", ""),
                        "parameters": row.get("Parameters", ""),
                        "access": row.get("Access", ""),
                        "static": row.get("Static", ""),
                        "final": row.get("Final", ""),
                        "line": row.get("Line", ""),
                    },
                )
                elements.append(element)
        except Exception as e:
            # If CSV parsing fails, create error element
            elements.append(
                FormatElement(
                    element_type="error",
                    name="csv_parse_error",
                    content=str(e),
                    line_number=1,
                    column_number=1,
                    attributes={},
                )
            )

        return elements

    def _parse_markdown_elements(self, output: str) -> list[FormatElement]:
        """Parse Markdown format elements"""
        elements = []
        lines = output.split("\n")

        current_section = None
        current_table = []
        in_table = False

        for line_num, line in enumerate(lines, start=1):
            line = line.strip()

            # Section headers
            if line.startswith("##"):
                current_section = line.replace("#", "").strip()
                elements.append(
                    FormatElement(
                        element_type="section",
                        name=current_section,
                        content=line,
                        line_number=line_num,
                        column_number=1,
                        attributes={"section_type": current_section},
                    )
                )
                in_table = False
                current_table = []

            # Table headers
            elif "|" in line and not line.startswith("|--"):
                if not in_table:
                    in_table = True
                    current_table = []

                # Parse table row
                cells = [cell.strip() for cell in line.split("|") if cell.strip()]
                if cells:
                    element = FormatElement(
                        element_type="table_row",
                        name=cells[0] if cells else "",
                        content=line,
                        line_number=line_num,
                        column_number=1,
                        attributes={
                            "cells": cells,
                            "section": current_section,
                            "table_index": len(current_table),
                        },
                    )
                    elements.append(element)
                    current_table.append(element)

            # Table separator
            elif line.startswith("|--"):
                continue

            # End of table
            elif in_table and not line:
                in_table = False

        return elements

    def _validate_element_relationships(
        self, elements: list[FormatElement], language: str
    ) -> list[AssertionResult]:
        """Validate relationships between elements"""
        results = []

        # Group elements by type
        by_type = {}
        for element in elements:
            if element.element_type not in by_type:
                by_type[element.element_type] = []
            by_type[element.element_type].append(element)

        # Validate class-method relationships
        if "class" in by_type and "method" in by_type:
            results.extend(
                self._validate_class_method_relationships(
                    by_type["class"], by_type["method"], language
                )
            )

        # Validate constructor relationships
        if "constructor" in by_type:
            results.extend(
                self._validate_constructor_relationships(
                    by_type.get("class", []), by_type["constructor"], language
                )
            )

        # Validate inheritance relationships
        results.extend(self._validate_inheritance_relationships(elements, language))

        return results

    def _validate_class_method_relationships(
        self, classes: list[FormatElement], methods: list[FormatElement], language: str
    ) -> list[AssertionResult]:
        """Validate class-method relationships"""
        results = []

        for class_elem in classes:
            class_name = class_elem.name

            # Find methods that should belong to this class
            class_methods = [
                m for m in methods if self._is_method_in_class(m, class_name)
            ]

            # Check for missing constructor
            if language in ["java", "typescript"] and class_name:
                has_constructor = any(
                    m.name == class_name or m.name == "constructor"
                    for m in class_methods
                )

                if not has_constructor:
                    results.append(
                        AssertionResult(
                            passed=False,
                            message=f"Class '{class_name}' missing constructor",
                            details={
                                "class_name": class_name,
                                "class_line": class_elem.line_number,
                                "expected_constructor": (
                                    class_name if language == "java" else "constructor"
                                ),
                            },
                            severity="warning",
                            location=(class_elem.line_number, class_elem.column_number),
                            suggestion=f"Add constructor for class '{class_name}'",
                        )
                    )

        return results

    def _validate_naming_conventions(
        self, elements: list[FormatElement], language: str
    ) -> list[AssertionResult]:
        """Validate naming conventions"""
        results = []

        naming_rules = {
            "python": {
                "class": r"^[A-Z][a-zA-Z0-9]*$",
                "method": r"^[a-z_][a-z0-9_]*$",
                "field": r"^[a-z_][a-z0-9_]*$",
            },
            "java": {
                "class": r"^[A-Z][a-zA-Z0-9]*$",
                "method": r"^[a-z][a-zA-Z0-9]*$",
                "field": r"^[a-z][a-zA-Z0-9]*$",
            },
            "javascript": {
                "class": r"^[A-Z][a-zA-Z0-9]*$",
                "method": r"^[a-z][a-zA-Z0-9]*$",
                "field": r"^[a-z][a-zA-Z0-9]*$",
            },
            "typescript": {
                "class": r"^[A-Z][a-zA-Z0-9]*$",
                "method": r"^[a-z][a-zA-Z0-9]*$",
                "field": r"^[a-z][a-zA-Z0-9]*$",
            },
        }

        rules = naming_rules.get(language, {})

        for element in elements:
            if element.element_type in rules and element.name:
                pattern = rules[element.element_type]

                if not re.match(pattern, element.name):
                    results.append(
                        AssertionResult(
                            passed=False,
                            message=f"Invalid {element.element_type} name '{element.name}' for {language}",
                            details={
                                "element_type": element.element_type,
                                "element_name": element.name,
                                "expected_pattern": pattern,
                                "language": language,
                            },
                            severity="warning",
                            location=(element.line_number, element.column_number),
                            suggestion=f"Use {language} naming convention for {element.element_type}",
                        )
                    )

        return results

    def _validate_type_consistency(
        self, elements: list[FormatElement], language: str
    ) -> list[AssertionResult]:
        """Validate type consistency"""
        results = []

        # Common type mappings
        type_mappings = {
            "java": {
                "string": "String",
                "int": "int",
                "boolean": "boolean",
                "void": "void",
            },
            "typescript": {
                "string": "string",
                "number": "number",
                "boolean": "boolean",
                "void": "void",
            },
        }

        if language not in type_mappings:
            return results

        valid_types = set(type_mappings[language].values())

        for element in elements:
            return_type = element.attributes.get("return_type", "")

            if return_type and return_type not in valid_types:
                # Check if it's a custom type (starts with uppercase)
                if not (
                    return_type[0].isupper() or return_type in ["var", "let", "const"]
                ):
                    results.append(
                        AssertionResult(
                            passed=False,
                            message=f"Invalid return type '{return_type}' for {language}",
                            details={
                                "element_name": element.name,
                                "return_type": return_type,
                                "valid_types": list(valid_types),
                                "language": language,
                            },
                            severity="error",
                            location=(element.line_number, element.column_number),
                            suggestion=f"Use valid {language} type or ensure custom type is properly defined",
                        )
                    )

        return results

    def _validate_access_modifiers(
        self, elements: list[FormatElement], language: str
    ) -> list[AssertionResult]:
        """Validate access modifiers"""
        results = []

        valid_modifiers = {
            "java": {"public", "private", "protected", "package"},
            "typescript": {"public", "private", "protected"},
            "python": {"public", "private"},  # Simplified
            "javascript": {"public"},  # Simplified
        }

        if language not in valid_modifiers:
            return results

        valid_set = valid_modifiers[language]

        for element in elements:
            access = element.attributes.get("access", "")

            if access and access not in valid_set:
                results.append(
                    AssertionResult(
                        passed=False,
                        message=f"Invalid access modifier '{access}' for {language}",
                        details={
                            "element_name": element.name,
                            "access_modifier": access,
                            "valid_modifiers": list(valid_set),
                            "language": language,
                        },
                        severity="error",
                        location=(element.line_number, element.column_number),
                        suggestion=f"Use valid {language} access modifier",
                    )
                )

        return results

    def _is_method_in_class(self, method: FormatElement, class_name: str) -> bool:
        """Check if method belongs to class (simplified heuristic)"""
        # This is a simplified check - in practice, you'd need more context
        return True

    def _validate_constructor_relationships(
        self,
        classes: list[FormatElement],
        constructors: list[FormatElement],
        language: str,
    ) -> list[AssertionResult]:
        """Validate constructor relationships"""
        results = []

        for constructor in constructors:
            # Find matching class
            matching_class = None
            for class_elem in classes:
                if (language == "java" and constructor.name == class_elem.name) or (
                    language in ["typescript", "javascript"]
                    and constructor.name == "constructor"
                ):
                    matching_class = class_elem
                    break

            if not matching_class:
                results.append(
                    AssertionResult(
                        passed=False,
                        message=f"Constructor '{constructor.name}' has no matching class",
                        details={
                            "constructor_name": constructor.name,
                            "constructor_line": constructor.line_number,
                            "available_classes": [c.name for c in classes],
                        },
                        severity="error",
                        location=(constructor.line_number, constructor.column_number),
                        suggestion="Ensure constructor matches a defined class",
                    )
                )

        return results

    def _validate_inheritance_relationships(
        self, elements: list[FormatElement], language: str
    ) -> list[AssertionResult]:
        """Validate inheritance relationships"""
        results = []

        # This would require more sophisticated parsing to detect inheritance
        # For now, we'll do basic validation

        class_names = {e.name for e in elements if e.element_type == "class"}

        for element in elements:
            # Check for references to undefined classes in parameters or return types
            return_type = element.attributes.get("return_type", "")
            parameters = element.attributes.get("parameters", "")

            # Simple check for custom types
            for text in [return_type, parameters]:
                if text:
                    # Look for capitalized words that might be class names
                    potential_classes = re.findall(r"\b[A-Z][a-zA-Z0-9]*\b", text)
                    for potential_class in potential_classes:
                        if (
                            potential_class not in class_names
                            and potential_class
                            not in ["String", "Integer", "Boolean", "Object"]
                        ):
                            results.append(
                                AssertionResult(
                                    passed=False,
                                    message=f"Reference to undefined class '{potential_class}'",
                                    details={
                                        "element_name": element.name,
                                        "referenced_class": potential_class,
                                        "context": text,
                                        "defined_classes": list(class_names),
                                    },
                                    severity="warning",
                                    location=(
                                        element.line_number,
                                        element.column_number,
                                    ),
                                    suggestion=f"Ensure class '{potential_class}' is defined or imported",
                                )
                            )

        return results


class StructuralFormatValidator:
    """Validates structural aspects of format output"""

    def validate_table_structure(
        self, output: str, format_type: str
    ) -> list[AssertionResult]:
        """Validate table structure consistency"""
        results = []

        if format_type == "csv":
            results.extend(self._validate_csv_structure(output))
        else:
            results.extend(self._validate_markdown_table_structure(output))

        return results

    def _validate_csv_structure(self, output: str) -> list[AssertionResult]:
        """Validate CSV structure"""
        results = []
        lines = output.strip().split("\n")

        if not lines:
            results.append(
                AssertionResult(
                    passed=False,
                    message="Empty CSV output",
                    details={"line_count": 0},
                    severity="error",
                )
            )
            return results

        # Check header
        header_line = lines[0]
        expected_headers = [
            "Type",
            "Name",
            "ReturnType",
            "Parameters",
            "Access",
            "Static",
            "Final",
            "Line",
        ]
        actual_headers = [h.strip() for h in header_line.split(",")]

        if actual_headers != expected_headers:
            results.append(
                AssertionResult(
                    passed=False,
                    message="CSV header mismatch",
                    details={
                        "expected_headers": expected_headers,
                        "actual_headers": actual_headers,
                        "missing_headers": set(expected_headers) - set(actual_headers),
                        "extra_headers": set(actual_headers) - set(expected_headers),
                    },
                    severity="error",
                    location=(1, 1),
                    suggestion="Use standard CSV header format",
                )
            )

        # Check row consistency
        header_count = len(actual_headers)
        for line_num, line in enumerate(lines[1:], start=2):
            if line.strip():
                row_cells = line.split(",")
                if len(row_cells) != header_count:
                    results.append(
                        AssertionResult(
                            passed=False,
                            message=f"CSV row {line_num} has incorrect column count",
                            details={
                                "expected_columns": header_count,
                                "actual_columns": len(row_cells),
                                "line_content": line,
                            },
                            severity="error",
                            location=(line_num, 1),
                            suggestion="Ensure all CSV rows have the same number of columns",
                        )
                    )

        return results

    def _validate_markdown_table_structure(self, output: str) -> list[AssertionResult]:
        """Validate Markdown table structure"""
        results = []
        lines = output.split("\n")

        in_table = False
        table_start_line = 0
        table_headers = []

        for line_num, line in enumerate(lines, start=1):
            line = line.strip()

            if "|" in line and not line.startswith("|--"):
                if not in_table:
                    # Start of new table
                    in_table = True
                    table_start_line = line_num
                    table_headers = [
                        cell.strip() for cell in line.split("|") if cell.strip()
                    ]
                else:
                    # Table row
                    row_cells = [
                        cell.strip() for cell in line.split("|") if cell.strip()
                    ]
                    if len(row_cells) != len(table_headers):
                        results.append(
                            AssertionResult(
                                passed=False,
                                message=f"Table row {line_num} has incorrect column count",
                                details={
                                    "table_start_line": table_start_line,
                                    "expected_columns": len(table_headers),
                                    "actual_columns": len(row_cells),
                                    "headers": table_headers,
                                    "row_content": line,
                                },
                                severity="error",
                                location=(line_num, 1),
                                suggestion="Ensure all table rows have the same number of columns as headers",
                            )
                        )

            elif line.startswith("|--"):
                # Table separator - validate format
                separators = [cell.strip() for cell in line.split("|") if cell.strip()]
                if len(separators) != len(table_headers):
                    results.append(
                        AssertionResult(
                            passed=False,
                            message=f"Table separator at line {line_num} has incorrect column count",
                            details={
                                "expected_columns": len(table_headers),
                                "actual_columns": len(separators),
                                "separator_line": line,
                            },
                            severity="error",
                            location=(line_num, 1),
                            suggestion="Ensure table separator matches header column count",
                        )
                    )

            elif in_table and not line:
                # End of table
                in_table = False

        return results


class ContentAwareValidator:
    """Validates content-specific aspects of format output"""

    def validate_content_accuracy(
        self, format_output: str, source_code: str, language: str
    ) -> list[AssertionResult]:
        """Validate that format output accurately represents source code"""
        results = []

        # Parse source code to extract actual elements
        actual_elements = self._parse_source_code(source_code, language)

        # Parse format output to extract reported elements
        reported_elements = self._parse_format_output(format_output)

        # Compare actual vs reported
        results.extend(self._compare_elements(actual_elements, reported_elements))

        return results

    def _parse_source_code(
        self, source_code: str, language: str
    ) -> dict[str, list[dict[str, Any]]]:
        """Parse source code to extract actual elements"""
        elements = {"classes": [], "methods": [], "fields": []}

        if language == "python":
            elements.update(self._parse_python_code(source_code))
        elif language == "java":
            elements.update(self._parse_java_code(source_code))
        # Add other languages as needed

        return elements

    def _parse_python_code(self, source_code: str) -> dict[str, list[dict[str, Any]]]:
        """Parse Python source code using AST"""
        elements = {"classes": [], "methods": [], "fields": []}

        try:
            tree = ast.parse(source_code)

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    elements["classes"].append(
                        {"name": node.name, "line": node.lineno, "type": "class"}
                    )

                elif isinstance(node, ast.FunctionDef):
                    elements["methods"].append(
                        {
                            "name": node.name,
                            "line": node.lineno,
                            "type": "method",
                            "args": [arg.arg for arg in node.args.args],
                        }
                    )

                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            elements["fields"].append(
                                {
                                    "name": target.id,
                                    "line": node.lineno,
                                    "type": "field",
                                }
                            )

        except SyntaxError:
            # Handle syntax errors gracefully
            pass

        return elements

    def _parse_java_code(self, source_code: str) -> dict[str, list[dict[str, Any]]]:
        """Parse Java source code using regex patterns"""
        elements = {"classes": [], "methods": [], "fields": []}

        lines = source_code.split("\n")

        for line_num, line in enumerate(lines, start=1):
            line = line.strip()

            # Class declarations
            class_match = re.match(r".*class\s+(\w+)", line)
            if class_match:
                elements["classes"].append(
                    {"name": class_match.group(1), "line": line_num, "type": "class"}
                )

            # Method declarations
            method_match = re.match(r".*\s+(\w+)\s*\([^)]*\)\s*{?", line)
            if method_match and not class_match:
                elements["methods"].append(
                    {"name": method_match.group(1), "line": line_num, "type": "method"}
                )

            # Field declarations
            field_match = re.match(r".*\s+(\w+)\s*[=;]", line)
            if field_match and not method_match and not class_match:
                elements["fields"].append(
                    {"name": field_match.group(1), "line": line_num, "type": "field"}
                )

        return elements

    def _parse_format_output(
        self, format_output: str
    ) -> dict[str, list[dict[str, Any]]]:
        """Parse format output to extract reported elements"""
        elements = {"classes": [], "methods": [], "fields": []}

        # This would parse the format output based on its structure
        # Implementation depends on the specific format

        return elements

    def _compare_elements(
        self,
        actual: dict[str, list[dict[str, Any]]],
        reported: dict[str, list[dict[str, Any]]],
    ) -> list[AssertionResult]:
        """Compare actual vs reported elements"""
        results = []

        for element_type in ["classes", "methods", "fields"]:
            actual_names = {elem["name"] for elem in actual.get(element_type, [])}
            reported_names = {elem["name"] for elem in reported.get(element_type, [])}

            # Missing elements
            missing = actual_names - reported_names
            for name in missing:
                results.append(
                    AssertionResult(
                        passed=False,
                        message=f"Missing {element_type[:-1]} '{name}' in format output",
                        details={
                            "element_type": element_type[:-1],
                            "element_name": name,
                            "actual_elements": list(actual_names),
                            "reported_elements": list(reported_names),
                        },
                        severity="error",
                        suggestion=f"Ensure {element_type[:-1]} '{name}' is included in format output",
                    )
                )

            # Extra elements
            extra = reported_names - actual_names
            for name in extra:
                results.append(
                    AssertionResult(
                        passed=False,
                        message=f"Extra {element_type[:-1]} '{name}' in format output",
                        details={
                            "element_type": element_type[:-1],
                            "element_name": name,
                            "actual_elements": list(actual_names),
                            "reported_elements": list(reported_names),
                        },
                        severity="warning",
                        suggestion=f"Remove or verify {element_type[:-1]} '{name}' in format output",
                    )
                )

        return results


class EnhancedFormatAssertions(FormatComplianceAssertions):
    """Enhanced format assertions with semantic and structural validation"""

    def __init__(self):
        super().__init__()
        self.semantic_validator = SemanticFormatValidator()
        self.structural_validator = StructuralFormatValidator()
        self.content_validator = ContentAwareValidator()

    def assert_semantic_correctness(
        self,
        format_output: str,
        format_type: str,
        language: str,
        source_code: str | None = None,
    ) -> list[AssertionResult]:
        """Assert semantic correctness of format output"""
        results = []

        # Semantic validation
        results.extend(
            self.semantic_validator.validate_semantic_consistency(
                format_output, format_type, language
            )
        )

        # Structural validation
        results.extend(
            self.structural_validator.validate_table_structure(
                format_output, format_type
            )
        )

        # Content accuracy validation (if source code provided)
        if source_code:
            results.extend(
                self.content_validator.validate_content_accuracy(
                    format_output, source_code, language
                )
            )

        return results

    def assert_format_completeness(
        self, format_output: str, expected_elements: dict[str, int]
    ) -> list[AssertionResult]:
        """Assert format output completeness"""
        results = []

        # Count actual elements in output
        actual_counts = self._count_format_elements(format_output)

        for element_type, expected_count in expected_elements.items():
            actual_count = actual_counts.get(element_type, 0)

            if actual_count != expected_count:
                results.append(
                    AssertionResult(
                        passed=False,
                        message=f"Element count mismatch for {element_type}",
                        details={
                            "element_type": element_type,
                            "expected_count": expected_count,
                            "actual_count": actual_count,
                            "all_counts": actual_counts,
                        },
                        severity="error",
                        suggestion=f"Ensure {element_type} count matches expected value",
                    )
                )

        return results

    def assert_format_consistency(
        self, outputs: dict[str, str]
    ) -> list[AssertionResult]:
        """Assert consistency across different format types"""
        results = []

        # Extract element counts from each format
        format_counts = {}
        for format_type, output in outputs.items():
            format_counts[format_type] = self._count_format_elements(output)

        # Compare counts across formats
        if len(format_counts) > 1:
            format_types = list(format_counts.keys())
            base_format = format_types[0]
            base_counts = format_counts[base_format]

            for other_format in format_types[1:]:
                other_counts = format_counts[other_format]

                for element_type in base_counts:
                    if element_type in other_counts:
                        if base_counts[element_type] != other_counts[element_type]:
                            results.append(
                                AssertionResult(
                                    passed=False,
                                    message=f"Element count inconsistency between {base_format} and {other_format}",
                                    details={
                                        "element_type": element_type,
                                        "base_format": base_format,
                                        "base_count": base_counts[element_type],
                                        "other_format": other_format,
                                        "other_count": other_counts[element_type],
                                    },
                                    severity="error",
                                    suggestion=f"Ensure {element_type} count is consistent across all formats",
                                )
                            )

        return results

    def _count_format_elements(self, output: str) -> dict[str, int]:
        """Count elements in format output"""
        counts = {}

        # Count different types of elements based on patterns
        lines = output.split("\n")

        for line in lines:
            line = line.strip()

            # Count table rows (excluding headers and separators)
            if "|" in line and not line.startswith("|--") and not line.startswith("##"):
                cells = [cell.strip() for cell in line.split("|") if cell.strip()]
                if cells and len(cells) > 1:  # Valid table row
                    element_type = cells[0].lower() if cells else "unknown"
                    counts[element_type] = counts.get(element_type, 0) + 1

            # Count sections
            elif line.startswith("##"):
                section_type = line.replace("#", "").strip().lower()
                counts[f"section_{section_type}"] = (
                    counts.get(f"section_{section_type}", 0) + 1
                )

        return counts

    def generate_assertion_report(
        self, results: list[AssertionResult]
    ) -> dict[str, Any]:
        """Generate comprehensive assertion report"""
        total_assertions = len(results)
        passed_assertions = sum(1 for r in results if r.passed)
        failed_assertions = total_assertions - passed_assertions

        # Group by severity
        by_severity = {}
        for result in results:
            severity = result.severity
            if severity not in by_severity:
                by_severity[severity] = []
            by_severity[severity].append(result)

        # Group by message type
        by_message_type = {}
        for result in results:
            message_type = (
                result.message.split(":")[0]
                if ":" in result.message
                else result.message.split(" ")[0]
            )
            if message_type not in by_message_type:
                by_message_type[message_type] = []
            by_message_type[message_type].append(result)

        return {
            "summary": {
                "total_assertions": total_assertions,
                "passed_assertions": passed_assertions,
                "failed_assertions": failed_assertions,
                "success_rate": (
                    passed_assertions / total_assertions if total_assertions > 0 else 0
                ),
            },
            "by_severity": {
                severity: {
                    "count": len(results),
                    "messages": [r.message for r in results],
                }
                for severity, results in by_severity.items()
            },
            "by_message_type": {
                msg_type: len(results) for msg_type, results in by_message_type.items()
            },
            "detailed_results": [
                {
                    "passed": r.passed,
                    "message": r.message,
                    "severity": r.severity,
                    "location": r.location,
                    "suggestion": r.suggestion,
                    "details": r.details,
                }
                for r in results
            ],
        }


class EnhancedAssertions:
    """Main enhanced assertions class that integrates all validation components"""

    def __init__(self):
        self.semantic_validator = SemanticFormatValidator()
        self.structural_validator = StructuralFormatValidator()
        self.content_validator = ContentAwareValidator()

    def validate_format_output(
        self, output: str, format_type: str, language: str = "python"
    ) -> dict[str, Any]:
        """Comprehensive format output validation"""

        all_results = []

        # Semantic validation
        semantic_results = self.semantic_validator.validate_semantic_consistency(
            output, format_type, language
        )
        all_results.extend(semantic_results)

        # Structural validation
        structural_results = self.structural_validator.validate_table_structure(
            output, format_type
        )
        all_results.extend(structural_results)

        # Content validation
        content_results = self.content_validator.validate_content_accuracy(
            output, format_type, language
        )
        all_results.extend(content_results)

        # Analyze results
        analysis = self._analyze_assertion_results(all_results)

        return {
            "valid": analysis["summary"]["failed_assertions"] == 0,
            "issues": [r.message for r in all_results if not r.passed],
            "analysis": analysis,
            "total_checks": len(all_results),
            "passed_checks": analysis["summary"]["passed_assertions"],
            "failed_checks": analysis["summary"]["failed_assertions"],
        }

    def _analyze_assertion_results(
        self, results: list[AssertionResult]
    ) -> dict[str, Any]:
        """Analyze assertion results and provide summary"""

        total_assertions = len(results)
        passed_assertions = sum(1 for r in results if r.passed)
        failed_assertions = total_assertions - passed_assertions

        # Group by severity
        by_severity = {}
        for result in results:
            severity = result.severity
            if severity not in by_severity:
                by_severity[severity] = []
            by_severity[severity].append(result)

        # Group by message type
        by_message_type = {}
        for result in results:
            message_type = (
                result.message.split(":")[0]
                if ":" in result.message
                else result.message.split(" ")[0]
            )
            if message_type not in by_message_type:
                by_message_type[message_type] = []
            by_message_type[message_type].append(result)

        return {
            "summary": {
                "total_assertions": total_assertions,
                "passed_assertions": passed_assertions,
                "failed_assertions": failed_assertions,
                "success_rate": (
                    passed_assertions / total_assertions if total_assertions > 0 else 0
                ),
            },
            "by_severity": {
                severity: {
                    "count": len(results),
                    "messages": [r.message for r in results],
                }
                for severity, results in by_severity.items()
            },
            "by_message_type": {
                msg_type: len(results) for msg_type, results in by_message_type.items()
            },
            "detailed_results": [
                {
                    "passed": r.passed,
                    "message": r.message,
                    "severity": r.severity,
                    "location": r.location,
                    "suggestion": r.suggestion,
                    "details": r.details,
                }
                for r in results
            ],
        }
