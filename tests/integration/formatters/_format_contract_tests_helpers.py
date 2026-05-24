"""Compatibility facade for format contract test helpers."""

from ._format_contract_assertion_helpers import (
    assert_access_modifier_consistency,
    assert_backward_compatibility_contract,
    assert_cross_format_data_integrity,
    assert_csv_parameter_encoding,
    assert_field_count_consistency,
    assert_line_number_consistency,
    assert_method_count_consistency,
    assert_outputs_contain_class_name,
    collect_format_outputs,
    extract_contract_infos,
)
from ._format_contract_info_helpers import (
    extract_compact_format_info,
    extract_csv_format_info,
    extract_full_format_info,
    parse_markdown_table,
    validate_field_consistency,
    validate_method_consistency,
)
from ._format_contract_tests_data import (
    cleanup_comprehensive_contract_fixture,
    create_comprehensive_contract_fixture,
)
from ._format_contract_validator_helpers import (
    validate_class_consistency,
    validate_compact_format_contracts,
    validate_count_consistency,
    validate_cross_format_contracts,
    validate_csv_format_contracts,
    validate_csv_parameters,
    validate_full_format_contracts,
)

__all__ = [
    "assert_access_modifier_consistency",
    "assert_backward_compatibility_contract",
    "assert_cross_format_data_integrity",
    "assert_csv_parameter_encoding",
    "assert_field_count_consistency",
    "assert_line_number_consistency",
    "assert_method_count_consistency",
    "assert_outputs_contain_class_name",
    "cleanup_comprehensive_contract_fixture",
    "collect_format_outputs",
    "create_comprehensive_contract_fixture",
    "extract_compact_format_info",
    "extract_contract_infos",
    "extract_csv_format_info",
    "extract_full_format_info",
    "parse_markdown_table",
    "validate_class_consistency",
    "validate_compact_format_contracts",
    "validate_count_consistency",
    "validate_cross_format_contracts",
    "validate_csv_format_contracts",
    "validate_csv_parameters",
    "validate_field_consistency",
    "validate_full_format_contracts",
    "validate_method_consistency",
]
