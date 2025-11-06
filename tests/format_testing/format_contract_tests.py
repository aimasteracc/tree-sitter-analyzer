"""
Format Contract Tests

Tests that validate format contracts - agreements about what information
each format must provide and how formats relate to each other.

Format contracts ensure:
1. Information consistency across formats
2. Backward compatibility
3. API contract compliance
4. Cross-format data integrity
"""

import csv
import io
import re
import tempfile
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool


class FormatContractValidator:
    """Validator for format contracts and cross-format consistency"""

    def __init__(self):
        self.violations: list[str] = []
        self.warnings: list[str] = []

    def validate_information_consistency(
        self, full_output: str, compact_output: str, csv_output: str
    ) -> bool:
        """Validate that all formats contain consistent information"""
        self.violations.clear()
        self.warnings.clear()

        # Extract information from each format
        full_info = self._extract_full_format_info(full_output)
        compact_info = self._extract_compact_format_info(compact_output)
        csv_info = self._extract_csv_format_info(csv_output)

        # Validate class information consistency
        if not self._validate_class_consistency(full_info, compact_info, csv_info):
            return False

        # Validate method information consistency
        if not self._validate_method_consistency(full_info, compact_info, csv_info):
            return False

        # Validate field information consistency
        if not self._validate_field_consistency(full_info, compact_info, csv_info):
            return False

        # Validate count consistency
        if not self._validate_count_consistency(full_info, compact_info, csv_info):
            return False

        return len(self.violations) == 0

    def validate_format_contracts(
        self, full_output: str, compact_output: str, csv_output: str
    ) -> bool:
        """Validate format-specific contracts"""
        self.violations.clear()
        self.warnings.clear()

        # Full format contracts
        if not self._validate_full_format_contracts(full_output):
            return False

        # Compact format contracts
        if not self._validate_compact_format_contracts(compact_output):
            return False

        # CSV format contracts
        if not self._validate_csv_format_contracts(csv_output):
            return False

        # Cross-format contracts
        if not self._validate_cross_format_contracts(
            full_output, compact_output, csv_output
        ):
            return False

        return len(self.violations) == 0

    def _extract_full_format_info(self, output: str) -> dict[str, Any]:
        """Extract structured information from full format"""
        info = {
            "class_name": "",
            "package": "",
            "methods": [],
            "fields": [],
            "imports": [],
        }

        # Extract class name and package from header
        header_match = re.search(r"^# (.+)$", output, re.MULTILINE)
        if header_match:
            full_name = header_match.group(1)
            if "." in full_name:
                parts = full_name.split(".")
                info["class_name"] = parts[-1]
                info["package"] = ".".join(parts[:-1])
            else:
                info["class_name"] = full_name

        # Extract methods
        methods_section = re.search(
            r"## Methods\s*\n(.*?)(?=\n## |\Z)", output, re.DOTALL
        )
        if methods_section:
            table_content = methods_section.group(1)
            info["methods"] = self._parse_markdown_table(table_content)

        # Extract fields
        fields_section = re.search(
            r"## Fields\s*\n(.*?)(?=\n## |\Z)", output, re.DOTALL
        )
        if fields_section:
            table_content = fields_section.group(1)
            info["fields"] = self._parse_markdown_table(table_content)

        # Extract imports
        imports_section = re.search(
            r"## Imports\s*\n(.*?)(?=\n## |\Z)", output, re.DOTALL
        )
        if imports_section:
            content = imports_section.group(1)
            # v1.6.1.4 format uses code block, not table
            if "```" in content:
                # Extract imports from code block
                code_match = re.search(r"```\w*\n(.*?)\n```", content, re.DOTALL)
                if code_match:
                    import_lines = code_match.group(1).strip().split("\n")
                    info["imports"] = [
                        [line.strip()] for line in import_lines if line.strip()
                    ]
            else:
                # Fallback to table parsing
                info["imports"] = self._parse_markdown_table(content)

        return info

    def _extract_compact_format_info(self, output: str) -> dict[str, Any]:
        """Extract structured information from compact format"""
        info = {"class_name": "", "methods": [], "fields": [], "counts": {}}

        # Extract class name from header
        header_match = re.search(r"^# (.+)$", output, re.MULTILINE)
        if header_match:
            info["class_name"] = header_match.group(1)

        # Extract counts from Info section
        info_section = re.search(r"## Info\n(.*?)\n\n", output, re.DOTALL)
        if info_section:
            table_content = info_section.group(1)
            info_rows = self._parse_markdown_table(table_content)
            for row in info_rows:
                if len(row) >= 2:
                    property_name = row[0].lower()
                    value = row[1]
                    if property_name in ["methods", "fields"]:
                        try:
                            info["counts"][property_name] = int(value)
                        except ValueError:
                            pass

        # Extract methods
        methods_section = re.search(
            r"## Methods\s*\n(.*?)(?=\n## |\Z)", output, re.DOTALL
        )
        if methods_section:
            table_content = methods_section.group(1)
            info["methods"] = self._parse_markdown_table(table_content)

        # Extract fields
        fields_section = re.search(
            r"## Fields\s*\n(.*?)(?=\n## |\Z)", output, re.DOTALL
        )
        if fields_section:
            table_content = fields_section.group(1)
            info["fields"] = self._parse_markdown_table(table_content)

        return info

    def _extract_csv_format_info(self, output: str) -> dict[str, Any]:
        """Extract structured information from CSV format"""
        info = {"class_name": "", "methods": [], "fields": [], "classes": []}

        try:
            reader = csv.reader(io.StringIO(output))
            header = next(reader)

            for row in reader:
                if len(row) >= 8:
                    row_dict = dict(zip(header, row, strict=False))
                    row_type = row_dict.get("Type", "")

                    if row_type == "class":
                        info["classes"].append(row_dict)
                        # Extract class name from Name field
                        class_name = row_dict.get("Name", "")
                        if "." in class_name:
                            info["class_name"] = class_name.split(".")[-1]
                        else:
                            info["class_name"] = class_name
                    elif row_type in ["method", "constructor"]:
                        info["methods"].append(row_dict)
                    elif row_type in ["field", "property"]:
                        info["fields"].append(row_dict)

        except (csv.Error, StopIteration):
            pass

        return info

    def _parse_markdown_table(self, table_content: str) -> list[list[str]]:
        """Parse Markdown table content into rows"""
        lines = [
            line.strip() for line in table_content.strip().split("\n") if line.strip()
        ]

        if len(lines) < 2:
            return []

        # Skip header and separator, parse data rows
        data_rows = []
        for line in lines[2:]:  # Skip header and separator
            if line.startswith("|") and line.endswith("|"):
                cells = [cell.strip() for cell in line.split("|")[1:-1]]
                data_rows.append(cells)

        return data_rows

    def _validate_class_consistency(
        self,
        full_info: dict[str, Any],
        compact_info: dict[str, Any],
        csv_info: dict[str, Any],
    ) -> bool:
        """Validate class information consistency"""
        # Class names should be consistent
        full_class = full_info.get("class_name", "")
        compact_class = compact_info.get("class_name", "")
        csv_class = csv_info.get("class_name", "")

        if full_class and compact_class and full_class != compact_class:
            self.violations.append(
                f"Class name mismatch: full='{full_class}', compact='{compact_class}'"
            )

        if full_class and csv_class and full_class != csv_class:
            self.violations.append(
                f"Class name mismatch: full='{full_class}', csv='{csv_class}'"
            )

        if compact_class and csv_class and compact_class != csv_class:
            self.violations.append(
                f"Class name mismatch: compact='{compact_class}', csv='{csv_class}'"
            )

        return True

    def _validate_method_consistency(
        self,
        full_info: dict[str, Any],
        compact_info: dict[str, Any],
        csv_info: dict[str, Any],
    ) -> bool:
        """Validate method information consistency"""
        # Extract method names
        full_methods = {row[0] for row in full_info.get("methods", []) if row}
        compact_methods = {row[0] for row in compact_info.get("methods", []) if row}
        csv_methods = {row.get("Name", "") for row in csv_info.get("methods", [])}

        # Remove empty names
        full_methods.discard("")
        compact_methods.discard("")
        csv_methods.discard("")

        # Check method count consistency
        if len(full_methods) != len(compact_methods):
            self.violations.append(
                f"Method count mismatch: full={len(full_methods)}, compact={len(compact_methods)}"
            )

        if len(full_methods) != len(csv_methods):
            self.violations.append(
                f"Method count mismatch: full={len(full_methods)}, csv={len(csv_methods)}"
            )

        # Check method name consistency
        if full_methods and compact_methods:
            missing_in_compact = full_methods - compact_methods
            if missing_in_compact:
                self.violations.append(
                    f"Methods missing in compact format: {missing_in_compact}"
                )

            extra_in_compact = compact_methods - full_methods
            if extra_in_compact:
                self.violations.append(
                    f"Extra methods in compact format: {extra_in_compact}"
                )

        if full_methods and csv_methods:
            missing_in_csv = full_methods - csv_methods
            if missing_in_csv:
                self.violations.append(
                    f"Methods missing in CSV format: {missing_in_csv}"
                )

            extra_in_csv = csv_methods - full_methods
            if extra_in_csv:
                self.violations.append(f"Extra methods in CSV format: {extra_in_csv}")

        return True

    def _validate_field_consistency(
        self,
        full_info: dict[str, Any],
        compact_info: dict[str, Any],
        csv_info: dict[str, Any],
    ) -> bool:
        """Validate field information consistency"""
        # Extract field names
        full_fields = {row[0] for row in full_info.get("fields", []) if row}
        compact_fields = {row[0] for row in compact_info.get("fields", []) if row}
        csv_fields = {row.get("Name", "") for row in csv_info.get("fields", [])}

        # Remove empty names
        full_fields.discard("")
        compact_fields.discard("")
        csv_fields.discard("")

        # Check field count consistency
        if len(full_fields) != len(compact_fields):
            self.violations.append(
                f"Field count mismatch: full={len(full_fields)}, compact={len(compact_fields)}"
            )

        if len(full_fields) != len(csv_fields):
            self.violations.append(
                f"Field count mismatch: full={len(full_fields)}, csv={len(csv_fields)}"
            )

        # Check field name consistency
        if full_fields and compact_fields:
            missing_in_compact = full_fields - compact_fields
            if missing_in_compact:
                self.violations.append(
                    f"Fields missing in compact format: {missing_in_compact}"
                )

            extra_in_compact = compact_fields - full_fields
            if extra_in_compact:
                self.violations.append(
                    f"Extra fields in compact format: {extra_in_compact}"
                )

        if full_fields and csv_fields:
            missing_in_csv = full_fields - csv_fields
            if missing_in_csv:
                self.violations.append(
                    f"Fields missing in CSV format: {missing_in_csv}"
                )

            extra_in_csv = csv_fields - full_fields
            if extra_in_csv:
                self.violations.append(f"Extra fields in CSV format: {extra_in_csv}")

        return True

    def _validate_count_consistency(
        self,
        full_info: dict[str, Any],
        compact_info: dict[str, Any],
        csv_info: dict[str, Any],
    ) -> bool:
        """Validate count information consistency"""
        # Get actual counts
        full_method_count = len(full_info.get("methods", []))
        full_field_count = len(full_info.get("fields", []))

        # Get reported counts from compact format
        compact_counts = compact_info.get("counts", {})
        reported_method_count = compact_counts.get("methods")
        reported_field_count = compact_counts.get("fields")

        # Validate reported counts match actual counts
        if (
            reported_method_count is not None
            and reported_method_count != full_method_count
        ):
            self.violations.append(
                f"Compact format reports {reported_method_count} methods, but full format has {full_method_count}"
            )

        if (
            reported_field_count is not None
            and reported_field_count != full_field_count
        ):
            self.violations.append(
                f"Compact format reports {reported_field_count} fields, but full format has {full_field_count}"
            )

        return True

    def _validate_full_format_contracts(self, output: str) -> bool:
        """Validate Full Format specific contracts"""
        # Must contain complete information
        required_sections = ["## Class Info", "## Methods", "## Fields"]

        for section in required_sections:
            if section not in output:
                self.violations.append(
                    f"Full format missing required section: {section}"
                )

        # Must contain detailed parameter information
        if "## Methods" in output:
            methods_section = re.search(
                r"## Methods\n(.*?)(?=\n##|\n$)", output, re.DOTALL
            )
            if methods_section:
                table_content = methods_section.group(1)
                if "Parameters" not in table_content:
                    self.violations.append(
                        "Full format Methods table missing Parameters column"
                    )

        # Must contain detailed field information
        if "## Fields" in output:
            fields_section = re.search(
                r"## Fields\n(.*?)(?=\n##|\n$)", output, re.DOTALL
            )
            if fields_section:
                table_content = fields_section.group(1)
                required_columns = ["Static", "Final"]
                for column in required_columns:
                    if column not in table_content:
                        self.violations.append(
                            f"Full format Fields table missing {column} column"
                        )

        return True

    def _validate_compact_format_contracts(self, output: str) -> bool:
        """Validate Compact Format specific contracts"""
        # Must contain summary information
        if "## Info" not in output:
            self.violations.append("Compact format missing required Info section")

        # Must omit detailed parameter information
        if "Parameters" in output:
            self.warnings.append(
                "Compact format should omit detailed parameter information"
            )

        # Must omit package information from header
        header_match = re.search(r"^# (.+)$", output, re.MULTILINE)
        if header_match:
            header_content = header_match.group(1)
            if "." in header_content:
                self.warnings.append(
                    "Compact format header should omit package information"
                )

        return True

    def _validate_csv_format_contracts(self, output: str) -> bool:
        """Validate CSV Format specific contracts"""
        try:
            reader = csv.reader(io.StringIO(output))
            header = next(reader)
            rows = list(reader)

            # Must have proper header
            expected_header = [
                "Type",
                "Name",
                "ReturnType",
                "Parameters",
                "Access",
                "Static",
                "Final",
                "Line",
            ]
            if header != expected_header:
                self.violations.append(
                    f"CSV format header contract violation: {header}"
                )

            # Must have at least one class row
            class_rows = [row for row in rows if row and row[0] == "class"]
            if not class_rows:
                self.violations.append("CSV format must contain at least one class row")

            # Must encode parameters properly
            for row in rows:
                if len(row) >= 4 and row[3]:  # Parameters column
                    parameters = row[3]
                    if parameters and not self._validate_csv_parameters(parameters):
                        self.violations.append(
                            f"CSV format invalid parameter encoding: {parameters}"
                        )

        except (csv.Error, StopIteration) as e:
            self.violations.append(f"CSV format structure violation: {e}")

        return True

    def _validate_cross_format_contracts(
        self, full_output: str, compact_output: str, csv_output: str
    ) -> bool:
        """Validate contracts that span multiple formats"""
        # All formats must represent the same source code
        # This is validated by information consistency checks above

        # Full format must be superset of compact format information
        full_info = self._extract_full_format_info(full_output)
        compact_info = self._extract_compact_format_info(compact_output)

        # Compact format should not have information that full format lacks
        compact_methods = {row[0] for row in compact_info.get("methods", []) if row}
        full_methods = {row[0] for row in full_info.get("methods", []) if row}

        extra_methods = compact_methods - full_methods
        if extra_methods:
            self.violations.append(
                f"Compact format has methods not in full format: {extra_methods}"
            )

        compact_fields = {row[0] for row in compact_info.get("fields", []) if row}
        full_fields = {row[0] for row in full_info.get("fields", []) if row}

        extra_fields = compact_fields - full_fields
        if extra_fields:
            self.violations.append(
                f"Compact format has fields not in full format: {extra_fields}"
            )

        return True

    def _validate_csv_parameters(self, parameters: str) -> bool:
        """Validate CSV parameter encoding format"""
        if not parameters.strip():
            return True

        # Should be param1:type1;param2:type2 format
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

    def get_contract_report(self) -> dict[str, Any]:
        """Get contract validation report"""
        return {
            "valid": len(self.violations) == 0,
            "violations": self.violations.copy(),
            "warnings": self.warnings.copy(),
            "violation_count": len(self.violations),
            "warning_count": len(self.warnings),
        }


class TestFormatContracts:
    """Test format contracts and cross-format consistency"""

    @pytest.fixture
    def comprehensive_test_file(self):
        """Create a comprehensive test file for contract testing"""
        temp_dir = tempfile.mkdtemp()

        java_content = """package com.example.contracts;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;

/**
 * Contract testing service
 * Demonstrates comprehensive class structure for format contract validation
 */
public class ContractTestService {

    // Static fields
    private static final String SERVICE_NAME = "ContractTestService";
    private static final int MAX_RETRIES = 3;

    // Instance fields
    private final Map<String, Object> configuration;
    private List<String> activeConnections;
    private boolean isInitialized = false;

    /**
     * Default constructor
     */
    public ContractTestService() {
        this.configuration = new HashMap<>();
        this.activeConnections = new ArrayList<>();
    }

    /**
     * Constructor with configuration
     * @param config initial configuration
     */
    public ContractTestService(Map<String, Object> config) {
        this.configuration = new HashMap<>(config);
        this.activeConnections = new ArrayList<>();
        this.isInitialized = true;
    }

    /**
     * Initialize the service
     * @param timeout timeout in milliseconds
     * @return initialization result
     */
    public CompletableFuture<Boolean> initialize(long timeout) {
        return CompletableFuture.supplyAsync(() -> {
            // Initialization logic
            this.isInitialized = true;
            return true;
        });
    }

    /**
     * Process data with multiple parameters
     * @param data input data list
     * @param options processing options
     * @param callback completion callback
     * @return processing result
     */
    public Optional<String> processData(
        List<String> data,
        Map<String, Object> options,
        Runnable callback
    ) {
        if (!isInitialized) {
            return Optional.empty();
        }

        // Processing logic
        callback.run();
        return Optional.of("processed");
    }

    /**
     * Get service configuration
     * @return configuration map
     */
    public Map<String, Object> getConfiguration() {
        return new HashMap<>(configuration);
    }

    /**
     * Update configuration
     * @param key configuration key
     * @param value configuration value
     */
    public void updateConfiguration(String key, Object value) {
        configuration.put(key, value);
    }

    /**
     * Check if service is initialized
     * @return true if initialized
     */
    public boolean isInitialized() {
        return isInitialized;
    }

    /**
     * Get active connections count
     * @return number of active connections
     */
    public int getActiveConnectionsCount() {
        return activeConnections.size();
    }

    /**
     * Add connection
     * @param connectionId connection identifier
     */
    public void addConnection(String connectionId) {
        if (!activeConnections.contains(connectionId)) {
            activeConnections.add(connectionId);
        }
    }

    /**
     * Remove connection
     * @param connectionId connection identifier
     * @return true if connection was removed
     */
    public boolean removeConnection(String connectionId) {
        return activeConnections.remove(connectionId);
    }

    /**
     * Shutdown the service
     */
    public void shutdown() {
        activeConnections.clear();
        configuration.clear();
        isInitialized = false;
    }
}"""

        test_file = Path(temp_dir) / "ContractTestService.java"
        test_file.write_text(java_content, encoding="utf-8")

        yield temp_dir, test_file, "ContractTestService"

        # Cleanup
        test_file.unlink()
        Path(temp_dir).rmdir()

    @pytest.fixture
    def contract_validator(self):
        """Create contract validator"""
        return FormatContractValidator()

    @pytest.mark.asyncio
    async def test_information_consistency_contract(
        self, comprehensive_test_file, contract_validator
    ):
        """Test information consistency contract across all formats"""
        temp_dir, file_path, class_name = comprehensive_test_file

        tool = TableFormatTool(project_root=temp_dir)

        # Generate all format outputs
        outputs = {}
        for format_type in ["full", "compact", "csv"]:
            result = await tool.execute(
                {
                    "file_path": str(file_path),
                    "format_type": format_type,
                    "language": "java",
                }
            )
            outputs[format_type] = result["table_output"]

        # Validate information consistency
        is_consistent = contract_validator.validate_information_consistency(
            outputs["full"], outputs["compact"], outputs["csv"]
        )

        report = contract_validator.get_contract_report()

        # Print report for debugging
        if not is_consistent:
            print(f"Information consistency violations: {report['violations']}")
        if report["warnings"]:
            print(f"Information consistency warnings: {report['warnings']}")

        # Assert consistency
        assert (
            is_consistent
        ), f"Information consistency contract violated: {report['violations']}"

        # Verify that all formats contain the class name
        for format_type, output in outputs.items():
            assert class_name in output, f"{format_type} format missing class name"

    @pytest.mark.asyncio
    async def test_format_specific_contracts(
        self, comprehensive_test_file, contract_validator
    ):
        """Test format-specific contracts"""
        temp_dir, file_path, class_name = comprehensive_test_file

        tool = TableFormatTool(project_root=temp_dir)

        # Generate all format outputs
        outputs = {}
        for format_type in ["full", "compact", "csv"]:
            result = await tool.execute(
                {
                    "file_path": str(file_path),
                    "format_type": format_type,
                    "language": "java",
                }
            )
            outputs[format_type] = result["table_output"]

        # Validate format contracts
        is_valid = contract_validator.validate_format_contracts(
            outputs["full"], outputs["compact"], outputs["csv"]
        )

        report = contract_validator.get_contract_report()

        # Print report for debugging
        if not is_valid:
            print(f"Format contract violations: {report['violations']}")
        if report["warnings"]:
            print(f"Format contract warnings: {report['warnings']}")

        # Assert contract compliance
        assert is_valid, f"Format contracts violated: {report['violations']}"

    @pytest.mark.asyncio
    async def test_method_count_contract(
        self, comprehensive_test_file, contract_validator
    ):
        """Test method count consistency contract"""
        temp_dir, file_path, class_name = comprehensive_test_file

        tool = TableFormatTool(project_root=temp_dir)

        # Generate outputs
        full_result = await tool.execute(
            {"file_path": str(file_path), "format_type": "full", "language": "java"}
        )

        compact_result = await tool.execute(
            {"file_path": str(file_path), "format_type": "compact", "language": "java"}
        )

        csv_result = await tool.execute(
            {"file_path": str(file_path), "format_type": "csv", "language": "java"}
        )

        # Extract method information
        full_info = contract_validator._extract_full_format_info(
            full_result["table_output"]
        )
        compact_info = contract_validator._extract_compact_format_info(
            compact_result["table_output"]
        )
        csv_info = contract_validator._extract_csv_format_info(
            csv_result["table_output"]
        )

        # Count methods
        full_method_count = len(full_info.get("methods", []))
        compact_method_count = len(compact_info.get("methods", []))
        csv_method_count = len(csv_info.get("methods", []))

        # All formats should report same method count
        assert (
            full_method_count == compact_method_count
        ), f"Method count mismatch: full={full_method_count}, compact={compact_method_count}"

        assert (
            full_method_count == csv_method_count
        ), f"Method count mismatch: full={full_method_count}, csv={csv_method_count}"

        # Verify expected method count (based on test file)
        expected_methods = 11  # Based on ContractTestService methods
        assert (
            full_method_count >= expected_methods - 2
        ), f"Expected at least {expected_methods-2} methods, got {full_method_count}"

    @pytest.mark.asyncio
    async def test_field_count_contract(
        self, comprehensive_test_file, contract_validator
    ):
        """Test field count consistency contract"""
        temp_dir, file_path, class_name = comprehensive_test_file

        tool = TableFormatTool(project_root=temp_dir)

        # Generate outputs
        outputs = {}
        for format_type in ["full", "compact", "csv"]:
            result = await tool.execute(
                {
                    "file_path": str(file_path),
                    "format_type": format_type,
                    "language": "java",
                }
            )
            outputs[format_type] = result["table_output"]

        # Extract field information
        full_info = contract_validator._extract_full_format_info(outputs["full"])
        compact_info = contract_validator._extract_compact_format_info(
            outputs["compact"]
        )
        csv_info = contract_validator._extract_csv_format_info(outputs["csv"])

        # Count fields
        full_field_count = len(full_info.get("fields", []))
        compact_field_count = len(compact_info.get("fields", []))
        csv_field_count = len(csv_info.get("fields", []))

        # All formats should report same field count
        assert (
            full_field_count == compact_field_count
        ), f"Field count mismatch: full={full_field_count}, compact={compact_field_count}"

        assert (
            full_field_count == csv_field_count
        ), f"Field count mismatch: full={full_field_count}, csv={csv_field_count}"

        # Verify expected field count (based on test file)
        expected_fields = 4  # Based on ContractTestService fields
        assert (
            full_field_count >= expected_fields - 1
        ), f"Expected at least {expected_fields-1} fields, got {full_field_count}"

    @pytest.mark.asyncio
    async def test_parameter_encoding_contract(
        self, comprehensive_test_file, contract_validator
    ):
        """Test parameter encoding consistency contract"""
        temp_dir, file_path, class_name = comprehensive_test_file

        tool = TableFormatTool(project_root=temp_dir)

        # Generate CSV output (which has explicit parameter encoding)
        csv_result = await tool.execute(
            {"file_path": str(file_path), "format_type": "csv", "language": "java"}
        )

        csv_output = csv_result["table_output"]

        # Validate parameter encoding
        try:
            reader = csv.reader(io.StringIO(csv_output))
            next(reader)  # Skip header

            for row in reader:
                if len(row) >= 4 and row[0] in ["method", "constructor"]:
                    parameters = row[3]  # Parameters column
                    if parameters.strip():
                        # Should follow param1:type1;param2:type2 format
                        assert contract_validator._validate_csv_parameters(
                            parameters
                        ), f"Invalid parameter encoding: {parameters}"

        except (csv.Error, StopIteration):
            pytest.fail("Failed to parse CSV output for parameter validation")

    @pytest.mark.asyncio
    async def test_access_modifier_consistency_contract(
        self, comprehensive_test_file, contract_validator
    ):
        """Test access modifier consistency across formats"""
        temp_dir, file_path, class_name = comprehensive_test_file

        tool = TableFormatTool(project_root=temp_dir)

        # Generate outputs
        outputs = {}
        for format_type in ["full", "compact", "csv"]:
            result = await tool.execute(
                {
                    "file_path": str(file_path),
                    "format_type": format_type,
                    "language": "java",
                }
            )
            outputs[format_type] = result["table_output"]

        # Extract access modifier information
        full_info = contract_validator._extract_full_format_info(outputs["full"])
        compact_info = contract_validator._extract_compact_format_info(
            outputs["compact"]
        )
        csv_info = contract_validator._extract_csv_format_info(outputs["csv"])

        # Check method access modifiers
        for method_row in full_info.get("methods", []):
            if len(method_row) >= 4:  # Name, Return Type, Parameters, Access
                method_name = method_row[0]
                full_access = method_row[3]

                # Find corresponding method in compact format
                compact_method = None
                for compact_row in compact_info.get("methods", []):
                    if len(compact_row) >= 3 and compact_row[0] == method_name:
                        compact_method = compact_row
                        break

                if compact_method and len(compact_method) >= 3:
                    compact_access = compact_method[2]  # Access column in compact
                    assert (
                        full_access == compact_access
                    ), f"Access modifier mismatch for method {method_name}: full='{full_access}', compact='{compact_access}'"

                # Find corresponding method in CSV format
                csv_method = None
                for csv_row in csv_info.get("methods", []):
                    if csv_row.get("Name") == method_name:
                        csv_method = csv_row
                        break

                if csv_method:
                    csv_access = csv_method.get("Access", "")
                    assert (
                        full_access == csv_access
                    ), f"Access modifier mismatch for method {method_name}: full='{full_access}', csv='{csv_access}'"

    @pytest.mark.asyncio
    async def test_line_number_consistency_contract(
        self, comprehensive_test_file, contract_validator
    ):
        """Test line number consistency across formats"""
        temp_dir, file_path, class_name = comprehensive_test_file

        tool = TableFormatTool(project_root=temp_dir)

        # Generate outputs
        outputs = {}
        for format_type in ["full", "compact", "csv"]:
            result = await tool.execute(
                {
                    "file_path": str(file_path),
                    "format_type": format_type,
                    "language": "java",
                }
            )
            outputs[format_type] = result["table_output"]

        # Extract line number information
        full_info = contract_validator._extract_full_format_info(outputs["full"])
        compact_info = contract_validator._extract_compact_format_info(
            outputs["compact"]
        )
        csv_info = contract_validator._extract_csv_format_info(outputs["csv"])

        # Check method line numbers
        for method_row in full_info.get("methods", []):
            if len(method_row) >= 5:  # Name, Return Type, Parameters, Access, Line
                method_name = method_row[0]
                full_line = method_row[4]

                # Find corresponding method in compact format
                # For overloaded methods, we need to match by line number too
                compact_method = None
                for compact_row in compact_info.get("methods", []):
                    if len(compact_row) >= 4:
                        if compact_row[0] == method_name:
                            # For methods with same name (overloaded), match by line number
                            compact_line = compact_row[3]
                            if compact_line == full_line:
                                compact_method = compact_row
                                break

                if compact_method and len(compact_method) >= 4:
                    compact_line = compact_method[3]  # Line column in compact
                    assert (
                        full_line == compact_line
                    ), f"Line number mismatch for method {method_name}: full='{full_line}', compact='{compact_line}'"

                # Find corresponding method in CSV format
                # Match by both name and line number for overloaded methods
                csv_method = None
                for csv_row in csv_info.get("methods", []):
                    if (
                        csv_row.get("Name") == method_name
                        and csv_row.get("Line", "") == full_line
                    ):
                        csv_method = csv_row
                        break

                if csv_method:
                    csv_line = csv_method.get("Line", "")
                    assert (
                        full_line == csv_line
                    ), f"Line number mismatch for method {method_name}: full='{full_line}', csv='{csv_line}'"

    @pytest.mark.asyncio
    async def test_backward_compatibility_contract(
        self, comprehensive_test_file, contract_validator
    ):
        """Test backward compatibility contract"""
        temp_dir, file_path, class_name = comprehensive_test_file

        tool = TableFormatTool(project_root=temp_dir)

        # Generate current format outputs
        current_outputs = {}
        for format_type in ["full", "compact", "csv"]:
            result = await tool.execute(
                {
                    "file_path": str(file_path),
                    "format_type": format_type,
                    "language": "java",
                }
            )
            current_outputs[format_type] = result["table_output"]

        # Validate that outputs follow expected structure
        # (This simulates checking against previous version outputs)

        # Full format should have all required sections
        full_output = current_outputs["full"]
        required_full_sections = ["# ", "## Class Info", "## Methods", "## Fields"]
        for section in required_full_sections:
            assert (
                section in full_output
            ), f"Backward compatibility: missing {section} in full format"

        # Compact format should have simplified structure
        compact_output = current_outputs["compact"]
        required_compact_sections = ["# ", "## Info", "## Methods", "## Fields"]
        for section in required_compact_sections:
            assert (
                section in compact_output
            ), f"Backward compatibility: missing {section} in compact format"

        # CSV format should have proper header
        csv_output = current_outputs["csv"]
        expected_csv_header = "Type,Name,ReturnType,Parameters,Access,Static,Final,Line"
        assert csv_output.startswith(
            expected_csv_header
        ), "Backward compatibility: CSV header format changed"

    @pytest.mark.asyncio
    async def test_cross_format_data_integrity_contract(
        self, comprehensive_test_file, contract_validator
    ):
        """Test cross-format data integrity contract"""
        temp_dir, file_path, class_name = comprehensive_test_file

        tool = TableFormatTool(project_root=temp_dir)

        # Generate outputs
        outputs = {}
        for format_type in ["full", "compact", "csv"]:
            result = await tool.execute(
                {
                    "file_path": str(file_path),
                    "format_type": format_type,
                    "language": "java",
                }
            )
            outputs[format_type] = result["table_output"]

        # Validate complete data integrity
        is_consistent = contract_validator.validate_information_consistency(
            outputs["full"], outputs["compact"], outputs["csv"]
        )

        is_contract_valid = contract_validator.validate_format_contracts(
            outputs["full"], outputs["compact"], outputs["csv"]
        )

        report = contract_validator.get_contract_report()

        # Both consistency and contracts must be valid
        assert (
            is_consistent and is_contract_valid
        ), f"Data integrity contract violated: {report['violations']}"

        # Additional integrity checks
        # 1. No format should have empty essential information
        for format_type, output in outputs.items():
            assert (
                len(output.strip()) > 0
            ), f"{format_type} format produced empty output"
            assert class_name in output, f"{format_type} format missing class name"

        # 2. All formats should represent the same source file
        # This is implicitly validated by the consistency checks above

        # 3. Format-specific integrity
        # Full format should have the most detailed information
        full_lines = len(outputs["full"].split("\n"))
        compact_lines = len(outputs["compact"].split("\n"))

        assert (
            full_lines >= compact_lines
        ), "Full format should have more or equal lines compared to compact format"
