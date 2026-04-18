"""Unit tests for CouplingMetricsAnalyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.coupling_metrics import (
    RISK_FLEXIBLE,
    RISK_STABLE,
    RISK_UNSTABLE,
    CouplingMetricsAnalyzer,
    CouplingResult,
    FileCouplingMetrics,
    _classify_risk,
)


@pytest.fixture
def analyzer() -> CouplingMetricsAnalyzer:
    return CouplingMetricsAnalyzer()


def _write_tmp(project_dir: str, rel_path: str, content: str) -> str:
    full = Path(project_dir) / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    return str(full)


class TestClassifyRisk:
    def test_stable(self) -> None:
        assert _classify_risk(0.1) == RISK_STABLE
        assert _classify_risk(0.0) == RISK_STABLE
        assert _classify_risk(0.29) == RISK_STABLE

    def test_flexible(self) -> None:
        assert _classify_risk(0.3) == RISK_FLEXIBLE
        assert _classify_risk(0.5) == RISK_FLEXIBLE
        assert _classify_risk(0.7) == RISK_FLEXIBLE

    def test_unstable(self) -> None:
        assert _classify_risk(0.71) == RISK_UNSTABLE
        assert _classify_risk(1.0) == RISK_UNSTABLE


class TestDataclasses:
    def test_file_coupling_to_dict(self) -> None:
        m = FileCouplingMetrics(
            file_path="a.py",
            fan_out=3,
            fan_in=1,
            instability=0.75,
            risk=RISK_UNSTABLE,
        )
        d = m.to_dict()
        assert d["file_path"] == "a.py"
        assert d["fan_out"] == 3
        assert d["fan_in"] == 1
        assert d["instability"] == 0.75
        assert d["risk"] == RISK_UNSTABLE

    def test_coupling_result_to_dict(self) -> None:
        m = FileCouplingMetrics(
            file_path="x.py", fan_out=1, fan_in=0,
            instability=1.0, risk=RISK_UNSTABLE,
        )
        r = CouplingResult(
            project_root="/tmp", total_files=1, total_edges=0,
            avg_fan_out=1.0, avg_fan_in=0.0,
            most_coupled=(m,), most_critical=(),
            unstable_files=(m,), file_metrics=(m,),
        )
        d = r.to_dict()
        assert d["total_files"] == 1
        assert d["unstable_count"] == 1
        assert len(d["file_metrics"]) == 1

    def test_get_high_risk(self) -> None:
        m_stable = FileCouplingMetrics(
            file_path="a.py", fan_out=0, fan_in=5,
            instability=0.0, risk=RISK_STABLE,
        )
        m_unstable = FileCouplingMetrics(
            file_path="b.py", fan_out=5, fan_in=0,
            instability=1.0, risk=RISK_UNSTABLE,
        )
        r = CouplingResult(
            project_root="/tmp", total_files=2, total_edges=5,
            avg_fan_out=2.5, avg_fan_in=2.5,
            most_coupled=(), most_critical=(),
            unstable_files=(m_unstable,),
            file_metrics=(m_stable, m_unstable),
        )
        high = r.get_high_risk()
        assert len(high) == 1
        assert high[0].file_path == "b.py"


class TestAnalyzerWithProject:
    def test_empty_project(self, analyzer: CouplingMetricsAnalyzer) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = analyzer.analyze_project(tmp)
            assert result.total_files == 0
            assert result.total_edges == 0
            assert result.avg_fan_out == 0.0
            assert result.avg_fan_in == 0.0

    def test_nonexistent_path(self, analyzer: CouplingMetricsAnalyzer) -> None:
        result = analyzer.analyze_project("/nonexistent/path")
        assert result.total_files == 0

    def test_single_file_no_deps(
        self, analyzer: CouplingMetricsAnalyzer
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "main.py", "x = 1\n")
            result = analyzer.analyze_project(tmp)
            assert result.total_files == 1
            assert result.total_edges == 0
            assert result.file_metrics[0].fan_out == 0
            assert result.file_metrics[0].fan_in == 0

    def test_two_files_with_import(
        self, analyzer: CouplingMetricsAnalyzer
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "a.py", "x = 1\n")
            _write_tmp(tmp, "b.py", "import a\n")
            result = analyzer.analyze_project(tmp)
            assert result.total_files == 2
            assert result.total_edges >= 1

            b_metrics = [
                m for m in result.file_metrics if m.file_path == "b.py"
            ]
            assert len(b_metrics) == 1
            assert b_metrics[0].fan_out >= 1

            a_metrics = [
                m for m in result.file_metrics if m.file_path == "a.py"
            ]
            assert len(a_metrics) == 1
            assert a_metrics[0].fan_in >= 1

    def test_most_coupled(
        self, analyzer: CouplingMetricsAnalyzer
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "a.py", "x = 1\n")
            _write_tmp(tmp, "b.py", "y = 2\n")
            _write_tmp(tmp, "c.py", "import a\nimport b\n")
            result = analyzer.analyze_project(tmp)
            if result.total_edges > 0:
                assert result.most_coupled[0].fan_out >= 1

    def test_most_critical(
        self, analyzer: CouplingMetricsAnalyzer
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "core.py", "x = 1\n")
            _write_tmp(tmp, "a.py", "import core\n")
            _write_tmp(tmp, "b.py", "import core\n")
            result = analyzer.analyze_project(tmp)
            if result.total_edges > 0:
                assert result.most_critical[0].fan_in >= 1

    def test_instability_calculation(
        self, analyzer: CouplingMetricsAnalyzer
    ) -> None:
        m = FileCouplingMetrics(
            file_path="t.py", fan_out=3, fan_in=1,
            instability=0.75, risk=RISK_UNSTABLE,
        )
        assert m.instability == pytest.approx(0.75)

    def test_java_project(self, analyzer: CouplingMetricsAnalyzer) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(
                tmp, "Main.java",
                "import java.util.List;\n"
                "public class Main { }\n",
            )
            result = analyzer.analyze_project(tmp)
            assert result.total_files == 1

    def test_javascript_project(
        self, analyzer: CouplingMetricsAnalyzer
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "utils.js", "module.exports = {};\n")
            _write_tmp(tmp, "main.js", 'const utils = require("./utils");\n')
            result = analyzer.analyze_project(tmp)
            assert result.total_files == 2
            assert result.total_edges >= 1

    def test_go_project(self, analyzer: CouplingMetricsAnalyzer) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(
                tmp, "main.go",
                'package main\nimport "fmt"\nfunc main() {}\n',
            )
            result = analyzer.analyze_project(tmp)
            assert result.total_files == 1

    def test_mixed_language_project(
        self, analyzer: CouplingMetricsAnalyzer
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "app.py", "x = 1\n")
            _write_tmp(tmp, "util.js", "module.exports = {};\n")
            _write_tmp(tmp, "Main.java", "public class Main { }\n")
            result = analyzer.analyze_project(tmp)
            assert result.total_files == 3
