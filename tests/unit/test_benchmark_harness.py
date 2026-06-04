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
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# ``benchmarks/agent-tasks`` sits at the repo root, not under ``tree_sitter_analyzer``.
_BENCH_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "agent-tasks"
if str(_BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(_BENCH_DIR))

import bench_runner  # noqa: E402
import scenarios  # noqa: E402

from benchmarks.codegraph_compare import analyze as compare_analyze  # noqa: E402
from benchmarks.codegraph_compare import evaluate as compare_evaluate  # noqa: E402
from benchmarks.codegraph_compare import run as compare_run  # noqa: E402
from benchmarks.codegraph_compare.adapters import IndexStats  # noqa: E402
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
            assert any(
                t.startswith("mcp__tree-sitter-analyzer__") for t in allowed
            )
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


class TestCodeGraphCompareAnalysisGate:
    def test_gate_flags_failed_and_low_quality_arms(self):
        runs = [
            {
                "_arm": "codex/tsa-warm",
                "answer": "ok",
                "error": "",
                "_quality": 4.0,
            },
            {
                "_arm": "codex/tsa-warm",
                "answer": "ok",
                "error": "timeout",
                "_quality": 4.0,
            },
            {
                "_arm": "codex/native-only",
                "answer": "ok",
                "error": "",
                "_quality": 2.0,
            },
        ]

        violations = compare_analyze.gate_violations(runs, has_evals=True)

        assert any(
            "codex/tsa-warm" in item and "failure rate" in item for item in violations
        )
        assert any(
            "codex/native-only" in item and "below quality" in item
            for item in violations
        )


class TestCodeGraphCompareEvaluator:
    def test_eval_prompt_renders_inputs_without_formatting_json_example(self):
        prompt = compare_evaluate._build_eval_prompt(
            question_text="Where is route matching handled?",
            expected_key_points=["router tree", "method matching"],
            answer="The route tree is used in tree.go.",
        )

        assert '"correctness"' in prompt
        assert "Where is route matching handled?" in prompt
        assert "router tree" in prompt
        assert "The route tree is used in tree.go." in prompt

    def test_evaluate_all_accepts_current_run_schema(self, tmp_path: Path):
        repo = tmp_path / "gin"
        repo.mkdir()
        (repo / "tree.go").write_text("package gin\n", encoding="utf-8")

        runs_jsonl = tmp_path / "runs.jsonl"
        runs_jsonl.write_text(
            json.dumps(
                {
                    "run_id": "gin-route-matching__tsa-warm__codex__00",
                    "repo": "gin",
                    "question_id": "gin-route-matching",
                    "arm": "tsa-warm",
                    "answer": "Route matching is handled in tree.go:1.",
                    "citations": ["tree.go:1"],
                    "error": None,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        questions_yaml = tmp_path / "questions.yaml"
        questions_yaml.write_text(
            textwrap.dedent(
                """
                questions:
                  - id: gin-route-matching
                    repo: gin
                    category: entrypoint-tracing
                    prompt: Where is route matching handled?
                    expected_key_points:
                      - route matching
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        manifest = tmp_path / "prepared_repos.json"
        manifest.write_text(
            json.dumps([{"id": "gin", "local_path": str(repo)}]),
            encoding="utf-8",
        )
        results_dir = tmp_path / "results"

        evals = compare_evaluate.evaluate_all(
            runs_jsonl=runs_jsonl,
            questions_yaml=questions_yaml,
            prepared_manifest=manifest,
            results_dir=results_dir,
            dry_run=True,
        )

        assert len(evals) == 1
        record = evals[0]
        assert record["arm_id"] == "tsa-warm"
        assert record["repo_path"] == str(repo)
        assert record["bad_citations"] == []
        assert record["overall"] == 3.0
        assert record["evaluated_with_llm"] is False
        assert record["evaluator_model"] == record["eval_model"]

    def test_evaluate_run_marks_llm_fallback_as_not_evaluated(self, tmp_path: Path):
        run = {
            "run_id": "gin-route-matching__tsa-warm__codex__00",
            "repo": "gin",
            "question_id": "gin-route-matching",
            "arm": "tsa-warm",
            "answer": "Route matching is handled in tree.go:1.",
            "citations": ["tree.go:1"],
            "error": None,
        }
        question = {
            "id": "gin-route-matching",
            "prompt": "Where is route matching handled?",
            "expected_key_points": ["route matching"],
        }
        (tmp_path / "tree.go").write_text("package gin\n", encoding="utf-8")

        with patch(
            "benchmarks.codegraph_compare.evaluate._call_llm",
            return_value={
                "correctness": 3,
                "completeness": 3,
                "citation_quality": 3,
                "hallucination_risk": 3,
                "reasoning": "fallback",
                "_llm_success": False,
            },
        ):
            record = compare_evaluate.evaluate_run(
                run=run,
                question=question,
                repo_path=tmp_path,
                dry_run=False,
            )

        assert record["evaluated_with_llm"] is False
        assert record["overall"] == 3.0
