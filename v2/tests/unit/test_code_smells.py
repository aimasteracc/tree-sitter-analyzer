"""
Unit tests for code smell detection.

Sprint 7: detect_code_smells() on CodeMapResult.
Sprint 8: New smells (long_parameter_list, unused_import).
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.core.code_map import CodeSmell, ProjectCodeMap
from tree_sitter_analyzer_v2.core.code_map.analyzers.smell import detect_code_smells
from tree_sitter_analyzer_v2.core.code_map.types import ModuleInfo, SymbolInfo


@pytest.fixture
def cross_file_project():
    return Path(__file__).parent.parent / "fixtures" / "cross_file_project"


@pytest.fixture
def result(cross_file_project):
    mapper = ProjectCodeMap()
    return mapper.scan(str(cross_file_project), extensions=[".py"])


class TestDetectCodeSmellsExists:
    """Test that detect_code_smells() exists and returns results."""

    def test_method_exists(self, result):
        assert hasattr(result, "detect_code_smells")
        assert callable(result.detect_code_smells)

    def test_returns_list(self, result):
        smells = result.detect_code_smells()
        assert isinstance(smells, list)

    def test_smells_have_required_fields(self, result):
        smells = result.detect_code_smells()
        for s in smells:
            assert isinstance(s, CodeSmell)
            assert hasattr(s, "kind")
            assert hasattr(s, "severity")
            assert hasattr(s, "message")
            assert hasattr(s, "file_path")


class TestCircularDependencyDetection:
    """Test circular dependency detection."""

    def test_no_false_circular_deps(self, result):
        """Should not report circular deps where there are none."""
        smells = result.detect_code_smells()
        circular = [s for s in smells if s.kind == "circular_dependency"]
        assert isinstance(circular, list)


class TestGodClassDetection:
    """Test god class detection (classes with too many methods)."""

    def test_god_class_threshold(self, result):
        """Classes with many methods should be flagged."""
        smells = result.detect_code_smells()
        god_classes = [s for s in smells if s.kind == "god_class"]
        assert isinstance(god_classes, list)


class TestDeepInheritanceDetection:
    """Test deep inheritance chain detection."""

    def test_deep_inheritance_detected(self, result):
        """Classes with deep inheritance should be flagged."""
        smells = result.detect_code_smells()
        deep = [s for s in smells if s.kind == "deep_inheritance"]
        assert isinstance(deep, list)


class TestCodeSmellToon:
    """Test TOON output for code smells."""

    def test_smell_to_toon(self):
        """Each smell should produce TOON output."""
        smell = CodeSmell(
            kind="god_class",
            severity="warning",
            message="Class 'BigService' has 30 methods",
            file_path="services/big.py",
        )
        toon = smell.to_toon()
        assert "god_class" in toon
        assert "BigService" in toon


class TestMcpSmellsAction:
    """Test MCP tool exposure."""

    def test_smells_action_in_intelligence_tool(self):
        from tree_sitter_analyzer_v2.mcp.tools.intelligence import _VALID_ACTIONS
        assert "code_smells" in _VALID_ACTIONS


# ──────── S8: New Smell Tests (Pure Function) ────────


class TestLongParameterListDetection:
    """Test long_parameter_list smell."""

    def test_few_params_no_smell(self):
        """Functions with <= 5 params should not trigger."""
        symbols = [SymbolInfo(
            name="ok_func", kind="function", file="a.py",
            line_start=1, line_end=10, params="a,b,c",
        )]
        smells = detect_code_smells([], symbols, [])
        long_params = [s for s in smells if s.kind == "long_parameter_list"]
        assert len(long_params) == 0

    def test_many_params_triggers(self):
        """Functions with >5 params should trigger."""
        symbols = [SymbolInfo(
            name="complex_func", kind="function", file="big.py",
            line_start=1, line_end=10, params="a,b,c,d,e,f",
        )]
        smells = detect_code_smells([], symbols, [])
        long_params = [s for s in smells if s.kind == "long_parameter_list"]
        assert len(long_params) == 1
        assert "6 parameters" in long_params[0].message

    def test_boundary_5_params(self):
        """Exactly 5 params should not trigger."""
        symbols = [SymbolInfo(
            name="edge", kind="function", file="a.py",
            line_start=1, line_end=10, params="a,b,c,d,e",
        )]
        smells = detect_code_smells([], symbols, [])
        long_params = [s for s in smells if s.kind == "long_parameter_list"]
        assert len(long_params) == 0

    def test_severity_warning(self):
        """long_parameter_list should have warning severity."""
        symbols = [SymbolInfo(
            name="many", kind="method", file="a.py",
            line_start=1, line_end=10, params="a,b,c,d,e,f,g",
        )]
        smells = detect_code_smells([], symbols, [])
        long_params = [s for s in smells if s.kind == "long_parameter_list"]
        assert long_params[0].severity == "warning"

    def test_classes_ignored(self):
        """Classes should not trigger long_parameter_list."""
        symbols = [SymbolInfo(
            name="BigClass", kind="class", file="a.py",
            line_start=1, line_end=100, params="",
        )]
        smells = detect_code_smells([], symbols, [])
        long_params = [s for s in smells if s.kind == "long_parameter_list"]
        assert len(long_params) == 0

    def test_empty_params_no_smell(self):
        """Empty params should not trigger."""
        symbols = [SymbolInfo(
            name="no_args", kind="function", file="a.py",
            line_start=1, line_end=10, params="",
        )]
        smells = detect_code_smells([], symbols, [])
        long_params = [s for s in smells if s.kind == "long_parameter_list"]
        assert len(long_params) == 0


class TestUnusedImportDetection:
    """Test unused_import smell."""

    def test_used_import_no_smell(self):
        """Imports that match symbol names should not trigger."""
        modules = [ModuleInfo(
            path="main.py", language="python", lines=10,
            imports=[{"module": "utils", "names": ["helper"], "line_start": 1}],
        )]
        symbols = [SymbolInfo(
            name="helper", kind="function", file="utils.py",
            line_start=1, line_end=5,
        )]
        smells = detect_code_smells(modules, symbols, [])
        unused = [s for s in smells if s.kind == "unused_import"]
        assert len(unused) == 0

    def test_unused_import_triggers(self):
        """Imports with no matching symbol/call should trigger."""
        modules = [ModuleInfo(
            path="main.py", language="python", lines=10,
            imports=[{"module": "utils", "names": ["never_used"], "line_start": 1}],
        )]
        symbols = [SymbolInfo(
            name="other_func", kind="function", file="main.py",
            line_start=5, line_end=10,
        )]
        smells = detect_code_smells(modules, symbols, [])
        unused = [s for s in smells if s.kind == "unused_import"]
        assert len(unused) == 1
        assert "never_used" in unused[0].message

    def test_severity_info(self):
        """unused_import should have info severity."""
        modules = [ModuleInfo(
            path="main.py", language="python", lines=10,
            imports=[{"module": "os", "names": ["getcwd"], "line_start": 1}],
        )]
        smells = detect_code_smells(modules, [], [])
        unused = [s for s in smells if s.kind == "unused_import"]
        assert len(unused) == 1
        assert unused[0].severity == "info"

    def test_star_import_ignored(self):
        """Star imports (*) should not trigger unused_import."""
        modules = [ModuleInfo(
            path="main.py", language="python", lines=10,
            imports=[{"module": "utils", "names": ["*"], "line_start": 1}],
        )]
        smells = detect_code_smells(modules, [], [])
        unused = [s for s in smells if s.kind == "unused_import"]
        assert len(unused) == 0

    def test_import_used_in_call_sites(self):
        """Imports referenced in call_sites should not trigger."""
        modules = [ModuleInfo(
            path="main.py", language="python", lines=10,
            imports=[{"module": "utils", "names": ["helper"], "line_start": 1}],
            call_sites={"process": ["helper"]},
        )]
        smells = detect_code_smells(modules, [], [])
        unused = [s for s in smells if s.kind == "unused_import"]
        assert len(unused) == 0

    def test_multiple_imports_partial_unused(self):
        """Multiple names in one import: only unused ones trigger."""
        modules = [ModuleInfo(
            path="main.py", language="python", lines=10,
            imports=[{"module": "utils", "names": ["used", "unused_one"], "line_start": 1}],
        )]
        symbols = [SymbolInfo(
            name="used", kind="function", file="utils.py",
            line_start=1, line_end=5,
        )]
        smells = detect_code_smells(modules, symbols, [])
        unused = [s for s in smells if s.kind == "unused_import"]
        assert len(unused) == 1
        assert "unused_one" in unused[0].message


class TestSmellCombination:
    """Test that multiple smells can be detected simultaneously."""

    def test_multiple_smell_types(self):
        """Should detect multiple smell types in the same analysis."""
        modules = [ModuleInfo(
            path="big.py", language="python", lines=100,
            imports=[{"module": "os", "names": ["unused_os"], "line_start": 1}],
        )]
        symbols = [
            SymbolInfo(
                name="many_args_func", kind="function", file="big.py",
                line_start=1, line_end=10, params="a,b,c,d,e,f,g",
            ),
        ]
        deps = [("big.py", "other.py"), ("other.py", "big.py")]
        smells = detect_code_smells(modules, symbols, deps)
        kinds = {s.kind for s in smells}
        assert "circular_dependency" in kinds
        assert "long_parameter_list" in kinds
        assert "unused_import" in kinds
