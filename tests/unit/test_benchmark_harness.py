"""Unit tests for benchmarks/agent-tasks/{bench_runner,scenarios}.

The harness lives outside ``tree_sitter_analyzer/`` so the wheel doesn't ship
it. We import it via a path hack — same trick ``bench_runner`` itself uses
for sibling-module imports.

Created: 2026-05-22 r37fE
"""

from __future__ import annotations

import json
import sqlite3
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

# ``benchmarks/agent-tasks`` sits at the repo root, not under ``tree_sitter_analyzer``.
_BENCH_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "agent-tasks"
if str(_BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(_BENCH_DIR))

import bench_runner  # noqa: E402
import scenarios  # noqa: E402

from benchmarks.codegraph_compare.adapters import IndexStats  # noqa: E402
from benchmarks.codegraph_compare.adapters.claude_runner import (  # noqa: E402
    _stdin_prompt_for_backend,
)
from benchmarks.codegraph_compare.adapters.tree_sitter_analyzer import (  # noqa: E402
    TSAAdapter,
)

# ---------------------------------------------------------------------------
# Fixtures — a tiny Python project the harness can analyze fast
# ---------------------------------------------------------------------------


@pytest.fixture
def tiny_repo(tmp_path: Path) -> Path:
    """Create a 3-file Python project. Returns the repo root."""
    src = tmp_path / "tiny_pkg"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "main.py").write_text(
        textwrap.dedent(
            """
            from .util import helper

            def run():
                return helper(1)

            def execute():
                return run()
            """
        ).strip()
        + "\n"
    )
    (src / "util.py").write_text(
        textwrap.dedent(
            """
            def helper(x):
                if x:
                    if x > 0:
                        if x > 1:
                            return x * 2
                return 0
            """
        ).strip()
        + "\n"
    )
    (tmp_path / "README.md").write_text("# Tiny Repo\n\nA test fixture.\n")
    return tmp_path


# ---------------------------------------------------------------------------
# scenarios.SCENARIOS registry contract
# ---------------------------------------------------------------------------


class TestScenarioRegistry:
    def test_lists_four_scenarios(self):
        ids = scenarios.list_scenarios()
        assert set(ids) == {
            "cold-start",
            "find-callers",
            "change-impact",
            "refactor-suggest",
        }

    @pytest.mark.parametrize(
        "task",
        ["cold-start", "find-callers", "change-impact", "refactor-suggest"],
    )
    def test_each_scenario_has_both_runners(self, task: str):
        entry = scenarios.SCENARIOS[task]
        assert callable(entry["tsa"])
        assert callable(entry["baseline"])
        assert isinstance(entry["tsa_tool"], str) and entry["tsa_tool"]


# ---------------------------------------------------------------------------
# bench_runner.run_case → schema contract
# ---------------------------------------------------------------------------


class TestRunCaseSchema:
    def test_tsa_cold_start_returns_required_fields(self, tiny_repo: Path):
        row = bench_runner.run_case(str(tiny_repo), "cold-start", "tsa")
        for field in bench_runner.REQUIRED_FIELDS:
            assert field in row, f"missing {field}; got {sorted(row)}"
        assert row["tool_calls"] == 1
        assert row["wall_clock_s"] >= 0.0

    def test_baseline_cold_start_returns_required_fields(self, tiny_repo: Path):
        row = bench_runner.run_case(str(tiny_repo), "cold-start", "baseline")
        for field in bench_runner.REQUIRED_FIELDS:
            assert field in row
        # Baseline always makes more than 1 call (README + ls + git log + find)
        assert row["tool_calls"] >= 1

    @pytest.mark.parametrize(
        "task,extra",
        [
            ("cold-start", {}),
            ("find-callers", {"symbol": "execute"}),
            ("change-impact", {}),
            ("refactor-suggest", {}),
        ],
    )
    def test_tsa_each_scenario_runs_without_crash(
        self, tiny_repo: Path, task: str, extra: dict
    ):
        row = bench_runner.run_case(str(tiny_repo), task, "tsa", **extra)
        # Even if change-impact has no diff to analyze, the row must be
        # schema-complete (verdict will be SAFE / NOT_FOUND / INFO).
        for field in bench_runner.REQUIRED_FIELDS:
            assert field in row, f"task={task} missing {field}"
        assert isinstance(row["verdict"], str) and row["verdict"]
        assert isinstance(row["agent_decidable"], bool)

    def test_unknown_task_raises(self, tiny_repo: Path):
        with pytest.raises(ValueError, match="Unknown task"):
            bench_runner.run_case(str(tiny_repo), "no-such-task", "tsa")

    def test_unknown_tool_raises(self, tiny_repo: Path):
        with pytest.raises(ValueError, match="tool must be"):
            bench_runner.run_case(str(tiny_repo), "cold-start", "weird-tool")


# ---------------------------------------------------------------------------
# JSONL output round-trip
# ---------------------------------------------------------------------------


class TestJsonlRoundTrip:
    def test_each_line_parses_as_json(self, tiny_repo: Path, tmp_path: Path):
        out_path = tmp_path / "results.jsonl"
        rows = [
            bench_runner.run_case(str(tiny_repo), "cold-start", "tsa"),
            bench_runner.run_case(str(tiny_repo), "cold-start", "baseline"),
        ]
        bench_runner.write_jsonl(rows, out_path)
        assert out_path.exists()
        loaded: list[dict] = []
        with out_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                loaded.append(json.loads(line))
        assert len(loaded) == 2
        for parsed in loaded:
            for field in bench_runner.REQUIRED_FIELDS:
                assert field in parsed

    def test_aggregate_json_has_rows_and_metadata(
        self, tiny_repo: Path, tmp_path: Path
    ):
        out_path = tmp_path / "results.json"
        rows = [bench_runner.run_case(str(tiny_repo), "cold-start", "tsa")]
        bench_runner.write_json_aggregate(rows, out_path)
        payload = json.loads(out_path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1
        assert payload["row_count"] == 1
        assert isinstance(payload["rows"], list)
        assert payload["rows"][0]["task"] == "cold-start"


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


class TestTokenEstimation:
    def test_empty_string_zero_tokens(self):
        assert scenarios.estimate_tokens("") == 0

    def test_short_string_clamps_to_one(self):
        assert scenarios.estimate_tokens("a") == 1

    def test_long_string_scales_by_four_chars(self):
        # 400 chars → 100 tokens (within 1)
        text = "x" * 400
        assert 99 <= scenarios.estimate_tokens(text) <= 101


class TestCodeGraphCompareTSAAdapter:
    def test_run_config_prefers_chained_query(self, tmp_path: Path):
        config = TSAAdapter().build_run_config(tmp_path, "How does request flow work?")

        assert "--codegraph-query" in config.system_prompt
        assert "--codegraph-query" in config.extra_context
        assert "flow(" in config.system_prompt
        assert ".prefer(exclude_tests=True).callees(depth=1).answer()" in (
            config.system_prompt + config.extra_context
        )
        assert "at most 2 TSA CLI calls" in config.system_prompt
        assert "at most 2 TSA CLI calls" in config.extra_context

    def test_warm_index_rebuilds_when_db_is_empty(self, tmp_path: Path):
        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        index_db = cache_dir / "index.db"
        conn = sqlite3.connect(index_db)
        conn.execute("CREATE TABLE ast_index (file_path TEXT)")
        conn.commit()
        conn.close()

        expected = IndexStats(build_seconds=1.0, index_size_bytes=2, file_count=3)
        with patch(
            "benchmarks.codegraph_compare.adapters.tree_sitter_analyzer._build_cache",
            return_value=expected,
        ) as build_cache:
            result = TSAAdapter().prepare_index(tmp_path, cold=False)

        assert result == expected
        build_cache.assert_called_once()

    def test_warm_index_skips_when_db_has_rows(self, tmp_path: Path):
        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        index_db = cache_dir / "index.db"
        conn = sqlite3.connect(index_db)
        conn.execute("CREATE TABLE ast_index (file_path TEXT)")
        conn.execute("INSERT INTO ast_index VALUES ('src/main.py')")
        conn.commit()
        conn.close()

        with patch(
            "benchmarks.codegraph_compare.adapters.tree_sitter_analyzer._build_cache"
        ) as build_cache:
            result = TSAAdapter().prepare_index(tmp_path, cold=False)

        assert result.build_seconds == 0.0
        assert result.file_count == 1
        build_cache.assert_not_called()


class TestCodeGraphCompareToolPolicy:
    def test_tsa_arms_are_index_first(self):
        from benchmarks.codegraph_compare.adapters.claude_runner import (
            _ARM_ALLOWED_TOOLS,
            _ARM_DISALLOWED_TOOLS,
        )
        from benchmarks.codegraph_compare.adapters.tree_sitter_analyzer import (
            _ALLOWED_TOOLS,
        )

        raw_tools = {
            "Read",
            "Glob",
            "Grep",
            "Bash(grep *)",
            "Bash(rg *)",
            "Bash(find *)",
            "Bash(ls *)",
        }
        for arm in ("tsa-warm", "tsa-cold"):
            allowed = set(_ARM_ALLOWED_TOOLS[arm])
            disallowed = set(_ARM_DISALLOWED_TOOLS[arm])

            assert allowed
            assert all("tree_sitter_analyzer" in tool for tool in allowed)
            assert raw_tools.isdisjoint(allowed)
            assert raw_tools <= disallowed
        assert _ALLOWED_TOOLS == ["Bash"]

    def test_tsa_prompt_rejects_filesystem_discovery(self):
        prompt_path = (
            Path(__file__).resolve().parents[2]
            / "benchmarks"
            / "codegraph_compare"
            / "prompts"
            / "system_tsa.md"
        )
        prompt = prompt_path.read_text(encoding="utf-8")

        assert "TSA is the index" in prompt
        assert "invalidates the benchmark" in prompt

    def test_tsa_prompt_prefers_codegraph_query(self):
        prompt_path = (
            Path(__file__).resolve().parents[2]
            / "benchmarks"
            / "codegraph_compare"
            / "prompts"
            / "system_tsa.md"
        )
        prompt = prompt_path.read_text(encoding="utf-8")

        query_pos = prompt.index("--codegraph-query")
        explore_pos = prompt.index("--codegraph-explore")
        assert query_pos < explore_pos
        assert "jQuery selector pipeline" in prompt
        assert "ServeHTTP handleHTTPRequest getValue" in prompt
        assert ".prefer(exclude_tests=True).callees(depth=1).answer()" in prompt
        assert "at most 2 TSA CLI calls" in prompt

    def test_codex_backend_receives_full_prompt_on_stdin(self):
        assert (
            _stdin_prompt_for_backend(
                "codex",
                full_prompt="SYSTEM\n\nUSER",
                user_message="USER",
            )
            == "SYSTEM\n\nUSER"
        )
        assert (
            _stdin_prompt_for_backend(
                "claude",
                full_prompt="SYSTEM\n\nUSER",
                user_message="USER",
            )
            == "USER"
        )
