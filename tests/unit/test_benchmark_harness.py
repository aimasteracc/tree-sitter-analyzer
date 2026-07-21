"""Unit tests for benchmarks/agent-tasks/{bench_runner,scenarios}.

The harness lives outside ``tree_sitter_analyzer/`` so the wheel doesn't ship
it. We import it via a path hack — same trick ``bench_runner`` itself uses
for sibling-module imports.

Created: 2026-05-22 r37fE
"""

from __future__ import annotations

import hashlib
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
        with patch(
            "benchmarks.codegraph_compare.adapters.codegraph.subprocess.run",
            return_value=SimpleNamespace(returncode=3, stderr="codegraph failed"),
        ):
            with pytest.raises(RuntimeError, match="exited with code 3"):
                _build_index(tmp_path, index_dir)

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


class TestCodeGraphCompareSetupGate:
    """Model-backed matrix work must be fail-closed behind setup validation."""

    @staticmethod
    def _matrix_args() -> SimpleNamespace:
        return SimpleNamespace(
            repos="all",
            arms="all",
            repeats=1,
            question_limit=None,
            dry_run=False,
            agent_backend="codex",
            model="gpt-5",
            timeout_seconds=1200,
            manifest=None,
            setup_only=False,
            index_evidence=None,
        )

    @staticmethod
    def _matrix_configs(repo_path: Path) -> tuple[list[dict], list[dict], list[dict]]:
        repos = [{"id": "demo", "local_path": str(repo_path)}]
        arms = [
            {"id": "native-only", "index_mode": "none"},
            {"id": "codegraph-warm", "index_mode": "warm"},
            {"id": "tsa-warm", "index_mode": "warm"},
        ]
        questions = [
            {
                "id": "demo-q1",
                "repo": "demo",
                "prompt": "Where is the entry point?",
            }
        ]
        return repos, arms, questions

    @staticmethod
    def _install_runner_modules(
        monkeypatch, get_adapter, run_one, validate_backend=None
    ) -> None:
        from types import ModuleType

        adapters_module = ModuleType("adapters")
        adapters_module.get_adapter = get_adapter
        runner_module = ModuleType("adapters.claude_runner")
        runner_module.run_one = run_one
        runner_module.validate_backend_arm_support = validate_backend or (
            lambda agent_backend, arm_id: None
        )
        monkeypatch.setitem(sys.modules, "adapters", adapters_module)
        monkeypatch.setitem(sys.modules, "adapters.claude_runner", runner_module)

    @staticmethod
    def _patch_matrix_inputs(monkeypatch, tmp_path: Path) -> None:
        repos, arms, questions = TestCodeGraphCompareSetupGate._matrix_configs(tmp_path)
        configs = {
            compare_run.REPOS_YAML: repos,
            compare_run.ARMS_YAML: arms,
            compare_run.QUESTIONS_YAML: questions,
        }
        monkeypatch.setattr(compare_run, "_load_yaml", configs.__getitem__)
        monkeypatch.setattr(
            compare_run, "_repo_local_path", lambda repo: Path(repo["local_path"])
        )
        monkeypatch.setattr(compare_run, "RESULTS_DIR", tmp_path / "results")

    @staticmethod
    def _patch_v1_matrix_inputs(monkeypatch, tmp_path: Path) -> None:
        configs = {
            compare_run.REPOS_YAML: [{"id": "gin", "local_path": str(tmp_path)}],
            compare_run.ARMS_YAML: [
                {"id": "codegraph-warm", "index_mode": "warm"},
                {"id": "tsa-warm", "index_mode": "warm"},
            ],
            compare_run.QUESTIONS_YAML: [
                {
                    "id": "q1",
                    "repo": "gin",
                    "prompt": "Where is the entry point?",
                }
            ],
        }
        monkeypatch.setattr(compare_run, "_load_yaml", configs.__getitem__)
        monkeypatch.setattr(
            compare_run, "_repo_local_path", lambda repo: Path(repo["local_path"])
        )
        monkeypatch.setattr(compare_run, "RESULTS_DIR", tmp_path / "results")

    @staticmethod
    def _write_v1_manifest(tmp_path: Path, manifest) -> Path:
        from dataclasses import asdict

        path = tmp_path / "experiment_manifest.json"
        path.write_text(json.dumps(asdict(manifest)), encoding="utf-8")
        return path

    @staticmethod
    def _write_v1_index_evidence(tmp_path: Path, manifest, *, readiness=True) -> Path:
        from dataclasses import asdict, replace

        cells = []
        for arm_id in ("codegraph-warm", "tsa-warm"):
            record = _v1_run(manifest, f"q1__{arm_id}__codex__00")
            assert record.index_stats is not None
            stats = record.index_stats
            if not readiness and arm_id == "tsa-warm":
                stats = replace(stats, readiness_oracles=("unexpected-symbol",))
            cells.append(
                {"repo_id": "gin", "arm_id": arm_id, "index_stats": asdict(stats)}
            )
        path = tmp_path / "index_evidence.json"
        path.write_text(
            json.dumps({"schema_version": 1, "cells": cells}), encoding="utf-8"
        )
        return path

    def test_manifest_bound_setup_only_writes_success_evidence_without_model_calls(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig

        manifest = _v1_manifest()
        manifest_path = self._write_v1_manifest(tmp_path, manifest)
        evidence_input = self._write_v1_index_evidence(tmp_path, manifest)
        model_calls = 0

        class Adapter:
            def __init__(self, arm_id: str) -> None:
                self.arm_id = arm_id

            def prepare_index(self, repo_path: Path, cold: bool):
                record = _v1_run(manifest, f"q1__{self.arm_id}__codex__00")
                assert record.index_stats is not None
                return record.index_stats

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                return RunConfig(self.arm_id, repo_path, "system")

        def run_one(**kwargs):
            nonlocal model_calls
            model_calls += 1
            raise AssertionError("setup-only must not call the model")

        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(monkeypatch, Adapter, run_one)
        args = self._matrix_args()
        args.manifest = str(manifest_path)
        args.setup_only = True
        args.index_evidence = evidence_input

        assert compare_run.cmd_run_matrix(args) == 0
        assert model_calls == 0
        evidence_path = next(
            (tmp_path / "results" / "experiments" / manifest.manifest_hash).glob(
                "setup_*.json"
            )
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert evidence["schema_version"] == 1
        assert evidence["experiment_id"] == manifest.experiment_id
        assert evidence["manifest_hash"] == manifest.manifest_hash
        assert evidence["status"] == "setup_passed"
        assert evidence["validation_level"] == "manifest-bound-v1-consumer"
        assert evidence["publishable"] is False
        assert evidence["model_calls_started"] == 0
        assert [(cell["repo_id"], cell["arm_id"]) for cell in evidence["cells"]] == [
            ("gin", "codegraph-warm"),
            ("gin", "tsa-warm"),
        ]
        registry_events = [
            json.loads(line)
            for line in (tmp_path / "results" / "experiment_registry.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert registry_events == [
            {
                "experiment_id": manifest.experiment_id,
                "manifest_hash": manifest.manifest_hash,
                "outcome": "setup_started",
                "status": "PLANNED",
            },
            {
                "experiment_id": manifest.experiment_id,
                "manifest_hash": manifest.manifest_hash,
                "outcome": "setup_passed",
                "status": "PLANNED",
            },
        ]

    def test_matrix_manifest_mismatch_fails_before_adapter_creation(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = _v1_manifest()
        manifest_path = self._write_v1_manifest(tmp_path, manifest)
        adapter_calls = 0
        model_calls = 0

        def get_adapter(arm_id: str):
            nonlocal adapter_calls
            adapter_calls += 1
            raise AssertionError("mismatched matrix must not create an adapter")

        def run_one(**kwargs):
            nonlocal model_calls
            model_calls += 1
            raise AssertionError("mismatched matrix must not call the model")

        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(monkeypatch, get_adapter, run_one)
        args = self._matrix_args()
        args.arms = "tsa-warm"
        args.manifest = str(manifest_path)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)

        assert compare_run.cmd_run_matrix(args) == 1
        assert adapter_calls == 0
        assert model_calls == 0
        evidence_path = next(
            (tmp_path / "results" / "experiments" / manifest.manifest_hash).glob(
                "setup_*.json"
            )
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert [failure["code"] for failure in evidence["failures"]] == [
            "MATRIX_MANIFEST_MISMATCH"
        ]

    def test_readiness_oracle_mismatch_fails_closed_without_model_calls(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = _v1_manifest()
        manifest_path = self._write_v1_manifest(tmp_path, manifest)
        evidence_input = self._write_v1_index_evidence(
            tmp_path, manifest, readiness=False
        )
        model_calls = 0

        def run_one(**kwargs):
            nonlocal model_calls
            model_calls += 1
            raise AssertionError("failed readiness must not call the model")

        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(
            monkeypatch,
            lambda arm_id: (_ for _ in ()).throw(
                AssertionError("evidence consumer must not create adapters")
            ),
            run_one,
        )
        args = self._matrix_args()
        args.manifest = str(manifest_path)
        args.setup_only = True
        args.index_evidence = evidence_input

        assert compare_run.cmd_run_matrix(args) == 1
        assert model_calls == 0
        evidence_path = next(
            (tmp_path / "results" / "experiments" / manifest.manifest_hash).glob(
                "setup_*.json"
            )
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert [failure["code"] for failure in evidence["failures"]] == [
            "READINESS_ORACLE_MISMATCH"
        ]

    def test_setup_evidence_uses_exclusive_create(self, monkeypatch, tmp_path: Path):
        from benchmarks.codegraph_compare.adapters import RunConfig

        manifest = _v1_manifest()
        manifest_path = self._write_v1_manifest(tmp_path, manifest)
        evidence_input = self._write_v1_index_evidence(tmp_path, manifest)
        session_id = "20260721T010203000000Z"
        experiment_dir = tmp_path / "results" / "experiments" / manifest.manifest_hash
        experiment_dir.mkdir(parents=True)
        evidence_path = experiment_dir / f"setup_{session_id}.json"
        evidence_path.write_text("sentinel\n", encoding="utf-8")

        class Adapter:
            def __init__(self, arm_id: str) -> None:
                self.arm_id = arm_id

            def prepare_index(self, repo_path: Path, cold: bool):
                record = _v1_run(manifest, f"q1__{self.arm_id}__codex__00")
                assert record.index_stats is not None
                return record.index_stats

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                return RunConfig(self.arm_id, repo_path, "system")

        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(
            monkeypatch,
            Adapter,
            lambda **kwargs: (_ for _ in ()).throw(
                AssertionError("setup-only must not call the model")
            ),
        )
        monkeypatch.setattr(
            compare_run,
            "datetime",
            SimpleNamespace(
                now=lambda timezone: SimpleNamespace(
                    strftime=lambda pattern: session_id
                )
            ),
        )
        args = self._matrix_args()
        args.manifest = str(manifest_path)
        args.setup_only = True
        args.index_evidence = evidence_input

        with pytest.raises(FileExistsError):
            compare_run.cmd_run_matrix(args)

        assert evidence_path.read_text(encoding="utf-8") == "sentinel\n"
        registry_events = [
            json.loads(line)
            for line in (tmp_path / "results" / "experiment_registry.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert registry_events == [
            {
                "experiment_id": manifest.experiment_id,
                "manifest_hash": manifest.manifest_hash,
                "outcome": "setup_started",
                "status": "PLANNED",
            },
            {
                "experiment_id": manifest.experiment_id,
                "manifest_hash": manifest.manifest_hash,
                "outcome": "setup_internal_failed",
                "status": "BLOCKED",
            },
        ]

    def test_invalid_index_evidence_records_started_and_blocked(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = _v1_manifest()
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        args = self._matrix_args()
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = tmp_path / "invalid.json"
        args.index_evidence.write_text("{not-json", encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            compare_run.cmd_run_matrix(args)

        assert exc_info.value.code == 1
        registry_events = [
            json.loads(line)
            for line in (tmp_path / "results" / "experiment_registry.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert [event["outcome"] for event in registry_events] == [
            "setup_started",
            "setup_input_failed",
        ]
        assert [event["status"] for event in registry_events] == [
            "PLANNED",
            "BLOCKED",
        ]

    def test_invalid_matrix_yaml_shape_records_started_and_blocked(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = _v1_manifest()
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        original_load = compare_run._load_yaml
        monkeypatch.setattr(
            compare_run,
            "_load_yaml",
            lambda path: (
                [{"local_path": str(tmp_path)}]
                if path == compare_run.REPOS_YAML
                else original_load(path)
            ),
        )
        args = self._matrix_args()
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)

        with pytest.raises(SystemExit) as exc_info:
            compare_run.cmd_run_matrix(args)

        assert exc_info.value.code == 1
        registry_events = [
            json.loads(line)
            for line in (tmp_path / "results" / "experiment_registry.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert [event["outcome"] for event in registry_events] == [
            "setup_started",
            "setup_input_failed",
        ]

    def test_setup_only_rejects_dry_run_before_adapter_creation(
        self, monkeypatch, tmp_path: Path, capsys
    ):
        manifest = _v1_manifest()
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(
            monkeypatch,
            lambda arm_id: (_ for _ in ()).throw(
                AssertionError("invalid setup flags must not create adapters")
            ),
            lambda **kwargs: (_ for _ in ()).throw(
                AssertionError("invalid setup flags must not call the model")
            ),
        )
        args = self._matrix_args()
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)
        args.dry_run = True

        with pytest.raises(SystemExit) as exc_info:
            compare_run.cmd_run_matrix(args)

        assert exc_info.value.code == 1
        assert "cannot be combined with --dry-run" in capsys.readouterr().err

    def test_duplicate_matrix_entry_is_rejected_before_adapter_creation(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = _v1_manifest()
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        original_load = compare_run._load_yaml
        monkeypatch.setattr(
            compare_run,
            "_load_yaml",
            lambda path: (
                original_load(path) + [original_load(path)[0]]
                if path == compare_run.ARMS_YAML
                else original_load(path)
            ),
        )
        self._install_runner_modules(
            monkeypatch,
            lambda arm_id: (_ for _ in ()).throw(
                AssertionError("duplicate matrix must not create adapters")
            ),
            lambda **kwargs: (_ for _ in ()).throw(
                AssertionError("duplicate matrix must not call the model")
            ),
        )
        args = self._matrix_args()
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)

        assert compare_run.cmd_run_matrix(args) == 1

    def test_setup_failure_checks_all_indexed_arms_and_blocks_model_calls(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig

        events: list[str] = []

        class Adapter:
            def __init__(self, arm_id: str) -> None:
                self.arm_id = arm_id

            def prepare_index(self, repo_path: Path, cold: bool) -> IndexStats:
                events.append(f"prepare:{self.arm_id}")
                if self.arm_id == "codegraph-warm":
                    raise RuntimeError("codegraph executable missing")
                if self.arm_id == "tsa-warm":
                    return IndexStats(0.1, 0, 0)
                return IndexStats(0.1, 100, 2)

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                return RunConfig(self.arm_id, repo_path, "system")

        def run_one(**kwargs):
            events.append(f"model:{kwargs['arm_id']}")
            raise AssertionError("model call must remain unreachable")

        self._patch_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(monkeypatch, Adapter, run_one)

        exit_code = compare_run.cmd_run_matrix(self._matrix_args())

        assert exit_code == 1
        assert events == ["prepare:codegraph-warm", "prepare:tsa-warm"]
        evidence_files = list((tmp_path / "results").glob("setup_failures_*.json"))
        assert len(evidence_files) == 1
        evidence = json.loads(evidence_files[0].read_text(encoding="utf-8"))
        assert evidence["status"] == "setup_failed"
        assert evidence["model_calls_started"] == 0
        assert evidence["failures"] == [
            {
                "arm_id": "codegraph-warm",
                "code": "PREPARE_EXCEPTION",
                "index_mode": "warm",
                "message": "codegraph executable missing",
                "repo_id": "demo",
            },
            {
                "arm_id": "tsa-warm",
                "code": "EMPTY_INDEX",
                "index_mode": "warm",
                "message": "index preparation returned zero indexed files",
                "repo_id": "demo",
            },
        ]

    def test_all_indexed_setup_finishes_before_first_model_call(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig

        events: list[str] = []

        class Adapter:
            def __init__(self, arm_id: str) -> None:
                self.arm_id = arm_id

            def prepare_index(self, repo_path: Path, cold: bool) -> IndexStats:
                events.append(f"prepare:{self.arm_id}")
                return IndexStats(0.1, 100, 2)

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                events.append(f"config:{self.arm_id}")
                return RunConfig(self.arm_id, repo_path, "system")

        def run_one(**kwargs):
            events.append(f"model:{kwargs['arm_id']}")
            return {
                "answer": "ok",
                "elapsed_seconds": 0.1,
            }

        self._patch_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(monkeypatch, Adapter, run_one)

        exit_code = compare_run.cmd_run_matrix(self._matrix_args())

        assert exit_code == 0
        first_model = next(
            i for i, event in enumerate(events) if event.startswith("model:")
        )
        assert events[:first_model] == [
            "config:native-only",
            "prepare:codegraph-warm",
            "config:codegraph-warm",
            "prepare:tsa-warm",
            "config:tsa-warm",
        ]
        assert events.count("prepare:codegraph-warm") == 1
        assert events.count("prepare:tsa-warm") == 1

    def test_dry_run_preserves_stub_execution_without_index_setup(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig

        dry_run_calls: list[bool] = []

        class Adapter:
            def __init__(self, arm_id: str) -> None:
                self.arm_id = arm_id

            def prepare_index(self, repo_path: Path, cold: bool) -> IndexStats:
                raise AssertionError("dry-run must not prepare indexes")

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                return RunConfig(self.arm_id, repo_path, "system")

        def run_one(**kwargs):
            dry_run_calls.append(kwargs["dry_run"])
            return {"answer": "DRY_RUN", "elapsed_seconds": 0.0}

        self._patch_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(monkeypatch, Adapter, run_one)
        args = self._matrix_args()
        args.dry_run = True

        exit_code = compare_run.cmd_run_matrix(args)

        assert exit_code == 0
        assert dry_run_calls == [True, True, True]
        assert not list((tmp_path / "results").glob("setup_failures_*.json"))

    def test_run_config_failure_is_collected_before_model_execution(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig

        model_calls = 0

        class Adapter:
            def __init__(self, arm_id: str) -> None:
                self.arm_id = arm_id

            def prepare_index(self, repo_path: Path, cold: bool) -> IndexStats:
                return IndexStats(0.1, 100, 2)

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                if self.arm_id == "tsa-warm":
                    raise RuntimeError("prompt unavailable")
                return RunConfig(self.arm_id, repo_path, "system")

        def run_one(**kwargs):
            nonlocal model_calls
            model_calls += 1
            raise AssertionError("model call must remain unreachable")

        self._patch_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(monkeypatch, Adapter, run_one)

        assert compare_run.cmd_run_matrix(self._matrix_args()) == 1
        assert model_calls == 0
        evidence_path = next((tmp_path / "results").glob("setup_failures_*.json"))
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert evidence["failures"] == [
            {
                "arm_id": "tsa-warm",
                "code": "RUN_CONFIG_EXCEPTION",
                "index_mode": "warm",
                "message": "prompt unavailable",
                "question_id": "demo-q1",
                "repo_id": "demo",
            }
        ]

    def test_invalid_mode_and_malformed_stats_fail_closed(self, tmp_path: Path):
        from benchmarks.codegraph_compare.setup_validation import (
            validate_matrix_setup,
        )

        class InvalidStatsAdapter:
            def prepare_index(self, repo_path: Path, cold: bool):
                return None

        result = validate_matrix_setup(
            [{"id": "demo", "local_path": str(tmp_path)}],
            [
                {"id": "bad-mode", "index_mode": "typo"},
                {"id": "bad-stats", "index_mode": "warm"},
            ],
            questions_by_repo={"demo": []},
            repo_path_resolver=lambda repo: Path(repo["local_path"]),
            adapter_factory=lambda arm_id: InvalidStatsAdapter(),
        )

        assert result.ok is False
        assert [failure.code for failure in result.failures] == [
            "INVALID_INDEX_MODE",
            "INVALID_INDEX_STATS",
        ]

    def test_unsupported_backend_arms_block_native_model_before_index_setup(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig

        events: list[str] = []

        class Adapter:
            def __init__(self, arm_id: str) -> None:
                self.arm_id = arm_id

            def prepare_index(self, repo_path: Path, cold: bool) -> IndexStats:
                events.append(f"prepare:{self.arm_id}")
                return IndexStats(0.1, 100, 2)

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                return RunConfig(self.arm_id, repo_path, "system")

        def validate_backend(agent_backend: str, arm_id: str) -> None:
            events.append(f"validate:{agent_backend}:{arm_id}")
            if agent_backend == "codex" and arm_id != "native-only":
                raise NotImplementedError(f"codex does not support {arm_id}")

        def run_one(**kwargs):
            events.append(f"model:{kwargs['arm_id']}")
            raise AssertionError("model call must remain unreachable")

        self._patch_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(
            monkeypatch, Adapter, run_one, validate_backend=validate_backend
        )

        assert compare_run.cmd_run_matrix(self._matrix_args()) == 1
        assert events == [
            "validate:codex:native-only",
            "validate:codex:codegraph-warm",
            "validate:codex:tsa-warm",
        ]
        evidence_path = next((tmp_path / "results").glob("setup_failures_*.json"))
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert [item["code"] for item in evidence["failures"]] == [
            "BACKEND_UNSUPPORTED",
            "BACKEND_UNSUPPORTED",
        ]

    @pytest.mark.parametrize("arm_id", ("codegraph-warm", "tsa-warm"))
    def test_codex_backend_validator_rejects_indexed_mcp_arms(self, arm_id: str):
        from benchmarks.codegraph_compare.adapters.claude_runner import (
            validate_backend_arm_support,
        )

        with pytest.raises(NotImplementedError, match="Per-arm MCP isolation"):
            validate_backend_arm_support("codex", arm_id)

    def test_backend_validator_allows_supported_combinations(self):
        from benchmarks.codegraph_compare.adapters.claude_runner import (
            validate_backend_arm_support,
        )

        validate_backend_arm_support("codex", "native-only")
        validate_backend_arm_support("claude", "tsa-warm")


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


class TestRunIdUniqueness:
    """Raw benchmark artifacts must survive re-runs: a per-invocation session_id
    keeps repeated runs of the same (question, arm, repeat) from overwriting each
    other's transcript — without it, n>1 cost measurement loses earlier data."""

    def test_session_id_uniquifies_raw_artifacts(self, tmp_path):
        from benchmarks.codegraph_compare.adapters import RunConfig
        from benchmarks.codegraph_compare.adapters.claude_runner import run_one

        repo = tmp_path / "repo"
        repo.mkdir()
        results = tmp_path / "results"
        cfg = RunConfig(arm_id="native-only", repo_path=repo, system_prompt="sys")

        common = {
            "question_id": "q1",
            "question_prompt": "trace it",
            "arm_id": "native-only",
            "repo_path": repo,
            "repeat": 0,
            "run_config": cfg,
            "results_dir": results,
            "agent_backend": "claude",
            "dry_run": True,
        }
        r1 = run_one(**common, session_id="SESS_A")
        r2 = run_one(**common, session_id="SESS_B")

        # Same logical run_id (grouping key) ...
        assert r1["run_id"] == r2["run_id"]
        # ... but DISTINCT session ids + distinct raw artifact paths (no overwrite).
        assert r1["session_id"] == "SESS_A"
        assert r2["session_id"] == "SESS_B"
        assert r1["transcript_path"] != r2["transcript_path"]
        raw = results / "raw"
        results_files = sorted(p.name for p in raw.glob("*_result.jsonl"))
        assert len(results_files) == 2, results_files
        assert any("SESS_A" in n for n in results_files)
        assert any("SESS_B" in n for n in results_files)

    def test_run_record_with_session_id_validates_against_schema(self, tmp_path):
        """Codex P2 #332: the new session_id field must NOT break RunRecord's
        extra='forbid' schema — fresh runner output has to validate."""
        from benchmarks.codegraph_compare.adapters import RunConfig
        from benchmarks.codegraph_compare.adapters.claude_runner import run_one
        from benchmarks.codegraph_compare.schemas import RunRecord

        repo = tmp_path / "repo"
        repo.mkdir()
        cfg = RunConfig(arm_id="native-only", repo_path=repo, system_prompt="sys")
        record = run_one(
            question_id="q1",
            question_prompt="trace it",
            arm_id="native-only",
            repo_path=repo,
            repeat=0,
            run_config=cfg,
            results_dir=tmp_path / "results",
            agent_backend="claude",
            dry_run=True,
            session_id="SESS_X",
        )
        # Must not raise — session_id is now a declared optional field.
        validated = RunRecord(**record)
        assert validated.session_id == "SESS_X"


# ---------------------------------------------------------------------------
# Cost / cache accounting capture (real API numbers, not estimates)
# ---------------------------------------------------------------------------


class TestRunRecordCostCacheColumns:
    """The benchmark must record the provider's REAL cache/cost accounting so a
    cost comparison can't be silently contaminated by estimates (see
    benchmark-cost-analysis-rigor memory). The new columns must be optional with
    defaults so pre-existing runs.jsonl records still validate under
    extra='forbid'."""

    def test_run_record_defaults_keep_old_records_loadable(self):
        from benchmarks.codegraph_compare.schemas import RunRecord

        # An "old" record written before the cost/cache columns existed — it has
        # none of the new keys. extra='forbid' + defaults must let it validate.
        old_record = {
            "run_id": "q1__native-only__claude__00",
            "repo": "gin",
            "question_id": "q1",
            "arm": "native-only",
            "repeat": 0,
            "started_at": "2026-06-07T00:00:00+00:00",
            "ended_at": "2026-06-07T00:00:01+00:00",
            "elapsed_seconds": 1.0,
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "estimated_cost_usd": 0.001,
            "tool_calls": 1,
            "file_reads": 1,
            "search_calls": 0,
            "index_queries": 0,
            "answer": "ok",
            "citations": [],
            "transcript_path": "/tmp/x.jsonl",
        }
        validated = RunRecord(**old_record)
        # Defaults applied — no real accounting present in an old record.
        assert validated.cache_read_tokens == 0
        assert validated.cache_creation_tokens == 0
        assert validated.total_cost_usd == 0.0
        assert validated.num_turns == 0

    def test_run_record_accepts_real_cost_cache_columns(self):
        from benchmarks.codegraph_compare.schemas import RunRecord

        record = {
            "run_id": "q1__tsa-warm__claude__00",
            "repo": "gin",
            "question_id": "q1",
            "arm": "tsa-warm",
            "repeat": 0,
            "started_at": "2026-06-07T00:00:00+00:00",
            "ended_at": "2026-06-07T00:00:01+00:00",
            "elapsed_seconds": 1.0,
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "estimated_cost_usd": 0.001,
            "tool_calls": 1,
            "file_reads": 0,
            "search_calls": 0,
            "index_queries": 1,
            "answer": "ok",
            "citations": [],
            "transcript_path": "/tmp/x.jsonl",
            "cache_read_tokens": 1234,
            "cache_creation_tokens": 56,
            "total_cost_usd": 0.0421,
            "num_turns": 7,
        }
        validated = RunRecord(**record)
        assert validated.cache_read_tokens == 1234
        assert validated.cache_creation_tokens == 56
        assert validated.total_cost_usd == 0.0421
        assert validated.num_turns == 7

    def test_runner_parses_real_cache_cost_from_claude_usage_block(self):
        """The runner must pull cache_read/creation, total_cost_usd and num_turns
        straight from the claude --print result/usage block — not estimate them."""
        from benchmarks.codegraph_compare.adapters.claude_runner import (
            _extract_cost_accounting,
        )

        raw_result = {
            "total_cost_usd": 0.0421,
            "num_turns": 7,
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 1234,
                "cache_creation_input_tokens": 56,
            },
        }
        acct = _extract_cost_accounting(raw_result)
        assert acct["cache_read_tokens"] == 1234
        assert acct["cache_creation_tokens"] == 56
        assert acct["total_cost_usd"] == 0.0421
        assert acct["num_turns"] == 7

    def test_runner_captures_codex_cache_hits(self):
        """Codex reports prompt-cache hits as `cached_input_tokens`, not Claude's
        `cache_read_input_tokens` — the backend-neutral cache_read_tokens column
        must capture them, not record 0 (Codex P2 #342)."""
        from benchmarks.codegraph_compare.adapters.claude_runner import (
            _extract_cost_accounting,
        )

        acct = _extract_cost_accounting(
            {"usage": {"input_tokens": 100, "cached_input_tokens": 999}}
        )
        assert acct["cache_read_tokens"] == 999

    def test_runner_emits_cost_cache_columns_in_record(self, tmp_path):
        from benchmarks.codegraph_compare.adapters import RunConfig
        from benchmarks.codegraph_compare.adapters.claude_runner import run_one
        from benchmarks.codegraph_compare.schemas import RunRecord

        repo = tmp_path / "repo"
        repo.mkdir()
        cfg = RunConfig(arm_id="native-only", repo_path=repo, system_prompt="sys")
        record = run_one(
            question_id="q1",
            question_prompt="trace it",
            arm_id="native-only",
            repo_path=repo,
            repeat=0,
            run_config=cfg,
            results_dir=tmp_path / "results",
            agent_backend="claude",
            dry_run=True,
            session_id="SESS_X",
        )
        # Keys present on every record (dry-run → zeros) and schema-valid.
        for key in (
            "cache_read_tokens",
            "cache_creation_tokens",
            "total_cost_usd",
            "num_turns",
        ):
            assert key in record, key
        RunRecord(**record)  # must not raise


# ---------------------------------------------------------------------------
# RFC-0021 Slice A1 — experiment integrity core
# ---------------------------------------------------------------------------


def _v1_paths_hash(paths: tuple[str, ...]) -> str:
    payload = json.dumps(
        list(paths), ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _v1_manifest(**overrides):
    from benchmarks.codegraph_compare.integrity import ExpectedCellV1, create_manifest

    values = {
        "benchmark_git_sha": "abc123",
        "config_hash": "cfg123",
        "question_hash": "questions123",
        "oracle_hash": "oracles123",
        "seed": 210021,
        "timeout_seconds": 300,
        "schedule_hash": "schedule123",
        "agent_backend": "codex",
        "model": "gpt-5",
        "agent_cli_fingerprint": "codex-cli-1",
        "platform": "windows-x64",
        "environment_fingerprint": "env123",
        "primary_session_id": "PRIMARY",
        "retry_session_ids": (),
        "expected_run_ids": (
            "q1__codegraph-warm__codex__00",
            "q1__tsa-warm__codex__00",
        ),
        "required_arms": ("codegraph-warm", "tsa-warm"),
        "indexed_arms": ("codegraph-warm", "tsa-warm"),
        "tool_fingerprints": {"codegraph-warm": "cg141", "tsa-warm": "tsa130"},
        "repo_commits": {"gin": "repo123"},
        "repo_fingerprints": {"gin": "repo-fingerprint"},
        "eligible_paths": {"gin": tuple(f"src/file_{index}.py" for index in range(10))},
        "parse_error_allowlists": {"gin": ()},
        "required_readiness_oracles": {
            "codegraph-warm": ("known-symbol",),
            "tsa-warm": ("known-symbol",),
        },
    }
    values.update(overrides)
    if "eligible_paths_hashes" not in overrides:
        values["eligible_paths_hashes"] = {
            repo: _v1_paths_hash(paths)
            for repo, paths in values["eligible_paths"].items()
        }
    if "indexed_arms" not in overrides:
        values["indexed_arms"] = tuple(
            arm for arm in values["required_arms"] if arm != "native-only"
        )
    if "required_readiness_oracles" not in overrides:
        values["required_readiness_oracles"] = dict.fromkeys(
            values["indexed_arms"], ("known-symbol",)
        )
    run_ids = values.pop("expected_run_ids")
    values["expected_cells"] = tuple(
        ExpectedCellV1(
            repo="gin",
            question_id=run_id.rsplit("__", 3)[0],
            arm=run_id.rsplit("__", 3)[1],
            agent_backend=run_id.rsplit("__", 3)[2],
            repeat=int(run_id.rsplit("__", 3)[3]),
            run_id=run_id,
        )
        for run_id in run_ids
    )
    return create_manifest(**values)


def _registry_for(manifest):
    from benchmarks.codegraph_compare.integrity import RegistryEvent

    return (
        RegistryEvent(
            manifest.experiment_id,
            manifest.manifest_hash,
            "PLANNED",
            "registered",
        ),
    )


def _v1_run(manifest, run_id: str, **overrides):
    from benchmarks.codegraph_compare.schemas import (
        BenchmarkStatus,
        IndexStatsV1,
        RunRecordV1,
    )

    arm = run_id.rsplit("__", 3)[1]
    eligible_paths = dict(manifest.eligible_paths)["gin"]
    empty_paths: tuple[str, ...] = ()
    tool_fingerprint = {
        "codegraph-warm": "cg141",
        "tsa-warm": "tsa130",
        "native-only": "native1",
    }[arm]
    values = {
        "benchmark_version": 1,
        "experiment_id": manifest.experiment_id,
        "session_id": "PRIMARY",
        "run_id": run_id,
        "attempt_no": 0,
        "retry_of": None,
        "status": BenchmarkStatus.SUCCESS,
        "repo": "gin",
        "question_id": "q1",
        "arm": arm,
        "repeat": 0,
        "agent_backend": "codex",
        "model": "gpt-5",
        "config_hash": "cfg123",
        "question_hash": "questions123",
        "oracle_hash": "oracles123",
        "tool_fingerprint": tool_fingerprint,
        "repo_commit": "repo123",
        "benchmark_git_sha": "abc123",
        "agent_cli_fingerprint": "codex-cli-1",
        "platform": "windows-x64",
        "environment_fingerprint": "env123",
        "blocker_reason": None,
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "total_cost_usd": 0.01,
        "tool_calls": 1,
        "answer": "answer",
        "index_stats": IndexStatsV1(
            eligible_source_files=len(eligible_paths),
            indexed_source_files=len(eligible_paths),
            excluded_source_files=0,
            parse_error_files=0,
            eligible_paths_hash=_v1_paths_hash(eligible_paths),
            indexed_paths_hash=_v1_paths_hash(eligible_paths),
            excluded_paths_hash=_v1_paths_hash(empty_paths),
            parse_error_paths_hash=_v1_paths_hash(empty_paths),
            indexed_paths=eligible_paths,
            excluded_paths=empty_paths,
            parse_error_paths=empty_paths,
            build_seconds=1.0,
            index_size_bytes=100,
            repo_fingerprint="repo-fingerprint",
            tool_fingerprint=tool_fingerprint,
            readiness_oracles=("known-symbol",),
        ),
    }
    values.update(overrides)
    return RunRecordV1(**values)


def _v1_eval(run):
    from benchmarks.codegraph_compare.schemas import EvalRecordV1

    return EvalRecordV1(
        benchmark_version=1,
        experiment_id=run.experiment_id,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_no=run.attempt_no,
        correctness=5,
        completeness=5,
        citation_location_validity=1.0,
        claim_support=5,
        overall=5.0,
        evaluator_model="judge-v1",
    )


class TestBenchmarkV1SchemaDispatch:
    def test_record_without_version_uses_legacy_schema(self):
        from benchmarks.codegraph_compare.schemas import RunRecord, parse_run_record

        legacy = {
            "run_id": "q1__native-only__codex__00",
            "repo": "gin",
            "question_id": "q1",
            "arm": "native-only",
            "repeat": 0,
            "started_at": "2026-07-17T00:00:00Z",
            "ended_at": "2026-07-17T00:00:01Z",
            "elapsed_seconds": 1.0,
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
            "estimated_cost_usd": 0.0,
            "tool_calls": 0,
            "file_reads": 0,
            "search_calls": 0,
            "index_queries": 0,
            "answer": "ok",
            "citations": [],
            "transcript_path": "legacy.jsonl",
        }

        parsed = parse_run_record(legacy)

        assert type(parsed) is RunRecord

    def test_unknown_benchmark_version_is_rejected(self):
        from benchmarks.codegraph_compare.schemas import parse_run_record

        with pytest.raises(ValueError, match="Unsupported benchmark_version: 2"):
            parse_run_record({"benchmark_version": 2})

    def test_boolean_benchmark_version_is_rejected(self):
        from benchmarks.codegraph_compare.schemas import parse_run_record

        with pytest.raises(ValueError, match="Unsupported benchmark_version: True"):
            parse_run_record({"benchmark_version": True})

    def test_v1_run_survives_real_json_round_trip(self):
        from dataclasses import asdict

        from benchmarks.codegraph_compare.schemas import parse_run_record

        manifest = _v1_manifest(
            retry_session_ids=("RETRY",),
            expected_run_ids=("q1__tsa-warm__codex__00",),
            required_arms=("tsa-warm",),
            tool_fingerprints={"tsa-warm": "tsa130"},
        )
        primary = _v1_run(manifest, "q1__tsa-warm__codex__00")
        retry = _v1_run(
            manifest,
            "q1__tsa-warm__codex__00",
            session_id="RETRY",
            attempt_no=1,
            retry_of=primary.identity,
            citations=("file.py:10",),
        )
        payload = json.loads(json.dumps(asdict(retry)))

        parsed = parse_run_record(payload)

        assert parsed == retry

    def test_v1_eval_survives_real_json_round_trip(self):
        from dataclasses import asdict

        from benchmarks.codegraph_compare.schemas import parse_eval_record

        manifest = _v1_manifest(
            expected_run_ids=("q1__tsa-warm__codex__00",),
            required_arms=("tsa-warm",),
            tool_fingerprints={"tsa-warm": "tsa130"},
        )
        evaluation = _v1_eval(_v1_run(manifest, "q1__tsa-warm__codex__00"))
        payload = json.loads(json.dumps(asdict(evaluation)))

        parsed = parse_eval_record(payload)

        assert parsed == evaluation


class TestBenchmarkExperimentIntegrity:
    def test_manifest_id_is_stable_across_mapping_order(self):
        first = _v1_manifest(
            tool_fingerprints={"codegraph-warm": "cg141", "tsa-warm": "tsa130"}
        )
        second = _v1_manifest(
            tool_fingerprints={"tsa-warm": "tsa130", "codegraph-warm": "cg141"}
        )

        assert first.experiment_id == second.experiment_id

    def test_manifest_survives_real_json_round_trip(self):
        from dataclasses import asdict

        from benchmarks.codegraph_compare.integrity import parse_manifest_v1

        manifest = _v1_manifest()
        payload = json.loads(json.dumps(asdict(manifest)))

        parsed = parse_manifest_v1(payload)

        assert parsed == manifest

    def test_manifest_rejects_required_arm_without_expected_cell(self):
        with pytest.raises(
            ValueError, match="Required arms must exactly match expected cell arms"
        ):
            _v1_manifest(
                expected_run_ids=("q1__tsa-warm__codex__00",),
                required_arms=("codegraph-warm", "tsa-warm"),
            )

    def test_registry_rejects_conflicting_manifest_for_same_experiment(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.integrity import (
            RegistryEvent,
            append_registry_event,
        )

        registry = tmp_path / "registry.jsonl"
        append_registry_event(
            registry,
            RegistryEvent("EXP", "hash-a", "PLANNED", "created"),
        )

        with pytest.raises(
            ValueError, match="Experiment EXP already has manifest hash hash-a"
        ):
            append_registry_event(
                registry,
                RegistryEvent("EXP", "hash-b", "PLANNED", "replaced"),
            )

        assert registry.read_text(encoding="utf-8").count("\n") == 1

    def test_publish_gate_rejects_exact_missing_manifest_cell(self):
        from benchmarks.codegraph_compare.integrity import (
            validate_publishable_experiment,
        )

        manifest = _v1_manifest()
        tsa = _v1_run(manifest, "q1__tsa-warm__codex__00")

        verdict = validate_publishable_experiment(
            manifest,
            registry=_registry_for(manifest),
            runs=(tsa,),
            evals=(_v1_eval(tsa),),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        assert verdict.publishable is False
        assert verdict.claim_level == "INVALID"
        assert verdict.expected_cell_count == 2
        assert verdict.observed_cell_count == 1
        assert tuple(item.code for item in verdict.violations) == ("MISSING_RUN_CELL",)
        assert verdict.violations[0].identity == (
            manifest.experiment_id,
            "PRIMARY",
            "q1__codegraph-warm__codex__00",
            0,
        )

    def test_publish_gate_rejects_unregistered_current_experiment(self):
        from benchmarks.codegraph_compare.integrity import (
            validate_publishable_experiment,
        )

        manifest = _v1_manifest(
            expected_run_ids=("q1__tsa-warm__codex__00",),
            required_arms=("tsa-warm",),
            tool_fingerprints={"tsa-warm": "tsa130"},
        )
        tsa = _v1_run(manifest, "q1__tsa-warm__codex__00")

        verdict = validate_publishable_experiment(
            manifest,
            registry=(),
            runs=(tsa,),
            evals=(_v1_eval(tsa),),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        assert tuple(item.code for item in verdict.violations) == (
            "UNREGISTERED_EXPERIMENT",
        )
        assert verdict.publishable is False

    def test_unlinked_session_cannot_replace_failed_primary(self):
        from benchmarks.codegraph_compare.integrity import (
            validate_publishable_experiment,
        )
        from benchmarks.codegraph_compare.schemas import BenchmarkStatus

        manifest = _v1_manifest(
            expected_run_ids=("q1__tsa-warm__codex__00",),
            required_arms=("tsa-warm",),
            tool_fingerprints={"tsa-warm": "tsa130"},
        )
        failed = _v1_run(
            manifest,
            "q1__tsa-warm__codex__00",
            status=BenchmarkStatus.PRODUCT_FAILURE,
            answer="",
        )
        rogue = _v1_run(
            manifest,
            "q1__tsa-warm__codex__00",
            session_id="ROGUE",
        )

        verdict = validate_publishable_experiment(
            manifest,
            registry=_registry_for(manifest),
            runs=(failed, rogue),
            evals=(),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        assert tuple(item.code for item in verdict.violations) == (
            "UNLINKED_SESSION",
            "REQUIRED_CELL_FAILED",
        )
        assert verdict.canonical_attempts == (failed,)
        assert verdict.reliability_attempts == (failed, rogue)
        assert verdict.disclosed_attempts == (failed, rogue)

    def test_not_evaluated_competitor_disables_dominance(self):
        from benchmarks.codegraph_compare.integrity import (
            validate_publishable_experiment,
        )
        from benchmarks.codegraph_compare.schemas import BenchmarkStatus

        manifest = _v1_manifest()
        codegraph = _v1_run(
            manifest,
            "q1__codegraph-warm__codex__00",
            status=BenchmarkStatus.NOT_EVALUATED,
            blocker_reason="INSTALL_FAILED",
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            total_cost_usd=0.0,
            tool_calls=0,
            answer="",
        )
        tsa = _v1_run(manifest, "q1__tsa-warm__codex__00")

        verdict = validate_publishable_experiment(
            manifest,
            registry=_registry_for(manifest),
            runs=(codegraph, tsa),
            evals=(_v1_eval(tsa),),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        assert verdict.publishable is False
        assert verdict.claim_level == "NOT_EVALUATED"
        assert verdict.dominance_allowed is False
        assert verdict.winner is None
        assert tuple(item.code for item in verdict.violations) == (
            "REQUIRED_ARM_NOT_EVALUATED",
        )
        assert verdict.violations[0].arm == "codegraph-warm"
        assert verdict.violations[0].reason == "INSTALL_FAILED"

    def test_expected_codegraph_cell_cannot_be_faked_by_tsa_record(self):
        from benchmarks.codegraph_compare.integrity import (
            validate_publishable_experiment,
        )

        manifest = _v1_manifest(
            expected_run_ids=("q1__codegraph-warm__codex__00",),
            required_arms=("codegraph-warm",),
            tool_fingerprints={"codegraph-warm": "cg141"},
        )
        disguised = _v1_run(
            manifest,
            "q1__codegraph-warm__codex__00",
            arm="tsa-warm",
            tool_fingerprint="tsa130",
        )

        verdict = validate_publishable_experiment(
            manifest,
            registry=_registry_for(manifest),
            runs=(disguised,),
            evals=(_v1_eval(disguised),),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        assert tuple(item.code for item in verdict.violations) == (
            "CELL_PROVENANCE_MISMATCH",
        )
        assert verdict.publishable is False

    def test_retry_after_success_is_rejected(self):
        from benchmarks.codegraph_compare.integrity import (
            validate_publishable_experiment,
        )

        manifest = _v1_manifest(
            retry_session_ids=("RETRY",),
            expected_run_ids=("q1__tsa-warm__codex__00",),
            required_arms=("tsa-warm",),
            tool_fingerprints={"tsa-warm": "tsa130"},
        )
        primary = _v1_run(manifest, "q1__tsa-warm__codex__00")
        retry = _v1_run(
            manifest,
            "q1__tsa-warm__codex__00",
            session_id="RETRY",
            attempt_no=1,
            retry_of=primary.identity,
        )

        verdict = validate_publishable_experiment(
            manifest,
            registry=_registry_for(manifest),
            runs=(primary, retry),
            evals=(_v1_eval(primary),),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        assert tuple(item.code for item in verdict.violations) == (
            "ILLEGAL_RETRY_STATUS",
        )
        assert verdict.canonical_attempts == (primary,)

    def test_unretried_infrastructure_failure_is_not_publishable(self):
        from benchmarks.codegraph_compare.integrity import (
            validate_publishable_experiment,
        )
        from benchmarks.codegraph_compare.schemas import BenchmarkStatus

        manifest = _v1_manifest(
            expected_run_ids=("q1__tsa-warm__codex__00",),
            required_arms=("tsa-warm",),
            tool_fingerprints={"tsa-warm": "tsa130"},
        )
        failed = _v1_run(
            manifest,
            "q1__tsa-warm__codex__00",
            status=BenchmarkStatus.INFRA_FAILURE,
            answer="",
        )

        verdict = validate_publishable_experiment(
            manifest,
            registry=_registry_for(manifest),
            runs=(failed,),
            evals=(),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        assert tuple(item.code for item in verdict.violations) == (
            "REQUIRED_CELL_FAILED",
        )
        assert verdict.publishable is False

    def test_duplicate_evaluation_is_rejected(self):
        from benchmarks.codegraph_compare.integrity import (
            validate_publishable_experiment,
        )

        manifest = _v1_manifest(
            expected_run_ids=("q1__tsa-warm__codex__00",),
            required_arms=("tsa-warm",),
            tool_fingerprints={"tsa-warm": "tsa130"},
        )
        tsa = _v1_run(manifest, "q1__tsa-warm__codex__00")
        evaluation = _v1_eval(tsa)

        verdict = validate_publishable_experiment(
            manifest,
            registry=_registry_for(manifest),
            runs=(tsa,),
            evals=(evaluation, evaluation),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        assert tuple(item.code for item in verdict.violations) == ("DUPLICATE_EVAL",)
        assert verdict.publishable is False

    def test_native_control_requires_no_index_stats(self):
        from benchmarks.codegraph_compare.integrity import (
            validate_publishable_experiment,
        )

        manifest = _v1_manifest(
            expected_run_ids=("q1__native-only__codex__00",),
            required_arms=("native-only",),
            indexed_arms=(),
            tool_fingerprints={"native-only": "native1"},
            required_readiness_oracles={},
        )
        native = _v1_run(
            manifest,
            "q1__native-only__codex__00",
            index_stats=None,
        )

        verdict = validate_publishable_experiment(
            manifest,
            registry=_registry_for(manifest),
            runs=(native,),
            evals=(_v1_eval(native),),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        assert verdict.violations == ()
        assert verdict.publishable is True

    def test_stale_index_repo_fingerprint_is_rejected(self):
        from dataclasses import replace

        from benchmarks.codegraph_compare.integrity import (
            validate_publishable_experiment,
        )

        manifest = _v1_manifest(
            expected_run_ids=("q1__tsa-warm__codex__00",),
            required_arms=("tsa-warm",),
            tool_fingerprints={"tsa-warm": "tsa130"},
        )
        valid = _v1_run(manifest, "q1__tsa-warm__codex__00")
        stale = replace(
            valid,
            index_stats=replace(valid.index_stats, repo_fingerprint="stale-repo"),
        )

        verdict = validate_publishable_experiment(
            manifest,
            registry=_registry_for(manifest),
            runs=(stale,),
            evals=(_v1_eval(stale),),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        assert tuple(item.code for item in verdict.violations) == (
            "MIXED_INDEX_PROVENANCE",
        )
        assert verdict.publishable is False

    def test_report_gate_rejects_hidden_registered_experiment(self):
        from benchmarks.codegraph_compare.integrity import (
            RegistryEvent,
            validate_publishable_experiment,
        )

        manifest = _v1_manifest()
        codegraph = _v1_run(manifest, "q1__codegraph-warm__codex__00")
        tsa = _v1_run(manifest, "q1__tsa-warm__codex__00")
        hidden = RegistryEvent("EXP_FAILED", "failed-hash", "FAILED", "unfavorable")

        verdict = validate_publishable_experiment(
            manifest,
            registry=(*_registry_for(manifest), hidden),
            runs=(codegraph, tsa),
            evals=(_v1_eval(codegraph), _v1_eval(tsa)),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        assert tuple(item.code for item in verdict.violations) == ("HIDDEN_EXPERIMENT",)
        assert verdict.violations[0].experiment_id == "EXP_FAILED"
        assert verdict.disclosed_experiment_ids == tuple(
            sorted(("EXP_FAILED", manifest.experiment_id))
        )
        assert verdict.publishable is False

    def test_linked_retry_keeps_failure_in_reliability_denominator(self):
        from benchmarks.codegraph_compare.integrity import (
            validate_publishable_experiment,
        )
        from benchmarks.codegraph_compare.schemas import BenchmarkStatus

        manifest = _v1_manifest(
            primary_session_id="PRIMARY",
            retry_session_ids=("RETRY",),
            expected_run_ids=("q1__tsa-warm__codex__00",),
            required_arms=("tsa-warm",),
            tool_fingerprints={"tsa-warm": "tsa130"},
        )
        failed = _v1_run(
            manifest,
            "q1__tsa-warm__codex__00",
            status=BenchmarkStatus.INFRA_FAILURE,
            answer="",
        )
        retry = _v1_run(
            manifest,
            "q1__tsa-warm__codex__00",
            session_id="RETRY",
            attempt_no=1,
            retry_of=failed.identity,
        )

        verdict = validate_publishable_experiment(
            manifest,
            registry=_registry_for(manifest),
            runs=(failed, retry),
            evals=(_v1_eval(retry),),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        assert verdict.publishable is True
        assert verdict.claim_level == "E1"
        assert verdict.canonical_attempts == (retry,)
        assert verdict.reliability_attempts == (failed, retry)
        assert verdict.violations == ()

    def test_paired_retry_must_use_one_retry_session(self):
        from benchmarks.codegraph_compare.integrity import (
            validate_publishable_experiment,
        )
        from benchmarks.codegraph_compare.schemas import BenchmarkStatus

        manifest = _v1_manifest(retry_session_ids=("R1", "R2"))
        codegraph = _v1_run(
            manifest,
            "q1__codegraph-warm__codex__00",
            status=BenchmarkStatus.INFRA_FAILURE,
            answer="",
        )
        tsa = _v1_run(
            manifest,
            "q1__tsa-warm__codex__00",
            status=BenchmarkStatus.INFRA_FAILURE,
            answer="",
        )
        codegraph_retry = _v1_run(
            manifest,
            codegraph.run_id,
            session_id="R1",
            attempt_no=1,
            retry_of=codegraph.identity,
        )
        tsa_retry = _v1_run(
            manifest,
            tsa.run_id,
            session_id="R2",
            attempt_no=1,
            retry_of=tsa.identity,
        )

        verdict = validate_publishable_experiment(
            manifest,
            registry=_registry_for(manifest),
            runs=(codegraph, tsa, codegraph_retry, tsa_retry),
            evals=(_v1_eval(codegraph_retry), _v1_eval(tsa_retry)),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        assert tuple(item.code for item in verdict.violations) == (
            "MIXED_RETRY_SESSION",
        )
        assert verdict.publishable is False

    @pytest.mark.parametrize("mode", ("incomplete", "unapproved_parse_errors"))
    def test_index_partition_must_exactly_cover_eligible_paths(self, mode):
        from dataclasses import replace

        from benchmarks.codegraph_compare.integrity import (
            validate_publishable_experiment,
        )

        manifest = _v1_manifest(
            expected_run_ids=("q1__tsa-warm__codex__00",),
            required_arms=("tsa-warm",),
            tool_fingerprints={"tsa-warm": "tsa130"},
        )
        valid = _v1_run(manifest, "q1__tsa-warm__codex__00")
        assert valid.index_stats is not None
        eligible = valid.index_stats.indexed_paths
        if mode == "incomplete":
            stats = replace(
                valid.index_stats,
                indexed_source_files=1,
                indexed_paths=(eligible[0],),
                indexed_paths_hash=_v1_paths_hash((eligible[0],)),
            )
        else:
            errors = eligible[1:]
            stats = replace(
                valid.index_stats,
                indexed_source_files=1,
                parse_error_files=len(errors),
                indexed_paths=(eligible[0],),
                parse_error_paths=errors,
                indexed_paths_hash=_v1_paths_hash((eligible[0],)),
                parse_error_paths_hash=_v1_paths_hash(errors),
            )
        run = replace(valid, index_stats=stats)

        verdict = validate_publishable_experiment(
            manifest,
            registry=_registry_for(manifest),
            runs=(run,),
            evals=(_v1_eval(run),),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        assert "INDEX_NOT_READY" in {violation.code for violation in verdict.violations}
        assert verdict.publishable is False

    def test_invalid_manifest_returns_verdict_instead_of_crashing(self):
        from dataclasses import replace

        from benchmarks.codegraph_compare.integrity import (
            validate_publishable_experiment,
        )

        valid_manifest = _v1_manifest(
            expected_run_ids=("q1__tsa-warm__codex__00",),
            required_arms=("tsa-warm",),
            tool_fingerprints={"tsa-warm": "tsa130"},
        )
        tampered_manifest = replace(valid_manifest, eligible_paths=())
        run = _v1_run(valid_manifest, "q1__tsa-warm__codex__00")

        verdict = validate_publishable_experiment(
            tampered_manifest,
            registry=_registry_for(tampered_manifest),
            runs=(run,),
            evals=(_v1_eval(run),),
            reported_experiment_ids=(tampered_manifest.experiment_id,),
        )

        assert verdict.publishable is False
        assert tuple(item.code for item in verdict.violations) == (
            "INVALID_MANIFEST_HASH",
            "INVALID_MANIFEST_STRUCTURE",
        )

    def test_failed_registry_status_is_terminal(self):
        from benchmarks.codegraph_compare.integrity import (
            RegistryEvent,
            validate_publishable_experiment,
        )

        manifest = _v1_manifest(
            expected_run_ids=("q1__tsa-warm__codex__00",),
            required_arms=("tsa-warm",),
            tool_fingerprints={"tsa-warm": "tsa130"},
        )
        run = _v1_run(manifest, "q1__tsa-warm__codex__00")
        registry = (
            RegistryEvent(
                manifest.experiment_id,
                manifest.manifest_hash,
                "FAILED",
                "runner failed",
            ),
        )

        verdict = validate_publishable_experiment(
            manifest,
            registry=registry,
            runs=(run,),
            evals=(_v1_eval(run),),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        assert verdict.publishable is False
        assert tuple(item.code for item in verdict.violations) == (
            "REGISTRY_TERMINAL_FAILURE",
        )
