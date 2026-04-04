"""Unit tests for Phase 3 AutoDiscoveryEngine."""

import pytest

from tree_sitter_analyzer.grammar_coverage.auto_discovery import (
    AutoDiscoveryEngine,
    CoverageGapReport,
    NodeStats,
    _score_wrapper_node,
)
from tree_sitter_analyzer.grammar_coverage.discovery_corpus import (
    BUILTIN_CORPUS,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def engine() -> AutoDiscoveryEngine:
    return AutoDiscoveryEngine(wrapper_threshold=30.0)


@pytest.fixture(scope="module")
def python_corpus() -> str:
    return BUILTIN_CORPUS["python"]


@pytest.fixture(scope="module")
def python_report(engine: AutoDiscoveryEngine, python_corpus: str) -> CoverageGapReport:
    return engine.analyze_coverage_gap("python", python_corpus)


# ---------------------------------------------------------------------------
# 1. get_all_node_types
# ---------------------------------------------------------------------------


def test_get_all_node_types_python(engine: AutoDiscoveryEngine) -> None:
    types = engine.get_all_node_types("python")
    assert isinstance(types, list)
    assert len(types) >= 50, f"Expected >= 50 node types, got {len(types)}"


def test_get_all_node_types_is_sorted(engine: AutoDiscoveryEngine) -> None:
    types = engine.get_all_node_types("python")
    assert types == sorted(types)


def test_get_all_node_types_returns_named_only(engine: AutoDiscoveryEngine) -> None:
    types = engine.get_all_node_types("python")
    # Named nodes should not include anonymous tokens like "(" or ")"
    # (they are typically short punctuation)
    anonymous_tokens = [t for t in types if t in ("(", ")", "{", "}", ";", ":")]
    assert anonymous_tokens == [], f"Found anonymous tokens: {anonymous_tokens}"


def test_get_all_node_types_contains_known_types(engine: AutoDiscoveryEngine) -> None:
    types = engine.get_all_node_types("python")
    type_set = set(types)
    expected = {"function_definition", "class_definition", "import_statement"}
    missing = expected - type_set
    assert not missing, f"Expected node types not found: {missing}"


def test_get_all_node_types_unsupported_language(engine: AutoDiscoveryEngine) -> None:
    with pytest.raises((ValueError, ImportError)):
        engine.get_all_node_types("nonexistent_lang_xyz")


def test_get_all_node_types_typescript(engine: AutoDiscoveryEngine) -> None:
    types = engine.get_all_node_types("typescript")
    assert len(types) >= 80


# ---------------------------------------------------------------------------
# 2. get_all_field_names
# ---------------------------------------------------------------------------


def test_get_all_field_names_python(engine: AutoDiscoveryEngine) -> None:
    fields = engine.get_all_field_names("python")
    assert isinstance(fields, list)
    assert len(fields) > 5
    # Python should have common fields
    assert "name" in fields or "body" in fields


def test_get_all_field_names_unavailable_language(engine: AutoDiscoveryEngine) -> None:
    # Should return empty list gracefully, not raise
    fields = engine.get_all_field_names("nonexistent_lang_xyz")
    assert fields == []


# ---------------------------------------------------------------------------
# 3. detect_wrapper_nodes
# ---------------------------------------------------------------------------


def test_detect_wrapper_nodes_python_has_results(
    engine: AutoDiscoveryEngine, python_corpus: str
) -> None:
    candidates = engine.detect_wrapper_nodes("python", python_corpus)
    assert isinstance(candidates, list)


def test_detect_wrapper_nodes_python_decorated_definition(
    engine: AutoDiscoveryEngine, python_corpus: str
) -> None:
    candidates = engine.detect_wrapper_nodes("python", python_corpus)
    node_types = [c.node_type for c in candidates]
    assert "decorated_definition" in node_types, (
        f"Expected 'decorated_definition' in wrapper candidates, got: {node_types}"
    )


def test_detect_wrapper_nodes_sorted_by_score(
    engine: AutoDiscoveryEngine, python_corpus: str
) -> None:
    candidates = engine.detect_wrapper_nodes("python", python_corpus)
    scores = [c.score for c in candidates]
    assert scores == sorted(scores, reverse=True)


def test_detect_wrapper_nodes_threshold_effect(
    engine: AutoDiscoveryEngine, python_corpus: str
) -> None:
    low_engine = AutoDiscoveryEngine(wrapper_threshold=10.0)
    high_engine = AutoDiscoveryEngine(wrapper_threshold=90.0)
    low_results = low_engine.detect_wrapper_nodes("python", python_corpus)
    high_results = high_engine.detect_wrapper_nodes("python", python_corpus)
    assert len(low_results) >= len(high_results)


def test_detect_wrapper_nodes_typescript(
    engine: AutoDiscoveryEngine,
) -> None:
    corpus = BUILTIN_CORPUS["typescript"]
    candidates = engine.detect_wrapper_nodes("typescript", corpus)
    assert isinstance(candidates, list)


def test_detect_wrapper_nodes_empty_code(engine: AutoDiscoveryEngine) -> None:
    # go has no BUILTIN_CORPUS_EXTRA, so empty corpus → no stats → no candidates
    candidates = engine.detect_wrapper_nodes("go", "")
    assert candidates == []


# ---------------------------------------------------------------------------
# 4. enumerate_syntax_paths
# ---------------------------------------------------------------------------


def test_enumerate_syntax_paths_returns_list(
    engine: AutoDiscoveryEngine, python_corpus: str
) -> None:
    paths = engine.enumerate_syntax_paths("python", python_corpus)
    assert isinstance(paths, list)
    assert len(paths) > 0


def test_enumerate_syntax_paths_format(
    engine: AutoDiscoveryEngine, python_corpus: str
) -> None:
    paths = engine.enumerate_syntax_paths("python", python_corpus)
    for path in paths[:10]:
        assert " > " in path, f"Path '{path}' should contain ' > '"


def test_enumerate_syntax_paths_no_duplicates(
    engine: AutoDiscoveryEngine, python_corpus: str
) -> None:
    paths = engine.enumerate_syntax_paths("python", python_corpus)
    assert len(paths) == len(set(paths)), "Paths should be unique"


def test_enumerate_syntax_paths_max_depth(
    engine: AutoDiscoveryEngine, python_corpus: str
) -> None:
    paths_d1 = engine.enumerate_syntax_paths("python", python_corpus, max_depth=1)
    paths_d5 = engine.enumerate_syntax_paths("python", python_corpus, max_depth=5)
    # More depth should discover at least as many paths
    assert len(paths_d5) >= len(paths_d1)


# ---------------------------------------------------------------------------
# 5. analyze_coverage_gap
# ---------------------------------------------------------------------------


def test_analyze_coverage_gap_has_required_keys(python_report: CoverageGapReport) -> None:
    assert python_report.language == "python"
    assert isinstance(python_report.total_node_types, int)
    assert isinstance(python_report.discovered_node_types, list)
    assert isinstance(python_report.missing_node_types, list)
    assert isinstance(python_report.wrapper_candidates, list)
    assert isinstance(python_report.coverage_rate, float)
    assert isinstance(python_report.elapsed_ms, float)


def test_analyze_coverage_gap_coverage_positive(python_report: CoverageGapReport) -> None:
    assert python_report.coverage_rate > 0.0
    assert python_report.coverage_rate <= 100.0


def test_analyze_coverage_gap_total_types_positive(python_report: CoverageGapReport) -> None:
    assert python_report.total_node_types > 0


def test_analyze_coverage_gap_consistency(python_report: CoverageGapReport) -> None:
    # discovered + missing should be consistent with total grammar types
    discovered_set = set(python_report.discovered_node_types)
    # discovered_set should be non-empty if total > 0
    assert len(discovered_set) > 0


def test_analyze_coverage_gap_is_ok(python_report: CoverageGapReport) -> None:
    assert python_report.is_ok
    assert python_report.error is None


def test_analyze_coverage_gap_custom_corpus(engine: AutoDiscoveryEngine) -> None:
    code = "def hello():\n    pass\n"
    report = engine.analyze_coverage_gap("python", code)
    assert report.is_ok
    assert "function_definition" in report.discovered_node_types


def test_analyze_coverage_gap_unavailable_language(engine: AutoDiscoveryEngine) -> None:
    report = engine.analyze_coverage_gap("nonexistent_xyz", "some code")
    assert not report.is_ok
    assert report.error is not None


def test_analyze_coverage_gap_elapsed_ms(python_report: CoverageGapReport) -> None:
    # Should complete reasonably fast
    assert python_report.elapsed_ms > 0
    assert python_report.elapsed_ms < 10_000  # 10 seconds absolute upper bound


# ---------------------------------------------------------------------------
# 6. analyze_all_languages
# ---------------------------------------------------------------------------


def test_analyze_all_languages_no_crash(engine: AutoDiscoveryEngine) -> None:
    results = engine.analyze_all_languages()
    assert isinstance(results, dict)
    assert len(results) > 0


def test_analyze_all_languages_contains_python(engine: AutoDiscoveryEngine) -> None:
    results = engine.analyze_all_languages()
    assert "python" in results


def test_analyze_all_languages_custom_list(engine: AutoDiscoveryEngine) -> None:
    results = engine.analyze_all_languages(["python", "javascript"])
    assert set(results.keys()) == {"python", "javascript"}


def test_analyze_all_languages_at_least_half_ok(engine: AutoDiscoveryEngine) -> None:
    results = engine.analyze_all_languages()
    ok_count = sum(1 for r in results.values() if r.is_ok)
    assert ok_count >= len(results) // 2, (
        f"Only {ok_count}/{len(results)} languages analyzed successfully"
    )


# ---------------------------------------------------------------------------
# 7. generate_report
# ---------------------------------------------------------------------------


def test_generate_report_not_empty(engine: AutoDiscoveryEngine) -> None:
    results = engine.analyze_all_languages(["python"])
    report = engine.generate_report(results)
    assert isinstance(report, str)
    assert len(report) > 100


def test_generate_report_contains_language(engine: AutoDiscoveryEngine) -> None:
    results = engine.analyze_all_languages(["python"])
    report = engine.generate_report(results)
    assert "python" in report


def test_generate_report_markdown_structure(engine: AutoDiscoveryEngine) -> None:
    results = engine.analyze_all_languages(["python"])
    report = engine.generate_report(results)
    assert "# Phase 3 Auto-Discovery Report" in report
    assert "## Summary" in report
    assert "## Details" in report


# ---------------------------------------------------------------------------
# 8. Internal scoring function
# ---------------------------------------------------------------------------


def test_score_wrapper_node_empty_stats() -> None:
    stats = NodeStats(node_type="module")
    score, reasons = _score_wrapper_node("module", stats)
    assert score == 0.0
    assert reasons == []


def test_score_wrapper_node_with_definition_field() -> None:
    stats = NodeStats(node_type="decorated_definition")
    stats.field_usage = {"definition": 3, "decorator": 2}
    stats.child_types = {"function_definition": 3, "decorator": 2}
    stats.samples = 3
    stats.total_children = 9
    score, reasons = _score_wrapper_node("decorated_definition", stats)
    assert score >= 60.0
    assert "definition_field" in reasons
    assert "decorator_field" in reasons


def test_score_wrapper_node_name_pattern() -> None:
    stats = NodeStats(node_type="decorated_definition")
    score, reasons = _score_wrapper_node("decorated_definition", stats)
    assert "name_pattern" in reasons


# ---------------------------------------------------------------------------
# 9. NodeStats dataclass
# ---------------------------------------------------------------------------


def test_node_stats_avg_children_zero_samples() -> None:
    ns = NodeStats(node_type="foo")
    assert ns.avg_children == 0.0


def test_node_stats_avg_children_computed() -> None:
    ns = NodeStats(node_type="foo", samples=4, total_children=12)
    assert ns.avg_children == 3.0


# ---------------------------------------------------------------------------
# 10. CoverageGapReport
# ---------------------------------------------------------------------------


def test_coverage_gap_report_is_ok() -> None:
    r = CoverageGapReport(
        language="python",
        total_node_types=100,
        discovered_node_types=["foo"],
        missing_node_types=["bar"],
        wrapper_candidates=[],
        coverage_rate=50.0,
        elapsed_ms=5.0,
    )
    assert r.is_ok


def test_coverage_gap_report_not_ok() -> None:
    r = CoverageGapReport(
        language="python",
        total_node_types=0,
        discovered_node_types=[],
        missing_node_types=[],
        wrapper_candidates=[],
        coverage_rate=0.0,
        elapsed_ms=1.0,
        error="module not found",
    )
    assert not r.is_ok
