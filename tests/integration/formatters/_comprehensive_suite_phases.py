"""Phase implementations for the comprehensive formatter suite."""

from typing import Any

from ._comprehensive_suite_phase_cases import (
    run_one_cross_component_test,
    run_one_end_to_end_test,
    run_one_enhanced_assertion_test,
    run_one_format_contract_test,
    run_one_golden_master_test,
    run_one_integration_test,
    run_one_performance_test,
    run_one_schema_validation_test,
    run_one_specification_compliance_test,
)
from ._comprehensive_suite_phase_helpers import (
    FORMAT_TYPES,
    PhaseCase,
    add_error,
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
