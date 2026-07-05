"""Tests for codegraph_query_tool relation steps, sort, build, and facet helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools._codegraph_query_dsl import _ChainStep
from tree_sitter_analyzer.mcp.tools.codegraph_query_tool import (
    _absolute_path,
    _affected_tests_facet,
    _build_file_entries,
    _compact_facets,
    _complexity_facet,
    _dedupe_symbols,
    _drop_test_shadow_symbols,
    _health_facet,
    _include_facets,
    _is_relation_noise_symbol,
    _QueryState,
    _relation_step,
    _risk_facet,
    _sort_state,
    _source_preference_key,
)


class TestCodeGraphQueryInternalsFacets:
    def test_relation_step_skips_symbols_without_names_and_empty_rows(self):
        mock_cache = MagicMock()
        mock_cache.query_callers.return_value = [
            {"caller_name": "", "caller_file": "ignored.py", "caller_line": 1},
            {
                "caller_name": "entry",
                "caller_file": "entry.py",
                "caller_line": 10,
                "depth": 2,
            },
        ]
        state = _QueryState()
        state.current = [
            {"file": "ignored.py", "line": 1},
            {"name": "run", "file": "main.py", "line": 2},
        ]

        related = _relation_step(
            mock_cache,
            state,
            direction="callers",
            step=_ChainStep("callers", [], {"depth": "bad", "limit": 2}),
        )

        assert [symbol["name"] for symbol in related] == ["entry"]
        mock_cache.query_callers.assert_called_once_with("run", "main.py", max_depth=1)
        assert state.relationships["callers"]["main.py:2:run"][0]["name"] == "entry"

    def test_relation_step_sorts_source_edges_before_tests_then_limits(self):
        mock_cache = MagicMock()
        mock_cache.query_callees.return_value = [
            {
                "callee_name": "ServeHTTP",
                "callee_file": "utils_test.go",
                "callee_line": 33,
                "depth": 1,
            },
            {
                "callee_name": "ServeHTTP",
                "callee_file": "gin.go",
                "callee_line": 623,
                "depth": 1,
            },
        ]
        state = _QueryState()
        state.current = [{"name": "dispatch", "file": "gin.go", "line": 600}]

        related = _relation_step(
            mock_cache,
            state,
            direction="callees",
            step=_ChainStep("callees", [], {"limit": 1}),
        )

        assert [symbol["file"] for symbol in related] == ["gin.go"]
        assert state.relationships["callees"]["gin.go:600:dispatch"][0]["line"] == 623

    def test_relation_step_filters_builtin_runtime_noise_before_limits(self):
        mock_cache = MagicMock()
        mock_cache.query_callees.return_value = [
            {
                "callee_name": "len",
                "callee_file": "gin.go",
                "callee_line": 698,
                "depth": 1,
            },
            {
                "callee_name": "make",
                "callee_file": "gin.go",
                "callee_line": 741,
                "depth": 1,
            },
            {
                "callee_name": "getValue",
                "callee_file": "tree.go",
                "callee_line": 418,
                "depth": 1,
            },
        ]
        state = _QueryState()
        state.current = [{"name": "handleHTTPRequest", "file": "gin.go", "line": 690}]

        related = _relation_step(
            mock_cache,
            state,
            direction="callees",
            step=_ChainStep("callees", [], {"limit": 2}),
        )

        assert [symbol["name"] for symbol in related] == ["getValue"]
        assert state.relationships["callees"]["gin.go:690:handleHTTPRequest"] == [
            {
                "name": "getValue",
                "kind": "function",
                "file": "tree.go",
                "line": 418,
                "end_line": 418,
                "language": "",
                "depth": 1,
            }
        ]

    def test_relation_noise_symbol_identifies_runtime_helpers(self):
        assert _is_relation_noise_symbol({"name": "len"})
        assert _is_relation_noise_symbol({"name": "super().__init__"})
        assert not _is_relation_noise_symbol({"name": "getValue"})

    def test_source_preference_key_identifies_test_fixture_and_generated_paths(self):
        source = {"file": "gin.go", "line": 2, "name": "run"}
        test = {"file": "tests/fixtures/gin_test.go", "line": 1, "name": "run"}
        generated = {"file": "src/generated/gin.go", "line": 1, "name": "run"}

        assert _source_preference_key(source) < _source_preference_key(test)
        assert _source_preference_key(source) < _source_preference_key(generated)
        assert _drop_test_shadow_symbols([test, source]) == [source]
        assert _drop_test_shadow_symbols([test]) == [test]

    def test_sort_state_supports_path_alias_fan_out_and_rejects_unknown_fields(self):
        state = _QueryState()
        state.current = [
            {"file": "b.py", "line": 2, "name": "b"},
            {"file": "a.py", "line": 1, "name": "a"},
        ]
        state.symbols = list(state.current)
        state.relationships["callees"] = {"a.py:1:a": [{}, {}], "b.py:2:b": [{}]}

        _sort_state(state, _ChainStep("sort", [], {"by": "path"}))
        assert [symbol["file"] for symbol in state.current] == ["a.py", "b.py"]

        _sort_state(state, _ChainStep("sort", [], {"by": "fan_out", "desc": True}))
        assert [symbol["name"] for symbol in state.current] == ["a", "b"]

        with pytest.raises(ValueError, match="unsupported field"):
            _sort_state(state, _ChainStep("sort", [], {"by": "unknown"}))

    def test_sort_state_by_confidence_desc(self):
        state = _QueryState()
        state.current = [
            {"file": "low.py", "line": 1, "name": "low", "confidence": 0.3},
            {"file": "high.py", "line": 1, "name": "high", "confidence": 0.95},
            {"file": "none.py", "line": 1, "name": "none"},
        ]
        state.symbols = list(state.current)

        _sort_state(state, _ChainStep("sort", [], {"by": "confidence", "desc": True}))

        names = [s["name"] for s in state.current]
        assert names[0] == "high"
        assert names[-1] == "none"

    def test_build_file_entries_includes_truncated_excerpt_for_long_symbols(
        self, tmp_path
    ):
        source = tmp_path / "main.py"
        source.write_text(
            "\n".join(f"line_{idx}" for idx in range(1, 201)) + "\n",
            encoding="utf-8",
        )

        entries = _build_file_entries(
            project_root=str(tmp_path),
            symbols=[
                {"name": "nameless", "file": "", "line": 1, "end_line": 1},
                {
                    "name": "run",
                    "kind": "function",
                    "file": "main.py",
                    "line": 1,
                    "end_line": 200,
                    "language": "python",
                },
            ],
            max_files=3,
            include_code=True,
        )

        assert entries == [
            {
                "file_path": "main.py",
                "language": "python",
                "symbols": [
                    {
                        "name": "run",
                        "kind": "function",
                        "start_line": 1,
                        "end_line": 200,
                        "code": "\n".join(f"line_{idx}" for idx in range(1, 25)) + "\n",
                        "code_truncated": True,
                        "code_lines": "1-24 of 200",
                    }
                ],
            }
        ]

    def test_include_facets_collects_quality_health_tests_and_risk(self, tmp_path):
        source = tmp_path / "main.py"
        source.write_text("def run():\n    return 1\n", encoding="utf-8")
        mock_cache = MagicMock()
        mock_cache.query_callers.return_value = [
            {"caller_name": f"caller_{i}", "caller_file": f"c{i}.py", "caller_line": i}
            for i in range(10)
        ]
        mock_cache.query_callees.return_value = [
            {"callee_name": "helper", "callee_file": "helper.py", "callee_line": 7}
        ]
        state = _QueryState()
        state.current = [
            {"file": "main.py", "line": 1, "name": "run", "kind": "function"},
            {
                "file": "tests/test_main.py",
                "line": 3,
                "name": "test_run",
                "kind": "function",
            },
        ]
        state.symbols = list(state.current)

        complexity_row = MagicMock(name="run", line=1, complexity=22)
        health_score = MagicMock(total=51, grade="D", dimensions={"complexity": 20})
        with (
            patch(
                "tree_sitter_analyzer.complexity_heatmap."
                "analyze_file_complexity_from_cache",
                return_value=[complexity_row],
            ),
            patch("tree_sitter_analyzer.health_scorer.HealthScorer") as scorer_cls,
        ):
            scorer_cls.return_value.score_file.return_value = health_score
            _include_facets(
                cache=mock_cache,
                project_root=str(tmp_path),
                state=state,
                step=_ChainStep(
                    "include",
                    [],
                    {
                        "source": True,
                        "callers": True,
                        "callees": True,
                        "complexity": True,
                        "health": True,
                        "affected_tests": True,
                        "risk": True,
                        "include_code": False,
                    },
                ),
                default_max_symbols=10,
                default_max_files=5,
                default_include_code=True,
            )

        assert set(state.facets) == {
            "source",
            "callers",
            "callees",
            "complexity",
            "health",
            "affected_tests",
            "risk",
        }
        assert state.facets["complexity"]["files"][0]["max_complexity"] == 22
        assert state.facets["health"]["files"][0]["grade"] == "D"
        assert state.facets["affected_tests"]["files"] == ["tests/test_main.py"]
        assert state.facets["risk"]["level"] == "review"

    def test_compact_facets_trim_source_relationship_and_quality_shapes(self):
        facets = {
            "source": {
                "status": "included",
                "file_count": 1,
                "files": [
                    {
                        "file_path": "main.py",
                        "language": "python",
                        "symbols": [
                            {
                                "name": "run",
                                "kind": "function",
                                "start_line": 1,
                                "end_line": 2,
                                "code": "def run():\n    pass\n",
                                "code_truncated": True,
                                "code_lines": "1-2 of 8",
                            }
                        ],
                    }
                ],
            },
            "callees": {
                "status": "included",
                "edges": {
                    "main.py:1:run": [
                        {
                            "name": "helper",
                            "kind": "function",
                            "file": "main.py",
                            "line": 4,
                            "end_line": 4,
                            "language": "",
                            "depth": 1,
                        }
                    ]
                },
            },
            "complexity": {
                "status": "included",
                "files": [
                    {
                        "file": "main.py",
                        "status": "included",
                        "max_complexity": 12,
                        "total_complexity": 20,
                        "hotspots": [{"name": "run", "line": 1, "complexity": 12}],
                    }
                ],
            },
            "health": {
                "status": "included",
                "files": [
                    {
                        "file": "main.py",
                        "status": "included",
                        "total": 82,
                        "grade": "B",
                        "dimensions": {"complexity": 80},
                    }
                ],
            },
            "risk": {"status": "included", "level": "info", "reasons": []},
        }

        compact = _compact_facets(facets)

        assert compact["source"]["files"][0]["file"] == "main.py"
        assert compact["source"]["files"][0]["symbols"][0]["lines"] == "1-2"
        assert compact["source"]["files"][0]["symbols"][0]["code_truncated"] is True
        assert compact["source"]["files"][0]["symbols"][0]["code_lines"] == "1-2 of 8"
        assert compact["callees"]["edges"]["main.py:1:run"] == [
            {
                "name": "helper",
                "file": "main.py",
                "line": 4,
                "kind": "function",
                "depth": 1,
            }
        ]
        assert compact["complexity"]["files"][0]["hotspots"][0]["cc"] == 12
        assert "dimensions" not in compact["health"]["files"][0]
        assert compact["risk"] == {"status": "included", "level": "info", "reasons": []}

    def test_quality_facets_cover_empty_error_and_missing_paths(self, tmp_path):
        symbols = [{"file": "main.py", "line": 1, "name": "run"}]

        with patch.dict(
            "sys.modules", {"tree_sitter_analyzer.complexity_heatmap": None}
        ):
            assert (
                _complexity_facet(MagicMock(), str(tmp_path), symbols, max_files=1)[
                    "status"
                ]
                == "missing"
            )

        with patch(
            "tree_sitter_analyzer.complexity_heatmap.analyze_file_complexity_from_cache",
            side_effect=[[], RuntimeError("boom")],
        ):
            result = _complexity_facet(
                MagicMock(),
                str(tmp_path),
                [*symbols, {"file": "other.py", "line": 2, "name": "other"}],
                max_files=2,
            )

        assert result["files"][0]["status"] == "no_functions"
        assert result["files"][1]["status"] == "error"

        with patch("tree_sitter_analyzer.health_scorer.HealthScorer") as scorer_cls:
            scorer_cls.return_value.score_file.side_effect = RuntimeError("bad health")
            health = _health_facet(str(tmp_path), symbols, max_files=1)

        assert health["files"] == [
            {"file": "main.py", "status": "error", "error": "bad health"}
        ]
        with patch.dict("sys.modules", {"tree_sitter_analyzer.health_scorer": None}):
            assert _health_facet(str(tmp_path), symbols, max_files=1)["status"] == (
                "missing"
            )

        empty_state = _QueryState()
        assert _affected_tests_facet(empty_state)["status"] == "missing"
        assert _risk_facet(empty_state)["level"] == "info"
        caution_state = _QueryState()
        caution_state.facets["complexity"] = {
            "files": [
                {"file": "mid.py", "max_complexity": 12},
                {"file": "small.py", "max_complexity": 5},
            ]
        }
        caution_state.facets["health"] = {"files": [{"file": "ok.py", "grade": "B"}]}
        assert _risk_facet(caution_state)["reasons"] == ["mid.py: high complexity 12"]
        assert _absolute_path(str(tmp_path), str(tmp_path / "main.py")) == str(
            tmp_path / "main.py"
        )

    def test_dedupe_symbols_keeps_first_instance(self):
        symbols = [
            {"file": "main.py", "line": 1, "name": "run"},
            {"file": "main.py", "line": 1, "name": "run"},
            {"file": "main.py", "line": 2, "name": "run"},
        ]

        assert _dedupe_symbols(symbols) == [symbols[0], symbols[2]]
