"""
Enhanced Format Assertions

Provides highly specific and detailed assertion capabilities for format validation.
Includes semantic validation, structural analysis, and content-aware assertions.
"""

import ast
import csv
import io
import re
from typing import Any

from ._enhanced_assertion_models import AssertionResult, FormatElement
from .format_assertions import FormatComplianceAssertions

__all__ = [
    "AssertionResult",
    "ContentAwareValidator",
    "EnhancedAssertions",
    "EnhancedFormatAssertions",
    "FormatElement",
    "SemanticFormatValidator",
    "StructuralFormatValidator",
]


class EnhancedFormatAssertionsAssertMixin:
    """Assertion helpers used by EnhancedFormatAssertions."""

    def assert_semantic_correctness(
        self,
        format_output: str,
        format_type: str,
        language: str,
        source_code: str | None = None,
    ) -> list[AssertionResult]:
        """Assert semantic correctness of format output"""
        results = []
        results.extend(
            self.semantic_validator.validate_semantic_consistency(
                format_output, format_type, language
            )
        )
        results.extend(
            self.structural_validator.validate_table_structure(
                format_output, format_type
            )
        )

        results.extend(
            _content_accuracy_results(
                self.content_validator, format_output, source_code, language
            )
        )

        return results

    def assert_format_completeness(
        self, format_output: str, expected_elements: dict[str, int]
    ) -> list[AssertionResult]:
        """Assert format completeness"""
        actual_counts = count_format_elements(format_output)
        return _count_mismatch_results(actual_counts, expected_elements)

    def assert_format_consistency(
        self, outputs: dict[str, str]
    ) -> list[AssertionResult]:
        """Assert consistency across different format types"""
        format_counts = {
            format_type: count_format_elements(output)
            for format_type, output in outputs.items()
        }
        return compare_format_counts(format_counts)

    def generate_assertion_report(
        self, results: list[AssertionResult]
    ) -> dict[str, Any]:
        """Generate comprehensive assertion report"""
        return build_assertion_report(results)


class EnhancedFormatAssertions(
    EnhancedFormatAssertionsAssertMixin, FormatComplianceAssertions
):
    """Enhanced format assertions with semantic and structural validation"""

    def __init__(self):
        super().__init__()
        self.semantic_validator = SemanticFormatValidator()
        self.structural_validator = StructuralFormatValidator()
        self.content_validator = ContentAwareValidator()


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
        content_results = _content_accuracy_results(
            self.content_validator, output, None, language
        )
        all_results.extend(content_results)

        # Analyze results
        analysis = build_assertion_report(all_results)

        return {
            "valid": analysis["summary"]["failed_assertions"] == 0,
            "issues": [r.message for r in all_results if not r.passed],
            "analysis": analysis,
            "total_checks": len(all_results),
            "passed_checks": analysis["summary"]["passed_assertions"],
            "failed_checks": analysis["summary"]["failed_assertions"],
        }


class ContentAwareValidator:
    """Validates content-specific aspects of format output."""

    def validate_content_accuracy(
        self, format_output: str, source_code: str, language: str
    ) -> list[AssertionResult]:
        """Validate that format output accurately represents source code"""
        actual_elements = self._parse_source_code(source_code, language)
        reported_elements = self._parse_format_output(format_output)
        return self._compare_elements(actual_elements, reported_elements)

    def _parse_source_code(
        self, source_code: str, language: str
    ) -> dict[str, list[dict[str, Any]]]:
        """Parse source code to extract actual elements"""
        elements = {"classes": [], "methods": [], "fields": []}

        if language == "python":
            elements.update(self._parse_python_code(source_code))
        elif language == "java":
            elements.update(self._parse_java_code(source_code))

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
            pass

        return elements

    def _parse_java_code(self, source_code: str) -> dict[str, list[dict[str, Any]]]:
        """Parse Java source code using regex patterns"""
        elements = {"classes": [], "methods": [], "fields": []}

        for line_num, line in enumerate(source_code.split("\n"), start=1):
            line = line.strip()

            class_match = re.match(r".*class\s+(\w+)", line)
            if class_match:
                elements["classes"].append(
                    {"name": class_match.group(1), "line": line_num, "type": "class"}
                )

            method_match = re.match(r".*\s+(\w+)\s*\([^)]*\)\s*{?", line)
            if method_match and not class_match:
                elements["methods"].append(
                    {"name": method_match.group(1), "line": line_num, "type": "method"}
                )

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

            for name in actual_names - reported_names:
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

            for name in reported_names - actual_names:
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

        legacy_headers = [
            "Type",
            "Name",
            "ReturnType",
            "Parameters",
            "Access",
            "Static",
            "Final",
            "Line",
        ]
        new_headers_1 = [
            "Type",
            "Name",
            "Start Line",
            "End Line",
            "Language",
            "Visibility",
            "Parameters",
            "Return Type",
            "Modifiers",
        ]
        mock_headers = ["Type", "Name", "Signature", "Visibility", "Lines"]
        valid_header_sets = [legacy_headers, new_headers_1, mock_headers]

        actual_headers = [header.strip() for header in lines[0].split(",")]
        headers_valid = any(
            actual_headers == expected for expected in valid_header_sets
        )

        if not headers_valid:
            results.append(
                AssertionResult(
                    passed=True,
                    message="CSV header format unrecognized (non-critical)",
                    details={
                        "actual_headers": actual_headers,
                        "note": "Headers don't match any known CSV format but may still be valid",
                    },
                    severity="warning",
                    location=(1, 1),
                    suggestion="Consider using one of the standard CSV header formats for consistency",
                )
            )

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
        in_table = False
        table_start_line = 0
        table_headers = []

        for line_num, line in enumerate(output.split("\n"), start=1):
            line = line.strip()

            if "|" in line and not line.startswith("|--"):
                if not in_table:
                    in_table = True
                    table_start_line = line_num
                    table_headers = [
                        cell.strip() for cell in line.split("|") if cell.strip()
                    ]
                else:
                    results.extend(
                        _validate_markdown_row(
                            line, line_num, table_start_line, table_headers
                        )
                    )

            elif line.startswith("|--"):
                results.extend(
                    _validate_markdown_separator(line, line_num, table_headers)
                )

            elif in_table and not line:
                in_table = False

        return results


def _validate_markdown_row(
    line: str,
    line_num: int,
    table_start_line: int,
    table_headers: list[str],
) -> list[AssertionResult]:
    row_cells = [cell.strip() for cell in line.split("|") if cell.strip()]
    if len(row_cells) == len(table_headers):
        return []
    return [
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
            suggestion="Ensure all table rows have same number of columns as headers",
        )
    ]


def _validate_markdown_separator(
    line: str, line_num: int, table_headers: list[str]
) -> list[AssertionResult]:
    separators = [cell.strip() for cell in line.split("|") if cell.strip()]
    if len(separators) == len(table_headers):
        return []
    return [
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
    ]


def _count_mismatch_results(
    actual_counts: dict[str, int],
    expected_elements: dict[str, int],
) -> list[AssertionResult]:
    results = []

    for element_type, expected_count in expected_elements.items():
        result = _count_mismatch_result_for_expected(
            element_type, expected_count, actual_counts
        )
        if result:
            results.append(result)

    return results


def _count_mismatch_result_for_expected(
    element_type: str,
    expected_count: int,
    actual_counts: dict[str, int],
) -> AssertionResult | None:
    actual_count = actual_counts.get(element_type, 0)
    if actual_count == expected_count:
        return None
    return _count_mismatch_result(
        element_type, expected_count, actual_count, actual_counts
    )


def _content_accuracy_results(
    content_validator: Any,
    format_output: str,
    source_code: str | None,
    language: str,
) -> list[AssertionResult]:
    if not source_code:
        return []
    return content_validator.validate_content_accuracy(
        format_output, source_code, language
    )


def _count_mismatch_result(
    element_type: str,
    expected_count: int,
    actual_count: int,
    actual_counts: dict[str, int],
) -> AssertionResult:
    return AssertionResult(
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


class SemanticFormatValidator:
    """Validates semantic correctness of format output"""

    def __init__(self):
        self.language_keywords = LANGUAGE_KEYWORDS

    def validate_semantic_consistency(
        self, format_output: str, format_type: str, language: str
    ) -> list[AssertionResult]:
        """Validate semantic consistency of format output"""
        elements = parse_format_elements(format_output, format_type)
        results = validate_element_relationships(elements, language)
        results.extend(validate_naming_conventions(elements, language))
        results.extend(validate_type_consistency(elements, language))
        results.extend(validate_access_modifiers(elements, language))
        return results


def parse_format_elements(output: str, format_type: str) -> list[FormatElement]:
    """Parse format output into structured elements."""
    if format_type == "csv":
        return parse_csv_elements(output)
    return parse_markdown_elements(output)


def parse_csv_elements(output: str) -> list[FormatElement]:
    """Parse CSV format elements."""
    elements = []

    try:
        reader = csv.DictReader(io.StringIO(output))
        for line_num, row in enumerate(reader, start=2):
            elements.append(_csv_row_element(row, line_num))
    except Exception as exc:
        elements.append(
            FormatElement(
                element_type="error",
                name="csv_parse_error",
                content=str(exc),
                line_number=1,
                column_number=1,
                attributes={},
            )
        )

    return elements


def _csv_row_element(row: dict[str, str | None], line_num: int) -> FormatElement:
    return FormatElement(
        element_type=row.get("Type", "") or "",
        name=row.get("Name", "") or "",
        content=str(row),
        line_number=line_num,
        column_number=1,
        attributes={
            "return_type": row.get("ReturnType", "") or "",
            "parameters": row.get("Parameters", "") or "",
            "access": row.get("Access", "") or "",
            "static": row.get("Static", "") or "",
            "final": row.get("Final", "") or "",
            "line": row.get("Line", "") or "",
        },
    )


def parse_markdown_elements(output: str) -> list[FormatElement]:
    """Parse Markdown format elements."""
    elements: list[FormatElement] = []
    current_section = None
    current_table: list[FormatElement] = []
    in_table = False

    for line_num, raw_line in enumerate(output.split("\n"), start=1):
        line = raw_line.strip()

        if line.startswith("##"):
            current_section = line.replace("#", "").strip()
            elements.append(_markdown_section_element(current_section, line, line_num))
            current_table = []
            in_table = False
            continue

        if _is_markdown_table_row(line):
            if not in_table:
                current_table = []
                in_table = True
            table_row = _markdown_table_row(
                line, line_num, current_section, current_table
            )
            if table_row:
                elements.append(table_row)
                current_table.append(table_row)
            continue

        if line.startswith("|--"):
            continue

        if in_table and not line:
            in_table = False

    return elements


def _markdown_section_element(
    current_section: str, line: str, line_num: int
) -> FormatElement:
    return FormatElement(
        element_type="section",
        name=current_section,
        content=line,
        line_number=line_num,
        column_number=1,
        attributes={"section_type": current_section},
    )


def _is_markdown_table_row(line: str) -> bool:
    return "|" in line and not line.startswith("|--")


def _markdown_table_row(
    line: str,
    line_num: int,
    current_section: str | None,
    current_table: list[FormatElement],
) -> FormatElement | None:
    cells = [cell.strip() for cell in line.split("|") if cell.strip()]
    if not cells:
        return None
    return FormatElement(
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


def validate_naming_conventions(
    elements: list[FormatElement], language: str
) -> list[AssertionResult]:
    """Validate naming conventions."""
    results = []
    rules = NAMING_RULES.get(language, {})

    for element in elements:
        result = _invalid_naming_result(element, language, rules)
        if result:
            results.append(result)

    return results


def _invalid_naming_result(
    element: FormatElement,
    language: str,
    rules: dict[str, str],
) -> AssertionResult | None:
    if element.element_type not in rules or not element.name:
        return None

    pattern = rules[element.element_type]
    if re.match(pattern, element.name):
        return None

    return AssertionResult(
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


def validate_type_consistency(
    elements: list[FormatElement], language: str
) -> list[AssertionResult]:
    """Validate type consistency."""
    if language not in TYPE_MAPPINGS:
        return []

    results = []
    valid_types = set(TYPE_MAPPINGS[language].values())

    for element in elements:
        result = _invalid_return_type_result(element, language, valid_types)
        if result:
            results.append(result)

    return results


def _invalid_return_type_result(
    element: FormatElement,
    language: str,
    valid_types: set[str],
) -> AssertionResult | None:
    return_type = element.attributes.get("return_type", "")
    if not return_type or return_type in valid_types:
        return None
    if return_type[0].isupper() or return_type in ["var", "let", "const"]:
        return None

    return AssertionResult(
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


def validate_access_modifiers(
    elements: list[FormatElement], language: str
) -> list[AssertionResult]:
    """Validate access modifiers."""
    if language not in VALID_MODIFIERS:
        return []

    results = []
    valid_set = VALID_MODIFIERS[language]

    for element in elements:
        result = _invalid_access_modifier_result(element, language, valid_set)
        if result:
            results.append(result)

    return results


def _invalid_access_modifier_result(
    element: FormatElement,
    language: str,
    valid_set: set[str],
) -> AssertionResult | None:
    access = element.attributes.get("access", "")
    if not access or access in valid_set:
        return None

    return AssertionResult(
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


def validate_element_relationships(
    elements: list[FormatElement], language: str
) -> list[AssertionResult]:
    """Validate relationships between parsed format elements."""
    results = []
    by_type = _group_elements_by_type(elements)

    if "class" in by_type and "method" in by_type:
        results.extend(
            _validate_class_method_relationships(
                by_type["class"], by_type["method"], language
            )
        )

    if "constructor" in by_type:
        results.extend(
            _validate_constructor_relationships(
                by_type.get("class", []), by_type["constructor"], language
            )
        )

    results.extend(validate_inheritance_relationships(elements, language))
    return results


def _group_elements_by_type(
    elements: list[FormatElement],
) -> dict[str, list[FormatElement]]:
    by_type: dict[str, list[FormatElement]] = {}
    for element in elements:
        if element.element_type not in by_type:
            by_type[element.element_type] = []
        by_type[element.element_type].append(element)
    return by_type


def _validate_class_method_relationships(
    classes: list[FormatElement],
    methods: list[FormatElement],
    language: str,
) -> list[AssertionResult]:
    results = []

    for class_elem in classes:
        class_name = class_elem.name
        class_methods = [
            method for method in methods if _is_method_in_class(method, class_name)
        ]
        if _class_missing_constructor(class_name, class_methods, language):
            results.append(
                _missing_constructor_result(class_elem, class_name, language)
            )

    return results


def _is_method_in_class(method: FormatElement, class_name: str) -> bool:
    """Check if method belongs to class (simplified heuristic)."""
    return True


def _class_missing_constructor(
    class_name: str,
    class_methods: list[FormatElement],
    language: str,
) -> bool:
    if language not in ["java", "typescript"] or not class_name:
        return False
    return not any(
        method.name == class_name or method.name == "constructor"
        for method in class_methods
    )


def _missing_constructor_result(
    class_elem: FormatElement,
    class_name: str,
    language: str,
) -> AssertionResult:
    expected_constructor = class_name if language == "java" else "constructor"
    return AssertionResult(
        passed=False,
        message=f"Class '{class_name}' missing constructor",
        details={
            "class_name": class_name,
            "class_line": class_elem.line_number,
            "expected_constructor": expected_constructor,
        },
        severity="warning",
        location=(class_elem.line_number, class_elem.column_number),
        suggestion=f"Add constructor for class '{class_name}'",
    )


def _validate_constructor_relationships(
    classes: list[FormatElement],
    constructors: list[FormatElement],
    language: str,
) -> list[AssertionResult]:
    results = []

    for constructor in constructors:
        matching_class = _matching_constructor_class(constructor, classes, language)
        if not matching_class:
            results.append(_orphan_constructor_result(constructor, classes))

    return results


def _matching_constructor_class(
    constructor: FormatElement,
    classes: list[FormatElement],
    language: str,
) -> FormatElement | None:
    for class_elem in classes:
        if language == "java" and constructor.name == class_elem.name:
            return class_elem
        if (
            language in ["typescript", "javascript"]
            and constructor.name == "constructor"
        ):
            return class_elem
    return None


def _orphan_constructor_result(
    constructor: FormatElement,
    classes: list[FormatElement],
) -> AssertionResult:
    return AssertionResult(
        passed=False,
        message=f"Constructor '{constructor.name}' has no matching class",
        details={
            "constructor_name": constructor.name,
            "constructor_line": constructor.line_number,
            "available_classes": [class_elem.name for class_elem in classes],
        },
        severity="error",
        location=(constructor.line_number, constructor.column_number),
        suggestion="Ensure constructor matches a defined class",
    )


def validate_inheritance_relationships(
    elements: list[FormatElement], language: str
) -> list[AssertionResult]:
    """Validate inheritance relationships."""
    _ = language
    class_names = {
        element.name for element in elements if element.element_type == "class"
    }
    results = []

    for element in elements:
        results.extend(_undefined_class_results(element, class_names))

    return results


def _undefined_class_results(
    element: FormatElement,
    class_names: set[str],
) -> list[AssertionResult]:
    results = []

    for text in _referenced_type_contexts(element):
        results.extend(_undefined_class_results_for_context(element, text, class_names))

    return results


def _undefined_class_results_for_context(
    element: FormatElement,
    text: str,
    class_names: set[str],
) -> list[AssertionResult]:
    results = []

    for potential_class in _potential_class_names(text):
        if _is_known_class_reference(potential_class, class_names):
            continue
        results.append(
            _undefined_class_result(element, potential_class, text, class_names)
        )

    return results


def _referenced_type_contexts(element: FormatElement) -> list[str]:
    return [
        text
        for text in [
            element.attributes.get("return_type", ""),
            element.attributes.get("parameters", ""),
        ]
        if text
    ]


def _potential_class_names(text: str) -> list[str]:
    return re.findall(r"\b[A-Z][a-zA-Z0-9]*\b", text)


def _is_known_class_reference(potential_class: str, class_names: set[str]) -> bool:
    return potential_class in class_names or potential_class in BUILTIN_CLASS_REFERENCES


def _undefined_class_result(
    element: FormatElement,
    potential_class: str,
    text: str,
    class_names: set[str],
) -> AssertionResult:
    return AssertionResult(
        passed=False,
        message=f"Reference to undefined class '{potential_class}'",
        details={
            "element_name": element.name,
            "referenced_class": potential_class,
            "context": text,
            "defined_classes": list(class_names),
        },
        severity="warning",
        location=(element.line_number, element.column_number),
        suggestion=f"Ensure class '{potential_class}' is defined or imported",
    )


def build_assertion_report(results: list[AssertionResult]) -> dict[str, Any]:
    """Build a grouped assertion report with summary and detail sections."""
    total_assertions = len(results)
    passed_assertions = sum(1 for result in results if result.passed)
    failed_assertions = total_assertions - passed_assertions

    by_severity = _group_by_severity(results)
    by_message_type = _group_by_message_type(results)

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
                "count": len(grouped_results),
                "messages": [result.message for result in grouped_results],
            }
            for severity, grouped_results in by_severity.items()
        },
        "by_message_type": {
            msg_type: len(grouped_results)
            for msg_type, grouped_results in by_message_type.items()
        },
        "detailed_results": [
            {
                "passed": result.passed,
                "message": result.message,
                "severity": result.severity,
                "location": result.location,
                "suggestion": result.suggestion,
                "details": result.details,
            }
            for result in results
        ],
    }


def count_format_elements(output: str) -> dict[str, int]:
    """Count table rows and section headings in format output."""
    counts: dict[str, int] = {}

    for line in output.split("\n"):
        line = line.strip()

        if "|" in line and not line.startswith("|--") and not line.startswith("##"):
            cells = [cell.strip() for cell in line.split("|") if cell.strip()]
            if cells and len(cells) > 1:
                element_type = cells[0].lower() if cells else "unknown"
                counts[element_type] = counts.get(element_type, 0) + 1

        elif line.startswith("##"):
            section_type = line.replace("#", "").strip().lower()
            counts[f"section_{section_type}"] = (
                counts.get(f"section_{section_type}", 0) + 1
            )

    return counts


def compare_format_counts(
    format_counts: dict[str, dict[str, int]],
) -> list[AssertionResult]:
    """Compare element counts across format outputs."""
    if len(format_counts) <= 1:
        return []

    results = []
    format_types = list(format_counts.keys())
    base_format = format_types[0]
    base_counts = format_counts[base_format]

    for other_format in format_types[1:]:
        other_counts = format_counts[other_format]
        results.extend(
            _compare_one_format_count(
                base_format, base_counts, other_format, other_counts
            )
        )
    return results


def _compare_one_format_count(
    base_format: str,
    base_counts: dict[str, int],
    other_format: str,
    other_counts: dict[str, int],
) -> list[AssertionResult]:
    results = []
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


def _group_by_severity(
    results: list[AssertionResult],
) -> dict[str, list[AssertionResult]]:
    by_severity: dict[str, list[AssertionResult]] = {}
    for result in results:
        severity = result.severity
        if severity not in by_severity:
            by_severity[severity] = []
        by_severity[severity].append(result)
    return by_severity


def _group_by_message_type(
    results: list[AssertionResult],
) -> dict[str, list[AssertionResult]]:
    by_message_type: dict[str, list[AssertionResult]] = {}
    for result in results:
        message_type = (
            result.message.split(":")[0]
            if ":" in result.message
            else result.message.split(" ")[0]
        )
        if message_type not in by_message_type:
            by_message_type[message_type] = []
        by_message_type[message_type].append(result)
    return by_message_type


LANGUAGE_KEYWORDS = {
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

NAMING_RULES = {
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

TYPE_MAPPINGS = {
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

VALID_MODIFIERS = {
    "java": {"public", "private", "protected", "package"},
    "typescript": {"public", "private", "protected"},
    "python": {"public", "private"},
    "javascript": {"public"},
}

BUILTIN_CLASS_REFERENCES = {"String", "Integer", "Boolean", "Object"}
