"""
Tests for mcp/tools/ai_assistant.py module.

TDD: Testing AI assistant tools.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.mcp.tools.ai_assistant import (
    PatternRecognizerTool,
    DuplicateDetectorTool,
    SmellDetectorTool,
    ImprovementSuggesterTool,
    BestPracticeCheckerTool,
)


class TestPatternRecognizerTool:
    """Test PatternRecognizerTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = PatternRecognizerTool()
        assert tool.get_name() == "pattern_recognizer"

    def test_file_not_found(self) -> None:
        """Should handle missing file."""
        tool = PatternRecognizerTool()
        result = tool.execute({"file_path": "/nonexistent.py"})
        assert result["success"] is False

    def test_detect_singleton_pattern(self) -> None:
        """Should detect Singleton pattern."""
        tool = PatternRecognizerTool()
        
        code = '''
class Singleton:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
'''
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({
                "file_path": path,
                "pattern_types": ["design_patterns"]
            })
            
            assert result["success"] is True
            patterns = result["patterns"]["design_patterns"]
            assert any(p["type"] == "Singleton" for p in patterns)
        finally:
            Path(path).unlink()

    def test_detect_factory_pattern(self) -> None:
        """Should detect Factory pattern."""
        tool = PatternRecognizerTool()
        
        code = '''
class ShapeFactory:
    def create_shape(self, shape_type):
        pass
'''
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({
                "file_path": path,
                "pattern_types": ["design_patterns"]
            })
            
            assert result["success"] is True
            patterns = result["patterns"]["design_patterns"]
            assert any(p["type"] == "Factory" for p in patterns)
        finally:
            Path(path).unlink()

    def test_detect_anti_patterns(self) -> None:
        """Should detect anti-patterns."""
        tool = PatternRecognizerTool()
        
        # Create a "God Class" with many methods
        methods = "\n".join([f"    def method{i}(self): pass" for i in range(25)])
        code = f"class GodClass:\n{methods}\n"
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({
                "file_path": path,
                "pattern_types": ["anti_patterns"]
            })
            
            assert result["success"] is True
            anti = result["patterns"]["anti_patterns"]
            assert any(p["type"] == "God Class" for p in anti)
        finally:
            Path(path).unlink()

    def test_detect_idioms(self) -> None:
        """Should detect Python idioms."""
        tool = PatternRecognizerTool()
        
        code = '''
data = [x * 2 for x in range(10)]
with open("file.txt") as f:
    pass
'''
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({
                "file_path": path,
                "pattern_types": ["idioms"]
            })
            
            assert result["success"] is True
            idioms = result["patterns"]["idioms"]
            assert any(i["type"] == "List Comprehension" for i in idioms)
            assert any(i["type"] == "Context Manager" for i in idioms)
        finally:
            Path(path).unlink()


class TestDuplicateDetectorTool:
    """Test DuplicateDetectorTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = DuplicateDetectorTool()
        assert tool.get_name() == "duplicate_detector_advanced"

    def test_directory_not_found(self) -> None:
        """Should handle missing directory."""
        tool = DuplicateDetectorTool()
        result = tool.execute({"directory": "/nonexistent"})
        assert result["success"] is False

    def test_detect_duplicates(self) -> None:
        """Should detect duplicate code blocks."""
        tool = DuplicateDetectorTool()
        
        duplicate_code = "x = 1\ny = 2\nz = 3\na = 4\nb = 5\n"
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "a.py").write_text(duplicate_code)
            (Path(tmpdir) / "b.py").write_text(duplicate_code)
            
            result = tool.execute({
                "directory": tmpdir,
                "min_lines": 5
            })
            
            assert result["success"] is True
            assert result["total_duplicates"] >= 1

    def test_no_duplicates(self) -> None:
        """Should return empty for unique code."""
        tool = DuplicateDetectorTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "a.py").write_text("x = 1\n")
            (Path(tmpdir) / "b.py").write_text("y = 2\n")
            
            result = tool.execute({
                "directory": tmpdir,
                "min_lines": 5
            })
            
            assert result["success"] is True


class TestSmellDetectorTool:
    """Test SmellDetectorTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = SmellDetectorTool()
        assert tool.get_name() == "smell_detector_advanced"

    def test_file_not_found(self) -> None:
        """Should handle missing file."""
        tool = SmellDetectorTool()
        result = tool.execute({"file_path": "/nonexistent.py"})
        assert result["success"] is False

    def test_detect_long_method(self) -> None:
        """Should detect long methods."""
        tool = SmellDetectorTool()
        
        # Create method with 35 lines
        lines = "\n".join([f"    x{i} = {i}" for i in range(35)])
        code = f"def long_method():\n{lines}\n"
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"file_path": path})
            
            assert result["success"] is True
            assert len(result["smells"]["long_methods"]) >= 1
        finally:
            Path(path).unlink()

    def test_detect_long_parameters(self) -> None:
        """Should detect long parameter lists."""
        tool = SmellDetectorTool()
        
        code = "def many_params(a, b, c, d, e, f, g):\n    pass\n"
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"file_path": path})
            
            assert result["success"] is True
            assert len(result["smells"]["long_parameters"]) >= 1
        finally:
            Path(path).unlink()

    def test_detect_magic_numbers(self) -> None:
        """Should detect magic numbers."""
        tool = SmellDetectorTool()
        
        code = "x = 42\ny = 3.14\n"
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"file_path": path})
            
            assert result["success"] is True
            assert len(result["smells"]["magic_numbers"]) >= 2
        finally:
            Path(path).unlink()


class TestImprovementSuggesterTool:
    """Test ImprovementSuggesterTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = ImprovementSuggesterTool()
        assert tool.get_name() == "improvement_suggester"

    def test_file_not_found(self) -> None:
        """Should handle missing file."""
        tool = ImprovementSuggesterTool()
        result = tool.execute({"file_path": "/nonexistent.py"})
        assert result["success"] is False

    def test_suggest_docstring(self) -> None:
        """Should suggest adding docstrings."""
        tool = ImprovementSuggesterTool()
        
        code = "def no_docstring():\n    pass\n"
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"file_path": path})
            
            assert result["success"] is True
            has_docstring_suggestion = any(
                s["type"] == "missing_docstring" for s in result["suggestions"]
            )
            assert has_docstring_suggestion
        finally:
            Path(path).unlink()


class TestBestPracticeCheckerTool:
    """Test BestPracticeCheckerTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = BestPracticeCheckerTool()
        assert tool.get_name() == "best_practice_checker"

    def test_file_not_found(self) -> None:
        """Should handle missing file."""
        tool = BestPracticeCheckerTool()
        result = tool.execute({"file_path": "/nonexistent.py"})
        assert result["success"] is False

    def test_detect_mutable_default(self) -> None:
        """Should detect mutable default arguments."""
        tool = BestPracticeCheckerTool()
        
        code = "def bad_default(items=[]):\n    items.append(1)\n"
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"file_path": path})
            
            assert result["success"] is True
            has_violation = any(
                v["rule"] == "mutable_default_argument" for v in result["violations"]
            )
            assert has_violation
        finally:
            Path(path).unlink()

    def test_detect_bare_except(self) -> None:
        """Should detect bare except."""
        tool = BestPracticeCheckerTool()
        
        code = "try:\n    pass\nexcept:\n    pass\n"
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"file_path": path})
            
            assert result["success"] is True
            has_violation = any(
                v["rule"] == "bare_except" for v in result["violations"]
            )
            assert has_violation
        finally:
            Path(path).unlink()

    def test_clean_code_passes(self) -> None:
        """Should pass clean code."""
        tool = BestPracticeCheckerTool()
        
        code = '''
def good_function(items=None):
    """Good function with proper default."""
    if items is None:
        items = []
    return items
'''
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"file_path": path})
            
            assert result["success"] is True
            assert result["passed"] is True
        finally:
            Path(path).unlink()
