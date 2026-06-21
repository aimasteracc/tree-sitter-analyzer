"""Tests for CodeGraphPRReviewTool — AST diff + semantic classify + call graph review."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool import (
    CodeGraphPRReviewTool,
    FileReview,
    PRReviewResult,
    _build_recommendations,
    _compute_verdict,
    _extract_file_diff,
    _extract_old_new_from_diff,
    _filter_affected_by_language,
    _get_local_diff,
    _parse_diff_files,
    _risk_to_score,
    _score_to_risk,
)


def _run(tool: CodeGraphPRReviewTool, args: dict) -> dict:
    return asyncio.run(tool.execute(args))


def _make_project(*files: tuple[str, str]) -> str:
    tmpdir = tempfile.mkdtemp()
    for name, content in files:
        p = Path(tmpdir) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmpdir


class TestHelpers:
    def test_risk_to_score(self):
        assert _risk_to_score("low") == 1
        assert _risk_to_score("medium") == 2
        assert _risk_to_score("high") == 3
        assert _risk_to_score("critical") == 4
        assert _risk_to_score("unknown") == 2

    def test_score_to_risk(self):
        assert _score_to_risk(0.5) == "low"
        assert _score_to_risk(1.5) == "medium"
        assert _score_to_risk(2.5) == "high"
        assert _score_to_risk(3.5) == "critical"

    def test_compute_verdict(self):
        # pain #9 (dogfood pass 2): PR review verdict must use canonical set
        # (SAFE | CAUTION | REVIEW | UNSAFE | INFO | WARN | ERROR | NOT_FOUND).
        # Old values CLEAN / NEEDS_REVIEW / LOOKS_GOOD were silently ignored
        # by agents branching on verdict.
        assert _compute_verdict("critical", 1, 10) == "CAUTION"
        assert _compute_verdict("high", 0, 0) == "CAUTION"
        assert _compute_verdict("medium", 1, 4) == "REVIEW"
        assert _compute_verdict("low", 0, 0) == "INFO"

    def test_parse_diff_files(self):
        diff = (
            "diff --git a/foo.py b/foo.py\n"
            "--- a/foo.py\n"
            "+++ b/foo.py\n"
            "@@ -1,3 +1,4 @@\n"
            "+import os\n"
            "diff --git a/bar.js b/bar.js\n"
            "--- a/bar.js\n"
            "+++ b/bar.js\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )
        files = _parse_diff_files(diff)
        assert "foo.py" in files
        assert "bar.js" in files

    def test_branch_diff_uses_current_pr_base(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[0] == "gh":
                return MagicMock(returncode=0, stdout="develop\n")
            if cmd[:3] == ["git", "show-ref", "--verify"]:
                return MagicMock(returncode=0)
            if cmd[:2] == ["git", "diff"]:
                return MagicMock(returncode=0, stdout="diff text")
            return MagicMock(returncode=1, stdout="")

        with patch("subprocess.run", side_effect=fake_run):
            assert _get_local_diff("branch", "/repo") == "diff text"

        assert calls == [
            ["gh", "pr", "view", "--json", "baseRefName", "--jq", ".baseRefName"],
            [
                "git",
                "show-ref",
                "--verify",
                "--quiet",
                "refs/remotes/origin/develop",
            ],
            ["git", "diff", "origin/develop...HEAD"],
        ]

    def test_build_recommendations_empty(self):
        recs = _build_recommendations([], [], [])
        assert len(recs) == 1
        assert "Low-risk" in recs[0]

    def test_build_recommendations_api_changes(self):
        review = FileReview(
            file_path="api.py",
            language="python",
            dominant_category="api_change",
            risk_level="high",
            change_summary="API change",
            category_counts={"api_change": 1},
            hunk_count=2,
        )
        recs = _build_recommendations([review], ["api.py: signature changed"], [])
        assert any("API breaking" in r for r in recs)


class TestFileReview:
    def test_to_dict_minimal(self):
        r = FileReview(
            file_path="test.py",
            language="python",
            dominant_category="internal_change",
            risk_level="low",
            change_summary="minor",
            category_counts={},
            hunk_count=1,
        )
        d = r.to_dict()
        assert d["file"] == "test.py"
        assert d["risk"] == "low"
        assert "categories" not in d

    def test_to_dict_with_details(self):
        r = FileReview(
            file_path="test.py",
            language="python",
            dominant_category="api_change",
            risk_level="high",
            change_summary="api change",
            category_counts={"api_change": 2},
            hunk_count=3,
            high_risk_hunks=[{"category": "api_change", "risk": "high"}],
        )
        d = r.to_dict()
        assert d["categories"] == {"api_change": 2}
        assert len(d["high_risk_changes"]) == 1


class TestPRReviewResult:
    def test_to_dict(self):
        r = PRReviewResult(
            files_reviewed=3,
            files_skipped=1,
            overall_risk="medium",
            overall_verdict="CAUTION",
            file_reviews=[],
            api_changes=["a.py: sig"],
            affected_functions=[{"function": "foo", "direction": "upstream"}],
            recommendations=["Check this"],
        )
        d = r.to_dict()
        assert d["files_reviewed"] == 3
        assert d["overall_risk"] == "medium"
        assert d["verdict"] == "CAUTION"
        assert len(d["api_changes"]) == 1
        assert len(d["recommendations"]) == 1


class TestCodeGraphPRReviewTool:
    def test_tool_definition(self):
        tool = CodeGraphPRReviewTool()
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_pr_review"
        assert "AST diff" in defn["description"]
        schema = tool.get_tool_schema()
        assert "mode" in schema["properties"]
        assert "pr_url" in schema["properties"]

    def test_validate_bad_mode(self):
        tool = CodeGraphPRReviewTool()
        with pytest.raises(ValueError, match="mode must be"):
            asyncio.run(tool.validate_arguments({"mode": "invalid"}))

    def test_no_changes(self):
        tmpdir = _make_project(("main.py", "print('hello')\n"))
        tool = CodeGraphPRReviewTool(tmpdir)
        with patch(
            "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool._get_local_diff",
            return_value="",
        ):
            result = _run(tool, {"mode": "diff"})
        assert result["success"] is True
        assert result["files_reviewed"] == 0

    def test_local_diff_review(self):
        src_old = "def old_func():\n    pass\n"
        src_new = (
            "def old_func():\n    return 42\n\ndef new_func(x):\n    return x + 1\n"
        )
        tmpdir = _make_project(("example.py", src_new))
        diff_text = (
            "diff --git a/example.py b/example.py\n"
            "--- a/example.py\n"
            "+++ b/example.py\n"
            "@@ -1,2 +1,4 @@\n"
            "-def old_func():\n"
            "-    pass\n"
            "+def old_func():\n"
            "+    return 42\n"
            "+\n"
            "+def new_func(x):\n"
            "+    return x + 1\n"
        )
        tool = CodeGraphPRReviewTool(tmpdir)
        with patch(
            "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool._get_local_diff",
            return_value=diff_text,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool._get_old_source",
                return_value=src_old,
            ):
                result = _run(
                    tool,
                    {
                        "mode": "diff",
                        "include_call_graph": False,
                        "output_format": "json",
                    },
                )
        assert result["success"] is True
        assert result["files_reviewed"]
        assert "overall_risk" in result
        assert "verdict" in result
        assert "recommendations" in result

    def test_pr_url_invalid(self):
        tool = CodeGraphPRReviewTool()
        result = _run(tool, {"mode": "pr", "pr_url": "not-a-url"})
        assert result["success"] is False
        assert "Invalid" in result.get("error", "")

    def test_pr_url_gh_unavailable(self):
        tool = CodeGraphPRReviewTool()
        with patch(
            "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool.check_gh_available",
            return_value=False,
        ):
            result = _run(
                tool,
                {
                    "mode": "pr",
                    "pr_url": "https://github.com/owner/repo/pull/42",
                },
            )
        assert result["success"] is False
        assert "gh CLI" in result.get("error", "")

    def test_output_format_json(self):
        tmpdir = _make_project(("main.py", "x = 1\n"))
        tool = CodeGraphPRReviewTool(tmpdir)
        with patch(
            "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool._get_local_diff",
            return_value="",
        ):
            result = _run(tool, {"mode": "diff", "output_format": "json"})
        assert result["success"] is True

    # ------------------------------------------------------------------
    # Issue #451 — mode=pr without pr_url must fail loudly, not silently
    # fall through to local diff and return "No changed files".
    # ------------------------------------------------------------------

    def test_pr_mode_without_pr_url_fails_with_error(self):
        """mode=pr with missing pr_url → success:False, error naming the param."""
        tool = CodeGraphPRReviewTool()
        result = _run(tool, {"mode": "pr"})
        assert result["success"] is False
        assert result.get("verdict") == "ERROR"
        assert "pr_url" in result.get("error", "")

    def test_pr_mode_with_empty_pr_url_fails_with_error(self):
        """mode=pr with pr_url='' → same failure (typo scenario from issue #451)."""
        tool = CodeGraphPRReviewTool()
        result = _run(tool, {"mode": "pr", "pr_url": ""})
        assert result["success"] is False
        assert result.get("verdict") == "ERROR"
        assert "pr_url" in result.get("error", "")

    def test_pr_mode_without_pr_url_has_recovery_hint(self):
        """Error response must carry a recovery_hint with a usage example."""
        tool = CodeGraphPRReviewTool()
        result = _run(tool, {"mode": "pr"})
        assert result["success"] is False
        # recovery_hint must be non-empty and guide the caller
        hint = result.get("recovery_hint", "")
        assert hint, "recovery_hint must be non-empty for mode=pr missing pr_url"
        assert "pr_url" in hint

    def test_pr_mode_wrong_param_name_fails_not_empty_success(self):
        """After facade projects args, inner receives mode=pr without pr_url.
        This simulates the #451 scenario: agent typo'd param name (e.g. query=)
        and the facade stripped it, so inner gets {mode: pr} with no pr_url.
        Direct call to the inner with only mode=pr must return error, not
        success+empty.
        """
        tool = CodeGraphPRReviewTool()
        # Simulate post-projection args: only mode=pr, no pr_url
        result = _run(tool, {"mode": "pr"})
        assert result["success"] is False
        assert result.get("verdict") == "ERROR"

    def test_no_changed_files_only_reachable_with_valid_non_pr_mode(self):
        """The 'No changed files found' path must only trigger for non-pr modes
        where the diff is genuinely empty — NOT when mode=pr is missing pr_url."""
        tmpdir = _make_project(("main.py", "x = 1\n"))
        tool = CodeGraphPRReviewTool(tmpdir)
        # Non-pr mode with empty local diff → still OK to return NOT_FOUND
        with patch(
            "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool._get_local_diff",
            return_value="",
        ):
            result = _run(tool, {"mode": "diff"})
        assert result["success"] is True
        assert result["files_reviewed"] == 0
        assert result.get("verdict") == "NOT_FOUND"


# ------------------------------------------------------------------
# Issue #450 — same-name phantom edges across languages must be dropped
# ------------------------------------------------------------------


class TestPhantomEdgeFilter:
    """RED-first tests for _filter_affected_by_language (Issue #450).

    Scenario: a PR touches kotlin_helpers.kt (a real Kotlin file).
    The call graph returns:
      - REAL upstream: kotlin_caller.kt → extract_kotlin_function  (kotlin, specific name)
      - PHANTOM upstream: swift_file.swift → extract_kotlin_function (swift, cross-lang)
      - PHANTOM downstream: toon_encoder.py → encode (python, cross-lang; also known-generic)
      - AMBIGUOUS upstream: helper.kt → some_generic  (kotlin, same-lang but count ≥ threshold)

    After filtering:
      - affected_functions contains exactly ["kotlin_caller.kt extract_kotlin_function"]
      - stats.cross_language_edges_dropped accounts for cross-lang phantoms
      - stats.ambiguous_name_edges_dropped accounts for dropped generic names
    """

    def _make_func(
        self,
        name: str,
        file: str,
        language: str,
        direction: str = "upstream",
    ) -> dict:
        return {
            "function": name,
            "file": file,
            "language": language,
            "direction": direction,
            "line": 1,
        }

    def test_same_language_specific_name_kept(self):
        """A same-language upstream edge with a specific (non-generic) name must survive."""
        changed_langs = {"kotlin"}
        funcs = [
            self._make_func("extract_kotlin_function", "kotlin_caller.kt", "kotlin")
        ]
        kept, stats = _filter_affected_by_language(
            funcs, changed_langs, name_file_count={}
        )
        function_names = [f["function"] for f in kept]
        assert function_names == ["extract_kotlin_function"]
        assert stats["cross_language_edges_dropped"] == 0
        assert stats["ambiguous_name_edges_dropped"] == 0

    def test_cross_language_phantom_dropped(self):
        """A swift phantom for a kotlin change must be dropped (cross-language gate)."""
        changed_langs = {"kotlin"}
        funcs = [
            self._make_func("extract_kotlin_function", "kotlin_caller.kt", "kotlin"),
            self._make_func("extract_kotlin_function", "_swift_plugin.py", "swift"),
        ]
        kept, stats = _filter_affected_by_language(
            funcs, changed_langs, name_file_count={}
        )
        assert len(kept) == 1
        assert kept[0]["file"] == "kotlin_caller.kt"
        assert stats["cross_language_edges_dropped"] == 1
        assert stats["ambiguous_name_edges_dropped"] == 0

    def test_ambiguous_count_name_dropped(self):
        """A same-language edge whose bare name exists in ≥ threshold files is
        dropped with ambiguous_name_edges_dropped incremented."""
        changed_langs = {"kotlin"}
        # "some_util" appears in 5 files — above threshold
        name_file_count = {"some_util": 5}
        funcs = [
            self._make_func("extract_kotlin_function", "kotlin_caller.kt", "kotlin"),
            self._make_func(
                "some_util", "helper.kt", "kotlin"
            ),  # same-lang but ambiguous
        ]
        kept, stats = _filter_affected_by_language(
            funcs, changed_langs, name_file_count=name_file_count
        )
        kept_names = [f["function"] for f in kept]
        assert kept_names == ["extract_kotlin_function"]
        assert stats["ambiguous_name_edges_dropped"] == 1
        assert stats["cross_language_edges_dropped"] == 0

    def test_known_generic_callback_name_dropped(self):
        """A name in _KNOWN_GENERIC_CALLBACK_NAMES is dropped even below count threshold."""
        from tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool import (
            _KNOWN_GENERIC_CALLBACK_NAMES,
        )

        changed_langs = {"python"}
        # "get_node_text" is in KNOWN_GENERIC_CALLBACK_NAMES; count below threshold
        funcs = [
            self._make_func("extract_kotlin_function", "kotlin_caller.py", "python"),
            self._make_func("get_node_text", "_swift_extractor.py", "python"),
        ]
        kept, stats = _filter_affected_by_language(
            funcs, changed_langs, name_file_count={}
        )
        assert len(kept) == 1
        assert kept[0]["function"] == "extract_kotlin_function"
        assert stats["ambiguous_name_edges_dropped"] == 1
        assert "get_node_text" in _KNOWN_GENERIC_CALLBACK_NAMES

    def test_full_scenario_exact_pin(self):
        """Integration scenario: kotlin change with real caller + swift phantom
        + python downstream phantom (known-generic) + ambiguous same-lang edge.

        After filtering: exactly ["kotlin_caller.kt extract_kotlin_function"] kept.
        cross_language_edges_dropped == 1 (swift phantom)
        ambiguous_name_edges_dropped == 2 (known-generic encode + count-generic some_util)
        """
        changed_langs = {"kotlin"}
        # "some_util" has count=5 (above threshold); "encode" is in KNOWN list
        name_file_count = {"some_util": 5}
        funcs = [
            # REAL — same language, non-ambiguous, specific name
            self._make_func(
                "extract_kotlin_function",
                "kotlin_caller.kt",
                "kotlin",
                direction="upstream",
            ),
            # PHANTOM — swift, different language family
            self._make_func(
                "extract_kotlin_function",
                "_swift_plugin.py",
                "swift",
                direction="upstream",
            ),
            # PHANTOM — known generic callback name (encode)
            self._make_func("encode", "some_util.kt", "kotlin", direction="downstream"),
            # AMBIGUOUS — same lang but count ≥ threshold
            self._make_func("some_util", "helper.kt", "kotlin", direction="upstream"),
        ]
        kept, stats = _filter_affected_by_language(
            funcs, changed_langs, name_file_count=name_file_count
        )
        # Exact pin: only the specific kotlin edge survives
        assert len(kept) == 1
        assert kept[0]["file"] == "kotlin_caller.kt"
        assert kept[0]["function"] == "extract_kotlin_function"
        assert stats["cross_language_edges_dropped"] == 1
        assert stats["ambiguous_name_edges_dropped"] == 2

    def test_empty_language_passes_through(self):
        """An edge with empty/unknown language must not be dropped (unknown > wrong)."""
        changed_langs = {"kotlin"}
        funcs = [self._make_func("mystery_specific_func", "some_file.ext", "")]
        kept, stats = _filter_affected_by_language(
            funcs, changed_langs, name_file_count={}
        )
        assert len(kept) == 1
        assert stats["cross_language_edges_dropped"] == 0

    # ------------------------------------------------------------------
    # Item 1: directional language gate (Codex P2) — upstream vs downstream
    # C-family rules from _language_family._DIRECTED_C_COMPAT:
    #   cpp → c  is allowed  (C++ caller, C header)
    #   c → cpp  is NOT allowed (pure-C caller, C++ definition)
    # ------------------------------------------------------------------

    def test_upstream_cpp_caller_of_c_header_kept(self):
        """Upstream edge: C++ caller calls into a changed .h (indexed as 'c').
        languages_compatible(candidate_lang='cpp', changed_lang='c') → True → kept.
        """
        changed_langs = {"c"}  # the changed .h file is indexed as c
        funcs = [
            {
                "function": "my_func",
                "file": "src/consumer.cpp",
                "language": "cpp",
                "direction": "upstream",  # cpp calls into the changed c header
                "line": 10,
            }
        ]
        kept, stats = _filter_affected_by_language(
            funcs, changed_langs, name_file_count={}
        )
        assert len(kept) == 1
        assert kept[0]["file"] == "src/consumer.cpp"
        assert stats["cross_language_edges_dropped"] == 0

    def test_upstream_pure_c_caller_of_cpp_definition_dropped(self):
        """Upstream edge: pure-C caller calls into a changed .cpp definition.
        languages_compatible(candidate_lang='c', changed_lang='cpp') → False → dropped.
        """
        changed_langs = {"cpp"}
        funcs = [
            {
                "function": "cpp_func",
                "file": "src/pure_c_caller.c",
                "language": "c",
                "direction": "upstream",  # c tries to call cpp — foreign binding
                "line": 5,
            }
        ]
        kept, stats = _filter_affected_by_language(
            funcs, changed_langs, name_file_count={}
        )
        assert len(kept) == 0
        assert stats["cross_language_edges_dropped"] == 1

    def test_downstream_cpp_definition_called_from_c_header_dropped(self):
        """Downstream edge: changed c file calls a cpp definition.
        languages_compatible(changed_lang='c', candidate_lang='cpp') → False → dropped.
        (c→cpp is not in _DIRECTED_C_COMPAT)
        """
        changed_langs = {"c"}
        funcs = [
            {
                "function": "cpp_impl",
                "file": "src/impl.cpp",
                "language": "cpp",
                "direction": "downstream",  # changed c file calling cpp — blocked
                "line": 20,
            }
        ]
        kept, stats = _filter_affected_by_language(
            funcs, changed_langs, name_file_count={}
        )
        assert len(kept) == 0
        assert stats["cross_language_edges_dropped"] == 1

    def test_downstream_c_definition_called_from_cpp_caller_kept(self):
        """Downstream edge: changed cpp file calls a c definition (c header).
        languages_compatible(changed_lang='cpp', candidate_lang='c') → True → kept.
        """
        changed_langs = {"cpp"}
        funcs = [
            {
                "function": "c_util",
                "file": "src/util.c",
                "language": "c",
                "direction": "downstream",  # changed cpp calling a c helper — allowed
                "line": 3,
            }
        ]
        kept, stats = _filter_affected_by_language(
            funcs, changed_langs, name_file_count={}
        )
        assert len(kept) == 1
        assert kept[0]["file"] == "src/util.c"
        assert stats["cross_language_edges_dropped"] == 0

    # ------------------------------------------------------------------
    # Item 2: ambiguity threshold counts DISTINCT FILES (Codex P2)
    # ------------------------------------------------------------------

    def test_three_same_name_functions_in_one_file_not_ambiguous(self):
        """3 refs of the same name all from ONE file → distinct-file count == 1
        → below threshold (3) → edge kept.
        The OLD per-ref counting would yield count=3 and drop it — that was wrong.
        Uses 'visit_node' which is not in _KNOWN_GENERIC_CALLBACK_NAMES.
        """
        from tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool import (
            _AMBIGUOUS_NAME_FILE_THRESHOLD,
            _KNOWN_GENERIC_CALLBACK_NAMES,
        )

        assert _AMBIGUOUS_NAME_FILE_THRESHOLD == 3  # pin the constant
        assert "visit_node" not in _KNOWN_GENERIC_CALLBACK_NAMES  # verify name choice

        # Build name_file_count the same way _analyze_call_graph_impact does:
        # one file defines "visit_node" 3 times (overloads / inner methods)
        name_files: dict = {"visit_node": {"only_one_file.py"}}  # 1 distinct file
        name_file_count = {n: len(fs) for n, fs in name_files.items()}
        assert name_file_count["visit_node"] == 1  # confirm distinct-file counting

        changed_langs = {"python"}
        funcs = [
            {
                "function": "visit_node",
                "file": "some_caller.py",
                "language": "python",
                "direction": "upstream",
                "line": 1,
            }
        ]
        kept, stats = _filter_affected_by_language(
            funcs, changed_langs, name_file_count=name_file_count
        )
        # count=1 < threshold=3 → NOT ambiguous → kept
        assert len(kept) == 1
        assert stats["ambiguous_name_edges_dropped"] == 0

    def test_same_name_across_three_distinct_files_is_ambiguous(self):
        """Same name in 3 different files → distinct-file count == 3
        → meets threshold → edge dropped + counted in ambiguous_name_edges_dropped.
        Uses 'visit_node' which is not in _KNOWN_GENERIC_CALLBACK_NAMES.
        """
        from tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool import (
            _AMBIGUOUS_NAME_FILE_THRESHOLD,
            _KNOWN_GENERIC_CALLBACK_NAMES,
        )

        assert _AMBIGUOUS_NAME_FILE_THRESHOLD == 3
        assert "visit_node" not in _KNOWN_GENERIC_CALLBACK_NAMES

        # name appears in exactly 3 distinct files
        name_file_count = {"visit_node": 3}

        changed_langs = {"python"}
        funcs = [
            {
                "function": "visit_node",
                "file": "some_caller.py",
                "language": "python",
                "direction": "upstream",
                "line": 1,
            }
        ]
        kept, stats = _filter_affected_by_language(
            funcs, changed_langs, name_file_count=name_file_count
        )
        # count=3 >= threshold=3 → ambiguous → dropped
        assert len(kept) == 0
        assert stats["ambiguous_name_edges_dropped"] == 1
        assert stats["cross_language_edges_dropped"] == 0

    def test_analyze_call_graph_impact_distinct_file_counting(self):
        """Integration: _analyze_call_graph_impact uses distinct-file counting.
        One file that defines 'visit_node' 3 times must NOT trip the ambiguity gate.
        """
        import tempfile
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        from tree_sitter_analyzer.call_graph import FunctionRef

        tmpdir = tempfile.mkdtemp()
        (Path(tmpdir) / "changed.py").write_text(
            "def process(): pass\n", encoding="utf-8"
        )
        tool = CodeGraphPRReviewTool(tmpdir)

        # anchor: the changed file's function (non-generic, non-ambiguous)
        anchor_ref = FunctionRef(
            file_path="changed.py",
            name="process_data_unique",
            start_line=1,
            language="python",
        )
        # 3 FunctionRefs for "visit_node" all from the SAME file
        same_file_ref_1 = FunctionRef(
            file_path="visitor_module.py",
            name="visit_node",
            start_line=1,
            language="python",
        )
        same_file_ref_2 = FunctionRef(
            file_path="visitor_module.py",
            name="visit_node",
            start_line=20,
            language="python",
        )
        same_file_ref_3 = FunctionRef(
            file_path="visitor_module.py",
            name="visit_node",
            start_line=40,
            language="python",
        )
        # A caller with a non-generic name
        real_caller = FunctionRef(
            file_path="consumer.py",
            name="process_data_unique_wrapper",
            start_line=5,
            language="python",
        )

        mock_graph = MagicMock()
        mock_graph.build = MagicMock()
        # function_refs returns 3 visit_node refs (same file) + anchor
        mock_graph.function_refs = MagicMock(
            return_value=[anchor_ref, same_file_ref_1, same_file_ref_2, same_file_ref_3]
        )
        mock_graph._func_by_file = {"changed.py": [anchor_ref]}
        mock_graph.caller_refs_of = MagicMock(return_value=[real_caller])
        mock_graph.callee_refs_of = MagicMock(return_value=[])

        with patch.object(tool, "_get_call_graph", return_value=mock_graph):
            result = tool._analyze_call_graph_impact(["changed.py"])

        # "process_data_unique" only appears once → not ambiguous → real_caller kept
        # "visit_node" appears 3x but from 1 file → distinct-file count = 1 → not ambiguous
        kept = result["affected_functions"]
        assert len(kept) == 1
        assert kept[0]["file"] == "consumer.py"
        assert result["stats"]["ambiguous_name_edges_dropped"] == 0

    def test_analyze_call_graph_impact_filters_phantoms(self):
        """End-to-end: _analyze_call_graph_impact populates stats fields
        and excludes cross-language phantom entries.

        The method now iterates _func_by_file + caller_refs_of/callee_refs_of
        (not file_impact) so we mock those instead.
        """
        from tree_sitter_analyzer.call_graph import FunctionRef

        tmpdir = _make_project(
            ("kotlin_helpers.kt", "fun extract_kotlin_function() {}\n"),
        )
        tool = CodeGraphPRReviewTool(tmpdir)

        # The one "real" function in the changed file (non-generic name)
        anchor_ref = FunctionRef(
            file_path="kotlin_helpers.kt",
            name="extract_kotlin_function",
            start_line=1,
            language="kotlin",
        )
        # Real kotlin upstream caller
        real_caller = FunctionRef(
            file_path="kotlin_caller.kt",
            name="call_extract",
            start_line=5,
            language="kotlin",
        )
        # Phantom swift upstream caller (cross-language)
        phantom_caller = FunctionRef(
            file_path="_swift_extractor.py",
            name="call_extract",
            start_line=3,
            language="swift",
        )
        # Downstream callee: known-generic name "encode"
        generic_callee = FunctionRef(
            file_path="toon_encoder.py",
            name="encode",
            start_line=10,
            language="kotlin",  # same language — would pass lang gate, caught by generic gate
        )

        mock_graph = MagicMock()
        mock_graph.build = MagicMock()
        mock_graph.function_refs = MagicMock(return_value=[anchor_ref])
        mock_graph._func_by_file = {"kotlin_helpers.kt": [anchor_ref]}
        mock_graph.caller_refs_of = MagicMock(
            return_value=[real_caller, phantom_caller]
        )
        mock_graph.callee_refs_of = MagicMock(return_value=[generic_callee])

        with patch.object(tool, "_get_call_graph", return_value=mock_graph):
            result = tool._analyze_call_graph_impact(["kotlin_helpers.kt"])

        kept = result["affected_functions"]
        stats = result["stats"]

        # Real kotlin upstream survives; swift phantom dropped (cross-lang gate).
        # encode dropped (known-generic gate, rule 3).
        assert len(kept) == 1
        assert kept[0]["file"] == "kotlin_caller.kt"
        assert stats["cross_language_edges_dropped"] == 1
        assert stats["ambiguous_name_edges_dropped"] == 1


# ------------------------------------------------------------------
# Coverage for helper utilities (Item 3: patch-line coverage ≥ 95%)
# ------------------------------------------------------------------


class TestHelperUtilities:
    """Cover standalone helper functions not exercised by the E2E path."""

    def test_extract_file_diff_found(self):
        diff = (
            "diff --git a/foo.py b/foo.py\n"
            "index 1234..abcd 100644\n"
            "--- a/foo.py\n"
            "+++ b/foo.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
            "diff --git a/bar.py b/bar.py\n"
            "--- a/bar.py\n"
            "+++ b/bar.py\n"
        )
        content, path = _extract_file_diff(diff, "foo.py")
        assert "old" in content
        assert path == "foo.py"

    def test_extract_file_diff_not_found_returns_empty(self):
        diff = "diff --git a/other.py b/other.py\n--- a/other.py\n+++ b/other.py\n"
        content, path = _extract_file_diff(diff, "missing.py")
        assert content == ""
        assert path == "missing.py"

    def test_extract_old_new_from_diff_basic(self):
        diff = "+new line\n-old line\n context line\n"
        old, new = _extract_old_new_from_diff(diff)
        assert "old line" in old
        assert "new line" in new

    def test_extract_old_new_no_newline_marker(self):
        r"""'\' continuation lines (e.g. '\ No newline at end of file') are skipped."""
        diff = "+new\n\\ No newline at end of file\n"
        old, new = _extract_old_new_from_diff(diff)
        assert "new" in new

    def test_get_local_diff_no_project_root(self):
        result = _get_local_diff("diff", None)
        assert result == ""

    def test_get_local_diff_subprocess_timeout(self):
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            result = _get_local_diff("diff", "/tmp")
        assert result == ""

    def test_get_local_diff_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            result = _get_local_diff("diff", "/tmp")
        assert result == ""

    def test_get_local_diff_nonzero_returncode(self):
        mock_rc = MagicMock()
        mock_rc.returncode = 1
        mock_rc.stdout = "some output"
        with patch("subprocess.run", return_value=mock_rc):
            result = _get_local_diff("diff", "/tmp")
        assert result == ""


class TestCoverageToolMethods:
    """Cover CodeGraphPRReviewTool methods not exercised by main execute path."""

    def test_call_graph_initialized_false(self):
        tool = CodeGraphPRReviewTool()
        assert tool.call_graph_initialized is False

    def test_call_graph_initialized_true_after_set(self):
        tool = CodeGraphPRReviewTool()
        tool._call_graph = MagicMock()
        assert tool.call_graph_initialized is True

    def test_get_call_graph_no_project_root(self):
        tool = CodeGraphPRReviewTool()
        import pytest

        with pytest.raises(ValueError, match="Project root not set"):
            tool._get_call_graph()

    def test_get_call_graph_public_alias(self):
        """get_call_graph() delegates to _get_call_graph()."""
        tool = CodeGraphPRReviewTool()
        mock_cg = MagicMock()
        with patch.object(tool, "_get_call_graph", return_value=mock_cg):
            assert tool.get_call_graph() is mock_cg

    def test_on_project_root_changed_resets_call_graph(self):
        tool = CodeGraphPRReviewTool()
        tool._call_graph = MagicMock()
        tool._on_project_root_changed("/new/path")
        assert tool._call_graph is None

    def test_try_get_cache_no_project_root(self):
        tool = CodeGraphPRReviewTool()
        # project_root is None → returns None without error
        assert tool._try_get_cache() is None

    def test_analyze_call_graph_impact_graph_build_exception(self):
        """If graph.build() raises, returns empty stats (no crash)."""
        tmpdir = _make_project(("f.py", "x=1\n"))
        tool = CodeGraphPRReviewTool(tmpdir)
        mock_graph = MagicMock()
        mock_graph.build.side_effect = RuntimeError("index not ready")
        with patch.object(tool, "_get_call_graph", return_value=mock_graph):
            result = tool._analyze_call_graph_impact(["f.py"])
        assert result["affected_functions"] == []
        assert result["stats"]["cross_language_edges_dropped"] == 0

    def test_analyze_call_graph_impact_function_refs_exception(self):
        """If function_refs() raises, name_file_count stays empty (no crash)."""
        from tree_sitter_analyzer.call_graph import FunctionRef

        tmpdir = _make_project(("f.py", "x=1\n"))
        tool = CodeGraphPRReviewTool(tmpdir)

        anchor_ref = FunctionRef(
            file_path="f.py", name="my_unique_func", start_line=1, language="python"
        )
        mock_graph = MagicMock()
        mock_graph.build = MagicMock()
        mock_graph.function_refs.side_effect = RuntimeError("broken")
        mock_graph._func_by_file = {"f.py": [anchor_ref]}
        mock_graph.caller_refs_of = MagicMock(return_value=[])
        mock_graph.callee_refs_of = MagicMock(return_value=[])
        with patch.object(tool, "_get_call_graph", return_value=mock_graph):
            result = tool._analyze_call_graph_impact(["f.py"])
        # Empty name_file_count → no ambiguity drops; no callers/callees → empty
        assert result["affected_functions"] == []

    def test_analyze_call_graph_impact_dedup_upstream(self):
        """Duplicate caller entries (same qualified_name) are deduplicated."""
        from tree_sitter_analyzer.call_graph import FunctionRef

        tmpdir = _make_project(("f.py", "x=1\n"))
        tool = CodeGraphPRReviewTool(tmpdir)

        anchor_ref = FunctionRef(
            file_path="f.py", name="special_func", start_line=1, language="python"
        )
        caller = FunctionRef(
            file_path="caller.py", name="do_call", start_line=3, language="python"
        )
        mock_graph = MagicMock()
        mock_graph.build = MagicMock()
        mock_graph.function_refs = MagicMock(return_value=[anchor_ref])
        mock_graph._func_by_file = {"f.py": [anchor_ref]}
        # Return same caller twice to exercise dedup path
        mock_graph.caller_refs_of = MagicMock(return_value=[caller, caller])
        mock_graph.callee_refs_of = MagicMock(return_value=[])
        with patch.object(tool, "_get_call_graph", return_value=mock_graph):
            result = tool._analyze_call_graph_impact(["f.py"])
        # Deduplicated: only 1 entry
        assert len(result["affected_functions"]) == 1

    def test_compute_verdict_fallback(self):
        """Unknown risk falls through to REVIEW (fail-safe)."""
        # The last return "REVIEW" line (l.735) is only reached for non-low unknown
        # We can't reach it with the current logic (low→INFO covers "low",
        # and the else branch only fires for truly unknown strings).
        # Actually, "low" → INFO; this checks the else-REVIEW path.
        # Verified: _compute_verdict("unknown_risk", 0, 0) → REVIEW
        result = _compute_verdict("unknown_risk", 0, 0)
        assert result == "REVIEW"

    def test_build_recommendations_large_blast_radius(self):
        """More than 5 upstream callers triggers the large-blast-radius recommendation."""
        # Need > 5 upstream entries
        affected = [
            {"function": f"func_{i}", "file": "f.py", "direction": "upstream"}
            for i in range(6)
        ]
        recs = _build_recommendations([], [], affected)
        assert any("blast radius" in r for r in recs)

    def test_build_recommendations_refactor(self):
        """Refactor files trigger the refactor recommendation."""
        review = FileReview(
            file_path="mod.py",
            language="python",
            dominant_category="refactor",
            risk_level="medium",
            change_summary="Refactored",
            category_counts={"refactor": 3},
            hunk_count=2,
        )
        recs = _build_recommendations([review], [], [])
        assert any("Refactoring" in r for r in recs)

    def test_execute_skipped_file_no_language(self):
        """Files without a recognised extension are counted in files_skipped."""
        diff_text = (
            "diff --git a/file.unknown_ext b/file.unknown_ext\n"
            "--- a/file.unknown_ext\n"
            "+++ b/file.unknown_ext\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )
        tmpdir = _make_project(("file.unknown_ext", "new\n"))
        tool = CodeGraphPRReviewTool(tmpdir)
        with patch(
            "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool._get_local_diff",
            return_value=diff_text,
        ):
            result = _run(
                tool,
                {"mode": "diff", "include_call_graph": False, "output_format": "json"},
            )
        assert result["success"] is True
        assert result["files_skipped"] == 1

    def test_get_old_source_exception(self):
        """_get_old_source returns '' when subprocess raises TimeoutExpired."""
        import subprocess

        from tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool import (
            _get_old_source,
        )

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 5)):
            assert _get_old_source("/tmp", "foo.py") == ""

    def test_get_old_source_file_not_found(self):
        """_get_old_source returns '' when git binary missing."""
        from tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool import (
            _get_old_source,
        )

        with patch("subprocess.run", side_effect=FileNotFoundError("git")):
            assert _get_old_source("/tmp", "foo.py") == ""

    def test_get_new_source_os_error(self):
        """_get_new_source returns '' when file is unreadable."""
        from tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool import (
            _get_new_source,
        )

        with patch("pathlib.Path.read_text", side_effect=OSError("no read")):
            assert _get_new_source("/tmp", "missing.py") == ""

    def test_try_get_cache_exception_returns_none(self):
        """_try_get_cache returns None when ASTCache import raises."""
        tool = CodeGraphPRReviewTool("/tmp")
        with patch(
            "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool.CodeGraphPRReviewTool._try_get_cache",
            side_effect=Exception("cache error"),
        ):
            # Patch _try_get_cache to raise; then manually call the real one
            pass
        # Test the real implementation with a broken import
        with patch(
            "tree_sitter_analyzer.ast_cache.ASTCache",
            side_effect=RuntimeError("broken"),
        ):
            result = tool._try_get_cache()
        assert result is None

    def test_get_call_graph_uses_cache_if_available(self):
        """_get_call_graph uses CachedCallGraph when _try_get_cache returns a cache."""
        tmpdir = _make_project(("f.py", "x=1\n"))
        tool = CodeGraphPRReviewTool(tmpdir)
        mock_cache = MagicMock()
        with patch.object(tool, "_try_get_cache", return_value=mock_cache):
            cg = tool._get_call_graph()
        from tree_sitter_analyzer.call_graph import CachedCallGraph

        assert isinstance(cg, CachedCallGraph)

    def test_execute_skips_file_with_no_old_new_src(self):
        """Files with no old + new source are counted as skipped (both empty)."""
        diff_text = (
            "diff --git a/empty.py b/empty.py\n"
            "--- a/empty.py\n"
            "+++ b/empty.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )
        tmpdir = _make_project(("empty.py", "x=1\n"))
        tool = CodeGraphPRReviewTool(tmpdir)
        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool._get_local_diff",
                return_value=diff_text,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool._get_old_source",
                return_value="",
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool._get_new_source",
                return_value="",
            ),
        ):
            result = _run(
                tool,
                {"mode": "diff", "include_call_graph": False, "output_format": "json"},
            )
        assert result["success"] is True
        assert result["files_skipped"] == 1

    def test_execute_api_change_detection(self):
        """API changes are captured in api_changes field."""
        from unittest.mock import MagicMock

        src_old = "def my_api_func(x):\n    pass\n"
        src_new = "def my_api_func(x, y):\n    pass\n"
        diff_text = (
            "diff --git a/api.py b/api.py\n"
            "--- a/api.py\n"
            "+++ b/api.py\n"
            "@@ -1 +1 @@\n"
            "-def my_api_func(x):\n"
            "+def my_api_func(x, y):\n"
        )
        tmpdir = _make_project(("api.py", src_new))
        tool = CodeGraphPRReviewTool(tmpdir)

        # Mock classifier to return an api_change classification
        mock_hunk = MagicMock()
        mock_hunk.category.value = "api_change"
        mock_hunk.reason = "signature changed"
        mock_hunk.to_dict.return_value = {"category": "api_change", "risk": "high"}

        mock_result = MagicMock()
        mock_result.classifications = [mock_hunk]
        mock_result.dominant_category.value = "api_change"
        mock_result.risk_level = "high"
        mock_result.change_summary = "API signature changed"
        mock_result.category_counts = {"api_change": 1}

        mock_diff_result = MagicMock()
        mock_diff_result.hunks = []

        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool._get_local_diff",
                return_value=diff_text,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool._get_old_source",
                return_value=src_old,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool._get_new_source",
                return_value=src_new,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool.ASTDiffer.diff_strings",
                return_value=mock_diff_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool.SemanticChangeClassifier.classify",
                return_value=mock_result,
            ),
        ):
            result = _run(
                tool,
                {"mode": "diff", "include_call_graph": False, "output_format": "json"},
            )
        assert result["success"] is True
        assert len(result["api_changes"]) == 1  # fixture yields exactly one

    def test_high_risk_changes_hunks_are_lean_no_ast_children(self):
        """BUG A (Codex P2 #696 follow-up): high_risk_changes entries must NOT
        contain AST children keys in hunk.old / hunk.new.

        codegraph_pr_review calls ch.to_dict() with no args; the default must
        be lean (include_children=False).  Before the fix, ClassifiedHunk.to_dict()
        hard-coded include_children=True, embedding full subtrees for up to 5
        hunks/file.
        """
        # Use a real api_change-triggering diff so SemanticChangeClassifier
        # produces an actual ClassifiedHunk with a real ASTDiffHunk.
        src_old = "def public_api(x: int) -> int:\n    return x\n"
        src_new = "def public_api(x: int, y: int = 0) -> int:\n    return x + y\n"
        diff_text = (
            "diff --git a/api.py b/api.py\n"
            "--- a/api.py\n"
            "+++ b/api.py\n"
            "@@ -1,2 +1,2 @@\n"
            "-def public_api(x: int) -> int:\n"
            "+def public_api(x: int, y: int = 0) -> int:\n"
            "     return x\n"
        )
        tmpdir = _make_project(("api.py", src_new))
        tool = CodeGraphPRReviewTool(tmpdir)

        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool._get_local_diff",
                return_value=diff_text,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool._get_old_source",
                return_value=src_old,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool._get_new_source",
                return_value=src_new,
            ),
        ):
            result = _run(
                tool,
                {"mode": "diff", "include_call_graph": False, "output_format": "json"},
            )
        assert result["success"] is True
        file_reviews = result.get("file_reviews", [])
        assert len(file_reviews) == 1
        high_risk_changes = file_reviews[0].get("high_risk_changes", [])
        # Verify lean serialization: no hunk.old/new children in any high_risk entry.
        for i, entry in enumerate(high_risk_changes):
            hunk = entry.get("hunk", {})
            assert "children" not in hunk.get("old", {}), (
                f"high_risk_changes[{i}].hunk.old must NOT contain 'children' "
                "(lean default — PR review must not embed full AST subtrees)"
            )
            assert "children" not in hunk.get("new", {}), (
                f"high_risk_changes[{i}].hunk.new must NOT contain 'children' "
                "(lean default — PR review must not embed full AST subtrees)"
            )

    def test_analyze_call_graph_impact_dedup_callee(self):
        """Duplicate callee entries (same qualified_name) are deduplicated."""
        from tree_sitter_analyzer.call_graph import FunctionRef

        tmpdir = _make_project(("f.py", "x=1\n"))
        tool = CodeGraphPRReviewTool(tmpdir)

        anchor_ref = FunctionRef(
            file_path="f.py", name="special_fn", start_line=1, language="python"
        )
        callee = FunctionRef(
            file_path="helper.py", name="helper_unique", start_line=3, language="python"
        )
        mock_graph = MagicMock()
        mock_graph.build = MagicMock()
        mock_graph.function_refs = MagicMock(return_value=[anchor_ref])
        mock_graph._func_by_file = {"f.py": [anchor_ref]}
        mock_graph.caller_refs_of = MagicMock(return_value=[])
        # Return same callee twice to exercise callee dedup path
        mock_graph.callee_refs_of = MagicMock(return_value=[callee, callee])
        with patch.object(tool, "_get_call_graph", return_value=mock_graph):
            result = tool._analyze_call_graph_impact(["f.py"])
        # Deduplicated: only 1 downstream entry
        assert len(result["affected_functions"]) == 1
        assert result["affected_functions"][0]["direction"] == "downstream"

    def test_analyze_call_graph_impact_ambiguous_anchor_dropped(self):
        """Anchor with ambiguous name (count >= threshold) → callers go to ambiguous_dropped."""
        from tree_sitter_analyzer.call_graph import FunctionRef

        tmpdir = _make_project(("f.py", "x=1\n"))
        tool = CodeGraphPRReviewTool(tmpdir)

        # anchor_ref has a "generic" name that will appear in many files
        anchor_ref = FunctionRef(
            file_path="f.py", name="get_node_text", start_line=1, language="python"
        )
        # A would-be caller that should be skipped (anchor is generic)
        caller = FunctionRef(
            file_path="caller.py", name="some_call", start_line=5, language="python"
        )
        # 3 other refs for get_node_text from different files → count=4 in name_file_count
        other_ref_1 = FunctionRef(
            file_path="plugin_a.py",
            name="get_node_text",
            start_line=1,
            language="python",
        )
        other_ref_2 = FunctionRef(
            file_path="plugin_b.py",
            name="get_node_text",
            start_line=1,
            language="python",
        )
        other_ref_3 = FunctionRef(
            file_path="plugin_c.py",
            name="get_node_text",
            start_line=1,
            language="python",
        )
        mock_graph = MagicMock()
        mock_graph.build = MagicMock()
        # "get_node_text" appears in 4 distinct files → name_file_count["get_node_text"]=4
        mock_graph.function_refs = MagicMock(
            return_value=[anchor_ref, other_ref_1, other_ref_2, other_ref_3]
        )
        mock_graph._func_by_file = {"f.py": [anchor_ref]}
        mock_graph.caller_refs_of = MagicMock(return_value=[caller])
        mock_graph.callee_refs_of = MagicMock(return_value=[])
        with patch.object(tool, "_get_call_graph", return_value=mock_graph):
            result = tool._analyze_call_graph_impact(["f.py"])
        # anchor is ambiguous (in KNOWN_GENERIC_CALLBACK_NAMES or count>=threshold)
        # so all callers are dropped into ambiguous_anchor_dropped
        assert result["affected_functions"] == []
        assert result["stats"]["ambiguous_name_edges_dropped"] == 1

    def test_analyze_call_graph_impact_unknown_lang_file(self):
        """Changed file with unknown extension → empty changed_langs → lang gate skips."""
        from tree_sitter_analyzer.call_graph import FunctionRef

        tmpdir = _make_project(("f.unkn", "x=1\n"))
        tool = CodeGraphPRReviewTool(tmpdir)

        anchor_ref = FunctionRef(
            file_path="f.unkn", name="unique_fn_xyz", start_line=1, language="python"
        )
        caller = FunctionRef(
            file_path="caller.py", name="call_it", start_line=1, language="python"
        )
        mock_graph = MagicMock()
        mock_graph.build = MagicMock()
        mock_graph.function_refs = MagicMock(return_value=[anchor_ref])
        mock_graph._func_by_file = {"f.unkn": [anchor_ref]}
        mock_graph.caller_refs_of = MagicMock(return_value=[caller])
        mock_graph.callee_refs_of = MagicMock(return_value=[])
        with patch.object(tool, "_get_call_graph", return_value=mock_graph):
            result = tool._analyze_call_graph_impact(["f.unkn"])
        # No lang gate (unknown lang) → caller passes through
        assert len(result["affected_functions"]) == 1

    def test_execute_pr_url_in_response(self):
        """When pr_url is provided via gh path (mocked), it appears in the response."""
        diff_text = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n"
        tmpdir = _make_project(("x.py", "x=1\n"))
        tool = CodeGraphPRReviewTool(tmpdir)
        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool.check_gh_available",
                return_value=True,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool.fetch_pr_diff",
                return_value=diff_text,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool.parse_pr_url",
                return_value=("owner", "repo", 42),
            ),
        ):
            result = _run(
                tool,
                {
                    "mode": "pr",
                    "pr_url": "https://github.com/owner/repo/pull/42",
                    "include_call_graph": False,
                    "output_format": "json",
                },
            )
        assert result.get("pr_url") == "https://github.com/owner/repo/pull/42"
