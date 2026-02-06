"""
Tests for features/tech_debt_tracker.py module.

TDD: Testing tech debt analysis and tracking.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.features.tech_debt_tracker import (
    DebtType,
    TechDebt,
    TechDebtAnalyzer,
    analyze_tech_debt,
)


class TestDebtType:
    """Test DebtType enum."""

    def test_debt_types(self) -> None:
        """Should have all debt types."""
        assert DebtType.TODO.value == "todo"
        assert DebtType.FIXME.value == "fixme"
        assert DebtType.HACK.value == "hack"
        assert DebtType.CODE_SMELL.value == "code_smell"
        assert DebtType.COMPLEXITY.value == "complexity"
        assert DebtType.DUPLICATION.value == "duplication"
        assert DebtType.DEPRECATED.value == "deprecated"


class TestTechDebt:
    """Test TechDebt dataclass."""

    def test_creation(self) -> None:
        """Should create TechDebt."""
        debt = TechDebt(
            file="test.py",
            line_number=10,
            debt_type=DebtType.TODO,
            severity="low",
            description="# TODO: Fix this",
            estimated_fix_time=30
        )
        
        assert debt.file == "test.py"
        assert debt.line_number == 10
        assert debt.debt_type == DebtType.TODO
        assert debt.severity == "low"


class TestTechDebtAnalyzer:
    """Test TechDebtAnalyzer class."""

    def test_detect_todo(self) -> None:
        """Should detect TODO comments."""
        analyzer = TechDebtAnalyzer()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x = 1\n# TODO: implement this\ny = 2\n")
            f.flush()
            file_path = Path(f.name)
        
        try:
            debts = analyzer.analyze_file(file_path)
            
            assert len(debts) >= 1
            todo = next((d for d in debts if d.debt_type == DebtType.TODO), None)
            assert todo is not None
            assert todo.severity == "low"
        finally:
            file_path.unlink()

    def test_detect_fixme(self) -> None:
        """Should detect FIXME comments."""
        analyzer = TechDebtAnalyzer()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# FIXME: broken code here\n")
            f.flush()
            file_path = Path(f.name)
        
        try:
            debts = analyzer.analyze_file(file_path)
            
            fixme = next((d for d in debts if d.debt_type == DebtType.FIXME), None)
            assert fixme is not None
            assert fixme.severity == "medium"
        finally:
            file_path.unlink()

    def test_detect_hack(self) -> None:
        """Should detect HACK comments."""
        analyzer = TechDebtAnalyzer()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# HACK: temporary workaround\n")
            f.flush()
            file_path = Path(f.name)
        
        try:
            debts = analyzer.analyze_file(file_path)
            
            hack = next((d for d in debts if d.debt_type == DebtType.HACK), None)
            assert hack is not None
            assert hack.severity == "high"
        finally:
            file_path.unlink()

    def test_detect_deprecated(self) -> None:
        """Should detect deprecated usage."""
        analyzer = TechDebtAnalyzer()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# This is deprecated\nold_func()\n")
            f.flush()
            file_path = Path(f.name)
        
        try:
            debts = analyzer.analyze_file(file_path)
            
            deprecated = next((d for d in debts if d.debt_type == DebtType.DEPRECATED), None)
            assert deprecated is not None
        finally:
            file_path.unlink()

    def test_detect_lowercase_keywords(self) -> None:
        """Should detect lowercase keywords (todo, fixme, hack)."""
        analyzer = TechDebtAnalyzer()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# todo: lowercase todo\n# fixme: lowercase fixme\n# hack: lowercase hack\n")
            f.flush()
            file_path = Path(f.name)
        
        try:
            debts = analyzer.analyze_file(file_path)
            
            assert len(debts) >= 3
        finally:
            file_path.unlink()

    def test_analyze_clean_file(self) -> None:
        """Should return empty for clean file."""
        analyzer = TechDebtAnalyzer()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("def clean_function():\n    return 42\n")
            f.flush()
            file_path = Path(f.name)
        
        try:
            debts = analyzer.analyze_file(file_path)
            
            assert len(debts) == 0
        finally:
            file_path.unlink()

    def test_analyze_nonexistent_file(self) -> None:
        """Should handle non-existent file."""
        analyzer = TechDebtAnalyzer()
        
        debts = analyzer.analyze_file(Path("/nonexistent/file.py"))
        assert debts == []

    def test_analyze_directory(self) -> None:
        """Should analyze directory."""
        analyzer = TechDebtAnalyzer()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "a.py").write_text("# TODO: fix a\n")
            (Path(tmpdir) / "b.py").write_text("# FIXME: fix b\n")
            
            debts = analyzer.analyze_directory(Path(tmpdir))
            
            assert len(debts) >= 2

    def test_calculate_total_debt(self) -> None:
        """Should calculate total debt."""
        analyzer = TechDebtAnalyzer()
        
        debts = [
            TechDebt("a.py", 1, DebtType.TODO, "low", "todo", 30),
            TechDebt("b.py", 1, DebtType.FIXME, "medium", "fixme", 60),
            TechDebt("c.py", 1, DebtType.HACK, "high", "hack", 120),
        ]
        
        result = analyzer.calculate_total_debt(debts)
        
        assert result["total_debts"] == 3
        assert result["total_fix_time_minutes"] == 210
        assert result["total_fix_time_hours"] == 3.5
        assert "by_type" in result
        assert "by_severity" in result

    def test_generate_report(self) -> None:
        """Should generate debt report."""
        analyzer = TechDebtAnalyzer()
        
        debts = [
            TechDebt("file.py", 10, DebtType.TODO, "low", "desc", 30),
        ]
        
        report = analyzer.generate_report(debts)
        
        assert "timestamp" in report
        assert "summary" in report
        assert "top_debts" in report
        assert "recommendations" in report

    def test_recommendations_critical(self) -> None:
        """Should generate critical recommendations for high debt."""
        analyzer = TechDebtAnalyzer()
        
        # Create enough debt to exceed 30 days (30 * 8 * 60 = 14400 minutes)
        debts = [
            TechDebt("f.py", i, DebtType.HACK, "high", "hack", 500)
            for i in range(30)
        ]  # 15000 minutes = 31+ days
        
        report = analyzer.generate_report(debts)
        
        has_critical = any("Critical" in r or "critical" in r.lower() for r in report["recommendations"])
        assert has_critical

    def test_recommendations_good(self) -> None:
        """Should generate good recommendations for low debt."""
        analyzer = TechDebtAnalyzer()
        
        debts = [
            TechDebt("f.py", 1, DebtType.TODO, "low", "todo", 30)
        ]  # Only 30 minutes
        
        report = analyzer.generate_report(debts)
        
        has_good = any("Good" in r for r in report["recommendations"])
        assert has_good


class TestAnalyzeTechDebt:
    """Test analyze_tech_debt convenience function."""

    def test_analyze_tech_debt(self) -> None:
        """Should analyze tech debt for project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "main.py").write_text("# TODO: implement main\n")
            (Path(tmpdir) / "utils.py").write_text("# FIXME: fix utils\n")
            
            report = analyze_tech_debt(Path(tmpdir))
            
            assert "summary" in report
            assert "top_debts" in report
            assert report["summary"]["total_debts"] >= 2
