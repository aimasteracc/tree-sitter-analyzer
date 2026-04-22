"""Tests for ProjectBrain — pre-warmed holistic project model."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.project_brain import FileKnowledge, ProjectBrain


@pytest.fixture
def sample_project(tmp_path: Path) -> str:
    """Create a small sample project for brain testing."""
    src = tmp_path / "src"
    src.mkdir()

    (src / "clean.py").write_text(
        "def hello():\n    return 'hello'\n"
    )
    (src / "messy.py").write_text(
        "class GodClass:\n"
        "    def a(self): pass\n"
        "    def b(self): pass\n"
        "    def c(self): pass\n"
        "    def d(self): pass\n"
        "    def e(self): pass\n"
        "    def f(self): pass\n"
        "    def g(self): pass\n"
        "    def h(self): pass\n"
        "    def i(self): pass\n"
        "    def j(self): pass\n"
        "\n"
        "def deep(x):\n"
        "    if x > 0:\n"
        "        if x > 10:\n"
        "            if x > 100:\n"
        "                for i in range(x):\n"
        "                    if i % 2 == 0:\n"
        "                        pass\n"
        "    return x\n"
    )
    (src / "utils.js").write_text(
        "function add(a, b) { return a + b; }\n"
    )
    return str(tmp_path)


class TestProjectBrainWarmUp:
    def test_warm_up_discovers_files(self, sample_project: str):
        brain = ProjectBrain(project_root=sample_project)
        brain.warm_up()
        assert brain._total_files >= 3

    def test_warm_up_builds_file_map(self, sample_project: str):
        brain = ProjectBrain(project_root=sample_project)
        brain.warm_up()
        assert len(brain._file_map) >= 3

    def test_warm_up_computes_health(self, sample_project: str):
        brain = ProjectBrain(project_root=sample_project)
        brain.warm_up()
        health = brain.get_health_score()
        assert 0.0 <= health <= 100.0

    def test_warm_up_tracks_duration(self, sample_project: str):
        brain = ProjectBrain(project_root=sample_project)
        brain.warm_up()
        assert brain._warm_duration > 0

    def test_warm_up_counts_lines(self, sample_project: str):
        brain = ProjectBrain(project_root=sample_project)
        brain.warm_up()
        assert brain._total_lines > 0


class TestProjectBrainQueries:
    def test_get_file_perception(self, sample_project: str):
        brain = ProjectBrain(project_root=sample_project)
        brain.warm_up()
        py_files = [p for p in brain._file_map if p.endswith("clean.py")]
        assert len(py_files) >= 1
        knowledge = brain.get_file_perception(py_files[0])
        assert knowledge is not None
        assert isinstance(knowledge, FileKnowledge)
        assert knowledge.language == "python"

    def test_get_file_perception_unknown(self, sample_project: str):
        brain = ProjectBrain(project_root=sample_project)
        brain.warm_up()
        assert brain.get_file_perception("/nonexistent.py") is None

    def test_get_hotspots(self, sample_project: str):
        brain = ProjectBrain(project_root=sample_project)
        brain.warm_up()
        hotspots = brain.get_hotspots(min_analyzers=2)
        assert isinstance(hotspots, list)

    def test_get_summary(self, sample_project: str):
        brain = ProjectBrain(project_root=sample_project)
        brain.warm_up()
        summary = brain.get_summary()
        assert summary["total_files"] >= 3
        assert "overall_health" in summary
        assert "warm_time" in summary

    def test_what_happens_if_i_change(self, sample_project: str):
        brain = ProjectBrain(project_root=sample_project)
        brain.warm_up()
        py_files = [p for p in brain._file_map if p.endswith("messy.py")]
        assert len(py_files) >= 1
        result = brain.what_happens_if_i_change(py_files[0])
        assert "current_health" in result
        assert "existing_findings" in result

    def test_what_happens_with_line(self, sample_project: str):
        brain = ProjectBrain(project_root=sample_project)
        brain.warm_up()
        py_files = [p for p in brain._file_map if p.endswith("messy.py")]
        result = brain.what_happens_if_i_change(py_files[0], line=1)
        assert "warnings" in result

    def test_get_context_for_file(self, sample_project: str):
        brain = ProjectBrain(project_root=sample_project)
        brain.warm_up()
        py_files = [p for p in brain._file_map if p.endswith("clean.py")]
        ctx = brain.get_context_for_file(py_files[0])
        assert ctx["language"] == "python"
        assert "health" in ctx
        assert "project_health" in ctx
        assert "project_files" in ctx


class TestProjectBrainIncremental:
    def test_incremental_skips_unchanged(self, sample_project: str):
        brain = ProjectBrain(project_root=sample_project)
        brain.warm_up()
        initial_count = len(brain._file_map)
        brain.warm_up_incremental([])
        assert len(brain._file_map) == initial_count


class TestFileKnowledge:
    def test_frozen(self):
        fk = FileKnowledge(
            path="test.py",
            language="python",
            line_count=10,
            health_score=80.0,
            perception_score=0.2,
            total_findings=3,
            fired_neurons=5,
            total_neurons=10,
            severity_distribution={"medium": 2, "low": 1},
            category_coverage={"complexity": 1, "smell": 2},
            critical_hotspot_lines=(42,),
            top_issues=("[high] L42: god_class",),
        )
        assert fk.path == "test.py"
        assert fk.health_score == 80.0


class TestProjectBrainTestPerception:
    """Tests for deep test perception: coverage, quality, health."""

    @pytest.fixture
    def project_with_tests(self, tmp_path: Path) -> str:
        """Create a project with source files and test files."""
        src = tmp_path / "my_pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")

        (src / "calculator.py").write_text(
            "class Calculator:\n"
            "    def __init__(self):\n"
            "        self.result = 0\n"
            "    def add(self, value):\n"
            "        self.result += value\n"
            "        return self.result\n"
            "    def subtract(self, value):\n"
            "        self.result -= value\n"
            "        return self.result\n"
            "\n"
            "def helper():\n"
            "    return 42\n"
        )

        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "__init__.py").write_text("")

        (tests / "test_calculator.py").write_text(
            "from my_pkg.calculator import Calculator, helper\n"
            "import pytest\n"
            "\n"
            "def test_add():\n"
            "    c = Calculator()\n"
            "    assert c.add(5) == 5\n"
            "    assert c.add(3) == 8\n"
            "\n"
            "def test_subtract():\n"
            "    c = Calculator()\n"
            "    assert c.subtract(3) == -3\n"
            "\n"
            "def test_helper():\n"
            "    assert helper() == 42\n"
            "\n"
            "def test_no_assert():\n"
            "    c = Calculator()\n"
            "    c.add(1)\n"
            "\n"
            "def test_raises():\n"
            "    with pytest.raises(TypeError):\n"
            "        raise TypeError('bad')\n"
        )

        return str(tmp_path)

    def test_method_defs_tracked(self, project_with_tests: str):
        brain = ProjectBrain(project_root=project_with_tests)
        brain._build_impact_graph()
        assert "Calculator.__init__" in brain._method_defs
        assert "Calculator.add" in brain._method_defs
        assert "Calculator.subtract" in brain._method_defs

    def test_symbol_calls_tracked(self, project_with_tests: str):
        brain = ProjectBrain(project_root=project_with_tests)
        brain._build_impact_graph()
        assert "Calculator" in brain._symbol_calls
        assert "add" in brain._symbol_calls
        assert "subtract" in brain._symbol_calls
        assert "helper" in brain._symbol_calls

    def test_test_coverage_query(self, project_with_tests: str):
        brain = ProjectBrain(project_root=project_with_tests)
        brain._build_impact_graph()
        cov = brain.get_test_coverage(str(Path(project_with_tests) / "my_pkg" / "calculator.py"))
        assert cov["total_symbols"] > 0
        assert cov["covered_count"] > 0
        assert cov["coverage_pct"] > 0
        assert "Calculator" in cov["covered_symbols"]
        assert "Calculator.add" in cov["covered_symbols"]
        assert "test_calculator.py" in cov["test_files"][0]

    def test_uncovered_symbols(self, project_with_tests: str):
        brain = ProjectBrain(project_root=project_with_tests)
        brain._build_impact_graph()
        uncovered = brain.uncovered_symbols(str(Path(project_with_tests) / "my_pkg" / "calculator.py"))
        assert isinstance(uncovered, list)

    def test_test_health(self, project_with_tests: str):
        brain = ProjectBrain(project_root=project_with_tests)
        brain._build_impact_graph()
        health = brain.test_health()
        assert health["total_test_functions"] == 5
        assert health["total_asserts"] == 5  # 2+1+1+0+1(raises)
        assert health["assert_density"] == 1.0
        assert len(health["zero_assert_tests"]) == 1
        assert health["zero_assert_tests"][0]["test"] == "test_no_assert"

    def test_test_quality_metrics(self, project_with_tests: str):
        brain = ProjectBrain(project_root=project_with_tests)
        brain._build_impact_graph()
        test_rel = brain._relative(str(Path(project_with_tests) / "tests" / "test_calculator.py"))
        quality = brain._test_quality[test_rel]
        assert quality["test_count"] == 5
        assert quality["assert_count"] == 5
        assert "test_no_assert" in quality["zero_assert_tests"]

    def test_context_includes_test_info(self, project_with_tests: str):
        brain = ProjectBrain(project_root=project_with_tests)
        brain.warm_up()
        src = str(Path(project_with_tests) / "my_pkg" / "calculator.py")
        ctx = brain.get_context_for_file(src)
        assert "tests" in ctx
        assert "real_tests" in ctx
        assert "test_count" in ctx
        assert ctx["test_count"] >= 1
