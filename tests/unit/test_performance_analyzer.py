"""
Tests for features/performance_analyzer.py module.

TDD: Testing performance hotspot analysis.
"""

import tempfile
from pathlib import Path
import ast

import pytest

from tree_sitter_analyzer_v2.features.performance_analyzer import (
    PerformanceHotspot,
    ComplexityCalculator,
    PerformanceAnalyzer,
    analyze_performance,
)


class TestPerformanceHotspot:
    """Test PerformanceHotspot dataclass."""

    def test_creation(self) -> None:
        """Should create PerformanceHotspot."""
        hotspot = PerformanceHotspot(
            file="test.py",
            function="process",
            complexity=10,
            call_frequency_estimate=5,
            hotspot_score=50.0,
            line_number=10,
            recommendation="Optimize"
        )
        
        assert hotspot.function == "process"
        assert hotspot.hotspot_score == 50.0


class TestComplexityCalculator:
    """Test ComplexityCalculator."""

    def test_simple_function(self) -> None:
        """Should calculate complexity for simple function."""
        calc = ComplexityCalculator()
        
        code = "def simple():\n    return 1\n"
        tree = ast.parse(code)
        func = tree.body[0]
        
        complexity = calc.calculate(func)
        assert complexity == 1  # Base complexity

    def test_function_with_if(self) -> None:
        """Should add complexity for if statements."""
        calc = ComplexityCalculator()
        
        code = "def func():\n    if x:\n        pass\n"
        tree = ast.parse(code)
        func = tree.body[0]
        
        complexity = calc.calculate(func)
        assert complexity >= 2

    def test_function_with_loop(self) -> None:
        """Should add complexity for loops."""
        calc = ComplexityCalculator()
        
        code = "def func():\n    for i in range(10):\n        pass\n"
        tree = ast.parse(code)
        func = tree.body[0]
        
        complexity = calc.calculate(func)
        assert complexity >= 2

    def test_function_with_while(self) -> None:
        """Should add complexity for while loops."""
        calc = ComplexityCalculator()
        
        code = "def func():\n    while x:\n        pass\n"
        tree = ast.parse(code)
        func = tree.body[0]
        
        complexity = calc.calculate(func)
        assert complexity >= 2

    def test_function_with_exception(self) -> None:
        """Should add complexity for exception handlers."""
        calc = ComplexityCalculator()
        
        code = "def func():\n    try:\n        pass\n    except:\n        pass\n"
        tree = ast.parse(code)
        func = tree.body[0]
        
        complexity = calc.calculate(func)
        assert complexity >= 2

    def test_function_with_bool_op(self) -> None:
        """Should add complexity for boolean operations."""
        calc = ComplexityCalculator()
        
        code = "def func():\n    if x and y:\n        pass\n"
        tree = ast.parse(code)
        func = tree.body[0]
        
        complexity = calc.calculate(func)
        assert complexity >= 3  # if + and

    def test_function_with_comprehension(self) -> None:
        """Should add complexity for list comprehensions."""
        calc = ComplexityCalculator()
        
        code = "def func():\n    return [x for x in items]\n"
        tree = ast.parse(code)
        func = tree.body[0]
        
        complexity = calc.calculate(func)
        assert complexity >= 2

    def test_complex_function(self) -> None:
        """Should calculate high complexity for complex function."""
        calc = ComplexityCalculator()
        
        code = """
def complex():
    for i in range(10):
        if x:
            while y:
                if z or w:
                    try:
                        pass
                    except:
                        pass
"""
        tree = ast.parse(code)
        func = tree.body[0]
        
        complexity = calc.calculate(func)
        assert complexity > 5


class TestPerformanceAnalyzer:
    """Test PerformanceAnalyzer."""

    def test_analyze_file(self) -> None:
        """Should analyze file for hotspots."""
        analyzer = PerformanceAnalyzer()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("def process():\n    for i in range(10):\n        pass\n")
            f.flush()
            path = Path(f.name)
        
        try:
            hotspots = analyzer.analyze_file(path)
            
            assert len(hotspots) >= 1
            assert hotspots[0].function == "process"
            assert hotspots[0].complexity >= 2
        finally:
            path.unlink()

    def test_analyze_file_nonexistent(self) -> None:
        """Should handle non-existent file."""
        analyzer = PerformanceAnalyzer()
        
        hotspots = analyzer.analyze_file(Path("/nonexistent/file.py"))
        assert hotspots == []

    def test_analyze_file_syntax_error(self) -> None:
        """Should handle syntax errors."""
        analyzer = PerformanceAnalyzer()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("{{{ invalid")
            f.flush()
            path = Path(f.name)
        
        try:
            hotspots = analyzer.analyze_file(path)
            assert hotspots == []
        finally:
            path.unlink()

    def test_analyze_directory(self) -> None:
        """Should analyze directory."""
        analyzer = PerformanceAnalyzer()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "a.py").write_text("def func_a():\n    pass\n")
            (Path(tmpdir) / "b.py").write_text("def func_b():\n    pass\n")
            
            hotspots = analyzer.analyze_directory(Path(tmpdir))
            
            assert len(hotspots) >= 2

    def test_get_top_hotspots(self) -> None:
        """Should return top hotspots by score."""
        analyzer = PerformanceAnalyzer()
        
        hotspots = [
            PerformanceHotspot("a.py", "low", 2, 1, 2.0, 1, ""),
            PerformanceHotspot("b.py", "high", 20, 10, 200.0, 1, ""),
            PerformanceHotspot("c.py", "med", 10, 5, 50.0, 1, ""),
        ]
        
        top = analyzer.get_top_hotspots(hotspots, top_n=2)
        
        assert len(top) == 2
        assert top[0].function == "high"
        assert top[1].function == "med"

    def test_estimate_call_frequency_private(self) -> None:
        """Should estimate low frequency for private functions."""
        analyzer = PerformanceAnalyzer()
        
        freq = analyzer._estimate_call_frequency("_private_func")
        assert freq == 1

    def test_estimate_call_frequency_main(self) -> None:
        """Should estimate high frequency for main functions."""
        analyzer = PerformanceAnalyzer()
        
        freq = analyzer._estimate_call_frequency("main")
        assert freq == 10

    def test_estimate_call_frequency_getter(self) -> None:
        """Should estimate medium frequency for getters."""
        analyzer = PerformanceAnalyzer()
        
        freq = analyzer._estimate_call_frequency("get_data")
        assert freq == 5

    def test_generate_recommendation_critical(self) -> None:
        """Should generate critical recommendation."""
        analyzer = PerformanceAnalyzer()
        
        rec = analyzer._generate_recommendation(complexity=20, call_frequency=10)
        assert "Critical" in rec or "critical" in rec.lower()

    def test_generate_recommendation_ok(self) -> None:
        """Should generate OK recommendation for low impact."""
        analyzer = PerformanceAnalyzer()
        
        rec = analyzer._generate_recommendation(complexity=2, call_frequency=1)
        assert "OK" in rec


class TestAnalyzePerformance:
    """Test analyze_performance convenience function."""

    def test_analyze_performance(self) -> None:
        """Should analyze performance for project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "main.py").write_text("""
def main():
    for i in range(100):
        if i % 2:
            process(i)

def process(x):
    return x * 2
""")
            
            result = analyze_performance(Path(tmpdir), top_n=5)
            
            assert "total_functions" in result
            assert "top_hotspots" in result
            assert "summary" in result
            assert result["total_functions"] >= 2
