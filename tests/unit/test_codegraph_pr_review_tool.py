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
    _filter_affected_by_language,
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
        assert result["files_reviewed"] >= 1
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
