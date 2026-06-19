"""Counts-consistency invariant tests for health action=dead (issue #448).

Contract:
  - listed == min(total, cap)   for each category
  - candidates <= total         (labeled_stats relationship)
  - truncated == (any category exceeds its cap)
  - next_step narrative uses the same counts as the structured fields
  - No third hidden number (no raw stats["dead_functions"] bleeding through)

Tests use a synthetic DeadCodeResult fixture injected via monkeypatch so
results are deterministic and independent of live analysis.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import tree_sitter_analyzer.mcp.tools.dead_code_tool as mod
from tree_sitter_analyzer.call_graph import FunctionRef
from tree_sitter_analyzer.dead_code_analyzer import (
    DeadCodeResult,
    DeadFunction,
    UnreferencedVariable,
    UnusedImport,
)
from tree_sitter_analyzer.mcp.tools.dead_code_tool import CodeGraphDeadCodeTool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_func_ref(name: str, file: str = "a.py", line: int = 1) -> FunctionRef:
    """Create a minimal FunctionRef (no tree-sitter node needed for serialization)."""
    return FunctionRef(
        file_path=file,
        name=name,
        start_line=line,
        end_line=line + 3,
        language="python",
    )


def _make_dead(name: str, file: str = "a.py", line: int = 1) -> DeadFunction:
    return DeadFunction(
        function=_make_func_ref(name, file, line),
        reason="orphan_no_callers_no_callees",
        dead_callees=[],
    )


def _make_import(name: str, file: str = "a.py") -> UnusedImport:
    return UnusedImport(
        file=file, line=1, import_text=f"import {name}", unused_names=[name]
    )


def _make_var(name: str, file: str = "a.py") -> UnreferencedVariable:
    return UnreferencedVariable(file=file, name=name, line=1, language="python")


def _fake_result(
    n_dead: int = 0,
    n_imports: int = 0,
    n_vars: int = 0,
) -> DeadCodeResult:
    return DeadCodeResult(
        dead_functions=[_make_dead(f"dead_{i}") for i in range(n_dead)],
        unused_imports=[_make_import(f"mod_{i}") for i in range(n_imports)],
        unreferenced_variables=[_make_var(f"var_{i}") for i in range(n_vars)],
        stats={
            "total_functions": n_dead,
            "dead_functions": n_dead,
            "unused_imports": n_imports,
            "unreferenced_variables": n_vars,
            "total_call_edges": 0,
        },
    )


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixture: tmp project dir that the tool can accept as project_root
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_root(tmp_path):
    (tmp_path / "placeholder.py").write_text("x = 1\n")
    return str(tmp_path)


# ---------------------------------------------------------------------------
# Core invariant tests
# ---------------------------------------------------------------------------


class TestDeadCodeCountsConsistency:
    """Invariant: every count in the response must label what it counts,
    listed == min(total, cap), and truncated is set honestly."""

    def test_no_truncation_listed_equals_total(self, fake_root, monkeypatch):
        """When total < cap, listed == total and truncated is False."""
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _fake_result(5, 3, 2)
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = _run(
            tool.execute(
                {
                    "output_format": "json",
                    "max_dead": 50,
                    "max_imports": 50,
                    "max_variables": 50,
                }
            )
        )

        stats = result["stats"]
        assert result["truncated"] is False
        assert stats["dead_functions_listed"] == 5
        assert stats["unused_imports_listed"] == 3
        assert stats["unreferenced_variables_listed"] == 2

    def test_truncated_flag_set_when_dead_exceeds_cap(self, fake_root, monkeypatch):
        """listed == cap when total > cap, truncated is True."""
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _fake_result(n_dead=20)
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = _run(tool.execute({"output_format": "json", "max_dead": 5}))

        stats = result["stats"]
        assert result["truncated"] is True
        assert stats["dead_functions_listed"] == 5
        assert stats["total_dead_functions_transitive"] == 20
        # listed == min(total, cap)
        assert stats["dead_functions_listed"] == min(
            stats["total_dead_functions_transitive"], stats["dead_functions_cap"]
        )

    def test_truncated_flag_set_when_imports_exceeds_cap(self, fake_root, monkeypatch):
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _fake_result(n_imports=15)
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = _run(tool.execute({"output_format": "json", "max_imports": 3}))

        stats = result["stats"]
        assert result["truncated"] is True
        assert stats["unused_imports_listed"] == 3
        assert stats["total_unused_imports"] == 15
        assert stats["unused_imports_listed"] == min(
            stats["total_unused_imports"], stats["unused_imports_cap"]
        )

    def test_truncated_flag_set_when_vars_exceed_cap(self, fake_root, monkeypatch):
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _fake_result(n_vars=10)
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = _run(tool.execute({"output_format": "json", "max_variables": 4}))

        stats = result["stats"]
        assert result["truncated"] is True
        assert stats["unreferenced_variables_listed"] == 4
        assert stats["total_unreferenced_variables"] == 10
        assert stats["unreferenced_variables_listed"] == min(
            stats["total_unreferenced_variables"], stats["unreferenced_variables_cap"]
        )

    def test_no_hidden_third_number_in_response(self, fake_root, monkeypatch):
        """The old stats["dead_functions"] raw total must NOT appear in the tool
        response (it was the "1379" that contradicted "80" and "50")."""
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _fake_result(100, 10, 5)
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = _run(tool.execute({"output_format": "json", "max_dead": 10}))

        stats = result["stats"]
        # The old unlabeled "dead_functions" key must not exist
        assert "dead_functions" not in stats, (
            "stats['dead_functions'] is the old unlabeled raw total that caused #448; "
            "it must not appear — use total_dead_functions_transitive instead"
        )

    def test_narrative_uses_same_count_as_listed_total(self, fake_root, monkeypatch):
        """next_step must cite the same count as listed_total, not a third number."""
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _fake_result(3, 2, 1)
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = _run(tool.execute({"output_format": "json"}))

        stats = result["stats"]
        listed_total = (
            stats["dead_functions_listed"]
            + stats["unused_imports_listed"]
            + stats["unreferenced_variables_listed"]
        )
        # 6 total issues; next_step should mention "6 candidate"
        assert str(listed_total) in result["next_step"], (
            f"next_step '{result['next_step']}' does not contain listed_total={listed_total}"
        )

    def test_truncated_next_step_mentions_totals(self, fake_root, monkeypatch):
        """When truncated, next_step must cite both the listed and total counts."""
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _fake_result(n_dead=100)
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = _run(tool.execute({"output_format": "json", "max_dead": 10}))

        assert result["truncated"] is True
        # next_step must name both the listed count (10) and total (100)
        next_step = result["next_step"]
        assert "10" in next_step, f"listed count 10 missing from next_step: {next_step}"
        assert "100" in next_step, (
            f"total count 100 missing from next_step: {next_step}"
        )
        assert "max_dead" in next_step, (
            f"guidance on raising cap missing from next_step: {next_step}"
        )

    def test_candidates_lte_total(self, fake_root, monkeypatch):
        """candidates_after_filters <= total_dead_functions_transitive (they're equal here;
        test documents the relationship)."""
        monkeypatch.setattr(mod, "analyze_dead_code", lambda *a, **k: _fake_result(7))
        tool = CodeGraphDeadCodeTool(fake_root)
        result = _run(tool.execute({"output_format": "json"}))

        stats = result["stats"]
        assert (
            stats["candidates_after_filters"]
            == stats["total_dead_functions_transitive"]
        )

    def test_empty_result_truncated_false(self, fake_root, monkeypatch):
        """A clean result must report truncated=False and zero listed counts."""
        monkeypatch.setattr(mod, "analyze_dead_code", lambda *a, **k: _fake_result())
        tool = CodeGraphDeadCodeTool(fake_root)
        result = _run(tool.execute({"output_format": "json"}))

        assert result["truncated"] is False
        stats = result["stats"]
        assert stats["dead_functions_listed"] == 0
        assert stats["unused_imports_listed"] == 0
        assert stats["unreferenced_variables_listed"] == 0

    def test_listed_equals_min_total_cap_parametric(self, fake_root, monkeypatch):
        """Parametric: for several (total, cap) combos, listed == min(total, cap)."""
        cases = [(0, 50), (30, 50), (50, 50), (51, 50), (200, 10)]
        for total, cap in cases:
            monkeypatch.setattr(
                mod,
                "analyze_dead_code",
                lambda *a, _n=total, **k: _fake_result(n_dead=_n),
            )
            tool = CodeGraphDeadCodeTool(fake_root)
            result = _run(tool.execute({"output_format": "json", "max_dead": cap}))
            stats = result["stats"]
            expected_listed = min(total, cap)
            assert stats["dead_functions_listed"] == expected_listed, (
                f"total={total}, cap={cap}: expected listed={expected_listed}, "
                f"got {stats['dead_functions_listed']}"
            )
            assert result["truncated"] is (total > cap), (
                f"total={total}, cap={cap}: expected truncated={total > cap}"
            )


class TestDeadCodeToolEdgeCases:
    """Coverage for error paths and mode-filter branches."""

    def test_no_project_root_returns_error(self):
        """Tool with no project_root must return success=False, not raise."""
        tool = CodeGraphDeadCodeTool(None)
        result = asyncio.run(tool.execute({"output_format": "json"}))
        assert result["success"] is False
        assert "project root" in result["error"].lower()

    def test_invalid_mode_raises_value_error(self, fake_root):
        """validate_arguments must raise ValueError for unknown mode."""
        tool = CodeGraphDeadCodeTool(fake_root)
        with pytest.raises(ValueError, match="Invalid mode.*Valid values"):
            tool.validate_arguments({"mode": "bogus"})

    def test_invalid_mode_enumerates_valid_values(self, fake_root):
        """Error message must list all valid mode values (issue #449)."""
        tool = CodeGraphDeadCodeTool(fake_root)
        try:
            tool.validate_arguments({"mode": "invalid_mode"})
            assert False, "Should have raised ValueError"
        except ValueError as exc:
            error_msg = str(exc)
            # Check that the error message includes the enumeration
            assert "all" in error_msg
            assert "dead_functions" in error_msg
            assert "unused_imports" in error_msg
            assert "variables" in error_msg
            assert "invalid_mode" in error_msg
            # Verify the message structure (issue #449 compliance)
            assert "Valid values:" in error_msg

    def test_analyze_dead_code_exception_returns_error(self, fake_root, monkeypatch):
        """If analyze_dead_code raises, tool must return success=False."""
        import tree_sitter_analyzer.mcp.tools.dead_code_tool as mod2

        monkeypatch.setattr(
            mod2,
            "analyze_dead_code",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = asyncio.run(tool.execute({"output_format": "json"}))
        assert result["success"] is False
        assert "boom" in result["error"]

    def test_mode_dead_functions_omits_imports_and_vars(self, fake_root, monkeypatch):
        """mode=dead_functions must drop unused_imports and unreferenced_variables."""
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _fake_result(2, 3, 1)
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = asyncio.run(
            tool.execute({"output_format": "json", "mode": "dead_functions"})
        )
        assert result["success"] is True
        assert "dead_functions" in result
        assert "unused_imports" not in result
        assert "unreferenced_variables" not in result

    def test_mode_unused_imports_omits_dead_and_vars(self, fake_root, monkeypatch):
        """mode=unused_imports must drop dead_functions and unreferenced_variables."""
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _fake_result(2, 3, 1)
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = asyncio.run(
            tool.execute({"output_format": "json", "mode": "unused_imports"})
        )
        assert result["success"] is True
        assert "unused_imports" in result
        assert "dead_functions" not in result
        assert "unreferenced_variables" not in result

    def test_mode_variables_omits_dead_and_imports(self, fake_root, monkeypatch):
        """mode=variables must drop dead_functions and unused_imports."""
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _fake_result(2, 3, 1)
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = asyncio.run(
            tool.execute({"output_format": "json", "mode": "variables"})
        )
        assert result["success"] is True
        assert "unreferenced_variables" in result
        assert "dead_functions" not in result
        assert "unused_imports" not in result


def _mixed_path_result() -> DeadCodeResult:
    """Dead items spread across product / corpus / benchmarks paths (#1084)."""
    return DeadCodeResult(
        dead_functions=[
            _make_dead("prod_a", "tree_sitter_analyzer/mcp/x.py"),
            _make_dead("prod_b", "tree_sitter_analyzer/mcp/sub/y.py"),
            _make_dead("corpus_c", "corpus/python/z.py"),
            _make_dead("bench_d", "benchmarks/agent-tasks/scenarios.py"),
            _make_dead("root_e", "analyze_coverage_json.py"),
        ],
        unused_imports=[
            _make_import("prod_imp", "tree_sitter_analyzer/mcp/x.py"),
            _make_import("corpus_imp", "corpus/python/z.py"),
        ],
        unreferenced_variables=[
            _make_var("prod_var", "tree_sitter_analyzer/mcp/x.py"),
            _make_var("corpus_var", "corpus/python/z.py"),
        ],
        stats={
            "total_functions": 5,
            "dead_functions": 5,
            "unused_imports": 2,
            "unreferenced_variables": 2,
            "total_call_edges": 0,
        },
    )


class TestDeadCodePathScoping:
    """#1084: ``path`` scopes results to items defined under a path prefix
    (the ``next_step`` 'filter by path' guidance must become real)."""

    def test_no_path_returns_everything(self, fake_root, monkeypatch):
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _mixed_path_result()
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = _run(tool.execute({"output_format": "json"}))
        assert result["stats"]["total_dead_functions_transitive"] == 5
        assert result["stats"]["total_unused_imports"] == 2
        assert result["stats"]["total_unreferenced_variables"] == 2

    def test_path_scopes_to_product_package(self, fake_root, monkeypatch):
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _mixed_path_result()
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = _run(
            tool.execute({"output_format": "json", "path": "tree_sitter_analyzer/mcp"})
        )
        stats = result["stats"]
        # 2 dead funcs + 1 import + 1 var live under tree_sitter_analyzer/mcp
        assert stats["total_dead_functions_transitive"] == 2
        assert stats["total_unused_imports"] == 1
        assert stats["total_unreferenced_variables"] == 1
        files = {df["file"] for df in result["dead_functions"]}
        assert files == {
            "tree_sitter_analyzer/mcp/x.py",
            "tree_sitter_analyzer/mcp/sub/y.py",
        }

    def test_path_excludes_corpus_and_benchmarks(self, fake_root, monkeypatch):
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _mixed_path_result()
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = _run(
            tool.execute({"output_format": "json", "path": "tree_sitter_analyzer/mcp"})
        )
        files = {df["file"] for df in result["dead_functions"]}
        assert not any(
            f.startswith("corpus/") or f.startswith("benchmarks/") for f in files
        )

    def test_path_matches_single_subtree(self, fake_root, monkeypatch):
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _mixed_path_result()
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = _run(tool.execute({"output_format": "json", "path": "corpus"}))
        assert result["stats"]["total_dead_functions_transitive"] == 1
        assert result["dead_functions"][0]["file"] == "corpus/python/z.py"

    def test_path_trailing_slash_normalized(self, fake_root, monkeypatch):
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _mixed_path_result()
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = _run(
            tool.execute({"output_format": "json", "path": "tree_sitter_analyzer/mcp/"})
        )
        assert result["stats"]["total_dead_functions_transitive"] == 2

    def test_path_respects_segment_boundary(self, fake_root, monkeypatch):
        """A partial segment ('.../m') must NOT match '.../mcp/...' — the
        filter is path-segment aware, not a raw string prefix."""
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _mixed_path_result()
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = _run(
            tool.execute({"output_format": "json", "path": "tree_sitter_analyzer/m"})
        )
        assert result["stats"]["total_dead_functions_transitive"] == 0

    def test_path_dot_means_whole_project(self, fake_root, monkeypatch):
        """Codex P2: ``path='.'`` is the root scope — must match everything,
        not reject every project-relative file."""
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _mixed_path_result()
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = _run(tool.execute({"output_format": "json", "path": "."}))
        assert result["stats"]["total_dead_functions_transitive"] == 5

    def test_path_leading_dot_slash_normalized(self, fake_root, monkeypatch):
        """Codex P2: a copy-pasted ``./pkg`` prefix must behave like ``pkg``."""
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _mixed_path_result()
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = _run(
            tool.execute(
                {"output_format": "json", "path": "./tree_sitter_analyzer/mcp"}
            )
        )
        assert result["stats"]["total_dead_functions_transitive"] == 2

    def test_path_no_match_is_empty_not_error(self, fake_root, monkeypatch):
        monkeypatch.setattr(
            mod, "analyze_dead_code", lambda *a, **k: _mixed_path_result()
        )
        tool = CodeGraphDeadCodeTool(fake_root)
        result = _run(
            tool.execute({"output_format": "json", "path": "nonexistent/dir"})
        )
        assert result["success"] is True
        assert result["stats"]["total_dead_functions_transitive"] == 0
        assert result["verdict"] == "INFO"


def test_scoped_mode_ignores_hidden_category_truncation(tmp_path) -> None:
    """Codex P2 (#486): mode=unused_imports strips dead_functions from the
    response — the truncated flag must NOT fire for the hidden dead-function
    cap when the visible categories are uncapped."""
    import asyncio
    from unittest.mock import patch

    from tree_sitter_analyzer.mcp.tools.dead_code_tool import CodeGraphDeadCodeTool

    tool = CodeGraphDeadCodeTool(str(tmp_path))
    fake = _fake_result(n_dead=20, n_imports=1, n_vars=0)
    with patch(
        "tree_sitter_analyzer.mcp.tools.dead_code_tool.analyze_dead_code",
        return_value=fake,
    ):
        result = asyncio.run(
            tool.execute(
                {
                    "mode": "unused_imports",
                    "max_dead": 5,
                    "output_format": "json",
                }
            )
        )
    # 20 dead functions exceed cap 5, but they are hidden in this mode.
    assert result["truncated"] is False
    assert "dead_functions" not in result
