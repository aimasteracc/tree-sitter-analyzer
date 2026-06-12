#!/usr/bin/env python3
"""RED-first tests for byte budget + honest truncation on structure/outline surface.

Issue #513 leg 3: GetCodeOutlineTool must cap large responses by default so
MCP agents stay within context-window budgets, following the honest-truncation
pattern from DF-13 (callers) and DF-1 (search_content).

Cap design:
  DEFAULT_OUTLINE_CLASSES_CAP = 50  — max classes listed in MCP default
  DEFAULT_OUTLINE_FUNCTIONS_CAP = 50  — max top_level_functions listed

Response additions (when truncation fires):
  classes_total               — pre-cap count of all classes
  classes_listed              — count actually in the list (== min(total, cap))
  top_level_functions_total   — pre-cap count of all top-level functions
  top_level_functions_listed  — count actually in the list
  listed_cap                  — the cap value that was applied
  truncated                   — bool: True when any list was capped

Statistics (class_count / method_count) are ALWAYS computed over ALL elements,
never over the capped subset — so totals stay honest.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
    DEFAULT_OUTLINE_CLASSES_CAP,
    DEFAULT_OUTLINE_FUNCTIONS_CAP,
    GetCodeOutlineTool,
)

# ---------------------------------------------------------------------------
# Test fixture helpers
# ---------------------------------------------------------------------------


def _make_element(
    element_type: str, name: str, start: int, end: int, **kw
) -> MagicMock:
    elem = MagicMock()
    elem.element_type = element_type
    elem.name = name
    elem.start_line = start
    elem.end_line = end
    elem.parent = None  # clause 6: explicit parent=None prevents OOM
    for k, v in kw.items():
        setattr(elem, k, v)
    return elem


def _make_class_elem(name: str, start: int, end: int) -> MagicMock:
    elem = _make_element("class", name, start, end)
    elem.class_type = "interface"
    elem.extends_class = None
    elem.implements_interfaces = []
    return elem


def _make_method_elem(
    name: str, start: int, end: int, class_start: int = -1
) -> MagicMock:
    """Make a method element; placed inside a class by default (start_line > class_start)."""
    elem = _make_element("function", name, start, end)
    elem.return_type = "void"
    elem.visibility = "public"
    elem.is_constructor = False
    elem.is_static = False
    elem.parameters = []
    elem.receiver_type = None
    return elem


def _make_analysis_result(elements: list, n_classes: int, n_methods: int) -> MagicMock:
    """Synthetic AnalysisResult for n_classes classes each with n_methods methods."""
    result = MagicMock()
    result.elements = elements
    result.file_path = "/proj/giant.d.ts"
    result.language = "typescript"
    result.line_count = n_classes * 20 + 10
    result.success = True
    return result


def _make_giant_elements(n_classes: int, methods_per_class: int = 5) -> list:
    """Build a list of class + method elements for a giant file.

    Each class spans 20 lines; methods are at offsets inside the class body.
    """
    elements = []
    for cls_idx in range(n_classes):
        cls_start = cls_idx * 20 + 1
        cls_end = cls_start + 19
        elements.append(
            _make_class_elem(f"Interface_{cls_idx:04d}", cls_start, cls_end)
        )
        for m_idx in range(methods_per_class):
            m_start = cls_start + m_idx + 1
            elements.append(
                _make_method_elem(
                    f"method_{m_idx:03d}",
                    m_start,
                    m_start + 1,
                )
            )
    return elements


def _run_outline(arguments: dict) -> dict:
    """Execute GetCodeOutlineTool with a mocked analysis engine."""
    tool = GetCodeOutlineTool()
    n_classes = arguments.pop("_n_classes", 80)
    methods_per_class = arguments.pop("_methods_per_class", 5)
    elements = _make_giant_elements(n_classes, methods_per_class)
    analysis_result = _make_analysis_result(
        elements, n_classes, n_classes * methods_per_class
    )

    with (
        patch.object(
            tool, "resolve_and_validate_file_path", return_value="/proj/giant.d.ts"
        ),
        patch("pathlib.Path.exists", return_value=True),
        patch(
            "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.detect_language_mismatch",
            return_value=None,
        ),
        patch(
            "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.detect_language_from_file",
            return_value="typescript",
        ),
        patch.object(
            tool.analysis_engine,
            "analyze",
            new_callable=AsyncMock,
            return_value=analysis_result,
        ),
    ):
        return asyncio.run(tool.execute(arguments))


# ---------------------------------------------------------------------------
# 1. Default cap constants exist at module level
# ---------------------------------------------------------------------------


class TestDefaultCapConstants:
    """Verify the constants are exported from the module."""

    def test_classes_cap_is_50(self):
        assert DEFAULT_OUTLINE_CLASSES_CAP == 50

    def test_functions_cap_is_50(self):
        assert DEFAULT_OUTLINE_FUNCTIONS_CAP == 50


# ---------------------------------------------------------------------------
# 2. Truncation fires on giant fixture (>50 classes)
# ---------------------------------------------------------------------------


class TestGiantFixtureTruncation:
    """structure action=outline on an 80-class fixture: default cap fires."""

    def setup_method(self):
        # 80 classes, 5 methods each — well above the 50-class default cap
        self.result = _run_outline(
            {
                "file_path": "/proj/giant.d.ts",
                "output_format": "json",
                "_n_classes": 80,
                "_methods_per_class": 5,
            }
        )

    def test_truncated_true(self):
        assert self.result["truncated"] is True

    def test_classes_total_is_full_count(self):
        """Pre-cap total == 80, not just the listed slice."""
        assert self.result["classes_total"] == 80

    def test_classes_listed_is_cap(self):
        """Only DEFAULT_OUTLINE_CLASSES_CAP classes are listed."""
        assert self.result["classes_listed"] == 50

    def test_listed_cap_field(self):
        assert self.result["listed_cap"] == 50

    def test_classes_list_length_equals_listed(self):
        """The actual classes list in the response is exactly the cap."""
        assert len(self.result["classes"]) == 50

    def test_classes_list_length_in_outline(self):
        """The outline.classes list is also capped."""
        assert len(self.result["outline"]["classes"]) == 50

    def test_class_count_stat_is_full_total(self):
        """statistics.class_count is the PRE-cap total — always honest."""
        assert self.result["class_count"] == 80
        assert self.result["outline"]["statistics"]["class_count"] == 80

    def test_method_count_stat_is_full_total(self):
        """method_count reflects ALL 400 methods (80 * 5), not just listed."""
        assert self.result["method_count"] == 400
        assert self.result["outline"]["statistics"]["method_count"] == 400

    def test_next_step_hint_present(self):
        """agent_summary.next_step must mention how to narrow."""
        agent_summary = self.result.get("agent_summary", {})
        next_step = agent_summary.get("next_step", "") or ""
        # Should mention the truncation or suggest narrowing
        assert (
            "truncat" in next_step.lower()
            or "listed_cap" in next_step.lower()
            or "cap" in next_step.lower()
        )

    def test_ordering_is_by_start_line(self):
        """Listed classes must be in start_line order (deterministic)."""
        classes = self.result["classes"]
        starts = [c["line_start"] for c in classes]
        assert starts == sorted(starts)


# ---------------------------------------------------------------------------
# 3. No truncation when classes <= cap
# ---------------------------------------------------------------------------


class TestSmallFileNoTruncation:
    """30 classes — below default cap of 50; truncated must be False."""

    def setup_method(self):
        self.result = _run_outline(
            {
                "file_path": "/proj/small.d.ts",
                "output_format": "json",
                "_n_classes": 30,
                "_methods_per_class": 3,
            }
        )

    def test_truncated_false(self):
        assert self.result["truncated"] is False

    def test_classes_total_equals_listed(self):
        assert self.result["classes_total"] == 30
        assert self.result["classes_listed"] == 30

    def test_all_classes_returned(self):
        assert len(self.result["classes"]) == 30

    def test_listed_cap_field_present(self):
        """listed_cap should be present even when not truncating."""
        assert self.result["listed_cap"] == 50


# ---------------------------------------------------------------------------
# 4. Explicit listed_cap param raises the limit
# ---------------------------------------------------------------------------


class TestExplicitCapParam:
    """User passes listed_cap=100 — should show up to 100 classes."""

    def setup_method(self):
        self.result = _run_outline(
            {
                "file_path": "/proj/giant.d.ts",
                "output_format": "json",
                "listed_cap": 100,
                "_n_classes": 80,
                "_methods_per_class": 5,
            }
        )

    def test_all_80_classes_returned_within_explicit_cap(self):
        """80 classes < cap of 100 → all 80 returned, truncated=False."""
        assert self.result["classes_listed"] == 80
        assert self.result["truncated"] is False

    def test_listed_cap_reflects_user_value(self):
        assert self.result["listed_cap"] == 100


class TestExplicitCapBelowDefault:
    """User passes listed_cap=10 (narrower than default 50)."""

    def setup_method(self):
        self.result = _run_outline(
            {
                "file_path": "/proj/giant.d.ts",
                "output_format": "json",
                "listed_cap": 10,
                "_n_classes": 80,
                "_methods_per_class": 5,
            }
        )

    def test_only_10_classes_returned(self):
        assert self.result["classes_listed"] == 10
        assert len(self.result["classes"]) == 10

    def test_truncated_true(self):
        assert self.result["truncated"] is True

    def test_classes_total_still_full(self):
        assert self.result["classes_total"] == 80


# ---------------------------------------------------------------------------
# 5. Summary stats NEVER reflect truncation (aggregate-mode lesson from #505)
# ---------------------------------------------------------------------------


class TestAggregateStatsUnaffectedByTruncation:
    """statistics.class_count / method_count must equal the full element counts.

    This is the aggregate-mode invariant from #505: the cap must NEVER corrupt
    total counts. If class_count were set to listed count, agents would think
    the file is smaller than it is.
    """

    def test_full_class_count_despite_truncation(self):
        result = _run_outline(
            {
                "file_path": "/proj/giant.d.ts",
                "output_format": "json",
                "_n_classes": 80,
                "_methods_per_class": 5,
            }
        )
        # listed is 50 but class_count must be the full 80
        assert result["classes_listed"] == 50
        assert result["class_count"] == 80

    def test_method_count_covers_unlisted_classes(self):
        result = _run_outline(
            {
                "file_path": "/proj/giant.d.ts",
                "output_format": "json",
                "_n_classes": 80,
                "_methods_per_class": 5,
            }
        )
        # 80 classes * 5 methods = 400 total methods, even though only 50 classes listed
        assert result["method_count"] == 400


# ---------------------------------------------------------------------------
# 6. Schema exposes listed_cap parameter
# ---------------------------------------------------------------------------


class TestSchemaHasListedCapParam:
    """GetCodeOutlineTool schema must declare listed_cap so the facade
    whitelist passes it through (not-required, integer, >= 1)."""

    def setup_method(self):
        self.tool = GetCodeOutlineTool()
        self.schema = self.tool.get_tool_schema()

    def test_listed_cap_in_properties(self):
        assert "listed_cap" in self.schema["properties"]

    def test_listed_cap_is_integer(self):
        assert self.schema["properties"]["listed_cap"]["type"] == "integer"

    def test_listed_cap_not_in_required(self):
        """NEVER mark listed_cap required — facade required: trap has hit 6 times."""
        required = self.schema.get("required", [])
        assert "listed_cap" not in required

    def test_listed_cap_has_default(self):
        assert self.schema["properties"]["listed_cap"]["default"] == 50


# ---------------------------------------------------------------------------
# 7. Rule-11 differential invariant: default bytes < unlimited bytes
# ---------------------------------------------------------------------------


class TestByteBudgetDifferentialInvariant:
    """Capped response must be strictly smaller than uncapped.

    Follows the rule-11 differential invariant pattern from DF-13.
    Synthetic fixture has no tmp paths — byte counts are deterministic.
    """

    def _measure_bytes(self, n_classes: int, cap: int) -> int:
        result = _run_outline(
            {
                "file_path": "/proj/giant.d.ts",
                "output_format": "json",
                "listed_cap": cap,
                "_n_classes": n_classes,
                "_methods_per_class": 5,
            }
        )
        return len(json.dumps(result, ensure_ascii=False))

    def test_default_cap_bytes_less_than_unlimited(self):
        """Default (50/80) response must be strictly smaller than uncapped (80/80)."""
        capped_bytes = self._measure_bytes(80, 50)
        uncapped_bytes = self._measure_bytes(80, 80)
        assert capped_bytes < uncapped_bytes, (
            f"default cap ({capped_bytes}B) >= uncapped ({uncapped_bytes}B) — "
            "budget cap is a no-op"
        )

    def test_exact_capped_bytes_pin(self):
        """Exact byte pin for the 80-class / 50-cap synthetic fixture.

        Measure with: python3 -c (see test body) then re-pin if envelope changes.
        Re-measure date: 2026-06-12
        """
        capped_bytes = self._measure_bytes(80, 50)
        # Measured 2026-06-12 — re-pin if response envelope fields change.
        assert capped_bytes == _EXPECTED_CAPPED_BYTES, (
            f"outline capped bytes drifted: {capped_bytes} != {_EXPECTED_CAPPED_BYTES} "
            "— re-measure and re-pin"
        )

    def test_exact_uncapped_bytes_pin(self):
        uncapped_bytes = self._measure_bytes(80, 80)
        assert uncapped_bytes == _EXPECTED_UNCAPPED_BYTES, (
            f"outline uncapped bytes drifted: {uncapped_bytes} != {_EXPECTED_UNCAPPED_BYTES} "
            "— re-measure and re-pin"
        )


# ---------------------------------------------------------------------------
# Byte pins — measured 2026-06-12 with the synthetic fixture.
# capped (50/80 classes, 5 methods each): 99217 B
# uncapped (80/80 classes, 5 methods each): 158804 B  (ratio 1.60x)
# Re-measure and re-pin if response envelope fields change.
# ---------------------------------------------------------------------------
_EXPECTED_CAPPED_BYTES: int = 99217
_EXPECTED_UNCAPPED_BYTES: int = 158804
