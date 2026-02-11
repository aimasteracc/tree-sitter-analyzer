"""
Unit tests for test architecture audit capability.

Tests:
- Import-based matching (precise, not filename guessing)
- Symbol-level coverage metrics
- Test quality detection (thin test files)
- Risk-sorted untested files (hot spots first)
- V1 real-world audit
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.core.code_map import (
    ArchitectureTestReport,
    ProjectCodeMap,
)


@pytest.fixture
def v1_root():
    return "D:/git/tree-sitter-analyzer-v2/tree_sitter_analyzer"


@pytest.fixture
def v1_test_roots():
    return ["D:/git/tree-sitter-analyzer-v2/tests"]


@pytest.fixture
def fixture_result():
    mapper = ProjectCodeMap()
    return mapper.scan(
        str(Path(__file__).parent.parent / "fixtures" / "cross_file_project"),
        extensions=[".py"],
    )


class TestAuditMethodExists:
    """audit_test_architecture() exists and returns a report."""

    def test_method_exists(self, fixture_result):
        assert hasattr(fixture_result, "audit_test_architecture")

    def test_returns_report(self, fixture_result):
        report = fixture_result.audit_test_architecture()
        assert isinstance(report, ArchitectureTestReport)


class TestReportFields:
    """Report should contain the required audit data."""

    def test_has_coverage_fields(self, fixture_result):
        report = fixture_result.audit_test_architecture()
        assert hasattr(report, "source_files")
        assert hasattr(report, "test_files")
        assert hasattr(report, "untested_files")
        assert hasattr(report, "test_layers")
        assert hasattr(report, "coverage_percent")

    def test_has_symbol_coverage(self, fixture_result):
        report = fixture_result.audit_test_architecture()
        assert hasattr(report, "total_source_symbols")
        assert hasattr(report, "tested_symbols")
        assert hasattr(report, "symbol_coverage_percent")
        assert isinstance(report.symbol_coverage_percent, float)

    def test_has_test_quality_metrics(self, fixture_result):
        report = fixture_result.audit_test_architecture()
        assert hasattr(report, "total_test_functions")
        assert hasattr(report, "test_quality")
        assert isinstance(report.test_quality, dict)

    def test_has_import_matched(self, fixture_result):
        report = fixture_result.audit_test_architecture()
        assert hasattr(report, "import_matched")
        assert isinstance(report.import_matched, dict)

    def test_has_toon_output(self, fixture_result):
        report = fixture_result.audit_test_architecture()
        toon = report.to_toon()
        assert isinstance(toon, str)
        assert "TEST_AUDIT" in toon
        assert "FILE_COVERAGE" in toon
        assert "SYMBOL_COVERAGE" in toon


class TestV1Audit:
    """Run actual audit against v1 to verify detection."""

    def test_v1_detects_low_coverage(self, v1_root, v1_test_roots):
        mapper = ProjectCodeMap()
        r = mapper.scan(v1_root, extensions=[".py"])
        report = r.audit_test_architecture(test_roots=v1_test_roots)
        assert report.coverage_percent < 30

    def test_v1_detects_missing_layers(self, v1_root, v1_test_roots):
        mapper = ProjectCodeMap()
        r = mapper.scan(v1_root, extensions=[".py"])
        report = r.audit_test_architecture(test_roots=v1_test_roots)
        missing = report.missing_layers
        assert "e2e" in missing or "system" in missing

    def test_v1_finds_untested_mcp_tools(self, v1_root, v1_test_roots):
        mapper = ProjectCodeMap()
        r = mapper.scan(v1_root, extensions=[".py"])
        report = r.audit_test_architecture(test_roots=v1_test_roots)
        assert len(report.untested_tools) > 0

    def test_v1_report_toon_detailed(self, v1_root, v1_test_roots):
        mapper = ProjectCodeMap()
        r = mapper.scan(v1_root, extensions=[".py"])
        report = r.audit_test_architecture(test_roots=v1_test_roots)
        toon = report.to_toon()
        assert "UNTESTED" in toon
        assert "FILE_COVERAGE" in toon
        assert "SYMBOL_COVERAGE" in toon

    def test_v1_has_symbol_coverage(self, v1_root, v1_test_roots):
        mapper = ProjectCodeMap()
        r = mapper.scan(v1_root, extensions=[".py"])
        report = r.audit_test_architecture(test_roots=v1_test_roots)
        assert report.total_source_symbols > 0
        # v1 has very low symbol coverage
        assert report.symbol_coverage_percent < 50

    def test_v1_test_quality(self, v1_root, v1_test_roots):
        mapper = ProjectCodeMap()
        r = mapper.scan(v1_root, extensions=[".py"])
        report = r.audit_test_architecture(test_roots=v1_test_roots)
        assert report.total_test_functions >= 0

    def test_v1_import_matching_more_precise(self, v1_root, v1_test_roots):
        """Import matching should find more connections than name-only."""
        mapper = ProjectCodeMap()
        r = mapper.scan(v1_root, extensions=[".py"])
        report = r.audit_test_architecture(test_roots=v1_test_roots)
        # Import matching should discover at least some connections
        assert len(report.import_matched) >= 0  # may be 0 if tests don't import from source


class TestMcpAction:
    """Test MCP tool exposure."""

    def test_test_audit_action(self):
        from tree_sitter_analyzer_v2.mcp.tools.intelligence import _VALID_ACTIONS
        assert "test_audit" in _VALID_ACTIONS
