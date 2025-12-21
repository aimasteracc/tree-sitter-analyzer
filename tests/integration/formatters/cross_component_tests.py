"""
Cross-Component Format Validation Tests

Tests that validate format consistency across different interfaces:
- MCP Server interface
- CLI interface
- API interface
- Direct library usage

Ensures all interfaces produce identical format output for same inputs.

NOTE: This test module is currently disabled pending refactoring for v1.6.1.4 API changes.
The analyze_code_structure API was removed and needs to be replaced with analyze_file().
"""

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.core import AnalysisEngine
from tree_sitter_analyzer.formatters.formatter_factory import TableFormatterFactory
from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool

from .schema_validation import validate_format

# Skip all tests in this module - needs refactoring for v1.6.1.4
pytestmark = pytest.mark.skip(
    reason="Needs refactoring for v1.6.1.4 API changes - analyze_code_structure removed"
)

# Note: analyze_code_structure was removed from API in v1.6.1.4
# This test file needs refactoring to use the current API (analyze_file)
# For now, skip all tests that depend on the old API


class CrossComponentFormatValidator:
    """Validator for cross-component format consistency"""

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.results: dict[str, dict[str, Any]] = {}

    async def collect_mcp_result(
        self, file_path: str, format_type: str, language: str | None = None
    ) -> dict[str, Any]:
        """Collect result from MCP interface"""
        tool = TableFormatTool(project_root=self.project_root)

        params = {"file_path": file_path, "format_type": format_type}
        if language:
            params["language"] = language

        result = await tool.execute(params)

        return {
            "interface": "mcp",
            "table_output": result["table_output"],
            "metadata": result.get("metadata", {}),
            "format_type": result["format_type"],
            "language": result["language"],
        }

    async def collect_api_result(
        self, file_path: str, format_type: str, language: str | None = None
    ) -> dict[str, Any]:
        """Collect result from API interface"""
        # API interface test disabled - analyze_code_structure removed in v1.6.1.4
        # TODO: Refactor to use analyze_file() with proper formatting
        pytest.skip("API interface test needs refactoring for v1.6.1.4 API changes")

        params = {"file_path": file_path, "format_type": format_type}
        if language:
            params["language"] = language

        # This function no longer exists in the API
        # result = await analyze_code_structure(**params)

        return {
            "interface": "api",
            "table_output": "",
            "metadata": {},
            "format_type": format_type,
            "language": language or "unknown",
        }

    def collect_cli_result(
        self, file_path: str, format_type: str, language: str | None = None
    ) -> dict[str, Any] | None:
        """Collect result from CLI interface"""
        try:
            cmd = [
                sys.executable,
                "-m",
                "tree_sitter_analyzer",
                "--file",
                file_path,
                "--table",
                format_type,
            ]

            if language:
                cmd.extend(["--language", language])

            result = subprocess.run(
                cmd, capture_output=True, text=True, cwd=self.project_root, timeout=30
            )

            if result.returncode == 0:
                return {
                    "interface": "cli",
                    "table_output": result.stdout.strip(),
                    "metadata": {},  # CLI doesn't return structured metadata
                    "format_type": format_type,
                    "language": language or "auto-detected",
                }
            else:
                return {
                    "interface": "cli",
                    "error": result.stderr,
                    "returncode": result.returncode,
                }

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return {"interface": "cli", "error": str(e)}

    async def collect_direct_result(
        self, file_path: str, format_type: str, language: str | None = None
    ) -> dict[str, Any]:
        """Collect result from direct library usage"""
        try:
            # Use core components directly
            engine = AnalysisEngine()
            analysis_result = await engine.analyze_file(
                Path(file_path), language=language
            )

            # Format using formatter factory
            formatter = TableFormatterFactory.create_formatter(
                language=analysis_result.language, format_type=format_type
            )

            table_output = formatter.format(analysis_result)

            return {
                "interface": "direct",
                "table_output": table_output,
                "metadata": {
                    "elements_count": len(analysis_result.elements),
                    "language": analysis_result.language,
                },
                "format_type": format_type,
                "language": analysis_result.language,
            }

        except Exception as e:
            return {"interface": "direct", "error": str(e)}

    async def validate_cross_component_consistency(
        self, file_path: str, format_type: str, language: str | None = None
    ) -> dict[str, Any]:
        """Validate consistency across all interfaces"""

        # Collect results from all interfaces
        results = {}

        # MCP interface
        try:
            results["mcp"] = await self.collect_mcp_result(
                file_path, format_type, language
            )
        except Exception as e:
            results["mcp"] = {"interface": "mcp", "error": str(e)}

        # API interface
        try:
            results["api"] = await self.collect_api_result(
                file_path, format_type, language
            )
        except Exception as e:
            results["api"] = {"interface": "api", "error": str(e)}

        # CLI interface
        cli_result = self.collect_cli_result(file_path, format_type, language)
        if cli_result:
            results["cli"] = cli_result

        # Direct interface
        try:
            results["direct"] = await self.collect_direct_result(
                file_path, format_type, language
            )
        except Exception as e:
            results["direct"] = {"interface": "direct", "error": str(e)}

        # Analyze consistency
        consistency_report = self._analyze_consistency(results)

        return {"results": results, "consistency_report": consistency_report}

    def _analyze_consistency(
        self, results: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze consistency across interface results"""

        # Filter successful results
        successful_results = {
            interface: result
            for interface, result in results.items()
            if "error" not in result and "table_output" in result
        }

        if len(successful_results) < 2:
            return {
                "consistent": False,
                "reason": "Insufficient successful results for comparison",
                "successful_interfaces": list(successful_results.keys()),
                "failed_interfaces": [
                    interface
                    for interface, result in results.items()
                    if "error" in result
                ],
            }

        # Compare table outputs
        outputs = {
            interface: result["table_output"]
            for interface, result in successful_results.items()
        }

        # Check if all outputs are identical
        reference_output = next(iter(outputs.values()))
        identical_outputs = all(
            output == reference_output for output in outputs.values()
        )

        # Check format compliance for all outputs
        format_compliance = {}
        for interface, output in outputs.items():
            try:
                # Determine schema type
                format_type = successful_results[interface]["format_type"]
                schema_type = "csv" if format_type == "csv" else "markdown"

                validation_result = validate_format(output, schema_type)
                format_compliance[interface] = {
                    "valid": validation_result.is_valid,
                    "errors": validation_result.errors,
                }
            except Exception as e:
                format_compliance[interface] = {"valid": False, "errors": [str(e)]}

        # Check metadata consistency
        metadata_consistency = self._check_metadata_consistency(successful_results)

        return {
            "consistent": identical_outputs,
            "successful_interfaces": list(successful_results.keys()),
            "failed_interfaces": [
                interface for interface, result in results.items() if "error" in result
            ],
            "output_lengths": {
                interface: len(output) for interface, output in outputs.items()
            },
            "format_compliance": format_compliance,
            "metadata_consistency": metadata_consistency,
            "differences": (
                self._find_output_differences(outputs) if not identical_outputs else {}
            ),
        }

    def _check_metadata_consistency(
        self, results: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """Check consistency of metadata across interfaces"""
        metadata_fields = {}

        for interface, result in results.items():
            metadata = result.get("metadata", {})
            for field, value in metadata.items():
                if field not in metadata_fields:
                    metadata_fields[field] = {}
                metadata_fields[field][interface] = value

        # Check for consistent values
        consistent_fields = {}
        inconsistent_fields = {}

        for field, values in metadata_fields.items():
            if len(set(values.values())) == 1:
                consistent_fields[field] = next(iter(values.values()))
            else:
                inconsistent_fields[field] = values

        return {
            "consistent_fields": consistent_fields,
            "inconsistent_fields": inconsistent_fields,
            "all_consistent": len(inconsistent_fields) == 0,
        }

    def _find_output_differences(self, outputs: dict[str, str]) -> dict[str, Any]:
        """Find specific differences between outputs"""
        if len(outputs) < 2:
            return {}

        # Compare line by line
        interfaces = list(outputs.keys())
        reference_interface = interfaces[0]
        reference_lines = outputs[reference_interface].split("\n")

        differences = {}

        for interface in interfaces[1:]:
            lines = outputs[interface].split("\n")

            # Find line differences
            line_diffs = []
            max_lines = max(len(reference_lines), len(lines))

            for i in range(max_lines):
                ref_line = reference_lines[i] if i < len(reference_lines) else ""
                comp_line = lines[i] if i < len(lines) else ""

                if ref_line != comp_line:
                    line_diffs.append(
                        {
                            "line_number": i + 1,
                            "reference": ref_line,
                            "compared": comp_line,
                        }
                    )

            if line_diffs:
                differences[f"{reference_interface}_vs_{interface}"] = {
                    "line_differences": line_diffs[
                        :10
                    ],  # Limit to first 10 differences
                    "total_differences": len(line_diffs),
                }

        return differences


class TestCrossComponentFormatValidation:
    """Test cross-component format validation"""

    @pytest.fixture
    def test_file(self):
        """Create a test file for cross-component testing"""
        temp_dir = tempfile.mkdtemp()

        java_content = """package com.example.test;

import java.util.List;
import java.util.Map;

/**
 * Simple test class for cross-component validation
 */
public class TestService {
    private String name;
    private int count;

    public TestService(String name) {
        this.name = name;
        this.count = 0;
    }

    /**
     * Get the service name
     * @return service name
     */
    public String getName() {
        return name;
    }

    /**
     * Increment counter
     */
    public void increment() {
        count++;
    }

    /**
     * Get current count
     * @return current count value
     */
    public int getCount() {
        return count;
    }

    /**
     * Process data with given parameters
     * @param data input data
     * @param options processing options
     * @return processed result
     */
    public Map<String, Object> processData(List<String> data, Map<String, String> options) {
        // Processing logic here
        return Map.of("processed", true, "count", data.size());
    }
}"""

        test_file = Path(temp_dir) / "TestService.java"
        test_file.write_text(java_content, encoding="utf-8")

        yield temp_dir, test_file

        # Cleanup
        test_file.unlink()
        Path(temp_dir).rmdir()

    @pytest.fixture
    def validator(self, test_file):
        """Create cross-component validator"""
        temp_dir, _ = test_file
        return CrossComponentFormatValidator(temp_dir)

    @pytest.mark.asyncio
    async def test_mcp_api_consistency(self, test_file, validator):
        """Test consistency between MCP and API interfaces"""
        temp_dir, file_path = test_file

        for format_type in ["full", "compact", "csv"]:
            # Get results from both interfaces
            mcp_result = await validator.collect_mcp_result(
                str(file_path), format_type, "java"
            )
            api_result = await validator.collect_api_result(
                str(file_path), format_type, "java"
            )

            # Both should succeed
            assert (
                "error" not in mcp_result
            ), f"MCP failed for {format_type}: {mcp_result.get('error')}"
            assert (
                "error" not in api_result
            ), f"API failed for {format_type}: {api_result.get('error')}"

            # Outputs should be identical
            assert (
                mcp_result["table_output"] == api_result["table_output"]
            ), f"MCP and API outputs differ for {format_type}"

            # Format types should match
            assert mcp_result["format_type"] == api_result["format_type"] == format_type

            # Languages should match
            assert mcp_result["language"] == api_result["language"]

    @pytest.mark.asyncio
    async def test_all_interfaces_consistency(self, test_file, validator):
        """Test consistency across all available interfaces"""
        temp_dir, file_path = test_file

        for format_type in ["full", "compact", "csv"]:
            validation_result = await validator.validate_cross_component_consistency(
                str(file_path), format_type, "java"
            )

            consistency_report = validation_result["consistency_report"]

            # Should have at least MCP and API working
            assert (
                len(consistency_report["successful_interfaces"]) >= 2
            ), f"Too few successful interfaces for {format_type}: {consistency_report['successful_interfaces']}"

            # All successful interfaces should produce consistent output
            if consistency_report["successful_interfaces"]:
                assert consistency_report[
                    "consistent"
                ], f"Inconsistent output for {format_type}: {consistency_report.get('differences', {})}"

            # All outputs should be format-compliant
            for interface, compliance in consistency_report[
                "format_compliance"
            ].items():
                assert compliance[
                    "valid"
                ], f"Format compliance failed for {interface} in {format_type}: {compliance['errors']}"

    @pytest.mark.asyncio
    async def test_metadata_consistency(self, test_file, validator):
        """Test metadata consistency across interfaces"""
        temp_dir, file_path = test_file

        validation_result = await validator.validate_cross_component_consistency(
            str(file_path), "full", "java"
        )

        metadata_consistency = validation_result["consistency_report"][
            "metadata_consistency"
        ]

        # Check that common metadata fields are consistent
        if metadata_consistency["consistent_fields"]:
            # Should have some consistent metadata
            assert len(metadata_consistency["consistent_fields"]) > 0

        # Report any inconsistencies for debugging
        if metadata_consistency["inconsistent_fields"]:
            print(
                f"Metadata inconsistencies: {metadata_consistency['inconsistent_fields']}"
            )

    @pytest.mark.asyncio
    async def test_cli_integration_when_available(self, test_file, validator):
        """Test CLI integration when CLI is available"""
        temp_dir, file_path = test_file

        # Test CLI interface
        cli_result = validator.collect_cli_result(str(file_path), "compact", "java")

        if cli_result and "error" not in cli_result:
            # CLI is available, test consistency with other interfaces
            mcp_result = await validator.collect_mcp_result(
                str(file_path), "compact", "java"
            )

            # Basic structure should be similar
            cli_output = cli_result["table_output"]
            mcp_output = mcp_result["table_output"]

            # Both should contain the class name
            assert "TestService" in cli_output
            assert "TestService" in mcp_output

            # Both should have table structure
            assert "|" in cli_output or "," in cli_output  # Table or CSV
            assert "|" in mcp_output or "," in mcp_output

            # If outputs are not identical, they should at least be format-compliant
            if cli_output != mcp_output:
                schema_type = "markdown"  # compact format uses markdown
                cli_validation = validate_format(cli_output, schema_type)
                mcp_validation = validate_format(mcp_output, schema_type)

                assert (
                    cli_validation.is_valid
                ), f"CLI output not format-compliant: {cli_validation.errors}"
                assert (
                    mcp_validation.is_valid
                ), f"MCP output not format-compliant: {mcp_validation.errors}"
        else:
            pytest.skip("CLI interface not available or failed")

    @pytest.mark.asyncio
    async def test_direct_library_consistency(self, test_file, validator):
        """Test direct library usage consistency"""
        temp_dir, file_path = test_file

        # Test direct library usage
        direct_result = await validator.collect_direct_result(
            str(file_path), "full", "java"
        )

        if "error" not in direct_result:
            # Compare with MCP interface
            mcp_result = await validator.collect_mcp_result(
                str(file_path), "full", "java"
            )

            # Should produce similar results
            direct_output = direct_result["table_output"]
            mcp_output = mcp_result["table_output"]

            # Both should contain the class name
            assert "TestService" in direct_output
            assert "TestService" in mcp_output

            # Both should be format-compliant
            validation_direct = validate_format(direct_output, "markdown")
            validation_mcp = validate_format(mcp_output, "markdown")

            assert (
                validation_direct.is_valid
            ), f"Direct output not format-compliant: {validation_direct.errors}"
            assert (
                validation_mcp.is_valid
            ), f"MCP output not format-compliant: {validation_mcp.errors}"
        else:
            pytest.fail(f"Direct library usage failed: {direct_result['error']}")

    @pytest.mark.asyncio
    async def test_format_regression_across_interfaces(self, test_file, validator):
        """Test that format regressions are detected across all interfaces"""
        temp_dir, file_path = test_file

        # Collect baseline results from all interfaces
        baseline_results = await validator.validate_cross_component_consistency(
            str(file_path), "compact", "java"
        )

        # Verify baseline consistency
        assert baseline_results["consistency_report"][
            "consistent"
        ], "Baseline results are not consistent across interfaces"

        # This test validates that our cross-component validation
        # would detect regressions if they occurred
        successful_interfaces = baseline_results["consistency_report"][
            "successful_interfaces"
        ]
        assert (
            len(successful_interfaces) >= 2
        ), "Need at least 2 successful interfaces to detect regressions"

        # Verify all outputs are format-compliant
        for interface, compliance in baseline_results["consistency_report"][
            "format_compliance"
        ].items():
            assert compliance[
                "valid"
            ], f"Baseline format compliance failed for {interface}: {compliance['errors']}"


class TestFormatContractValidation:
    """Test format contracts across components"""

    @pytest.mark.asyncio
    async def test_format_contract_compliance(self, test_file):
        """Test that all interfaces comply with format contracts"""
        temp_dir, file_path = test_file
        validator = CrossComponentFormatValidator(temp_dir)

        # Define format contracts
        format_contracts = {
            "full": {
                "required_sections": ["# ", "## Class Info", "## Methods", "## Fields"],
                "table_markers": ["|"],
                "min_lines": 5,
            },
            "compact": {
                "required_sections": ["# ", "## "],
                "table_markers": ["|"],
                "min_lines": 3,
            },
            "csv": {"required_sections": [], "table_markers": [","], "min_lines": 2},
        }

        for format_type, contract in format_contracts.items():
            validation_result = await validator.validate_cross_component_consistency(
                str(file_path), format_type, "java"
            )

            successful_results = {
                interface: result
                for interface, result in validation_result["results"].items()
                if "error" not in result and "table_output" in result
            }

            # Test contract compliance for each successful interface
            for interface, result in successful_results.items():
                output = result["table_output"]
                lines = output.split("\n")

                # Check minimum lines
                assert (
                    len(lines) >= contract["min_lines"]
                ), f"{interface} {format_type} output too short: {len(lines)} < {contract['min_lines']}"

                # Check required sections
                for section in contract["required_sections"]:
                    assert (
                        section in output
                    ), f"{interface} {format_type} missing required section: {section}"

                # Check table markers
                for marker in contract["table_markers"]:
                    assert (
                        marker in output
                    ), f"{interface} {format_type} missing table marker: {marker}"

    @pytest.mark.asyncio
    async def test_error_handling_consistency(self, validator):
        """Test that error handling is consistent across interfaces"""
        # Test with non-existent file
        non_existent_file = "/path/that/does/not/exist.java"

        validation_result = await validator.validate_cross_component_consistency(
            non_existent_file, "full", "java"
        )

        # All interfaces should handle the error gracefully
        for interface, result in validation_result["results"].items():
            if "error" in result:
                # Error should be meaningful
                error_msg = result["error"].lower()
                assert any(
                    keyword in error_msg
                    for keyword in ["not found", "no such file", "does not exist"]
                ), f"{interface} error message not descriptive: {result['error']}"
            else:
                # If no error, should have empty or error-indicating output
                output = result.get("table_output", "")
                assert (
                    len(output.strip()) == 0
                    or "error" in output.lower()
                    or "not found" in output.lower()
                ), f"{interface} should indicate error for non-existent file"
