"""Issue #1376：test_benchmark_harness 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

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

# benchmarks/agent-tasks 位于仓库根目录，不在 tree_sitter_analyzer 下。
_BENCH_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "agent-tasks"
if str(_BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(_BENCH_DIR))

import bench_runner  # noqa: E402
import scenarios  # noqa: E402


@pytest.fixture
def tiny_repo(tmp_path: Path) -> Path:
    """创建包含三个文件的 Python 项目，并返回仓库根目录。"""
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
        # 基线始终调用不止一次，包括 README、ls、git log 和 find。
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
        # 即使 change-impact 没有差异可分析，结果行也必须
        # 满足完整 schema；verdict 可以是 SAFE、NOT_FOUND 或 INFO。
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
        # 400 个字符对应 100 个 token，容差为 1。
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
        # TSA 组现在通过 MCP facade 工具运行，而不是 CLI，因此
        # mcp__tree-sitter-analyzer__* 调用计为索引查询，Bash 计为搜索，
        # Read 计为文件读取，与 CodeGraph MCP adapter 的统计规则一致。
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

        # 引导 agent 使用单次调用的 MCP context 入口，而非 CLI。
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

            # TSA MCP facade 工具可用，采用索引优先路径。
            assert "mcp__tree-sitter-analyzer__nav" in allowed
            assert any(t.startswith("mcp__tree-sitter-analyzer__") for t in allowed)
            # 为实现公平且隔离的 TSA 与 CodeGraph 比较，
            # 必须阻止竞争索引和绕过限制的路径。
            assert "mcp__codegraph__*" in disallowed
            assert "ToolSearch" in disallowed
            assert "Agent" in disallowed

        # adapter 暴露 TSA MCP facade 工具，同时保留原始发现能力，
        # 但提示词会引导 agent 不去使用原始发现能力。
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

        # MCP 组提示词要求先执行 nav action=context，以索引为权威来源。
        assert "mcp__tree-sitter-analyzer__nav" in prompt
        assert "action=context" in prompt
        assert "AST index is the source of truth" in prompt
        # 不能残留旧 CLI 组的 CLI-DSL 引用。
        assert "--codegraph-query" not in prompt

    def test_tsa_mcp_config_pins_target_repo_as_project_root(self, tmp_path: Path):
        """TSA MCP server 必须接收 --project-root <目标仓库>。

        缺少该参数时，server 自动探测到自身包所在的 ANALYZER 仓库，所有查询都会分析 tree-sitter-analyzer 而非 benchmark 目标。agent 随后调用 set_project_path、重新查询并读取 analyzer 目录树，导致成本约增至 2.5 倍，并使比较失效。"""
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
        # 参数值必须是仓库路径，并紧随参数标志之后。
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
