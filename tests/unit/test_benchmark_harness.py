"""Issue #1376：core 行为组，原测试 AST 保持不变。"""

from __future__ import annotations

import json
import sqlite3
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from benchmarks.codegraph_compare import run as compare_run
from benchmarks.codegraph_compare.adapters import IndexStats
from benchmarks.codegraph_compare.adapters.tree_sitter_analyzer import TSAAdapter

# ``benchmarks/agent-tasks`` sits at the repo root, not under ``tree_sitter_analyzer``.
_BENCH_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "agent-tasks"
if str(_BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(_BENCH_DIR))

import bench_runner  # noqa: E402
import scenarios  # noqa: E402


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


class TestRunCaseSchema:
    def test_baseline_cold_start_returns_required_fields(self, tiny_repo: Path):
        row = bench_runner.run_case(str(tiny_repo), "cold-start", "baseline")
        for field in bench_runner.REQUIRED_FIELDS:
            assert field in row
        # Baseline always makes more than 1 call (README + ls + git log + find)
        assert row["tool_calls"]

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

    def test_failed_tsa_index_command_raises_instead_of_counting_cache_files(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters.tree_sitter_analyzer import (
            _build_cache,
        )

        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        (cache_dir / "stale-metadata.json").write_text("{}", encoding="utf-8")
        with patch(
            "benchmarks.codegraph_compare.adapters.tree_sitter_analyzer.subprocess.run",
            return_value=SimpleNamespace(returncode=2, stderr="index failed"),
        ):
            with pytest.raises(RuntimeError, match="exited with code 2"):
                _build_cache(tmp_path, cache_dir)

    def test_successful_tsa_command_does_not_count_metadata_as_indexed_source(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters.tree_sitter_analyzer import (
            _build_cache,
        )

        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        index_db = cache_dir / "index.db"
        conn = sqlite3.connect(index_db)
        conn.execute("CREATE TABLE ast_index (file_path TEXT)")
        conn.commit()
        conn.close()
        (cache_dir / "metadata.json").write_text("{}", encoding="utf-8")

        with patch(
            "benchmarks.codegraph_compare.adapters.tree_sitter_analyzer.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stderr=""),
        ):
            stats = _build_cache(tmp_path, cache_dir)

        assert stats.file_count == 0

    def test_failed_codegraph_index_command_raises_before_stale_files_count(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters.codegraph import _build_index

        index_dir = tmp_path / ".codegraph"
        index_dir.mkdir()
        (index_dir / "stale.json").write_text("{}", encoding="utf-8")
        with (
            patch(
                "benchmarks.codegraph_compare.adapters.codegraph.subprocess.run",
                return_value=SimpleNamespace(returncode=3, stderr="codegraph failed"),
            ),
            patch(
                "benchmarks.codegraph_compare.adapters.codegraph.resolve_codegraph_executable",
                return_value=Path("/cached/codegraph"),
            ),
        ):
            with pytest.raises(RuntimeError, match="exited with code 3"):
                _build_index(tmp_path, index_dir)

    def test_codegraph_index_uses_pinned_package_without_telemetry(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters.codegraph import _build_index

        index_dir = tmp_path / ".codegraph"
        with (
            patch(
                "benchmarks.codegraph_compare.adapters.codegraph.subprocess.run",
                return_value=SimpleNamespace(returncode=0, stderr=""),
            ) as run,
            patch(
                "benchmarks.codegraph_compare.adapters.codegraph.resolve_codegraph_executable",
                return_value=Path("/cached/codegraph"),
            ),
        ):
            _build_index(tmp_path, index_dir)

        assert run.call_args.args[0] == [
            str(Path("/cached/codegraph")),
            "init",
            "-i",
        ]
        assert run.call_args.kwargs["env"]["CODEGRAPH_TELEMETRY"] == "0"
        assert run.call_args.kwargs["env"]["CODEGRAPH_NO_DAEMON"] == "1"

    def test_codegraph_warm_rebuilds_stale_directory_without_valid_db(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters.codegraph import CodeGraphAdapter

        index_dir = tmp_path / ".codegraph"
        index_dir.mkdir()
        (index_dir / "stale.json").write_text("{}", encoding="utf-8")
        expected = IndexStats(1.0, 200, 3)

        with patch(
            "benchmarks.codegraph_compare.adapters.codegraph._build_index",
            return_value=expected,
        ) as build_index:
            result = CodeGraphAdapter().prepare_index(tmp_path, cold=False)

        assert result == expected
        assert not (index_dir / "stale.json").exists()
        build_index.assert_called_once_with(tmp_path, index_dir)

    def test_codegraph_warm_counts_distinct_source_paths_from_database(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters.codegraph import CodeGraphAdapter

        index_dir = tmp_path / ".codegraph"
        index_dir.mkdir()
        conn = sqlite3.connect(index_dir / "codegraph.db")
        conn.execute("CREATE TABLE nodes (file_path TEXT)")
        conn.executemany(
            "INSERT INTO nodes VALUES (?)",
            [("src/a.py",), ("src/a.py",), ("src/b.py",)],
        )
        conn.commit()
        conn.close()

        with patch(
            "benchmarks.codegraph_compare.adapters.codegraph._build_index"
        ) as build_index:
            result = CodeGraphAdapter().prepare_index(tmp_path, cold=False)

        assert result.file_count == 2
        build_index.assert_not_called()

    def test_parse_tool_metrics_counts_mcp_calls_as_index_queries(self):
        # The TSA arm now runs through its MCP facade tools (not the CLI), so
        # mcp__tree-sitter-analyzer__* calls count as index queries, Bash as
        # search, Read as file reads — mirroring the CodeGraph MCP adapter.
        transcript = textwrap.dedent(
            """
            Tool: mcp__tree-sitter-analyzer__nav
            {"action": "context", "query": "Router"}
            Tool: Bash
            rg Router
            Tool: Read
            src/router.ts
            """
        ).strip()

        result = TSAAdapter().parse_tool_metrics(transcript)

        assert result.tool_calls == 3
        assert result.index_queries == 1
        assert result.search_calls == 1
        assert result.file_reads == 1

    def test_run_config_promotes_mcp_nav_context_first(self, tmp_path: Path):
        config = TSAAdapter().build_run_config(tmp_path, "Where is routing handled?")

        # Steer the agent to the one-call MCP context entry point, not the CLI.
        assert "mcp__tree-sitter-analyzer__nav" in config.extra_context
        assert "action=context" in config.extra_context
        assert "--codegraph-query" not in config.extra_context


class TestCodeGraphCompareToolPolicy:
    def test_tsa_arms_expose_mcp_tools_and_block_competitors(self):
        from benchmarks.codegraph_compare.adapters.claude_runner import (
            _ARM_ALLOWED_TOOLS,
            _ARM_DISALLOWED_TOOLS,
        )
        from benchmarks.codegraph_compare.adapters.tree_sitter_analyzer import (
            _ALLOWED_TOOLS,
        )

        for arm in ("tsa-warm", "tsa-cold"):
            allowed = set(_ARM_ALLOWED_TOOLS[arm])
            disallowed = set(_ARM_DISALLOWED_TOOLS[arm])

            # The TSA MCP facade tools are available (index-first path).
            assert "mcp__tree-sitter-analyzer__nav" in allowed
            assert any(t.startswith("mcp__tree-sitter-analyzer__") for t in allowed)
            # The competing index and escape hatches are blocked for a fair,
            # isolated TSA-vs-CodeGraph comparison.
            assert "mcp__codegraph__*" in disallowed
            assert "ToolSearch" in disallowed
            assert "Agent" in disallowed

        # The adapter exposes the TSA MCP facade tools (alongside raw discovery,
        # which the prompt steers the agent away from).
        assert "mcp__tree-sitter-analyzer__nav" in _ALLOWED_TOOLS
        assert "mcp__tree-sitter-analyzer__search" in _ALLOWED_TOOLS

    def test_tsa_prompt_is_mcp_index_first(self):
        prompt_path = (
            Path(__file__).resolve().parents[2]
            / "benchmarks"
            / "codegraph_compare"
            / "prompts"
            / "system_tsa.md"
        )
        prompt = prompt_path.read_text(encoding="utf-8")

        # MCP-arm prompt: nav action=context first, index is source of truth.
        assert "mcp__tree-sitter-analyzer__nav" in prompt
        assert "action=context" in prompt
        assert "AST index is the source of truth" in prompt
        # No stale CLI-DSL references from the old CLI-based arm.
        assert "--codegraph-query" not in prompt

    def test_tsa_mcp_config_pins_target_repo_as_project_root(self, tmp_path: Path):
        """The TSA MCP server must get --project-root <target repo>.

        Without it the server auto-detects and resolves to the ANALYZER repo
        (where its package lives), so every query analyzes tree-sitter-analyzer
        instead of the benchmark target — the agent then calls set_project_path,
        re-queries, and Reads the analyzer tree, inflating cost ~2.5x and
        invalidating the comparison.
        """
        import json as _json

        from benchmarks.codegraph_compare.adapters.claude_runner import (
            _write_arm_mcp_config,
        )

        repo = tmp_path / "gin"
        repo.mkdir()
        cfg_path = _write_arm_mcp_config("tsa-warm", repo)
        cfg = _json.loads(cfg_path.read_text())
        args = cfg["mcpServers"]["tree-sitter-analyzer"]["args"]

        assert "--project-root" in args
        assert str(repo) in args
        # The flag value must be the repo, immediately after the flag.
        assert args[args.index("--project-root") + 1] == str(repo)


class TestCodeGraphComparePhases:
    def test_smoke_phase_expands_to_one_question_dry_run_defaults(self):
        args = SimpleNamespace(
            phase="smoke",
            repos="",
            arms="",
            repeats=None,
            question_limit=None,
            dry_run=True,
            agent_backend="codex",
            model=None,
            timeout_seconds=1200,
        )

        matrix_args = compare_run._phase_to_matrix_args(args)

        assert matrix_args.repos == "gin"
        assert matrix_args.arms == "all"
        assert matrix_args.repeats == 1
        assert matrix_args.question_limit == 1
        assert matrix_args.dry_run is True
        assert matrix_args.agent_backend == "codex"

    def test_pilot_phase_rejects_too_few_repeats(self):
        args = SimpleNamespace(
            phase="pilot",
            repos="",
            arms="",
            repeats=1,
            question_limit=None,
            dry_run=True,
            agent_backend="codex",
            model=None,
            timeout_seconds=1200,
        )

        with pytest.raises(SystemExit):
            compare_run._phase_to_matrix_args(args)
