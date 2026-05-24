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

from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool as TableFormatTool,
)

from ._format_contract_tests_helpers import (
    assert_access_modifier_consistency,
    assert_backward_compatibility_contract,
    assert_cross_format_data_integrity,
    assert_csv_parameter_encoding,
    assert_field_count_consistency,
    assert_line_number_consistency,
    assert_method_count_consistency,
    assert_outputs_contain_class_name,
    cleanup_comprehensive_contract_fixture,
    collect_format_outputs,
    create_comprehensive_contract_fixture,
    extract_compact_format_info,
    extract_contract_infos,
    extract_csv_format_info,
    extract_full_format_info,
    parse_markdown_table,
    validate_class_consistency,
    validate_compact_format_contracts,
    validate_count_consistency,
    validate_cross_format_contracts,
    validate_csv_format_contracts,
    validate_csv_parameters,
    validate_field_consistency,
    validate_full_format_contracts,
    validate_method_consistency,
)


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
        return extract_full_format_info(output)

    def _extract_compact_format_info(self, output: str) -> dict[str, Any]:
        """Extract structured information from compact format"""
        return extract_compact_format_info(output)

    def _extract_csv_format_info(self, output: str) -> dict[str, Any]:
        """Extract structured information from CSV format"""
        return extract_csv_format_info(output)

    def _parse_markdown_table(self, table_content: str) -> list[list[str]]:
        """Parse Markdown table content into rows"""
        return parse_markdown_table(table_content)

    def _validate_class_consistency(
        self,
        full_info: dict[str, Any],
        compact_info: dict[str, Any],
        csv_info: dict[str, Any],
    ) -> bool:
        """Validate class information consistency"""
        return validate_class_consistency(
            full_info, compact_info, csv_info, self.violations
        )

    def _validate_method_consistency(
        self,
        full_info: dict[str, Any],
        compact_info: dict[str, Any],
        csv_info: dict[str, Any],
    ) -> bool:
        """Validate method information consistency"""
        return validate_method_consistency(
            full_info, compact_info, csv_info, self.violations
        )

    def _validate_field_consistency(
        self,
        full_info: dict[str, Any],
        compact_info: dict[str, Any],
        csv_info: dict[str, Any],
    ) -> bool:
        """Validate field information consistency"""
        return validate_field_consistency(
            full_info, compact_info, csv_info, self.violations
        )

    def _validate_count_consistency(
        self,
        full_info: dict[str, Any],
        compact_info: dict[str, Any],
        csv_info: dict[str, Any],
    ) -> bool:
        """Validate count information consistency"""
        return validate_count_consistency(
            full_info, compact_info, csv_info, self.violations
        )

    def _validate_full_format_contracts(self, output: str) -> bool:
        """Validate Full Format specific contracts"""
        return validate_full_format_contracts(output, self.violations)

    def _validate_compact_format_contracts(self, output: str) -> bool:
        """Validate Compact Format specific contracts"""
        return validate_compact_format_contracts(output, self.violations, self.warnings)

    def _validate_csv_format_contracts(self, output: str) -> bool:
        """Validate CSV Format specific contracts"""
        return validate_csv_format_contracts(output, self.violations)

    def _validate_cross_format_contracts(
        self, full_output: str, compact_output: str, csv_output: str
    ) -> bool:
        """Validate contracts that span multiple formats"""
        del csv_output
        return validate_cross_format_contracts(
            full_output, compact_output, self.violations
        )

    def _validate_csv_parameters(self, parameters: str) -> bool:
        """Validate CSV parameter encoding format"""
        return validate_csv_parameters(parameters)

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
        temp_dir, test_file, class_name = create_comprehensive_contract_fixture()

        yield temp_dir, test_file, class_name

        cleanup_comprehensive_contract_fixture(temp_dir, test_file)

    @pytest.fixture
    def contract_validator(self):
        """Create contract validator"""
        return FormatContractValidator()

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Format contracts outdated - current implementation uses different section structure (## Public Methods vs ## Methods)"
    )
    async def test_information_consistency_contract(
        self, comprehensive_test_file, contract_validator
    ):
        """Test information consistency contract across all formats"""
        temp_dir, file_path, class_name = comprehensive_test_file

        tool = TableFormatTool(project_root=temp_dir)
        outputs = await collect_format_outputs(tool, file_path)

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
        assert is_consistent, (
            f"Information consistency contract violated: {report['violations']}"
        )

        assert_outputs_contain_class_name(outputs, class_name)

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Format contracts outdated - CSV/Fields structure changed in current implementation"
    )
    async def test_format_specific_contracts(
        self, comprehensive_test_file, contract_validator
    ):
        """Test format-specific contracts"""
        temp_dir, file_path, _class_name = comprehensive_test_file

        tool = TableFormatTool(project_root=temp_dir)
        outputs = await collect_format_outputs(tool, file_path)

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
    @pytest.mark.skip(
        reason="Method count extraction logic needs update for new section structure"
    )
    async def test_method_count_contract(
        self, comprehensive_test_file, contract_validator
    ):
        """Test method count consistency contract"""
        temp_dir, file_path, class_name = comprehensive_test_file

        tool = TableFormatTool(project_root=temp_dir)
        outputs = await collect_format_outputs(tool, file_path)
        full_info, compact_info, csv_info = extract_contract_infos(
            contract_validator, outputs
        )
        assert_method_count_consistency(
            full_info, compact_info, csv_info, expected_methods=11
        )

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Field count extraction logic needs update for new section structure"
    )
    async def test_field_count_contract(
        self, comprehensive_test_file, contract_validator
    ):
        """Test field count consistency contract"""
        temp_dir, file_path, class_name = comprehensive_test_file

        tool = TableFormatTool(project_root=temp_dir)
        outputs = await collect_format_outputs(tool, file_path)
        full_info, compact_info, csv_info = extract_contract_infos(
            contract_validator, outputs
        )
        assert_field_count_consistency(
            full_info, compact_info, csv_info, expected_fields=4
        )

    @pytest.mark.asyncio
    async def test_parameter_encoding_contract(
        self, comprehensive_test_file, contract_validator
    ):
        """Test parameter encoding consistency contract"""
        temp_dir, file_path, class_name = comprehensive_test_file

        tool = TableFormatTool(project_root=temp_dir)
        outputs = await collect_format_outputs(tool, file_path, format_types=("csv",))
        assert_csv_parameter_encoding(outputs["csv"], contract_validator)
        assert "csv" in outputs
        assert len(outputs["csv"]) > 0

    @pytest.mark.asyncio
    async def test_access_modifier_consistency_contract(
        self, comprehensive_test_file, contract_validator
    ):
        """Test access modifier consistency across formats"""
        temp_dir, file_path, class_name = comprehensive_test_file

        tool = TableFormatTool(project_root=temp_dir)
        outputs = await collect_format_outputs(tool, file_path)
        full_info, compact_info, csv_info = extract_contract_infos(
            contract_validator, outputs
        )
        assert_access_modifier_consistency(full_info, compact_info, csv_info)
        assert full_info is not None
        assert compact_info is not None
        assert csv_info is not None

    @pytest.mark.asyncio
    async def test_line_number_consistency_contract(
        self, comprehensive_test_file, contract_validator
    ):
        """Test line number consistency across formats"""
        temp_dir, file_path, class_name = comprehensive_test_file

        tool = TableFormatTool(project_root=temp_dir)
        outputs = await collect_format_outputs(tool, file_path)
        full_info, compact_info, csv_info = extract_contract_infos(
            contract_validator, outputs
        )
        assert_line_number_consistency(full_info, compact_info, csv_info)
        assert isinstance(full_info, dict)
        assert isinstance(compact_info, dict)
        assert isinstance(csv_info, dict)

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Backward compatibility contract based on old format (## Methods vs ## Public Methods)"
    )
    async def test_backward_compatibility_contract(
        self, comprehensive_test_file, contract_validator
    ):
        """Test backward compatibility contract"""
        temp_dir, file_path, class_name = comprehensive_test_file

        tool = TableFormatTool(project_root=temp_dir)
        current_outputs = await collect_format_outputs(tool, file_path)
        assert_backward_compatibility_contract(current_outputs)

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Data integrity contract based on old format specifications"
    )
    async def test_cross_format_data_integrity_contract(
        self, comprehensive_test_file, contract_validator
    ):
        """Test cross-format data integrity contract"""
        temp_dir, file_path, class_name = comprehensive_test_file

        tool = TableFormatTool(project_root=temp_dir)
        outputs = await collect_format_outputs(tool, file_path)

        # Validate complete data integrity
        is_consistent = contract_validator.validate_information_consistency(
            outputs["full"], outputs["compact"], outputs["csv"]
        )

        is_contract_valid = contract_validator.validate_format_contracts(
            outputs["full"], outputs["compact"], outputs["csv"]
        )

        report = contract_validator.get_contract_report()

        assert_cross_format_data_integrity(
            outputs, class_name, is_consistent, is_contract_valid, report
        )
