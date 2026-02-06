"""
Tests for features/refactoring_analyzer.py module.

TDD: Testing refactoring impact analysis.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.features.refactoring_analyzer import (
    CallSite,
    CallChain,
    RefactoringAnalyzer,
    analyze_refactoring_impact,
)


class TestCallSite:
    """Test CallSite dataclass."""

    def test_creation(self) -> None:
        """Should create CallSite."""
        site = CallSite(
            file=Path("test.py"),
            function_name="caller",
            line_number=10,
            context="caller()"
        )
        
        assert site.function_name == "caller"
        assert site.line_number == 10


class TestCallChain:
    """Test CallChain dataclass."""

    def test_creation(self) -> None:
        """Should create CallChain."""
        chain = CallChain(
            target_function="target",
            depth=2,
            call_path=["target", "caller1"]
        )
        
        assert chain.target_function == "target"
        assert chain.depth == 2


class TestRefactoringAnalyzer:
    """Test RefactoringAnalyzer class."""

    def test_init(self) -> None:
        """Should initialize with default depth."""
        analyzer = RefactoringAnalyzer()
        assert analyzer.max_depth == 10

    def test_init_custom_depth(self) -> None:
        """Should accept custom depth."""
        analyzer = RefactoringAnalyzer(max_depth=5)
        assert analyzer.max_depth == 5

    def test_analyze_directory(self) -> None:
        """Should analyze directory."""
        analyzer = RefactoringAnalyzer()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "module.py").write_text('''
def helper():
    pass

def caller():
    helper()
''')
            
            analyzer.analyze_directory(Path(tmpdir))
            
            assert "helper" in analyzer.function_defs
            assert "caller" in analyzer.function_defs

    def test_find_callers(self) -> None:
        """Should find callers of a function."""
        analyzer = RefactoringAnalyzer()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "module.py").write_text('''
def target():
    pass

def caller1():
    target()

def caller2():
    target()
''')
            
            analyzer.analyze_directory(Path(tmpdir))
            chains = analyzer.find_callers("target")
            
            assert len(chains) >= 2

    def test_find_callers_no_matches(self) -> None:
        """Should return empty for uncalled function."""
        analyzer = RefactoringAnalyzer()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "module.py").write_text('''
def standalone():
    pass
''')
            
            analyzer.analyze_directory(Path(tmpdir))
            chains = analyzer.find_callers("standalone")
            
            assert len(chains) == 0

    def test_get_impact_summary(self) -> None:
        """Should get impact summary."""
        analyzer = RefactoringAnalyzer()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "module.py").write_text('''
def target():
    pass

def caller():
    target()
''')
            
            analyzer.analyze_directory(Path(tmpdir))
            summary = analyzer.get_impact_summary("target")
            
            assert summary["function_name"] == "target"
            assert "total_call_sites" in summary
            assert "affected_files" in summary

    def test_cross_file_analysis(self) -> None:
        """Should analyze across files."""
        analyzer = RefactoringAnalyzer()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "lib.py").write_text('''
def helper():
    pass
''')
            (Path(tmpdir) / "app.py").write_text('''
from lib import helper

def main():
    helper()
''')
            
            analyzer.analyze_directory(Path(tmpdir))
            
            # Both files should be indexed
            assert "helper" in analyzer.function_defs
            assert "main" in analyzer.function_defs

    def test_handle_syntax_errors(self) -> None:
        """Should handle files with syntax errors."""
        analyzer = RefactoringAnalyzer()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "bad.py").write_text("{{{ invalid")
            (Path(tmpdir) / "good.py").write_text("def valid(): pass")
            
            analyzer.analyze_directory(Path(tmpdir))
            
            # Should still index the good file
            assert "valid" in analyzer.function_defs


class TestAnalyzeRefactoringImpact:
    """Test analyze_refactoring_impact convenience function."""

    def test_analyze_impact(self) -> None:
        """Should analyze refactoring impact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "module.py").write_text('''
def target():
    pass

def user():
    target()
''')
            
            result = analyze_refactoring_impact(
                Path(tmpdir),
                "target",
                max_depth=5
            )
            
            assert result["function_name"] == "target"
            assert "total_call_sites" in result
