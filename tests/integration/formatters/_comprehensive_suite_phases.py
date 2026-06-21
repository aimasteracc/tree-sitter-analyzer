"""Phase implementations for the comprehensive formatter suite."""

import tempfile
from pathlib import Path
from typing import Any

from ._comprehensive_suite_phase_helpers import (
    FORMAT_TYPES,
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
    new_phase_results,
)


class ComprehensiveSuitePhasesMixin:
    """Runs each validation phase behind the suite interface."""

    async def _run_golden_master_tests(
        self, analyzer_function: callable, test_data_sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run golden master tests"""
        results = new_phase_results()

        for test_data in test_data_sources:
            for format_type in FORMAT_TYPES:
                case = _format_phase_case(
                    analyzer_function, test_data, format_type, "golden_master", results
                )
                run_one_golden_master_test(self, case)

        return results

    async def _run_schema_validation_tests(
        self, analyzer_function: callable, test_data_sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run schema validation tests"""
        results = new_phase_results()

        for test_data in test_data_sources:
            for format_type in FORMAT_TYPES:
                case = _format_phase_case(
                    analyzer_function,
                    test_data,
                    format_type,
                    "schema_validation",
                    results,
                )
                await run_one_schema_validation_test(self, case)

        return results

    async def _run_integration_tests(
        self, analyzer_function: callable, test_data_sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run integration tests"""
        results = new_phase_results()

        try:
            for test_data in test_data_sources:
                case = _language_phase_case(
                    analyzer_function, test_data, "integration", results
                )
                run_one_integration_test(case)
        except Exception as exc:
            results["total"] += 1
            add_error(results, "integration_suite", exc)

        return results

    async def _run_end_to_end_tests(
        self, analyzer_function: callable, test_data_sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run end-to-end tests"""
        results = new_phase_results()

        try:
            for test_data in test_data_sources:
                for format_type in FORMAT_TYPES:
                    case = _format_phase_case(
                        analyzer_function, test_data, format_type, "e2e", results
                    )
                    run_one_end_to_end_test(case)
        except Exception as exc:
            results["total"] += 1
            add_error(results, "end_to_end_suite", exc)

        return results

    async def _run_cross_component_tests(
        self, analyzer_function: callable, test_data_sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run cross-component tests"""
        results = new_phase_results()

        try:
            for test_data in test_data_sources:
                case = _language_phase_case(
                    analyzer_function, test_data, "cross_component", results
                )
                run_one_cross_component_test(case)
        except Exception as exc:
            results["total"] += 1
            add_error(results, "cross_component_suite", exc)

        return results

    async def _run_specification_compliance_tests(
        self, analyzer_function: callable, test_data_sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run specification compliance tests"""
        results = new_phase_results()

        try:
            for test_data in test_data_sources:
                for format_type in FORMAT_TYPES:
                    case = _format_phase_case(
                        analyzer_function,
                        test_data,
                        format_type,
                        "spec_compliance",
                        results,
                    )
                    await run_one_specification_compliance_test(case)
        except Exception as exc:
            results["total"] += 1
            add_error(results, "specification_compliance_suite", exc)

        return results

    async def _run_format_contract_tests(
        self, analyzer_function: callable, test_data_sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run format contract tests"""
        results = new_phase_results()

        try:
            for test_data in test_data_sources:
                case = _language_phase_case(
                    analyzer_function, test_data, "format_contract", results
                )
                run_one_format_contract_test(case)
        except Exception as exc:
            results["total"] += 1
            add_error(results, "format_contract_suite", exc)

        return results

    async def _run_enhanced_assertion_tests(
        self, analyzer_function: callable, test_data_sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run enhanced assertion tests"""
        results = new_phase_results()

        for test_data in test_data_sources:
            for format_type in FORMAT_TYPES:
                case = _format_phase_case(
                    analyzer_function,
                    test_data,
                    format_type,
                    "enhanced_assertions",
                    results,
                )
                await run_one_enhanced_assertion_test(self, case)

        return results

    async def _run_performance_tests(
        self, analyzer_function: callable, test_data_sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run performance tests"""
        results = new_phase_results({"performance_metrics": []})

        for test_data in test_data_sources:
            case = _language_phase_case(
                analyzer_function, test_data, "performance", results
            )
            run_one_performance_test(self, case)

        return results


def _format_phase_case(
    analyzer_function: callable,
    test_data: dict[str, Any],
    format_type: str,
    prefix: str,
    results: dict[str, Any],
) -> PhaseCase:
    results["total"] += 1
    return PhaseCase(
        analyzer_function=analyzer_function,
        test_data=test_data,
        test_name=f"{prefix}_{test_data['language']}_{format_type}",
        results=results,
        format_type=format_type,
    )


def _language_phase_case(
    analyzer_function: callable,
    test_data: dict[str, Any],
    prefix: str,
    results: dict[str, Any],
) -> PhaseCase:
    results["total"] += 1
    return PhaseCase(
        analyzer_function=analyzer_function,
        test_data=test_data,
        test_name=f"{prefix}_{test_data['language']}",
        results=results,
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
