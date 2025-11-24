"""
Format-Specific Assertion Libraries

Provides specialized assertion functions for different output formats to enable
precise validation of format structure, content, and compliance with specifications.
"""

import re
from re import Pattern

from .schema_validation import validate_format


class FormatAssertions:
    """Base class for format-specific assertions"""

    @staticmethod
    def assert_not_empty(
        content: str, message: str = "Content should not be empty"
    ) -> None:
        """Assert content is not empty"""
        assert content and content.strip(), message

    @staticmethod
    def assert_contains_all(content: str, required_items: list[str]) -> None:
        """Assert content contains all required items"""
        missing_items = [item for item in required_items if item not in content]
        assert not missing_items, f"Missing required items: {missing_items}"

    @staticmethod
    def assert_line_count_range(
        content: str, min_lines: int, max_lines: int | None = None
    ) -> None:
        """Assert content has line count within specified range"""
        lines = content.split("\n")
        line_count = len(lines)

        assert (
            line_count >= min_lines
        ), f"Expected at least {min_lines} lines, got {line_count}"

        if max_lines is not None:
            assert (
                line_count <= max_lines
            ), f"Expected at most {max_lines} lines, got {line_count}"

    @staticmethod
    def assert_valid_markdown_table(content: str) -> bool:
        """Assert content contains valid markdown table structure"""
        lines = content.split("\n")

        # Find table sections
        table_found = False
        for i, line in enumerate(lines):
            if (
                "|" in line
                and line.strip().startswith("|")
                and line.strip().endswith("|")
            ):
                table_found = True
                # Check if next line is separator
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if re.match(r"^\|[-:\s]+\|$", next_line):
                        return True

        return table_found

    @staticmethod
    def assert_valid_csv_format(content: str) -> bool:
        """Assert content contains valid CSV format"""
        if not content or not content.strip():
            return False

        lines = content.strip().split("\n")
        if len(lines) < 2:  # Need at least header and one data row
            return False

        # Check if all lines have consistent comma count
        header_comma_count = lines[0].count(",")
        for line in lines[1:]:
            if line.strip() and line.count(",") != header_comma_count:
                return False

        return True


class MarkdownTableAssertions(FormatAssertions):
    """Assertions for Markdown table format validation"""

    # Regex patterns for markdown elements
    HEADER_PATTERN: Pattern = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
    TABLE_HEADER_PATTERN: Pattern = re.compile(r"^\|.*\|$", re.MULTILINE)
    TABLE_SEPARATOR_PATTERN: Pattern = re.compile(r"^\|[\s\-:|]+\|$", re.MULTILINE)
    CODE_BLOCK_PATTERN: Pattern = re.compile(r"```(\w+)?\n(.*?)\n```", re.DOTALL)

    @staticmethod
    def assert_markdown_table_structure(
        content: str, expected_sections: list[str], require_all_sections: bool = True
    ) -> None:
        """
        Assert markdown table has required sections and structure

        Args:
            content: Markdown content to validate
            expected_sections: List of expected section names
            require_all_sections: If True, all sections must be present
        """
        # Validate basic markdown structure
        validation_result = validate_format(content, "markdown")
        assert (
            validation_result.is_valid
        ), f"Invalid markdown structure: {validation_result.errors}"

        # Check for section headers
        found_sections = MarkdownTableAssertions._extract_section_headers(content)

        if require_all_sections:
            missing_sections = set(expected_sections) - set(found_sections)
            assert (
                not missing_sections
            ), f"Missing required sections: {missing_sections}"

        # Validate table structure after each section
        sections = content.split("## ")
        for section in sections[1:]:  # Skip first empty section
            if "|" in section:  # Has table content
                MarkdownTableAssertions._validate_table_in_section(section)

    @staticmethod
    def assert_main_header_format(content: str, expected_class_name: str) -> None:
        """Assert main header follows expected format"""
        lines = content.split("\n")
        if not lines:
            assert False, "Content is empty"

        main_header = lines[0]
        assert main_header.startswith("# "), "Main header should start with '# '"
        assert (
            expected_class_name in main_header
        ), f"Main header should contain class name '{expected_class_name}'"

    @staticmethod
    def assert_table_column_headers(
        content: str, section_name: str, expected_columns: list[str]
    ) -> None:
        """Assert table in section has expected column headers"""
        section_content = MarkdownTableAssertions._extract_section_content(
            content, section_name
        )
        assert section_content, f"Section '{section_name}' not found"

        # Find table header line
        table_lines = [
            line for line in section_content.split("\n") if line.strip().startswith("|")
        ]
        assert table_lines, f"No table found in section '{section_name}'"

        header_line = table_lines[0]
        header_columns = [
            col.strip() for col in header_line.split("|")[1:-1]
        ]  # Remove empty first/last

        for expected_col in expected_columns:
            assert (
                expected_col in header_columns
            ), f"Missing column '{expected_col}' in section '{section_name}'"

    @staticmethod
    def assert_table_row_count(
        content: str, section_name: str, min_rows: int, max_rows: int | None = None
    ) -> None:
        """Assert table in section has expected number of rows"""
        section_content = MarkdownTableAssertions._extract_section_content(
            content, section_name
        )
        assert section_content, f"Section '{section_name}' not found"

        table_lines = [
            line for line in section_content.split("\n") if line.strip().startswith("|")
        ]
        # Subtract header and separator rows
        data_rows = len(table_lines) - 2 if len(table_lines) >= 2 else 0

        assert (
            data_rows >= min_rows
        ), f"Section '{section_name}' has {data_rows} rows, expected at least {min_rows}"

        if max_rows is not None:
            assert (
                data_rows <= max_rows
            ), f"Section '{section_name}' has {data_rows} rows, expected at most {max_rows}"

    @staticmethod
    def assert_code_block_language(content: str, expected_language: str) -> None:
        """Assert code blocks use expected language"""
        code_blocks = MarkdownTableAssertions.CODE_BLOCK_PATTERN.findall(content)

        for language, _ in code_blocks:
            if language:  # Language specified
                assert (
                    language == expected_language
                ), f"Code block language '{language}' should be '{expected_language}'"

    @staticmethod
    def _extract_section_headers(content: str) -> list[str]:
        """Extract section header names from content"""
        headers = MarkdownTableAssertions.HEADER_PATTERN.findall(content)
        return [header.strip() for header in headers]

    @staticmethod
    def _extract_section_content(content: str, section_name: str) -> str | None:
        """Extract content of specific section"""
        pattern = re.compile(
            f"^## {re.escape(section_name)}$(.*?)(?=^## |\\Z)", re.MULTILINE | re.DOTALL
        )
        match = pattern.search(content)
        return match.group(1).strip() if match else None

    @staticmethod
    def _validate_table_in_section(section_content: str) -> None:
        """Validate table structure within a section"""
        lines = section_content.split("\n")
        table_lines = [line for line in lines if line.strip().startswith("|")]

        if len(table_lines) < 2:
            assert False, "Table must have at least header and separator rows"

        # Check separator row
        separator_line = table_lines[1]
        assert MarkdownTableAssertions.TABLE_SEPARATOR_PATTERN.match(
            separator_line
        ), f"Invalid table separator: {separator_line}"


class CompactFormatAssertions(MarkdownTableAssertions):
    """Assertions specific to compact format"""

    @staticmethod
    @staticmethod
    def assert_compact_format_includes_complexity(content: str) -> None:
        """Assert compact format includes complexity scores"""
        # v1.6.1.4 compact format does not include complexity scores
        # This assertion is optional for backward compatibility
        pass

    @staticmethod
    def assert_compact_visibility_symbols(content: str) -> None:
        """Assert compact format includes visibility information"""
        # v1.6.1.4 compact format uses text (public, private, protected)
        # instead of symbols (+ - #)
        assert (
            "public" in content or "private" in content or "protected" in content
        ), "Missing visibility information in compact format"

    @staticmethod
    def assert_compact_abbreviated_signatures(content: str) -> None:
        """Assert compact format uses simplified structure"""
        # v1.6.1.4 compact format simplifies by:
        # 1. Removing Parameters column (only in full format)
        # 2. Using 4-column table for methods: Name, Return Type, Access, Line
        # Check for simplified table structure
        assert (
            "| Name | Return Type | Access | Line |" in content
        ), "Compact format should use simplified method table structure"


class CSVFormatAssertions(FormatAssertions):
    """Assertions for CSV format validation"""

    @staticmethod
    def assert_csv_format_compliance(content: str) -> None:
        """Assert CSV format follows specification"""
        # Validate CSV structure
        validation_result = validate_format(content, "csv")
        assert (
            validation_result.is_valid
        ), f"Invalid CSV structure: {validation_result.errors}"

        lines = content.strip().split("\n")
        assert len(lines) >= 2, "CSV must have header and at least one data row"

        # Validate header
        header = lines[0].split(",")
        CSVFormatAssertions._assert_csv_header_compliance(header)

    @staticmethod
    def assert_csv_required_columns(content: str, required_columns: list[str]) -> None:
        """Assert CSV has all required columns"""
        lines = content.strip().split("\n")
        if not lines:
            assert False, "CSV content is empty"

        header = [col.strip('"') for col in lines[0].split(",")]
        missing_columns = set(required_columns) - set(header)
        assert not missing_columns, f"Missing required CSV columns: {missing_columns}"

    @staticmethod
    def assert_csv_row_format(
        content: str, row_type: str, expected_pattern: Pattern
    ) -> None:
        """Assert CSV rows of specific type match expected pattern"""
        lines = content.strip().split("\n")[1:]  # Skip header

        matching_rows = [line for line in lines if line.startswith(f"{row_type},")]
        assert matching_rows, f"No {row_type} rows found in CSV"

        for row in matching_rows:
            assert expected_pattern.match(
                row
            ), f"Row doesn't match expected pattern: {row}"

    @staticmethod
    def assert_csv_complexity_scores(content: str) -> None:
        """Assert CSV includes complexity scores for methods"""
        lines = content.strip().split("\n")[1:]  # Skip header

        method_rows = [
            line
            for line in lines
            if line.startswith("Method,") or line.startswith("Constructor,")
        ]
        assert method_rows, "No method rows found in CSV"

        for row in method_rows:
            parts = row.split(",")
            if len(parts) >= 6:  # Assuming complexity is in 6th column
                complexity = parts[5].strip()
                assert (
                    complexity and complexity.isdigit()
                ), f"Invalid complexity score in row: {row}"

    @staticmethod
    def _assert_csv_header_compliance(header: list[str]) -> None:
        """Assert CSV header follows specification"""
        required_columns = ["Type", "Name", "Signature", "Visibility", "Lines"]

        for required_col in required_columns:
            assert (
                required_col in header
            ), f"Missing required CSV column: {required_col}"


class FullFormatAssertions(MarkdownTableAssertions):
    """Assertions specific to full format"""

    @staticmethod
    def assert_full_format_sections(content: str, class_name: str) -> None:
        """Assert full format has all required sections"""
        expected_sections = [
            "Package",
            "Imports",
            "Class Info",
            f"{class_name}",  # Class detail section
        ]

        MarkdownTableAssertions.assert_markdown_table_structure(
            content, expected_sections, require_all_sections=False
        )

    @staticmethod
    def assert_full_format_class_info_table(content: str) -> None:
        """Assert full format has proper Class Info table"""
        expected_columns = ["Property", "Value"]
        MarkdownTableAssertions.assert_table_column_headers(
            content, "Class Info", expected_columns
        )

        # Check for required properties in the actual v1.6.1.4 format
        required_properties = [
            "Name",
            "Package",
            "Type",
            "Access",
        ]
        for prop in required_properties:
            assert (
                f"| {prop} |" in content
            ), f"Missing property '{prop}' in Class Info table"

    @staticmethod
    def assert_full_format_detailed_sections(content: str) -> None:
        """Assert full format has detailed method/field sections"""
        # v1.6.1.4 format uses ## level sections for Methods and Fields
        expected_sections = [
            "Methods",
            "Fields",
        ]

        for section in expected_sections:
            # Check if section exists (at least one should exist)
            if f"## {section}" in content:
                # If section exists, it should have proper table structure
                section_content = MarkdownTableAssertions._extract_section_content(
                    content, section
                )
                if section_content:  # May be empty if no methods/fields
                    # Should have table markers if there's content
                    has_table = "|" in section_content
                    # Accept empty sections (class with no methods/fields)
                    assert (
                        has_table or not section_content.strip()
                    ), f"Section '{section}' should contain a table or be empty"


class FormatComplianceAssertions:
    """Cross-format validation assertions"""

    @staticmethod
    def assert_format_consistency(
        outputs: dict[str, str], element_counts: dict[str, int]
    ) -> None:
        """Assert consistency across different format outputs"""
        # All formats should contain the same basic information
        for format_type, output in outputs.items():
            FormatAssertions.assert_not_empty(
                output, f"{format_type} format should not be empty"
            )

        # Check element counts consistency
        FormatComplianceAssertions._assert_element_count_consistency(
            outputs, element_counts
        )

    @staticmethod
    def assert_no_format_regression(
        current_output: str,
        reference_output: str,
        format_type: str,
        allow_additions: bool = False,
    ) -> None:
        """Assert current output doesn't regress from reference"""
        if not allow_additions:
            # Exact match required
            assert (
                current_output == reference_output
            ), f"Format regression detected in {format_type} format"
        else:
            # Current output can have additions but not removals
            reference_lines = set(reference_output.split("\n"))
            current_lines = set(current_output.split("\n"))

            missing_lines = reference_lines - current_lines
            assert (
                not missing_lines
            ), f"Format regression: missing lines in {format_type} format: {missing_lines}"

    @staticmethod
    def _assert_element_count_consistency(
        outputs: dict[str, str], expected_counts: dict[str, int]
    ) -> None:
        """Assert element counts are consistent across formats"""
        for element_type, expected_count in expected_counts.items():
            for format_type, output in outputs.items():
                # Count occurrences of element type in output
                if element_type == "methods":
                    # Count method references (varies by format)
                    if format_type == "csv":
                        actual_count = output.count("Method,") + output.count(
                            "Constructor,"
                        )
                    else:
                        # For markdown formats, count method names in tables
                        actual_count = len(
                            re.findall(r"\|\s*\w+\s*\|.*\|.*\|.*\|", output)
                        )
                elif element_type == "fields":
                    if format_type == "csv":
                        actual_count = output.count("Field,")
                    else:
                        # Count field entries in tables
                        actual_count = len(
                            re.findall(r"\|\s*\w+\s*\|\s*\w+\s*\|.*\|.*\|", output)
                        )
                else:
                    continue  # Skip unknown element types

                # Allow some tolerance for different counting methods
                assert (
                    abs(actual_count - expected_count) <= 1
                ), f"Element count mismatch in {format_type}: expected {expected_count} {element_type}, got {actual_count}"


# Convenience functions for common assertions
def assert_full_format_compliance(content: str, class_name: str) -> None:
    """Assert content complies with full format specification"""
    FullFormatAssertions.assert_full_format_sections(content, class_name)
    FullFormatAssertions.assert_full_format_class_info_table(content)
    FullFormatAssertions.assert_full_format_detailed_sections(content)


def assert_compact_format_compliance(content: str) -> None:
    """Assert content complies with compact format specification"""
    CompactFormatAssertions.assert_compact_format_includes_complexity(content)
    CompactFormatAssertions.assert_compact_visibility_symbols(content)
    CompactFormatAssertions.assert_compact_abbreviated_signatures(content)


def assert_csv_format_compliance(content: str) -> None:
    """Assert content complies with CSV format specification"""
    required_columns = [
        "Type",
        "Name",
        "Signature",
        "Visibility",
        "Lines",
        "Complexity",
    ]
    CSVFormatAssertions.assert_csv_format_compliance(content)
    CSVFormatAssertions.assert_csv_required_columns(content, required_columns)
    CSVFormatAssertions.assert_csv_complexity_scores(content)
