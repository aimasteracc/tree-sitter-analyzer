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

    def test_decision_node_types_cover_major_languages(self):
        """All major languages should have CC decision node definitions."""
        from tree_sitter_analyzer.health_scorer import DECISION_NODE_TYPES

        expected_counts = {
            "python": 14,
            "javascript": 11,
            "typescript": 11,
            "java": 8,
            "c": 8,
            "cpp": 10,
            "go": 6,
            "rust": 8,
            "ruby": 12,
            "php": 9,
            "kotlin": 9,
            "csharp": 10,
        }
        for lang, expected in expected_counts.items():
            assert lang in DECISION_NODE_TYPES, f"Missing CC nodes for {lang}"
            assert len(DECISION_NODE_TYPES[lang]) == expected, (
                f"{lang} has {len(DECISION_NODE_TYPES[lang])} decision node types, expected {expected}"
            )

    def test_bash_scala_have_complexity_node_types(self):
        """bash/scala must have CC decision + function node types so newly
        scanned shell/Scala files do not always score a perfect CC=1 100."""
        from tree_sitter_analyzer.health_scorer import (
            DECISION_NODE_TYPES,
            FUNCTION_NODE_TYPES,
        )

        assert DECISION_NODE_TYPES["bash"] == {
            "if_statement",
            "while_statement",
            "for_statement",
            "case_item",
            "elif_clause",
        }
        assert FUNCTION_NODE_TYPES["bash"] == {"function_definition"}
        assert DECISION_NODE_TYPES["scala"] == {
            "if_expression",
            "while_expression",
            "for_expression",
            "match_expression",
            "case_clause",
        }
        assert FUNCTION_NODE_TYPES["scala"] == {
            "function_definition",
            "function_declaration",
        }

    def test_swift_has_function_node_types(self):
        """swift had DECISION_NODE_TYPES but no FUNCTION_NODE_TYPES, so
        multi-function Swift files skipped per-function CC normalization."""
        from tree_sitter_analyzer.health_scorer import FUNCTION_NODE_TYPES

        assert FUNCTION_NODE_TYPES["swift"] == {
            "function_declaration",
            "init_declaration",
            "deinit_declaration",
            "subscript_declaration",
        }

    def test_bash_complexity_counts_decision_nodes(self, scorer, tmp_path):
        """A bash function with these branches must yield CC=12: 4 if + 2
        while + 2 for + 2 case_item (the 2-arm case) + 1 elif = 11 decision
        nodes, +1 base. The 2-arm case contributes 2 (one per arm) now that
        ``case_item`` replaced the wrapping ``case_statement``."""
        from tree_sitter_analyzer.core.parser import Parser
        from tree_sitter_analyzer.health_scorer import (
            DECISION_NODE_TYPES,
            FUNCTION_NODE_TYPES,
        )

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
        parser = Parser()
        result = parser.parse_file(str(sh), "bash")
        decision = DECISION_NODE_TYPES["bash"]
        function = FUNCTION_NODE_TYPES["bash"]
        cc = 1
        n_funcs = 0

        def walk(node):
            nonlocal cc, n_funcs
            if node.type in decision:
                cc += 1
            if node.type in function:
                n_funcs += 1
            for child in node.children:
                walk(child)

        walk(result.tree.root_node)
        assert cc == 12
        assert n_funcs == 1

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

    def test_bash_case_scores_one_decision_per_arm(self, tmp_path):
        """A K-arm bash ``case`` dispatch must score K decision points (one
        ``case_item`` per arm), not 1 for the whole ``case_statement``. A
        10-arm case therefore yields CC = 1 + 10 = 11."""
        from tree_sitter_analyzer.core.parser import Parser
        from tree_sitter_analyzer.health_scorer import (
            DECISION_NODE_TYPES,
            FUNCTION_NODE_TYPES,
        )

        arms = "\n".join(f"    {i}) echo {i} ;;" for i in range(1, 11))
        sh = tmp_path / "dispatch.sh"
        sh.write_text(
            '#!/bin/bash\ndispatch() {\n  case "$1" in\n' + arms + "\n  esac\n}\n",
            encoding="utf-8",
        )
        parser = Parser()
        result = parser.parse_file(str(sh), "bash")
        decision = DECISION_NODE_TYPES["bash"]
        function = FUNCTION_NODE_TYPES["bash"]
        cc = 1
        n_funcs = 0
        n_case_items = 0

        def walk(node):
            nonlocal cc, n_funcs, n_case_items
            if node.type in decision:
                cc += 1
            if node.type == "case_item":
                n_case_items += 1
            if node.type in function:
                n_funcs += 1
            for child in node.children:
                walk(child)

        walk(result.tree.root_node)
        assert n_case_items == 10
        assert cc == 11
        assert n_funcs == 1

    def test_scala_avg_cc_skips_no_body_abstract_methods(self, tmp_path):
        """A Scala trait with N abstract methods (``function_declaration``,
        no body) + M concrete methods (``function_definition``, with body)
        must average CC over only the M concrete ones. Abstract methods carry
        0 branches; counting them in ``n_funcs`` would dilute the average and
        inflate the score."""
        from tree_sitter_analyzer.core.parser import Parser
        from tree_sitter_analyzer.health_scorer import (
            DECISION_NODE_TYPES,
            FUNCTION_NODE_TYPES,
            _has_function_body,
        )

        scala = tmp_path / "T.scala"
        # 2 abstract (no body) + 3 concrete (each has one `if` -> 1 branch).
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
        parser = Parser()
        result = parser.parse_file(str(scala), "scala")
        decision = DECISION_NODE_TYPES["scala"]
        function = FUNCTION_NODE_TYPES["scala"]
        cc = 1
        n_funcs = 0
        n_funcs_all = 0

        def walk(node):
            nonlocal cc, n_funcs, n_funcs_all
            if node.type in decision:
                cc += 1
            if node.type in function:
                n_funcs_all += 1
                if _has_function_body(node):
                    n_funcs += 1
            for child in node.children:
                walk(child)

        walk(result.tree.root_node)
        # 5 declarations exist, but only 3 have bodies.
        assert n_funcs_all == 5
        assert n_funcs == 3
        # 3 `if` branches + base 1.
        assert cc == 4

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
