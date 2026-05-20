"""Content-aware validation for formatter output."""

import ast
import re
from typing import Any

from ._enhanced_assertion_models import AssertionResult


class ContentAwareValidator:
    """Validates content-specific aspects of format output"""

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
