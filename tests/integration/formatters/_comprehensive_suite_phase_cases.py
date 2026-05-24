"""Single-case executors for comprehensive formatter suite phases."""

import tempfile
from pathlib import Path
from typing import Any

from ._comprehensive_suite_phase_helpers import (
    PhaseCase,
    add_error,
    add_failure,
    add_pass,
    call_analyzer,
    e2e_failure_message,
    is_non_empty_output,
    is_schema_valid,
    is_specification_compliant,
    is_valid_e2e_output,
)


def run_one_golden_master_test(suite: Any, case: PhaseCase) -> None:
    try:
        current_output = case.analyzer_function(
            case.test_data["source_code"], format_type=case.format_type
        )
        golden_content = suite.golden_master_tester.get_golden_master_content(
            case.test_name
        )

        if golden_content is None:
            suite.golden_master_tester.create_golden_master(
                current_output, case.test_name
            )
            add_pass(case.results, case.test_name, "Golden master created")
            return

        comparison_result = {"matches": current_output == golden_content}
        if comparison_result["matches"]:
            add_pass(case.results, case.test_name, "Matches golden master")
        else:
            add_failure(
                case.results,
                case.test_name,
                f"Golden master mismatch: {comparison_result.get('differences', 'Unknown')}",
            )
    except Exception as exc:
        add_error(case.results, case.test_name, exc)


async def run_one_schema_validation_test(suite: Any, case: PhaseCase) -> None:
    try:
        output = await call_analyzer(
            case.analyzer_function,
            case.test_data["source_code"],
            case.format_type,
        )
        is_valid, errors = is_schema_valid(suite, case.format_type, output)
        if is_valid:
            add_pass(case.results, case.test_name, "Schema validation passed")
        else:
            add_failure(
                case.results, case.test_name, f"Schema validation failed: {errors}"
            )
    except Exception as exc:
        add_error(case.results, case.test_name, exc)


def run_one_integration_test(case: PhaseCase) -> None:
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=f".{case.test_data['language']}", delete=False
        ) as temp_file_handle:
            temp_file_handle.write(case.test_data["source_code"])
            temp_file = temp_file_handle.name

        output = case.analyzer_function(
            case.test_data["source_code"], format_type="full"
        )
        if is_non_empty_output(output):
            add_pass(case.results, case.test_name, "Integration test passed")
        else:
            add_failure(case.results, case.test_name, "Empty output generated")

        Path(temp_file).unlink(missing_ok=True)
    except Exception as exc:
        add_error(case.results, case.test_name, exc)


def run_one_end_to_end_test(case: PhaseCase) -> None:
    try:
        output = case.analyzer_function(
            case.test_data["source_code"], format_type=case.format_type
        )
        if is_valid_e2e_output(case.format_type, output):
            add_pass(case.results, case.test_name, "End-to-end test passed")
        else:
            add_failure(
                case.results, case.test_name, e2e_failure_message(case.format_type)
            )
    except Exception as exc:
        add_error(case.results, case.test_name, exc)


def run_one_cross_component_test(case: PhaseCase) -> None:
    try:
        outputs = {
            format_type: case.analyzer_function(
                case.test_data["source_code"], format_type=format_type
            )
            for format_type in ["full", "compact", "csv"]
        }
        if all(is_non_empty_output(output) for output in outputs.values()):
            add_pass(
                case.results, case.test_name, "Cross-component consistency test passed"
            )
        else:
            add_failure(
                case.results, case.test_name, "Inconsistent outputs across formats"
            )
    except Exception as exc:
        add_error(case.results, case.test_name, exc)


async def run_one_specification_compliance_test(case: PhaseCase) -> None:
    try:
        output = await call_analyzer(
            case.analyzer_function,
            case.test_data["source_code"],
            case.format_type,
        )
        if is_specification_compliant(case.format_type, output):
            add_pass(
                case.results, case.test_name, "Specification compliance test passed"
            )
        else:
            add_failure(
                case.results,
                case.test_name,
                f"Specification compliance failed for {case.format_type} format",
            )
    except Exception as exc:
        add_error(case.results, case.test_name, exc)


def run_one_format_contract_test(case: PhaseCase) -> None:
    try:
        outputs = [
            case.analyzer_function(case.test_data["source_code"], format_type="full")
            for _ in range(3)
        ]
        if all(output == outputs[0] for output in outputs):
            add_pass(
                case.results,
                case.test_name,
                "Format contract test passed - deterministic output",
            )
        else:
            add_failure(
                case.results,
                case.test_name,
                "Format contract failed - non-deterministic output",
            )
    except Exception as exc:
        add_error(case.results, case.test_name, exc)


async def run_one_enhanced_assertion_test(suite: Any, case: PhaseCase) -> None:
    try:
        output = await call_analyzer(
            case.analyzer_function,
            case.test_data["source_code"],
            case.format_type,
        )
        assertion_result = suite.enhanced_assertions.validate_format_output(
            output, case.format_type, case.test_data["language"]
        )
        if assertion_result["valid"]:
            add_pass(case.results, case.test_name, "Enhanced assertions passed")
        else:
            add_failure(
                case.results,
                case.test_name,
                f"Enhanced assertions failed: {assertion_result['issues']}",
            )
    except Exception as exc:
        add_error(case.results, case.test_name, exc)


def run_one_performance_test(suite: Any, case: PhaseCase) -> None:
    try:
        performance_results = suite.performance_tester.test_format_performance(
            case.analyzer_function,
            case.test_data["source_code"],
            case.test_data["language"],
        )
        if _performance_is_acceptable(performance_results):
            add_pass(
                case.results, case.test_name, "Performance within acceptable limits"
            )
        else:
            add_failure(
                case.results, case.test_name, "Performance exceeded acceptable limits"
            )

        case.results["performance_metrics"].append(
            {"test_name": case.test_name, "results": performance_results}
        )
    except Exception as exc:
        add_error(case.results, case.test_name, exc)


def _performance_is_acceptable(performance_results: dict[str, Any]) -> bool:
    for _format_type, metrics in performance_results.items():
        if not metrics.success or metrics.execution_time_ms > 5000:
            return False
    return True
