"""Full format validation helpers for specification compliance tests."""

import re


class FormatSpecificationValidatorFullMixin:
    """Full-format validation behavior for format specification tests."""

    def validate_full_format_specification(self, output: str, class_name: str) -> bool:
        """Validate Full Format specification compliance"""
        self.errors.clear()
        self.warnings.clear()

        lines = output.split("\n")

        if not self._validate_full_format_header(lines, class_name):
            return False

        if not self._validate_full_format_sections(lines):
            return False

        if not self._validate_full_format_tables(lines):
            return False

        if not self._validate_common_formatting(output):
            return False

        return len(self.errors) == 0

    def _validate_full_format_header(self, lines: list[str], class_name: str) -> bool:
        """Validate Full Format header: # {package}.{ClassName}"""
        if not lines or not any(line.strip() for line in lines):
            self.errors.append("Empty output")
            return False

        header_line = lines[0].strip()

        if not header_line:
            self.errors.append("Empty output")
            return False

        if not header_line.startswith("# "):
            self.errors.append(f"Header must start with '# ', got: {header_line}")
            return False

        header_content = header_line[2:]
        if class_name not in header_content:
            self.errors.append(
                f"Header must contain class name '{class_name}', got: {header_content}"
            )
            return False

        if "." not in header_content:
            self.warnings.append(
                f"Header should contain package information: {header_content}"
            )

        return True

    def _validate_full_format_sections(self, lines: list[str]) -> bool:
        """Validate required sections for Full Format"""
        content = "\n".join(lines)

        required_sections = ["## Class Info", "## Methods", "## Fields"]

        for section in required_sections:
            if section not in content:
                self.errors.append(f"Missing required section: {section}")

        if "## Imports" not in content:
            self.warnings.append("Missing optional section: ## Imports")

        return len([e for e in self.errors if "Missing required section" in e]) == 0

    def _validate_full_format_tables(self, lines: list[str]) -> bool:
        """Validate table structures for Full Format"""
        content = "\n".join(lines)

        class_info_match = re.search(r"## Class Info\n(.*?)\n\n", content, re.DOTALL)
        if class_info_match:
            table_content = class_info_match.group(1)
            if not self._validate_markdown_table(table_content, ["Property", "Value"]):
                self.errors.append("Invalid Class Info table structure")

        methods_match = re.search(r"## Methods\n(.*?)(?=\n##|\n$)", content, re.DOTALL)
        if methods_match:
            table_content = methods_match.group(1)
            expected_headers = ["Name", "Return Type", "Parameters", "Access", "Line"]
            if not self._validate_markdown_table(table_content, expected_headers):
                self.errors.append("Invalid Methods table structure")

        fields_match = re.search(r"## Fields\n(.*?)(?=\n##|\n$)", content, re.DOTALL)
        if fields_match:
            table_content = fields_match.group(1)
            expected_headers = ["Name", "Type", "Access", "Static", "Final", "Line"]
            if not self._validate_markdown_table(table_content, expected_headers):
                self.errors.append("Invalid Fields table structure")

        return (
            len([e for e in self.errors if "Invalid" in e and "table structure" in e])
            == 0
        )
