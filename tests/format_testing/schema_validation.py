"""
Format Schema Validation

Provides comprehensive validation for different output formats including:
- Markdown table structure validation
- CSV format compliance checking
- JSON schema validation
- Format-specific syntax validation
"""

import csv
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from io import StringIO
from re import Pattern
from typing import Any


@dataclass
class ValidationResult:
    """Result of format validation"""

    is_valid: bool
    errors: list[str]
    warnings: list[str]

    @classmethod
    def success(cls) -> "ValidationResult":
        """Create successful validation result"""
        return cls(is_valid=True, errors=[], warnings=[])

    @classmethod
    def error(cls, message: str) -> "ValidationResult":
        """Create error validation result"""
        return cls(is_valid=False, errors=[message], warnings=[])

    @classmethod
    def warning(cls, message: str) -> "ValidationResult":
        """Create warning validation result"""
        return cls(is_valid=True, errors=[], warnings=[message])

    def add_error(self, message: str) -> None:
        """Add error message"""
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        """Add warning message"""
        self.warnings.append(message)

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        """Merge with another validation result"""
        return ValidationResult(
            is_valid=self.is_valid and other.is_valid,
            errors=self.errors + other.errors,
            warnings=self.warnings + other.warnings,
        )


class FormatValidator(ABC):
    """Abstract base class for format validators"""

    @abstractmethod
    def validate(self, content: str) -> ValidationResult:
        """Validate format content"""
        pass


class MarkdownTableValidator(FormatValidator):
    """Validator for Markdown table structure and syntax"""

    # Regex patterns for markdown table validation
    TABLE_HEADER_PATTERN: Pattern = re.compile(r"^\|.*\|$")
    TABLE_SEPARATOR_PATTERN: Pattern = re.compile(r"^\|(?:\s*:?-+:?\s*\|)+$")
    TABLE_ROW_PATTERN: Pattern = re.compile(r"^\|.*\|$")
    SECTION_HEADER_PATTERN: Pattern = re.compile(r"^#{1,6}\s+.+$")

    def validate(self, content: str) -> ValidationResult:
        """
        Validate markdown table structure and syntax

        Args:
            content: Markdown content to validate

        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult.success()
        lines = content.split("\n")

        # Check overall structure
        self._validate_overall_structure(lines, result)

        # Check table syntax
        self._validate_table_syntax(lines, result)

        # Check section headers
        self._validate_section_headers(lines, result)

        # Check table alignment
        self._validate_table_alignment(lines, result)

        return result

    def _validate_overall_structure(
        self, lines: list[str], result: ValidationResult
    ) -> None:
        """Validate overall markdown structure"""
        if not lines:
            result.add_error("Content is empty")
            return

        # Should start with main header
        if not lines[0].startswith("#"):
            result.add_warning("Content should start with a header")

        # Check for presence of tables
        has_tables = any(self._is_table_line(line) for line in lines)
        if not has_tables:
            result.add_warning("No tables found in markdown content")

    def _validate_table_syntax(
        self, lines: list[str], result: ValidationResult
    ) -> None:
        """Validate table syntax"""
        in_table = False
        table_start_line = -1
        expected_columns = 0

        for i, line in enumerate(lines):
            if self._is_table_line(line):
                if not in_table:
                    # Starting new table
                    in_table = True
                    table_start_line = i
                    expected_columns = self._count_table_columns(line)

                    # Check if this is a header line
                    if not self.TABLE_HEADER_PATTERN.match(line):
                        result.add_error(
                            f"Invalid table header syntax at line {i + 1}: {line}"
                        )

                else:
                    # Continuing table
                    current_columns = self._count_table_columns(line)

                    # Check for separator row
                    if self.TABLE_SEPARATOR_PATTERN.match(line):
                        if i != table_start_line + 1:
                            result.add_error(
                                f"Table separator not immediately after header at line {i + 1}"
                            )

                    # Check column count consistency
                    elif current_columns != expected_columns:
                        result.add_error(
                            f"Inconsistent column count at line {i + 1}: "
                            f"expected {expected_columns}, got {current_columns}"
                        )
            else:
                if in_table:
                    # End of table
                    in_table = False

    def _validate_section_headers(
        self, lines: list[str], result: ValidationResult
    ) -> None:
        """Validate section headers"""
        header_levels = []

        for i, line in enumerate(lines):
            if self.SECTION_HEADER_PATTERN.match(line):
                level = len(line) - len(line.lstrip("#"))
                header_levels.append((i + 1, level, line))

        # Check header hierarchy
        for i in range(1, len(header_levels)):
            prev_level = header_levels[i - 1][1]
            curr_level = header_levels[i][1]

            # Headers should not skip levels (e.g., # followed by ###)
            if curr_level > prev_level + 1:
                result.add_warning(
                    f"Header level skip at line {header_levels[i][0]}: "
                    f"level {curr_level} after level {prev_level}"
                )

    def _validate_table_alignment(
        self, lines: list[str], result: ValidationResult
    ) -> None:
        """Validate table column alignment"""
        table_groups = self._extract_table_groups(lines)

        for table_start, table_lines in table_groups:
            if len(table_lines) < 2:
                result.add_error(
                    f"Table at line {table_start + 1} has no separator row"
                )
                continue

            # Check separator row format
            separator = table_lines[1]
            if not self.TABLE_SEPARATOR_PATTERN.match(separator):
                result.add_error(
                    f"Invalid separator row at line {table_start + 2}: {separator}"
                )

    def _is_table_line(self, line: str) -> bool:
        """Check if line is part of a table"""
        stripped = line.strip()
        return stripped.startswith("|") and stripped.endswith("|")

    def _count_table_columns(self, line: str) -> int:
        """Count number of columns in table line"""
        # Count pipe characters, subtract 1 for leading/trailing pipes
        return line.count("|") - 1

    def _extract_table_groups(self, lines: list[str]) -> list[tuple[int, list[str]]]:
        """Extract groups of consecutive table lines"""
        groups = []
        current_group = []
        group_start = -1

        for i, line in enumerate(lines):
            if self._is_table_line(line):
                if not current_group:
                    group_start = i
                current_group.append(line)
            else:
                if current_group:
                    groups.append((group_start, current_group))
                    current_group = []

        # Add final group if exists
        if current_group:
            groups.append((group_start, current_group))

        return groups


class CSVFormatValidator(FormatValidator):
    """Validator for CSV format compliance"""

    def validate(self, content: str) -> ValidationResult:
        """
        Validate CSV format compliance

        Args:
            content: CSV content to validate

        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult.success()

        if not content.strip():
            result.add_error("CSV content is empty")
            return result

        try:
            # Parse CSV content
            reader = csv.reader(StringIO(content))
            rows = list(reader)

            if not rows:
                result.add_error("No rows found in CSV")
                return result

            # Validate header row
            self._validate_csv_header(rows[0], result)

            # Validate data consistency
            self._validate_csv_data_consistency(rows, result)

            # Validate required columns
            self._validate_csv_required_columns(rows[0], result)

        except csv.Error as e:
            result.add_error(f"CSV parsing error: {e}")

        return result

    def _validate_csv_header(self, header: list[str], result: ValidationResult) -> None:
        """Validate CSV header row"""
        if not header:
            result.add_error("CSV header is empty")
            return

        # Check for empty column names
        for i, col in enumerate(header):
            if not col.strip():
                result.add_error(f"Empty column name at position {i}")

        # Check for duplicate column names
        seen_columns = set()
        for i, col in enumerate(header):
            if col in seen_columns:
                result.add_error(f"Duplicate column name '{col}' at position {i}")
            seen_columns.add(col)

    def _validate_csv_data_consistency(
        self, rows: list[list[str]], result: ValidationResult
    ) -> None:
        """Validate CSV data consistency"""
        if len(rows) < 2:
            result.add_warning("CSV has header but no data rows")
            return

        header_count = len(rows[0])

        for i, row in enumerate(rows[1:], 1):
            if len(row) != header_count:
                result.add_error(
                    f"Row {i + 1} has {len(row)} columns, expected {header_count}"
                )

    def _validate_csv_required_columns(
        self, header: list[str], result: ValidationResult
    ) -> None:
        """Validate presence of required columns"""
        # Support multiple CSV format variations
        
        # Format 1: Mock analyzer format (simple)
        format1_required = {"Type", "Name", "Signature", "Visibility", "Lines"}
        
        # Format 2: New multi-language format
        format2_required = {"Type", "Name", "Start Line", "End Line", "Language", "Visibility"}
        
        # Format 3: Legacy Java format
        format3_required = {"Type", "Name"}
        
        header_set = set(header)
        
        # Check if any format is satisfied
        format1_satisfied = format1_required.issubset(header_set)
        format2_satisfied = format2_required.issubset(header_set)
        format3_satisfied = format3_required.issubset(header_set)
        
        if not (format1_satisfied or format2_satisfied or format3_satisfied):
            result.add_error(
                f"CSV does not match any known format. "
                f"Headers found: {', '.join(header)}"
            )
        
        # Just add a warning for unexpected columns, not an error
        all_known_columns = {
            "Type", "Name", "Signature", "Visibility", "Lines",
            "Start Line", "End Line", "Language", "Parameters", 
            "Return Type", "Modifiers", "Complexity", "Doc",
            "ReturnType", "Access", "Static", "Final", "Line"
        }
        unexpected_columns = header_set - all_known_columns
        
        if unexpected_columns:
            result.add_warning(f"Unexpected columns: {', '.join(unexpected_columns)}")


class JSONFormatValidator(FormatValidator):
    """Validator for JSON format compliance"""

    def __init__(self, schema: dict[str, Any] | None = None):
        """
        Initialize JSON validator

        Args:
            schema: JSON schema for validation (optional)
        """
        self.schema = schema

    def validate(self, content: str) -> ValidationResult:
        """
        Validate JSON format compliance

        Args:
            content: JSON content to validate

        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult.success()

        if not content.strip():
            result.add_error("JSON content is empty")
            return result

        try:
            # Parse JSON
            data = json.loads(content)

            # Validate against schema if provided
            if self.schema:
                self._validate_json_schema(data, result)

        except json.JSONDecodeError as e:
            result.add_error(f"JSON parsing error: {e}")

        return result

    def _validate_json_schema(self, data: Any, result: ValidationResult) -> None:
        """Validate JSON data against schema"""
        # Basic schema validation (can be extended with jsonschema library)
        if not isinstance(data, dict):
            result.add_error("JSON root must be an object")
            return

        # Check required fields if defined in schema
        if "required" in self.schema:
            for field in self.schema["required"]:
                if field not in data:
                    result.add_error(f"Missing required field: {field}")


class FormatValidatorFactory:
    """Factory for creating format validators"""

    _validators = {
        "markdown": MarkdownTableValidator,
        "csv": CSVFormatValidator,
        "json": JSONFormatValidator,
    }

    @classmethod
    def create_validator(self, format_type: str, **kwargs) -> FormatValidator:
        """
        Create format validator for specified type

        Args:
            format_type: Type of format (markdown, csv, json)
            **kwargs: Additional arguments for validator

        Returns:
            FormatValidator instance

        Raises:
            ValueError: If format type is not supported
        """
        if format_type not in self._validators:
            raise ValueError(f"Unsupported format type: {format_type}")

        validator_class = self._validators[format_type]
        return validator_class(**kwargs)

    @classmethod
    def get_supported_formats(cls) -> list[str]:
        """Get list of supported format types"""
        return list(cls._validators.keys())


def validate_format(content: str, format_type: str, **kwargs) -> ValidationResult:
    """
    Convenience function to validate format content

    Args:
        content: Content to validate
        format_type: Type of format (markdown, csv, json)
        **kwargs: Additional arguments for validator

    Returns:
        ValidationResult with validation status and messages
    """
    validator = FormatValidatorFactory.create_validator(format_type, **kwargs)
    return validator.validate(content)
