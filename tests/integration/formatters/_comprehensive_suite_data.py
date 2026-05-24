"""Test data preparation for the comprehensive formatter suite."""

from typing import Any


class ComprehensiveSuiteDataMixin:
    """Prepares generated or fallback test data for suite phases."""

    async def _prepare_test_data(self) -> list[dict[str, Any]]:
        """Prepare test data for comprehensive testing"""
        test_data_sources = []

        if self.config.generate_test_data:
            print("📝 Generating test data...")
            created_ids = self.test_data_manager.create_test_data_suite(
                languages=self.config.test_data_languages,
                complexities=self.config.test_data_complexities,
                count_per_combination=2,
            )
            test_data_sources.extend(self._load_created_test_data(created_ids))

        if not test_data_sources:
            test_data_sources = [_default_python_test_data()]

        print(f"📊 Prepared {len(test_data_sources)} test data sources")
        return test_data_sources

    def _load_created_test_data(self, created_ids: list[str]) -> list[dict[str, Any]]:
        test_data_sources = []
        for test_id in created_ids:
            test_data_set = self.test_data_manager.repository.get_test_data(test_id)
            if test_data_set:
                test_data_sources.append(_test_data_set_source(test_id, test_data_set))
        return test_data_sources


def _test_data_set_source(test_id: str, test_data_set: Any) -> dict[str, Any]:
    return {
        "id": test_id,
        "language": test_data_set.metadata.language,
        "complexity": test_data_set.metadata.complexity_level,
        "source_code": test_data_set.source_code,
        "expected_outputs": test_data_set.expected_outputs,
        "test_scenarios": test_data_set.test_scenarios,
    }


def _default_python_test_data() -> dict[str, Any]:
    return {
        "id": "default_python",
        "language": "python",
        "complexity": "simple",
        "source_code": 'class TestClass:\n    def test_method(self):\n        return "test"',
        "expected_outputs": {},
        "test_scenarios": [],
    }
