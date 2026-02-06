"""
Tests for Project Knowledge Engine - Core functionality for instant project understanding

Test Coverage:
- Snapshot building and caching
- Function impact calculation
- Hotspot identification
- Incremental updates
- Compression format validation
"""

import json
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.features.project_knowledge import (
    FunctionInfo,
    ProjectKnowledgeEngine,
    ProjectSnapshot,
)


class TestProjectSnapshot:
    """Test ProjectSnapshot data structure and compression"""

    def test_snapshot_creation(self):
        """Test creating a project snapshot"""
        snapshot = ProjectSnapshot(
            timestamp="2026-02-06T12:00:00",
            total_files=10,
            total_functions=50
        )
        
        assert snapshot.version == "1.0"
        assert snapshot.total_files == 10
        assert snapshot.total_functions == 50

    def test_compact_format_generation(self):
        """Test ultra-compact format generation"""
        snapshot = ProjectSnapshot(
            total_files=2,
            total_functions=3
        )
        
        # Add test functions
        snapshot.functions["test.py::func_a"] = FunctionInfo(
            name="func_a",
            file=Path("test.py"),
            calls=["test.py::func_b"],
            called_by=["main.py::main"],
            impact_score=15,
            impact_level="medium"
        )
        
        snapshot.functions["test.py::func_b"] = FunctionInfo(
            name="func_b",
            file=Path("test.py"),
            calls=[],
            called_by=["test.py::func_a"],
            impact_score=5,
            impact_level="low"
        )
        
        # Generate compact format
        compact = snapshot.to_compact_format(max_functions=10)
        
        assert "PROJECT_SNAPSHOT" in compact
        assert "MEDIUM IMPACT" in compact
        assert "LOW IMPACT" in compact
        assert "func_a" in compact
        assert "func_b" in compact

    def test_compact_format_respects_max_functions(self):
        """Test that compact format respects max_functions limit"""
        snapshot = ProjectSnapshot(total_files=1, total_functions=5)
        
        # Add 5 functions with different impact levels
        for i in range(5):
            snapshot.functions[f"test.py::func_{i}"] = FunctionInfo(
                name=f"func_{i}",
                file=Path("test.py"),
                impact_score=20 - i * 5,
                impact_level="high" if i == 0 else "medium"
            )
        
        # Request only top 3
        compact = snapshot.to_compact_format(max_functions=3)
        lines = compact.split('\n')
        function_lines = [l for l in lines if '::' in l]
        
        assert len(function_lines) == 3


class TestProjectKnowledgeEngine:
    """Test ProjectKnowledgeEngine core functionality"""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary test project"""
        # Create test files
        (tmp_path / "module_a.py").write_text("""
def main():
    result = process_data()
    return result

def process_data():
    value = helper()
    return value * 2

def helper():
    return 42
""")
        
        (tmp_path / "module_b.py").write_text("""
from module_a import main

def run():
    return main()
""")
        
        return tmp_path

    def test_engine_initialization(self, temp_project):
        """Test engine initializes correctly"""
        engine = ProjectKnowledgeEngine(temp_project)
        
        assert engine.project_root == temp_project
        assert engine.cache_dir == temp_project / ".analysis"
        assert engine.snapshot is None

    def test_build_snapshot(self, temp_project):
        """Test building project snapshot"""
        engine = ProjectKnowledgeEngine(temp_project)
        snapshot = engine.build_snapshot(pattern="**/*.py")
        
        assert snapshot.total_files == 2
        assert snapshot.total_functions > 0
        assert len(snapshot.functions) > 0
        
        # Verify functions were extracted
        function_names = [f.name for f in snapshot.functions.values()]
        assert "main" in function_names
        assert "process_data" in function_names
        assert "helper" in function_names

    def test_snapshot_caching(self, temp_project):
        """Test snapshot is cached and reloaded"""
        engine = ProjectKnowledgeEngine(temp_project)
        
        # Build snapshot
        snapshot1 = engine.build_snapshot()
        assert engine.cache_file.exists()
        
        # Create new engine and load from cache
        engine2 = ProjectKnowledgeEngine(temp_project)
        loaded = engine2._load_from_cache()
        
        assert loaded is True
        assert engine2.snapshot is not None
        assert engine2.snapshot.total_functions == snapshot1.total_functions

    def test_get_function_impact(self, temp_project):
        """Test getting function impact information"""
        engine = ProjectKnowledgeEngine(temp_project)
        engine.build_snapshot()
        
        # Query function impact
        impact = engine.get_function_impact("main")
        
        assert impact is not None
        assert impact["function"] == "main"
        assert "called_by" in impact
        assert "callees" in impact
        assert "impact_level" in impact
        assert impact["impact_level"] in ["high", "medium", "low"]

    def test_get_hotspots(self, temp_project):
        """Test getting hotspot functions"""
        engine = ProjectKnowledgeEngine(temp_project)
        engine.build_snapshot()
        
        hotspots = engine.get_hotspots(top_n=5)
        
        assert isinstance(hotspots, list)
        assert len(hotspots) > 0
        
        # Verify hotspots are sorted by impact
        if len(hotspots) > 1:
            assert hotspots[0]["impact_score"] >= hotspots[1]["impact_score"]

    def test_load_snapshot_text(self, temp_project):
        """Test loading snapshot as compressed text"""
        engine = ProjectKnowledgeEngine(temp_project)
        engine.build_snapshot()
        
        text = engine.load_snapshot(max_functions=10)
        
        assert "PROJECT_SNAPSHOT" in text
        assert "Files:" in text
        assert "Functions:" in text
        assert "::" in text  # Function format

    def test_impact_level_calculation(self):
        """Test impact level is calculated correctly"""
        engine = ProjectKnowledgeEngine(Path.cwd())
        
        # High impact
        assert engine._calculate_impact_level(25) == "high"
        assert engine._calculate_impact_level(21) == "high"
        
        # Medium impact
        assert engine._calculate_impact_level(20) == "medium"
        assert engine._calculate_impact_level(15) == "medium"
        assert engine._calculate_impact_level(11) == "medium"
        
        # Low impact
        assert engine._calculate_impact_level(10) == "low"
        assert engine._calculate_impact_level(5) == "low"
        assert engine._calculate_impact_level(0) == "low"

    def test_incremental_update_with_no_changes(self, temp_project):
        """Test incremental update when no files changed"""
        engine = ProjectKnowledgeEngine(temp_project)
        engine.build_snapshot()
        
        # Update with no changes
        result = engine.incremental_update([])
        
        assert result is True

    def test_function_not_found(self, temp_project):
        """Test querying non-existent function returns None"""
        engine = ProjectKnowledgeEngine(temp_project)
        engine.build_snapshot()
        
        impact = engine.get_function_impact("non_existent_function")
        
        assert impact is None


class TestImpactCalculation:
    """Test impact score calculation algorithm"""

    def test_impact_score_formula(self):
        """Test the impact score calculation formula"""
        engine = ProjectKnowledgeEngine(Path.cwd())
        
        # Create function with known metrics
        func = FunctionInfo(
            name="test_func",
            file=Path("test.py"),
            calls=[],
            called_by=["file1.py::caller1", "file2.py::caller2", "file3.py::caller3"]
        )
        
        score = engine._calculate_impact_score(func)
        
        # Score should reflect: called_by_count*2 + cross_file_count*3
        assert score > 0

    def test_cross_file_impact_weighted_higher(self):
        """Test cross-file calls are weighted higher than same-file calls"""
        engine = ProjectKnowledgeEngine(Path.cwd())
        
        # Function with cross-file callers
        func_cross = FunctionInfo(
            name="func_cross",
            file=Path("test.py"),
            called_by=["other1.py::caller", "other2.py::caller"]
        )
        
        # Function with same-file callers
        func_same = FunctionInfo(
            name="func_same",
            file=Path("test.py"),
            called_by=["test.py::caller1", "test.py::caller2"]
        )
        
        score_cross = engine._calculate_impact_score(func_cross)
        score_same = engine._calculate_impact_score(func_same)
        
        # Cross-file impact should be higher
        assert score_cross > score_same


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
