"""Tests for AH-012: Test Coverage Analysis."""
from __future__ import annotations

import pytest

from tree_sitter_analyzer.intelligence.architecture_metrics import ArchitectureMetrics
from tree_sitter_analyzer.intelligence.dependency_graph import DependencyGraphBuilder
from tree_sitter_analyzer.intelligence.models import SymbolDefinition, SymbolReference
from tree_sitter_analyzer.intelligence.symbol_index import SymbolIndex


def _build(defs: list[SymbolDefinition], refs: list[SymbolReference]) -> ArchitectureMetrics:
    si = SymbolIndex()
    for d in defs:
        si.add_definition(d)
    for r in refs:
        si.add_reference(r)
    dg = DependencyGraphBuilder()
    return ArchitectureMetrics(dg, si)


# Helper to create test files predicate
def _is_test(path: str) -> bool:
    """Simple test file classifier matching the ProjectIndexer logic."""
    import os
    basename = os.path.basename(path)
    if basename.startswith("test_") and basename.endswith(".py"):
        return True
    if basename.endswith("_test.py"):
        return True
    if basename == "conftest.py":
        return True
    parts = path.replace("\\", "/").split("/")
    for part in parts[:-1]:
        if part in ("tests", "test"):
            return True
    return False


class TestAnalyzeTestCoverage:
    """_analyze_test_coverage must classify symbols by test exposure."""

    def test_untested_symbol_detected(self):
        """A public function with zero test references -> untested."""
        metrics = _build(
            defs=[
                SymbolDefinition("process_data", "src/core.py", 10, 20, "function"),
            ],
            refs=[
                # Only source references, no test references
                SymbolReference("process_data", "src/utils.py", 5, "call"),
            ],
        )
        report = metrics._analyze_test_coverage(scope="", test_file_predicate=_is_test)
        untested_names = [s.name for s in report.untested_symbols]
        assert "process_data" in untested_names

    def test_tested_symbol_not_in_untested(self):
        """A function with at least one test reference -> NOT untested."""
        metrics = _build(
            defs=[
                SymbolDefinition("process_data", "src/core.py", 10, 20, "function"),
            ],
            refs=[
                SymbolReference("process_data", "tests/test_core.py", 15, "call"),
            ],
        )
        report = metrics._analyze_test_coverage(scope="", test_file_predicate=_is_test)
        untested_names = [s.name for s in report.untested_symbols]
        assert "process_data" not in untested_names

    def test_overtested_symbol_detected(self):
        """A function with >threshold distinct test function references -> overtested."""
        refs = [
            SymbolReference("compute", f"tests/test_{i}.py", i + 1, "call", context_function=f"test_fn_{i}")
            for i in range(12)
        ]
        metrics = _build(
            defs=[
                SymbolDefinition("compute", "src/engine.py", 10, 20, "function"),
            ],
            refs=refs,
        )
        report = metrics._analyze_test_coverage(
            scope="", test_file_predicate=_is_test, overtested_threshold=10,
        )
        overtested_names = [s.name for s in report.overtested_symbols]
        assert "compute" in overtested_names

    def test_not_overtested_below_threshold(self):
        """Below threshold -> not overtested."""
        refs = [
            SymbolReference("compute", f"tests/test_{i}.py", i + 1, "call", context_function=f"test_fn_{i}")
            for i in range(5)
        ]
        metrics = _build(
            defs=[
                SymbolDefinition("compute", "src/engine.py", 10, 20, "function"),
            ],
            refs=refs,
        )
        report = metrics._analyze_test_coverage(
            scope="", test_file_predicate=_is_test, overtested_threshold=10,
        )
        overtested_names = [s.name for s in report.overtested_symbols]
        assert "compute" not in overtested_names

    def test_test_only_symbol_detected(self):
        """A symbol referenced ONLY from test files -> test_only."""
        metrics = _build(
            defs=[
                SymbolDefinition("helper_fixture", "src/helpers.py", 10, 20, "function"),
            ],
            refs=[
                SymbolReference("helper_fixture", "tests/test_a.py", 5, "call"),
                SymbolReference("helper_fixture", "tests/test_b.py", 10, "import"),
            ],
        )
        report = metrics._analyze_test_coverage(scope="", test_file_predicate=_is_test)
        assert "helper_fixture" in report.test_only_symbols

    def test_not_test_only_when_source_also_references(self):
        """If source code also references it -> not test_only."""
        metrics = _build(
            defs=[
                SymbolDefinition("shared_util", "src/utils.py", 10, 20, "function"),
            ],
            refs=[
                SymbolReference("shared_util", "src/core.py", 5, "call"),
                SymbolReference("shared_util", "tests/test_core.py", 10, "call"),
            ],
        )
        report = metrics._analyze_test_coverage(scope="", test_file_predicate=_is_test)
        assert "shared_util" not in report.test_only_symbols

    def test_coverage_ratio(self):
        """coverage_ratio = tested / total public symbols."""
        metrics = _build(
            defs=[
                SymbolDefinition("func_a", "src/mod.py", 1, 5, "function"),
                SymbolDefinition("func_b", "src/mod.py", 10, 15, "function"),
                SymbolDefinition("func_c", "src/mod.py", 20, 25, "function"),
                SymbolDefinition("_private", "src/mod.py", 30, 35, "function"),  # private
            ],
            refs=[
                SymbolReference("func_a", "tests/test_mod.py", 5, "call"),
                SymbolReference("func_b", "tests/test_mod.py", 10, "call"),
                # func_c has no test ref
            ],
        )
        report = metrics._analyze_test_coverage(scope="", test_file_predicate=_is_test)
        # 3 public symbols, 2 tested -> 2/3
        assert abs(report.coverage_ratio - 2 / 3) < 0.01

    def test_private_symbols_excluded(self):
        """Symbols starting with _ are excluded from untested analysis."""
        metrics = _build(
            defs=[
                SymbolDefinition("_internal", "src/core.py", 10, 20, "function"),
            ],
            refs=[],
        )
        report = metrics._analyze_test_coverage(scope="", test_file_predicate=_is_test)
        untested_names = [s.name for s in report.untested_symbols]
        assert "_internal" not in untested_names

    def test_test_file_definitions_excluded(self):
        """Definitions in test files should not be analysed as 'untested source'."""
        metrics = _build(
            defs=[
                SymbolDefinition("test_helper", "tests/conftest.py", 10, 20, "function"),
            ],
            refs=[],
        )
        report = metrics._analyze_test_coverage(scope="", test_file_predicate=_is_test)
        untested_names = [s.name for s in report.untested_symbols]
        assert "test_helper" not in untested_names

    def test_scope_filters_definitions(self):
        """Only definitions within scope are analysed."""
        metrics = _build(
            defs=[
                SymbolDefinition("in_scope", "src/core.py", 10, 20, "function"),
                SymbolDefinition("out_scope", "lib/other.py", 10, 20, "function"),
            ],
            refs=[],
        )
        report = metrics._analyze_test_coverage(scope="src/", test_file_predicate=_is_test)
        untested_names = [s.name for s in report.untested_symbols]
        assert "in_scope" in untested_names
        assert "out_scope" not in untested_names


class TestAH013PropertyAndInnerFunctionExclusion:
    """AH-013: @property and inner functions must NOT appear in untested_symbols."""

    def test_property_method_excluded_from_untested(self):
        """A @property method with no test refs should NOT be untested (attribute access)."""
        metrics = _build(
            defs=[
                SymbolDefinition(
                    "instability", "src/models.py", 135, 140, "method",
                    modifiers=["property"],
                ),
            ],
            refs=[],  # no references at all
        )
        report = metrics._analyze_test_coverage(scope="", test_file_predicate=_is_test)
        untested_names = [s.name for s in report.untested_symbols]
        assert "instability" not in untested_names

    def test_staticmethod_excluded_from_untested(self):
        """A @staticmethod with no test refs should NOT be untested."""
        metrics = _build(
            defs=[
                SymbolDefinition(
                    "is_test_file", "src/indexer.py", 50, 60, "method",
                    modifiers=["staticmethod"],
                ),
            ],
            refs=[],
        )
        report = metrics._analyze_test_coverage(scope="", test_file_predicate=_is_test)
        untested_names = [s.name for s in report.untested_symbols]
        assert "is_test_file" not in untested_names

    def test_classmethod_excluded_from_untested(self):
        """A @classmethod with no test refs should NOT be untested."""
        metrics = _build(
            defs=[
                SymbolDefinition(
                    "from_config", "src/factory.py", 20, 30, "method",
                    modifiers=["classmethod"],
                ),
            ],
            refs=[],
        )
        report = metrics._analyze_test_coverage(scope="", test_file_predicate=_is_test)
        untested_names = [s.name for s in report.untested_symbols]
        assert "from_config" not in untested_names

    def test_inner_function_excluded_from_untested(self):
        """A nested function (has context_function in its definition) should be excluded."""
        metrics = _build(
            defs=[
                # Inner function 'wrapper' inside 'handle_exceptions'
                SymbolDefinition(
                    "wrapper", "src/exceptions.py", 318, 340, "function",
                    parent_class=None,
                ),
                # The enclosing decorator that also defines 'decorator' inside it
                SymbolDefinition(
                    "decorator", "src/exceptions.py", 317, 345, "function",
                    parent_class=None,
                ),
                # The outer function
                SymbolDefinition(
                    "handle_exceptions", "src/exceptions.py", 310, 350, "function",
                    parent_class=None,
                ),
            ],
            refs=[
                # Only handle_exceptions has test refs; inner functions do not
                SymbolReference("handle_exceptions", "tests/test_exc.py", 5, "call"),
            ],
        )
        report = metrics._analyze_test_coverage(scope="", test_file_predicate=_is_test)
        untested_names = [s.name for s in report.untested_symbols]
        # Inner functions should not be untested if enclosing function is tested
        assert "wrapper" not in untested_names
        assert "decorator" not in untested_names

    def test_property_excluded_but_not_counted_in_public(self):
        """Properties excluded from untested should also not inflate total_public."""
        metrics = _build(
            defs=[
                SymbolDefinition("func_a", "src/mod.py", 1, 5, "function"),
                SymbolDefinition(
                    "prop_b", "src/mod.py", 10, 15, "method",
                    modifiers=["property"],
                ),
            ],
            refs=[
                SymbolReference("func_a", "tests/test_mod.py", 5, "call"),
            ],
        )
        report = metrics._analyze_test_coverage(scope="", test_file_predicate=_is_test)
        # Only func_a is public+eligible -> 1 total, 1 tested -> ratio = 1.0
        assert abs(report.coverage_ratio - 1.0) < 0.01

    def test_regular_method_still_untested(self):
        """A normal method without modifiers should still be reported as untested."""
        metrics = _build(
            defs=[
                SymbolDefinition("old_helper", "src/utils.py", 10, 20, "function"),
            ],
            refs=[],
        )
        report = metrics._analyze_test_coverage(scope="", test_file_predicate=_is_test)
        untested_names = [s.name for s in report.untested_symbols]
        assert "old_helper" in untested_names


class TestAH014OvertestedScopedByFile:
    """AH-014: Overtested counts must be scoped by (file_path, name)."""

    def test_same_name_different_files_not_aggregated(self):
        """execute in tools/a.py (5 refs) + tools/b.py (5 refs) should NOT be overtested."""
        metrics = _build(
            defs=[
                SymbolDefinition("execute", "tools/a.py", 10, 50, "method"),
                SymbolDefinition("execute", "tools/b.py", 10, 50, "method"),
            ],
            refs=[
                # 5 test refs for tools/a.py execute
                *[SymbolReference("execute", f"tests/test_a_{i}.py", i, "call",
                                  context_function=f"test_a_{i}") for i in range(5)],
                # 5 test refs for tools/b.py execute
                *[SymbolReference("execute", f"tests/test_b_{i}.py", i, "call",
                                  context_function=f"test_b_{i}") for i in range(5)],
            ],
        )
        report = metrics._analyze_test_coverage(
            scope="", test_file_predicate=_is_test, overtested_threshold=8,
        )
        # Neither should be overtested: 5 < 8 threshold for each
        overtested_names = [s.name for s in report.overtested_symbols]
        assert "execute" not in overtested_names

    def test_single_file_truly_overtested(self):
        """A single file's method with 15 distinct test refs IS overtested."""
        refs = [
            SymbolReference("process", f"tests/test_{i}.py", i + 1, "call",
                            context_function=f"test_fn_{i}")
            for i in range(15)
        ]
        metrics = _build(
            defs=[
                SymbolDefinition("process", "src/engine.py", 10, 20, "function"),
            ],
            refs=refs,
        )
        report = metrics._analyze_test_coverage(
            scope="", test_file_predicate=_is_test, overtested_threshold=10,
        )
        overtested_names = [s.name for s in report.overtested_symbols]
        assert "process" in overtested_names
        # Verify it references the correct file
        match = [s for s in report.overtested_symbols if s.name == "process"]
        assert match[0].file_path == "src/engine.py"
        assert match[0].test_ref_count == 15

    def test_overtested_entries_have_file_path(self):
        """Each overtested entry must have the specific file_path, not just the name.

        With 2 definitions, refs are split proportionally (30/2 = 15 per def).
        """
        refs_a = [
            SymbolReference("run", f"tests/test_a_{i}.py", i, "call",
                            context_function=f"test_a_{i}") for i in range(25)
        ]
        refs_b = [
            SymbolReference("run", f"tests/test_b_{i}.py", i, "call",
                            context_function=f"test_b_{i}") for i in range(5)
        ]
        metrics = _build(
            defs=[
                SymbolDefinition("run", "src/runner.py", 10, 50, "function"),
                SymbolDefinition("run", "src/server.py", 10, 50, "function"),
            ],
            refs=refs_a + refs_b,
        )
        report = metrics._analyze_test_coverage(
            scope="", test_file_predicate=_is_test, overtested_threshold=10,
        )
        # With 30 refs / 2 defs = 15 per def > 10 threshold
        # Both definitions should be overtested
        overtested = report.overtested_symbols
        overtested_files = [(s.name, s.file_path) for s in overtested]
        # At least one entry with the file path for "run"
        assert any(name == "run" for name, _fp in overtested_files)
        # Each entry has the specific file_path
        for entry in overtested:
            assert entry.file_path in ("src/runner.py", "src/server.py")
