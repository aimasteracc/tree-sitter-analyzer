"""
Format Specification Compliance Tests

Tests that validate output compliance with the formal format specifications
defined in docs/format_specifications.md
"""

import csv
import io
import re
import tempfile
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool


class FormatSpecificationValidator:
    """Validator for format specification compliance"""

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate_full_format_specification(self, output: str, class_name: str) -> bool:
        """Validate Full Format specification compliance"""
        self.errors.clear()
        self.warnings.clear()

        lines = output.split("\n")

        # Check header format
        if not self._validate_full_format_header(lines, class_name):
            return False

        # Check required sections
        if not self._validate_full_format_sections(lines):
            return False

        # Check table structures
        if not self._validate_full_format_tables(lines):
            return False

        # Check encoding and formatting
        if not self._validate_common_formatting(output):
            return False

        return len(self.errors) == 0

    def validate_compact_format_specification(
        self, output: str, class_name: str
    ) -> bool:
        """Validate Compact Format specification compliance"""
        self.errors.clear()
        self.warnings.clear()

        lines = output.split("\n")

        # Check header format (should be just class name)
        if not self._validate_compact_format_header(lines, class_name):
            return False

        # Check required sections
        if not self._validate_compact_format_sections(lines):
            return False

        # Check table structures
        if not self._validate_compact_format_tables(lines):
            return False

        # Check encoding and formatting
        if not self._validate_common_formatting(output):
            return False

        return len(self.errors) == 0

    def validate_csv_format_specification(self, output: str) -> bool:
        """Validate CSV Format specification compliance"""
        self.errors.clear()
        self.warnings.clear()

        # Check CSV structure
        if not self._validate_csv_structure(output):
            return False

        # Check header compliance
        if not self._validate_csv_header(output):
            return False

        # Check data rows
        if not self._validate_csv_data_rows(output):
            return False

        # Check encoding and formatting
        if not self._validate_common_formatting(output):
            return False

        return len(self.errors) == 0

    def _validate_full_format_header(self, lines: list[str], class_name: str) -> bool:
        """Validate Full Format header: # {package}.{ClassName}"""
        if not lines:
            self.errors.append("Empty output")
            return False

        header_line = lines[0].strip()

        # Must start with #
        if not header_line.startswith("# "):
            self.errors.append(f"Header must start with '# ', got: {header_line}")
            return False

        # Must contain class name
        header_content = header_line[2:]  # Remove '# '
        if class_name not in header_content:
            self.errors.append(
                f"Header must contain class name '{class_name}', got: {header_content}"
            )
            return False

        # Should contain package (dot notation)
        if "." not in header_content:
            self.warnings.append(
                f"Header should contain package information: {header_content}"
            )

        return True

    def _validate_compact_format_header(
        self, lines: list[str], class_name: str
    ) -> bool:
        """Validate Compact Format header: # {ClassName}"""
        if not lines:
            self.errors.append("Empty output")
            return False

        header_line = lines[0].strip()

        # Must start with #
        if not header_line.startswith("# "):
            self.errors.append(f"Header must start with '# ', got: {header_line}")
            return False

        # Should be just class name (no package)
        header_content = header_line[2:]  # Remove '# '
        if header_content != class_name:
            # Allow some flexibility for simple class names
            if class_name not in header_content:
                self.errors.append(
                    f"Header should contain class name '{class_name}', got: {header_content}"
                )
                return False

            # Warn if package is included (should be omitted in compact format)
            if "." in header_content:
                self.warnings.append(
                    f"Compact format header should omit package: {header_content}"
                )

        return True

    def _validate_full_format_sections(self, lines: list[str]) -> bool:
        """Validate required sections for Full Format"""
        content = "\n".join(lines)

        required_sections = ["## Class Info", "## Methods", "## Fields"]

        for section in required_sections:
            if section not in content:
                self.errors.append(f"Missing required section: {section}")

        # Imports section is optional but recommended
        if "## Imports" not in content:
            self.warnings.append("Missing optional section: ## Imports")

        return len([e for e in self.errors if "Missing required section" in e]) == 0

    def _validate_compact_format_sections(self, lines: list[str]) -> bool:
        """Validate required sections for Compact Format"""
        content = "\n".join(lines)

        required_sections = ["## Info", "## Methods", "## Fields"]

        for section in required_sections:
            if section not in content:
                self.errors.append(f"Missing required section: {section}")

        return len([e for e in self.errors if "Missing required section" in e]) == 0

    def _validate_full_format_tables(self, lines: list[str]) -> bool:
        """Validate table structures for Full Format"""
        content = "\n".join(lines)

        # Class Info table validation
        class_info_match = re.search(r"## Class Info\n(.*?)\n\n", content, re.DOTALL)
        if class_info_match:
            table_content = class_info_match.group(1)
            if not self._validate_markdown_table(table_content, ["Property", "Value"]):
                self.errors.append("Invalid Class Info table structure")

        # Methods table validation
        methods_match = re.search(r"## Methods\n(.*?)(?=\n##|\n$)", content, re.DOTALL)
        if methods_match:
            table_content = methods_match.group(1)
            expected_headers = ["Name", "Return Type", "Parameters", "Access", "Line"]
            if not self._validate_markdown_table(table_content, expected_headers):
                self.errors.append("Invalid Methods table structure")

        # Fields table validation
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

    def _validate_compact_format_tables(self, lines: list[str]) -> bool:
        """Validate table structures for Compact Format"""
        content = "\n".join(lines)

        # Info table validation
        info_match = re.search(r"## Info\n(.*?)\n\n", content, re.DOTALL)
        if info_match:
            table_content = info_match.group(1)
            if not self._validate_markdown_table(table_content, ["Property", "Value"]):
                self.errors.append("Invalid Info table structure")

        # Methods table validation (simplified)
        methods_match = re.search(r"## Methods\n(.*?)(?=\n##|\n$)", content, re.DOTALL)
        if methods_match:
            table_content = methods_match.group(1)
            expected_headers = ["Name", "Return Type", "Access", "Line"]
            if not self._validate_markdown_table(table_content, expected_headers):
                self.errors.append("Invalid Methods table structure")

        # Fields table validation (simplified)
        fields_match = re.search(r"## Fields\n(.*?)(?=\n##|\n$)", content, re.DOTALL)
        if fields_match:
            table_content = fields_match.group(1)
            expected_headers = ["Name", "Type", "Access", "Line"]
            if not self._validate_markdown_table(table_content, expected_headers):
                self.errors.append("Invalid Fields table structure")

        return (
            len([e for e in self.errors if "Invalid" in e and "table structure" in e])
            == 0
        )

    def _validate_markdown_table(
        self, table_content: str, expected_headers: list[str]
    ) -> bool:
        """Validate Markdown table structure"""
        lines = [
            line.strip() for line in table_content.strip().split("\n") if line.strip()
        ]

        if len(lines) < 2:
            return False

        # Check header row
        header_line = lines[0]
        if not header_line.startswith("|") or not header_line.endswith("|"):
            return False

        headers = [h.strip() for h in header_line.split("|")[1:-1]]

        # Check if all expected headers are present
        for expected_header in expected_headers:
            if expected_header not in headers:
                return False

        # Check separator row
        separator_line = lines[1]
        if not re.match(r"^\|[\s\-\|]+\|$", separator_line):
            return False

        # Check data rows format
        for line in lines[2:]:
            if not line.startswith("|") or not line.endswith("|"):
                return False

            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) != len(headers):
                return False

        return True

    def _validate_csv_structure(self, output: str) -> bool:
        """Validate CSV structure"""
        try:
            # Parse CSV
            reader = csv.reader(io.StringIO(output))
            rows = list(reader)

            if len(rows) < 1:
                self.errors.append("CSV must have at least header row")
                return False

            # Check that all rows have same number of columns
            header_cols = len(rows[0])
            for i, row in enumerate(rows[1:], 1):
                if len(row) != header_cols:
                    self.errors.append(
                        f"Row {i} has {len(row)} columns, expected {header_cols}"
                    )

            return True

        except csv.Error as e:
            self.errors.append(f"Invalid CSV format: {e}")
            return False

    def _validate_csv_header(self, output: str) -> bool:
        """Validate CSV header compliance"""
        try:
            reader = csv.reader(io.StringIO(output))
            header = next(reader)

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

            if header != expected_headers:
                self.errors.append(
                    f"CSV header mismatch. Expected: {expected_headers}, Got: {header}"
                )
                return False

            return True

        except (csv.Error, StopIteration) as e:
            self.errors.append(f"Cannot read CSV header: {e}")
            return False

    def _validate_csv_data_rows(self, output: str) -> bool:
        """Validate CSV data rows"""
        try:
            reader = csv.reader(io.StringIO(output))
            header = next(reader)  # Skip header

            for i, row in enumerate(reader, 1):
                if not self._validate_csv_row(row, i):
                    return False

            return True

        except (csv.Error, StopIteration) as e:
            self.errors.append(f"Cannot read CSV data: {e}")
            return False

    def _validate_csv_row(self, row: list[str], row_num: int) -> bool:
        """Validate individual CSV row"""
        if len(row) != 8:
            self.errors.append(f"Row {row_num} has {len(row)} columns, expected 8")
            return False

        type_val, name, return_type, parameters, access, static, final, line = row

        # Validate Type field
        valid_types = [
            "class",
            "interface",
            "enum",
            "method",
            "constructor",
            "field",
            "property",
        ]
        if type_val not in valid_types:
            self.errors.append(
                f"Row {row_num}: Invalid type '{type_val}', must be one of {valid_types}"
            )

        # Validate Name field
        if not name.strip():
            self.errors.append(f"Row {row_num}: Name cannot be empty")

        # Validate boolean fields
        for field_name, field_value in [("Static", static), ("Final", final)]:
            if field_value not in ["true", "false", ""]:
                self.errors.append(
                    f"Row {row_num}: {field_name} must be 'true', 'false', or empty, got '{field_value}'"
                )

        # Validate Line field
        if line.strip():
            try:
                line_num = int(line)
                if line_num < 1:
                    self.errors.append(
                        f"Row {row_num}: Line number must be positive, got {line_num}"
                    )
            except ValueError:
                self.errors.append(
                    f"Row {row_num}: Line must be a number, got '{line}'"
                )

        # Validate Parameters format
        if parameters.strip():
            if not self._validate_parameters_format(parameters):
                self.errors.append(
                    f"Row {row_num}: Invalid parameters format '{parameters}'"
                )

        return True

    def _validate_parameters_format(self, parameters: str) -> bool:
        """Validate parameters format: param1:type1;param2:type2"""
        if not parameters.strip():
            return True

        # Split by semicolon
        params = parameters.split(";")

        for param in params:
            param = param.strip()
            if ":" not in param:
                return False

            parts = param.split(":")
            if len(parts) != 2:
                return False

            name, type_name = parts
            if not name.strip() or not type_name.strip():
                return False

        return True

    def _validate_common_formatting(self, output: str) -> bool:
        """Validate common formatting requirements"""
        # Check encoding (should be UTF-8 compatible)
        try:
            output.encode("utf-8")
        except UnicodeEncodeError:
            self.errors.append("Output contains non-UTF-8 characters")
            return False

        # Check line endings (should be LF)
        if "\r\n" in output:
            self.warnings.append("Output contains CRLF line endings, should use LF")

        # Check line length (max 1000 characters per line)
        lines = output.split("\n")
        for i, line in enumerate(lines, 1):
            if len(line) > 1000:
                self.errors.append(
                    f"Line {i} exceeds 1000 character limit: {len(line)} characters"
                )

        # Check for unnecessary empty lines
        if output.endswith("\n\n\n"):
            self.warnings.append("Output has excessive trailing empty lines")

        return len(self.errors) == 0

    def get_validation_report(self) -> dict[str, Any]:
        """Get validation report"""
        return {
            "valid": len(self.errors) == 0,
            "errors": self.errors.copy(),
            "warnings": self.warnings.copy(),
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
        }


class TestFormatSpecificationCompliance:
    """Test format specification compliance"""

    @pytest.fixture
    def test_java_file(self):
        """Create a comprehensive Java test file"""
        temp_dir = tempfile.mkdtemp()

        java_content = """package com.example.analytics;

import java.util.List;
import java.util.Map;
import java.util.HashMap;
import java.util.concurrent.ConcurrentHashMap;
import static java.util.Collections.emptyList;

/**
 * Analytics service for processing user data
 * Provides comprehensive analytics functionality
 */
public class AnalyticsService {

    private static final Logger logger = LoggerFactory.getLogger(AnalyticsService.class);
    private final Map<String, Object> cache = new ConcurrentHashMap<>();
    private UserRepository userRepository;
    private boolean enabled = true;

    /**
     * Constructor with repository injection
     * @param userRepository the user repository
     */
    public AnalyticsService(UserRepository userRepository) {
        this.userRepository = userRepository;
        logger.info("AnalyticsService initialized");
    }

    /**
     * Process user analytics data
     * @param userId User ID to process
     * @param metrics List of metrics to calculate
     * @return Analytics result
     * @throws SQLException if database error occurs
     */
    public AnalyticsResult processUserAnalytics(Long userId, List<String> metrics) throws SQLException {
        if (userId == null) {
            throw new IllegalArgumentException("User ID cannot be null");
        }

        User user = userRepository.findById(userId);
        Map<String, Double> results = calculateMetrics(user, metrics);

        return new AnalyticsResult(userId, results);
    }

    /**
     * Calculate metrics for user
     * @param user the user
     * @param metrics list of metrics
     * @return calculated results
     */
    private Map<String, Double> calculateMetrics(User user, List<String> metrics) {
        Map<String, Double> results = new HashMap<>();

        for (String metric : metrics) {
            Double value = calculateSingleMetric(user, metric);
            if (value != null) {
                results.put(metric, value);
            }
        }

        return results;
    }

    /**
     * Calculate single metric
     * @param user the user
     * @param metric metric name
     * @return calculated value
     */
    private Double calculateSingleMetric(User user, String metric) {
        String cacheKey = user.getId() + ":" + metric;

        if (cache.containsKey(cacheKey)) {
            return (Double) cache.get(cacheKey);
        }

        Double result = performCalculation(user, metric);

        if (result != null) {
            cache.put(cacheKey, result);
        }

        return result;
    }

    /**
     * Perform actual calculation
     * @param user the user
     * @param metric metric name
     * @return calculated value
     */
    private Double performCalculation(User user, String metric) {
        switch (metric.toLowerCase()) {
            case "engagement":
                return user.getLoginCount() * 0.1;
            case "retention":
                return Math.max(0.0, 1.0 - (user.getDaysSinceLastLogin() / 30.0));
            default:
                return null;
        }
    }

    /**
     * Clear analytics cache
     */
    public void clearCache() {
        cache.clear();
        logger.info("Analytics cache cleared");
    }

    /**
     * Check if service is enabled
     * @return true if enabled
     */
    public boolean isEnabled() {
        return enabled;
    }

    /**
     * Set service enabled state
     * @param enabled new enabled state
     */
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
        logger.info("AnalyticsService enabled: " + enabled);
    }
}"""

        test_file = Path(temp_dir) / "AnalyticsService.java"
        test_file.write_text(java_content, encoding="utf-8")

        yield temp_dir, test_file, "AnalyticsService"

        # Cleanup
        test_file.unlink()
        Path(temp_dir).rmdir()

    @pytest.fixture
    def validator(self):
        """Create specification validator"""
        return FormatSpecificationValidator()

    @pytest.mark.asyncio
    async def test_full_format_specification_compliance(
        self, test_java_file, validator
    ):
        """Test Full Format specification compliance"""
        temp_dir, file_path, class_name = test_java_file

        # Generate full format output
        tool = TableFormatTool(project_root=temp_dir)
        result = await tool.execute(
            {"file_path": str(file_path), "format_type": "full", "language": "java"}
        )

        output = result["table_output"]

        # Validate specification compliance
        is_valid = validator.validate_full_format_specification(output, class_name)
        report = validator.get_validation_report()

        # Print report for debugging
        if not is_valid:
            print(f"Full format validation errors: {report['errors']}")
        if report["warnings"]:
            print(f"Full format validation warnings: {report['warnings']}")

        # Assert compliance
        assert (
            is_valid
        ), f"Full format specification compliance failed: {report['errors']}"

        # Additional checks
        assert "# com.example.analytics.AnalyticsService" in output
        assert "## Class Info" in output
        assert "## Methods" in output
        assert "## Fields" in output
        assert "| Name | Return Type | Parameters | Access | Line |" in output

    @pytest.mark.asyncio
    async def test_compact_format_specification_compliance(
        self, test_java_file, validator
    ):
        """Test Compact Format specification compliance"""
        temp_dir, file_path, class_name = test_java_file

        # Generate compact format output
        tool = TableFormatTool(project_root=temp_dir)
        result = await tool.execute(
            {"file_path": str(file_path), "format_type": "compact", "language": "java"}
        )

        output = result["table_output"]

        # Validate specification compliance
        is_valid = validator.validate_compact_format_specification(output, class_name)
        report = validator.get_validation_report()

        # Print report for debugging
        if not is_valid:
            print(f"Compact format validation errors: {report['errors']}")
        if report["warnings"]:
            print(f"Compact format validation warnings: {report['warnings']}")

        # Assert compliance
        assert (
            is_valid
        ), f"Compact format specification compliance failed: {report['errors']}"

        # Additional checks
        assert f"# {class_name}" in output
        assert "## Info" in output
        assert "## Methods" in output
        assert "## Fields" in output
        assert "| Name | Return Type | Access | Line |" in output

    @pytest.mark.asyncio
    async def test_csv_format_specification_compliance(self, test_java_file, validator):
        """Test CSV Format specification compliance"""
        temp_dir, file_path, class_name = test_java_file

        # Generate CSV format output
        tool = TableFormatTool(project_root=temp_dir)
        result = await tool.execute(
            {"file_path": str(file_path), "format_type": "csv", "language": "java"}
        )

        output = result["table_output"]

        # Validate specification compliance
        is_valid = validator.validate_csv_format_specification(output)
        report = validator.get_validation_report()

        # Print report for debugging
        if not is_valid:
            print(f"CSV format validation errors: {report['errors']}")
        if report["warnings"]:
            print(f"CSV format validation warnings: {report['warnings']}")

        # Assert compliance
        assert (
            is_valid
        ), f"CSV format specification compliance failed: {report['errors']}"

        # Additional checks
        lines = output.strip().split("\n")
        assert len(lines) >= 2, "CSV must have header and at least one data row"

        # Check header
        header = lines[0]
        expected_header = "Type,Name,ReturnType,Parameters,Access,Static,Final,Line"
        assert header == expected_header, f"CSV header mismatch: {header}"

        # Check that we have class, method, and field rows
        has_class = any("class," in line for line in lines[1:])
        has_method = any("method," in line for line in lines[1:])
        has_field = any("field," in line for line in lines[1:])

        assert has_class, "CSV should contain class row"
        assert has_method, "CSV should contain method rows"
        assert has_field, "CSV should contain field rows"

    @pytest.mark.asyncio
    async def test_specification_compliance_across_formats(
        self, test_java_file, validator
    ):
        """Test specification compliance across all formats"""
        temp_dir, file_path, class_name = test_java_file

        tool = TableFormatTool(project_root=temp_dir)

        # Test all formats
        formats = ["full", "compact", "csv"]
        results = {}

        for format_type in formats:
            result = await tool.execute(
                {
                    "file_path": str(file_path),
                    "format_type": format_type,
                    "language": "java",
                }
            )

            output = result["table_output"]
            results[format_type] = output

            # Validate each format
            if format_type == "full":
                is_valid = validator.validate_full_format_specification(
                    output, class_name
                )
            elif format_type == "compact":
                is_valid = validator.validate_compact_format_specification(
                    output, class_name
                )
            elif format_type == "csv":
                is_valid = validator.validate_csv_format_specification(output)

            report = validator.get_validation_report()

            assert is_valid, f"{format_type} format specification compliance failed: {report['errors']}"

        # Verify that all formats contain the same basic information
        # (though in different structures)
        for format_type, output in results.items():
            assert class_name in output, f"{format_type} format missing class name"

            # All should contain method information
            if format_type == "csv":
                assert (
                    "method," in output
                ), f"{format_type} format missing method information"
            else:
                assert (
                    "processUserAnalytics" in output
                ), f"{format_type} format missing method information"

    @pytest.mark.asyncio
    async def test_specification_error_handling(self, validator):
        """Test specification validation error handling"""
        # Test invalid full format
        invalid_full = """# InvalidClass

        This is not a valid format
        """

        is_valid = validator.validate_full_format_specification(
            invalid_full, "InvalidClass"
        )
        assert not is_valid

        report = validator.get_validation_report()
        assert len(report["errors"]) > 0
        assert any("Missing required section" in error for error in report["errors"])

        # Test invalid CSV format
        invalid_csv = """Invalid,CSV,Header
        data,without,proper,structure
        """

        is_valid = validator.validate_csv_format_specification(invalid_csv)
        assert not is_valid

        report = validator.get_validation_report()
        assert len(report["errors"]) > 0
        assert any("CSV header mismatch" in error for error in report["errors"])

    @pytest.mark.asyncio
    async def test_specification_edge_cases(self, validator):
        """Test specification validation with edge cases"""
        # Test empty output
        is_valid = validator.validate_full_format_specification("", "TestClass")
        assert not is_valid

        report = validator.get_validation_report()
        assert "Empty output" in report["errors"]

        # Test minimal valid full format
        minimal_full = """# TestClass

## Class Info
| Property | Value |
|----------|-------|
| Name | TestClass |

## Methods
| Name | Return Type | Parameters | Access | Line |
|------|-------------|------------|--------|------|

## Fields
| Name | Type | Access | Static | Final | Line |
|------|------|--------|--------|-------|------|
"""

        is_valid = validator.validate_full_format_specification(
            minimal_full, "TestClass"
        )
        assert (
            is_valid
        ), f"Minimal valid format failed: {validator.get_validation_report()['errors']}"

        # Test minimal valid CSV
        minimal_csv = """Type,Name,ReturnType,Parameters,Access,Static,Final,Line
class,TestClass,,,public,false,false,1
"""

        is_valid = validator.validate_csv_format_specification(minimal_csv)
        assert (
            is_valid
        ), f"Minimal valid CSV failed: {validator.get_validation_report()['errors']}"
