#!/usr/bin/env python3
"""
Property-based tests for QueryFilter correctness.

**Feature: test-coverage-improvement, Property 7: Query Filter Correctness**
**Validates: Requirements 5.2, 5.4**

This module tests that for any query with filter criteria, all returned results
SHALL satisfy all filter conditions.
"""

import re

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.core.query_filter import QueryFilter


# Strategies for generating test data
@st.composite
def method_name_strategy(draw: st.DrawFn) -> str:
    """Generate valid method names."""
    first_char = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz_"))
    rest = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_",
            min_size=0,
            max_size=20,
        )
    )
    return first_char + rest


@st.composite
def modifier_strategy(draw: st.DrawFn) -> str:
    """Generate access modifiers."""
    return draw(st.sampled_from(["public", "private", "protected", ""]))


@st.composite
def static_modifier_strategy(draw: st.DrawFn) -> str:
    """Generate static modifier."""
    return draw(st.sampled_from(["static", ""]))


@st.composite
def parameter_list_strategy(draw: st.DrawFn) -> tuple[str, int]:
    """Generate parameter list and count."""
    param_count = draw(st.integers(min_value=0, max_value=5))
    if param_count == 0:
        return "", 0

    param_types = ["String", "int", "boolean", "Object", "List"]
    params = []
    for i in range(param_count):
        param_type = draw(st.sampled_from(param_types))
        param_name = f"param{i}"
        params.append(f"{param_type} {param_name}")

    return ", ".join(params), param_count


@st.composite
def java_method_content_strategy(draw: st.DrawFn) -> dict:
    """Generate Java method content with known properties."""
    modifier = draw(modifier_strategy())
    static_mod = draw(static_modifier_strategy())
    method_name = draw(method_name_strategy())
    params, param_count = draw(parameter_list_strategy())

    # Build method signature
    parts = []
    if modifier:
        parts.append(modifier)
    if static_mod:
        parts.append(static_mod)
    parts.append("void")
    parts.append(f"{method_name}({params})")
    parts.append("{ }")

    content = " ".join(parts)

    return {
        "content": content,
        "capture_name": "method",
        "node_type": "method_declaration",
        "start_line": 1,
        "end_line": 1,
        # Metadata for verification
        "_method_name": method_name,
        "_modifier": modifier,
        "_static": static_mod,
        "_param_count": param_count,
    }


@st.composite
def query_results_strategy(draw: st.DrawFn) -> list[dict]:
    """Generate a list of query results."""
    count = draw(st.integers(min_value=1, max_value=10))
    results = []
    for i in range(count):
        result = draw(java_method_content_strategy())
        result["start_line"] = i * 5 + 1
        result["end_line"] = i * 5 + 3
        results.append(result)
    return results


class TestQueryFilterCorrectnessProperties:
    """
    Property-based tests for QueryFilter correctness.

    **Feature: test-coverage-improvement, Property 7: Query Filter Correctness**
    **Validates: Requirements 5.2, 5.4**
    """

    def setup_method(self):
        """Set up test fixtures."""
        self.filter = QueryFilter()

    @given(results=query_results_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_property_7_name_exact_filter_correctness(self, results: list[dict]):
        """
        **Feature: test-coverage-improvement, Property 7: Query Filter Correctness**
        **Validates: Requirements 5.2, 5.4**

        For any query results filtered by exact name, all returned results
        SHALL have the specified method name.
        """
        if not results:
            return

        # Pick a random method name from the results to filter by
        target_name = results[0]["_method_name"]
        filter_expr = f"name={target_name}"

        filtered = self.filter.filter_results(results, filter_expr)

        # Property: All filtered results must have the exact name
        for result in filtered:
            extracted_name = self.filter._extract_method_name(result["content"])
            assert (
                extracted_name == target_name
            ), f"Filtered result has name '{extracted_name}' but filter was for '{target_name}'"

    @given(results=query_results_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_property_7_static_filter_correctness(self, results: list[dict]):
        """
        **Feature: test-coverage-improvement, Property 7: Query Filter Correctness**
        **Validates: Requirements 5.2, 5.4**

        For any query results filtered by static=true, all returned results
        SHALL contain the 'static' keyword.
        """
        filter_expr = "static=true"
        filtered = self.filter.filter_results(results, filter_expr)

        # Property: All filtered results must contain 'static'
        for result in filtered:
            assert (
                "static" in result["content"]
            ), f"Filtered result does not contain 'static': {result['content']}"

    @given(results=query_results_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_property_7_static_false_filter_correctness(self, results: list[dict]):
        """
        **Feature: test-coverage-improvement, Property 7: Query Filter Correctness**
        **Validates: Requirements 5.2, 5.4**

        For any query results filtered by static=false, all returned results
        SHALL NOT contain the 'static' keyword.
        """
        filter_expr = "static=false"
        filtered = self.filter.filter_results(results, filter_expr)

        # Property: All filtered results must NOT contain 'static'
        for result in filtered:
            assert (
                "static" not in result["content"]
            ), f"Filtered result contains 'static' but filter was static=false: {result['content']}"

    @given(results=query_results_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_property_7_public_filter_correctness(self, results: list[dict]):
        """
        **Feature: test-coverage-improvement, Property 7: Query Filter Correctness**
        **Validates: Requirements 5.2, 5.4**

        For any query results filtered by public=true, all returned results
        SHALL contain the 'public' keyword.
        """
        filter_expr = "public=true"
        filtered = self.filter.filter_results(results, filter_expr)

        # Property: All filtered results must contain 'public'
        for result in filtered:
            assert (
                "public" in result["content"]
            ), f"Filtered result does not contain 'public': {result['content']}"

    @given(results=query_results_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_property_7_private_filter_correctness(self, results: list[dict]):
        """
        **Feature: test-coverage-improvement, Property 7: Query Filter Correctness**
        **Validates: Requirements 5.2, 5.4**

        For any query results filtered by private=true, all returned results
        SHALL contain the 'private' keyword.
        """
        filter_expr = "private=true"
        filtered = self.filter.filter_results(results, filter_expr)

        # Property: All filtered results must contain 'private'
        for result in filtered:
            assert (
                "private" in result["content"]
            ), f"Filtered result does not contain 'private': {result['content']}"

    @given(results=query_results_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_property_7_protected_filter_correctness(self, results: list[dict]):
        """
        **Feature: test-coverage-improvement, Property 7: Query Filter Correctness**
        **Validates: Requirements 5.2, 5.4**

        For any query results filtered by protected=true, all returned results
        SHALL contain the 'protected' keyword.
        """
        filter_expr = "protected=true"
        filtered = self.filter.filter_results(results, filter_expr)

        # Property: All filtered results must contain 'protected'
        for result in filtered:
            assert (
                "protected" in result["content"]
            ), f"Filtered result does not contain 'protected': {result['content']}"

    @given(
        results=query_results_strategy(),
        param_count=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_property_7_params_filter_correctness(
        self, results: list[dict], param_count: int
    ):
        """
        **Feature: test-coverage-improvement, Property 7: Query Filter Correctness**
        **Validates: Requirements 5.2, 5.4**

        For any query results filtered by params=N, all returned results
        SHALL have exactly N parameters.
        """
        filter_expr = f"params={param_count}"
        filtered = self.filter.filter_results(results, filter_expr)

        # Property: All filtered results must have exactly param_count parameters
        for result in filtered:
            actual_count = self.filter._count_parameters(result["content"])
            assert (
                actual_count == param_count
            ), f"Filtered result has {actual_count} params but filter was for {param_count}: {result['content']}"

    @given(results=query_results_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_property_7_combined_filters_correctness(self, results: list[dict]):
        """
        **Feature: test-coverage-improvement, Property 7: Query Filter Correctness**
        **Validates: Requirements 5.2, 5.4**

        For any query results filtered by multiple conditions (AND logic),
        all returned results SHALL satisfy ALL filter conditions.
        """
        # Filter by public=true AND static=true
        filter_expr = "public=true,static=true"
        filtered = self.filter.filter_results(results, filter_expr)

        # Property: All filtered results must satisfy BOTH conditions
        for result in filtered:
            assert (
                "public" in result["content"]
            ), f"Filtered result does not contain 'public': {result['content']}"
            assert (
                "static" in result["content"]
            ), f"Filtered result does not contain 'static': {result['content']}"

    @given(results=query_results_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_property_7_pattern_filter_correctness(self, results: list[dict]):
        """
        **Feature: test-coverage-improvement, Property 7: Query Filter Correctness**
        **Validates: Requirements 5.2, 5.4**

        For any query results filtered by pattern name, all returned results
        SHALL have method names matching the pattern.
        """
        if not results:
            return

        # Use a pattern that matches names starting with the first letter of first result
        first_name = results[0]["_method_name"]
        if not first_name:
            return

        pattern = f"{first_name[0]}*"
        filter_expr = f"name=~{pattern}"

        filtered = self.filter.filter_results(results, filter_expr)

        # Property: All filtered results must match the pattern
        regex_pattern = pattern.replace("*", ".*")
        for result in filtered:
            extracted_name = self.filter._extract_method_name(result["content"])
            assert (
                re.match(regex_pattern, extracted_name, re.IGNORECASE) is not None
            ), f"Filtered result name '{extracted_name}' does not match pattern '{pattern}'"

    @given(results=query_results_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_property_7_empty_filter_returns_all(self, results: list[dict]):
        """
        **Feature: test-coverage-improvement, Property 7: Query Filter Correctness**
        **Validates: Requirements 5.2, 5.4**

        For any query results with empty filter expression,
        all original results SHALL be returned unchanged.
        """
        # Empty filter should return all results
        filtered_empty = self.filter.filter_results(results, "")
        assert filtered_empty == results, "Empty filter should return all results"

        # None filter should also return all results
        filtered_none = self.filter.filter_results(results, None)
        assert filtered_none == results, "None filter should return all results"

    @given(results=query_results_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_property_7_filtered_subset_of_original(self, results: list[dict]):
        """
        **Feature: test-coverage-improvement, Property 7: Query Filter Correctness**
        **Validates: Requirements 5.2, 5.4**

        For any filter operation, the filtered results SHALL be a subset
        of the original results (no new results introduced).
        """
        filter_expr = "public=true"
        filtered = self.filter.filter_results(results, filter_expr)

        # Property: Every filtered result must exist in original results
        for result in filtered:
            assert (
                result in results
            ), f"Filtered result not found in original results: {result}"

    @given(results=query_results_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_property_7_filter_preserves_result_structure(self, results: list[dict]):
        """
        **Feature: test-coverage-improvement, Property 7: Query Filter Correctness**
        **Validates: Requirements 5.2, 5.4**

        For any filter operation, the filtered results SHALL preserve
        the original structure of each result (no modification).
        """
        filter_expr = "static=true"
        filtered = self.filter.filter_results(results, filter_expr)

        # Property: Each filtered result should be the exact same object (identity)
        # from the original list - filter should not create new objects
        for result in filtered:
            # Check that the result is the exact same object (by identity) in original
            found = any(result is r for r in results)
            assert found, "Filtered result must be the same object from original list"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
