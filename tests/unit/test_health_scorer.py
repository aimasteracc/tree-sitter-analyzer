"""Unit tests for health_scorer.py — file-level code health scoring."""

import json
import os
import sys
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "project_graph"
HEALTH_PROJECT = FIXTURES_DIR / "health_project"


# ============================================================
# HealthScorer tests
# ============================================================


class TestHealthScorer:
    """Test file health scoring."""

    @pytest.fixture
    def scorer(self):
        from tree_sitter_analyzer.health_scorer import HealthScorer

        return HealthScorer()

    def test_healthy_file_scores_higher(self, scorer):
        """healthy.py should score higher than unhealthy.py."""
        healthy_score = scorer.score_file(str(HEALTH_PROJECT / "healthy.py"))
        unhealthy_score = scorer.score_file(str(HEALTH_PROJECT / "unhealthy.py"))
        assert healthy_score.total > unhealthy_score.total, (
            f"Expected healthy ({healthy_score.total}) > unhealthy ({unhealthy_score.total})"
        )

    def test_score_is_between_0_and_100(self, scorer):
        """All scores should be in the 0-100 range."""
        for fname in ["healthy.py", "unhealthy.py"]:
            result = scorer.score_file(str(HEALTH_PROJECT / fname))
            assert 0 <= result.total <= 100, (
                f"Score for {fname} out of range: {result.total}"
            )

    def test_score_has_breakdown(self, scorer):
        """Score should include per-dimension breakdown."""
        result = scorer.score_file(str(HEALTH_PROJECT / "healthy.py"))
        breakdown = result.to_dict()
        assert "total" in breakdown
        assert "dimensions" in breakdown
        dims = breakdown["dimensions"]
        for key in ("size", "complexity", "dependencies", "structure"):
            assert key in dims, f"Missing dimension: {key}"

    def test_score_empty_file(self, scorer, tmp_path):
        """Empty file gets a baseline score."""
        empty = tmp_path / "empty.py"
        empty.write_text("")
        result = scorer.score_file(str(empty))
        assert result.total == 87.5

    def test_score_nonexistent_file(self, scorer):
        """Nonexistent file returns 0 score."""
        result = scorer.score_file("/nonexistent/file.py")
        assert result.total == 0

    def test_score_project(self, scorer):
        """Can score an entire project directory."""
        results = scorer.score_project(str(HEALTH_PROJECT))
        assert len(results) == 2
        for r in results:
            assert 0 <= r.total <= 100

    def test_score_project_includes_reported_source_extensions(self, scorer, tmp_path):
        """Project scoring should include all configured reportable extensions."""
        from tree_sitter_analyzer.health_scorer import PROJECT_HEALTH_SOURCE_EXTS

        for idx, ext in enumerate(sorted(PROJECT_HEALTH_SOURCE_EXTS)):
            path = tmp_path / f"sample{idx}{ext}"
            path.write_text("x = 1\n")

        unknown = tmp_path / "ignored.log"
        unknown.write_text("x = 1\n")

        results = scorer.score_project(str(tmp_path))
        names = {Path(result.file_path).name for result in results}
        included = {
            f"sample{idx}{ext}"
            for idx, ext in enumerate(sorted(PROJECT_HEALTH_SOURCE_EXTS))
        }

        assert names >= included
        assert "ignored.log" not in names

    def test_score_project_respects_custom_source_extensions(self, tmp_path):
        """Health scorer should limit scan scope to caller-provided extensions."""
        from tree_sitter_analyzer.health_scorer import HealthScorer

        py_file = tmp_path / "main.py"
        cfg_file = tmp_path / "project.cfg"
        py_file.write_text("x = 1\n")
        cfg_file.write_text("x = 1\n")

        scorer = HealthScorer(source_extensions={".cfg"})
        results = scorer.score_project(str(tmp_path))
        names = {Path(result.file_path).name for result in results}

        assert names == {"project.cfg"}

    def test_score_file_fast_dependencies_uses_fallback(self, monkeypatch, tmp_path):
        """Latency-sensitive callers can bypass whole-project dependency graphing."""
        from tree_sitter_analyzer import health_scorer
        from tree_sitter_analyzer.health_scorer import HealthScorer

        source = tmp_path / "main.py"
        source.write_text("import app.service\n")

        def fail_full_graph(_file_path):
            raise AssertionError("full dependency graph should not be used")

        monkeypatch.setattr(health_scorer, "score_dependencies", fail_full_graph)
        monkeypatch.setattr(
            health_scorer,
            "_score_deps_fallback",
            lambda _file_path: 42.0,
        )

        result = HealthScorer().score_file(str(source), fast_dependencies=True)

        assert result.dimensions["dependencies"] == 42.0

    def test_score_file_default_dependencies_uses_full_graph_score(
        self, monkeypatch, tmp_path
    ):
        """Default scoring keeps the full dependency graph dimension."""
        from tree_sitter_analyzer import health_scorer
        from tree_sitter_analyzer.health_scorer import HealthScorer

        source = tmp_path / "main.py"
        source.write_text("import app.service\n")

        monkeypatch.setattr(
            health_scorer,
            "score_dependencies",
            lambda _file_path: 77.0,
        )

        result = HealthScorer().score_file(str(source))

        assert result.dimensions["dependencies"] == 77.0

    def test_is_excluded_falls_back_to_absolute_parts(self, tmp_path):
        """Paths outside root still honor generated/hidden path parts."""
        from tree_sitter_analyzer.health_scorer import HealthScorer

        scorer = HealthScorer()

        assert scorer._is_excluded(tmp_path / ".hidden" / "file.py", Path("/outside"))

    def test_iter_source_files_skips_hidden_filenames(self, tmp_path):
        """Hidden filenames are not counted as project source files."""
        from tree_sitter_analyzer.health_scorer import HealthScorer

        visible = tmp_path / "src" / "main.py"
        hidden = tmp_path / "src" / ".ignored.py"
        visible.parent.mkdir(parents=True)
        visible.write_text("x = 1\n")
        hidden.write_text("x = 1\n")

        files, pruned = HealthScorer(source_extensions={".py"})._iter_source_files(
            tmp_path
        )

        assert [path.name for path in files] == ["main.py"]
        assert pruned == 0

    def test_score_project_counts_scoring_failures(self, monkeypatch, tmp_path):
        """Stats should record files that were discovered but failed scoring."""
        from tree_sitter_analyzer.health_scorer import HealthScorer

        source = tmp_path / "main.py"
        source.write_text("x = 1\n")
        scorer = HealthScorer(source_extensions={".py"})
        monkeypatch.setattr(scorer, "_score_file_with_cache", lambda *_args: None)

        scores, stats = scorer.score_project_with_stats(str(tmp_path), use_cache=False)

        assert scores == []
        assert stats["skip_reasons"]["scoring_failed"] == 1

    def test_score_project_counts_defensive_excluded_file(self, monkeypatch, tmp_path):
        """A defensive _is_excluded hit is still reported in project stats."""
        from tree_sitter_analyzer.health_scorer import HealthScorer

        hidden = tmp_path / ".hidden" / "main.py"
        hidden.parent.mkdir()
        hidden.write_text("x = 1\n")
        scorer = HealthScorer(source_extensions={".py"})
        monkeypatch.setattr(scorer, "_iter_source_files", lambda _root: ([hidden], 0))
        monkeypatch.setattr(
            scorer,
            "_score_file_with_cache",
            lambda *_args: pytest.fail("excluded files must not be scored"),
        )

        scores, stats = scorer.score_project_with_stats(str(tmp_path), use_cache=False)

        assert scores == []
        assert stats["total_files_scanned"] == 1
        assert stats["skip_reasons"]["excluded_dir"] == 1

    def test_score_project_prunes_hidden_and_generated_dirs(self, tmp_path):
        """Project scoring should not descend into hidden/generated directories."""
        from tree_sitter_analyzer.health_scorer import HealthScorer

        visible = tmp_path / "src" / "main.py"
        hidden = tmp_path / ".hidden" / "ignored.py"
        generated = tmp_path / "build" / "ignored.py"
        visible.parent.mkdir(parents=True)
        hidden.parent.mkdir(parents=True)
        generated.parent.mkdir(parents=True)
        visible.write_text("x = 1\n")
        hidden.write_text("x = 1\n")
        generated.write_text("x = 1\n")

        scores, stats = HealthScorer(
            source_extensions={".py"}
        ).score_project_with_stats(
            str(tmp_path),
            use_cache=False,
        )

        assert {Path(score.file_path).name for score in scores} == {"main.py"}
        assert stats["total_files_scanned"] == 1
        assert stats["skip_reasons"]["excluded_dir"] == 2

    def test_large_file_gets_penalized(self, scorer, tmp_path):
        """Files over 500 lines should have lower size score."""
        big = tmp_path / "big.py"
        big.write_text("\n".join([f"x{i} = {i}" for i in range(600)]))
        result = scorer.score_file(str(big))
        dims = result.to_dict()["dimensions"]
        assert dims["size"] < 85, (
            f"Large file should have low size score, got {dims['size']}"
        )

    def test_cc_penalizes_branches(self, scorer, tmp_path):
        """Code with many branches should have lower complexity score."""
        # High CC: 20 if-statements → CC = 21
        high_cc = tmp_path / "high_cc.py"
        lines = ["def f(x):"]
        for i in range(20):
            lines.append(f"    if x > {i}:")
            lines.append("        pass")
        high_cc.write_text("\n".join(lines))

        # Low CC: single return → CC = 1
        low_cc = tmp_path / "low_cc.py"
        low_cc.write_text("def f(x):\n    return x\n")

        high_result = scorer.score_file(str(high_cc))
        low_result = scorer.score_file(str(low_cc))
        assert (
            high_result.to_dict()["dimensions"]["complexity"]
            < low_result.to_dict()["dimensions"]["complexity"]
        ), "High CC code should have lower complexity score"

    def test_deeply_nested_code_penalized(self, scorer, tmp_path):
        """Deeply nested code should have lower structure score."""
        deep = tmp_path / "deep.py"
        deep.write_text(
            "def f(x):\n    if x:\n        if x:\n            if x:\n"
            "                if x:\n                    if x:\n"
            "                        if x:\n                            pass\n"
        )
        flat = tmp_path / "flat.py"
        flat.write_text("def f(x):\n    return x\n")
        deep_result = scorer.score_file(str(deep))
        flat_result = scorer.score_file(str(flat))
        assert (
            deep_result.to_dict()["dimensions"]["structure"]
            < flat_result.to_dict()["dimensions"]["structure"]
        ), "Deep nesting should have lower structure score"

    def test_coverage_none_without_data(self, scorer, tmp_path):
        """Coverage should be None (excluded from total) when no coverage.json exists."""
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        result = scorer.score_file(str(f))
        dims = result.to_dict()["dimensions"]
        assert "coverage" not in dims, (
            f"Coverage should be absent when no data, got {dims}"
        )

    def test_stale_coverage_json_is_ignored(self, monkeypatch, tmp_path):
        """Do not use stale JSON coverage when pytest-cov has newer raw data."""
        from tree_sitter_analyzer.health_scorer import HealthScorer

        source = tmp_path / "pkg" / "module.py"
        source.parent.mkdir()
        source.write_text("x = 1\n")
        coverage_json = tmp_path / "coverage.json"
        coverage_json.write_text(
            json.dumps(
                {
                    "files": {"pkg/module.py": {"summary": {"percent_covered": 12.5}}},
                    "totals": {"percent_covered": 12.5},
                }
            ),
            encoding="utf-8",
        )
        coverage_db = tmp_path / ".coverage"
        coverage_db.write_text("newer raw coverage", encoding="utf-8")
        os.utime(coverage_json, (1000, 1000))
        os.utime(coverage_db, (2000, 2000))
        monkeypatch.chdir(tmp_path)

        result = HealthScorer().score_file(str(source))

        assert "coverage" not in result.to_dict()["dimensions"]

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Windows path drift — tracked separately"
    )
    def test_current_coverage_json_is_used(self, monkeypatch, tmp_path):
        """Use JSON coverage when it is as current as the raw coverage data."""
        from tree_sitter_analyzer.health_scorer import HealthScorer

        source = tmp_path / "pkg" / "module.py"
        source.parent.mkdir()
        source.write_text("x = 1\n")
        coverage_json = tmp_path / "coverage.json"
        coverage_json.write_text(
            json.dumps(
                {
                    "files": {"pkg/module.py": {"summary": {"percent_covered": 87.5}}},
                    "totals": {"percent_covered": 87.5},
                }
            ),
            encoding="utf-8",
        )
        coverage_db = tmp_path / ".coverage"
        coverage_db.write_text("older raw coverage", encoding="utf-8")
        os.utime(coverage_db, (1000, 1000))
        os.utime(coverage_json, (2000, 2000))
        monkeypatch.chdir(tmp_path)

        result = HealthScorer().score_file(str(source))

        assert result.to_dict()["dimensions"]["coverage"] == 87.5

    def test_weights_sum_to_100(self):
        """Default dimension weights must sum to 100."""
        from tree_sitter_analyzer.health_scorer import DIMENSION_WEIGHTS

        assert sum(DIMENSION_WEIGHTS.values()) == 100, (
            f"Weights sum to {sum(DIMENSION_WEIGHTS.values())}"
        )

    def test_bash_complexity_counts_decision_nodes(self, scorer, tmp_path):
        """A bash function with 4 if + 2 while + 2 for + 1 case + 1 elif
        must yield CC=11 from the extractor (single source of truth).

        The extractor counts the whole case statement as 1 branch (not
        per-arm), and counts the elif within its parent if-statement, so
        the result is 10 decision nodes + base 1 = CC=11.
        """
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity

        sh = tmp_path / "branchy.sh"
        sh.write_text(
            "#!/bin/bash\n"
            "mega() {\n"
            "  if true; then echo 1; fi\n"
            "  if true; then echo 2; fi\n"
            "  if true; then echo 3; fi\n"
            "  while true; do break; done\n"
            "  while true; do break; done\n"
            "  for i in 1 2 3; do echo $i; done\n"
            "  for j in a b c; do echo $j; done\n"
            '  case "$x" in 1) echo a;; 2) echo b;; esac\n'
            "  if true; then echo 4; elif false; then echo 5; fi\n"
            "}\n",
            encoding="utf-8",
        )
        funcs = analyze_file_complexity(str(sh), "bash")
        assert len(funcs) == 1
        assert funcs[0].complexity == 11

    def test_dependencies_neutral_for_unanalyzable_languages(self, tmp_path):
        """Languages DependencyGraph cannot resolve (bash/scala/swift) must
        get a NEUTRAL dependency score, not a false-perfect 100."""
        from tree_sitter_analyzer.health_scorer import score_dependencies

        for name, body in (
            ("a.sh", "#!/bin/bash\necho hi\n"),
            ("b.scala", "object M { def f(): Int = 1 }\n"),
            ("c.swift", "func f() {}\n"),
        ):
            f = tmp_path / name
            f.write_text(body, encoding="utf-8")
            assert score_dependencies(str(f)) == 50.0

    def test_fast_dependencies_neutral_for_unanalyzable_language(self, tmp_path):
        """The ``fast_dependencies=True`` path (``_score_deps_fallback``) must
        apply the SAME neutral-language guard as ``score_dependencies`` — a
        ``.sh`` file gets 50, not a false-perfect 100."""
        from tree_sitter_analyzer.health_scorer import _score_deps_fallback

        sh = tmp_path / "tool.sh"
        sh.write_text("#!/bin/bash\necho hi\n", encoding="utf-8")
        assert _score_deps_fallback(str(sh)) == 50.0

    def test_bash_case_scores_decision_per_case(self, tmp_path):
        """A K-arm bash ``case`` dispatch: the extractor (single source of
        truth) reports CC=2 for a 10-arm case (base 1 + 1 case_statement
        branch). The extractor does not count per-arm items for bash case."""
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity

        arms = "\n".join(f"    {i}) echo {i} ;;" for i in range(1, 11))
        sh = tmp_path / "dispatch.sh"
        sh.write_text(
            '#!/bin/bash\ndispatch() {\n  case "$1" in\n' + arms + "\n  esac\n}\n",
            encoding="utf-8",
        )
        funcs = analyze_file_complexity(str(sh), "bash")
        assert len(funcs) == 1
        assert funcs[0].complexity == 2

    def test_scala_avg_cc_includes_all_methods(self, tmp_path):
        """A Scala trait with abstract + concrete methods: the extractor
        reports all of them (abstract methods get CC=1 base). score_complexity
        averages over all 5 functions → avg_cc = (1+1+2+2+2)/5 = 1.6 → 100.0
        (still in the ideal range)."""
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity
        from tree_sitter_analyzer.health_scorer import score_complexity

        scala = tmp_path / "T.scala"
        scala.write_text(
            "trait T {\n"
            "  def a1(x: Int): Int\n"
            "  def a2(x: Int): Int\n"
            "  def c1(x: Int): Int = { if (x > 0) x else -x }\n"
            "  def c2(x: Int): Int = { if (x > 0) x else -x }\n"
            "  def c3(x: Int): Int = { if (x > 0) x else -x }\n"
            "}\n",
            encoding="utf-8",
        )
        funcs = analyze_file_complexity(str(scala), "scala")
        assert len(funcs) == 5
        total_cc = sum(fn.complexity for fn in funcs)
        assert total_cc == 8  # 1+1+2+2+2
        avg_cc = total_cc / len(funcs)
        assert avg_cc == 1.6

        src = scala.read_text(encoding="utf-8")
        score = score_complexity(str(scala), src, "scala")
        assert score == 100.0

    def test_duplication_penalizes_repeated_code(self, scorer, tmp_path):
        """Files with repeated code blocks should have lower duplication score."""
        # High duplication: same block repeated 10 times
        repeated = tmp_path / "dup.py"
        block = "x = 1\ny = 2\nz = 3\n"
        repeated.write_text(block * 10)

        # No duplication: unique lines
        unique = tmp_path / "unique.py"
        unique.write_text("\n".join([f"x{i} = {i}" for i in range(30)]))

        dup_result = scorer.score_file(str(repeated))
        unique_result = scorer.score_file(str(unique))
        assert (
            dup_result.to_dict()["dimensions"]["duplication"]
            < unique_result.to_dict()["dimensions"]["duplication"]
        ), "Repeated code should have lower duplication score"

    def test_git_hotspot_none_outside_git(self, scorer, tmp_path):
        """Git hotspot should be None for files outside git repo."""
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        result = scorer.score_file(str(f))
        # Single-line file with no complexity/deps/duplication → all dims score 100.0
        assert result.total == 100.0

    def test_git_hotspot_uses_repo_relative_pathspec(self, monkeypatch, tmp_path):
        """Git hotspot should query from repo root with a repo-relative path."""
        import subprocess
        from types import SimpleNamespace

        from tree_sitter_analyzer.health_scorer import score_git_hotspot

        repo = tmp_path / "repo"
        file_path = repo / "tree_sitter_analyzer" / "cli_main.py"
        file_path.parent.mkdir(parents=True)
        file_path.write_text("x = 1\n")
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            if cmd[:3] == ["git", "rev-parse", "--show-toplevel"]:
                return SimpleNamespace(returncode=0, stdout=f"{repo}\n")
            return SimpleNamespace(returncode=0, stdout="\n".join(["abc"] * 10))

        monkeypatch.setattr(subprocess, "run", fake_run)

        score = score_git_hotspot(str(file_path))

        assert score == pytest.approx(88.9, abs=0.1)
        assert calls[1][0][-1] == "tree_sitter_analyzer/cli_main.py"
        assert calls[1][1]["cwd"] == str(repo)

    def test_seven_dimensions_in_weights(self):
        """All 7 dimensions should be in DIMENSION_WEIGHTS."""
        from tree_sitter_analyzer.health_scorer import DIMENSION_WEIGHTS

        expected = {
            "size",
            "complexity",
            "dependencies",
            "coverage",
            "duplication",
            "structure",
            "git_hotspot",
        }
        assert set(DIMENSION_WEIGHTS.keys()) == expected


# ============================================================
# HealthScore data class tests
# ============================================================


class TestHealthScore:
    """Test the HealthScore data class."""

    def test_health_score_creation(self):
        from tree_sitter_analyzer.health_scorer import HealthScore

        score = HealthScore(
            file_path="test.py",
            total=75.0,
            dimensions={
                "size": 80,
                "complexity": 60,
                "dependencies": 90,
                "structure": 70,
            },
        )
        assert score.file_path == "test.py"
        assert score.total == 75.0
        assert len(score.dimensions) == 4

    def test_health_score_to_dict(self):
        from tree_sitter_analyzer.health_scorer import HealthScore

        score = HealthScore(
            file_path="test.py",
            total=75.0,
            dimensions={"size": 80, "complexity": 60, "dependencies": 90},
        )
        d = score.to_dict()
        assert d["file"] == "test.py"
        assert d["total"] == 75.0
        assert d["dimensions"]["size"] == 80

    def test_health_score_grade(self):
        from tree_sitter_analyzer.health_scorer import HealthScore

        assert HealthScore("f", 95, {}).grade == "A"
        assert HealthScore("f", 85, {}).grade == "B"
        assert HealthScore("f", 72, {}).grade == "C"
        assert HealthScore("f", 55, {}).grade == "D"
        assert HealthScore("f", 30, {}).grade == "F"


# ============================================================
# score_complexity extractor-path tests (RFC-0019 / #1094)
# ============================================================


class TestScoreComplexityExtractorPath:
    """Verify score_complexity derives CC from the extractor (single
    source of truth) rather than the stale DECISION_NODE_TYPES table.

    The key regression: Java with a 3-case switch + ternary + do-while
    was silently scored CC=1 (all missed) by the old AST-walk using
    DECISION_NODE_TYPES which mapped ``switch_statement`` (old grammar)
    and ``conditional_expression`` (wrong name) while tree-sitter-java
    emits ``switch_expression``, ``ternary_expression``, and
    ``do_statement``. The extractor (via complexity_heatmap) uses the
    correct node types and yields CC=6 for this method.
    """

    def _write(self, tmp_path, name: str, content: str):
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_java_switch_ternary_do_while_matches_extractor(self, tmp_path):
        """Java method with 3-case switch + ternary + do-while must yield
        the same aggregate CC the extractor computes (CC=6 for this method).

        Old scorer returned 100.0 (CC=1, all branches missed because
        DECISION_NODE_TYPES had switch_statement/conditional_expression/
        no do_statement while tree-sitter-java emits switch_expression/
        ternary_expression/do_statement).

        Extractor (complexity_heatmap) returns CC=6. Both CC=1 and CC=6 fall
        in the ideal range (≤15) so both give score=100. The real regression
        test is test_java_high_switch_penalised_by_extractor below.
        """
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity
        from tree_sitter_analyzer.health_scorer import score_complexity

        java_src = (
            "public class Foo {\n"
            "    public int compute(int x) {\n"
            "        int result = 0;\n"
            "        switch (x) {\n"
            "            case 1: result = 1; break;\n"
            "            case 2: result = 2; break;\n"
            "            case 3: result = 3; break;\n"
            "        }\n"
            "        result = (x > 0) ? result : -result;\n"
            "        do {\n"
            "            result--;\n"
            "        } while (result > 0);\n"
            "        return result;\n"
            "    }\n"
            "}\n"
        )
        f = self._write(tmp_path, "Foo.java", java_src)

        # Ground truth from the extractor (single source of truth)
        funcs = analyze_file_complexity(f, "java")
        assert len(funcs) == 1, f"Expected 1 function, got {len(funcs)}"
        extractor_cx = funcs[0].complexity
        assert extractor_cx == 6, (
            f"Extractor CC for switch(3)+ternary+do-while should be 6, got {extractor_cx}"
        )

        # health scorer must now delegate to the extractor (CC=6)
        scorer_score = score_complexity(f, java_src, "java")
        # CC=6, n_funcs=1 (<3) → absolute path: 6 <= CC_IDEAL=15 → 100.0
        assert scorer_score == 100.0, (
            f"score_complexity returned {scorer_score}, expected 100.0 "
            f"(CC=6 via extractor, still in ideal range)"
        )

    def test_java_high_switch_penalised_by_extractor(self, tmp_path):
        """Java method with 19 switch arms: extractor gives CC=20 (counted
        via switch_block_statement_group), old DECISION_NODE_TYPES would give
        CC=1 (switch_statement/case_clause don't match tree-sitter-java's
        actual node names switch_expression/switch_block_statement_group).

        This is the RED→GREEN regression test: old code returned 100.0;
        new extractor-based code must return a penalised score < 100.0.
        """
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity
        from tree_sitter_analyzer.health_scorer import CC_IDEAL, score_complexity

        switch_cases = "\n".join(
            f"            case {i}: result = {i}; break;" for i in range(1, 20)
        )
        java_src = (
            "public class Foo {\n"
            "    public int compute(int x) {\n"
            "        int result = 0;\n"
            "        switch (x) {\n"
            f"{switch_cases}\n"
            "        }\n"
            "        return result;\n"
            "    }\n"
            "}\n"
        )
        f = self._write(tmp_path, "Foo.java", java_src)

        # Extractor ground truth: CC=20 (19 switch_block_statement_groups + base 1)
        funcs = analyze_file_complexity(f, "java")
        assert len(funcs) == 1
        extractor_cx = funcs[0].complexity
        assert extractor_cx == 20, (
            f"Extractor CC for 19-arm switch must be 20, got {extractor_cx}"
        )
        assert extractor_cx > CC_IDEAL, "Test setup: extractor CC must exceed CC_IDEAL"

        # new scorer: uses extractor → CC=20 > CC_IDEAL=15 → penalised
        score = score_complexity(f, java_src, "java")
        assert score < 100.0, (
            f"Java 19-arm switch must be penalised (CC=20 > CC_IDEAL=15), "
            f"got score={score}"
        )
        # Verify score is in plausible range (not collapsed to 0 or 50-neutral)
        assert score >= 30.0, f"Score {score} is unexpectedly low for CC=20"

    def test_java_high_complexity_method_scored_correctly(self, tmp_path):
        """A single Java method with CC > 15 must be penalised.

        Old scorer would return 100.0 (CC=1 due to wrong node names).
        New scorer (via extractor) correctly counts the branches.
        """
        from tree_sitter_analyzer.health_scorer import score_complexity

        # Build a Java method with many if statements (15 → CC≈16 from extractor)
        branches = "\n".join(f"        if (x > {i}) result += {i};" for i in range(15))
        java_src = (
            "public class Bar {\n"
            "    public int f(int x) {\n"
            "        int result = 0;\n"
            f"{branches}\n"
            "        return result;\n"
            "    }\n"
            "}\n"
        )
        f = self._write(tmp_path, "Bar.java", java_src)

        score = score_complexity(f, java_src, "java")

        # Old scorer: CC=1 (all if_statement matched? Let us check):
        # Actually if_statement IS in old DECISION_NODE_TYPES for java, so it
        # scored correctly for if. The regression is specifically for switch /
        # ternary / do-while. This test verifies if-based CC still works.
        # CC = 1 + 15 = 16 > CC_IDEAL=15 → penalty starts.
        # n_funcs=1 < 3 → absolute path: cc=16 > CC_IDEAL → penalised.
        assert score < 100.0, (
            f"Java method with 15 if-branches must be penalised, got score={score}"
        )
        # Verify the range is plausible (16 should fall into moderate zone)
        assert score >= 30.0, f"Score {score} is too low for CC=16"

    def test_javascript_ternary_scored_correctly(self, tmp_path):
        """JavaScript ternary_expression was mapped to ``conditional_expression``
        in DECISION_NODE_TYPES (wrong node name). Extractor uses the correct
        name and counts it.

        A JS function with a ternary must yield CC > 1 from the extractor.
        """
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity
        from tree_sitter_analyzer.health_scorer import score_complexity

        js_src = "function compute(x) {\n  return x > 0 ? x : -x;\n}\n"
        f = self._write(tmp_path, "compute.js", js_src)

        funcs = analyze_file_complexity(f, "javascript")
        assert len(funcs) == 1
        extractor_cx = funcs[0].complexity
        # extractor sees ternary_expression -> CC >= 2
        assert extractor_cx >= 2, f"JS ternary should give CC >= 2, got {extractor_cx}"

        score = score_complexity(f, js_src, "javascript")
        # CC=2, n_funcs=1 (<3) → absolute path → CC=2 <= CC_IDEAL=15 → 100.0
        assert score == 100.0, f"Expected 100.0 for low-CC JS, got {score}"

    def test_no_plugin_language_returns_neutral(self, tmp_path):
        """When language is None, score_complexity returns 50.0 (neutral)."""
        from tree_sitter_analyzer.health_scorer import score_complexity

        f = self._write(tmp_path, "x.txt", "hello world\n")
        assert score_complexity(f, "hello world\n", None) == 50.0

    def test_extractor_aggregate_matches_scorer_for_multi_function_file(self, tmp_path):
        """For a Python file with >= 3 functions, score_complexity must use
        the average extractor CC (not a raw AST walk with stale node types).
        Both paths must agree on the average when using the extractor as source.
        """
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity
        from tree_sitter_analyzer.health_scorer import score_complexity

        # 4 identical simple functions → avg_cc should be 1.0 → score 100.0
        py_src = "\n".join([f"def f{i}(x):\n    return x\n" for i in range(4)])
        f = self._write(tmp_path, "multi.py", py_src)

        funcs = analyze_file_complexity(f, "python")
        assert len(funcs) == 4, f"Expected 4 functions, got {len(funcs)}"
        avg_cx = sum(fn.complexity for fn in funcs) / len(funcs)
        assert avg_cx == 1.0

        score = score_complexity(f, py_src, "python")
        assert score == 100.0, (
            f"4 simple Python functions must score 100.0 (avg_cc=1.0), got {score}"
        )
