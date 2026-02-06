"""
Tests for features/cicd_integration.py module.

TDD: Testing CI/CD integration functionality.
"""

import json
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.features.cicd_integration import (
    ExitCode,
    Issue,
    CICDReport,
    CICDConfig,
    generate_cicd_report,
)


class TestExitCode:
    """Test ExitCode enum."""

    def test_exit_codes(self) -> None:
        """Should have correct exit codes."""
        assert ExitCode.SUCCESS.value == 0
        assert ExitCode.WARNINGS.value == 1
        assert ExitCode.ERRORS.value == 2
        assert ExitCode.CRITICAL.value == 3


class TestIssue:
    """Test Issue dataclass."""

    def test_creation(self) -> None:
        """Should create Issue."""
        issue = Issue(
            file="test.py",
            line=10,
            column=5,
            severity="warning",
            message="Line too long",
            rule="E501"
        )
        
        assert issue.file == "test.py"
        assert issue.severity == "warning"


class TestCICDReport:
    """Test CICDReport dataclass."""

    def test_creation(self) -> None:
        """Should create CICDReport."""
        report = CICDReport(
            project="my_project",
            timestamp="2024-01-01T00:00:00",
            total_files=10,
            total_lines=500
        )
        
        assert report.project == "my_project"
        assert report.issues == []

    def test_to_json(self) -> None:
        """Should convert to JSON."""
        issue = Issue("test.py", 10, 5, "error", "Bad code", "E001")
        report = CICDReport(
            project="test",
            timestamp="2024-01-01",
            total_files=1,
            total_lines=100,
            issues=[issue],
            exit_code=2
        )
        
        json_str = report.to_json()
        data = json.loads(json_str)
        
        assert data["project"] == "test"
        assert len(data["issues"]) == 1
        assert data["summary"]["errors"] == 1


class TestCICDConfig:
    """Test CICDConfig dataclass."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        config = CICDConfig()
        
        assert config.max_complexity == 10
        assert config.max_line_length == 120
        assert config.fail_on_error is True
        assert config.fail_on_warning is False

    def test_load_nonexistent_file(self) -> None:
        """Should return defaults for missing file."""
        config = CICDConfig.load(Path("/nonexistent/.tree-sitter-ci.json"))
        
        assert config.max_complexity == 10

    def test_load_from_file(self) -> None:
        """Should load from config file."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump({
                "max_complexity": 15,
                "max_line_length": 100,
                "fail_on_error": False,
                "fail_on_warning": True
            }, f)
            f.flush()
            path = Path(f.name)
        
        try:
            config = CICDConfig.load(path)
            
            assert config.max_complexity == 15
            assert config.max_line_length == 100
            assert config.fail_on_error is False
            assert config.fail_on_warning is True
        finally:
            path.unlink()

    def test_load_invalid_json(self) -> None:
        """Should return defaults for invalid JSON."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            f.write("not valid json")
            f.flush()
            path = Path(f.name)
        
        try:
            config = CICDConfig.load(path)
            
            # Should return defaults
            assert config.max_complexity == 10
        finally:
            path.unlink()


class TestGenerateCICDReport:
    """Test generate_cicd_report function."""

    def test_generate_empty_project(self) -> None:
        """Should handle empty project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            report = generate_cicd_report(Path(tmpdir))
            
            assert report.total_files == 0
            assert report.exit_code == ExitCode.SUCCESS.value

    def test_generate_with_files(self) -> None:
        """Should analyze Python files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("x = 1\n")
            
            report = generate_cicd_report(Path(tmpdir))
            
            assert report.total_files == 1
            assert report.total_lines >= 1

    def test_generate_detects_long_lines(self) -> None:
        """Should detect long lines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            long_line = "x = " + "a" * 200
            (Path(tmpdir) / "test.py").write_text(long_line + "\n")
            
            config = CICDConfig(max_line_length=100)
            report = generate_cicd_report(Path(tmpdir), config=config)
            
            assert len(report.issues) >= 1
            assert report.issues[0].rule == "E501"

    def test_exit_code_with_errors(self) -> None:
        """Should return error exit code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            long_line = "x = " + "a" * 200
            (Path(tmpdir) / "test.py").write_text(long_line + "\n")
            
            config = CICDConfig(
                max_line_length=100,
                fail_on_warning=True
            )
            report = generate_cicd_report(Path(tmpdir), config=config)
            
            # warnings should cause warning exit code
            assert report.exit_code == ExitCode.WARNINGS.value

    def test_metrics_in_report(self) -> None:
        """Should include metrics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("x = 1\ny = 2\n")
            
            report = generate_cicd_report(Path(tmpdir))
            
            assert "files" in report.metrics
            assert "lines" in report.metrics
