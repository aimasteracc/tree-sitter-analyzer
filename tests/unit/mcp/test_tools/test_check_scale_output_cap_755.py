"""Bug #755 — check-scale / extract_structural_overview_universal must cap method list.

Without a cap, a 20 000-method file produces multi-MB JSON that can crash
agents. The fix adds a default cap of 50 entries to the methods list in
extract_structural_overview_universal (and the Java-path equivalent in
_extract_method_infos), with metadata fields:
  - structural_overview.methods_truncated: True  (only when list was cut)
  - structural_overview.total_methods: <full count>

The cap must be configurable via a ``method_cap`` keyword argument.
``total_methods`` is always present; ``methods_truncated`` is only present
when truncation actually occurred.

RED-first: these tests fail until the cap is added.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_scale_helpers import (
    METHODS_OUTPUT_CAP,
    extract_structural_overview,
    extract_structural_overview_universal,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_fn_element(
    name: str, start_line: int = 1, end_line: int = 5, complexity: int = 0
):
    """Minimal mock function element for universal overview."""
    e = MagicMock()
    e.element_type = "function"
    e.name = name
    e.start_line = start_line
    e.end_line = end_line
    e.complexity_score = complexity
    return e


def _make_java_fn_element(
    name: str,
    start_line: int = 1,
    end_line: int = 5,
    complexity_score: int = 0,
    visibility: str = "public",
    return_type: str = "void",
    parameters: list | None = None,
    is_constructor: bool = False,
    is_static: bool = False,
    annotations: list | None = None,
):
    """Minimal mock for the Java/Python extract_structural_overview path."""
    from tree_sitter_analyzer.constants import ELEMENT_TYPE_FUNCTION

    e = MagicMock()
    e.element_type = ELEMENT_TYPE_FUNCTION
    # is_element_of_type checks element_type attribute OR kind constant:
    e.name = name
    e.start_line = start_line
    e.end_line = end_line
    e.complexity_score = complexity_score
    e.visibility = visibility
    e.return_type = return_type
    e.parameters = parameters or []
    e.is_constructor = is_constructor
    e.is_static = is_static
    ann_mocks = []
    for a in annotations or []:
        m = MagicMock()
        m.name = a
        ann_mocks.append(m)
    e.annotations = ann_mocks
    return e


def _make_analysis_result_universal(elements):
    r = MagicMock()
    r.elements = elements
    return r


def _make_analysis_result_java(elements):
    r = MagicMock()
    r.elements = elements
    return r


# ---------------------------------------------------------------------------
# METHODS_OUTPUT_CAP constant
# ---------------------------------------------------------------------------


class TestMethodsOutputCap:
    def test_cap_constant_is_fifty(self):
        """Default cap must be exactly 50."""
        assert METHODS_OUTPUT_CAP == 50

    def test_cap_constant_is_int(self):
        assert isinstance(METHODS_OUTPUT_CAP, int)


# ---------------------------------------------------------------------------
# extract_structural_overview_universal — cap behaviour
# ---------------------------------------------------------------------------


class TestUniversalOverviewMethodCap:
    def _make_n_methods(self, n: int):
        return [
            _make_fn_element(f"fn_{i}", start_line=i * 10, end_line=i * 10 + 5)
            for i in range(n)
        ]

    def test_under_cap_no_truncation_metadata(self):
        """Fewer than CAP methods: no truncation flag, total_methods == len(methods)."""
        elements = self._make_n_methods(10)
        result = _make_analysis_result_universal(elements)
        overview = extract_structural_overview_universal(result)

        assert len(overview["methods"]) == 10
        assert (
            overview.get("methods_truncated") is None
            or overview.get("methods_truncated") is False
        ), "methods_truncated must not be True when no truncation occurred"
        assert overview["total_methods"] == 10

    def test_exactly_cap_no_truncation(self):
        """Exactly 50 methods: no truncation."""
        elements = self._make_n_methods(50)
        result = _make_analysis_result_universal(elements)
        overview = extract_structural_overview_universal(result)

        assert len(overview["methods"]) == 50
        assert (
            overview.get("methods_truncated") is None
            or overview.get("methods_truncated") is False
        )
        assert overview["total_methods"] == 50

    def test_over_cap_truncates_to_cap(self):
        """51 methods: list is capped at 50, truncation flag set."""
        elements = self._make_n_methods(51)
        result = _make_analysis_result_universal(elements)
        overview = extract_structural_overview_universal(result)

        assert len(overview["methods"]) == 50, (
            f"Expected 50 methods after cap, got {len(overview['methods'])}"
        )
        assert overview["methods_truncated"] is True, (
            "methods_truncated must be True when list was cut"
        )
        assert overview["total_methods"] == 51, (
            f"total_methods must reflect the full count, got {overview['total_methods']}"
        )

    @pytest.mark.slow_ok  # 20k MagicMocks is legitimately slow on Windows
    def test_large_method_count_capped_exactly(self):
        """20 000 methods: list stays at 50, total_methods = 20 000."""
        elements = self._make_n_methods(20_000)
        result = _make_analysis_result_universal(elements)
        overview = extract_structural_overview_universal(result)

        assert len(overview["methods"]) == 50
        assert overview["methods_truncated"] is True
        assert overview["total_methods"] == 20_000

    def test_cap_preserves_first_n_entries_by_line(self):
        """The kept entries should be the first N by line order (insertion order)."""
        elements = self._make_n_methods(100)
        result = _make_analysis_result_universal(elements)
        overview = extract_structural_overview_universal(result)

        kept_names = [m["name"] for m in overview["methods"]]
        expected_names = [f"fn_{i}" for i in range(50)]
        assert kept_names == expected_names, (
            "Cap should keep the first 50 entries by insertion order"
        )

    def test_custom_cap_via_kwarg(self):
        """method_cap keyword argument overrides the default cap."""
        elements = self._make_n_methods(20)
        result = _make_analysis_result_universal(elements)
        overview = extract_structural_overview_universal(result, method_cap=5)

        assert len(overview["methods"]) == 5
        assert overview["methods_truncated"] is True
        assert overview["total_methods"] == 20

    def test_zero_methods_no_truncation_metadata(self):
        """Empty method list: total_methods == 0, no truncation flag."""
        result = _make_analysis_result_universal([])
        overview = extract_structural_overview_universal(result)

        assert overview["total_methods"] == 0
        assert (
            overview.get("methods_truncated") is None
            or overview.get("methods_truncated") is False
        )


# ---------------------------------------------------------------------------
# extract_structural_overview (Java/Python path) — cap behaviour
# ---------------------------------------------------------------------------


class TestJavaOverviewMethodCap:
    """The Java/Python extract_structural_overview path must enforce the same cap."""

    def _make_n_java_methods(self, n: int):
        return [
            _make_java_fn_element(f"method_{i}", start_line=i * 10) for i in range(n)
        ]

    def _make_result(self, elements):
        r = MagicMock()
        r.elements = elements
        # is_element_of_type uses ELEMENT_TYPE_FUNCTION constant check too
        return r

    def test_under_cap_no_truncation(self):
        elements = self._make_n_java_methods(10)
        result = self._make_result(elements)
        overview = extract_structural_overview(result)

        assert len(overview["methods"]) == 10
        assert overview["total_methods"] == 10
        assert (
            overview.get("methods_truncated") is None
            or overview.get("methods_truncated") is False
        )

    def test_over_cap_truncates(self):
        elements = self._make_n_java_methods(200)
        result = self._make_result(elements)
        overview = extract_structural_overview(result)

        assert len(overview["methods"]) == 50
        assert overview["methods_truncated"] is True
        assert overview["total_methods"] == 200

    def test_exactly_cap_no_truncation(self):
        elements = self._make_n_java_methods(50)
        result = self._make_result(elements)
        overview = extract_structural_overview(result)

        assert len(overview["methods"]) == 50
        assert (
            overview.get("methods_truncated") is None
            or overview.get("methods_truncated") is False
        )
        assert overview["total_methods"] == 50
