"""Unit tests for benchmarks/agent-tasks/{bench_runner,scenarios}.

The harness lives outside ``tree_sitter_analyzer/`` so the wheel doesn't ship
it. We import it via a path hack — same trick ``bench_runner`` itself uses
for sibling-module imports.

Created: 2026-05-22 r37fE
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import struct
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

# ``benchmarks/agent-tasks`` sits at the repo root, not under ``tree_sitter_analyzer``.
_BENCH_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "agent-tasks"
if str(_BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(_BENCH_DIR))

import bench_runner  # noqa: E402
import scenarios  # noqa: E402

from benchmarks.codegraph_compare import analyze as compare_analyze  # noqa: E402
from benchmarks.codegraph_compare import evaluate as compare_evaluate  # noqa: E402
from benchmarks.codegraph_compare import gin_smoke  # noqa: E402
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


class TestGinSmokeQualification:
    def _bundle(self, tmp_path: Path) -> Path:
        bundle = tmp_path / "bundle"
        gin_smoke.create_bundle(
            bundle,
            benchmark_git_sha="a" * 40,
            repository_path="/fixture/repository",
            repository_commit="b" * 40,
            repository_fingerprint="c" * 64,
            question="Where is the Gin router assembled?",
            model="fixture-model",
            timeout_seconds=60,
        )
        return bundle

    def _validate(self, bundle: Path, git_sha: str = "a" * 40):
        digest = hashlib.sha256((bundle / "checksums.json").read_bytes()).hexdigest()
        return gin_smoke.validate_bundle(
            bundle,
            expected_git_sha=git_sha,
            expected_bundle_digest=digest,
        )

    def test_fixture_bundle_is_e0_only(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)

        result = self._validate(bundle)

        assert result["evidence_level"] == "E0"
        assert result["publishable"] is False
        assert result["dominance_allowed"] is False
        assert result["winner"] is None

    def test_replay_is_byte_identical(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)
        replay = tmp_path / "replay"

        gin_smoke.replay_bundle(
            bundle,
            replay,
            expected_git_sha="a" * 40,
            expected_bundle_digest=hashlib.sha256(
                (bundle / "checksums.json").read_bytes()
            ).hexdigest(),
        )

        source_bytes = {
            path.relative_to(bundle): path.read_bytes()
            for path in bundle.rglob("*")
            if path.is_file()
        }
        replay_bytes = {
            path.relative_to(replay): path.read_bytes()
            for path in replay.rglob("*")
            if path.is_file()
        }
        assert replay_bytes == source_bytes

    @pytest.mark.parametrize(
        ("path", "field", "value", "message"),
        [
            (
                "cells/native.json",
                "repository_path",
                "/wrong/repository",
                "wrong repository",
            ),
            (
                "cells/native.json",
                "input_fingerprint",
                "wrong",
                "mixed or invalid cell",
            ),
            (
                "cells/native.json",
                "index_namespace",
                "index/tree_sitter_analyzer",
                "mixed or invalid cell",
            ),
            (
                "cells/native.json",
                "repository_commit",
                "d" * 40,
                "wrong repository provenance",
            ),
        ],
    )
    def test_tampered_cell_is_rejected(
        self,
        tmp_path: Path,
        path: str,
        field: str,
        value: str,
        message: str,
    ):
        bundle = self._bundle(tmp_path)
        target = bundle / path
        payload = json.loads(target.read_text())
        payload[field] = value
        target.write_text(json.dumps(payload, sort_keys=True) + "\n")
        checksums = json.loads((bundle / "checksums.json").read_text())
        checksums["sha256"][path] = hashlib.sha256(target.read_bytes()).hexdigest()
        (bundle / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True) + "\n"
        )

        with pytest.raises(gin_smoke.QualificationError, match=message):
            self._validate(bundle)

    def test_cross_arm_tool_leakage_is_rejected(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)
        path = "policies/native.json"
        target = bundle / path
        policy = json.loads(target.read_text())
        policy["allowed_tools"].append("codegraph")
        target.write_text(json.dumps(policy, sort_keys=True) + "\n")
        checksums = json.loads((bundle / "checksums.json").read_text())
        checksums["sha256"][path] = hashlib.sha256(target.read_bytes()).hexdigest()
        (bundle / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True) + "\n"
        )

        with pytest.raises(gin_smoke.QualificationError, match="invalid cell"):
            self._validate(bundle)

    @pytest.mark.parametrize("mutation", ["missing_namespace", "extra_result"])
    def test_cell_schema_is_exact(self, tmp_path: Path, mutation: str):
        bundle = self._bundle(tmp_path)
        path = "cells/native.json"
        target = bundle / path
        cell = json.loads(target.read_text())
        if mutation == "missing_namespace":
            del cell["index_namespace"]
        else:
            cell["model_output"] = "undeclared result"
        target.write_text(json.dumps(cell, sort_keys=True) + "\n")
        checksums = json.loads((bundle / "checksums.json").read_text())
        checksums["sha256"][path] = hashlib.sha256(target.read_bytes()).hexdigest()
        (bundle / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True) + "\n"
        )

        with pytest.raises(gin_smoke.QualificationError, match="invalid cell"):
            self._validate(bundle)

    def test_recomputed_config_fingerprint_rejects_tampering(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)
        path = "manifest.json"
        target = bundle / path
        manifest = json.loads(target.read_text())
        manifest["model"] = "different-model"
        target.write_text(json.dumps(manifest, sort_keys=True) + "\n")
        checksums = json.loads((bundle / "checksums.json").read_text())
        checksums["sha256"][path] = hashlib.sha256(target.read_bytes()).hexdigest()
        (bundle / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True) + "\n"
        )

        with pytest.raises(
            gin_smoke.QualificationError, match="config fingerprint mismatch"
        ):
            self._validate(bundle)

    def test_external_bundle_digest_rejects_recomputed_checksums(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)
        original_digest = hashlib.sha256(
            (bundle / "checksums.json").read_bytes()
        ).hexdigest()
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["question_sha256"] = "b" * 64
        manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
        checksums = json.loads((bundle / "checksums.json").read_text())
        checksums["sha256"]["manifest.json"] = hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest()
        (bundle / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True) + "\n"
        )

        with pytest.raises(
            gin_smoke.QualificationError, match="external bundle digest mismatch"
        ):
            gin_smoke.validate_bundle(
                bundle,
                expected_git_sha="a" * 40,
                expected_bundle_digest=original_digest,
            )

    def test_recomputed_enabled_network_is_rejected(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["network"] = "enabled"
        shared = {
            key: manifest[key]
            for key in (
                "question_sha256",
                "model",
                "timeout_seconds",
                "network",
                "allowed_native_tools",
            )
        }
        manifest["config_fingerprint"] = gin_smoke._sha256(shared)
        manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
        for arm in gin_smoke.EXPECTED_ARMS:
            cell_path = bundle / "cells" / f"{arm}.json"
            cell = json.loads(cell_path.read_text())
            cell["config_fingerprint"] = manifest["config_fingerprint"]
            cell_path.write_text(json.dumps(cell, sort_keys=True) + "\n")
        checksums = {
            name: hashlib.sha256((bundle / name).read_bytes()).hexdigest()
            for name in gin_smoke.FILES
        }
        (bundle / "checksums.json").write_text(
            json.dumps({"sha256": checksums}, sort_keys=True) + "\n"
        )

        with pytest.raises(gin_smoke.QualificationError, match="invalid manifest"):
            self._validate(bundle)

    def test_transcript_semantic_tampering_is_rejected(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)
        path = "transcripts/native.jsonl"
        target = bundle / path
        transcript = json.loads(target.read_text())
        transcript["model_executed"] = True
        target.write_text(json.dumps(transcript, sort_keys=True) + "\n")
        checksums = json.loads((bundle / "checksums.json").read_text())
        checksums["sha256"][path] = hashlib.sha256(target.read_bytes()).hexdigest()
        (bundle / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True) + "\n"
        )

        with pytest.raises(
            gin_smoke.QualificationError, match="invalid qualification transcript"
        ):
            self._validate(bundle)

    def test_non_object_json_is_rejected_cleanly(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)
        path = "manifest.json"
        target = bundle / path
        target.write_text("[]\n")
        checksums = json.loads((bundle / "checksums.json").read_text())
        checksums["sha256"][path] = hashlib.sha256(target.read_bytes()).hexdigest()
        (bundle / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True) + "\n"
        )

        with pytest.raises(gin_smoke.QualificationError, match="JSON object required"):
            self._validate(bundle)

    def test_embedded_oracle_field_is_rejected(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)
        path = "manifest.json"
        target = bundle / path
        manifest = json.loads(target.read_text())
        manifest["expected_answer"] = "secret"
        target.write_text(json.dumps(manifest, sort_keys=True) + "\n")
        checksums = json.loads((bundle / "checksums.json").read_text())
        checksums["sha256"][path] = hashlib.sha256(target.read_bytes()).hexdigest()
        (bundle / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True) + "\n"
        )

        with pytest.raises(
            gin_smoke.QualificationError, match="oracle material is forbidden"
        ):
            self._validate(bundle)

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("ground_truth", "secret"),
            ("expected_arms", None),
            ("question_sha256", ""),
        ],
    )
    def test_manifest_schema_is_exact(self, tmp_path: Path, field: str, value: object):
        bundle = self._bundle(tmp_path)
        path = "manifest.json"
        target = bundle / path
        manifest = json.loads(target.read_text())
        manifest[field] = value
        target.write_text(json.dumps(manifest, sort_keys=True) + "\n")
        checksums = json.loads((bundle / "checksums.json").read_text())
        checksums["sha256"][path] = hashlib.sha256(target.read_bytes()).hexdigest()
        (bundle / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True) + "\n"
        )

        with pytest.raises(gin_smoke.QualificationError, match="invalid manifest"):
            self._validate(bundle)

    def test_external_git_anchor_is_required(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)

        with pytest.raises(
            gin_smoke.QualificationError, match="wrong benchmark Git SHA"
        ):
            self._validate(bundle, git_sha="b" * 40)

    def test_mutable_benchmark_ref_is_rejected(self, tmp_path: Path):
        with pytest.raises(gin_smoke.QualificationError, match="identity fields"):
            gin_smoke.create_bundle(
                tmp_path / "bundle",
                benchmark_git_sha="main",
                repository_path="/fixture/repository",
                repository_commit="b" * 40,
                repository_fingerprint="c" * 64,
                question="Where is the Gin router assembled?",
                model="fixture-model",
                timeout_seconds=60,
            )

    def test_missing_cell_is_rejected(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)
        (bundle / "cells" / "codegraph.json").unlink()

        with pytest.raises(
            gin_smoke.QualificationError,
            match="missing, duplicate, or unexpected",
        ):
            self._validate(bundle)


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
        repos, arms, questions = TestCodeGraphCompareSetupGate._v1_matrix_configs(
            tmp_path
        )
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
    def _v1_matrix_configs(
        repo_path: Path,
    ) -> tuple[list[dict], list[dict], list[dict]]:
        return (
            [{"id": "gin", "local_path": str(repo_path), "commit": "repo123"}],
            [
                {"id": "codegraph-warm", "index_mode": "warm"},
                {"id": "tsa-warm", "index_mode": "warm"},
            ],
            [
                {
                    "id": "q1",
                    "repo": "gin",
                    "prompt": "Where is the entry point?",
                }
            ],
        )

    @classmethod
    def _v1_setup_manifest(cls, *, agent_backend: str = "claude", **overrides):
        from benchmarks.codegraph_compare.setup_validation import (
            selected_matrix_config_hash,
            selected_questions_hash,
            selected_schedule_hash,
        )

        repos, arms, questions = cls._v1_matrix_configs(Path("/runtime-path"))
        questions_by_repo = {"gin": questions}
        values = {
            "agent_backend": agent_backend,
            "expected_run_ids": tuple(
                f"q1__{arm['id']}__{agent_backend}__00" for arm in arms
            ),
            "config_hash": selected_matrix_config_hash(repos, arms),
            "question_hash": selected_questions_hash(questions_by_repo),
            "schedule_hash": selected_schedule_hash(
                repos,
                arms,
                questions_by_repo,
                repeats=1,
                agent_backend=agent_backend,
            ),
            "timeout_seconds": 1200,
        }
        values.update(overrides)
        return _v1_manifest(
            **values,
        )

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
            record = _v1_run(
                manifest,
                f"q1__{arm_id}__{manifest.agent_backend}__00",
            )
            stats = record.index_stats
            if stats is None:
                pytest.fail(f"{arm_id} fixture must include V1 index statistics")
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

    @staticmethod
    def _v1_index_stats_payload(manifest) -> dict:
        from dataclasses import asdict

        stats = _v1_run(
            manifest,
            "q1__codegraph-warm__codex__00",
        ).index_stats
        if stats is None:
            pytest.fail("codegraph fixture must include V1 index statistics")
        return json.loads(json.dumps(asdict(stats)))

    @classmethod
    def _parse_v1_index_evidence(
        cls,
        *,
        cell_overrides: dict | None = None,
        stats_overrides: dict | None = None,
    ):
        from benchmarks.codegraph_compare.setup_validation import (
            parse_index_evidence_v1,
        )

        stats_raw = cls._v1_index_stats_payload(_v1_manifest())
        stats_raw.update(stats_overrides or {})
        cell = {
            "repo_id": "gin",
            "arm_id": "codegraph-warm",
            "index_stats": stats_raw,
        }
        cell.update(cell_overrides or {})
        return parse_index_evidence_v1({"schema_version": 1, "cells": [cell]})

    def test_index_evidence_schema_version_requires_integer_one(self):
        from benchmarks.codegraph_compare.setup_validation import (
            parse_index_evidence_v1,
        )

        with pytest.raises(
            ValueError,
            match="Index evidence schema_version must be the integer 1",
        ):
            parse_index_evidence_v1({"schema_version": True, "cells": []})

    @pytest.mark.parametrize(
        ("field", "value"),
        (
            ("repo_id", 1),
            ("repo_id", ""),
            ("arm_id", 1),
            ("arm_id", ""),
        ),
    )
    def test_index_evidence_cell_ids_require_nonempty_strings(
        self,
        field: str,
        value: object,
    ):
        with pytest.raises(
            ValueError,
            match="Index evidence repo_id and arm_id must be strings",
        ):
            self._parse_v1_index_evidence(cell_overrides={field: value})

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        (
            (
                "eligible_source_files",
                "10",
                "Index evidence count and size fields must be integers",
            ),
            (
                "build_seconds",
                "1.0",
                "Index evidence build_seconds must be a finite number",
            ),
            (
                "build_seconds",
                float("nan"),
                "Index evidence build_seconds must be a finite number",
            ),
        ),
    )
    def test_index_evidence_numeric_fields_reject_strings(
        self,
        field: str,
        value: object,
        message: str,
    ):
        with pytest.raises(ValueError, match=message):
            self._parse_v1_index_evidence(stats_overrides={field: value})

    def test_index_evidence_rejects_integer_duration_too_large_for_float(self):
        with pytest.raises(
            ValueError,
            match="Index evidence build_seconds must be a finite number",
        ):
            self._parse_v1_index_evidence(stats_overrides={"build_seconds": 10**400})

    def test_index_evidence_provenance_fields_require_strings(self):
        with pytest.raises(
            ValueError,
            match="Index evidence provenance fields must be strings",
        ):
            self._parse_v1_index_evidence(stats_overrides={"repo_fingerprint": 1})

    @pytest.mark.parametrize(
        ("field", "value"),
        (
            ("indexed_paths", "main.go"),
            ("readiness_oracles", [1]),
        ),
    )
    def test_index_evidence_tuple_fields_require_string_lists(
        self,
        field: str,
        value: object,
    ):
        with pytest.raises(
            ValueError,
            match="Index evidence path and oracle fields must be string lists",
        ):
            self._parse_v1_index_evidence(stats_overrides={field: value})

    def test_manifest_bound_setup_only_writes_success_evidence_without_model_calls(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig

        manifest = self._v1_setup_manifest()
        manifest_path = self._write_v1_manifest(tmp_path, manifest)
        evidence_input = self._write_v1_index_evidence(tmp_path, manifest)
        model_calls = 0

        class Adapter:
            def __init__(self, arm_id: str) -> None:
                self.arm_id = arm_id

            def prepare_index(self, repo_path: Path, cold: bool):
                record = _v1_run(
                    manifest,
                    f"q1__{self.arm_id}__{manifest.agent_backend}__00",
                )
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
        args.agent_backend = manifest.agent_backend
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

    def test_manifest_bound_execution_persists_v1_attempts_in_frozen_order(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig

        manifest = self._v1_setup_manifest(agent_backend="codex")
        manifest_path = self._write_v1_manifest(tmp_path, manifest)
        evidence_input = self._write_v1_index_evidence(tmp_path, manifest)
        observed: list[str] = []

        class Adapter:
            def __init__(self, arm_id: str) -> None:
                self.arm_id = arm_id

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                return RunConfig(self.arm_id, repo_path, "system")

        def run_one(**kwargs):
            run_id = (
                f"{kwargs['question_id']}__{kwargs['arm_id']}__"
                f"{kwargs['agent_backend']}__{kwargs['repeat']:02d}"
            )
            observed.append(run_id)
            transcript = tmp_path / f"{run_id}.jsonl"
            server = (
                "codegraph"
                if kwargs["arm_id"] == "codegraph-warm"
                else "tree-sitter-analyzer"
            )
            transcript.write_text(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "mcp_tool_call",
                            "server": server,
                            "tool": "search",
                        },
                    }
                ),
                encoding="utf-8",
            )
            return {
                "run_id": run_id,
                "session_id": kwargs["session_id"],
                "repo": "gin",
                "question_id": kwargs["question_id"],
                "arm": kwargs["arm_id"],
                "repeat": kwargs["repeat"],
                "agent_backend": kwargs["agent_backend"],
                "model": kwargs["model"],
                "started_at": "2026-07-31T00:00:00Z",
                "ended_at": "2026-07-31T00:00:01Z",
                "elapsed_seconds": 1.0,
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "estimated_cost_usd": 0.0,
                "total_cost_usd": 0.0,
                "tool_calls": 1,
                "file_reads": 0,
                "search_calls": 0,
                "index_queries": 1,
                "answer": "answer",
                "citations": ["gin.go"],
                "transcript_path": str(transcript),
                "error": None,
            }

        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(monkeypatch, Adapter, run_one)
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.manifest = str(manifest_path)
        args.index_evidence = evidence_input

        assert compare_run.cmd_run_matrix(args) == 0
        assert observed == [cell.run_id for cell in manifest.expected_cells]
        attempts_path = (
            tmp_path / "results" / "experiments" / manifest.manifest_hash / "runs.jsonl"
        )
        attempts = [
            json.loads(line)
            for line in attempts_path.read_text(encoding="utf-8").splitlines()
        ]
        assert [attempt["run_id"] for attempt in attempts] == observed
        assert [attempt["status"] for attempt in attempts] == [
            "SUCCESS",
            "SUCCESS",
        ]

    def test_matrix_manifest_mismatch_fails_before_adapter_creation(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = self._v1_setup_manifest()
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
        args.agent_backend = manifest.agent_backend
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

    def test_setup_only_rejects_timeout_that_differs_from_manifest(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = self._v1_setup_manifest()
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.timeout_seconds = manifest.timeout_seconds + 1
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)

        assert compare_run.cmd_run_matrix(args) == 1

        evidence_path = next(
            (tmp_path / "results" / "experiments" / manifest.manifest_hash).glob(
                "setup_*.json"
            )
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert [failure["code"] for failure in evidence["failures"]] == [
            "MATRIX_TIMEOUT_MISMATCH"
        ]

    def test_matrix_rejects_zero_repeats_instead_of_defaulting_to_one(
        self, monkeypatch, tmp_path: Path, capsys
    ):
        manifest = self._v1_setup_manifest()
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.repeats = 0
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)

        with pytest.raises(SystemExit) as exc_info:
            compare_run.cmd_run_matrix(args)

        assert exc_info.value.code == 1
        assert "--repeats must be greater than zero" in capsys.readouterr().err
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

    def test_setup_only_rejects_unsupported_backend_arm_pairs(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = self._v1_setup_manifest(agent_backend="unsupported")
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)

        assert compare_run.cmd_run_matrix(args) == 1

        evidence_path = next(
            (tmp_path / "results" / "experiments" / manifest.manifest_hash).glob(
                "setup_*.json"
            )
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert [failure["code"] for failure in evidence["failures"]] == [
            "BACKEND_UNSUPPORTED",
            "BACKEND_UNSUPPORTED",
        ]

    def test_setup_only_rejects_changed_arm_configuration(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = self._v1_setup_manifest()
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        original_load = compare_run._load_yaml
        changed_arms = [
            {**arm, "adapter": "changed-adapter"}
            for arm in original_load(compare_run.ARMS_YAML)
        ]
        monkeypatch.setattr(
            compare_run,
            "_load_yaml",
            lambda path: (
                changed_arms if path == compare_run.ARMS_YAML else original_load(path)
            ),
        )
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)

        assert compare_run.cmd_run_matrix(args) == 1

        evidence_path = next(
            (tmp_path / "results" / "experiments" / manifest.manifest_hash).glob(
                "setup_*.json"
            )
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert [failure["code"] for failure in evidence["failures"]] == [
            "MATRIX_CONFIG_HASH_MISMATCH"
        ]

    def test_setup_only_rejects_changed_question_configuration(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = self._v1_setup_manifest()
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        original_load = compare_run._load_yaml
        changed_questions = [
            {**question, "prompt": "Changed after manifest creation"}
            for question in original_load(compare_run.QUESTIONS_YAML)
        ]
        monkeypatch.setattr(
            compare_run,
            "_load_yaml",
            lambda path: (
                changed_questions
                if path == compare_run.QUESTIONS_YAML
                else original_load(path)
            ),
        )
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)

        assert compare_run.cmd_run_matrix(args) == 1

        evidence_path = next(
            (tmp_path / "results" / "experiments" / manifest.manifest_hash).glob(
                "setup_*.json"
            )
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert [failure["code"] for failure in evidence["failures"]] == [
            "MATRIX_QUESTION_HASH_MISMATCH"
        ]

    def test_setup_only_rejects_indexed_arm_omission(self, monkeypatch, tmp_path: Path):
        manifest = self._v1_setup_manifest(
            indexed_arms=(),
            required_readiness_oracles={},
        )
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)

        assert compare_run.cmd_run_matrix(args) == 1

        evidence_path = next(
            (tmp_path / "results" / "experiments" / manifest.manifest_hash).glob(
                "setup_*.json"
            )
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert [failure["code"] for failure in evidence["failures"]] == [
            "MATRIX_INDEXED_ARMS_MISMATCH"
        ]

    def test_setup_only_rejects_conflicting_repo_commit(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = self._v1_setup_manifest(repo_commits={"gin": "conflicting-revision"})
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)

        assert compare_run.cmd_run_matrix(args) == 1

        evidence_path = next(
            (tmp_path / "results" / "experiments" / manifest.manifest_hash).glob(
                "setup_*.json"
            )
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert [failure["code"] for failure in evidence["failures"]] == [
            "MATRIX_REPO_COMMIT_MISMATCH"
        ]

    def test_setup_only_accepts_pre_registered_interleaved_schedule(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.setup_validation import (
            selected_schedule_hash,
        )

        repos, arms, questions = self._v1_matrix_configs(Path("/runtime-path"))
        backend = "claude"
        interleaved_arms = list(reversed(arms))
        manifest = self._v1_setup_manifest(
            expected_run_ids=tuple(
                f"q1__{arm['id']}__{backend}__00" for arm in interleaved_arms
            ),
            schedule_hash=selected_schedule_hash(
                repos,
                interleaved_arms,
                {"gin": questions},
                repeats=1,
                agent_backend=backend,
            ),
        )
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)

        assert compare_run.cmd_run_matrix(args) == 0

    def test_setup_only_rejects_schedule_hash_not_bound_to_manifest_cells(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = self._v1_setup_manifest(schedule_hash="wrong-schedule")
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)

        assert compare_run.cmd_run_matrix(args) == 1

        evidence_path = next(
            (tmp_path / "results" / "experiments" / manifest.manifest_hash).glob(
                "setup_*.json"
            )
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert [failure["code"] for failure in evidence["failures"]] == [
            "MATRIX_SCHEDULE_HASH_MISMATCH"
        ]

    def test_matrix_manifest_rejects_selected_repo_without_questions(
        self,
        tmp_path: Path,
    ):
        from benchmarks.codegraph_compare.setup_validation import (
            validate_matrix_setup,
        )

        manifest = _v1_manifest(
            expected_run_ids=("q1__native-only__codex__00",),
            required_arms=("native-only",),
            tool_fingerprints={"native-only": "native"},
        )

        result = validate_matrix_setup(
            [
                {"id": "gin"},
                {"id": "empty"},
            ],
            [{"id": "native-only", "index_mode": "none"}],
            questions_by_repo={
                "gin": [{"id": "q1"}],
                "empty": [],
            },
            repo_path_resolver=lambda repo: tmp_path / str(repo["id"]),
            adapter_factory=lambda arm_id: pytest.fail(
                f"manifest validation created adapter {arm_id}"
            ),
            manifest=manifest,
            repeats=1,
            agent_backend="codex",
            model="gpt-5",
            supplied_index_stats={},
        )

        assert tuple(failure.code for failure in result.failures) == (
            "MATRIX_MANIFEST_MISMATCH",
        )

    def test_readiness_oracle_mismatch_fails_closed_without_model_calls(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = self._v1_setup_manifest()
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
        args.agent_backend = manifest.agent_backend
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

        manifest = self._v1_setup_manifest()
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
                record = _v1_run(
                    manifest,
                    f"q1__{self.arm_id}__{manifest.agent_backend}__00",
                )
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
        args.agent_backend = manifest.agent_backend
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

    def test_oversized_index_duration_records_started_and_blocked(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = _v1_manifest()
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        evidence_path = self._write_v1_index_evidence(tmp_path, manifest)
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence["cells"][0]["index_stats"]["build_seconds"] = 10**400
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        args = self._matrix_args()
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = evidence_path

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

    def test_non_object_manifest_uses_cli_diagnostic(
        self, monkeypatch, tmp_path: Path, capsys
    ):
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("[]", encoding="utf-8")
        args = self._matrix_args()
        args.manifest = manifest_path
        args.setup_only = True
        args.index_evidence = tmp_path / "unused-index-evidence.json"

        with pytest.raises(SystemExit) as exc_info:
            compare_run.cmd_run_matrix(args)

        assert exc_info.value.code == 1
        assert (
            f"Invalid experiment manifest {manifest_path}: "
            "Experiment manifest must be an object" in capsys.readouterr().err
        )

    def test_duplicate_manifest_member_uses_cli_diagnostic(
        self, tmp_path: Path, capsys
    ):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(
            '{"benchmark_version":1,"benchmark_version":1}',
            encoding="utf-8",
        )
        args = self._matrix_args()
        args.manifest = manifest_path
        args.setup_only = True
        args.index_evidence = tmp_path / "unused-index-evidence.json"

        with pytest.raises(SystemExit) as exc_info:
            compare_run.cmd_run_matrix(args)

        assert exc_info.value.code == 1
        assert (
            f"Invalid experiment manifest {manifest_path}: "
            "Duplicate JSON member: benchmark_version" in capsys.readouterr().err
        )

    def test_duplicate_index_evidence_member_records_input_failure(
        self, monkeypatch, tmp_path: Path, capsys
    ):
        manifest = self._v1_setup_manifest()
        evidence_path = tmp_path / "index-evidence.json"
        evidence_path.write_text(
            '{"schema_version":1,"schema_version":1,"cells":[]}',
            encoding="utf-8",
        )
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = evidence_path

        with pytest.raises(SystemExit) as exc_info:
            compare_run.cmd_run_matrix(args)

        assert exc_info.value.code == 1
        assert "Duplicate JSON member: schema_version" in capsys.readouterr().err
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

    def test_malformed_nested_manifest_uses_cli_diagnostic(
        self, monkeypatch, tmp_path: Path, capsys
    ):
        from dataclasses import asdict

        manifest = self._v1_setup_manifest()
        payload = json.loads(json.dumps(asdict(manifest)))
        payload["eligible_paths"] = [[]]
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        args = self._matrix_args()
        args.manifest = manifest_path
        args.setup_only = True
        args.index_evidence = tmp_path / "unused-index-evidence.json"

        with pytest.raises(SystemExit) as exc_info:
            compare_run.cmd_run_matrix(args)

        assert exc_info.value.code == 1
        assert (
            f"Invalid experiment manifest {manifest_path}: "
            "Manifest nested fields do not match the V1 schema"
            in capsys.readouterr().err
        )

    def test_setup_only_direct_script_preserves_package_imports(self, tmp_path: Path):
        import subprocess

        script = Path(compare_run.__file__).resolve()
        missing_manifest = tmp_path / "missing-manifest.json"
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                str(script),
                "run-matrix",
                "--manifest",
                str(missing_manifest),
                "--index-evidence",
                str(tmp_path / "unused-index-evidence.json"),
                "--setup-only",
            ],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert f"Invalid experiment manifest {missing_manifest}" in result.stderr
        assert "ModuleNotFoundError" not in result.stderr

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

    @pytest.mark.parametrize("arm_id", ("native-only", "codegraph-warm", "tsa-warm"))
    def test_codex_backend_validator_allows_isolated_smoke_arms(self, arm_id: str):
        from benchmarks.codegraph_compare.adapters.claude_runner import (
            validate_backend_arm_support,
        )

        validate_backend_arm_support("codex", arm_id)

    def test_backend_validator_allows_supported_combinations(self):
        from benchmarks.codegraph_compare.adapters.claude_runner import (
            validate_backend_arm_support,
        )

        validate_backend_arm_support("codex", "native-only")
        validate_backend_arm_support("claude", "tsa-warm")

    @pytest.mark.parametrize(
        ("arm_id", "server_name"),
        (
            ("tsa-warm", "tree-sitter-analyzer"),
            ("codegraph-warm", "codegraph"),
        ),
    )
    def test_codex_indexed_arm_command_ignores_user_config_and_requires_one_server(
        self, arm_id: str, server_name: str, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig
        from benchmarks.codegraph_compare.adapters.claude_runner import (
            _build_agent_cmd,
        )

        monkeypatch.setattr(
            "benchmarks.codegraph_compare.adapters.claude_runner.resolve_codegraph_executable",
            lambda: Path("/preinstalled/codegraph"),
        )
        command = _build_agent_cmd(
            arm_id,
            "gpt-5",
            tmp_path,
            RunConfig(arm_id, tmp_path, "system"),
            "Read",
            "ToolSearch",
            "codex",
        )

        assert "--ignore-user-config" in command
        assert "--strict-config" in command
        assert f"mcp_servers.{server_name}.required=true" in command
        assert "sandbox_workspace_write.network_access=false" in command
        configured_servers = [
            value
            for value in command
            if value.startswith("mcp_servers.") and value.endswith(".required=true")
        ]
        assert configured_servers == [f"mcp_servers.{server_name}.required=true"]
        if arm_id == "tsa-warm":
            assert not any(
                value.endswith(
                    'enabled_tools=["nav","search","structure","health","index","project"]'
                )
                for value in command
            )
            assert not any('"index"' in value for value in command)
        if arm_id == "codegraph-warm":
            assert (
                'mcp_servers.codegraph.env={ CODEGRAPH_TELEMETRY = "0", '
                'CODEGRAPH_NO_DAEMON = "1" }'
            ) in command

    def test_codex_arm_tool_preflight_qualifies_both_indexed_servers(
        self, monkeypatch, tmp_path: Path
    ):
        import subprocess

        from benchmarks.codegraph_compare.adapters import claude_runner

        executable = tmp_path / "server"
        executable.write_text("fixture", encoding="utf-8")
        monkeypatch.setattr(
            claude_runner,
            "_codex_mcp_config_args",
            lambda arm, repo: ["-c", f"fixture={arm}:{repo.name}"],
        )

        def fake_run(command, **kwargs):
            server = "tree-sitter-analyzer" if "tsa-warm" in command[3] else "codegraph"
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    [
                        {
                            "name": server,
                            "enabled": True,
                            "transport": {
                                "command": str(executable),
                                "args": ["serve", "--mcp"],
                            },
                        }
                    ]
                ),
                stderr="",
            )

        monkeypatch.setattr(claude_runner.subprocess, "run", fake_run)

        evidence = claude_runner.preflight_codex_arm_tools(
            {"tsa-warm": tmp_path, "codegraph-warm": tmp_path}
        )

        assert set(evidence) == {"tsa-warm", "codegraph-warm"}
        assert all(item["enabled"] for item in evidence.values())

    def test_codex_arm_tool_preflight_rejects_missing_executable(
        self, monkeypatch, tmp_path: Path
    ):
        import subprocess

        from benchmarks.codegraph_compare.adapters import claude_runner

        monkeypatch.setattr(
            claude_runner,
            "_codex_mcp_config_args",
            lambda arm, repo: ["-c", f"fixture={arm}:{repo.name}"],
        )
        monkeypatch.setattr(
            claude_runner.subprocess,
            "run",
            lambda command, **kwargs: subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    [
                        {
                            "name": "tree-sitter-analyzer",
                            "enabled": True,
                            "transport": {
                                "command": str(tmp_path / "missing"),
                                "args": [],
                            },
                        }
                    ]
                ),
                stderr="",
            ),
        )

        with pytest.raises(ValueError, match="executable is unavailable"):
            claude_runner.preflight_codex_arm_tools(
                {"tsa-warm": tmp_path, "codegraph-warm": tmp_path}
            )

    def test_codex_native_command_ignores_user_config_without_mcp_servers(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig
        from benchmarks.codegraph_compare.adapters.claude_runner import (
            _build_agent_cmd,
        )

        command = _build_agent_cmd(
            "native-only",
            "gpt-5",
            tmp_path,
            RunConfig("native-only", tmp_path, "system"),
            "Read",
            "ToolSearch",
            "codex",
        )

        assert "--ignore-user-config" in command
        assert "--strict-config" in command
        assert not any(value.startswith("mcp_servers.") for value in command)

    def test_codex_metrics_count_mcp_calls_as_index_queries(self):
        from benchmarks.codegraph_compare.adapters.claude_runner import (
            _parse_codex_tool_calls_from_stream,
        )

        metrics = _parse_codex_tool_calls_from_stream(
            [
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "mcp_tool_call",
                            "server": "codegraph",
                            "tool": "codegraph_search",
                        },
                    }
                )
            ]
        )

        assert metrics == (1, 0, 0, 1)


class TestGinSmokeManifestExecution:
    @staticmethod
    def _tsa_canary_item(call_id: str = "call-001") -> dict:
        payload = {
            "symbol": "Engine.ServeHTTP",
            "definition": {
                "definitions": [
                    {
                        "file": "gin.go",
                        "name": "Engine.ServeHTTP",
                        "kind": "method",
                    }
                ]
            },
        }
        return {
            "id": call_id,
            "type": "mcp_tool_call",
            "status": "completed",
            "server": "tree-sitter-analyzer",
            "tool": "nav",
            "arguments": {
                "action": "navigate",
                "symbol": "Engine.ServeHTTP",
                "file_path": "gin.go",
                "output_format": "json",
            },
            "result": {
                "content": [{"type": "text", "text": json.dumps(payload)}],
                "structured_content": {"untrusted": "not receipt evidence"},
            },
        }

    @staticmethod
    def _legacy_record(manifest, run_id: str, transcript_path: Path) -> dict:
        cell = next(cell for cell in manifest.expected_cells if cell.run_id == run_id)
        return {
            "run_id": cell.run_id,
            "session_id": manifest.primary_session_id,
            "repo": cell.repo,
            "question_id": cell.question_id,
            "arm": cell.arm,
            "repeat": cell.repeat,
            "agent_backend": cell.agent_backend,
            "model": manifest.model,
            "started_at": "2026-07-31T00:00:00Z",
            "ended_at": "2026-07-31T00:00:01Z",
            "elapsed_seconds": 1.0,
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "estimated_cost_usd": 0.0,
            "total_cost_usd": 0.0,
            "tool_calls": 1,
            "file_reads": 0,
            "search_calls": 0,
            "index_queries": 1,
            "answer": "answer",
            "citations": ["gin.go"],
            "transcript_path": str(transcript_path),
            "error": None,
        }

    def test_codex_transcript_accepts_only_the_declared_index_server(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "tsa.jsonl"
        transcript.write_text(
            "\n".join(
                (
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "mcp_tool_call",
                                "server": "tree-sitter-analyzer",
                                "tool": "nav",
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "command": "grep -n ServeHTTP gin.go",
                            },
                        }
                    ),
                )
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "tsa-warm")

        assert audit.violations == ()
        assert audit.observed_mcp_servers == ("tree-sitter-analyzer",)
        assert audit.observed_mcp_tools == ("nav",)

    @pytest.mark.parametrize(
        "failure",
        (
            {"status": "failed"},
            {"error": {"message": "server unavailable"}},
            {"isError": True},
            {"result": {"isError": True}},
            {"result": {"is_error": True}},
        ),
    )
    def test_codex_transcript_rejects_failed_index_query(
        self, tmp_path: Path, failure: dict
    ):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "failed-mcp.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "tree-sitter-analyzer",
                        "tool": "nav",
                        **failure,
                    },
                }
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "tsa-warm")

        assert audit.violations == ("MCP_CALL_FAILED:1", "MISSING_INDEX_QUERY")

    def test_codex_transcript_does_not_accept_started_index_query(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "started-mcp.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.started",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "tree-sitter-analyzer",
                        "tool": "nav",
                    },
                }
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "tsa-warm")

        assert audit.violations == ("MISSING_INDEX_QUERY",)
        assert audit.observed_mcp_servers == ()

    def test_codex_transcript_rejects_mutating_tsa_index_tool(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "mutating-index.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "tree-sitter-analyzer",
                        "tool": "index",
                    },
                }
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "tsa-warm")

        assert audit.violations == (
            "MUTATING_INDEX_TOOL:1",
            "MISSING_INDEX_QUERY",
        )

    def test_codex_transcript_rejects_cross_arm_mcp(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "cross-arm.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "codegraph",
                        "tool": "codegraph_search",
                    },
                }
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "tsa-warm")

        assert audit.violations == ("CROSS_ARM_MCP:1", "MISSING_INDEX_QUERY")

    def test_canary_transcript_binds_exact_mcp_receipt(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        transcript = tmp_path / "canary.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": self._tsa_canary_item(),
                }
            )
            + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "tsa-warm",
            expected_tool="nav",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == ()
        assert audit.receipt is not None
        assert audit.receipt.call_id == "call-001"
        assert audit.receipt.repository_relative_path == "gin.go"
        assert audit.receipt.symbol_identity == "Engine.ServeHTTP"
        assert audit.receipt.symbol_kind == "method"

    @pytest.mark.parametrize(
        "arguments",
        (
            {
                "action": "navigate",
                "symbol": "Engine.ServeHTTP",
                "file_path": "gin.go",
            },
            {
                "action": "navigate",
                "symbol": "Engine.ServeHTTP",
                "file_path": "gin.go",
                "output_format": "toon",
            },
            {
                "action": "resolve",
                "symbol": "Engine.ServeHTTP",
                "file_path": "gin.go",
                "output_format": "json",
            },
        ),
    )
    def test_canary_transcript_rejects_nonexact_tsa_arguments(
        self, tmp_path: Path, arguments: dict
    ):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        item = {**self._tsa_canary_item(), "arguments": arguments}
        transcript = tmp_path / "wrong-tsa-arguments.jsonl"
        transcript.write_text(
            json.dumps({"type": "item.completed", "item": item}) + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "tsa-warm",
            expected_tool="nav",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == (
            "CANARY_ARGUMENTS_MISMATCH:1",
            "CANARY_RECEIPT_MISSING",
        )
        assert audit.receipt is None

    @pytest.mark.parametrize(
        ("mutation", "violation"),
        (
            ({"tool": "unknown"}, "CANARY_TOOL_MISMATCH:1"),
            ({"id": ""}, "CANARY_RECEIPT_INVALID:1"),
            ({"result": {}}, "CANARY_RECEIPT_INVALID:1"),
            ({"status": "started"}, "CANARY_RECEIPT_INVALID:1"),
            ({"status": None}, "CANARY_RECEIPT_INVALID:1"),
        ),
    )
    def test_canary_transcript_rejects_ambiguous_mcp_success(
        self, tmp_path: Path, mutation: dict, violation: str
    ):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        item = {**self._tsa_canary_item(), **mutation}
        transcript = tmp_path / "ambiguous-canary.jsonl"
        transcript.write_text(
            json.dumps({"type": "item.completed", "item": item}) + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "tsa-warm",
            expected_tool="nav",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == (violation, "CANARY_RECEIPT_MISSING")
        assert audit.receipt is None

    def test_canary_transcript_binds_codegraph_markdown_receipt(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        markdown = (
            "**ServeHTTP** (method)\n"
            "func (engine *Engine) ServeHTTP(w http.ResponseWriter, req *http.Request)\n"
            "gin.go:688"
        )
        transcript = tmp_path / "wrong-symbol.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "call-001",
                        "type": "mcp_tool_call",
                        "status": "completed",
                        "server": "codegraph",
                        "tool": "codegraph_search",
                        "arguments": {
                            "query": "Engine.ServeHTTP",
                            "kind": "method",
                            "limit": 10,
                        },
                        "result": {"content": [{"type": "text", "text": markdown}]},
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "codegraph-warm",
            expected_tool="codegraph_search",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == ()
        assert audit.receipt is not None
        assert audit.receipt.server == "codegraph"
        assert audit.receipt.repository_relative_path == "gin.go"

    @pytest.mark.parametrize(
        "markdown",
        (
            "**ServeHTTP** (method)\ngin.go:688",
            "**ServeHTTP** (method)\nfunc ServeHTTP(w http.ResponseWriter)\ngin.go:688",
            "**ServeHTTP** (method)\nfunc (server *Server) ServeHTTP(w http.ResponseWriter)\ngin.go:688",
            "**ServeHTTP** (method)\nfunc (engine *Engine) ServeHTTP(w http.ResponseWriter)\ngin.go:688\n"
            "**ServeHTTP** (method)\nfunc (server *Server) ServeHTTP(w http.ResponseWriter)\nother.go:42",
        ),
    )
    def test_canary_transcript_rejects_codegraph_receiver_counterexamples(
        self, tmp_path: Path, markdown: str
    ):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        item = {
            "id": "call-001",
            "type": "mcp_tool_call",
            "status": "completed",
            "server": "codegraph",
            "tool": "codegraph_search",
            "arguments": {
                "query": "Engine.ServeHTTP",
                "kind": "method",
                "limit": 10,
            },
            "result": {"content": [{"type": "text", "text": markdown}]},
        }
        transcript = tmp_path / "receiver-counterexample.jsonl"
        transcript.write_text(
            json.dumps({"type": "item.completed", "item": item}) + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "codegraph-warm",
            expected_tool="codegraph_search",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == (
            "CANARY_RECEIPT_INVALID:1",
            "CANARY_RECEIPT_MISSING",
        )
        assert audit.receipt is None

    @pytest.mark.parametrize(
        ("arguments", "markdown", "violation"),
        (
            (
                {"query": "ServeHTTP", "kind": "method", "limit": 10},
                "**ServeHTTP** (method)\ngin.go:42",
                "CANARY_ARGUMENTS_MISMATCH:1",
            ),
            (
                {"query": "Engine.ServeHTTP", "kind": "method", "limit": 10},
                "**ServeHTTP** (method)\ngin.go:42\n**ServeHTTP** (method)\ngin.go:688",
                "CANARY_RECEIPT_INVALID:1",
            ),
            (
                {"query": "Engine.ServeHTTP", "kind": "method", "limit": 10},
                "**ServeHTTP** (method)\ngin.go:0",
                "CANARY_RECEIPT_INVALID:1",
            ),
        ),
    )
    def test_canary_transcript_rejects_codegraph_receipt_ambiguity(
        self, tmp_path: Path, arguments: dict, markdown: str, violation: str
    ):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        item = {
            "id": "call-001",
            "type": "mcp_tool_call",
            "status": "completed",
            "server": "codegraph",
            "tool": "codegraph_search",
            "arguments": arguments,
            "result": {"content": [{"type": "text", "text": markdown}]},
        }
        transcript = tmp_path / "bad-codegraph-receipt.jsonl"
        transcript.write_text(
            json.dumps({"type": "item.completed", "item": item}) + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "codegraph-warm",
            expected_tool="codegraph_search",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == (
            violation,
            "CANARY_RECEIPT_MISSING",
        )
        assert audit.receipt is None

    def test_canary_transcript_rejects_started_item_shape(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        item = {**self._tsa_canary_item(), "status": "in_progress"}
        transcript = tmp_path / "started-canary.jsonl"
        transcript.write_text(
            json.dumps({"type": "item.started", "item": item}) + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "tsa-warm",
            expected_tool="nav",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == ("MISSING_INDEX_QUERY", "CANARY_RECEIPT_MISSING")
        assert audit.receipt is None

    def test_canary_transcript_rejects_failed_item_status(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        item = {**self._tsa_canary_item(), "status": "failed"}
        transcript = tmp_path / "failed-canary.jsonl"
        transcript.write_text(
            json.dumps({"type": "item.completed", "item": item}) + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "tsa-warm",
            expected_tool="nav",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == (
            "MCP_CALL_FAILED:1",
            "MISSING_INDEX_QUERY",
            "CANARY_RECEIPT_MISSING",
        )
        assert audit.receipt is None

    def test_canary_transcript_rejects_wrong_tsa_definition(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        item = self._tsa_canary_item()
        payload = json.loads(item["result"]["content"][0]["text"])
        payload["definition"]["definitions"][0]["file"] = "tree.go"
        item["result"]["content"][0]["text"] = json.dumps(payload)
        transcript = tmp_path / "wrong-tsa-definition.jsonl"
        transcript.write_text(
            json.dumps({"type": "item.completed", "item": item}) + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "tsa-warm",
            expected_tool="nav",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == (
            "CANARY_EVIDENCE_MISMATCH:1",
            "CANARY_RECEIPT_MISSING",
        )
        assert audit.receipt is None

    def test_canary_transcript_rejects_multiple_exact_receipts(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        def event(call_id: str) -> str:
            return json.dumps(
                {
                    "type": "item.completed",
                    "item": self._tsa_canary_item(call_id),
                }
            )

        transcript = tmp_path / "duplicate-receipts.jsonl"
        transcript.write_text(
            event("call-001") + "\n" + event("call-002") + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "tsa-warm",
            expected_tool="nav",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == ("CANARY_RECEIPT_AMBIGUOUS",)
        assert audit.receipt is None

    @pytest.mark.parametrize("command", ("rg -n ServeHTTP .", "cat gin.go"))
    def test_canary_transcript_keeps_source_locked_after_unknown_mcp(
        self, tmp_path: Path, command: str
    ):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        transcript = tmp_path / "unknown-before-source.jsonl"
        transcript.write_text(
            "\n".join(
                (
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "call-unknown",
                                "type": "mcp_tool_call",
                                "status": "completed",
                                "server": "tree-sitter-analyzer",
                                "tool": "unknown",
                                "result": {},
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "command": command,
                            },
                        }
                    ),
                )
            )
            + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "tsa-warm",
            expected_tool="nav",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == (
            "CANARY_TOOL_MISMATCH:1",
            "CANARY_SOURCE_DISCOVERY_BEFORE_RECEIPT:2",
            "CANARY_RECEIPT_MISSING",
        )

    @pytest.mark.parametrize(
        "result_error",
        ({"isError": True}, {"error": {"message": "query failed"}}),
    )
    def test_canary_transcript_rejects_nested_error_result_before_source(
        self, tmp_path: Path, result_error: dict
    ):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        result = {**self._tsa_canary_item()["result"], **result_error}
        transcript = tmp_path / "failed-before-source.jsonl"
        transcript.write_text(
            "\n".join(
                (
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "call-failed",
                                "type": "mcp_tool_call",
                                "status": "completed",
                                "server": "tree-sitter-analyzer",
                                "tool": "nav",
                                "result": result,
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "command": "rg -n ServeHTTP .",
                            },
                        }
                    ),
                )
            )
            + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "tsa-warm",
            expected_tool="nav",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == (
            "MCP_CALL_FAILED:1",
            "SOURCE_DISCOVERY_BEFORE_INDEX:2",
            "MISSING_INDEX_QUERY",
            "CANARY_SOURCE_DISCOVERY_BEFORE_RECEIPT:2",
            "CANARY_RECEIPT_MISSING",
        )

    def test_canary_transcript_unlocks_source_after_exact_receipt(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        transcript = tmp_path / "receipt-before-source.jsonl"
        transcript.write_text(
            "\n".join(
                (
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": self._tsa_canary_item(),
                        }
                    ),
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "command": "cat gin.go",
                            },
                        }
                    ),
                )
            )
            + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "tsa-warm",
            expected_tool="nav",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == ()
        assert audit.receipt is not None
        assert audit.receipt.call_id == "call-001"

    @pytest.mark.parametrize(
        ("item", "violation"),
        (
            ({"type": "file_change"}, "FILE_CHANGE:1"),
            (
                {"type": "command_execution", "command": "touch marker"},
                "MUTATING_COMMAND:1",
            ),
            (
                {
                    "type": "command_execution",
                    "command": "tree_sitter_analyzer --outline",
                },
                "INDEX_COMMAND_OUTSIDE_MCP:1",
            ),
            (
                {
                    "type": "command_execution",
                    "command": "sqlite3 .ast-cache/index.db '.tables'",
                },
                "INDEX_NAMESPACE_OUTSIDE_MCP:1",
            ),
            (
                {"type": "command_execution", "command": "cat /etc/hosts"},
                "FILESYSTEM_BOUNDARY_ESCAPE:1",
            ),
            (
                {"type": "command_execution", "command": "ps aux"},
                "FILESYSTEM_BOUNDARY_ESCAPE:1",
            ),
            (
                {
                    "type": "command_execution",
                    "command": "curl https://example.com",
                },
                "NETWORK_COMMAND:1",
            ),
            (
                {"type": "command_execution", "command": "gh api repos/x/y"},
                "UNDECLARED_SHELL_COMMAND:1",
            ),
            (
                {
                    "type": "command_execution",
                    "command": "git -c credential.helper=x fetch origin",
                },
                "NETWORK_COMMAND:1",
            ),
            (
                {
                    "type": "command_execution",
                    "command": "awk 'BEGIN {system(\"curl example.com\")}'",
                },
                "UNDECLARED_SHELL_COMMAND:1",
            ),
            (
                {
                    "type": "command_execution",
                    "command": "find . -exec curl example.com ;",
                },
                "NETWORK_COMMAND:1",
            ),
        ),
    )
    def test_codex_transcript_rejects_non_readonly_events(
        self, tmp_path: Path, item: dict, violation: str
    ):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "forbidden.jsonl"
        transcript.write_text(
            json.dumps({"type": "item.completed", "item": item}),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "native-only")

        assert audit.violations == (violation,)

    @pytest.mark.parametrize(
        "command",
        (
            "find . -name '*.go'",
            "rg -n ServeHTTP .",
            "sed -n '1,40p' gin.go",
            "/bin/bash -lc 'grep -n ServeHTTP gin.go'",
            "/bin/sh -lc \"sed -n '1,40p' gin.go\"",
        ),
    )
    def test_codex_transcript_accepts_declared_readonly_discovery(
        self, tmp_path: Path, command: str
    ):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "readonly.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "command_execution", "command": command},
                }
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "native-only")

        assert audit.violations == ()

    @pytest.mark.parametrize(
        "command",
        (
            "grep -RIn 'http.MethodGet|http.ListenAndServe' .",
            "rg -n 'python|node|curl' README.md",
            "/bin/bash -lc \"grep -n 'func ServeHTTP' gin.go\"",
        ),
    )
    def test_codex_transcript_does_not_treat_search_terms_as_network_commands(
        self, tmp_path: Path, command: str
    ):
        """Regression for the retained NO1-001C false policy failures (#1216)."""
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "source-search.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "command_execution", "command": command},
                }
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "native-only")

        assert audit.violations == ()

    def test_codex_transcript_audits_inside_shell_launcher(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "wrapped-network.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "command": "/bin/bash -lc 'curl https://example.com'",
                    },
                }
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "native-only")

        assert audit.violations == ("NETWORK_COMMAND:1",)

    def test_codex_transcript_audits_literal_newline_commands(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "multiline-network.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "command": "rg -n foo .\ncurl https://example.com",
                    },
                }
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "native-only")

        assert audit.violations == ("NETWORK_COMMAND:1",)

    def test_indexed_arm_rejects_source_discovery_before_mcp(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "mcp-second.jsonl"
        transcript.write_text(
            "\n".join(
                (
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "command": "rg -n ServeHTTP .",
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "mcp_tool_call",
                                "server": "tree-sitter-analyzer",
                                "tool": "search",
                            },
                        }
                    ),
                )
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "tsa-warm")

        assert audit.violations == ("SOURCE_DISCOVERY_BEFORE_INDEX:1",)

    def test_v1_attempt_is_manifest_bound_and_append_only(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_execution import (
            PolicyAudit,
            append_v1_attempt,
            build_v1_attempt,
        )

        manifest = _v1_manifest()
        cell = manifest.expected_cells[0]
        legacy = self._legacy_record(manifest, cell.run_id, tmp_path / "raw.jsonl")
        stats = _v1_run(manifest, cell.run_id).index_stats
        audit = PolicyAudit(
            cell.arm,
            legacy["transcript_path"],
            ("codegraph",),
            ("codegraph_search",),
            (),
        )

        attempt = build_v1_attempt(
            manifest,
            cell,
            legacy,
            index_stats=stats,
            policy_audit=audit,
        )
        path = append_v1_attempt(tmp_path, manifest, attempt, audit)

        persisted = json.loads(path.read_text(encoding="utf-8"))
        assert persisted["experiment_id"] == manifest.experiment_id
        assert persisted["session_id"] == manifest.primary_session_id
        assert persisted["run_id"] == cell.run_id
        assert persisted["status"] == "SUCCESS"
        path.unlink()
        recovered = append_v1_attempt(tmp_path, manifest, attempt, audit)
        assert (
            json.loads(recovered.read_text(encoding="utf-8"))["run_id"] == cell.run_id
        )
        with pytest.raises(ValueError, match="Duplicate physical attempt"):
            append_v1_attempt(tmp_path, manifest, attempt, audit)

    def test_failed_manifest_smoke_records_supported_invalid_registry_status(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.smoke_execution import (
            execute_bound_manifest,
        )

        manifest = _v1_manifest()
        events: list[tuple[str, str]] = []
        monkeypatch.setattr(
            "benchmarks.codegraph_compare.smoke_execution.run_manifest_setup_gate",
            lambda **kwargs: 0,
        )
        monkeypatch.setattr(
            "benchmarks.codegraph_compare.smoke_execution.run_manifest_smoke",
            lambda **kwargs: 1,
        )

        result = execute_bound_manifest(
            manifest=manifest,
            args=SimpleNamespace(),
            supplied_index_stats={},
            workspace=None,
            repo_entries=[],
            arm_entries=[],
            question_entries_by_repo={},
            repeats=1,
            session_id=manifest.primary_session_id,
            results_dir=tmp_path,
            repo_path_resolver=lambda repo: tmp_path,
            append_event=lambda _, status, outcome: events.append((status, outcome)),
            adapter_factory=lambda arm: None,
            run_one=lambda **kwargs: None,
        )

        assert result == 1
        assert events == [
            ("RUNNING", "smoke_started"),
            ("INVALID", "smoke_invalid"),
        ]

    def test_manifest_smoke_retains_exception_and_continues_schedule(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig
        from benchmarks.codegraph_compare.smoke_execution import (
            run_manifest_smoke,
        )

        manifest = _v1_manifest()
        calls = 0

        class Adapter:
            def __init__(self, arm: str) -> None:
                self.arm = arm

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                return RunConfig(self.arm, repo_path, "system")

        def run_one(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("backend crashed")
            cell = manifest.expected_cells[1]
            transcript = tmp_path / "second.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "mcp_tool_call",
                            "server": "tree-sitter-analyzer",
                            "tool": "nav",
                        },
                    }
                ),
                encoding="utf-8",
            )
            return self._legacy_record(manifest, cell.run_id, transcript)

        stats = {
            ("gin", cell.arm): _v1_run(manifest, cell.run_id).index_stats
            for cell in manifest.expected_cells
        }
        result = run_manifest_smoke(
            manifest=manifest,
            repo_entries=[{"id": "gin", "local_path": str(tmp_path)}],
            arm_entries=[
                {"id": "codegraph-warm"},
                {"id": "tsa-warm"},
            ],
            questions_by_repo={"gin": [{"id": "q1", "prompt": "Where is it?"}]},
            supplied_index_stats=stats,
            results_dir=tmp_path / "results",
            workspace=None,
            repo_path_resolver=lambda repo: Path(repo["local_path"]),
            adapter_factory=Adapter,
            run_one=run_one,
        )

        records = [
            json.loads(line)
            for line in (
                tmp_path
                / "results"
                / "experiments"
                / manifest.manifest_hash
                / "runs.jsonl"
            )
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert result == 1
        assert calls == 2
        assert [record["status"] for record in records] == [
            "INVALID",
            "SUCCESS",
        ]
        assert json.loads(
            (
                tmp_path
                / "results"
                / "experiments"
                / manifest.manifest_hash
                / f"policy_{manifest.expected_cells[0].run_id}.json"
            ).read_text(encoding="utf-8")
        )["violations"] == [
            "EXECUTION_EXCEPTION:RuntimeError",
            "TRANSCRIPT_MISSING",
        ]

    def test_manifest_smoke_preserves_completed_evidence_after_index_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from dataclasses import replace

        from benchmarks.codegraph_compare.adapters import RunConfig
        from benchmarks.codegraph_compare.smoke_execution import (
            run_manifest_smoke,
        )
        from benchmarks.codegraph_compare.smoke_workspace import (
            IndexContentDriftError,
        )

        manifest = replace(
            _v1_manifest(),
            index_content_hashes=(
                ("codegraph-warm", "codegraph-index-hash"),
                ("tsa-warm", "tsa-index-hash"),
            ),
        )
        cells = iter(manifest.expected_cells)

        class Adapter:
            def __init__(self, arm: str) -> None:
                self.arm = arm

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                return RunConfig(self.arm, repo_path, "system")

        def run_one(**kwargs):
            cell = next(cells)
            transcript = tmp_path / f"{cell.run_id}.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "mcp_tool_call",
                            "server": (
                                "codegraph"
                                if cell.arm == "codegraph-warm"
                                else "tree-sitter-analyzer"
                            ),
                            "tool": "query",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            record = self._legacy_record(manifest, cell.run_id, transcript)
            record["answer"] = f"completed answer for {cell.arm}"
            record["input_tokens"] = 101
            record["output_tokens"] = 23
            record["total_tokens"] = 124
            record["tool_calls"] = 7
            record["file_reads"] = 3
            record["search_calls"] = 2
            record["index_queries"] = 1
            record["cached_input_tokens"] = 41
            record["reasoning_output_tokens"] = 11
            record["cache_read_tokens"] = 37
            record["cache_creation_tokens"] = 4
            record["total_cost_usd"] = 0.125
            record["estimated_cost_usd"] = 0.25
            record["citations"] = ["gin.go", "tree.go"]
            record["started_at"] = "2026-07-31T01:02:03Z"
            record["ended_at"] = "2026-07-31T01:02:08Z"
            record["elapsed_seconds"] = 5.0
            if cell.arm == "codegraph-warm":
                record["error"] = "provider returned a partial failure"
            return record

        validation_calls = 0

        def validate(*args):
            nonlocal validation_calls
            validation_calls += 1
            if validation_calls == 1:
                raise IndexContentDriftError("index changed after completed model call")
            raise OSError("index digest could not be read")

        workspace_cells = {}
        for arm, index_name in (
            ("codegraph-warm", ".codegraph"),
            ("tsa-warm", ".ast-cache"),
        ):
            checkout_path = tmp_path / "checkouts" / arm
            artifact_path = tmp_path / "artifacts" / arm
            index_path = tmp_path / "frozen-indexes" / arm / index_name
            checkout_path.mkdir(parents=True)
            artifact_path.mkdir(parents=True)
            index_path.mkdir(parents=True)
            workspace_cells[arm] = SimpleNamespace(
                checkout_path=checkout_path,
                artifact_path=artifact_path,
                index_path=index_path,
            )
        workspace = SimpleNamespace(cell=workspace_cells.__getitem__)
        expected_hashes = dict(manifest.index_content_hashes)
        monkeypatch.setattr(
            "benchmarks.codegraph_compare.smoke_execution.index_content_hash",
            lambda path: expected_hashes[
                next(arm for arm in manifest.indexed_arms if arm in path.parts)
            ],
        )
        monkeypatch.setattr(
            "benchmarks.codegraph_compare.smoke_execution.canonical_semantic_digest",
            lambda path: "semantic-digest",
        )

        def materialize(index_path, checkout_path, arm, expected_hash, expected_paths):
            runtime_path = checkout_path / index_path.name
            runtime_path.mkdir()
            return runtime_path

        monkeypatch.setattr(
            "benchmarks.codegraph_compare.smoke_execution.materialize_runtime_index",
            materialize,
        )
        monkeypatch.setattr(
            "benchmarks.codegraph_compare.smoke_execution.audit_runtime_index",
            lambda runtime_path, audit_path, arm, expected_paths: (
                "semantic-digest",
                expected_paths,
            ),
        )
        monkeypatch.setattr(
            "benchmarks.codegraph_compare.smoke_execution.validate_index_content_v1",
            validate,
        )
        stats = {
            ("gin", cell.arm): _v1_run(manifest, cell.run_id).index_stats
            for cell in manifest.expected_cells
        }

        result = run_manifest_smoke(
            manifest=manifest,
            repo_entries=[{"id": "gin", "local_path": str(tmp_path)}],
            arm_entries=[
                {"id": "codegraph-warm"},
                {"id": "tsa-warm"},
            ],
            questions_by_repo={"gin": [{"id": "q1", "prompt": "Where is it?"}]},
            supplied_index_stats=stats,
            results_dir=tmp_path / "results",
            workspace=workspace,
            repo_path_resolver=lambda repo: Path(repo["local_path"]),
            adapter_factory=Adapter,
            run_one=run_one,
        )

        experiment = tmp_path / "results" / "experiments" / manifest.manifest_hash
        first = json.loads(
            (experiment / "runs.jsonl").read_text(encoding="utf-8").splitlines()[0]
        )
        second = json.loads(
            (experiment / "runs.jsonl").read_text(encoding="utf-8").splitlines()[1]
        )
        policy = json.loads(
            (experiment / f"policy_{manifest.expected_cells[0].run_id}.json").read_text(
                encoding="utf-8"
            )
        )
        # Issue #1201: post-run index validation must not erase model evidence.
        assert result == 1
        assert first["answer"] == "completed answer for codegraph-warm"
        assert first["transcript_path"].endswith(
            f"{manifest.expected_cells[0].run_id}.jsonl"
        )
        assert first["input_tokens"] == 101
        assert first["output_tokens"] == 23
        assert first["total_tokens"] == 124
        assert first["tool_calls"] == 7
        assert first["file_reads"] == 3
        assert first["search_calls"] == 2
        assert first["index_queries"] == 1
        assert first["cached_input_tokens"] == 41
        assert first["reasoning_output_tokens"] == 11
        assert first["cache_read_tokens"] == 37
        assert first["cache_creation_tokens"] == 4
        assert first["total_cost_usd"] == 0.125
        assert first["estimated_cost_usd"] == 0.25
        assert first["citations"] == ["gin.go", "tree.go"]
        assert first["started_at"] == "2026-07-31T01:02:03Z"
        assert first["ended_at"] == "2026-07-31T01:02:08Z"
        assert first["elapsed_seconds"] == 5.0
        assert first["status"] == "INVALID"
        assert first["blocker_reason"] == (
            "POLICY_AUDIT:INDEX_CONTENT_DRIFT;"
            "PRODUCT_FAILURE:provider returned a partial failure"
        )
        assert policy["violations"] == ["INDEX_CONTENT_DRIFT"]
        assert second["status"] == "INVALID"
        assert second["blocker_reason"] == "POLICY_AUDIT:EXECUTION_EXCEPTION:OSError"


class TestGinSmokeIndexEvidence:
    def test_go_eligibility_excludes_generated_files(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_evidence import classify_go_paths

        (tmp_path / "gin.go").write_text("package gin\n", encoding="utf-8")
        generated = tmp_path / "test.pb.go"
        generated.write_text(
            "// Code generated by protoc-gen-go. DO NOT EDIT.\npackage gin\n",
            encoding="utf-8",
        )

        eligible, excluded = classify_go_paths(tmp_path, ("gin.go", "test.pb.go"))

        assert eligible == ("gin.go",)
        assert excluded == ("test.pb.go",)

    def test_masked_paths_restore_exclusions_after_failure(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_evidence import masked_paths

        generated = tmp_path / "testdata" / "test.pb.go"
        generated.parent.mkdir()
        generated.write_text("generated", encoding="utf-8")

        with pytest.raises(RuntimeError, match="index failed"):
            with masked_paths(tmp_path, ("testdata/test.pb.go",)):
                assert not generated.exists()
                raise RuntimeError("index failed")

        assert generated.read_text(encoding="utf-8") == "generated"

    def test_index_stats_reject_paths_outside_frozen_eligibility(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import IndexStats
        from benchmarks.codegraph_compare.smoke_evidence import _build_stats

        cache = tmp_path / ".ast-cache"
        cache.mkdir()
        connection = sqlite3.connect(cache / "index.db")
        connection.execute("CREATE TABLE ast_index (file_path TEXT, symbols_json TEXT)")
        connection.executemany(
            "INSERT INTO ast_index VALUES (?, ?)",
            (("gin.go", "ServeHTTP"), ("unexpected.go", "{}")),
        )
        connection.commit()
        connection.close()
        monkeypatch.setattr(
            "benchmarks.codegraph_compare.smoke_evidence.TSAAdapter.prepare_index",
            lambda self, repo_path, cold: IndexStats(1.0, 10, 2),
        )

        with pytest.raises(
            ValueError,
            match=r"unexpected=\('unexpected.go',\)",
        ):
            _build_stats(
                repo_path=tmp_path,
                arm="tsa-warm",
                eligible_paths=("gin.go",),
                generated_paths=(),
                repo_fingerprint="repo",
                tool_fingerprint="tool",
            )


class TestGinSmokeWorkspace:
    def test_freeze_index_baselines_moves_indexes_out_of_checkouts(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.smoke_plan import freeze_index_baselines

        checkouts = {}
        for arm, name in (
            ("tsa-warm", ".ast-cache"),
            ("codegraph-warm", ".codegraph"),
        ):
            checkout = tmp_path / "checkouts" / arm / "gin"
            index = checkout / name
            index.mkdir(parents=True)
            database_name = "index.db" if arm == "tsa-warm" else "codegraph.db"
            connection = sqlite3.connect(index / database_name)
            if arm == "tsa-warm":
                connection.execute(
                    "CREATE TABLE ast_index(file_path TEXT, symbols_json TEXT)"
                )
                connection.execute(
                    "INSERT INTO ast_index VALUES ('gin.go', 'ServeHTTP')"
                )
            else:
                connection.execute("CREATE TABLE nodes(file_path TEXT, name TEXT)")
                connection.execute("INSERT INTO nodes VALUES ('gin.go', 'ServeHTTP')")
            connection.commit()
            connection.close()
            checkouts[arm] = checkout

        frozen = freeze_index_baselines(
            checkouts,
            tmp_path / "checkouts",
            {"tsa-warm": ("gin.go",), "codegraph-warm": ("gin.go",)},
        )

        assert tuple(sorted(frozen)) == ("codegraph-warm", "tsa-warm")
        assert tuple(
            (checkouts[arm] / name).exists()
            for arm, name in (
                ("tsa-warm", ".ast-cache"),
                ("codegraph-warm", ".codegraph"),
            )
        ) == (False, False)
        assert tuple(path.parent.parent.name for path in frozen.values()) == (
            "frozen-indexes",
            "frozen-indexes",
        )

    @staticmethod
    def _fixture(tmp_path: Path):
        from dataclasses import replace

        from benchmarks.codegraph_compare.integrity import (
            ExpectedCellV1,
            _manifest_payload,
            _sha256,
            create_manifest,
        )
        from benchmarks.codegraph_compare.smoke_evidence import (
            index_content_hash,
            repository_fingerprint,
            tracked_paths,
        )
        from benchmarks.codegraph_compare.smoke_workspace import (
            parse_workspace_v1,
        )

        source = tmp_path / "source"
        source.mkdir()
        (source / "gin.go").write_text("package gin\n", encoding="utf-8")
        generated = source / "testdata" / "test.pb.go"
        generated.parent.mkdir()
        generated.write_text(
            "// Code generated by test. DO NOT EDIT.\npackage testdata\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q"], cwd=source, check=True)
        subprocess.run(
            ["git", "config", "user.email", "benchmark@example.invalid"],
            cwd=source,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Benchmark Test"],
            cwd=source,
            check=True,
        )
        subprocess.run(["git", "add", "."], cwd=source, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=source, check=True)
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=source,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        fingerprint = repository_fingerprint(source, tracked_paths(source))
        arms = ("native-only", "tsa-warm", "codegraph-warm")
        cells = tuple(
            ExpectedCellV1(
                repo="gin",
                question_id="q1",
                arm=arm,
                repeat=0,
                agent_backend="codex",
                run_id=f"q1__{arm}__codex__00",
            )
            for arm in arms
        )
        manifest = create_manifest(
            benchmark_git_sha="benchmark-sha",
            config_hash="config-hash",
            question_hash="question-hash",
            oracle_hash="oracle-hash",
            seed=210021,
            timeout_seconds=1200,
            schedule_hash="schedule-hash",
            agent_backend="codex",
            model="gpt-5",
            agent_cli_fingerprint="codex-cli",
            platform="linux-x86_64",
            environment_fingerprint="environment",
            primary_session_id="PRIMARY",
            retry_session_ids=(),
            expected_cells=cells,
            required_arms=arms,
            indexed_arms=("tsa-warm", "codegraph-warm"),
            tool_fingerprints=dict.fromkeys(arms, "tool"),
            repo_commits={"gin": commit},
            repo_fingerprints={"gin": fingerprint},
            eligible_paths={"gin": ("gin.go",)},
            eligible_paths_hashes={"gin": _v1_paths_hash(("gin.go",))},
            parse_error_allowlists={"gin": ()},
            required_readiness_oracles={
                "tsa-warm": ("known-symbol",),
                "codegraph-warm": ("known-symbol",),
            },
        )
        raw_cells = []
        for arm in arms:
            checkout = tmp_path / "checkouts" / arm / "gin"
            checkout.parent.mkdir(parents=True)
            subprocess.run(
                ["git", "clone", "-q", str(source), str(checkout)], check=True
            )
            index_path = None
            if arm == "tsa-warm":
                index_path = tmp_path / "frozen-indexes" / arm / ".ast-cache"
                index_path.parent.mkdir(parents=True)
                index_path.mkdir()
                (index_path / "index.db").write_bytes(b"tsa")
            elif arm == "codegraph-warm":
                index_path = tmp_path / "frozen-indexes" / arm / ".codegraph"
                index_path.parent.mkdir(parents=True)
                index_path.mkdir()
                (index_path / "codegraph.db").write_bytes(b"codegraph")
            artifact = tmp_path / "artifacts" / arm
            artifact.mkdir(parents=True)
            raw_cells.append(
                {
                    "arm_id": arm,
                    "checkout_path": str(checkout),
                    "index_path": str(index_path) if index_path else None,
                    "artifact_path": str(artifact),
                }
            )
        raw = {
            "schema_version": 1,
            "experiment_id": manifest.experiment_id,
            "manifest_hash": manifest.manifest_hash,
            "cells": raw_cells,
        }
        manifest = replace(
            manifest,
            index_content_hashes=tuple(
                (cell["arm_id"], index_content_hash(Path(cell["index_path"])))
                for cell in raw_cells
                if cell["index_path"] is not None
            ),
        )
        manifest = replace(
            manifest,
            manifest_hash=_sha256(_manifest_payload(manifest)),
        )
        manifest = replace(manifest, experiment_id=f"sha256:{manifest.manifest_hash}")
        raw["experiment_id"] = manifest.experiment_id
        raw["manifest_hash"] = manifest.manifest_hash
        return manifest, raw, parse_workspace_v1(raw)

    def test_workspace_accepts_three_independent_clean_checkouts(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            validate_workspace_v1,
        )

        manifest, _, workspace = self._fixture(tmp_path)

        validate_workspace_v1(workspace, manifest)

    def test_workspace_rejects_frozen_index_inside_checkout(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import validate_workspace_v1

        manifest, _, workspace = self._fixture(tmp_path)
        cell = workspace.cell("tsa-warm")
        object.__setattr__(cell, "index_path", cell.checkout_path)

        with pytest.raises(ValueError, match="frozen index overlaps checkout"):
            validate_workspace_v1(workspace, manifest)

    def test_workspace_rejects_existing_runtime_index(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import validate_workspace_v1

        manifest, _, workspace = self._fixture(tmp_path)
        (workspace.cell("tsa-warm").checkout_path / ".ast-cache").mkdir()

        with pytest.raises(ValueError, match="runtime index already exists"):
            validate_workspace_v1(workspace, manifest)

    def test_workspace_rejects_frozen_index_inside_artifact(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import validate_workspace_v1

        manifest, _, workspace = self._fixture(tmp_path)
        cell = workspace.cell("tsa-warm")
        object.__setattr__(cell, "index_path", cell.artifact_path)

        with pytest.raises(ValueError, match="frozen index overlaps artifact"):
            validate_workspace_v1(workspace, manifest)

    def test_workspace_rejects_hardlinked_frozen_index_file(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import validate_workspace_v1

        manifest, _, workspace = self._fixture(tmp_path)
        index = workspace.cell("tsa-warm").index_path
        expected_index = tmp_path / "frozen-indexes" / "tsa-warm" / ".ast-cache"
        assert index == expected_index
        (tmp_path / "alias.db").hardlink_to(expected_index / "index.db")

        with pytest.raises(ValueError, match="hardlinked file"):
            validate_workspace_v1(workspace, manifest)

    def test_snapshot_includes_committed_wal_with_open_writer(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            create_frozen_index_snapshot,
        )

        baseline = tmp_path / "baseline" / ".codegraph"
        baseline.mkdir(parents=True)
        connection = sqlite3.connect(baseline / "codegraph.db")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE nodes (file_path TEXT, name TEXT)")
        connection.execute("INSERT INTO nodes VALUES ('gin.go', 'ServeHTTP')")
        connection.commit()
        assert ((baseline / "codegraph.db-wal").stat().st_size == 0) is False
        frozen = create_frozen_index_snapshot(
            baseline,
            tmp_path / "frozen" / ".codegraph",
            "codegraph-warm",
            ("gin.go",),
        )
        connection.close()
        assert sqlite3.connect(frozen / "codegraph.db").execute(
            "SELECT file_path, name FROM nodes"
        ).fetchone() == ("gin.go", "ServeHTTP")

    def test_snapshot_excludes_uncommitted_rows(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            create_frozen_index_snapshot,
        )

        source = tmp_path / "live" / ".codegraph"
        source.mkdir(parents=True)
        writer = sqlite3.connect(source / "codegraph.db")
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE nodes(file_path TEXT, name TEXT)")
        writer.execute("INSERT INTO nodes VALUES ('gin.go', 'ServeHTTP')")
        writer.commit()
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO nodes VALUES ('secret.go', 'Uncommitted')")
        try:
            frozen = create_frozen_index_snapshot(
                source,
                tmp_path / "frozen" / ".codegraph",
                "codegraph-warm",
                ("gin.go",),
            )
        finally:
            writer.rollback()
            writer.close()
        assert sqlite3.connect(frozen / "codegraph.db").execute(
            "SELECT file_path FROM nodes ORDER BY file_path"
        ).fetchall() == [("gin.go",)]

    def test_snapshot_rejects_multiple_primary_databases(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            create_frozen_index_snapshot,
        )

        source = tmp_path / "live" / ".codegraph"
        source.mkdir(parents=True)
        sqlite3.connect(source / "codegraph.db").close()
        sqlite3.connect(source / "extra.db").close()
        with pytest.raises(ValueError, match="undeclared SQLite database: extra.db"):
            create_frozen_index_snapshot(
                source, tmp_path / "frozen", "codegraph-warm", ()
            )

    @pytest.mark.parametrize(
        ("relative", "message"),
        (
            ("nested/extra.db", "undeclared SQLite database"),
            ("nested/codegraph.db", "undeclared SQLite database"),
            ("nested/codegraph.db-wal", "undeclared SQLite sidecar"),
        ),
    )
    def test_snapshot_rejects_nested_sqlite_artifact(
        self, tmp_path: Path, relative: str, message: str
    ):
        from benchmarks.codegraph_compare.smoke_workspace import (
            create_frozen_index_snapshot,
        )

        source = tmp_path / "live" / ".codegraph"
        source.mkdir(parents=True)
        connection = sqlite3.connect(source / "codegraph.db")
        connection.execute("CREATE TABLE nodes(file_path TEXT, name TEXT)")
        connection.execute("INSERT INTO nodes VALUES ('gin.go', 'ServeHTTP')")
        connection.commit()
        connection.close()
        artifact = source / relative
        artifact.parent.mkdir()
        artifact.write_bytes(b"foreign")
        with pytest.raises(ValueError, match=message):
            create_frozen_index_snapshot(
                source, tmp_path / "frozen", "codegraph-warm", ("gin.go",)
            )

    def test_snapshot_rejects_evidence_path_mismatch(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            create_frozen_index_snapshot,
        )

        source = tmp_path / "live" / ".codegraph"
        source.mkdir(parents=True)
        connection = sqlite3.connect(source / "codegraph.db")
        connection.execute("CREATE TABLE nodes(file_path TEXT, name TEXT)")
        connection.execute("INSERT INTO nodes VALUES ('gin.go', 'ServeHTTP')")
        connection.commit()
        connection.close()
        with pytest.raises(ValueError, match="paths do not match index evidence"):
            create_frozen_index_snapshot(
                source, tmp_path / "frozen", "codegraph-warm", ("other.go",)
            )

    def test_snapshot_oracle_creates_no_sqlite_sidecars(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            create_frozen_index_snapshot,
        )

        source = tmp_path / "live" / ".codegraph"
        source.mkdir(parents=True)
        connection = sqlite3.connect(source / "codegraph.db")
        connection.execute("CREATE TABLE nodes(file_path TEXT, name TEXT)")
        connection.execute("INSERT INTO nodes VALUES ('gin.go', 'ServeHTTP')")
        connection.commit()
        connection.close()
        frozen = create_frozen_index_snapshot(
            source, tmp_path / "frozen" / ".codegraph", "codegraph-warm", ("gin.go",)
        )
        assert tuple(sorted(path.name for path in frozen.iterdir())) == (
            "codegraph.db",
        )

    def test_snapshot_closes_oracle_connection_before_publish(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # PR #1213: Windows refuses to rename a directory containing an open DB.
        from benchmarks.codegraph_compare import smoke_evidence

        source = tmp_path / "live" / ".codegraph"
        source.mkdir(parents=True)
        connection = sqlite3.connect(source / "codegraph.db")
        connection.execute("CREATE TABLE nodes(file_path TEXT, name TEXT)")
        connection.execute("INSERT INTO nodes VALUES ('gin.go', 'ServeHTTP')")
        connection.commit()
        connection.close()

        original_connect = smoke_evidence.sqlite3.connect
        oracle_connections = []

        class TrackingConnection:
            def __init__(self, wrapped):
                self.wrapped = wrapped
                self.closed = False

            def __getattr__(self, name):
                return getattr(self.wrapped, name)

            def __enter__(self):
                self.wrapped.__enter__()
                return self

            def __exit__(self, *args):
                return self.wrapped.__exit__(*args)

            def close(self):
                self.closed = True
                self.wrapped.close()

        def track_connect(database, *args, **kwargs):
            tracked = TrackingConnection(original_connect(database, *args, **kwargs))
            oracle_connections.append(tracked)
            return tracked

        monkeypatch.setattr(smoke_evidence.sqlite3, "connect", track_connect)

        observed = smoke_evidence.inspect_frozen_index("codegraph-warm", source)

        assert observed == ("gin.go",)
        assert tuple(item.closed for item in oracle_connections) == (True,)

    def test_materialize_uses_fixed_arm_oracle_and_distinct_copy(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_evidence import index_content_hash
        from benchmarks.codegraph_compare.smoke_workspace import (
            create_frozen_index_snapshot,
            materialize_runtime_index,
        )

        source = tmp_path / "live" / ".codegraph"
        source.mkdir(parents=True)
        connection = sqlite3.connect(source / "codegraph.db")
        connection.execute("CREATE TABLE nodes(file_path TEXT, name TEXT)")
        connection.execute("INSERT INTO nodes VALUES ('gin.go', 'ServeHTTP')")
        connection.commit()
        connection.close()
        frozen = create_frozen_index_snapshot(
            source, tmp_path / "frozen" / ".codegraph", "codegraph-warm", ("gin.go",)
        )
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        runtime = materialize_runtime_index(
            frozen, checkout, "codegraph-warm", index_content_hash(frozen), ("gin.go",)
        )
        assert (
            (frozen / "codegraph.db").stat().st_ino
            == (runtime / "codegraph.db").stat().st_ino
        ) is False

    def test_freeze_rolls_back_both_live_indexes_when_second_rename_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from benchmarks.codegraph_compare.smoke_plan import freeze_index_baselines

        checkouts = self._indexed_checkout_pair(tmp_path)
        original = Path.rename

        def fail_second(path: Path, target: Path):
            if path.name == ".codegraph" and target.name.endswith("freeze-quarantine"):
                raise OSError("rename failed")
            return original(path, target)

        monkeypatch.setattr(Path, "rename", fail_second)
        with pytest.raises(OSError, match="rename failed"):
            freeze_index_baselines(
                checkouts,
                tmp_path / "checkouts",
                {"tsa-warm": ("gin.go",), "codegraph-warm": ("gin.go",)},
            )
        assert tuple(
            (checkouts[arm] / name).is_dir()
            for arm, name in (
                ("tsa-warm", ".ast-cache"),
                ("codegraph-warm", ".codegraph"),
            )
        ) == (True, True)
        assert tuple((tmp_path / "checkouts").rglob("*.freeze-quarantine")) == ()
        assert tuple((tmp_path / "checkouts" / "frozen-indexes").rglob("*.db")) == ()

    def test_freeze_cleanup_failure_preserves_frozen_authority(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from benchmarks.codegraph_compare.smoke_plan import freeze_index_baselines

        checkouts = self._indexed_checkout_pair(tmp_path)
        original = shutil.rmtree

        def fail_quarantine(path: Path, *args, **kwargs):
            if Path(path).name == ".codegraph.freeze-quarantine":
                raise OSError("cleanup failed")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(shutil, "rmtree", fail_quarantine)
        with pytest.raises(RuntimeError, match="frozen authority"):
            freeze_index_baselines(
                checkouts,
                tmp_path / "checkouts",
                {"tsa-warm": ("gin.go",), "codegraph-warm": ("gin.go",)},
            )
        assert tuple(
            sorted(
                path.name
                for path in (tmp_path / "checkouts" / "frozen-indexes").rglob("*.db")
            )
        ) == ("codegraph.db", "index.db")
        assert (
            checkouts["codegraph-warm"] / ".codegraph.freeze-quarantine"
        ).is_dir() is True

    @staticmethod
    def _indexed_checkout_pair(tmp_path: Path) -> dict[str, Path]:
        checkouts = {}
        for arm, index_name, database_name in (
            ("tsa-warm", ".ast-cache", "index.db"),
            ("codegraph-warm", ".codegraph", "codegraph.db"),
        ):
            checkout = tmp_path / "checkouts" / arm / "gin"
            index = checkout / index_name
            index.mkdir(parents=True)
            connection = sqlite3.connect(index / database_name)
            if arm == "tsa-warm":
                connection.execute(
                    "CREATE TABLE ast_index(file_path TEXT, symbols_json TEXT)"
                )
                connection.execute(
                    "INSERT INTO ast_index VALUES ('gin.go', 'ServeHTTP')"
                )
            else:
                connection.execute("CREATE TABLE nodes(file_path TEXT, name TEXT)")
                connection.execute("INSERT INTO nodes VALUES ('gin.go', 'ServeHTTP')")
            connection.commit()
            connection.close()
            checkouts[arm] = checkout
        return checkouts

    def test_cleanup_runtime_index_rejects_path_escape(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import cleanup_runtime_index

        checkout = tmp_path / "checkout"
        checkout.mkdir()
        outside = tmp_path / ".ast-cache"
        outside.mkdir()

        with pytest.raises(ValueError, match="runtime cleanup target mismatch"):
            cleanup_runtime_index(checkout, ".ast-cache", outside)

    def test_cleanup_runtime_index_removes_exact_runtime_tree(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import cleanup_runtime_index

        checkout = tmp_path / "checkout"
        runtime = checkout / ".ast-cache"
        runtime.mkdir(parents=True)
        (runtime / "index.db").write_bytes(b"index")

        cleanup_runtime_index(checkout, ".ast-cache", runtime)

        assert runtime.exists() is False

    @pytest.mark.parametrize(
        "target_kind", ("dotdot", "broken_symlink", "checkout", "baseline", "root")
    )
    def test_cleanup_rejects_unsafe_target(self, tmp_path: Path, target_kind: str):
        from benchmarks.codegraph_compare.smoke_workspace import cleanup_runtime_index

        checkout = tmp_path / "checkout"
        checkout.mkdir()
        baseline = tmp_path / "baseline"
        baseline.mkdir()
        targets = {
            "dotdot": checkout / ".." / ".ast-cache",
            "broken_symlink": checkout / ".ast-cache",
            "checkout": checkout,
            "baseline": baseline,
            "root": Path("/"),
        }
        target = targets[target_kind]
        if target_kind == "broken_symlink":
            target.symlink_to(tmp_path / "missing")
        with pytest.raises(ValueError, match="runtime cleanup"):
            cleanup_runtime_index(checkout, ".ast-cache", target)

    def test_workspace_rejects_cross_arm_artifact_collision(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            parse_workspace_v1,
            validate_workspace_v1,
        )

        manifest, raw, _ = self._fixture(tmp_path)
        raw["cells"][1]["artifact_path"] = raw["cells"][0]["artifact_path"]

        with pytest.raises(ValueError, match="artifact namespace collision"):
            validate_workspace_v1(parse_workspace_v1(raw), manifest)

    def test_workspace_rejects_foreign_index_in_native_checkout(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            validate_workspace_v1,
        )

        manifest, _, workspace = self._fixture(tmp_path)
        (workspace.cell("native-only").checkout_path / ".codegraph").mkdir()

        with pytest.raises(ValueError, match="foreign index namespace"):
            validate_workspace_v1(workspace, manifest)

    def test_workspace_rejects_untracked_checkout_input(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            validate_workspace_v1,
        )

        manifest, _, workspace = self._fixture(tmp_path)
        (workspace.cell("native-only").checkout_path / "misleading.md").write_text(
            "not part of the pinned repository\n", encoding="utf-8"
        )

        with pytest.raises(ValueError, match="unprovenanced paths"):
            validate_workspace_v1(workspace, manifest)

    def test_workspace_rejects_symlinked_index_namespace(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            parse_workspace_v1,
            validate_workspace_v1,
        )

        manifest, raw, workspace = self._fixture(tmp_path)
        tsa_index = workspace.cell("tsa-warm").index_path
        assert tsa_index.name == ".ast-cache"
        (tsa_index / "index.db").unlink()
        tsa_index.rmdir()
        external = tmp_path / "shared-index"
        external.mkdir()
        tsa_index.symlink_to(external, target_is_directory=True)
        raw["cells"][1]["index_path"] = str(tsa_index)

        with pytest.raises(ValueError, match="index namespace contains a symlink"):
            validate_workspace_v1(parse_workspace_v1(raw), manifest)

    def test_workspace_rejects_symlinked_ancestor(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            parse_workspace_v1,
            validate_workspace_v1,
        )

        manifest, raw, workspace = self._fixture(tmp_path)
        checkout = workspace.cell("native-only").checkout_path
        alias = tmp_path / "checkout-alias"
        alias.symlink_to(checkout.parent, target_is_directory=True)
        raw["cells"][0]["checkout_path"] = str(alias / checkout.name)

        with pytest.raises(ValueError, match="contains a symlink"):
            validate_workspace_v1(parse_workspace_v1(raw), manifest)

    def test_workspace_rejects_symlink_nested_in_index(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            validate_workspace_v1,
        )

        manifest, _, workspace = self._fixture(tmp_path)
        index = workspace.cell("tsa-warm").index_path
        assert index.name == ".ast-cache"
        (index / "external.db").symlink_to(tmp_path / "outside.db")

        with pytest.raises(ValueError, match="contains a special node"):
            validate_workspace_v1(workspace, manifest)

    def test_workspace_rejects_index_content_not_bound_to_manifest(
        self, tmp_path: Path
    ):
        from dataclasses import replace

        from benchmarks.codegraph_compare.smoke_evidence import (
            index_content_hash,
        )
        from benchmarks.codegraph_compare.smoke_workspace import (
            validate_index_content_v1,
            validate_workspace_v1,
        )

        manifest, _, workspace = self._fixture(tmp_path)
        tsa_index = workspace.cell("tsa-warm").index_path
        codegraph_index = workspace.cell("codegraph-warm").index_path
        assert tsa_index.name == ".ast-cache"
        assert codegraph_index.name == ".codegraph"
        hashes = tuple(
            (
                arm,
                index_content_hash(index),
            )
            for arm, index in (
                ("tsa-warm", tsa_index),
                ("codegraph-warm", codegraph_index),
            )
        )
        bound_manifest = replace(manifest, index_content_hashes=hashes)
        validate_workspace_v1(workspace, bound_manifest)
        (tsa_index / "tampered.db").write_bytes(b"foreign index bytes")

        with pytest.raises(ValueError, match="index content hash mismatch"):
            validate_workspace_v1(workspace, bound_manifest)

        with pytest.raises(ValueError, match="index content hash mismatch"):
            validate_index_content_v1(workspace, bound_manifest, "tsa-warm")

    def test_workspace_schema_rejects_unknown_fields(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            parse_workspace_v1,
        )

        _, raw, _ = self._fixture(tmp_path)
        raw["undeclared"] = True

        with pytest.raises(ValueError, match="workspace keys mismatch"):
            parse_workspace_v1(raw)


class TestGinSmokeBundle:
    @staticmethod
    def _bundle_inputs(tmp_path: Path):
        from dataclasses import asdict

        from benchmarks.codegraph_compare.integrity import RegistryEvent
        from benchmarks.codegraph_compare.smoke_policy import PolicyAudit

        manifest = _v1_manifest(
            index_content_hashes={
                "codegraph-warm": "codegraph-index-hash",
                "tsa-warm": "tsa-index-hash",
            },
        )
        plan = tmp_path / "plan-source"
        plan.mkdir()
        (plan / "experiment-manifest.json").write_text(
            json.dumps(asdict(manifest)), encoding="utf-8"
        )
        from benchmarks.codegraph_compare.smoke_preflight import SENTINEL

        (plan / "model-preflight.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "PASSED",
                    "provider": "OpenAI",
                    "account_surface": "ChatGPT",
                    "model": manifest.model,
                    "checked_at": "2026-07-31T00:00:00+00:00",
                    "agent_cli": {},
                    "agent_cli_fingerprint": manifest.agent_cli_fingerprint,
                    "sentinel_sha256": hashlib.sha256(SENTINEL.encode()).hexdigest(),
                }
            ),
            encoding="utf-8",
        )
        (plan / "arm-tool-preflight.json").write_text(
            json.dumps(
                {
                    arm: {
                        "server": server,
                        "enabled": True,
                        "command": sys.executable,
                        "args": ["serve", "--mcp"],
                    }
                    for arm, server in {
                        "tsa-warm": "tree-sitter-analyzer",
                        "codegraph-warm": "codegraph",
                    }.items()
                }
            ),
            encoding="utf-8",
        )
        for name in (
            "eligibility.json",
            "index-evidence.json",
            "workspace-evidence.json",
        ):
            (plan / name).write_text("{}\n", encoding="utf-8")
        experiment = tmp_path / "experiment"
        experiment.mkdir()
        runs = []
        servers = {
            "codegraph-warm": "codegraph",
            "tsa-warm": "tree-sitter-analyzer",
        }
        for cell in manifest.expected_cells:
            transcript_path = f"/original/{cell.run_id}.jsonl"
            transcript = (
                plan / "artifacts" / cell.arm / "raw" / Path(transcript_path).name
            )
            transcript.parent.mkdir(parents=True)
            transcript.write_text(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "mcp_tool_call",
                            "server": servers[cell.arm],
                            "tool": "query",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            run = _v1_run(manifest, cell.run_id, transcript_path=transcript_path)
            runs.append(run)
            (experiment / f"policy_{cell.run_id}.json").write_text(
                json.dumps(
                    asdict(
                        PolicyAudit(
                            cell.arm,
                            transcript_path,
                            (servers[cell.arm],),
                            ("query",),
                            (),
                        )
                    )
                )
                + "\n",
                encoding="utf-8",
            )
        (experiment / "runs.jsonl").write_text(
            "".join(json.dumps(asdict(run)) + "\n" for run in runs),
            encoding="utf-8",
        )
        registry = tmp_path / "registry.jsonl"
        events = (
            RegistryEvent(
                manifest.experiment_id,
                manifest.manifest_hash,
                "RUNNING",
                "smoke_started",
            ),
            RegistryEvent(
                manifest.experiment_id,
                manifest.manifest_hash,
                "INVALID",
                "smoke_invalid",
            ),
        )
        registry.write_text(
            "".join(json.dumps(asdict(event)) + "\n" for event in events),
            encoding="utf-8",
        )
        return plan, experiment, registry

    def test_bundle_recomputes_invalid_claim_bounded_verdict(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_bundle import (
            create_smoke_bundle,
            validate_smoke_bundle,
        )

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        bundle = tmp_path / "bundle"
        digest = create_smoke_bundle(
            bundle,
            plan_dir=plan,
            experiment_dir=experiment,
            registry_path=registry,
        )

        verdict = validate_smoke_bundle(bundle, external_digest=digest)

        assert verdict["claim_level"] == "INVALID"
        assert verdict["dominance_allowed"] is False
        assert verdict["winner"] is None

    def test_bundle_rejects_orphan_runtime_evidence(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_bundle import create_smoke_bundle

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        (experiment / "runtime_index_unknown-run.json").write_text(
            "{}\n", encoding="utf-8"
        )

        # Issue #1219: every retained runtime audit must bind to an exact run.
        with pytest.raises(ValueError, match="runtime evidence inventory mismatch"):
            create_smoke_bundle(
                tmp_path / "bundle",
                plan_dir=plan,
                experiment_dir=experiment,
                registry_path=registry,
            )

    def test_bundle_accepts_bound_legacy_terminal_exception(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_bundle import create_smoke_bundle

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        runs_path = experiment / "runs.jsonl"
        runs = [
            json.loads(line)
            for line in runs_path.read_text(encoding="utf-8").splitlines()
        ]
        run = runs[0]
        violations = [
            "EXECUTION_EXCEPTION:ValueError",
            "TRANSCRIPT_MISSING",
        ]
        run["status"] = "INVALID"
        run["answer"] = "ERROR"
        run["transcript_path"] = ""
        run["blocker_reason"] = "POLICY_AUDIT:" + ",".join(violations)
        runs_path.write_text(
            "".join(json.dumps(item) + "\n" for item in runs),
            encoding="utf-8",
        )
        policy_path = experiment / f"policy_{run['run_id']}.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["transcript_path"] = ""
        policy["observed_mcp_servers"] = []
        policy["observed_mcp_tools"] = []
        policy["violations"] = violations
        policy_path.write_text(json.dumps(policy) + "\n", encoding="utf-8")
        # Issue #1201: immutable INVALID evidence predates transcript retention.
        digest = create_smoke_bundle(
            tmp_path / "bundle",
            plan_dir=plan,
            experiment_dir=experiment,
            registry_path=registry,
        )

        assert len(digest) == 64

    def test_bundle_accepts_evidence_fallback_after_runtime_failure(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.smoke_bundle import create_smoke_bundle

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        runs_path = experiment / "runs.jsonl"
        runs = [
            json.loads(line)
            for line in runs_path.read_text(encoding="utf-8").splitlines()
        ]
        run = runs[0]
        violations = ["EVIDENCE_EXCEPTION:ValueError", "TRANSCRIPT_MISSING"]
        run["status"] = "INVALID"
        run["answer"] = "ERROR"
        run["transcript_path"] = ""
        run["blocker_reason"] = "POLICY_AUDIT:" + ",".join(violations)
        runs_path.write_text(
            "".join(json.dumps(item) + "\n" for item in runs), encoding="utf-8"
        )
        policy_path = experiment / f"policy_{run['run_id']}.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy.update(
            transcript_path="",
            observed_mcp_servers=[],
            observed_mcp_tools=[],
            violations=violations,
        )
        policy_path.write_text(json.dumps(policy) + "\n", encoding="utf-8")
        manifest = json.loads((plan / "experiment-manifest.json").read_text())
        expected_hash = dict(manifest["index_content_hashes"])[run["arm"]]
        expected_paths = run["index_stats"]["indexed_paths"]
        (experiment / f"runtime_index_{run['run_id']}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "experiment_id": run["experiment_id"],
                    "manifest_hash": manifest["manifest_hash"],
                    "session_id": run["session_id"],
                    "run_id": run["run_id"],
                    "repo": run["repo"],
                    "arm": run["arm"],
                    "repeat": run["repeat"],
                    "expected_hash": expected_hash,
                    "expected_paths": expected_paths,
                    "failure_codes": ["RUNTIME_SEMANTIC_DRIFT"],
                    "materialized": True,
                    "runtime_hash_before": expected_hash,
                    "runtime_hash_after": expected_hash,
                    "runtime_mutated": False,
                    "semantic_digest_before": "before-digest",
                    "semantic_digest_after": "after-digest",
                    "post_paths": expected_paths,
                    "frozen_hash_after": expected_hash,
                    "cleanup_status": "SUCCESS",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        # Issue #1219: evidence fallback replaces the earlier runtime policy audit.
        digest = create_smoke_bundle(
            tmp_path / "bundle",
            plan_dir=plan,
            experiment_dir=experiment,
            registry_path=registry,
        )

        assert len(digest) == 64

        runtime_path = experiment / f"runtime_index_{run['run_id']}.json"
        valid_runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        for name, mutation, message in (
            ("wrong-paths", {"expected_paths": ["unrelated.go"]}, "path mismatch"),
            (
                "wrong-baseline",
                {"runtime_hash_before": "wrong"},
                "measurement mismatch",
            ),
            ("wrong-mutated", {"runtime_mutated": True}, "measurement mismatch"),
        ):
            runtime_path.write_text(
                json.dumps({**valid_runtime, **mutation}) + "\n", encoding="utf-8"
            )
            with pytest.raises(ValueError, match=message):
                create_smoke_bundle(
                    tmp_path / f"bundle-{name}",
                    plan_dir=plan,
                    experiment_dir=experiment,
                    registry_path=registry,
                )

    def test_bundle_accepts_runtime_marker_with_product_failure(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_bundle import create_smoke_bundle

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        runs_path = experiment / "runs.jsonl"
        runs = [
            json.loads(line)
            for line in runs_path.read_text(encoding="utf-8").splitlines()
        ]
        run = runs[0]
        policy_path = experiment / f"policy_{run['run_id']}.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        marker = "RUNTIME_CLEANUP_FAILED:OSError"
        policy["violations"] = [marker, *policy["violations"]]
        policy_path.write_text(json.dumps(policy) + "\n", encoding="utf-8")
        run["status"] = "INVALID"
        run["blocker_reason"] = (
            "POLICY_AUDIT:"
            + ",".join(policy["violations"])
            + ";PRODUCT_FAILURE:backend unavailable"
        )
        runs_path.write_text(
            "".join(json.dumps(item) + "\n" for item in runs), encoding="utf-8"
        )
        manifest = json.loads((plan / "experiment-manifest.json").read_text())
        expected_hash = dict(manifest["index_content_hashes"])[run["arm"]]
        expected_paths = run["index_stats"]["indexed_paths"]
        (experiment / f"runtime_index_{run['run_id']}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "experiment_id": run["experiment_id"],
                    "manifest_hash": manifest["manifest_hash"],
                    "session_id": run["session_id"],
                    "run_id": run["run_id"],
                    "repo": run["repo"],
                    "arm": run["arm"],
                    "repeat": run["repeat"],
                    "expected_hash": expected_hash,
                    "expected_paths": expected_paths,
                    "failure_codes": [marker],
                    "materialized": True,
                    "runtime_hash_before": expected_hash,
                    "runtime_hash_after": expected_hash,
                    "runtime_mutated": False,
                    "semantic_digest_before": "same-digest",
                    "semantic_digest_after": "same-digest",
                    "post_paths": expected_paths,
                    "frozen_hash_after": expected_hash,
                    "cleanup_status": "FAILED",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        # Issue #1219: product failures remain bound to runtime policy evidence.
        digest = create_smoke_bundle(
            tmp_path / "bundle",
            plan_dir=plan,
            experiment_dir=experiment,
            registry_path=registry,
        )

        assert len(digest) == 64

    def test_bundle_rejects_runtime_marker_contradicting_audit(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_bundle import create_smoke_bundle

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        runs_path = experiment / "runs.jsonl"
        runs = [
            json.loads(line)
            for line in runs_path.read_text(encoding="utf-8").splitlines()
        ]
        run = runs[0]
        policy_path = experiment / f"policy_{run['run_id']}.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        marker = "RUNTIME_POST_AUDIT_FAILED:ValueError"
        policy["violations"] = [marker, *policy["violations"]]
        policy_path.write_text(json.dumps(policy) + "\n", encoding="utf-8")
        run["status"] = "INVALID"
        run["blocker_reason"] = "POLICY_AUDIT:" + ",".join(policy["violations"])
        runs_path.write_text(
            "".join(json.dumps(item) + "\n" for item in runs), encoding="utf-8"
        )
        manifest = json.loads((plan / "experiment-manifest.json").read_text())
        expected_hash = dict(manifest["index_content_hashes"])[run["arm"]]
        expected_paths = run["index_stats"]["indexed_paths"]
        (experiment / f"runtime_index_{run['run_id']}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "experiment_id": run["experiment_id"],
                    "manifest_hash": manifest["manifest_hash"],
                    "session_id": run["session_id"],
                    "run_id": run["run_id"],
                    "repo": run["repo"],
                    "arm": run["arm"],
                    "repeat": run["repeat"],
                    "expected_hash": expected_hash,
                    "expected_paths": expected_paths,
                    "failure_codes": [marker],
                    "materialized": True,
                    "runtime_hash_before": expected_hash,
                    "runtime_hash_after": expected_hash,
                    "runtime_mutated": False,
                    "semantic_digest_before": "original-digest",
                    "semantic_digest_after": "unexpected-digest",
                    "post_paths": expected_paths,
                    "frozen_hash_after": expected_hash,
                    "cleanup_status": "SUCCESS",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        # Issue #1219: a policy marker cannot self-authorize runtime evidence.
        with pytest.raises(ValueError, match="runtime evidence measurement mismatch"):
            create_smoke_bundle(
                tmp_path / "bundle",
                plan_dir=plan,
                experiment_dir=experiment,
                registry_path=registry,
            )

    def test_bundle_accepts_bound_runtime_post_audit_failure(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_bundle import create_smoke_bundle

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        runs_path = experiment / "runs.jsonl"
        runs = [
            json.loads(line)
            for line in runs_path.read_text(encoding="utf-8").splitlines()
        ]
        run = runs[0]
        policy_path = experiment / f"policy_{run['run_id']}.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        violations = ["RUNTIME_POST_AUDIT_FAILED:ValueError", "TRANSCRIPT_MISSING"]
        run["status"] = "INVALID"
        run["answer"] = "retained backend answer"
        run["transcript_path"] = ""
        run["blocker_reason"] = "POLICY_AUDIT:" + ",".join(violations)
        runs_path.write_text(
            "".join(json.dumps(item) + "\n" for item in runs),
            encoding="utf-8",
        )
        policy.update(
            transcript_path="",
            observed_mcp_servers=[],
            observed_mcp_tools=[],
            violations=violations,
        )
        policy_path.write_text(json.dumps(policy) + "\n", encoding="utf-8")
        manifest = json.loads((plan / "experiment-manifest.json").read_text())
        expected_hash = dict(manifest["index_content_hashes"])[run["arm"]]
        expected_paths = run["index_stats"]["indexed_paths"]
        (experiment / f"runtime_index_{run['run_id']}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "experiment_id": run["experiment_id"],
                    "manifest_hash": manifest["manifest_hash"],
                    "session_id": run["session_id"],
                    "run_id": run["run_id"],
                    "repo": run["repo"],
                    "arm": run["arm"],
                    "repeat": run["repeat"],
                    "expected_hash": expected_hash,
                    "expected_paths": expected_paths,
                    "failure_codes": [violations[0]],
                    "materialized": True,
                    "runtime_hash_before": expected_hash,
                    "runtime_hash_after": expected_hash,
                    "runtime_mutated": False,
                    "semantic_digest_before": "original-digest",
                    "semantic_digest_after": None,
                    "post_paths": None,
                    "frozen_hash_after": expected_hash,
                    "cleanup_status": "SUCCESS",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        # Issue #1219: runtime terminal evidence must remain bundleable.
        digest = create_smoke_bundle(
            tmp_path / "bundle",
            plan_dir=plan,
            experiment_dir=experiment,
            registry_path=registry,
        )

        assert len(digest) == 64

    def test_bundle_replay_is_byte_identical(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_bundle import (
            create_smoke_bundle,
            replay_smoke_bundle,
        )

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        bundle = tmp_path / "bundle"
        digest = create_smoke_bundle(
            bundle,
            plan_dir=plan,
            experiment_dir=experiment,
            registry_path=registry,
        )

        replay_smoke_bundle(bundle, tmp_path / "replay", external_digest=digest)

        assert {
            path.relative_to(bundle): path.read_bytes()
            for path in bundle.rglob("*")
            if path.is_file()
        } == {
            path.relative_to(tmp_path / "replay"): path.read_bytes()
            for path in (tmp_path / "replay").rglob("*")
            if path.is_file()
        }

    def test_bundle_rejects_tampering_against_external_digest(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_bundle import (
            create_smoke_bundle,
            validate_smoke_bundle,
        )

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        bundle = tmp_path / "bundle"
        digest = create_smoke_bundle(
            bundle,
            plan_dir=plan,
            experiment_dir=experiment,
            registry_path=registry,
        )
        (bundle / "evidence" / "runs.jsonl").write_text("tampered\n", encoding="utf-8")

        with pytest.raises(ValueError, match="bundle checksum mismatch"):
            validate_smoke_bundle(bundle, external_digest=digest)

    def test_bundle_reaudits_transcript_instead_of_trusting_policy_file(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.smoke_bundle import (
            create_smoke_bundle,
        )

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        transcript = next((plan / "artifacts").rglob("*.jsonl"))
        transcript.write_text(
            json.dumps(
                {
                    "item": {
                        "type": "command_execution",
                        "command": "curl https://example.com",
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="policy audit mismatch"):
            create_smoke_bundle(
                tmp_path / "bundle",
                plan_dir=plan,
                experiment_dir=experiment,
                registry_path=registry,
            )


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
            "COMPLETE",
            "producer_completed",
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

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        (
            (
                "benchmark_git_sha",
                1,
                "Manifest scalar fields do not match the V1 schema",
            ),
            (
                "seed",
                True,
                "Manifest integer fields do not match the V1 schema",
            ),
            (
                "retry_session_ids",
                "RS",
                "Manifest sequence fields do not match the V1 schema",
            ),
            (
                "expected_cells",
                {},
                "Manifest expected cells do not match the V1 schema",
            ),
            (
                "tool_fingerprints",
                {},
                "Manifest mapping fields do not match the V1 schema",
            ),
            (
                "eligible_paths",
                [["gin", "src/main.py"]],
                "Manifest nested fields do not match the V1 schema",
            ),
        ),
    )
    def test_manifest_parser_rejects_noncanonical_json_shapes(
        self,
        field: str,
        value: object,
        message: str,
    ):
        from dataclasses import asdict

        from benchmarks.codegraph_compare.integrity import parse_manifest_v1

        payload = json.loads(json.dumps(asdict(_v1_manifest())))
        payload[field] = value

        with pytest.raises(ValueError, match=message):
            parse_manifest_v1(payload)

    def test_manifest_constructor_requires_string_provenance(self):
        with pytest.raises(
            ValueError,
            match=("Manifest identity and provenance fields must be non-empty strings"),
        ):
            _v1_manifest(benchmark_git_sha=1)

    @pytest.mark.parametrize(
        ("field", "message"),
        (
            ("seed", "seed must be an integer"),
            ("timeout_seconds", "timeout_seconds must be a positive integer"),
        ),
    )
    def test_manifest_integer_fields_reject_booleans(self, field: str, message: str):
        with pytest.raises(ValueError, match=message):
            _v1_manifest(**{field: True})

    def test_expected_cell_repeat_rejects_boolean(self):
        from benchmarks.codegraph_compare.integrity import ExpectedCellV1

        with pytest.raises(
            ValueError,
            match="Expected cell repeat must be a non-negative integer",
        ):
            ExpectedCellV1(
                repo="gin",
                question_id="q1",
                arm="native-only",
                repeat=True,
                agent_backend="codex",
                run_id="q1__native-only__codex__01",
            )

    def test_expected_cell_identity_requires_strings(self):
        from benchmarks.codegraph_compare.integrity import ExpectedCellV1

        with pytest.raises(
            ValueError,
            match="Expected cell identity fields must be non-empty strings",
        ):
            ExpectedCellV1(
                repo=1,
                question_id="q1",
                arm="native-only",
                repeat=0,
                agent_backend="codex",
                run_id="q1__native-only__codex__00",
            )

    def test_manifest_rejects_required_arm_without_expected_cell(self):
        with pytest.raises(
            ValueError, match="Required arms must exactly match expected cell arms"
        ):
            _v1_manifest(
                expected_run_ids=("q1__tsa-warm__codex__00",),
                required_arms=("codegraph-warm", "tsa-warm"),
            )

    def test_manifest_rejects_empty_required_readiness_oracle(self):
        with pytest.raises(
            ValueError,
            match="Readiness oracles must exactly cover indexed arms",
        ):
            _v1_manifest(
                required_readiness_oracles={
                    "codegraph-warm": ("",),
                    "tsa-warm": ("known-symbol",),
                }
            )

    def test_index_stats_rejects_empty_supplied_readiness_oracle(self):
        from dataclasses import replace

        manifest = _v1_manifest()
        stats = _v1_run(
            manifest,
            "q1__codegraph-warm__codex__00",
        ).index_stats
        if stats is None:
            pytest.fail("indexed fixture must include V1 index statistics")

        with pytest.raises(
            ValueError,
            match=("Readiness oracle identifiers must be non-empty canonical strings"),
        ):
            replace(stats, readiness_oracles=("",))

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

    def test_consumer_only_setup_events_cannot_be_published(self):
        from benchmarks.codegraph_compare.integrity import (
            RegistryEvent,
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
        registry = tuple(
            RegistryEvent(
                manifest.experiment_id,
                manifest.manifest_hash,
                "PLANNED",
                outcome,
            )
            for outcome in ("setup_started", "setup_passed")
        )

        verdict = validate_publishable_experiment(
            manifest,
            registry=registry,
            runs=(native,),
            evals=(_v1_eval(native),),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        assert tuple(item.code for item in verdict.violations) == (
            "REGISTRY_PRODUCER_INCOMPLETE",
        )
        assert verdict.publishable is False

    def test_registry_rejects_activity_after_producer_completion(self):
        from benchmarks.codegraph_compare.integrity import (
            RegistryEvent,
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
        registry = (
            *_registry_for(manifest),
            RegistryEvent(
                manifest.experiment_id,
                manifest.manifest_hash,
                "RUNNING",
                "producer_restarted",
            ),
        )

        verdict = validate_publishable_experiment(
            manifest,
            registry=registry,
            runs=(native,),
            evals=(_v1_eval(native),),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        assert tuple(item.code for item in verdict.violations) == (
            "REGISTRY_PRODUCER_INCOMPLETE",
        )
        assert verdict.publishable is False

    def test_registry_rejects_nonfinal_complete_with_alternate_outcome(self):
        from benchmarks.codegraph_compare.integrity import (
            RegistryEvent,
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
        registry = (
            RegistryEvent(
                manifest.experiment_id,
                manifest.manifest_hash,
                "COMPLETE",
                "alternate_completion",
            ),
            *_registry_for(manifest),
        )

        verdict = validate_publishable_experiment(
            manifest,
            registry=registry,
            runs=(native,),
            evals=(_v1_eval(native),),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        assert tuple(item.code for item in verdict.violations) == (
            "REGISTRY_PRODUCER_INCOMPLETE",
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

    def test_bound_index_hashes_survive_manifest_normalization(self):
        from benchmarks.codegraph_compare.integrity import (
            validate_publishable_experiment,
        )

        manifest = _v1_manifest(
            index_content_hashes={
                "codegraph-warm": "codegraph-index-hash",
                "tsa-warm": "tsa-index-hash",
            }
        )
        runs = tuple(_v1_run(manifest, cell.run_id) for cell in manifest.expected_cells)

        verdict = validate_publishable_experiment(
            manifest,
            registry=_registry_for(manifest),
            runs=runs,
            evals=tuple(_v1_eval(run) for run in runs),
            reported_experiment_ids=(manifest.experiment_id,),
        )

        # Issue #1201: index-bound manifests must normalize with their hashes.
        assert "INVALID_MANIFEST_STRUCTURE" not in {
            item.code for item in verdict.violations
        }

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


class TestSmokeModelPreflight:
    def test_preflight_runs_exact_model_outside_benchmark_tree(self, tmp_path: Path):
        # Issue #1201: unconstrained prompts produced "Acknowledged." intermittently.
        from benchmarks.codegraph_compare import smoke_preflight

        identity = {
            "command": "codex --version",
            "version": "codex-cli 1.2.3",
            "executable": "/tools/codex",
            "executable_sha256": "a" * 64,
        }
        event = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "text": json.dumps({"status": smoke_preflight.SENTINEL}),
                },
            }
        )
        output = tmp_path / "preflight.json"
        completed = subprocess.CompletedProcess([], 0, stdout=event, stderr="")

        with (
            patch.object(smoke_preflight, "_codex_identity", return_value=identity),
            patch.object(smoke_preflight, "_account_surface", return_value="ChatGPT"),
            patch.object(
                smoke_preflight.subprocess, "run", return_value=completed
            ) as run,
        ):
            evidence = smoke_preflight.run_model_preflight(
                model="gpt-fixture", output_path=output
            )

        command = run.call_args.args[0]
        assert command[command.index("--model") + 1] == "gpt-fixture"
        assert "--ephemeral" in command
        assert "--ignore-user-config" in command
        assert "--skip-git-repo-check" in command
        assert "--output-schema" in command
        assert Path(run.call_args.kwargs["cwd"]) != Path.cwd()
        assert evidence["status"] == "PASSED"
        assert json.loads(output.read_text()) == evidence

    def test_preflight_rejects_unstructured_acknowledgement(self):
        # Issue #1201: availability must be proven by schema-bound output.
        from benchmarks.codegraph_compare import smoke_preflight

        event = json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "Acknowledged."},
            }
        )

        with pytest.raises(ValueError, match="terminal message is not JSON"):
            smoke_preflight._agent_message(event)

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("status", "FAILED", "not a successful V1 record"),
            ("model", "wrong-model", "does not match"),
            ("account_surface", "API", "not approved"),
            ("agent_cli_fingerprint", "stale", "stale or mismatched"),
        ],
    )
    def test_preflight_rejects_unbound_evidence(
        self, tmp_path: Path, field: str, value: str, message: str
    ):
        from benchmarks.codegraph_compare import smoke_preflight

        evidence = {
            "schema_version": 1,
            "status": "PASSED",
            "provider": "OpenAI",
            "account_surface": "ChatGPT",
            "model": "gpt-fixture",
            "checked_at": "2026-07-31T00:00:00+00:00",
            "agent_cli": {},
            "agent_cli_fingerprint": "bound",
            "sentinel_sha256": hashlib.sha256(
                smoke_preflight.SENTINEL.encode()
            ).hexdigest(),
        }
        evidence[field] = value
        path = tmp_path / "preflight.json"
        path.write_text(json.dumps(evidence))

        with pytest.raises(ValueError, match=message):
            smoke_preflight.validate_model_preflight(
                path,
                expected_model="gpt-fixture",
                expected_cli_fingerprint="bound",
            )

    def test_preflight_rejects_stale_evidence_before_freeze(self, tmp_path: Path):
        from benchmarks.codegraph_compare import smoke_preflight

        path = tmp_path / "preflight.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "PASSED",
                    "provider": "OpenAI",
                    "account_surface": "ChatGPT",
                    "model": "gpt-fixture",
                    "checked_at": "2020-01-01T00:00:00+00:00",
                    "agent_cli": {},
                    "agent_cli_fingerprint": "bound",
                    "sentinel_sha256": hashlib.sha256(
                        smoke_preflight.SENTINEL.encode()
                    ).hexdigest(),
                }
            )
        )

        with pytest.raises(ValueError, match="stale or has a future timestamp"):
            smoke_preflight.validate_model_preflight(
                path,
                expected_model="gpt-fixture",
                expected_cli_fingerprint="bound",
                max_age_seconds=900,
            )


class TestCanaryLaunchPreflight:
    @staticmethod
    def _identity_probe(arm: str, executable: Path) -> dict[str, str]:
        if arm == "tsa-warm":
            return {
                "trusted_repo": "fixture",
                "entrypoint": "fixture",
                "entrypoint_sha256": "1" * 64,
                "source_root": "fixture",
                "source_sha256": "2" * 64,
                "dependency_lock": "fixture",
                "dependency_lock_sha256": "3" * 64,
            }
        return {
            "package": "@colbymchenry/codegraph@1.5.0",
            "version": "1.5.0",
        }

    @staticmethod
    def _fixture(tmp_path: Path):
        from benchmarks.codegraph_compare import canary_preflight

        checkout = tmp_path / "checkout"
        checkout.mkdir()
        tsa = Path(sys.executable)
        codegraph = Path(sys.executable)
        contracts = canary_preflight.build_canary_launch_contracts(
            checkout,
            tsa_executable=tsa,
            codegraph_executable=codegraph,
            identity_probe=TestCanaryLaunchPreflight._identity_probe,
        )
        return canary_preflight, checkout, tsa, codegraph, contracts

    def test_builder_pins_exact_tsa_nav_launch(self, tmp_path: Path):
        module, checkout, _tsa, _codegraph, contracts = self._fixture(tmp_path)

        contract = contracts[module.TSA_ARM]

        assert contract["args"] == [
            "-m",
            "tree_sitter_analyzer.mcp.server",
            "--project-root",
            str(checkout.resolve()),
        ]
        assert contract["enabled_tools"] == ["nav"]
        assert contract["required"] is True
        assert contract["network"] is False
        assert contract["env"] == {
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "TREE_SITTER_PROJECT_ROOT": str(checkout.resolve()),
        }
        assert contract["inherit_environment"] is False
        assert set(contract["tsa_identity"]) == {
            "trusted_repo",
            "entrypoint",
            "entrypoint_sha256",
            "source_root",
            "source_sha256",
            "dependency_lock",
            "dependency_lock_sha256",
        }
        assert contract["production_ready"] is False

    def test_builder_pins_exact_codegraph_search_launch(self, tmp_path: Path):
        module, checkout, _tsa, _codegraph, contracts = self._fixture(tmp_path)

        contract = contracts[module.CODEGRAPH_ARM]

        assert contract["package"] == "@colbymchenry/codegraph@1.5.0"
        assert contract["args"] == [
            "serve",
            "--mcp",
            "--no-watch",
            "-p",
            str(checkout.resolve()),
        ]
        assert contract["env"] == {
            "CODEGRAPH_MCP_TOOLS": "search",
            "CODEGRAPH_NO_DAEMON": "1",
            "CODEGRAPH_NO_UPDATE_CHECK": "1",
            "CODEGRAPH_TELEMETRY": "0",
            "PATH": os.defpath,
        }
        assert contract["enabled_tools"] == ["codegraph_search"]
        assert contract["required"] is True
        assert contract["network"] is False
        assert contract["inherit_environment"] is False
        assert contract["codegraph_identity"] == {
            "package": "@colbymchenry/codegraph@1.5.0",
            "version": "1.5.0",
        }
        assert contract["production_ready"] is False

    def test_builder_binds_absolute_executables_and_digests(self, tmp_path: Path):
        module, _checkout, tsa, codegraph, contracts = self._fixture(tmp_path)

        assert contracts[module.TSA_ARM]["command"] == str(tsa.resolve())
        assert (
            contracts[module.TSA_ARM]["executable_sha256"]
            == hashlib.sha256(tsa.read_bytes()).hexdigest()
        )
        assert contracts[module.CODEGRAPH_ARM]["command"] == str(codegraph.resolve())
        assert (
            contracts[module.CODEGRAPH_ARM]["executable_sha256"]
            == hashlib.sha256(codegraph.read_bytes()).hexdigest()
        )

    def test_builder_rejects_non_executable_server(self, tmp_path: Path):
        module, checkout, tsa, _codegraph, _contracts = self._fixture(tmp_path)
        codegraph = tmp_path / "codegraph"
        codegraph.write_bytes(b"not executable")

        with pytest.raises(ValueError, match="is not executable"):
            module.build_canary_launch_contracts(
                checkout,
                tsa_executable=tsa,
                codegraph_executable=codegraph,
                identity_probe=self._identity_probe,
            )

    def test_builder_rejects_untrusted_tsa_interpreter(self, tmp_path: Path):
        module, checkout, tsa, codegraph, _contracts = self._fixture(tmp_path)
        foreign = tmp_path / f"foreign-python{tsa.suffix}"
        shutil.copy2(tsa, foreign)

        with pytest.raises(ValueError, match="trusted repository interpreter"):
            module.build_canary_launch_contracts(
                checkout, tsa_executable=foreign, codegraph_executable=codegraph
            )

    def test_builder_rejects_wrong_codegraph_version(self, tmp_path: Path):
        module, checkout, tsa, codegraph, _contracts = self._fixture(tmp_path)

        def wrong_version(arm: str, executable: Path) -> dict[str, str]:
            if arm == module.CODEGRAPH_ARM:
                raise ValueError("CodeGraph version identity mismatch: '1.4.9'")
            return self._identity_probe(arm, executable)

        with pytest.raises(ValueError, match="version identity mismatch"):
            module.build_canary_launch_contracts(
                checkout,
                tsa_executable=tsa,
                codegraph_executable=codegraph,
                identity_probe=wrong_version,
            )

    def test_injected_identity_probe_marks_contract_as_scaffold(self, tmp_path: Path):
        from benchmarks.codegraph_compare import canary_preflight

        checkout = tmp_path / "checkout"
        checkout.mkdir()
        tsa = Path(sys.executable)
        codegraph = Path(sys.executable)

        contracts = canary_preflight.build_canary_launch_contracts(
            checkout,
            tsa_executable=tsa,
            codegraph_executable=codegraph,
            identity_probe=lambda arm, executable: {
                "fixture_arm": arm,
                "fixture_executable": str(executable),
            },
        )

        assert contracts["tsa-warm"]["production_ready"] is False
        assert contracts["codegraph-warm"]["production_ready"] is False

    @pytest.mark.parametrize(
        ("arm", "field", "value"),
        [
            ("tsa-warm", "args", ["--project-root", "/wrong"]),
            ("tsa-warm", "enabled_tools", ["search"]),
            ("tsa-warm", "required", False),
            ("tsa-warm", "network", True),
            ("tsa-warm", "executable_sha256", "0" * 64),
            ("codegraph-warm", "args", ["serve", "--mcp"]),
            ("codegraph-warm", "enabled_tools", ["search", "read"]),
            ("codegraph-warm", "env", {"CODEGRAPH_MCP_TOOLS": "search"}),
            ("codegraph-warm", "required", False),
            ("codegraph-warm", "executable_sha256", "f" * 64),
        ],
    )
    def test_validator_rejects_mutated_launch_surface(
        self, tmp_path: Path, arm: str, field: str, value: object
    ):
        module, checkout, tsa, codegraph, contracts = self._fixture(tmp_path)
        contracts[arm][field] = value

        with pytest.raises(ValueError, match="launch config hash is invalid"):
            module.validate_canary_launch_contracts(
                contracts,
                checkout,
                tsa_executable=tsa,
                codegraph_executable=codegraph,
                identity_probe=self._identity_probe,
            )

    def test_validator_rejects_rehashed_foreign_tool(self, tmp_path: Path):
        module, checkout, tsa, codegraph, contracts = self._fixture(tmp_path)
        contract = contracts[module.CODEGRAPH_ARM]
        contract["enabled_tools"] = ["read"]
        unsigned = {
            key: value for key, value in contract.items() if key != "launch_config_hash"
        }
        contract["launch_config_hash"] = module._sha256(unsigned)

        with pytest.raises(ValueError, match="codegraph-warm.enabled_tools"):
            module.validate_canary_launch_contracts(
                contracts,
                checkout,
                tsa_executable=tsa,
                codegraph_executable=codegraph,
                identity_probe=self._identity_probe,
            )

    def test_validator_rejects_rehashed_ambient_environment_inheritance(
        self, tmp_path: Path
    ):
        module, checkout, tsa, codegraph, contracts = self._fixture(tmp_path)
        contract = contracts[module.TSA_ARM]
        contract["inherit_environment"] = True
        unsigned = {
            key: value for key, value in contract.items() if key != "launch_config_hash"
        }
        contract["launch_config_hash"] = module._sha256(unsigned)

        with pytest.raises(ValueError, match="tsa-warm.inherit_environment"):
            module.validate_canary_launch_contracts(
                contracts,
                checkout,
                tsa_executable=tsa,
                codegraph_executable=codegraph,
                identity_probe=self._identity_probe,
            )

    def test_validator_accepts_exact_contracts(self, tmp_path: Path):
        module, checkout, tsa, codegraph, contracts = self._fixture(tmp_path)

        validated = module.validate_canary_launch_contracts(
            contracts,
            checkout,
            tsa_executable=tsa,
            codegraph_executable=codegraph,
            identity_probe=self._identity_probe,
        )

        assert validated == contracts


class TestCanaryWorkspaceImmutability:
    def _checkout(self, tmp_path: Path) -> Path:
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=checkout, check=True)
        subprocess.run(
            ["git", "config", "user.email", "canary@example.invalid"],
            cwd=checkout,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Canary"], cwd=checkout, check=True
        )
        (checkout / "gin.go").write_text("package gin\n", encoding="utf-8")
        (checkout / "README.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=checkout, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "fixture"], cwd=checkout, check=True
        )
        return checkout.resolve()

    def test_audit_records_exact_source_and_runtime_inventories(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_workspace import (
            audit_canary_checkout,
            cleanup_and_verify_canary_checkout,
            snapshot_canary_checkout,
        )

        checkout = self._checkout(tmp_path)
        snapshot = snapshot_canary_checkout(checkout, "tsa-warm")
        runtime = checkout / ".ast-cache"
        runtime.mkdir()
        (runtime / "index.db").write_bytes(b"index")

        audit = audit_canary_checkout(snapshot)

        assert audit.checkout_root == checkout
        assert audit.head_commit == snapshot.head_commit
        assert audit.tracked_paths == ("README.md", "gin.go")
        assert audit.repository_fingerprint == snapshot.repository_fingerprint
        assert audit.source_after == audit.source_before
        assert audit.runtime_before == ()
        assert audit.runtime_after == (
            ("index.db", hashlib.sha256(b"index").hexdigest()),
        )
        cleanup_and_verify_canary_checkout(snapshot, audit)
        assert os.path.lexists(runtime) is False

    def test_runtime_inventory_includes_nested_git_metadata(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_workspace import (
            audit_canary_checkout,
            snapshot_canary_checkout,
        )

        checkout = self._checkout(tmp_path)
        snapshot = snapshot_canary_checkout(checkout, "tsa-warm")
        runtime_git = checkout / ".ast-cache" / ".git"
        runtime_git.mkdir(parents=True)
        (runtime_git / "config").write_bytes(b"runtime-metadata")

        audit = audit_canary_checkout(snapshot)

        assert audit.runtime_after == (
            (
                ".git/config",
                hashlib.sha256(b"runtime-metadata").hexdigest(),
            ),
        )

    @pytest.mark.parametrize(
        ("mutation", "message"),
        [
            ("tracked", "tracked repository content changed"),
            ("new", "non-runtime checkout inventory changed"),
            ("delete", "tracked repository content changed"),
            ("rename", "tracked repository content changed"),
        ],
    )
    def test_audit_rejects_checkout_namespace_mutation(
        self, tmp_path: Path, mutation: str, message: str
    ):
        from benchmarks.codegraph_compare.canary_workspace import (
            audit_canary_checkout,
            snapshot_canary_checkout,
        )

        checkout = self._checkout(tmp_path)
        snapshot = snapshot_canary_checkout(checkout, "codegraph-warm")
        (checkout / ".codegraph").mkdir()
        if mutation == "tracked":
            (checkout / "gin.go").write_text("mutated\n", encoding="utf-8")
        elif mutation == "new":
            (checkout / "unprovenanced.txt").write_text("new\n", encoding="utf-8")
        elif mutation == "delete":
            (checkout / "gin.go").unlink()
        else:
            (checkout / "gin.go").rename(checkout / "renamed.go")

        with pytest.raises(ValueError, match=message):
            audit_canary_checkout(snapshot)

    def test_audit_rejects_symlinked_runtime_namespace(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_workspace import (
            audit_canary_checkout,
            snapshot_canary_checkout,
        )

        checkout = self._checkout(tmp_path)
        snapshot = snapshot_canary_checkout(checkout, "tsa-warm")
        target = tmp_path / "escaped"
        target.mkdir()
        (checkout / ".ast-cache").symlink_to(target, target_is_directory=True)

        with pytest.raises(
            ValueError, match="runtime namespace must be a real directory"
        ):
            audit_canary_checkout(snapshot)

    def test_snapshot_rejects_cross_arm_namespace(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_workspace import (
            snapshot_canary_checkout,
        )

        checkout = self._checkout(tmp_path)
        (checkout / ".codegraph").mkdir()

        with pytest.raises(ValueError, match="cross-arm runtime namespace"):
            snapshot_canary_checkout(checkout, "tsa-warm")

    def test_audit_rejects_hardlinked_runtime_file(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_workspace import (
            audit_canary_checkout,
            snapshot_canary_checkout,
        )

        checkout = self._checkout(tmp_path)
        snapshot = snapshot_canary_checkout(checkout, "codegraph-warm")
        runtime = checkout / ".codegraph"
        runtime.mkdir()
        source = tmp_path / "shared.db"
        source.write_bytes(b"shared")
        os.link(source, runtime / "codegraph.db")

        with pytest.raises(ValueError, match="checkout inventory contains hardlink"):
            audit_canary_checkout(snapshot)

    def test_cleanup_restores_checkout_when_audit_failed(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_workspace import (
            cleanup_and_verify_canary_checkout,
            snapshot_canary_checkout,
        )

        checkout = self._checkout(tmp_path)
        snapshot = snapshot_canary_checkout(checkout, "tsa-warm")
        runtime = checkout / ".ast-cache"
        runtime.mkdir()
        (runtime / "partial.db").write_bytes(b"partial")

        cleanup_and_verify_canary_checkout(snapshot, None)

        assert os.path.lexists(runtime) is False


class TestCanaryEvidence:
    @staticmethod
    def _manifest():
        from benchmarks.codegraph_compare.canary_evidence import create_canary_manifest

        return create_canary_manifest(
            benchmark_git_sha="benchmark-sha",
            benchmark_version="NO1-002C-E0-v1",
            model="gpt-fixture",
            agent_cli_fingerprint="codex-cli-fixture",
            gin_commit="gin-commit",
            gin_source_fingerprint="a" * 64,
            canary_prompt_sha256="b" * 64,
            launch_config_hashes={"tsa-warm": "c" * 64, "codegraph-warm": "d" * 64},
            timeout_seconds=300,
            seed=1195,
        )

    @staticmethod
    def _evidence(manifest, tmp_path):
        from benchmarks.codegraph_compare.canary_evidence import (
            CanaryArtifactV1,
            CanaryAttemptV1,
            CanaryRegistryEventV1,
        )

        attempts = []
        artifacts = []
        for index, cell in enumerate(manifest.cells):
            call_id = f"call-{index}"
            if cell.arm == "tsa-warm":
                item = TestGinSmokeManifestExecution._tsa_canary_item(call_id)
            else:
                item = {
                    "id": call_id,
                    "type": "mcp_tool_call",
                    "status": "completed",
                    "server": "codegraph",
                    "tool": "codegraph_search",
                    "arguments": {
                        "query": "Engine.ServeHTTP",
                        "kind": "method",
                        "limit": 10,
                    },
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": "**ServeHTTP** (method)\n"
                                "func (engine *Engine) ServeHTTP(w http.ResponseWriter, req *http.Request)\n"
                                "gin.go:42",
                            }
                        ]
                    },
                }
            transcript_payload = (
                json.dumps({"type": "item.completed", "item": item}) + "\n"
            ).encode()
            source_inventory = [["gin.go", "a" * 64]]
            audit = {
                "checkout_root": str((tmp_path / f"checkout-{index}").resolve()),
                "head_commit": "e" * 40,
                "tracked_paths": ["gin.go"],
                "repository_fingerprint": "f" * 64,
                "source_before": source_inventory,
                "source_after": source_inventory,
                "runtime_namespace": (
                    ".ast-cache" if cell.arm == "tsa-warm" else ".codegraph"
                ),
                "runtime_before": [],
                "runtime_after": [["index.db", "b" * 64]],
            }
            workspace = hashlib.sha256(
                json.dumps(audit, separators=(",", ":"), sort_keys=True).encode()
            ).hexdigest()
            payloads = {
                "receipt": json.dumps(
                    {"call_id": call_id}, separators=(",", ":"), sort_keys=True
                ).encode(),
                "transcript": transcript_payload,
                "workspace_audit": json.dumps(
                    {
                        "schema_version": 1,
                        "manifest_hash": manifest.manifest_hash,
                        "session_id": "session-001",
                        "run_id": cell.cell_id,
                        "cell_id": cell.cell_id,
                        "arm": cell.arm,
                        "audit_sha256": workspace,
                        "audit": audit,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode(),
            }
            runtime = hashlib.sha256(f"runtime-{index}".encode()).hexdigest()
            payloads["runtime"] = runtime.encode()
            transcript = hashlib.sha256(payloads["transcript"]).hexdigest()
            attempt = CanaryAttemptV1(
                1,
                manifest.manifest_hash,
                "session-001",
                cell.cell_id,
                cell.cell_id,
                cell.arm,
                1,
                call_id,
                transcript,
                workspace,
                runtime,
                "SUCCESS",
            )
            attempts.append(attempt)
            for kind, payload in payloads.items():
                path = (tmp_path / f"{cell.cell_id}.{kind}").resolve()
                path.write_bytes(payload)
                artifacts.append(
                    CanaryArtifactV1(
                        1,
                        manifest.manifest_hash,
                        "session-001",
                        cell.cell_id,
                        cell.cell_id,
                        cell.arm,
                        kind,
                        hashlib.sha256(payload).hexdigest(),
                        str(path),
                        call_id if kind == "receipt" else None,
                    )
                )
        registry = (
            CanaryRegistryEventV1(
                1,
                manifest.manifest_hash,
                "session-001",
                "COMPLETE",
                "canary_accepted",
                ("tsa-warm-canary", "codegraph-warm-canary"),
            ),
        )
        return tuple(attempts), tuple(artifacts), registry

    def test_manifest_freezes_exact_two_cell_e0_protocol(self):
        from benchmarks.codegraph_compare.canary_evidence import (
            canonical_sha256,
            validate_canary_manifest,
        )

        manifest = self._manifest()
        validate_canary_manifest(manifest)

        assert tuple(
            (
                cell.cell_id,
                cell.arm,
                cell.attempt_count,
                cell.schedule_order,
                cell.phase,
                cell.native_allowed,
            )
            for cell in manifest.cells
        ) == (
            ("tsa-warm-canary", "tsa-warm", 1, 0, "E0", False),
            ("codegraph-warm-canary", "codegraph-warm", 1, 1, "E0", False),
        )
        assert manifest.oracle == ("gin.go", "Engine.ServeHTTP", "method")
        assert manifest.oracle_hash == canonical_sha256(list(manifest.oracle))
        assert manifest.budget_ceiling_usd == 3.0
        assert (manifest.winner, manifest.dominance_allowed, manifest.publishable) == (
            None,
            False,
            False,
        )

    def test_canonical_sha256_is_key_order_independent_and_exact(self):
        from benchmarks.codegraph_compare.canary_evidence import canonical_sha256

        left = canonical_sha256({"b": 2, "a": [1, "x"]})
        right = canonical_sha256({"a": [1, "x"], "b": 2})

        assert (
            left
            == "8cbd548a32262b76a6536efe4e7ba86a0e811fcd0475d83a43e10acd0615aa37"  # pragma: allowlist secret
        )
        assert right == left

    def test_complete_two_cell_evidence_requires_production_trust_anchor(
        self, tmp_path
    ):
        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        verdict = validate_canary_evidence(
            manifest, *self._evidence(manifest, tmp_path)
        )

        assert verdict.status == "NOT_EVALUATED"
        assert verdict.violations == ("PRODUCTION_TRUST_ANCHOR_UNAVAILABLE",)
        assert (verdict.accepted_cells, verdict.required_cells) == (2, 2)
        assert (verdict.winner, verdict.dominance_allowed, verdict.publishable) == (
            None,
            False,
            False,
        )

    def test_absent_evidence_is_not_evaluated(self):
        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        verdict = validate_canary_evidence(self._manifest(), (), (), ())

        assert verdict.status == "NOT_EVALUATED"
        assert verdict.violations == ()
        assert (verdict.accepted_cells, verdict.required_cells) == (0, 2)
        assert verdict.publishable is False

    def test_tampered_protected_claim_flag_is_invalid_without_evidence(self):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = replace(self._manifest(), dominance_allowed=True)

        verdict = validate_canary_evidence(manifest, (), (), ())

        assert verdict.status == "INVALID"
        assert verdict.violations == (
            "MANIFEST_INVALID:protected claim flags must remain false/null",
        )
        assert (verdict.winner, verdict.dominance_allowed, verdict.publishable) == (
            None,
            False,
            False,
        )

    def test_malformed_manifest_type_returns_invalid_instead_of_raising(self):
        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        verdict = validate_canary_evidence({}, (), (), ())

        assert verdict.status == "INVALID"
        assert verdict.violations == (
            "MANIFEST_INVALID:manifest must be CanaryManifestV1",
        )
        assert (verdict.accepted_cells, verdict.required_cells) == (0, 2)

    @pytest.mark.parametrize("mutation", ("duplicate", "cross-arm"))
    def test_artifact_nonbijection_fails_closed(self, tmp_path, mutation: str):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        attempts, artifacts, registry = self._evidence(manifest, tmp_path)
        mutated = list(artifacts)
        if mutation == "duplicate":
            mutated.append(artifacts[0])
        else:
            mutated[4] = replace(
                mutated[4],
                cell_id="tsa-warm-canary",
                arm="tsa-warm",
                run_id="tsa-warm-canary",
            )

        verdict = validate_canary_evidence(manifest, attempts, mutated, registry)

        assert verdict.status == "INVALID"
        assert "ARTIFACT_BIJECTION:tsa-warm-canary" in verdict.violations
        assert verdict.publishable is False

    def test_attempt_receipt_binding_mismatch_is_invalid(self, tmp_path):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        attempts, artifacts, registry = self._evidence(manifest, tmp_path)
        attempts = (replace(attempts[0], receipt_call_id="call-tampered"), attempts[1])

        verdict = validate_canary_evidence(manifest, attempts, artifacts, registry)

        assert verdict.status == "INVALID"
        assert verdict.violations == ("ARTIFACT_BINDING:tsa-warm-canary",)
        assert verdict.publishable is False

    def test_artifact_digest_cannot_self_attest_tampered_bytes(self, tmp_path):
        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        attempts, artifacts, registry = self._evidence(manifest, tmp_path)
        Path(artifacts[0].evidence_path).write_bytes(b"tampered")

        verdict = validate_canary_evidence(manifest, attempts, artifacts, registry)

        assert verdict.status == "INVALID"
        assert verdict.violations == ("ARTIFACT_BINDING:tsa-warm-canary",)

    @pytest.mark.parametrize("mutation", ("no-receipt", "wrong-receiver"))
    def test_transcript_hash_cannot_replace_semantic_replay(
        self, tmp_path, mutation: str
    ):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        attempts, artifacts, registry = self._evidence(manifest, tmp_path)
        transcript = artifacts[1]
        if mutation == "no-receipt":
            payload = b'{"type":"turn.completed"}\n'
        else:
            item = TestGinSmokeManifestExecution._tsa_canary_item("call-0")
            body = json.loads(item["result"]["content"][0]["text"])
            body["symbol"] = "Other.ServeHTTP"
            item["result"]["content"][0]["text"] = json.dumps(body)
            payload = (
                json.dumps({"type": "item.completed", "item": item}) + "\n"
            ).encode()
        Path(transcript.evidence_path).write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        attempts = (replace(attempts[0], transcript_sha256=digest), attempts[1])
        artifacts = tuple(
            replace(artifact, sha256=digest) if artifact is transcript else artifact
            for artifact in artifacts
        )

        verdict = validate_canary_evidence(manifest, attempts, artifacts, registry)

        assert verdict.status == "INVALID"
        assert verdict.violations == ("ARTIFACT_BINDING:tsa-warm-canary",)

    def test_workspace_hash_cannot_replace_schema_binding(self, tmp_path):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        attempts, artifacts, registry = self._evidence(manifest, tmp_path)
        workspace = artifacts[2]
        payload = b'{"audit_sha256":"arbitrary"}'
        Path(workspace.evidence_path).write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        artifacts = tuple(
            replace(artifact, sha256=digest) if artifact is workspace else artifact
            for artifact in artifacts
        )

        verdict = validate_canary_evidence(manifest, attempts, artifacts, registry)

        assert verdict.status == "INVALID"
        assert verdict.violations == ("ARTIFACT_BINDING:tsa-warm-canary",)

    def test_workspace_arbitrary_self_hash_cannot_replace_raw_audit(self, tmp_path):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        attempts, artifacts, registry = self._evidence(manifest, tmp_path)
        workspace = artifacts[2]
        envelope = json.loads(Path(workspace.evidence_path).read_text())
        envelope["audit_sha256"] = "f" * 64
        payload = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode()
        Path(workspace.evidence_path).write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        attempts = (replace(attempts[0], workspace_audit_sha256="f" * 64), attempts[1])
        artifacts = tuple(
            replace(artifact, sha256=digest) if artifact is workspace else artifact
            for artifact in artifacts
        )

        verdict = validate_canary_evidence(manifest, attempts, artifacts, registry)

        assert verdict.status == "INVALID"
        assert verdict.violations == ("ARTIFACT_BINDING:tsa-warm-canary",)

    def test_synchronized_raw_audit_rehash_never_unlocks_accept(self, tmp_path):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        attempts, artifacts, registry = self._evidence(manifest, tmp_path)
        workspace = artifacts[2]
        envelope = json.loads(Path(workspace.evidence_path).read_text())
        envelope["audit"]["head_commit"] = "d" * 40
        audit_hash = hashlib.sha256(
            json.dumps(
                envelope["audit"], separators=(",", ":"), sort_keys=True
            ).encode()
        ).hexdigest()
        envelope["audit_sha256"] = audit_hash
        payload = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode()
        Path(workspace.evidence_path).write_bytes(payload)
        artifact_hash = hashlib.sha256(payload).hexdigest()
        attempts = (
            replace(attempts[0], workspace_audit_sha256=audit_hash),
            attempts[1],
        )
        artifacts = tuple(
            (
                replace(artifact, sha256=artifact_hash)
                if artifact is workspace
                else artifact
            )
            for artifact in artifacts
        )

        verdict = validate_canary_evidence(manifest, attempts, artifacts, registry)

        assert verdict.status == "NOT_EVALUATED"
        assert verdict.violations == ("PRODUCTION_TRUST_ANCHOR_UNAVAILABLE",)
        assert verdict.publishable is False

    @pytest.mark.parametrize("launches", (None, [], "not-a-tuple"))
    def test_malformed_manifest_launch_config_type_is_invalid(self, launches):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        verdict = validate_canary_evidence(
            replace(self._manifest(), launch_config_hashes=launches), (), (), ()
        )

        assert verdict.status == "INVALID"
        assert verdict.violations == (
            "MANIFEST_INVALID:launch_config_hashes must be a tuple",
        )

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        (
            ("schema_version", True, "unsupported canary manifest schema"),
            ("timeout_seconds", True, "timeout_seconds must be a positive integer"),
            ("seed", False, "seed must be a non-negative integer"),
            ("budget_ceiling_usd", 3, "budget ceiling mismatch"),
            ("dominance_allowed", 0, "protected claim flags must remain false/null"),
            ("publishable", 0, "protected claim flags must remain false/null"),
        ),
    )
    def test_manifest_rejects_bool_integer_type_confusion(self, field, value, message):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        verdict = validate_canary_evidence(
            replace(self._manifest(), **{field: value}), (), (), ()
        )

        assert verdict.status == "INVALID"
        assert verdict.violations == (f"MANIFEST_INVALID:{message}",)

    @pytest.mark.parametrize("invalid_artifact", (object(), {"kind": "receipt"}))
    def test_invalid_artifact_schema_fails_closed(
        self, tmp_path, invalid_artifact: object
    ):
        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        attempts, artifacts, registry = self._evidence(manifest, tmp_path)

        verdict = validate_canary_evidence(
            manifest, attempts, (*artifacts, invalid_artifact), registry
        )

        assert verdict.status == "INVALID"
        assert verdict.violations == ("ARTIFACT_SCHEMA_INVALID",)
        assert verdict.publishable is False

    def test_extra_registry_event_is_invalid(self, tmp_path):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        attempts, artifacts, registry = self._evidence(manifest, tmp_path)
        registry = (*registry, replace(registry[0], outcome="late_event"))

        verdict = validate_canary_evidence(manifest, attempts, artifacts, registry)

        assert verdict.status == "INVALID"
        assert verdict.violations == ("REGISTRY_TERMINAL_INVALID",)
        assert verdict.publishable is False


class TestCanaryProtocol:
    @staticmethod
    def _manifest():
        from benchmarks.codegraph_compare.canary_evidence import create_canary_manifest

        return create_canary_manifest(
            benchmark_git_sha="benchmark-sha",
            benchmark_version="NO1-002C-E0-v1",
            model="gpt-fixture",
            agent_cli_fingerprint="codex-cli-fixture",
            gin_commit="gin-commit",
            gin_source_fingerprint="a" * 64,
            canary_prompt_sha256="b" * 64,
            launch_config_hashes={"tsa-warm": "c" * 64, "codegraph-warm": "d" * 64},
            timeout_seconds=300,
            seed=1195,
        )

    @staticmethod
    def _runner(
        tmp_path,
        *,
        costs=(1.0, 1.0),
        policy_invalid=False,
        drift=False,
        run_raises=False,
        transcript_missing=False,
        cleanup_fails=False,
        fixture_cost_plan=(1.5, 1.5),
        execution_mode="fixture",
        omit_execution_mode=False,
    ):
        from benchmarks.codegraph_compare.canary_policy import (
            CanaryAudit,
            CanaryReceipt,
        )
        from benchmarks.codegraph_compare.canary_protocol import (
            CanaryProtocol,
            CanaryProtocolCallbacks,
            CanaryRunFailure,
            CanaryRunResult,
        )
        from benchmarks.codegraph_compare.smoke_policy import PolicyAudit

        state = {"runs": [], "setups": [], "cleanups": [], "ids": 0}

        def new_id(label):
            state["ids"] += 1
            return f"{label}-{state['ids']}"

        def setup(arm, checkout):
            state["setups"].append((arm, checkout))

        def run(
            cell,
            checkout,
            session_id,
            run_id,
            contract,
            remaining_usd,
            fixture_cost_limit_usd,
        ):
            index = len(state["runs"])
            transcript = tmp_path / f"{cell.cell_id}.jsonl"
            call_id = f"call-{cell.arm}"
            if cell.arm == "tsa-warm":
                item = TestGinSmokeManifestExecution._tsa_canary_item(call_id)
            else:
                item = {
                    "id": call_id,
                    "type": "mcp_tool_call",
                    "status": "completed",
                    "server": "codegraph",
                    "tool": "codegraph_search",
                    "arguments": {
                        "query": "Engine.ServeHTTP",
                        "kind": "method",
                        "limit": 10,
                    },
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": "**ServeHTTP** (method)\n"
                                "func (engine *Engine) ServeHTTP(w http.ResponseWriter, req *http.Request)\n"
                                "gin.go:42",
                            }
                        ]
                    },
                }
            transcript.write_text(
                json.dumps({"type": "item.completed", "item": item}) + "\n",
                encoding="utf-8",
            )
            state["runs"].append(
                (
                    cell.cell_id,
                    session_id,
                    run_id,
                    contract["arm"],
                    remaining_usd,
                    fixture_cost_limit_usd,
                )
            )
            if run_raises:
                raise CanaryRunFailure(
                    "run failed after transcript creation",
                    CanaryRunResult(transcript, costs[index], 0),
                )
            if transcript_missing:
                transcript.unlink()
            return CanaryRunResult(transcript, costs[index], 1)

        def policy(path, arm, **expected):
            violations = ("FIXTURE_POLICY_INVALID",) if policy_invalid else ()
            base = PolicyAudit(arm, str(path), (arm,), (expected["expected_tool"],), ())
            receipt = CanaryReceipt(
                f"call-{arm}",
                arm,
                expected["expected_tool"],
                expected["expected_path"],
                expected["expected_symbol"],
                expected["expected_kind"],
                1,
            )
            return CanaryAudit(base, receipt, violations)

        def workspace(snapshot):
            if drift:
                raise ValueError("workspace drift")
            source_inventory = [["gin.go", "a" * 64]]
            return {
                "checkout_root": str(Path(snapshot["checkout"]).resolve()),
                "head_commit": "e" * 40,
                "tracked_paths": ["gin.go"],
                "repository_fingerprint": "f" * 64,
                "source_before": source_inventory,
                "source_after": source_inventory,
                "runtime_namespace": (
                    ".ast-cache" if snapshot["arm"] == "tsa-warm" else ".codegraph"
                ),
                "runtime_before": [],
                "runtime_after": [["index.db", "b" * 64]],
            }

        def cleanup(snapshot, audit):
            state["cleanups"].append((snapshot["arm"], audit))
            if cleanup_fails:
                raise ValueError("cleanup failed")

        callbacks = CanaryProtocolCallbacks(
            validate_launch=lambda contracts, checkouts: None,
            snapshot=lambda checkout, arm: {"checkout": str(checkout), "arm": arm},
            setup_index=setup,
            run_cell=run,
            audit_policy=policy,
            audit_workspace=workspace,
            cleanup_workspace=cleanup,
            runtime_hash=lambda arm, checkout, audit: (
                "1" * 64 if arm == "tsa-warm" else "2" * 64
            ),
            new_id=new_id,
        )
        contracts = {
            "tsa-warm": {"arm": "tsa-warm"},
            "codegraph-warm": {"arm": "codegraph-warm"},
        }
        checkouts = {
            "tsa-warm": tmp_path / "tsa",
            "codegraph-warm": tmp_path / "codegraph",
        }
        mode_arguments = (
            {} if omit_execution_mode else {"execution_mode": execution_mode}
        )
        return (
            CanaryProtocol(
                TestCanaryProtocol._manifest(),
                contracts,
                checkouts,
                callbacks,
                tmp_path / "canary-journal.json",
                {
                    "tsa-warm-canary": fixture_cost_plan[0],
                    "codegraph-warm-canary": fixture_cost_plan[1],
                },
                **mode_arguments,
            ),
            state,
        )

    def test_fixture_simulates_exact_seeded_two_cell_order(self, tmp_path):
        runner, state = self._runner(tmp_path)

        result = runner.execute()

        assert result.status == "NOT_EVALUATED"
        assert result.violations[0] == "FIXTURE_SIMULATION_NOT_QUALIFICATION"
        assert result.cumulative_cost_usd == 2.0
        assert tuple(item[0] for item in state["runs"]) == (
            "tsa-warm-canary",
            "codegraph-warm-canary",
        )
        assert tuple((item[4], item[5]) for item in state["runs"]) == (
            (3.0, 1.5),
            (2.0, 1.5),
        )
        assert len(result.attempts) == 2
        assert len(result.artifacts) == 8
        assert len(result.registry) == 1
        assert result.registry[0].status == "INVALID"

    def test_first_cell_failure_prevents_second_cell(self, tmp_path):
        runner, state = self._runner(tmp_path, policy_invalid=True)

        result = runner.execute()

        assert result.status == "INVALID"
        assert len(state["runs"]) == 1
        assert len(result.attempts) == 1
        assert result.attempts[0].status == "INVALID"
        assert result.registry[0].status == "INVALID"

    def test_policy_invalid_is_terminal(self, tmp_path):
        runner, _ = self._runner(tmp_path, policy_invalid=True)

        result = runner.execute()

        assert result.violations[0] == (
            "CELL_INVALID:tsa-warm-canary:primary=policy audit rejected transcript"
        )

    def test_workspace_drift_is_terminal(self, tmp_path):
        runner, state = self._runner(tmp_path, drift=True)

        result = runner.execute()

        assert result.status == "INVALID"
        assert len(state["runs"]) == 1
        assert result.violations[0] == (
            "CELL_INVALID:tsa-warm-canary:workspace=workspace drift"
        )

    def test_fixture_cost_plan_rejects_overage_before_simulation_callback(
        self, tmp_path
    ):
        runner, state = self._runner(tmp_path, fixture_cost_plan=(3.01, 0.01))

        result = runner.execute()

        assert result.status == "INVALID"
        assert state["runs"] == []
        assert result.violations[0] == (
            "PREFLIGHT_INVALID:fixture cost plan exceeds declared simulation budget"
        )

    @pytest.mark.parametrize("cost", (float("nan"), float("inf"), float("-inf")))
    def test_nonfinite_cost_is_rejected_before_second_cell(self, tmp_path, cost):
        runner, state = self._runner(tmp_path, costs=(cost, 0.0))

        result = runner.execute()

        assert result.status == "INVALID"
        assert len(state["runs"]) == 1
        assert result.violations[0] == (
            "CELL_INVALID:tsa-warm-canary:primary="
            "reported cost must be a finite non-negative number"
        )

    def test_protocol_object_cannot_attempt_callbacks_twice(self, tmp_path):
        runner, state = self._runner(tmp_path)
        first = runner.execute()

        with pytest.raises(RuntimeError, match="one-shot; retry is forbidden"):
            runner.execute()

        assert first.status == "NOT_EVALUATED"
        assert len(state["runs"]) == 2

    @pytest.mark.parametrize("mode", (None, "production"))
    def test_nonfixture_mode_rejects_before_every_callback(self, tmp_path, mode):
        runner, state = self._runner(
            tmp_path,
            execution_mode=mode,
            omit_execution_mode=mode is None,
        )

        result = runner.execute()

        assert result.status == "NOT_EVALUATED"
        assert result.violations == ("QUALIFICATION_SCAFFOLD_NOT_PRODUCTION_READY",)
        assert state == {"runs": [], "setups": [], "cleanups": [], "ids": 0}
        assert result.registry == ()

    def test_terminal_journal_blocks_new_protocol_instance(self, tmp_path):
        runner, state = self._runner(tmp_path)
        first = runner.execute()
        journal = tmp_path / "canary-journal.json"
        terminal = json.loads(journal.read_text(encoding="utf-8"))
        replacement, _ = self._runner(tmp_path)

        with pytest.raises(RuntimeError, match="fixture.*retry is forbidden"):
            replacement.execute()

        assert first.status == "NOT_EVALUATED"
        assert terminal["state"] == "TERMINAL"
        assert terminal["status"] == "NOT_EVALUATED"
        assert len(state["runs"]) == 2

    def test_existing_reservation_blocks_first_simulation_callback(self, tmp_path):
        runner, state = self._runner(tmp_path)
        (tmp_path / "canary-journal.json").write_text(
            '{"state":"RESERVED"}\n', encoding="utf-8"
        )

        with pytest.raises(RuntimeError, match="fixture.*retry is forbidden"):
            runner.execute()

        assert state["runs"] == []

    def test_journal_inside_checkout_is_rejected_before_simulation_callback(
        self, tmp_path
    ):
        runner, state = self._runner(tmp_path)
        checkout = tmp_path / "tsa"
        checkout.mkdir()
        runner._journal_path = checkout / "journal.json"

        with pytest.raises(ValueError, match="outside every checkout"):
            runner.execute()

        assert state["runs"] == []

    def test_run_failure_after_setup_still_attempts_cleanup(self, tmp_path):
        runner, state = self._runner(tmp_path, run_raises=True)

        result = runner.execute()

        assert result.status == "INVALID"
        assert len(state["runs"]) == 1
        assert len(state["cleanups"]) == 1
        assert state["cleanups"][0][0] == "tsa-warm"
        assert result.cumulative_cost_usd == 1.0
        assert tuple(artifact.kind for artifact in result.artifacts) == (
            "transcript",
            "workspace_audit",
            "runtime",
        )
        expected_transcript = (tmp_path / "tsa-warm-canary.jsonl").read_bytes()
        assert (
            result.attempts[0].transcript_sha256
            == hashlib.sha256(expected_transcript).hexdigest()
        )
        transcript_artifact = next(
            artifact for artifact in result.artifacts if artifact.kind == "transcript"
        )
        assert (
            Path(transcript_artifact.evidence_path).read_bytes() == expected_transcript
        )
        assert tmp_path / "tsa" not in Path(transcript_artifact.evidence_path).parents
        journal = json.loads((tmp_path / "canary-journal.json").read_text())
        journal_transcript = next(
            artifact
            for artifact in journal["result"]["artifacts"]
            if artifact["kind"] == "transcript"
        )
        assert journal_transcript["evidence_path"] == transcript_artifact.evidence_path

    def test_cost_survives_transcript_hash_failure_in_terminal_journal(self, tmp_path):
        runner, state = self._runner(tmp_path, transcript_missing=True)

        result = runner.execute()
        journal = json.loads((tmp_path / "canary-journal.json").read_text())

        assert result.status == "INVALID"
        assert result.cumulative_cost_usd == 1.0
        assert len(state["runs"]) == 1
        assert journal["state"] == "TERMINAL"
        assert journal["result"]["cumulative_cost_usd"] == 1.0
        assert journal["result"]["attempts"][0]["transcript_sha256"] == "0" * 64

    def test_policy_failure_and_workspace_mutation_are_both_recorded(self, tmp_path):
        runner, state = self._runner(tmp_path, policy_invalid=True, drift=True)

        result = runner.execute()

        assert result.violations[0] == (
            "CELL_INVALID:tsa-warm-canary:primary=policy audit rejected transcript"
            "|workspace=workspace drift"
        )
        assert len(state["cleanups"]) == 1
        assert state["cleanups"][0][1] is None

    def test_cleanup_failure_is_terminal_and_prevents_second_cell(self, tmp_path):
        runner, state = self._runner(tmp_path, cleanup_fails=True)

        result = runner.execute()

        assert result.status == "INVALID"
        assert len(state["runs"]) == 1
        assert len(state["cleanups"]) == 1
        assert result.violations[0] == (
            "CELL_INVALID:tsa-warm-canary:cleanup=cleanup failed"
        )


POSIX_QUALIFICATION_TEST = pytest.mark.skipif(
    "os.name == 'nt'",
    reason="tracked: NO1-008A qualification requires openat/O_NOFOLLOW",
)


def _verifier_recovery_fixture():
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    manifest = {
        "cells": [
            {
                "contract": {
                    "decision_id": "1" * 64,
                    "decision_contract_sha256": "2" * 64,
                }
            }
        ]
    }
    raw = canonical_json_bytes(manifest)
    digest = hashlib.sha256(raw).hexdigest()
    measurement = {"runtime": "trusted"}
    config = {
        "verifier": {"key_id": "verifier", "public_key_hex": "00" * 32},
        "trusted": {"verifier_runtime": {"measurement": measurement}},
    }
    begin_signed = {
        "manifest_sha256": digest,
        "challenge": "3" * 64,
        "ledger_counter": 1,
        "ledger_prev_hash": "0" * 64,
        "issued_at_ns": 7,
        "service_identity": measurement,
    }
    begin = {
        **begin_signed,
        "key_id": "verifier",
        "algorithm": "Ed25519",
        "signature": "00" * 64,
    }
    consumed = {
        "counter": 2,
        "event": "CONSUMED",
        "challenge": "3" * 64,
        "manifest_sha256": digest,
    }

    def proof(record):
        return {
            "record": record,
            "key_id": "verifier",
            "algorithm": "Ed25519",
            "signature": "00" * 64,
        }

    envelope = {
        "manifest_sha256": digest,
        "decision_id": "1" * 64,
        "decision_contract_sha256": "2" * 64,
        "challenge": "3" * 64,
        "ledger_counter": 2,
        "ledger_prev_hash": "4" * 64,
        "issued_at_ns": 7,
        "verdict": {},
        "service_identity": measurement,
        "consumption_record": proof(consumed),
        "ledger_head": proof({"counter": 2, "record_hash": "5" * 64}),
        "key_id": "verifier",
        "algorithm": "Ed25519",
        "signature": "00" * 64,
    }
    return manifest, config, begin, envelope


def _disable_verifier_signature_checks(monkeypatch, verifier_service):
    class PublicKey:
        @staticmethod
        def from_public_bytes(_raw):
            return PublicKey()

        def verify(self, _signature, _message):
            return None

    monkeypatch.setattr(verifier_service, "Ed25519PublicKey", PublicKey)
    monkeypatch.setattr(verifier_service, "_validate_verdict_schema", lambda _v: None)


def test_verifier_retries_definitely_unsent_verification_request(monkeypatch):
    # PR #1249 review 3744975446: the issued challenge remains safe pre-send.
    from benchmarks.codegraph_compare import verifier_service

    manifest, config, begin, envelope = _verifier_recovery_fixture()
    _disable_verifier_signature_checks(monkeypatch, verifier_service)
    operations = []

    def round_trip(_path, request, _config, _timeout):
        operations.append(request["operation"])
        if request["operation"] == "begin-exact-14":
            return begin
        if operations.count("verify-exact-14") == 1:
            raise verifier_service._PreSendTransportError("unsent")
        return envelope

    monkeypatch.setattr(verifier_service, "_round_trip", round_trip)

    assert (
        verifier_service.request_verdict(
            socket_path=Path("/unused"), manifest=manifest, config=config, timeout=1
        )
        == envelope
    )
    assert operations == ["begin-exact-14", "verify-exact-14", "verify-exact-14"]


def test_verifier_polls_until_ambiguous_request_commits(monkeypatch):
    # PR #1249 review 3744975448: VERIFYING is transient under the original deadline.
    from benchmarks.codegraph_compare import verifier_service

    manifest, config, begin, envelope = _verifier_recovery_fixture()
    _disable_verifier_signature_checks(monkeypatch, verifier_service)
    operations = []

    def round_trip(_path, request, _config, _timeout):
        operations.append(request["operation"])
        if request["operation"] == "begin-exact-14":
            return begin
        raise verifier_service._PostSendTransportError("ambiguous")

    polls = iter(
        (
            verifier_service._VerdictPending("in progress"),
            verifier_service._VerdictPending("not found"),
            envelope,
        )
    )

    def query(**_kwargs):
        value = next(polls)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(verifier_service, "_round_trip", round_trip)
    monkeypatch.setattr(verifier_service, "query_verdict", query)
    monkeypatch.setattr(verifier_service.time, "sleep", lambda _delay: None)

    assert (
        verifier_service.request_verdict(
            socket_path=Path("/unused"), manifest=manifest, config=config, timeout=1
        )
        == envelope
    )
    assert operations == ["begin-exact-14", "verify-exact-14"]


def test_operator_rejects_staged_inventory_with_untrusted_digest(monkeypatch):
    # PR #1249 review 3744975449: digest failure must precede authority use.
    from benchmarks.codegraph_compare import qualification_operator as operator
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    payload = canonical_json_bytes({"repo_id": "repo"})
    monkeypatch.setattr(operator, "validate_receipt_inventory", lambda value: value)

    with pytest.raises(ValueError, match="trusted inventory digest"):
        operator._validate_staged_inventory(payload, "repo", "0" * 64)


def test_decision_parser_accepts_payload_above_receipt_parser_ceiling():
    # PR #1249 review 3744975455: decision parsing must honor its 64 MiB frame.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    padding = "x" * (16 * 1024 * 1024)
    payload = ('{"padding":"' + padding + '"}').encode()

    assert consumer._decision_json_loads(payload) == {"padding": padding}


def test_decision_preflight_rejects_final_frame_before_execution(monkeypatch):
    # PR #1249 review 3744975455: bound the final consume envelope pre-execution.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    monkeypatch.setattr(consumer, "DECISION_ENVELOPE_SCHEMA_OVERHEAD", 0)
    monkeypatch.setattr(consumer, "MAX_FRAME", 10)

    with pytest.raises(ValueError, match="upper bound exceeds frame ceiling"):
        consumer.preflight_decision_consume_request(
            {}, 0, {"closure_manifest": "root-signed-runtime"}
        )


def test_staged_plan_path_rejects_parent_traversal():
    # PR #1249 review 3744975460: receipt paths are canonical before reservation.
    from benchmarks.codegraph_compare.setup_qualification_executor import _bounded_path

    with pytest.raises(ValueError, match="artifact path is not canonical"):
        _bounded_path("../artifact", "artifact path")


_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno


def _qualification_git_repo(path: Path) -> str:
    import subprocess

    path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "main.ts").write_text("export class Main {}\n", encoding="utf-8")
    (path / "generated.ts").write_text("// @generated DO NOT EDIT\n", encoding="utf-8")
    (path / "notes.md").write_text("notes\n", encoding="utf-8")
    (path / "linked.ts").symlink_to("main.ts")
    subprocess.run(
        ["git", "add", "main.ts", "generated.ts", "notes.md", "linked.ts"],
        cwd=path,
        check=True,
    )
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=path, check=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    subprocess.run(
        [
            "git",
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{commit},deps/submodule",
        ],
        cwd=path,
        check=True,
    )
    subprocess.run(["git", "commit", "-qm", "gitlink"], cwd=path, check=True)
    (path / "deps" / "submodule").mkdir(parents=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _qualification_oracles():
    from benchmarks.codegraph_compare.setup_qualification import OracleSpecV1

    return (
        OracleSpecV1(
            "main.symbol", "symbol", (("name", "Main"),), {"path": "main.ts", "line": 1}
        ),
        OracleSpecV1(
            "main.call",
            "call",
            (("callee", "Main"), ("caller", "entry")),
            [{"path": "main.ts"}],
        ),
    )


def _qualification_source_inventory(tmp_path: Path):
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "repo"
    _qualification_git_repo(repo)
    return inventory_sources("vscode", repo, DEFAULT_SOURCE_RULES)


@pytest.mark.parametrize("relative", ("rogue.ts", "qualification-index/artifact.bin"))
def test_source_inventory_rejects_one_untracked_checkout_path(
    tmp_path: Path, relative: str
):
    # PR #1247: a fresh qualification checkout must contain no untracked inputs.
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "repo"
    _qualification_git_repo(repo)
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"untrusted")

    with pytest.raises(ValueError, match="tracked or untracked changes"):
        inventory_sources("vscode", repo, DEFAULT_SOURCE_RULES)


def test_source_inventory_rechecks_exact_full_status_after_blob_scan(tmp_path: Path):
    # PR #1247: checkout cleanliness is snapshotted both before and after inventory.
    import benchmarks.codegraph_compare.setup_qualification_inventory as module
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "repo"
    _qualification_git_repo(repo)
    calls: list[tuple[str, ...]] = []
    original_git = module._git

    def recording_git(path, *arguments, **kwargs):
        calls.append(arguments)
        return original_git(path, *arguments, **kwargs)

    with patch.object(module, "_git", side_effect=recording_git):
        inventory_sources("vscode", repo, DEFAULT_SOURCE_RULES)

    assert (
        calls.count(
            (
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--ignored=matching",
            )
        )
        == 2
    )


def test_source_inventory_rejects_assume_unchanged_flag(tmp_path: Path):
    # PR #1247: status porcelain hides assume-unchanged worktree divergence.
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "repo"
    _qualification_git_repo(repo)
    subprocess.run(
        ["git", "update-index", "--assume-unchanged", "main.ts"],
        cwd=repo,
        check=True,
    )
    (repo / "main.ts").write_text("export class Decoy {}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Hidden tracked index flag"):
        inventory_sources("vscode", repo, DEFAULT_SOURCE_RULES)


def test_source_inventory_rejects_skip_worktree_flag(tmp_path: Path):
    # PR #1247: skip-worktree entries cannot attest bytes consumed by a build.
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "repo"
    _qualification_git_repo(repo)
    subprocess.run(
        ["git", "update-index", "--skip-worktree", "main.ts"],
        cwd=repo,
        check=True,
    )

    with pytest.raises(ValueError, match="Hidden tracked index flag S"):
        inventory_sources("vscode", repo, DEFAULT_SOURCE_RULES)


def test_source_inventory_hashes_eligible_worktree_bytes_against_blob(
    tmp_path: Path,
):
    # PR #1247: build input bytes are verified independently of Git status hints.
    import benchmarks.codegraph_compare.setup_qualification_inventory as module
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "repo"
    _qualification_git_repo(repo)
    pristine_flags = module._tracked_flags(repo)
    subprocess.run(
        ["git", "update-index", "--assume-unchanged", "main.ts"],
        cwd=repo,
        check=True,
    )
    (repo / "main.ts").write_text("export class Decoy {}\n", encoding="utf-8")

    with (
        patch.object(module, "_tracked_flags", return_value=pristine_flags),
        pytest.raises(ValueError, match="worktree bytes do not match pinned blob"),
    ):
        inventory_sources("vscode", repo, DEFAULT_SOURCE_RULES)


def test_source_rules_inventory_tracks_only_regular_files(tmp_path: Path):
    inventory = _qualification_source_inventory(tmp_path)

    assert inventory.tracked_regular_paths == ("generated.ts", "main.ts", "notes.md")


def test_source_rules_inventory_selects_eligible_source(tmp_path: Path):
    inventory = _qualification_source_inventory(tmp_path)

    assert inventory.eligible_paths == ("main.ts",)


def test_source_inventory_requires_canonical_worktree_root(tmp_path: Path):
    # PR #1247: a subdirectory-scoped ls-files result cannot label the full commit.
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "repo"
    _qualification_git_repo(repo)

    with pytest.raises(ValueError, match="canonical Git worktree root"):
        inventory_sources("vscode", repo / "deps", DEFAULT_SOURCE_RULES)


@pytest.mark.parametrize(
    ("path", "reason"),
    (
        ("deps/submodule", "gitlink"),
        ("generated.ts", "generated"),
        ("linked.ts", "symlink"),
        ("notes.md", "extension"),
    ),
)
def test_source_rules_inventory_classifies_one_exclusion(
    tmp_path: Path, path: str, reason: str
):
    inventory = _qualification_source_inventory(tmp_path)

    assert dict(inventory.prefilter_exclusions)[path] == reason


def test_source_rules_inventory_hashes_exact_eligible_paths(tmp_path: Path):
    from benchmarks.codegraph_compare.integrity import _sha256

    inventory = _qualification_source_inventory(tmp_path)

    assert inventory.eligible_paths_hash == _sha256(["main.ts"])


@pytest.mark.parametrize("reserved_id", ("delete", "build", "health"))
def test_cell_plan_rejects_reserved_oracle_execution_ids(
    tmp_path: Path, reserved_id: str
):
    # PR #1247: an oracle must not replace a built-in execution in frozen argv.
    from dataclasses import replace

    from benchmarks.codegraph_compare.setup_qualification import ExecutionSpecV1

    plan = _qualification_plans(tmp_path)[0]
    oracles = (
        replace(plan.oracle_specs[0], oracle_id=reserved_id),
        plan.oracle_specs[1],
    )
    executions = (*plan.executions[:3],) + tuple(
        ExecutionSpecV1(
            spec.oracle_id,
            ("oracle", spec.oracle_id, plan.index_path),
            plan.executions[0].cwd,
            plan.executions[0].environment_digest,
        )
        for spec in oracles
    )

    with pytest.raises(ValueError, match="reserved execution IDs"):
        replace(plan, oracle_specs=oracles, executions=executions)


def test_cell_plan_allows_oracle_id_that_only_contains_reserved_word(tmp_path: Path):
    from dataclasses import replace

    plan = _qualification_plans(tmp_path)[0]
    oracles = (
        replace(plan.oracle_specs[0], oracle_id="delete.oracle"),
        plan.oracle_specs[1],
    )
    executions = (
        *plan.executions[:3],
        replace(plan.executions[3], execution_id="delete.oracle"),
        plan.executions[4],
    )

    replaced = replace(plan, oracle_specs=oracles, executions=executions)

    assert tuple(item.execution_id for item in replaced.executions) == (
        "delete",
        "build",
        "health",
        "delete.oracle",
        "main.call",
    )


def test_execution_spec_rejects_mutable_argv():
    # PR #1247: frozen dataclasses must not retain caller-owned command lists.
    from benchmarks.codegraph_compare.setup_qualification import ExecutionSpecV1

    with pytest.raises(ValueError, match="argv"):
        ExecutionSpecV1(
            "build",
            ["tool", "build"],  # type: ignore[arg-type]
            "/tmp",
            "0" * 64,
        )


def test_oracle_spec_rejects_mutable_query():
    # PR #1247: oracle query allowlists use exact immutable tuples.
    from benchmarks.codegraph_compare.setup_qualification import OracleSpecV1

    with pytest.raises(ValueError, match="immutable string pairs"):
        OracleSpecV1("main.symbol", "symbol", [("name", "Main")], {})  # type: ignore[arg-type]


def test_oracle_expected_result_is_copied_to_canonical_bytes():
    # PR #1247: later caller mutations cannot alter a signed oracle expectation.
    from benchmarks.codegraph_compare.setup_qualification import OracleSpecV1

    supplied = {"matches": [{"line": 1, "path": "main.ts"}]}
    spec = OracleSpecV1("main.symbol", "symbol", (("name", "Main"),), supplied)
    supplied["matches"][0]["line"] = 99

    assert spec.expected_result == b'{"matches":[{"line":1,"path":"main.ts"}]}'


def test_git_batch_parser_uses_size_framing_for_embedded_nul():
    import io

    import benchmarks.codegraph_compare.setup_qualification_inventory as inventory_module

    payload = b"before\0after"
    digest = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    output = f"{digest} blob {len(payload)}".encode() + b"\0" + payload + b"\0"

    assert inventory_module._stream_blob(
        io.BytesIO(output), "source.ts", digest, 0
    ) == (hashlib.sha256(payload).hexdigest(), False, len(payload))


def test_git_blob_generated_marker_is_detected_after_former_prefix_limit():
    # PR #1247: generated markers apply to the complete pinned blob.
    import io

    import benchmarks.codegraph_compare.setup_qualification_inventory as inventory_module

    payload = b"x" * 5000 + b"DO NOT EDIT"
    digest = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    output = f"{digest} blob {len(payload)}".encode() + b"\0" + payload + b"\0"

    assert inventory_module._stream_blob(
        io.BytesIO(output), "generated.ts", digest, 0, (b"DO NOT EDIT",)
    ) == (hashlib.sha256(payload).hexdigest(), True, len(payload))


def test_git_blob_generated_marker_is_detected_across_chunk_boundary():
    # PR #1247: rolling overlap binds markers straddling stream chunks.
    import io

    import benchmarks.codegraph_compare.setup_qualification_inventory as inventory_module

    payload = b"1234567DO NOT EDITtail"
    digest = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    output = f"{digest} blob {len(payload)}".encode() + b"\0" + payload + b"\0"
    with patch.object(inventory_module, "_STREAM_CHUNK_BYTES", 8):
        result = inventory_module._stream_blob(
            io.BytesIO(output), "generated.ts", digest, 0, (b"DO NOT EDIT",)
        )

    assert result == (hashlib.sha256(payload).hexdigest(), True, len(payload))


def test_git_batch_rejects_blob_above_trusted_ceiling():
    import io

    import benchmarks.codegraph_compare.setup_qualification_inventory as inventory_module

    digest = "a" * 40
    output = f"{digest} blob 8".encode() + b"\0"
    with (
        patch.object(inventory_module, "_GIT_BLOB_CEILING_BYTES", 7),
        pytest.raises(ValueError, match="blob exceeds trusted size ceiling"),
    ):
        inventory_module._stream_blob(io.BytesIO(output), "large.ts", digest, 0)


def test_git_batch_rejects_repository_above_trusted_total_ceiling():
    import io

    import benchmarks.codegraph_compare.setup_qualification_inventory as inventory_module

    payload = b"content"
    digest = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    output = f"{digest} blob {len(payload)}".encode() + b"\0"
    with (
        patch.object(inventory_module, "_GIT_TOTAL_CEILING_BYTES", len(payload)),
        pytest.raises(ValueError, match="trusted total size ceiling"),
    ):
        inventory_module._stream_blob(io.BytesIO(output), "source.ts", digest, 1)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda header, payload: header.replace(b" blob ", b" tree ") + payload + b"\0",
        lambda header, payload: (
            header.replace(str(len(payload)).encode(), str(len(payload) + 1).encode())
            + payload
            + b"\0"
        ),
        lambda header, payload: header + payload + b"X",
    ),
)
def test_git_batch_parser_rejects_malformed_type_size_or_terminator(mutate):
    # PR #1247: batch framing must fail closed rather than shift into the next blob.
    import io

    import benchmarks.codegraph_compare.setup_qualification_inventory as inventory_module

    payload = b"content"
    digest = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    header = f"{digest} blob {len(payload)}".encode() + b"\0"

    with pytest.raises(ValueError, match="Git batch"):
        inventory_module._stream_blob(
            io.BytesIO(mutate(header, payload)), "source.ts", digest, 0
        )


def test_git_batch_timeout_kills_and_reaps_process(tmp_path: Path):
    import io
    import time

    import benchmarks.codegraph_compare.setup_qualification_inventory as inventory_module

    class SlowOutput:
        def read(self, _size):
            time.sleep(0.1)
            return b""

    process = Mock(args=["git", "cat-file", "--batch", "-Z"])
    process.stdin = io.BytesIO()
    process.stdout = SlowOutput()
    process.poll.return_value = None
    with (
        patch.object(inventory_module.subprocess, "Popen", return_value=process),
        patch.object(inventory_module, "_GIT_TIMEOUT_SECONDS", 0.01),
    ):
        with pytest.raises(subprocess.TimeoutExpired):
            inventory_module._batch_blob_metadata(tmp_path, (("source.ts", "a" * 40),))

    process.kill.assert_called_once_with()
    process.wait.assert_called_once_with()


def test_large_source_inventory_uses_constant_subprocess_count(tmp_path: Path):
    # PR #1247: process count must not scale with tracked regular blobs.
    import benchmarks.codegraph_compare.setup_qualification_inventory as inventory_module
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "large-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    for number in range(256):
        (repo / f"source-{number:03}.ts").write_text(
            f"export const value{number} = {number};\n", encoding="utf-8"
        )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    real_popen = subprocess.Popen
    starts: list[tuple[str, ...]] = []

    def counted_popen(*args, **kwargs):
        starts.append(tuple(args[0]))
        return real_popen(*args, **kwargs)

    with patch.object(inventory_module.subprocess, "Popen", side_effect=counted_popen):
        result = inventory_sources("vscode", repo, DEFAULT_SOURCE_RULES)

    assert len(result.tracked_regular_paths) == 256
    assert len(starts) == 12
    assert [command[:3] for command in starts].count(
        ("git", "cat-file", "--batch")
    ) == 1
    assert all("hash-object" not in command for command in starts)


def _qualification_verifier_config():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare.setup_qualification_trust import VerifierConfigV1

    return VerifierConfigV1(
        executor_key_id="test-executor",
        executor_public_key=Ed25519PrivateKey.from_private_bytes(b"\x02" * 32)
        .public_key()
        .public_bytes_raw(),
        approver_key_id="test-approver",
        approver_public_key=Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
        .public_key()
        .public_bytes_raw(),
    )


def _qualification_inventories(plans):
    return {plan.repo_id: plan.eligibility for plan in plans}


def test_harness_artifact_rejects_huge_sparse_file(tmp_path: Path):
    # PR #1247: pinned harness verification must not materialize hostile files.
    import pytest

    from benchmarks.codegraph_compare.setup_qualification import HarnessArtifactV1

    sparse = tmp_path / "tool.bin"
    with sparse.open("wb") as stream:
        stream.seek(512 * 1024 * 1024)
        stream.write(b"x")

    with pytest.raises(ValueError, match="trusted size ceiling"):
        HarnessArtifactV1.read(sparse)


def _qualification_plans(tmp_path: Path):
    from dataclasses import replace

    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        EXPECTED_CELLS,
        FROZEN_EXECUTION_ENVIRONMENT_DIGEST,
        CellPlanV1,
        EligibilityV1,
        ExecutionSpecV1,
        HarnessArtifactV1,
        ResourcePlanV1,
    )

    tool_path = tmp_path / "tool.bin"
    config_path = tmp_path / "config.json"
    tool_path.write_bytes(b"pinned executable")
    config_path.write_bytes(b'{"offline":true}')
    tool = HarnessArtifactV1.read(tool_path)
    config = HarnessArtifactV1.read(config_path)
    import yaml

    commits = {
        item["id"]: item["commit"]
        for item in yaml.safe_load(
            Path("benchmarks/codegraph_compare/repos.yaml").read_text(encoding="utf-8")
        )["repos"]
    }
    base = EligibilityV1(
        "vscode",
        DEFAULT_SOURCE_RULES.digest,
        commits["vscode"],
        ("main.ts",),
        (("main.ts", "100644", "a" * 40),),
        (("main.ts", "100644", "a" * 40, 1, "e" * 64),),
        ("main.ts",),
        (),
        "b" * 64,
        "c" * 64,
        "d" * 64,
    )
    resources = ResourcePlanV1(30, 20, 1024, 4096, 1, 1024, 2, 8, 1)
    source_checkout = (tmp_path / "source-checkout").resolve()
    source_checkout.mkdir(exist_ok=True)
    return tuple(
        CellPlanV1(
            repo,
            arm,
            1,
            f"cells/{repo}/{arm}/cell-receipt.json",
            f"cells/{repo}/{arm}/index",
            source_checkout.as_posix(),
            replace(base, repo_id=repo, commit=commits[repo]),
            tool,
            config,
            _qualification_oracles(),
            resources,
            (
                ExecutionSpecV1(
                    "delete",
                    (
                        str(tool_path),
                        "delete",
                        "--config",
                        str(config_path),
                        "--index",
                        (tmp_path / "cells" / repo / arm / "index")
                        .resolve()
                        .as_posix(),
                    ),
                    tmp_path.resolve().as_posix(),
                    FROZEN_EXECUTION_ENVIRONMENT_DIGEST,
                ),
                ExecutionSpecV1(
                    "build",
                    (
                        str(tool_path),
                        "build",
                        "--config",
                        str(config_path),
                        "--source",
                        source_checkout.as_posix(),
                        "--index",
                        (tmp_path / "cells" / repo / arm / "index")
                        .resolve()
                        .as_posix(),
                    ),
                    source_checkout.as_posix(),
                    FROZEN_EXECUTION_ENVIRONMENT_DIGEST,
                ),
                ExecutionSpecV1(
                    "health",
                    (
                        str(tool_path),
                        "health",
                        "--config",
                        str(config_path),
                        "--index",
                        (tmp_path / "cells" / repo / arm / "index")
                        .resolve()
                        .as_posix(),
                    ),
                    tmp_path.resolve().as_posix(),
                    FROZEN_EXECUTION_ENVIRONMENT_DIGEST,
                ),
                *(
                    ExecutionSpecV1(
                        spec.oracle_id,
                        (
                            str(tool_path),
                            spec.kind,
                            "--config",
                            str(config_path),
                            *sum(
                                ((f"--{key}", value) for key, value in spec.query),
                                (),
                            ),
                            "--index",
                            (tmp_path / "cells" / repo / arm / "index")
                            .resolve()
                            .as_posix(),
                        ),
                        tmp_path.resolve().as_posix(),
                        FROZEN_EXECUTION_ENVIRONMENT_DIGEST,
                    )
                    for spec in _qualification_oracles()
                ),
            ),
        )
        for repo, arm in EXPECTED_CELLS
    )


def _write_valid_qualification_receipt(cell_root: Path, plan):
    import json
    from dataclasses import asdict

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    import benchmarks.codegraph_compare.setup_qualification as qualification
    from benchmarks.codegraph_compare.integrity import _sha256
    from benchmarks.codegraph_compare.setup_qualification import (
        ZERO_COUNTERS,
        _bytes_hash,
        _hash_tree,
    )

    verifier_config = _qualification_verifier_config()

    def sign(seed: bytes, payload):
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return Ed25519PrivateKey.from_private_bytes(seed * 32).sign(encoded).hex()

    cell_root.mkdir(parents=True, exist_ok=False)
    # The externally sealed snapshot includes the already-created receipt inode.
    (cell_root / "cell-receipt.json").touch()
    index = cell_root / "index"
    index.mkdir()
    (index / "index.bin").write_bytes(b"frozen index")

    def blob(relative: str, payload: bytes):
        path = cell_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return {
            "path": relative,
            "size_bytes": len(payload),
            "sha256": _bytes_hash(payload),
        }

    executions = []
    specs = {spec.oracle_id: spec for spec in plan.oracle_specs}
    for number, execution in enumerate(plan.executions):
        identifier = execution.execution_id
        spec = specs.get(identifier)
        stdout = b"{}" if spec is None else spec.expected_result
        query = (
            b"{}"
            if spec is None
            else json.dumps(
                dict(spec.query), sort_keys=True, separators=(",", ":")
            ).encode()
        )
        item = {
            "id": identifier,
            "argv": list(execution.argv),
            "cwd": execution.cwd,
            "exit_code": 0,
            "environment_digest": execution.environment_digest,
            "stdout_bytes": blob(f"raw/{number}-stdout", stdout),
            "stderr_bytes": blob(f"raw/{number}-stderr", b""),
            "query_bytes": blob(f"raw/{number}-query", query),
            "index_bytes": blob(f"raw/{number}-index", b"frozen index"),
        }
        if spec is not None:
            item["oracle_spec_hash"] = spec.digest
        executions.append(item)
    audit_blob = blob("raw/os-audit", b"deny sockets; process tree audited")
    approval_blob = blob("raw/human-approval", b"approved oracle set")
    snapshot_payload = {
        "schema_version": 1,
        "plan_hash": plan.digest,
        "snapshot_id": f"snapshot-{plan.repo_id}-{plan.arm_id}",
        "root_identity": list(
            qualification._stable_directory_identity(cell_root.stat())
        ),
        "mount": {"read_only": True},
        "producer_descendants": 0,
        "writes_blocked": True,
    }
    receipt = {
        "schema_version": 2,
        "repo_id": plan.repo_id,
        "arm_id": plan.arm_id,
        "attempt": 1,
        "plan_hash": plan.digest,
        "artifact_path": plan.artifact_path,
        "eligibility": json.loads(json.dumps(asdict(plan.eligibility))),
        "tool": asdict(plan.tool),
        "config": asdict(plan.config),
        "counters": dict(ZERO_COUNTERS),
        "resource_plan_hash": plan.resources.digest,
        "resource_observation": {
            "wall_seconds": 1,
            "cpu_seconds": 1,
            "index_bytes": 12,
            "disk_written_bytes": 128,
            "free_disk_bytes_before": 2,
            "peak_rss_bytes": 512,
            "peak_processes": 1,
            "peak_open_files": 4,
            "peak_concurrency": 1,
        },
        "index_path": plan.index_path,
        "index_content_hash": _hash_tree(index),
        "index_partition": {
            "indexed_paths": sorted(
                set(plan.eligibility.eligible_paths)
                - set(plan.explicit_excluded_allowlist)
                - set(plan.parse_error_allowlist)
            ),
            "excluded_paths": list(plan.explicit_excluded_allowlist),
            "parse_error_paths": list(plan.parse_error_allowlist),
            "parse_error_allowlist": list(plan.parse_error_allowlist),
            "indexed_paths_hash": _sha256(
                sorted(
                    set(plan.eligibility.eligible_paths)
                    - set(plan.explicit_excluded_allowlist)
                    - set(plan.parse_error_allowlist)
                )
            ),
            "excluded_paths_hash": _sha256(list(plan.explicit_excluded_allowlist)),
            "parse_error_paths_hash": _sha256(list(plan.parse_error_allowlist)),
        },
        "raw_executions": executions,
        "snapshot_audit": {
            "payload": snapshot_payload,
            "key_id": verifier_config.executor_key_id,
            "signature": sign(b"\x02", snapshot_payload),
        },
        "index_provenance": {},
        "os_audit": {
            "network_denied": True,
            "credentials_stripped": True,
            "descendants_observed": True,
            "process_audited": True,
            "audit_bytes": audit_blob,
        },
        "human_oracle_approval": {
            "approved": True,
            "approval_bytes": approval_blob,
        },
    }
    core = qualification._evidence_core_payload(
        receipt, plan=plan, actual_index_hash=_hash_tree(index)
    )
    core_digest = _bytes_hash(qualification._canonical_json_bytes(core))
    executor_payload = {
        "schema_version": 1,
        "plan_hash": plan.digest,
        "evidence_core_digest": core_digest,
    }
    receipt["index_provenance"] = {
        "payload": executor_payload,
        "key_id": verifier_config.executor_key_id,
        "signature": sign(b"\x02", executor_payload),
    }
    receipt["os_audit"].update(
        {
            "payload": executor_payload,
            "key_id": verifier_config.executor_key_id,
            "signature": sign(b"\x02", executor_payload),
        }
    )
    approval_payload = {
        "schema_version": 1,
        "plan_hash": plan.digest,
        "evidence_core_digest": core_digest,
        "approved": True,
        "approval_blob_hash": approval_blob["sha256"],
    }
    receipt["human_oracle_approval"].update(
        {
            "payload": approval_payload,
            "key_id": verifier_config.approver_key_id,
            "signature": sign(b"\x01", approval_payload),
        }
    )
    receipt["receipt_hash"] = _sha256(receipt)
    (cell_root / "cell-receipt.json").write_text(
        json.dumps(receipt, sort_keys=True), encoding="utf-8"
    )
    return receipt


def _validate_qualification_receipt(
    receipt, *, plan, cell_root, verifier_config, sync_retained=True
):
    from benchmarks.codegraph_compare.setup_qualification import (
        _open_root,
        _stable_directory_identity,
        validate_cell_receipt,
    )

    if sync_retained:
        (cell_root / "cell-receipt.json").write_text(
            json.dumps(receipt, sort_keys=True), encoding="utf-8"
        )
    experiment_root = cell_root.parent
    root_fd = _open_root(experiment_root)
    try:
        return validate_cell_receipt(
            receipt,
            plan=plan,
            cell_root=cell_root,
            verifier_config=verifier_config,
            trusted_root_fd=root_fd,
            trusted_root_identity=_stable_directory_identity(os.fstat(root_fd)),
            cell_relative=cell_root.name,
        )
    finally:
        os.close(root_fd)


def _resign_qualification_receipt(receipt):
    from benchmarks.codegraph_compare.integrity import _sha256

    receipt.pop("receipt_hash", None)
    receipt["receipt_hash"] = _sha256(receipt)
    return receipt


def test_canonical_path_rejects_alias_and_escape_mutations():
    import pytest

    from benchmarks.codegraph_compare.setup_qualification import canonical_relative_path

    rejected = (
        "../outside.ts",
        "dir/../outside.ts",
        "dir\\outside.ts",
        "./main.ts",
        "main.ts\x00x",
    )
    errors = []
    for value in rejected:
        with pytest.raises(ValueError) as caught:
            canonical_relative_path(value)
        errors.append(str(caught.value).split(":", 1)[0])

    assert tuple(errors) == ("Non-canonical POSIX path",) * 5


def test_producer_refuses_self_reported_collector_evidence():
    import pytest

    from benchmarks.codegraph_compare.setup_qualification import produce_strict_cell

    with pytest.raises(RuntimeError, match="NOT_EVALUATED"):
        produce_strict_cell(collector=object())


def test_strict_validator_accepts_complete_plan_bound_e0_receipt(tmp_path: Path):
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)

    assert (
        _validate_qualification_receipt(
            receipt,
            plan=plan,
            cell_root=cell_root,
            verifier_config=_qualification_verifier_config(),
        )
        == ()
    )


def test_strict_validator_rejects_source_eligibility_mutation(tmp_path: Path):
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    mutated = copy.deepcopy(receipt)
    mutated["eligibility"]["eligible_paths"] = []
    _resign_qualification_receipt(mutated)

    assert _validate_qualification_receipt(
        mutated,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "SOURCE_ELIGIBILITY_MISMATCH",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_resource_observation_mutation(tmp_path: Path):
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    mutated = copy.deepcopy(receipt)
    mutated["resource_observation"]["peak_processes"] = 3
    _resign_qualification_receipt(mutated)

    assert _validate_qualification_receipt(
        mutated,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RESOURCE_LIMIT_VIOLATION",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_raw_stdout_mutation(tmp_path: Path):
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    (cell_root / "raw/0-stdout").write_bytes(b"mutated")

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == ("RAW_EXECUTION_EVIDENCE_MISSING",)


def test_strict_validator_rejects_scalar_execution_without_crashing(tmp_path: Path):
    # PR #1247: malformed direct receipts must fail closed at the schema boundary.

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    receipt["raw_executions"].append(7)
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RECEIPT_SCHEMA_MISMATCH",
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_blob_above_trusted_per_blob_ceiling(tmp_path: Path):
    # PR #1247: producer-controlled blob metadata must not authorize large reads.
    from benchmarks.codegraph_compare.setup_qualification import (
        _bytes_hash,
    )

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    blob = receipt["raw_executions"][0]["stdout_bytes"]
    payload = b"x" * (plan.resources.max_index_bytes + 1)
    (cell_root / blob["path"]).write_bytes(payload)
    blob.update(size_bytes=len(payload), sha256=_bytes_hash(payload))
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_cumulative_blob_bytes_above_plan(tmp_path: Path):
    # PR #1247: individually bounded blobs must also share a trusted total budget.
    from dataclasses import replace

    from benchmarks.codegraph_compare.setup_qualification import (
        _bytes_hash,
    )

    base_plan = _qualification_plans(tmp_path)[0]
    plan = replace(
        base_plan,
        resources=replace(base_plan.resources, max_disk_write_bytes=1500),
    )
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    for execution in receipt["raw_executions"][:2]:
        blob = execution["stdout_bytes"]
        payload = b"x" * 900
        (cell_root / blob["path"]).write_bytes(payload)
        blob.update(size_bytes=len(payload), sha256=_bytes_hash(payload))
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_sparse_execution_blob(tmp_path: Path):
    # PR #1247: sparse raw evidence must be rejected before hashing or loading.
    from benchmarks.codegraph_compare.setup_qualification import (
        _bytes_hash,
    )

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    blob = receipt["raw_executions"][0]["stdout_bytes"]
    sparse = cell_root / blob["path"]
    with sparse.open("wb") as stream:
        stream.truncate(512)
    if sparse.stat().st_blocks * 512 >= sparse.stat().st_size:
        pytest.skip("tracked: filesystem does not represent sparse allocation")
    payload = b"\x00" * 512
    blob.update(size_bytes=len(payload), sha256=_bytes_hash(payload))
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_unplanned_explicit_exclusion(tmp_path: Path):
    # PR #1247: exclusions are an independent, plan-bound partition category.
    from benchmarks.codegraph_compare.integrity import _sha256

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    partition = receipt["index_partition"]
    partition["indexed_paths"] = []
    partition["indexed_paths_hash"] = _sha256([])
    partition["excluded_paths"] = ["main.ts"]
    partition["excluded_paths_hash"] = _sha256(["main.ts"])
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "INDEX_PARTITION_MISMATCH",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_accepts_exact_plan_bound_explicit_exclusion(tmp_path: Path):
    # PR #1247: explicit exclusions are frozen separately from parse errors.
    from dataclasses import replace

    base_plan = _qualification_plans(tmp_path)[0]
    plan = replace(base_plan, explicit_excluded_allowlist=("main.ts",))
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)

    assert (
        _validate_qualification_receipt(
            receipt,
            plan=plan,
            cell_root=cell_root,
            verifier_config=_qualification_verifier_config(),
        )
        == ()
    )


def test_oracle_spec_rejects_duplicate_query_key():
    # PR #1247: dict conversion must not discard an earlier frozen query value.
    from benchmarks.codegraph_compare.setup_qualification import OracleSpecV1

    with pytest.raises(ValueError, match="parameter keys"):
        OracleSpecV1(
            "duplicate.query",
            "symbol",
            (("name", "A"), ("name", "B")),
            {"path": "main.ts"},
        )


def test_direct_receipt_rejects_excessive_nesting_without_recursion_error(
    tmp_path: Path,
):
    # PR #1247: direct objects are bounded before recursive canonical hashing.

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    nested: object = "leaf"
    for _ in range(130):
        nested = [nested]
    receipt["eligibility"]["eligible_paths"] = nested

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == ("RECEIPT_SCHEMA_MISMATCH",)


def test_direct_receipt_rejects_excessive_node_count_before_hash(tmp_path: Path):
    # PR #1247: direct-object node limits are trusted independently of parser limits.
    import benchmarks.codegraph_compare.setup_qualification_schema as schema

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    receipt["eligibility"]["eligible_paths"] = ["main.ts", "extra.ts"]

    with patch.object(schema, "_MAX_STRICT_JSON_NODES", 10):
        failures = _validate_qualification_receipt(
            receipt,
            plan=plan,
            cell_root=cell_root,
            verifier_config=_qualification_verifier_config(),
        )

    assert failures == ("RECEIPT_SCHEMA_MISMATCH",)


@pytest.mark.parametrize(
    "query_key",
    ("config", "--INDEX", "source_path", "cwd", "tool-path"),
)
def test_oracle_spec_rejects_harness_owned_query_flags(query_key: str):
    # PR #1247: query expansion cannot override harness-selected execution inputs.
    from benchmarks.codegraph_compare.setup_qualification import OracleSpecV1

    with pytest.raises(ValueError, match="harness-owned flags"):
        OracleSpecV1(
            "reserved.query",
            "symbol",
            ((query_key, "decoy"),),
            {"matches": []},
        )


def test_oracle_spec_rejects_query_flag_normalization_collision():
    # PR #1247: syntactic aliases must not produce duplicate parser options.
    from benchmarks.codegraph_compare.setup_qualification import OracleSpecV1

    with pytest.raises(ValueError, match="collide after normalization"):
        OracleSpecV1(
            "alias.query",
            "symbol",
            (("foo-bar", "one"), ("foo_bar", "two")),
            {"matches": []},
        )


def test_cell_plan_rejects_noncanonical_execution_cwd(tmp_path: Path):
    # PR #1247: every frozen command is bound to an authenticated working directory.
    from dataclasses import replace

    plan = _qualification_plans(tmp_path)[0]
    changed = replace(plan.executions[2], cwd=plan.source_checkout_path)

    with pytest.raises(ValueError, match="trusted experiment root"):
        replace(plan, executions=(*plan.executions[:2], changed, *plan.executions[3:]))


def test_strict_validator_rejects_execution_cwd_mutation(tmp_path: Path):
    # PR #1247: a receipt cannot relocate an otherwise exact frozen command.
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = copy.deepcopy(_write_valid_qualification_receipt(cell_root, plan))
    receipt["raw_executions"][0]["cwd"] = plan.source_checkout_path
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_execution_environment_mutation(tmp_path: Path):
    # PR #1247: receipt environment evidence must equal the frozen plan digest.
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = copy.deepcopy(_write_valid_qualification_receipt(cell_root, plan))
    receipt["raw_executions"][0]["environment_digest"] = "0" * 64
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


@pytest.mark.parametrize(
    "index_path",
    (
        "cells/vscode/tsa-warm",
        "cells/vscode/tsa-warm/index/shard",
        "cells/vscode/tsa-warm/raw",
        "cells/vscode/tsa-warm/raw/index",
        "cells/vscode/tsa-warm/cell-receipt.json",
        "plan.json",
        "manifest/index",
    ),
)
def test_cell_plan_rejects_nonexact_or_reserved_index_path(
    tmp_path: Path, index_path: str
):
    # PR #1247: index output cannot overlap retained evidence or control documents.
    from dataclasses import replace

    plan = _qualification_plans(tmp_path)[0]

    with pytest.raises(ValueError, match="Index path"):
        replace(plan, index_path=index_path)


def test_direct_json_bounds_rejects_string_above_utf8_ceiling():
    # PR #1247: direct receipts get the same scalar allocation boundary as bytes.
    from benchmarks.codegraph_compare.setup_qualification_schema import (
        validate_direct_json_bounds,
    )

    with pytest.raises(ValueError, match="UTF-8 byte ceiling"):
        validate_direct_json_bounds("x" * (1024 * 1024 + 1))


def test_direct_json_bounds_rejects_integer_above_bit_ceiling():
    # PR #1247: hashing never formats an attacker-sized direct integer.
    from benchmarks.codegraph_compare.setup_qualification_schema import (
        validate_direct_json_bounds,
    )

    with pytest.raises(ValueError, match="bit ceiling"):
        validate_direct_json_bounds(1 << 16_384)


def test_direct_json_bounds_rejects_integer_above_digit_ceiling():
    # PR #1247: decimal conversion is bounded independently of integer bit size.
    from benchmarks.codegraph_compare.setup_qualification_schema import (
        validate_direct_json_bounds,
    )

    with pytest.raises(ValueError, match="digit ceiling"):
        validate_direct_json_bounds(10**4096)


def test_direct_json_bounds_rejects_aggregate_scalar_budget():
    # PR #1247: many individually valid strings share one encoded byte budget.
    import benchmarks.codegraph_compare.setup_qualification_schema as schema

    with patch.object(schema, "_MAX_DIRECT_ENCODED_SCALAR_BYTES", 15):
        with pytest.raises(ValueError, match="aggregate encoded scalar budget"):
            schema.validate_direct_json_bounds(["123456", "abcdef"])


def test_direct_receipt_scalar_bounds_run_before_hashing(tmp_path: Path):
    # PR #1247: direct receipt bounds precede canonical hashing and hex decoding.
    import benchmarks.codegraph_compare.setup_qualification_validation as validation

    plan = _qualification_plans(tmp_path)[0]
    receipt = _write_valid_qualification_receipt(tmp_path / "cell", plan)
    receipt["receipt_hash"] = "x" * (1024 * 1024 + 1)

    with patch.object(validation, "_sha256", side_effect=AssertionError("hashed")):
        failures = validation.validate_cell_receipt(
            receipt,
            plan=plan,
            cell_root=tmp_path / "cell",
            verifier_config=_qualification_verifier_config(),
        )

    assert failures == ("RECEIPT_SCHEMA_MISMATCH",)


def test_strict_validator_rejects_index_root_symlink(tmp_path: Path):
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "index.bin").write_bytes(b"frozen index")
    for child in (cell_root / "index").iterdir():
        child.unlink()
    (cell_root / "index").rmdir()
    (cell_root / "index").symlink_to(outside, target_is_directory=True)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "SNAPSHOT_AUDIT_MISSING",
        "INDEX_BYTES_MISMATCH",
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_harness_config_byte_mutation(tmp_path: Path):
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    Path(plan.config.path).write_bytes(b"mutated config")

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == ("HARNESS_BYTES_MISMATCH",)


def test_strict_validator_rejects_network_audit_mutation(tmp_path: Path):
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    mutated = copy.deepcopy(receipt)
    mutated["os_audit"]["network_denied"] = False
    _resign_qualification_receipt(mutated)

    assert _validate_qualification_receipt(
        mutated,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


@pytest.mark.parametrize(
    ("path", "value", "expected"),
    (
        (
            ("repo_id",),
            "django",
            (
                "CELL_IDENTITY_MISMATCH",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (
            ("attempt",),
            2,
            (
                "RECEIPT_SCHEMA_MISMATCH",
                "CELL_IDENTITY_MISMATCH",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (("plan_hash",), "0" * 64, "PLAN_BINDING_MISMATCH"),
        (
            ("artifact_path",),
            "cells/foreign/cell-receipt.json",
            (
                "PLAN_BINDING_MISMATCH",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (
            ("counters", "model_calls"),
            1,
            (
                "FORBIDDEN_COUNTER_MISMATCH",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (
            ("resource_plan_hash",),
            "0" * 64,
            (
                "RESOURCE_EVIDENCE_MISSING",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (
            ("resource_observation", "cpu_seconds"),
            21,
            (
                "RESOURCE_LIMIT_VIOLATION",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (
            ("raw_executions", 0, "id"),
            "foreign",
            (
                "RECEIPT_SCHEMA_MISMATCH",
                "RAW_EXECUTION_EVIDENCE_MISSING",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (
            ("raw_executions", 0, "exit_code"),
            1,
            (
                "RAW_EXECUTION_EVIDENCE_MISSING",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (
            ("raw_executions", 0, "argv"),
            [],
            (
                "RECEIPT_SCHEMA_MISMATCH",
                "RAW_EXECUTION_EVIDENCE_MISSING",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (
            ("os_audit", "credentials_stripped"),
            False,
            (
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (
            ("os_audit", "descendants_observed"),
            False,
            (
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (("human_oracle_approval", "approved"), False, "HUMAN_ORACLE_APPROVAL_MISSING"),
        (
            ("human_oracle_approval", "key_id"),
            "",
            ("RECEIPT_SCHEMA_MISMATCH", "HUMAN_ORACLE_APPROVAL_MISSING"),
        ),
        (
            ("index_content_hash",),
            "0" * 64,
            (
                "INDEX_BYTES_MISMATCH",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
    ),
)
def test_strict_validator_rejects_one_receipt_boundary_mutation(
    tmp_path: Path, path, value, expected
):
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    mutated = copy.deepcopy(_write_valid_qualification_receipt(cell_root, plan))
    target = mutated
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    _resign_qualification_receipt(mutated)

    wanted = expected if isinstance(expected, tuple) else (expected,)
    assert (
        _validate_qualification_receipt(
            mutated,
            plan=plan,
            cell_root=cell_root,
            verifier_config=_qualification_verifier_config(),
        )
        == wanted
    )


def test_source_inventory_is_exactly_bound_to_git_modes_objects_and_bytes(
    tmp_path: Path,
):
    import hashlib
    import subprocess
    from dataclasses import asdict

    from benchmarks.codegraph_compare.integrity import _sha256
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "repo"
    commit = _qualification_git_repo(repo)
    raw_records = subprocess.run(
        ["git", "ls-files", "-z", "--stage"],
        cwd=repo,
        capture_output=True,
        check=True,
    ).stdout
    records = []
    for raw in raw_records.split(b"\0"):
        if raw:
            metadata, encoded = raw.split(b"\t", 1)
            mode, object_id, _stage = metadata.decode("ascii").split(" ")
            records.append((encoded.decode(), mode, object_id))
    records.sort()
    regular = tuple(item for item in records if item[1] in {"100644", "100755"})
    file_hashes = [
        (path, mode, object_id, hashlib.sha256((repo / path).read_bytes()).hexdigest())
        for path, mode, object_id in regular
    ]

    root_tree_id = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=repo,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    assert asdict(inventory_sources("vscode", repo, DEFAULT_SOURCE_RULES)) == {
        "repo_id": "vscode",
        "source_rules_hash": DEFAULT_SOURCE_RULES.digest,
        "commit": commit,
        "tracked_regular_paths": ("generated.ts", "main.ts", "notes.md"),
        "tracked_entries": tuple(records),
        "root_tree_id": root_tree_id,
        "tracked_files": tuple(
            (path, mode, object_id, (repo / path).stat().st_size, content_hash)
            for path, mode, object_id, content_hash in file_hashes
        ),
        "eligible_paths": ("main.ts",),
        "prefilter_exclusions": (
            ("deps/submodule", "gitlink"),
            ("generated.ts", "generated"),
            ("linked.ts", "symlink"),
            ("notes.md", "extension"),
        ),
        "tracked_inventory_hash": _sha256(records),
        "eligible_paths_hash": _sha256(["main.ts"]),
        "repo_fingerprint": _sha256(
            {"commit": commit, "inventory": records, "files": file_hashes}
        ),
    }


def test_index_tree_hash_binds_exact_paths_and_bytes(tmp_path: Path):
    import hashlib

    from benchmarks.codegraph_compare.setup_qualification import _hash_tree

    index = tmp_path / "index"
    (index / "nested").mkdir(parents=True)
    (index / "a.bin").write_bytes(b"a")
    (index / "nested/b.bin").write_bytes(b"bb")
    digest = hashlib.sha256()
    for relative, payload in ((b"a.bin", b"a"), (b"nested/b.bin", b"bb")):
        digest.update(b"F" + len(relative).to_bytes(8, "big") + relative)
        digest.update(len(payload).to_bytes(8, "big") + payload)
    directory = b"nested"
    digest.update(b"D" + len(directory).to_bytes(8, "big") + directory)
    digest.update(b"C" + (2).to_bytes(8, "big") + (1).to_bytes(8, "big"))

    assert _hash_tree(index) == digest.hexdigest()


def test_index_tree_hash_binds_empty_directory_mutation(tmp_path: Path):
    # PR #1247: empty index shards are topology, even though they contain no bytes.
    from benchmarks.codegraph_compare.setup_qualification import _hash_tree

    index = tmp_path / "index"
    index.mkdir()
    before = _hash_tree(index)
    (index / "empty-shard").mkdir()

    assert _hash_tree(index) != before


def test_index_tree_breadth_is_rejected_before_unbounded_sort(tmp_path: Path):
    # PR #1247: each scandir is collected only to the remaining ceiling plus one.
    import pytest

    from benchmarks.codegraph_compare import setup_qualification_paths as paths

    index = tmp_path / "index"
    index.mkdir()
    for number in range(5):
        (index / f"{number}.bin").write_bytes(b"x")
    root_fd = paths._open_root(index)
    try:
        with pytest.raises(ValueError, match="entry count ceiling"):
            paths._visit_tree(root_fd, lambda _fd, _path: None, max_entries=3)
    finally:
        os.close(root_fd)


def test_index_tree_enumeration_checks_deadline_before_chunk_sort(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3745026816: wide directories cannot hide an expired deadline.
    from benchmarks.codegraph_compare import setup_qualification_paths as paths

    index = tmp_path / "index"
    index.mkdir()
    for number in range(256):
        (index / f"{number:03d}").write_bytes(b"")
    root_fd = paths._open_root(index)
    monkeypatch.setattr(
        paths, "time", SimpleNamespace(monotonic=iter((0.0, 1.0)).__next__)
    )
    try:
        with pytest.raises(TimeoutError, match="traversal deadline"):
            paths._visit_tree(
                root_fd,
                lambda _fd, _path: None,
                deadline_monotonic=0.5,
            )
    finally:
        os.close(root_fd)


def test_index_tree_rejects_directory_topology_race(tmp_path: Path):
    # PR #1247: directory pre/post metadata must bind one topology snapshot.
    import pytest

    from benchmarks.codegraph_compare import setup_qualification_paths as paths

    index = tmp_path / "index"
    index.mkdir()
    (index / "first.bin").write_bytes(b"x")
    root_fd = paths._open_root(index)

    def mutate(_descriptor: int, _relative: str) -> None:
        (index / "late.bin").write_bytes(b"y")

    try:
        with pytest.raises(ValueError, match="directory changed while hashing"):
            paths._visit_tree(root_fd, mutate)
    finally:
        os.close(root_fd)


def test_index_snapshot_returns_hash_bytes_and_exact_counts(tmp_path: Path):
    # PR #1247: hash, size, and topology counts come from one traversal.
    from benchmarks.codegraph_compare import setup_qualification_paths as paths

    index = tmp_path / "index"
    (index / "nested").mkdir(parents=True)
    (index / "a.bin").write_bytes(b"a")
    (index / "nested/b.bin").write_bytes(b"bb")
    root_fd = paths._open_root(tmp_path)
    try:
        snapshot = paths._snapshot_tree_at(root_fd, "index")
    finally:
        os.close(root_fd)

    assert snapshot == (paths._hash_tree(index), 3, 1, 2)


def test_index_tree_hash_rejects_concurrent_append(tmp_path: Path, monkeypatch):
    # PR #1247: a producer must not extend the verifier's snapshotted read.
    import os
    import threading

    import pytest

    from benchmarks.codegraph_compare import setup_qualification_paths as paths

    index = tmp_path / "index"
    index.mkdir()
    target = index / "artifact.bin"
    target.write_bytes(b"a" * (paths._HASH_CHUNK_BYTES + 1))
    append_requested = threading.Event()
    appended = threading.Event()
    real_read = os.read

    def append() -> None:
        assert append_requested.wait(timeout=2)
        with target.open("ab") as stream:
            stream.write(b"growth")
            stream.flush()
            os.fsync(stream.fileno())
        appended.set()

    writer = threading.Thread(target=append)
    writer.start()
    first_read = True

    def coordinated_read(descriptor: int, size: int) -> bytes:
        nonlocal first_read
        if first_read and size == paths._HASH_CHUNK_BYTES:
            first_read = False
            append_requested.set()
            assert appended.wait(timeout=2)
        return real_read(descriptor, size)

    monkeypatch.setattr(paths.os, "read", coordinated_read)
    try:
        with pytest.raises(ValueError, match="grew while hashing"):
            paths._hash_tree(index)
    finally:
        writer.join(timeout=2)

    assert writer.is_alive() is False


def test_index_tree_hash_handles_one_thousand_directory_levels(tmp_path: Path):
    # PR #1247: producer-controlled depth must not consume Python recursion.
    import hashlib
    import os

    from benchmarks.codegraph_compare.setup_qualification import _hash_tree

    index = tmp_path / "index"
    index.mkdir()
    root_fd = os.open(index, os.O_RDONLY | os.O_DIRECTORY)
    current = os.dup(root_fd)
    try:
        for _ in range(1000):
            os.mkdir("d", dir_fd=current)
            child = os.open("d", os.O_RDONLY | os.O_DIRECTORY, dir_fd=current)
            os.close(current)
            current = child
        descriptor = os.open(
            "leaf.bin", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=current
        )
        os.write(descriptor, b"deep")
        os.close(descriptor)
    finally:
        os.close(current)

    digest = hashlib.sha256()
    relative = "/".join(("d",) * 1000 + ("leaf.bin",)).encode()
    digest.update(b"F" + len(relative).to_bytes(8, "big") + relative)
    digest.update((4).to_bytes(8, "big") + b"deep")
    for depth in range(1000, 0, -1):
        directory = "/".join(("d",) * depth).encode()
        digest.update(b"D" + len(directory).to_bytes(8, "big") + directory)
    digest.update(b"C" + (1).to_bytes(8, "big") + (1000).to_bytes(8, "big"))
    try:
        assert _hash_tree(index) == digest.hexdigest()
    finally:
        descriptors = [os.dup(root_fd)]
        try:
            for _ in range(1000):
                descriptors.append(
                    os.open("d", os.O_RDONLY | os.O_DIRECTORY, dir_fd=descriptors[-1])
                )
            os.unlink("leaf.bin", dir_fd=descriptors[-1])
            for number in range(999, -1, -1):
                os.rmdir("d", dir_fd=descriptors[number])
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)
            os.close(root_fd)


def test_index_tree_hash_rejects_same_size_concurrent_rewrite(
    tmp_path: Path, monkeypatch
):
    # PR #1247: size stability alone must not authenticate mutable index bytes.
    import os

    import pytest

    from benchmarks.codegraph_compare import setup_qualification_paths as paths

    index = tmp_path / "index"
    index.mkdir()
    target = index / "artifact.bin"
    target.write_bytes(b"original")
    real_read = os.read
    rewritten = False

    def coordinated_read(descriptor: int, size: int) -> bytes:
        nonlocal rewritten
        if size == 1 and not rewritten:
            rewritten = True
            with target.open("r+b") as stream:
                stream.write(b"modified")
                stream.flush()
                os.fsync(stream.fileno())
        return real_read(descriptor, size)

    monkeypatch.setattr(paths.os, "read", coordinated_read)

    with pytest.raises(ValueError, match="changed while hashing"):
        paths._hash_tree(index)

    assert rewritten is True


def test_resource_plan_rejects_each_missing_ceiling():
    from dataclasses import fields

    import pytest

    from benchmarks.codegraph_compare.setup_qualification import ResourcePlanV1

    valid = {
        "wall_timeout_seconds": 30,
        "max_cpu_seconds": 20,
        "max_index_bytes": 1024,
        "max_disk_write_bytes": 4096,
        "min_free_disk_bytes": 1,
        "max_rss_bytes": 1024,
        "max_processes": 2,
        "max_open_files": 8,
        "max_concurrency": 1,
    }
    rejected = []
    for field in fields(ResourcePlanV1):
        values = dict(valid)
        values[field.name] = 0 if field.name != "max_concurrency" else 2
        with pytest.raises(ValueError, match="resource ceiling"):
            ResourcePlanV1(**values)
        rejected.append(field.name)

    assert tuple(rejected) == tuple(valid)


@pytest.mark.parametrize(
    ("value", "canonicalization_failure"),
    ((float("nan"), True), (float("inf"), True), (True, False)),
)
def test_strict_validator_rejects_nonfinite_or_boolean_resource_value(
    tmp_path: Path, value, canonicalization_failure
):
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = copy.deepcopy(_write_valid_qualification_receipt(cell_root, plan))
    receipt["resource_observation"]["wall_seconds"] = value
    _resign_qualification_receipt(receipt)
    expected = (
        ("RECEIPT_SCHEMA_MISMATCH",)
        if canonicalization_failure
        else (
            "RECEIPT_SCHEMA_MISMATCH",
            "RESOURCE_LIMIT_VIOLATION",
            "INDEX_PROVENANCE_MISSING",
            "OS_AUDIT_MISSING",
            "HUMAN_ORACLE_APPROVAL_MISSING",
        )
    )
    assert (
        _validate_qualification_receipt(
            receipt,
            plan=plan,
            cell_root=cell_root,
            verifier_config=_qualification_verifier_config(),
        )
        == expected
    )


def test_strict_validator_rejects_unknown_schema_version(tmp_path: Path):
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    receipt["schema_version"] = 1
    _resign_qualification_receipt(receipt)
    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == ("RECEIPT_SCHEMA_MISMATCH",)


def test_strict_validator_rejects_incomplete_index_partition(tmp_path: Path):
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    receipt["index_partition"]["indexed_paths"] = []
    from benchmarks.codegraph_compare.integrity import _sha256

    receipt["index_partition"]["indexed_paths_hash"] = _sha256([])
    _resign_qualification_receipt(receipt)
    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "INDEX_PARTITION_MISMATCH",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_forged_executor_signature(tmp_path: Path):
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    receipt["index_provenance"]["signature"] = "00" * 64
    _resign_qualification_receipt(receipt)
    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == ("INDEX_PROVENANCE_MISSING",)


def test_validator_authenticates_quiescence_before_tree_hash(
    tmp_path: Path, monkeypatch
):
    # PR #1247: an untrusted snapshot signature must fail before index bytes are read.
    import benchmarks.codegraph_compare.setup_qualification_validation as validation

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    receipt["snapshot_audit"]["signature"] = "00" * 64
    _resign_qualification_receipt(receipt)
    hash_calls = 0

    def forbidden_hash(*_args, **_kwargs):
        nonlocal hash_calls
        hash_calls += 1
        raise AssertionError("tree hash ran before quiescence authentication")

    monkeypatch.setattr(validation, "_snapshot_tree_at", forbidden_hash)
    failures = _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    )

    assert (failures[0], hash_calls) == ("SNAPSHOT_AUDIT_MISSING", 0)


def test_strict_validator_rejects_forged_audit_signature(tmp_path: Path):
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    receipt["os_audit"]["signature"] = "00" * 64
    _resign_qualification_receipt(receipt)
    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == ("OS_AUDIT_MISSING",)


def test_strict_validator_rejects_forged_approver_signature(tmp_path: Path):
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    receipt["human_oracle_approval"]["signature"] = "00" * 64
    _resign_qualification_receipt(receipt)
    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == ("HUMAN_ORACLE_APPROVAL_MISSING",)


@pytest.mark.parametrize(
    ("blob_name", "payload"),
    (
        ("query_bytes", b'{"name":"Wrong"}'),
        ("stdout_bytes", b'{"line":2,"path":"wrong.ts"}'),
    ),
)
def test_strict_validator_rejects_wrong_normalized_oracle_evidence(
    tmp_path: Path, blob_name: str, payload: bytes
):
    from benchmarks.codegraph_compare.setup_qualification import (
        _bytes_hash,
    )

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    blob = receipt["raw_executions"][3][blob_name]
    (cell_root / blob["path"]).write_bytes(payload)
    blob["size_bytes"] = len(payload)
    blob["sha256"] = _bytes_hash(payload)
    _resign_qualification_receipt(receipt)
    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_unplanned_parse_error_allowlist(tmp_path: Path):
    from benchmarks.codegraph_compare.integrity import _sha256

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    partition = receipt["index_partition"]
    partition["indexed_paths"] = []
    partition["indexed_paths_hash"] = _sha256([])
    partition["parse_error_paths"] = ["main.ts"]
    partition["parse_error_allowlist"] = ["main.ts"]
    partition["parse_error_paths_hash"] = _sha256(["main.ts"])
    _resign_qualification_receipt(receipt)
    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "INDEX_PARTITION_MISMATCH",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


@pytest.mark.parametrize("value", (float("nan"), float("inf"), True))
def test_resource_plan_rejects_nonfinite_or_boolean_ceiling(value):
    import pytest

    from benchmarks.codegraph_compare.setup_qualification import ResourcePlanV1

    values = {
        "wall_timeout_seconds": value,
        "max_cpu_seconds": 20,
        "max_index_bytes": 1024,
        "max_disk_write_bytes": 4096,
        "min_free_disk_bytes": 1,
        "max_rss_bytes": 1024,
        "max_processes": 2,
        "max_open_files": 8,
        "max_concurrency": 1,
    }
    with pytest.raises(ValueError, match="resource ceiling"):
        ResourcePlanV1(**values)


def test_resource_plan_accepts_arbitrarily_large_exact_integer_ceiling():
    # PR #1247: math.isfinite used to overflow while converting this JSON integer.
    from benchmarks.codegraph_compare.setup_qualification import ResourcePlanV1

    plan = ResourcePlanV1(10**400, 20, 1024, 4096, 1, 1024, 2, 8, 1)

    assert plan.wall_timeout_seconds == 10**400


def test_strict_validator_rejects_arbitrarily_large_integer_observation(tmp_path: Path):
    # PR #1247: resource validation must fail closed rather than raise OverflowError.
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = copy.deepcopy(_write_valid_qualification_receipt(cell_root, plan))
    receipt["resource_observation"]["wall_seconds"] = 10**400
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RESOURCE_LIMIT_VIOLATION",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


@pytest.mark.parametrize("constant", ("NaN", "Infinity", "-Infinity"))
def test_receipt_parser_recursively_rejects_nonfinite_json_constants(
    tmp_path: Path, constant: str
):
    # PR #1247: Python's JSON extensions are outside the strict receipt grammar.
    import json

    import pytest

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _parse_receipt,
    )

    plan = _qualification_plans(tmp_path)[0]
    receipt = _write_valid_qualification_receipt(tmp_path / "cell", plan)
    payload = json.dumps(receipt, sort_keys=True).replace(
        '"wall_seconds": 1', f'"wall_seconds": {constant}'
    )

    with pytest.raises(ValueError, match="Non-finite JSON number"):
        _parse_receipt(payload.encode("utf-8"))


@pytest.mark.parametrize(
    ("path", "value", "raw_failure"),
    (
        (("attempt",), True, ()),
        (
            ("raw_executions", 0, "stderr_bytes", "size_bytes"),
            False,
            ("RAW_EXECUTION_EVIDENCE_MISSING",),
        ),
        (("resource_observation", "peak_processes"), 1.5, ()),
    ),
)
def test_receipt_schema_rejects_non_exact_scalar_types(
    tmp_path: Path, path, value, raw_failure
):
    # PR #1247: bools must not compare equal to integers and counts stay integral.
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = copy.deepcopy(_write_valid_qualification_receipt(cell_root, plan))
    target = receipt
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RECEIPT_SCHEMA_MISMATCH",
        *raw_failure,
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_receipt_parser_rejects_exponent_overflow(tmp_path: Path):
    # PR #1247: parse_constant does not see a finite token that overflows float.
    import json

    import pytest

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _parse_receipt,
    )

    plan = _qualification_plans(tmp_path)[0]
    receipt = _write_valid_qualification_receipt(tmp_path / "cell", plan)
    payload = json.dumps(receipt, sort_keys=True).replace(
        '"wall_seconds": 1', '"wall_seconds": 1e400'
    )

    with pytest.raises(ValueError, match="Non-finite JSON number"):
        _parse_receipt(payload.encode("utf-8"))


def test_validator_rejects_null_digest_signatures_after_core_failure(tmp_path: Path):
    # PR #1247: a non-canonical evidence core cannot authenticate as a null digest.
    import copy
    import json

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = copy.deepcopy(_write_valid_qualification_receipt(cell_root, plan))
    receipt["raw_executions"][1]["oracle_spec_hash"] = float("inf")
    executor_payload = {
        "schema_version": 1,
        "plan_hash": plan.digest,
        "evidence_core_digest": None,
    }

    def sign(seed: bytes, payload):
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return Ed25519PrivateKey.from_private_bytes(seed * 32).sign(encoded).hex()

    receipt["index_provenance"]["payload"] = executor_payload
    receipt["index_provenance"]["signature"] = sign(b"\x02", executor_payload)
    receipt["os_audit"]["payload"] = executor_payload
    receipt["os_audit"]["signature"] = sign(b"\x02", executor_payload)
    approval_payload = dict(receipt["human_oracle_approval"]["payload"])
    approval_payload["evidence_core_digest"] = None
    receipt["human_oracle_approval"]["payload"] = approval_payload
    receipt["human_oracle_approval"]["signature"] = sign(b"\x01", approval_payload)
    _resign_qualification_receipt(receipt)

    failures = _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    )
    assert failures == ("RECEIPT_SCHEMA_MISMATCH",)


def test_strict_validator_rejects_receipt_extension_even_with_matching_hash(
    tmp_path: Path,
):
    # PR #1247: direct validator callers receive a fail-closed schema failure.

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    receipt["extension"] = "unsigned"
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == ("RECEIPT_SCHEMA_MISMATCH",)


@pytest.mark.parametrize(
    "path",
    (
        (),
        ("eligibility",),
        ("tool",),
        ("config",),
        ("counters",),
        ("resource_observation",),
        ("index_partition",),
        ("raw_executions", 0),
        ("raw_executions", 0, "stdout_bytes"),
        ("index_provenance",),
        ("index_provenance", "payload"),
        ("os_audit",),
        ("os_audit", "payload"),
        ("os_audit", "audit_bytes"),
        ("human_oracle_approval",),
        ("human_oracle_approval", "payload"),
        ("human_oracle_approval", "approval_bytes"),
    ),
)
def test_receipt_parser_rejects_extension_at_every_object_schema(
    tmp_path: Path, path: tuple[object, ...]
):
    # PR #1247: unsigned extension members must not survive strict loading.
    import copy
    import json

    import pytest

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _parse_receipt,
    )

    plan = _qualification_plans(tmp_path)[0]
    receipt = copy.deepcopy(_write_valid_qualification_receipt(tmp_path / "cell", plan))
    target = receipt
    for component in path:
        target = target[component]
    target["extension"] = "unsigned"
    _resign_qualification_receipt(receipt)

    with pytest.raises(ValueError, match="exactly the schema-v2 keys"):
        _parse_receipt(json.dumps(receipt, sort_keys=True).encode("utf-8"))


def test_strict_receipt_json_rejects_excessive_depth_before_loading():
    # PR #1247: producer JSON depth is a validation failure, not verifier recursion.
    import pytest

    from benchmarks.codegraph_compare.setup_qualification import strict_json_loads

    payload = b"[" * 129 + b"0" + b"]" * 129

    with pytest.raises(ValueError, match="trusted nesting limit"):
        strict_json_loads(payload)


def test_receipt_parser_preserves_valid_canonical_hash_roundtrip(tmp_path: Path):
    import json

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _parse_receipt,
    )

    plan = _qualification_plans(tmp_path)[0]
    receipt = _write_valid_qualification_receipt(tmp_path / "cell", plan)
    payload = json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8")

    assert _parse_receipt(payload) == json.loads(payload)


def test_receipt_parser_rejects_stale_canonical_receipt_hash(tmp_path: Path):
    # PR #1247: strict loading binds the complete closed receipt to its hash.
    import json

    import pytest

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _parse_receipt,
    )

    plan = _qualification_plans(tmp_path)[0]
    receipt = _write_valid_qualification_receipt(tmp_path / "cell", plan)
    receipt["resource_observation"]["wall_seconds"] = 2

    with pytest.raises(ValueError, match="Receipt hash does not match"):
        _parse_receipt(json.dumps(receipt, sort_keys=True).encode("utf-8"))


def test_cell_plan_rejects_duplicate_oracle_ids(tmp_path: Path):
    from dataclasses import replace

    import pytest

    plan = _qualification_plans(tmp_path)[0]
    duplicate = replace(plan.oracle_specs[1], oracle_id=plan.oracle_specs[0].oracle_id)
    with pytest.raises(ValueError, match="unique symbol and call oracle IDs"):
        replace(plan, oracle_specs=(plan.oracle_specs[0], duplicate))


def test_receipt_parser_rejects_duplicate_members_at_nested_depth():
    import pytest

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _parse_receipt,
    )

    with pytest.raises(ValueError, match="Duplicate JSON member: exit_code"):
        _parse_receipt(b'{"run":{"exit_code":1,"exit_code":0}}')


def test_index_hash_rejects_fifo_without_waiting_for_writer(tmp_path: Path):
    import pytest

    from benchmarks.codegraph_compare.setup_qualification_paths import _hash_tree

    os.mkfifo(tmp_path / "producer.fifo")
    with pytest.raises(ValueError, match="special file"):
        _hash_tree(tmp_path)


def test_validator_rejects_default_reopen_through_symlinked_ancestor(tmp_path: Path):
    # PR #1247: untrusted evidence has no path-reopen fallback.
    from benchmarks.codegraph_compare.setup_qualification import validate_cell_receipt

    plan = _qualification_plans(tmp_path)[0]
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    cell = real_parent / "cell"
    receipt = _write_valid_qualification_receipt(cell, plan)
    alias = tmp_path / "alias"
    alias.symlink_to(real_parent, target_is_directory=True)

    failures = validate_cell_receipt(
        receipt,
        plan=plan,
        cell_root=alias / "cell",
        verifier_config=_qualification_verifier_config(),
    )

    assert failures[0] == "CELL_ROOT_ISOLATION_MISMATCH"


def test_validator_uses_pinned_experiment_descriptor_after_path_replacement(
    tmp_path: Path,
):
    from benchmarks.codegraph_compare.setup_qualification import validate_cell_receipt
    from benchmarks.codegraph_compare.setup_qualification_paths import (
        _open_root,
        _stable_directory_identity,
    )

    plan = _qualification_plans(tmp_path)[0]
    experiment = tmp_path / "experiment"
    cell = experiment / "cells/vscode--tsa-warm"
    receipt = _write_valid_qualification_receipt(cell, plan)
    root_fd = _open_root(experiment)
    moved = tmp_path / "moved"
    experiment.rename(moved)
    outside = tmp_path / "outside"
    outside.mkdir()
    experiment.symlink_to(outside, target_is_directory=True)
    try:
        assert (
            validate_cell_receipt(
                receipt,
                plan=plan,
                cell_root=cell,
                verifier_config=_qualification_verifier_config(),
                trusted_root_fd=root_fd,
                trusted_root_identity=_stable_directory_identity(os.fstat(root_fd)),
                cell_relative="cells/vscode--tsa-warm",
            )
            == ()
        )
    finally:
        os.close(root_fd)


def test_plan_set_rejects_cross_arm_oracle_spec_difference(tmp_path: Path):
    # PR #1247: both comparison arms must use the exact same oracle contract.
    from dataclasses import replace

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _trusted_commits,
        _validate_plans,
    )

    plans = list(_qualification_plans(tmp_path))
    changed_oracle = replace(
        plans[1].oracle_specs[0], expected_result={"path": "other.ts", "line": 1}
    )
    plans[1] = replace(
        plans[1], oracle_specs=(changed_oracle, plans[1].oracle_specs[1])
    )
    trusted = _trusted_commits(Path("benchmarks/codegraph_compare/repos.yaml"))

    with pytest.raises(ValueError, match="exactly identical oracle specifications"):
        _validate_plans(plans, trusted, _qualification_inventories(plans))


def test_plan_set_distinguishes_boolean_from_integer_oracle_result(
    tmp_path: Path,
):
    # PR #1247: Python equality aliases JSON true and integer 1.
    from dataclasses import replace

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _trusted_commits,
        _validate_plans,
    )

    plans = list(_qualification_plans(tmp_path))
    first = replace(plans[0].oracle_specs[0], expected_result={"line": True})
    second = replace(plans[1].oracle_specs[0], expected_result={"line": 1})
    plans[0] = replace(plans[0], oracle_specs=(first, plans[0].oracle_specs[1]))
    plans[1] = replace(plans[1], oracle_specs=(second, plans[1].oracle_specs[1]))
    trusted = _trusted_commits(Path("benchmarks/codegraph_compare/repos.yaml"))

    with pytest.raises(ValueError, match="exactly identical oracle specifications"):
        _validate_plans(plans, trusted, _qualification_inventories(plans))


@pytest.mark.parametrize(
    "field",
    ("parse_error_allowlist", "explicit_excluded_allowlist"),
)
def test_plan_set_rejects_one_cross_arm_allowlist_difference(
    tmp_path: Path, field: str
):
    # PR #1247: comparison arms must index the exact same eligible source workload.
    from dataclasses import replace

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _trusted_commits,
        _validate_plans,
    )

    plans = list(_qualification_plans(tmp_path))
    plans[1] = replace(plans[1], **{field: ("main.ts",)})
    trusted = _trusted_commits(Path("benchmarks/codegraph_compare/repos.yaml"))

    with pytest.raises(ValueError, match="exactly identical source allowlists"):
        _validate_plans(plans, trusted, _qualification_inventories(plans))


def test_trusted_manifest_rejects_duplicate_id_before_mapping(tmp_path: Path):
    # PR #1247: mapping construction must not silently overwrite a repository pin.
    import yaml

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _trusted_commits,
    )

    source = yaml.safe_load(
        Path("benchmarks/codegraph_compare/repos.yaml").read_text(encoding="utf-8")
    )
    source["repos"][-1]["id"] = source["repos"][0]["id"]
    manifest = tmp_path / "repos.yaml"
    manifest.write_text(yaml.safe_dump(source), encoding="utf-8")

    with pytest.raises(ValueError, match="IDs must be unique"):
        _trusted_commits(manifest)


def test_e0_orchestrator_never_invokes_producer_or_creates_receipts(tmp_path: Path):
    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        orchestrate_qualification,
    )

    plans = _qualification_plans(tmp_path)
    experiment = tmp_path / "experiment"
    verdict = orchestrate_qualification(
        experiment_root=experiment,
        plans=plans,
        trusted_inventories=_qualification_inventories(plans),
    )

    assert verdict == {
        "schema_version": 2,
        "evaluation_stage": "E0",
        "status": "NOT_EVALUATED",
        "reason": "ISOLATED_EXTERNAL_PRODUCER_AND_FRESH_TRUSTED_VERIFIER_ARTIFACT_REQUIRED",
        "publishable": False,
        "winner": None,
        "dominance_allowed": False,
        "unlock_allowed": False,
        "expected_cells": 14,
        "observed_receipts": 0,
        "attempts_per_cell": 0,
        "failures": [],
        "counters": None,
    }
    assert tuple(sorted(path.name for path in experiment.iterdir())) == (
        "plan.json",
        "verdict.json",
    )


def test_e0_orchestrator_rejects_untrusted_complete_inventory(tmp_path: Path):
    from dataclasses import replace

    import pytest

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        orchestrate_qualification,
    )

    plans = _qualification_plans(tmp_path)
    inventories = _qualification_inventories(plans)
    inventories["vscode"] = replace(
        inventories["vscode"], eligible_paths=(), eligible_paths_hash="0" * 64
    )
    with pytest.raises(ValueError, match="complete trusted inventory"):
        orchestrate_qualification(
            experiment_root=tmp_path / "experiment",
            plans=plans,
            trusted_inventories=inventories,
        )


def test_strict_validator_rejects_decoy_receipt_index_path(tmp_path: Path):
    # PR #1247: receipt-selected decoy trees cannot replace the plan-bound index.
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    decoy = cell_root / "decoy"
    decoy.mkdir()
    (decoy / "index.bin").write_bytes(b"frozen index")
    receipt["index_path"] = f"cells/{plan.repo_id}/{plan.arm_id}/decoy"
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "PLAN_BINDING_MISMATCH",
        "SNAPSHOT_AUDIT_MISSING",
        "INDEX_BYTES_MISMATCH",
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_cell_plan_requires_each_execution_to_reference_index_path(tmp_path: Path):
    # PR #1247: every lifecycle and oracle command is bound to the same index.
    from dataclasses import replace

    plan = _qualification_plans(tmp_path)[0]
    unbound = replace(plan.executions[2], argv=("health", "without-index"))

    with pytest.raises(ValueError, match="plan-bound index path"):
        replace(plan, executions=(*plan.executions[:2], unbound, *plan.executions[3:]))


def test_cell_plan_build_argv_is_bound_to_exact_source_checkout(tmp_path: Path):
    # PR #1247: a frozen build cannot consume a checkout other than inventory source.
    from dataclasses import replace

    plan = _qualification_plans(tmp_path)[0]
    other_source = (tmp_path / "other-source").resolve()
    other_source.mkdir()

    with pytest.raises(ValueError, match="canonical source checkout"):
        replace(plan, source_checkout_path=other_source.as_posix())


def test_strict_validator_requires_exact_ordered_frozen_commands(tmp_path: Path):
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = copy.deepcopy(_write_valid_qualification_receipt(cell_root, plan))
    receipt["raw_executions"][0]["argv"] = ["true"]
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_verifier_trust_roots_are_immutable_config():
    from dataclasses import FrozenInstanceError

    import pytest

    config = _qualification_verifier_config()
    with pytest.raises(FrozenInstanceError):
        config.executor_public_key = b"\x00" * 32


def test_validator_exports_no_mutable_trust_key_globals():
    import benchmarks.codegraph_compare.setup_qualification as qualification

    assert (
        hasattr(qualification, "TRUSTED_EXECUTOR_PUBLIC_KEY"),
        hasattr(qualification, "TRUSTED_APPROVER_PUBLIC_KEY"),
    ) == (False, False)


def test_cell_plan_requires_delete_build_health_and_all_oracles(tmp_path: Path):
    from dataclasses import replace

    import pytest

    plan = _qualification_plans(tmp_path)[0]
    with pytest.raises(ValueError, match="ordered delete/build/health"):
        replace(plan, executions=plan.executions[1:])


def test_index_hash_fails_closed_without_openat_support(tmp_path: Path):
    from unittest.mock import patch

    from benchmarks.codegraph_compare.setup_qualification_paths import _hash_tree

    with (
        patch.object(os, "supports_dir_fd", set()),
        pytest.raises(RuntimeError, match="requires openat/O_NOFOLLOW support"),
    ):
        _hash_tree(tmp_path)


def test_index_hash_enforces_trusted_total_size_ceiling(tmp_path: Path):
    import pytest

    from benchmarks.codegraph_compare.setup_qualification_paths import _hash_tree

    (tmp_path / "large.bin").write_bytes(b"x" * 32)
    with pytest.raises(ValueError, match="trusted size ceiling"):
        _hash_tree(tmp_path, max_bytes=31)


def test_index_hash_rejects_sparse_files(tmp_path: Path):
    import pytest

    from benchmarks.codegraph_compare.setup_qualification_paths import _hash_tree

    sparse = tmp_path / "sparse.bin"
    with sparse.open("wb") as stream:
        stream.truncate(2 * 1024 * 1024)
    if sparse.stat().st_blocks * 512 >= sparse.stat().st_size:
        pytest.skip("tracked: filesystem does not represent sparse allocation")
    with pytest.raises(ValueError, match="Sparse artifact files"):
        _hash_tree(tmp_path)


def test_oracle_comparison_distinguishes_boolean_from_number(tmp_path: Path):
    from benchmarks.codegraph_compare.setup_qualification import (
        _bytes_hash,
    )

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    blob = receipt["raw_executions"][3]["stdout_bytes"]
    payload = b'{"line":true,"path":"main.ts"}'
    (cell_root / blob["path"]).write_bytes(payload)
    blob["size_bytes"] = len(payload)
    blob["sha256"] = _bytes_hash(payload)
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def _mark_posix_qualification_section_tests() -> None:
    """Apply the platform contract to every test defined in this final section."""
    namespace = globals()
    for name, candidate in tuple(namespace.items()):
        code = getattr(candidate, "__code__", None)
        if (
            name.startswith("test_")
            and code is not None
            and code.co_firstlineno > _POSIX_QUALIFICATION_SECTION_START
        ):
            namespace[name] = POSIX_QUALIFICATION_TEST(candidate)


def test_strict_receipt_json_rejects_flat_node_budget_overflow():
    # PR #1247 review 3742970270: byte/depth checks alone missed flat JSON trees.
    from benchmarks.codegraph_compare.setup_qualification import strict_json_loads

    payload = b"[" + b",".join([b"0"] * 100_000) + b"]"

    with pytest.raises(ValueError, match="depth or node limits"):
        strict_json_loads(payload)


def test_source_inventory_rejects_ignored_checkout_path(tmp_path: Path):
    # PR #1247 review 3742970272: fresh evidence requires a completely clean checkout.
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "repo"
    _qualification_git_repo(repo)
    (repo / ".git/info/exclude").write_text("rogue.ts\n", encoding="utf-8")
    (repo / "rogue.ts").write_text("export const decoy = true;\n", encoding="utf-8")

    with pytest.raises(ValueError, match="tracked or untracked changes"):
        inventory_sources("vscode", repo, DEFAULT_SOURCE_RULES)


def test_cell_plan_rejects_authenticated_tool_argv_decoy(tmp_path: Path):
    # PR #1247 review 3742970282: signed artifacts must be the executed artifacts.
    from dataclasses import replace

    plan = _qualification_plans(tmp_path)[0]
    build = plan.executions[1]
    decoy = replace(build, argv=("/tmp/decoy", *build.argv[1:]))

    with pytest.raises(ValueError, match="exactly bind authenticated tool/config"):
        replace(plan, executions=(plan.executions[0], decoy, *plan.executions[2:]))


def test_raw_blob_same_size_rewrite_is_rejected(tmp_path: Path):
    # PR #1247 review 3742970275: a first-pass digest is not quiescence evidence.
    import benchmarks.codegraph_compare.setup_qualification_validation as module

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    target = cell_root / receipt["raw_executions"][0]["stdout_bytes"]["path"]
    original_hash = module._hash_regular_descriptor
    calls = 0

    def rewrite_after_first_hash(*args, **kwargs):
        nonlocal calls
        result = original_hash(*args, **kwargs)
        calls += 1
        if calls == 1:
            target.write_bytes(b"[]")
        return result

    with patch.object(
        module, "_hash_regular_descriptor", side_effect=rewrite_after_first_hash
    ):
        failures = _validate_qualification_receipt(
            receipt,
            plan=plan,
            cell_root=cell_root,
            verifier_config=_qualification_verifier_config(),
        )

    assert failures == ("RAW_EXECUTION_EVIDENCE_MISSING",)


def test_qualification_architecture_codemap_lists_security_modules():
    # PR #1247 review 3742970277: codemap-first discovery includes the trust boundary.
    codemap = Path("docs/CODEMAPS/architecture.md").read_text(encoding="utf-8")

    assert (
        "`setup_qualification_paths.py` — canonical openat filesystem isolation"
        in codemap
    )
    assert "`setup_qualification_trust.py` — externally supplied Ed25519" in codemap


def test_posix_qualification_marker_invocation_is_final_top_level_statement():
    # PR #1247 review final11: appended tests must remain inside the marked section.
    import ast

    syntax = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    statement = syntax.body[-1]

    assert (
        type(statement).__name__,
        type(statement.value).__name__,
        type(statement.value.func).__name__,
        statement.value.func.id,
    ) == ("Expr", "Call", "Name", "_mark_posix_qualification_section_tests")


def test_posix_qualification_section_functions_have_collection_marker():
    # PR #1247 review final11: every collected section test must share the Windows skip.
    reason = "tracked: NO1-008A qualification requires openat/O_NOFOLLOW"
    section_tests = tuple(
        (name, candidate)
        for name, candidate in globals().items()
        if name.startswith("test_")
        and getattr(getattr(candidate, "__code__", None), "co_firstlineno", 0)
        > _POSIX_QUALIFICATION_SECTION_START
    )
    missing = tuple(
        name
        for name, candidate in section_tests
        if not any(
            mark.name == "skipif" and mark.kwargs.get("reason") == reason
            for mark in getattr(candidate, "pytestmark", ())
        )
    )

    assert missing == ()


def test_latest_qualification_tests_skip_in_simulated_windows(request, monkeypatch):
    # PR #1247 review final11: the five tests appended in 0d4d53f0 stay skipped on Windows.
    from _pytest.skipping import evaluate_condition

    latest_names = (
        "test_strict_receipt_json_rejects_flat_node_budget_overflow",
        "test_source_inventory_rejects_ignored_checkout_path",
        "test_cell_plan_rejects_authenticated_tool_argv_decoy",
        "test_raw_blob_same_size_rewrite_is_rejected",
        "test_qualification_architecture_codemap_lists_security_modules",
    )
    marks = tuple(
        next(mark for mark in globals()[name].pytestmark if mark.name == "skipif")
        for name in latest_names
    )
    with monkeypatch.context() as context:
        context.setattr(sys.modules[__name__], "os", SimpleNamespace(name="nt"))
        evaluations = tuple(
            evaluate_condition(request.node, mark, mark.args[0]) for mark in marks
        )

    assert evaluations == (
        (True, "tracked: NO1-008A qualification requires openat/O_NOFOLLOW"),
        (True, "tracked: NO1-008A qualification requires openat/O_NOFOLLOW"),
        (True, "tracked: NO1-008A qualification requires openat/O_NOFOLLOW"),
        (True, "tracked: NO1-008A qualification requires openat/O_NOFOLLOW"),
        (True, "tracked: NO1-008A qualification requires openat/O_NOFOLLOW"),
    )


def test_plan_set_rejects_cross_arm_resource_plan_difference(tmp_path: Path):
    # PR #1247 review 3743050574: comparison arms share one exact resource budget.
    from dataclasses import replace

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _trusted_commits,
        _validate_plans,
    )

    plans = list(_qualification_plans(tmp_path))
    plans[1] = replace(
        plans[1],
        resources=replace(
            plans[1].resources,
            wall_timeout_seconds=plans[1].resources.wall_timeout_seconds + 1,
        ),
    )
    trusted = _trusted_commits(Path("benchmarks/codegraph_compare/repos.yaml"))

    with pytest.raises(ValueError, match="exactly identical resource plans"):
        _validate_plans(plans, trusted, _qualification_inventories(plans))


def test_validator_rejects_missing_retained_receipt(tmp_path: Path):
    # PR #1247 review 3743050577: supplied mappings cannot replace retained evidence.
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    (cell_root / "cell-receipt.json").unlink()

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
        sync_retained=False,
    ) == ("RETAINED_RECEIPT_MISMATCH",)


def test_validator_rejects_stale_retained_receipt(tmp_path: Path):
    # PR #1247 review 3743050577: retained and supplied hashes must match exactly.
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    stale = copy.deepcopy(receipt)
    stale["resource_observation"]["wall_seconds"] = 2
    _resign_qualification_receipt(stale)
    (cell_root / "cell-receipt.json").write_text(
        json.dumps(stale, sort_keys=True), encoding="utf-8"
    )

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
        sync_retained=False,
    ) == ("RETAINED_RECEIPT_MISMATCH",)


def test_validator_rejects_type_different_retained_receipt(tmp_path: Path):
    # PR #1247 review 3743050577: JSON true never aliases integer one.
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    type_different = copy.deepcopy(receipt)
    type_different["resource_observation"]["wall_seconds"] = True
    _resign_qualification_receipt(type_different)
    (cell_root / "cell-receipt.json").write_text(
        json.dumps(type_different, sort_keys=True), encoding="utf-8"
    )

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
        sync_retained=False,
    ) == ("RETAINED_RECEIPT_MISMATCH",)


def test_validator_rejects_empty_retained_receipt_object(tmp_path: Path):
    # PR #1247 review 3743050577: an empty retained JSON object is not evidence.
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    (cell_root / "cell-receipt.json").write_bytes(b"{}")

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
        sync_retained=False,
    ) == ("RETAINED_RECEIPT_MISMATCH",)


# Keep this invocation at absolute EOF so every qualification test inherits the marker.


# NO1-008A receipt-v3 detached execution contract (setup evidence only).
def _qualification_v3_body(repo_id="vscode", arm_id="tsa-warm"):
    blob = {
        "path": "raw/empty",
        "size_bytes": 0,
        "sha256": hashlib.sha256(b"").hexdigest(),
    }
    executions = []
    for execution_id in ("delete", "build", "health", "symbol", "call"):
        executions.append(
            {
                "id": execution_id,
                "argv": [
                    "/tool/bin",
                    execution_id,
                    "--source",
                    "/source",
                    "--config",
                    "/config.json",
                ],
                "cwd": "/source",
                "environment_digest": "1" * 64,
                "exit_code": 0,
                "stdout_bytes": dict(blob),
                "stderr_bytes": dict(blob),
                "query_bytes": dict(blob),
                "final_index_observation": dict(blob),
            }
        )
    return {
        "run_nonce": "a" * 64,
        "role_images": {
            "producer": "sha256:" + "6" * 64,
            "executor": "sha256:" + "7" * 64,
            "approver": "sha256:" + "8" * 64,
            "auditor": "sha256:" + "a" * 64,
            "verifier": "sha256:" + "9" * 64,
        },
        "cell": {
            "repo_id": repo_id,
            "arm_id": arm_id,
            "attempt": 1,
            "artifact_path": f"cells/{repo_id}/{arm_id}/cell-receipt.json",
        },
        "plan": {
            "plan_hash": "2" * 64,
            "plan_set_hash": "3" * 64,
            "tool_sha256": "4" * 64,
            "config_sha256": "5" * 64,
            "image_digest": "sha256:" + "6" * 64,
            "seccomp_sha256": "7" * 64,
        },
        "source": {
            "commit": "8" * 40,
            "eligibility": {
                "repo_id": repo_id,
                "source_rules_hash": "4" * 64,
                "commit": "8" * 40,
                "tracked_regular_paths": ["main.ts"],
                "tracked_entries": [["main.ts", "100644", "a" * 40]],
                "root_tree_id": "c" * 40,
                "tracked_files": [["main.ts", "100644", "a" * 40, 1, "b" * 64]],
                "eligible_paths": ["main.ts"],
                "prefilter_exclusions": [],
                "tracked_inventory_hash": "5" * 64,
                "eligible_paths_hash": "6" * 64,
                "repo_fingerprint": "9" * 64,
            },
            "repo_fingerprint": "9" * 64,
            "mount_target": "/source",
            "read_only": True,
        },
        "environment": {
            "environment_digest": "1" * 64,
            "image_digest": "sha256:" + "6" * 64,
            "docker_security_flags": [
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
            ],
            "network_mode": "none",
            "seccomp_sha256": "7" * 64,
            "credentials_stripped": True,
        },
        "counters": {
            "api_cost_usd": 0,
            "input_tokens": 0,
            "model_calls": 0,
            "network_requests": 0,
            "output_tokens": 0,
            "provider_requests": 0,
        },
        "resources": {
            "plan_digest": "a" * 64,
            "wall_ns": 1,
            "cpu_usec": 1,
            "io_bytes": 1,
            "memory_peak_bytes": 1,
            "pids_peak": 1,
        },
        "executions": executions,
        "index_partition": {
            "indexed_paths": ["main.ts"],
            "excluded_paths": [],
            "parse_error_paths": [],
            "indexed_paths_hash": "b" * 64,
            "excluded_paths_hash": "c" * 64,
            "parse_error_paths_hash": "d" * 64,
        },
        "snapshot": {
            "format": "dm-verity-v1",
            "data_image_sha256": "e" * 64,
            "data_image_size": 1,
            "hash_image_sha256": "f" * 64,
            "hash_image_size": 1,
            "root_hash": "0" * 64,
            "salt": "1" * 64,
            "data_block_size": 4096,
            "hash_block_size": 4096,
            "data_blocks": 1,
            "tree_hash": "2" * 64,
            "index_content_hash": "3" * 64,
        },
        "process_audit": {
            "producer_container_id": "producer-1",
            "actual_image_id": "sha256:" + "a" * 64,
            "launch_token_sha256": "b" * 64,
            "container_user": "65532:65532",
            "readonly_rootfs": True,
            "cap_drop": ["ALL"],
            "mounts": [
                ["/host/config", "/config.json", True],
                ["/host/out", "/out", False],
                ["/host/plan", "/plan/cell-plan.json", True],
                ["/host/inventory", "/plan/inventory.json", True],
                ["/host/gate", "/run/no1-008a-launch-gate", True],
                ["/host/seccomp", "/plan/seccomp.json", True],
                ["/host/source", "/source", True],
                ["/host/tool", "/tool/bin", True],
            ],
            "resource_limits": {
                "pids_limit": 64,
                "memory": 4294967296,
                "nano_cpus": 1000000000,
            },
            "tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=64m"},
            "image_digest": "sha256:" + "6" * 64,
            "cgroup_id": "cg-1",
            "network_mode": "none",
            "security_opt": ["no-new-privileges", "seccomp=" + "7" * 64],
            "restart_count": 0,
            "terminal_pid": 0,
            "launch_count": 1,
            "cgroup_processes_after_stop": [],
            "pid1_exit": 0,
            "run_nonce": "a" * 64,
            "resource_observations": {
                "wall_ns": 1,
                "cpu_usec": 1,
                "io_bytes": 1,
                "memory_peak_bytes": 1,
                "pids_peak": 1,
            },
            "audit_bytes": dict(blob),
        },
        "oracle_approval": {
            "approved": True,
            "statement": "approver authorizes the exact oracle results",
            "oracle_results_hash": hashlib.sha256(
                json.dumps(
                    [blob["sha256"], blob["sha256"]], separators=(",", ":")
                ).encode()
            ).hexdigest(),
        },
    }


def _qualification_v3_receipt(repo_id="vscode", arm_id="tsa-warm"):
    from benchmarks.codegraph_compare.receipt_v3 import (
        assemble_receipt,
        sign_body,
        signature_record,
    )

    body = _qualification_v3_body(repo_id, arm_id)
    executor = signature_record("executor", sign_body(body, b"\x11" * 32))
    approver = signature_record("approver", sign_body(body, b"\x22" * 32))
    return assemble_receipt(body, executor, approver)


def _qualification_v3_public_config():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    role_specs = {
        "executor": (b"\x11" * 32, 901, "a"),
        "approver": (b"\x22" * 32, 902, "b"),
        "auditor": (b"\x33" * 32, 900, "d"),
        "verifier": (b"\x55" * 32, 903, "e"),
        "decision_consumer": (b"\x66" * 32, 904, "f"),
    }
    image_suffixes = {
        "producer": "6",
        "executor": "7",
        "approver": "8",
        "auditor": "a",
        "verifier": "9",
        "decision_consumer": "f",
    }
    image_id_suffixes = dict(zip(image_suffixes, "abcdef", strict=True))

    config = {
        "schema_version": 6,
        **{
            role: {
                "key_id": "verifier-service" if role == "verifier" else role,
                "public_key_hex": Ed25519PrivateKey.from_private_bytes(private)
                .public_key()
                .public_bytes_raw()
                .hex(),
                "protocol": (
                    "no1-008a-audit-v1"
                    if role == "auditor"
                    else f"no1-008a-{role.replace('_', '-')}-service-v1"
                ),
                "peer_uid": uid,
                "service_measurement": measurement * 64,
            }
            for role, (private, uid, measurement) in role_specs.items()
        },
        "trusted": {
            "plan_set_hash": "3" * 64,
            "plan_hashes": {
                f"{repo}/{arm}": "2" * 64
                for repo in (
                    "vscode",
                    "excalidraw",
                    "django",
                    "tokio",
                    "okhttp",
                    "gin",
                    "alamofire",
                )
                for arm in ("tsa-warm", "codegraph-warm")
            },
            "plan_document_sha256": {
                f"{repo}/{arm}": "1" * 64
                for repo in (
                    "vscode",
                    "excalidraw",
                    "django",
                    "tokio",
                    "okhttp",
                    "gin",
                    "alamofire",
                )
                for arm in ("tsa-warm", "codegraph-warm")
            },
            "inventory_sha256": dict.fromkeys(
                (
                    "vscode",
                    "excalidraw",
                    "django",
                    "tokio",
                    "okhttp",
                    "gin",
                    "alamofire",
                ),
                "4" * 64,
            ),
            "source_snapshot_sha256": dict.fromkeys(
                (
                    "vscode",
                    "excalidraw",
                    "django",
                    "tokio",
                    "okhttp",
                    "gin",
                    "alamofire",
                ),
                "5" * 64,
            ),
            "tool_sha256": "4" * 64,
            "config_sha256": "5" * 64,
            "seccomp_sha256": "7" * 64,
            "images": {
                role: "sha256:" + suffix * 64 for role, suffix in image_suffixes.items()
            },
            "image_ids": {
                role: "sha256:" + suffix * 64
                for role, suffix in image_id_suffixes.items()
            },
        },
    }
    trusted = config["trusted"]
    for role, (_private, uid, measurement) in role_specs.items():
        trusted[f"{role}_runtime"] = {
            "image_digest": trusted["images"][role],
            "image_id": trusted["image_ids"][role],
            "closure_manifest_sha256": measurement * 64,
            "measurement": {
                "interpreter_sha256": "1" * 64,
                "closure_manifest": {},
                "closure_manifest_sha256": measurement * 64,
                "uid": uid,
                "gid": uid,
                "rootfs_readonly": True,
                "allowed_writable_mounts": [],
            },
        }
    trusted["service_launch"] = {
        role: {
            "image_id": trusted["image_ids"][role],
            "cmd": ["python", "-m", f"benchmarks.codegraph_compare.{role}_service"],
            "entrypoint": None,
            "user": str(uid),
            "readonly_rootfs": True,
            "mounts": [],
            "network_mode": "none",
            "security_opt": ["no-new-privileges:true"],
        }
        for role, (_private, uid, _measurement) in role_specs.items()
    }
    return _sign_qualification_v3_config(config)


def _sign_qualification_v3_config(config):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes
    from benchmarks.codegraph_compare.verifier import ROOT_SIGNATURE_DOMAIN

    unsigned = {key: value for key, value in config.items() if key != "root_signature"}
    config["root_signature"] = (
        Ed25519PrivateKey.from_private_bytes(b"\x44" * 32)
        .sign(ROOT_SIGNATURE_DOMAIN + canonical_json_bytes(unsigned))
        .hex()
    )
    return config


def test_qualification_v3_signatures_cover_byte_identical_canonical_body():
    from benchmarks.codegraph_compare.receipt_v3 import verify_receipt

    config = _qualification_v3_public_config()
    receipt = _qualification_v3_receipt()
    verify_receipt(
        receipt,
        config["executor"]["key_id"],
        bytes.fromhex(config["executor"]["public_key_hex"]),
        config["approver"]["key_id"],
        bytes.fromhex(config["approver"]["public_key_hex"]),
    )
    assert (
        receipt["body_sha256"]
        == hashlib.sha256(
            json.dumps(
                receipt["body"],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
    )


def test_qualification_v3_approver_verifies_executor_handoff_before_signing():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare.receipt_v3 import (
        approve_executor_attestation,
        create_executor_attestation,
    )

    body = _qualification_v3_body()
    handoff = create_executor_attestation(body, "executor", b"\x11" * 32)
    receipt = approve_executor_attestation(
        handoff,
        "executor",
        Ed25519PrivateKey.from_private_bytes(b"\x11" * 32)
        .public_key()
        .public_bytes_raw(),
        "approver",
        b"\x22" * 32,
    )

    assert receipt["executor_signature"] == handoff["executor_signature"]


def test_qualification_v3_rejects_body_mutation():
    from benchmarks.codegraph_compare.receipt_v3 import verify_receipt

    receipt = _qualification_v3_receipt()
    receipt["body"]["cell"]["repo_id"] = "gin"
    config = _qualification_v3_public_config()
    with pytest.raises(ValueError, match="artifact path|body hash mismatch"):
        verify_receipt(
            receipt,
            "executor",
            bytes.fromhex(config["executor"]["public_key_hex"]),
            "approver",
            bytes.fromhex(config["approver"]["public_key_hex"]),
        )


def test_qualification_v3_rejects_signature_swap():
    from benchmarks.codegraph_compare.receipt_v3 import verify_receipt

    receipt = _qualification_v3_receipt()
    (
        receipt["executor_signature"]["signature"],
        receipt["approver_signature"]["signature"],
    ) = (
        receipt["approver_signature"]["signature"],
        receipt["executor_signature"]["signature"],
    )
    receipt["receipt_hash"] = hashlib.sha256(
        json.dumps(
            {k: v for k, v in receipt.items() if k != "receipt_hash"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    config = _qualification_v3_public_config()
    with pytest.raises(ValueError, match="signature mismatch"):
        verify_receipt(
            receipt,
            "executor",
            bytes.fromhex(config["executor"]["public_key_hex"]),
            "approver",
            bytes.fromhex(config["approver"]["public_key_hex"]),
        )


def test_qualification_v3_rejects_duplicate_json_member():
    from benchmarks.codegraph_compare.receipt_v3 import strict_json_loads

    with pytest.raises(ValueError, match="duplicate JSON member"):
        strict_json_loads(b'{"schema_version":3,"schema_version":3}')


def test_qualification_v3_rejects_nan():
    from benchmarks.codegraph_compare.receipt_v3 import strict_json_loads

    with pytest.raises(ValueError, match="non-finite"):
        strict_json_loads(b'{"value":NaN}')


def test_qualification_v3_rejects_extra_nested_field():
    from benchmarks.codegraph_compare.receipt_v3 import validate_body

    body = _qualification_v3_body()
    body["cell"]["unexpected"] = False
    with pytest.raises(ValueError, match="unknown or missing fields"):
        validate_body(body)


def test_qualification_v3_rejects_noncanonical_artifact_path():
    from benchmarks.codegraph_compare.receipt_v3 import validate_body

    body = _qualification_v3_body()
    body["cell"]["artifact_path"] = "cells/../receipt.json"
    with pytest.raises(ValueError, match="artifact path|not canonical"):
        validate_body(body)


def _qualification_v3_manifest():
    from benchmarks.codegraph_compare.setup_qualification import EXPECTED_CELLS

    return {
        "schema_version": 1,
        "verifier_nonce": "a" * 64,
        "verifier_image_digest": "sha256:" + "b" * 64,
        "run_contract": {"plan_set_hash": "3" * 64, "run_nonce": "a" * 64},
        "cells": [
            {
                "repo_id": repo,
                "arm_id": arm,
                "attempt": 1,
                "plan": {"identity": f"{repo}/{arm}"},
                "inventory": {"repo_id": repo},
                "receipt": _qualification_v3_receipt(repo, arm),
                "data_image": "/evidence/data.img",
                "hash_image": "/evidence/hash.img",
                "process_audit": "/evidence/process-audit.json",
                "source_snapshot": "/evidence/source.tar",
                "tool": "/evidence/tool",
                "config": "/evidence/config",
                "seccomp": "/evidence/seccomp",
            }
            for repo, arm in EXPECTED_CELLS
        ],
    }


def test_qualification_v3_aggregate_requires_public_config_and_full_verification(
    monkeypatch,
):
    from benchmarks.codegraph_compare import verifier_aggregate as verifier

    manifest = _qualification_v3_manifest()
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    plan_hashes = [
        hashlib.sha256(canonical_json_bytes(cell["plan"])).hexdigest()
        for cell in manifest["cells"]
    ]
    plan_set_hash = hashlib.sha256(canonical_json_bytes(plan_hashes)).hexdigest()
    for cell in manifest["cells"]:
        cell["plan"]["plan_set_hash"] = plan_set_hash
    config = _qualification_v3_public_config()
    config["trusted"]["plan_set_hash"] = plan_set_hash
    manifest["run_contract"]["plan_set_hash"] = plan_set_hash
    config["trusted"]["plan_hashes"] = {
        f"{cell['repo_id']}/{cell['arm_id']}": digest
        for cell, digest in zip(manifest["cells"], plan_hashes, strict=True)
    }
    config["trusted"]["plan_document_sha256"] = {
        f"{cell['repo_id']}/{cell['arm_id']}": hashlib.sha256(
            canonical_json_bytes(cell["plan"])
        ).hexdigest()
        for cell in manifest["cells"]
    }
    _sign_qualification_v3_config(config)
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import trust_anchor

    monkeypatch.setattr(
        trust_anchor,
        "baked_root_public_key",
        lambda: (
            Ed25519PrivateKey.from_private_bytes(b"\x44" * 32)
            .public_key()
            .public_bytes_raw()
        ),
    )
    monkeypatch.setattr(verifier, "verify_cell", lambda *args, **kwargs: ())
    diagnostic_root = (
        Ed25519PrivateKey.from_private_bytes(b"\x44" * 32)
        .public_key()
        .public_bytes_raw()
    )
    assert (
        verifier.aggregate_verdict(
            manifest,
            public_config=config,
            diagnostic_mode=True,
            diagnostic_root_public_key=diagnostic_root,
        )["status"]
        == "NOT_EVALUATED"
    )
    assert (
        verifier.aggregate_verdict(manifest, public_config=config)["status"]
        == "SETUP_QUALIFIED"
    )


def test_qualification_v3_aggregate_rejects_reordered_cells(monkeypatch):
    from benchmarks.codegraph_compare import verifier

    manifest = _qualification_v3_manifest()
    manifest["cells"][0], manifest["cells"][1] = (
        manifest["cells"][1],
        manifest["cells"][0],
    )
    monkeypatch.setattr(verifier, "verify_cell", lambda *args, **kwargs: ())
    assert (
        verifier.aggregate_verdict(
            manifest, public_config=_qualification_v3_public_config()
        )["status"]
        == "NOT_EVALUATED"
    )


def test_qualification_v3_aggregate_has_no_default_empty_violations():
    from benchmarks.codegraph_compare.verifier import aggregate_verdict

    with pytest.raises(TypeError, match="public_config"):
        aggregate_verdict({})


def test_qualification_v3_aggregate_claims_remain_e0_and_disabled():
    from benchmarks.codegraph_compare.verifier import aggregate_verdict

    verdict = aggregate_verdict({}, public_config=_qualification_v3_public_config())
    assert {
        key: verdict[key]
        for key in (
            "evaluation_stage",
            "status",
            "publishable",
            "winner",
            "dominance_allowed",
            "unlock_allowed",
        )
    } == {
        "evaluation_stage": "E0",
        "status": "NOT_EVALUATED",
        "publishable": False,
        "winner": None,
        "dominance_allowed": False,
        "unlock_allowed": False,
    }


def test_qualification_executor_rejects_nonempty_output(tmp_path: Path):
    from benchmarks.codegraph_compare.setup_qualification_executor import produce_cell

    output = tmp_path / "out"
    output.mkdir()
    (output / "preexisting").write_bytes(b"untrusted")
    with pytest.raises(ValueError, match="fresh empty directory"):
        produce_cell({}, output)


def test_qualification_index_observation_streams_canonical_bounded_records(
    tmp_path: Path,
):
    # PR #1249 review 3745026823: observations are bounded before producer success.
    from benchmarks.codegraph_compare.setup_qualification_executor import (
        _write_final_index_observation,
    )

    index = tmp_path / "index"
    raw = tmp_path / "raw"
    index.mkdir()
    raw.mkdir()
    (index / "b").write_bytes(b"bb")
    (index / "a").write_bytes(b"a")
    descriptor = _write_final_index_observation(
        index, raw, "observation", deadline_monotonic=time.monotonic() + 10
    )

    assert descriptor == {
        "path": "raw/observation",
        "size_bytes": (raw / "observation").stat().st_size,
        "sha256": hashlib.sha256((raw / "observation").read_bytes()).hexdigest(),
    }
    assert json.loads((raw / "observation").read_bytes()) == [
        {
            "path": "a",
            "sha256": hashlib.sha256(b"a").hexdigest(),
            "size_bytes": 1,
        },
        {
            "path": "b",
            "sha256": hashlib.sha256(b"bb").hexdigest(),
            "size_bytes": 2,
        },
    ]


def test_qualification_index_observation_rejects_receipt_node_overflow(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3745026823: node complexity fails before successful sealing.
    from benchmarks.codegraph_compare import setup_qualification_executor as executor

    index = tmp_path / "index"
    raw = tmp_path / "raw"
    index.mkdir()
    raw.mkdir()
    (index / "only").write_bytes(b"x")
    monkeypatch.setattr(executor, "MAX_NODES", 3)

    with pytest.raises(ValueError, match="receipt node bound"):
        executor._write_final_index_observation(
            index, raw, "observation", deadline_monotonic=time.monotonic() + 10
        )


def test_qualification_index_observation_rejects_receipt_byte_overflow(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3745026823: byte complexity fails before successful sealing.
    from benchmarks.codegraph_compare import setup_qualification_executor as executor

    index = tmp_path / "index"
    raw = tmp_path / "raw"
    index.mkdir()
    raw.mkdir()
    monkeypatch.setattr(executor, "MAX_JSON_BYTES", len(b'{"records":}'))

    with pytest.raises(ValueError, match="receipt JSON bound"):
        executor._write_final_index_observation(
            index, raw, "observation", deadline_monotonic=time.monotonic() + 10
        )


def test_sealed_read_budget_uses_named_actual_passes():
    # PR #1249 review 3745026813: budget counts signer x2 and verifier readers.
    from benchmarks.codegraph_compare.execution_budget import sealed_read_passes

    assert sealed_read_passes("executor") == sealed_read_passes("approver")
    assert {
        role: {kind: len(names) for kind, names in sealed_read_passes(role).items()}
        for role in ("executor", "approver", "verifier")
    } == {
        "executor": {"images": 4, "output": 9},
        "approver": {"images": 4, "output": 9},
        "verifier": {"images": 2, "output": 5},
    }


def test_qualification_operator_contract_is_exact_closed_service_pipeline():
    completed = subprocess.run(
        ["bash", "scripts/no1_008a_operator.sh", "contract"],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result == {
        "schema_version": 1,
        "cells": 14,
        "attempts_per_cell": 1,
        "max_concurrency": 1,
        "roles": [
            "producer",
            "auditor",
            "executor",
            "approver",
            "verifier",
            "decision-consumer",
        ],
        "qualification": "production-verifier-exact-14-only",
    }


def test_qualification_operator_dry_run_emits_each_cell_once():
    completed = subprocess.run(
        ["bash", "scripts/no1_008a_operator.sh", "dry-run"],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = [json.loads(line) for line in completed.stdout.splitlines()]
    identities = [(row["repo_id"], row["arm_id"], row["attempt"]) for row in rows]
    from benchmarks.codegraph_compare.setup_qualification import EXPECTED_CELLS

    assert identities == [(repo, arm, 1) for repo, arm in EXPECTED_CELLS]


def test_qualification_seccomp_denies_exact_network_syscall_set():
    profile = json.loads(Path("scripts/no1_008a_no_network_seccomp.json").read_text())
    assert profile["syscalls"] == [
        {
            "names": [
                "socket",
                "socketpair",
                "connect",
                "bind",
                "listen",
                "accept",
                "accept4",
                "sendto",
                "sendmsg",
                "recvfrom",
                "recvmsg",
            ],
            "action": "SCMP_ACT_ERRNO",
            "errnoRet": 1,
        }
    ]


def test_qualification_v3_manifest_requires_each_of_fourteen_complete_cells():
    # Audit 2026-08-09 B2: aggregate authority requires a complete external manifest.
    from benchmarks.codegraph_compare.verifier import validate_manifest

    manifest = _qualification_v3_manifest()
    del manifest["cells"][0]["hash_image"]
    with pytest.raises(ValueError, match="manifest cell"):
        validate_manifest(manifest)


def test_qualification_v3_manifest_rejects_thirteen_cells():
    # Audit 2026-08-09 B2: no partial matrix can enter aggregate verification.
    from benchmarks.codegraph_compare.verifier import validate_manifest

    manifest = _qualification_v3_manifest()
    manifest["cells"].pop()
    with pytest.raises(ValueError, match="exact 14"):
        validate_manifest(manifest)


def test_qualification_v3_verity_command_binds_both_image_hashes(tmp_path: Path):
    # Audit 2026-08-09 B3: fresh verifier authenticates data/hash images itself.
    from benchmarks.codegraph_compare.verifier import _verify_verity

    data = tmp_path / "data.img"
    hashes = tmp_path / "hash.img"
    data.write_bytes(b"data")
    hashes.write_bytes(b"hash")
    body = _qualification_v3_body()
    snapshot = body["snapshot"]
    snapshot.update(
        {
            "data_image_size": 4,
            "data_image_sha256": hashlib.sha256(b"data").hexdigest(),
            "hash_image_size": 4,
            "hash_image_sha256": hashlib.sha256(b"hash").hexdigest(),
        }
    )
    commands = []

    def runner(command):
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 0, b"", b"")

    _verify_verity(
        body,
        {"data_image": str(data.resolve()), "hash_image": str(hashes.resolve())},
        runner,
    )
    normalized = [
        [
            "/proc/self/fd/<open>" if part.startswith("/proc/self/fd/") else part
            for part in command
        ]
        for command in commands
    ]
    assert normalized == [
        [
            "veritysetup",
            "verify",
            "/proc/self/fd/<open>",
            "/proc/self/fd/<open>",
            "0" * 64,
            "--hash",
            "sha256",
            "--salt",
            "1" * 64,
            "--data-block-size",
            "4096",
            "--hash-block-size",
            "4096",
            "--data-blocks",
            "1",
        ]
    ]


def test_qualification_v3_verity_rejects_mutated_hash_image(tmp_path: Path):
    # Audit 2026-08-09 B3: mutation of either image fails before extraction.
    from benchmarks.codegraph_compare.verifier import _verify_verity

    data = tmp_path / "data.img"
    hashes = tmp_path / "hash.img"
    data.write_bytes(b"data")
    hashes.write_bytes(b"mutated")
    body = _qualification_v3_body()
    body["snapshot"].update(
        {
            "data_image_size": 4,
            "data_image_sha256": hashlib.sha256(b"data").hexdigest(),
            "hash_image_size": 4,
            "hash_image_sha256": hashlib.sha256(b"hash").hexdigest(),
        }
    )
    with pytest.raises(ValueError, match="image digest"):
        _verify_verity(
            body,
            {"data_image": str(data.resolve()), "hash_image": str(hashes.resolve())},
            lambda command: subprocess.CompletedProcess(command, 0, b"", b""),
        )


def test_qualification_v3_run_correlation_requires_process_isolation():
    # Audit 2026-08-09 P1.3: exit codes are never accepted as process identity.
    from benchmarks.codegraph_compare.verifier import verify_cell

    receipt = _qualification_v3_receipt()
    body = receipt["body"]
    failures = verify_cell(
        receipt,
        public_config=_qualification_v3_public_config(),
        plan={},
        inventory={},
        evidence={},
        verifier_nonce="a" * 64,
        verifier_image_digest=body["process_audit"]["image_digest"],
        process_identity="fresh-process",
        diagnostic_mode=True,
        diagnostic_root_public_key=__import__(
            "cryptography.hazmat.primitives.asymmetric.ed25519",
            fromlist=["Ed25519PrivateKey"],
        )
        .Ed25519PrivateKey.from_private_bytes(b"\x44" * 32)
        .public_key()
        .public_bytes_raw(),
    )
    assert failures == (
        "CELL_EVIDENCE_INVALID:verifier process is not isolated from producer",
    )


def test_qualification_v3_runtime_requires_exact_five_execution_order():
    # Audit 2026-08-09 P2.1: runtime and schema pin identical execution cardinality.
    from benchmarks.codegraph_compare.receipt_v3 import validate_body

    body = _qualification_v3_body()
    body["executions"].pop()
    with pytest.raises(ValueError, match="exact delete"):
        validate_body(body)


def test_qualification_v3_decision_commit_disconnect_queries_original_receipt(
    monkeypatch,
):
    # Audit 2026-08-09 B2: an EOF after commit must use the idempotent query path.
    import json
    import struct

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import decision_consumer_service as consumer
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    config = _qualification_v3_public_config()
    contract = {"decision_id": "d" * 64, "issued_at_ns": 0, "expires_at_ns": 2}
    envelope = {"manifest_sha256": "e" * 64}
    body = {
        "schema_version": 1,
        "decision_id": contract["decision_id"],
        "decision_contract_sha256": hashlib.sha256(
            canonical_json_bytes(contract)
        ).hexdigest(),
        "manifest_sha256": envelope["manifest_sha256"],
        "verdict_status": "SETUP_QUALIFIED",
        "consumed_at_ns": 1,
        "service_identity": config["trusted"]["decision_consumer_runtime"][
            "measurement"
        ],
    }
    receipt = {
        "receipt": body,
        "key_id": config["decision_consumer"]["key_id"],
        "algorithm": "Ed25519",
        "signature": Ed25519PrivateKey.from_private_bytes(b"\x66" * 32)
        .sign(consumer.RECEIPT_DOMAIN + canonical_json_bytes(body))
        .hex(),
    }
    requests = []

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 123, config["decision_consumer"]["peer_uid"], 123)

        def send(self, framed):
            requests.append(json.loads(framed[4:]))
            return len(framed)

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    replies = iter(
        (ValueError("frame truncated"), {"status": "consumed", "receipt": receipt})
    )

    def read_reply(*_args):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(consumer.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(consumer.socket, "socket", lambda *_args: FakeSocket())
    monkeypatch.setattr(consumer, "read_frame", read_reply)

    assert (
        consumer.request_decision(
            socket_path=Path("/unused"),
            contract=contract,
            envelope=envelope,
            config=config,
            timeout=1,
        )
        == receipt
    )
    assert [request["operation"] for request in requests] == [
        "consume-decision",
        "query-decision",
    ]
    assert requests[1]["decision_id"] == contract["decision_id"]


def test_qualification_v3_operator_delegates_privileged_run_cell_authority():
    operator = Path("scripts/no1_008a_operator.sh").read_text(encoding="utf-8")
    pipeline = Path("benchmarks/codegraph_compare/qualification_operator.py").read_text(
        encoding="utf-8"
    )
    assert (
        "from benchmarks.codegraph_compare.audit_authority_client import run_cell"
        in pipeline
    )
    assert "request_receipt" in pipeline
    assert "docker " not in operator
    assert "mkfs.ext4" not in operator
    assert "/var/run/docker.sock" not in operator


def test_qualification_v3_operator_preflight_requires_contracts_and_authority():
    operator = Path("scripts/no1_008a_operator.sh").read_text(encoding="utf-8")
    assert (
        '"$AUTHORITY_SOCKET" "$EXECUTOR_SOCKET" "$APPROVER_SOCKET" "$VERIFIER_SOCKET"'
        in operator
    )
    assert '"$PUBLIC_CONFIG" "$STAGED_ROOT"' in operator


def test_qualification_v3_runtime_schema_acceptance_parity():
    # Audit 2026-08-09 P2.1: published schema and runtime accept the same emitted receipt.
    from benchmarks.codegraph_compare.receipt_v3 import validate_receipt_shape

    receipt = _qualification_v3_receipt()
    validate_receipt_shape(receipt)


def test_qualification_v3_runtime_schema_mutation_contract():
    # Audit 2026-08-09 P2.1: representative shape mutations have exact parser parity.
    import copy

    from jsonschema import Draft202012Validator

    from benchmarks.codegraph_compare.receipt_v3 import (
        _published_schema,
        validate_receipt_shape,
    )

    schema, registry = _published_schema()
    validator = Draft202012Validator(schema, registry=registry)
    mutations = []
    missing = copy.deepcopy(_qualification_v3_receipt())
    del missing["body"]["run_nonce"]
    mutations.append(missing)
    extra = copy.deepcopy(_qualification_v3_receipt())
    extra["body"]["snapshot"]["mount_flags"] = ["ro"]
    mutations.append(extra)
    order = copy.deepcopy(_qualification_v3_receipt())
    order["body"]["executions"][0]["id"] = "health"
    mutations.append(order)
    duplicate = copy.deepcopy(_qualification_v3_receipt())
    duplicate["body"]["index_partition"]["indexed_paths"] *= 2
    mutations.append(duplicate)
    outcomes = []
    for receipt in mutations:
        try:
            validate_receipt_shape(receipt)
            runtime = True
        except ValueError:
            runtime = False
        schema_valid = not tuple(validator.iter_errors(receipt))
        outcomes.append((runtime, schema_valid))
    assert outcomes == [(False, False), (False, False), (False, False), (False, False)]


def test_receipt_v3_rejects_an_eighth_mount_with_wrong_target():
    # PR #1249 review 3744439666: the launch gate makes exactly eight targets.
    from benchmarks.codegraph_compare.receipt_v3 import validate_receipt_shape

    receipt = _qualification_v3_receipt()
    receipt["body"]["process_audit"]["mounts"][6][1] = "/unexpected"

    with pytest.raises(ValueError, match="mount"):
        validate_receipt_shape(receipt)


def test_receipt_v3_rejects_writable_non_output_mount():
    # PR #1249 review 3744302996: only the producer output mount is writable.
    from benchmarks.codegraph_compare.receipt_v3 import validate_receipt_shape

    receipt = _qualification_v3_receipt()
    receipt["body"]["process_audit"]["mounts"][0][2] = False

    with pytest.raises(ValueError, match="mount"):
        validate_receipt_shape(receipt)


def test_stage_copy_file_applies_requested_mode_despite_umask(tmp_path: Path):
    # PR #1249 review 3744303005: distinct service UIDs must read staged inputs.
    from benchmarks.codegraph_compare.stage_inputs import copy_file

    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.write_bytes(b"trusted")
    previous = os.umask(0o077)
    try:
        copy_file(source, destination, 0o444)
    finally:
        os.umask(previous)

    assert stat.S_IMODE(destination.stat().st_mode) == 0o444


def test_operator_success_state_replace_is_directory_durable(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744303001: terminal success must survive host power loss.
    from benchmarks.codegraph_compare import qualification_operator

    output = tmp_path / "experiment"
    synced = []
    monkeypatch.setattr(qualification_operator, "_run_impl", lambda _args: 0)
    monkeypatch.setattr(
        qualification_operator, "_fsync_directory", lambda path: synced.append(path)
    )

    assert qualification_operator.run(SimpleNamespace(experiment_root=str(output))) == 0
    assert synced == [output, output, output]
    assert json.loads((output / "operator-state.json").read_bytes()) == {
        "completed_cells": 14,
        "state": "SUCCESS",
    }


def test_operator_failed_state_replace_is_directory_durable(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744303001: terminal failure must survive host power loss.
    from benchmarks.codegraph_compare import qualification_operator

    output = tmp_path / "experiment"
    synced = []

    def fail(_args):
        raise RuntimeError("failed")

    monkeypatch.setattr(qualification_operator, "_run_impl", fail)
    monkeypatch.setattr(
        qualification_operator, "_fsync_directory", lambda path: synced.append(path)
    )

    with pytest.raises(RuntimeError, match="failed"):
        qualification_operator.run(SimpleNamespace(experiment_root=str(output)))
    assert synced == [output, output, output]
    assert json.loads((output / "operator-state.json").read_bytes()) == {
        "error": "RuntimeError",
        "state": "FAILED",
    }


def test_receipt_v3_docker_context_allows_only_five_schema_refs():
    # PR #1249 review 3744303008: the runtime schema COPY needs its exact closure.
    negations = [
        line
        for line in Path(".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.startswith("!rfcs")
    ]

    assert negations == [
        "!rfcs/",
        "!rfcs/schemas/",
        "!rfcs/schemas/no1-008a-cell-receipt-v3.schema.json",
        "!rfcs/schemas/no1-008a-cell-receipt-v3-body.schema.json",
        "!rfcs/schemas/no1-008a-cell-receipt-v3-common.schema.json",
        "!rfcs/schemas/no1-008a-cell-receipt-v3-fields-a.schema.json",
        "!rfcs/schemas/no1-008a-cell-receipt-v3-fields-b.schema.json",
    ]


def test_all_service_sockets_defer_access_control_to_peer_uid():
    # PR #1249 review 3744303010: service primary groups differ from the operator's.
    sources = {
        path: Path(path).read_text(encoding="utf-8")
        for path in (
            "benchmarks/codegraph_compare/audit_authority_service.py",
            "benchmarks/codegraph_compare/receipt_v3_service.py",
            "benchmarks/codegraph_compare/verifier_service.py",
            "benchmarks/codegraph_compare/decision_consumer_service.py",
        )
    }

    assert {
        path: (source.count("0o666"), source.count("peer_allowed("))
        for path, source in sources.items()
    } == {
        "benchmarks/codegraph_compare/audit_authority_service.py": (1, 1),
        "benchmarks/codegraph_compare/receipt_v3_service.py": (1, 1),
        "benchmarks/codegraph_compare/verifier_service.py": (1, 1),
        "benchmarks/codegraph_compare/decision_consumer_service.py": (1, 1),
    }


def test_qualification_v3_schema_fragments_stay_below_file_cap():
    # Audit 2026-08-09 P2.2: externally referenced schema fragments remain reviewable.
    schemas = sorted(Path("rfcs/schemas").glob("no1-008a-cell-receipt-v3*.schema.json"))
    assert [path.name for path in schemas] == [
        "no1-008a-cell-receipt-v3-body.schema.json",
        "no1-008a-cell-receipt-v3-common.schema.json",
        "no1-008a-cell-receipt-v3-fields-a.schema.json",
        "no1-008a-cell-receipt-v3-fields-b.schema.json",
        "no1-008a-cell-receipt-v3.schema.json",
    ]
    assert {path.name: len(path.read_text().splitlines()) for path in schemas} == {
        "no1-008a-cell-receipt-v3-body.schema.json": 62,
        "no1-008a-cell-receipt-v3-common.schema.json": 261,
        "no1-008a-cell-receipt-v3-fields-a.schema.json": 211,
        "no1-008a-cell-receipt-v3-fields-b.schema.json": 446,
        "no1-008a-cell-receipt-v3.schema.json": 35,
    }


def test_qualification_v3_operator_uses_only_root_authenticated_public_config():
    operator = Path("scripts/no1_008a_operator.sh").read_text()
    assert "parse_public_config" in operator
    assert "--diagnostic-mode" not in operator
    assert (
        "production CLIs authenticate"
        not in Path("benchmarks/codegraph_compare/README.md").read_text()
    )


def _diagnostic_authority_server(socket_path: Path, key: bytes):
    import socket
    import struct
    import threading

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare.host_auditor import DOMAIN
    from benchmarks.codegraph_compare.receipt_v3 import (
        canonical_json_bytes,
        strict_json_loads,
    )

    ready = threading.Event()

    def serve():
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(1)
        ready.set()
        connection, _ = listener.accept()
        header = connection.recv(4)
        size = struct.unpack("!I", header)[0]
        wire = bytearray()
        while len(wire) < size:
            wire.extend(connection.recv(size - len(wire)))
        request = strict_json_loads(bytes(wire))
        envelope = {
            "audit": request,
            "key_id": "auditor",
            "algorithm": "Ed25519",
            "signature": Ed25519PrivateKey.from_private_bytes(key)
            .sign(DOMAIN + canonical_json_bytes(request))
            .hex(),
        }
        response = canonical_json_bytes(envelope)
        connection.sendall(struct.pack("!I", len(response)) + response)
        connection.close()
        listener.close()
        socket_path.unlink(missing_ok=True)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    ready.wait(timeout=5)
    return thread


def test_qualification_external_audit_protocol_verifies_exact_signed_request(
    tmp_path: Path, monkeypatch
):
    # Mutation 5 (2026-08-10): only the external Unix authority may authorize an audit.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import audit_authority_client
    from benchmarks.codegraph_compare.host_auditor import DOMAIN, _authority

    monkeypatch.setattr(
        audit_authority_client,
        "_peer_credentials",
        lambda client: (1, os.getuid(), os.getgid()),
    )
    key = b"\x33" * 32
    socket_path = Path("/tmp") / f"tsa-audit-{os.getpid()}-{tmp_path.name[-6:]}.sock"
    thread = _diagnostic_authority_server(socket_path, key)
    authority = {
        "key_id": "auditor",
        "public_key_hex": Ed25519PrivateKey.from_private_bytes(key)
        .public_key()
        .public_bytes_raw()
        .hex(),
        "peer_uid": os.getuid(),
    }
    request = {
        "protocol": "no1-008a-audit-v1",
        "phase": "terminal",
        "service_measurement": "d" * 64,
        "audit": {"producer_container_id": "immutable-id"},
    }
    envelope = _authority(request, socket_path, authority, DOMAIN)
    thread.join(timeout=5)
    assert envelope["audit"] == request


def test_qualification_external_audit_protocol_rejects_forged_reply(
    tmp_path: Path, monkeypatch
):
    # Mutation 5 (2026-08-10): a socket endpoint without the pinned key is non-authorizing.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import audit_authority_client
    from benchmarks.codegraph_compare.host_auditor import DOMAIN, _authority

    monkeypatch.setattr(
        audit_authority_client,
        "_peer_credentials",
        lambda client: (1, os.getuid(), os.getgid()),
    )
    socket_path = Path("/tmp") / f"tsa-forge-{os.getpid()}-{tmp_path.name[-6:]}.sock"
    thread = _diagnostic_authority_server(socket_path, b"\x55" * 32)
    authority = {
        "key_id": "auditor",
        "public_key_hex": Ed25519PrivateKey.from_private_bytes(b"\x33" * 32)
        .public_key()
        .public_bytes_raw()
        .hex(),
        "peer_uid": os.getuid(),
    }
    request = {
        "protocol": "no1-008a-audit-v1",
        "phase": "terminal",
        "service_measurement": "d" * 64,
        "audit": {},
    }
    with pytest.raises(ValueError, match="signature mismatch"):
        _authority(request, socket_path, authority, DOMAIN)
    thread.join(timeout=5)


def test_qualification_host_auditor_rejects_local_private_key_cli():
    # Mutation 5 (2026-08-10): production has no local auditor-key compatibility path.
    from benchmarks.codegraph_compare.host_auditor import main

    with pytest.raises(SystemExit) as error:
        main(
            [
                "launch",
                "--container",
                "container",
                "--seccomp",
                "/seccomp",
                "--expected-image",
                "image@sha256:" + "1" * 64,
                "--authority-socket",
                "/authority.sock",
                "--public-config",
                "/config.json",
                "--since",
                "1",
                "--run-nonce",
                "2" * 64,
                "--private-key",
                "/local/auditor.key",
            ]
        )
    assert error.value.code == 2


def test_qualification_host_auditor_checks_root_pinned_top_level_image_id():
    # Mutation 5 (2026-08-10): Config.Image alone cannot authorize a container.
    from benchmarks.codegraph_compare.host_auditor import _docker_facts

    inspected = {
        "Image": "sha256:" + "9" * 64,
        "Config": {"Image": "producer@sha256:" + "1" * 64, "User": "65532:65532"},
        "HostConfig": {
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "NetworkMode": "none",
            "SecurityOpt": ["no-new-privileges", "seccomp=/trusted/seccomp"],
            "PidsLimit": 64,
            "Memory": 4294967296,
            "NanoCpus": 1000000000,
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=64m"},
        },
    }
    with pytest.raises(ValueError, match="top-level Image ID"):
        _docker_facts(
            inspected,
            "producer@sha256:" + "1" * 64,
            "sha256:" + "8" * 64,
            Path("/trusted/seccomp"),
        )


def test_qualification_host_auditor_preserves_exact_observed_security_options():
    # PR #1249 review 3745026819: terminal evidence is observed, not synthesized.
    from benchmarks.codegraph_compare.host_auditor import (
        PRODUCER_GATE_TARGET,
        PRODUCER_GATE_WRAPPER,
        _docker_facts,
    )

    image = "producer@sha256:" + "1" * 64
    image_id = "sha256:" + "8" * 64
    inspected = {
        "Image": image_id,
        "Config": {
            "Image": image,
            "User": "65532:65532",
            "Entrypoint": ["/bin/sh"],
            "Cmd": [
                "-c",
                PRODUCER_GATE_WRAPPER,
                "no1-008a-gate",
                PRODUCER_GATE_TARGET,
                "--plan",
                "/plan/cell-plan.json",
                "--out",
                "/out",
            ],
        },
        "HostConfig": {
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "NetworkMode": "none",
            "SecurityOpt": ["no-new-privileges", "seccomp=/trusted/seccomp"],
            "PidsLimit": 64,
            "Memory": 4294967296,
            "NanoCpus": 1000000000,
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=64m"},
        },
    }

    assert _docker_facts(inspected, image, image_id, Path("/trusted/seccomp"))[
        "security_opt"
    ] == ["no-new-privileges", "seccomp=/trusted/seccomp"]


def test_qualification_host_auditor_rejects_extra_security_option():
    # PR #1249 review 3745026819: unrequested Docker isolation options fail closed.
    from benchmarks.codegraph_compare.host_auditor import (
        PRODUCER_GATE_TARGET,
        PRODUCER_GATE_WRAPPER,
        _docker_facts,
    )

    image = "producer@sha256:" + "1" * 64
    inspected = {
        "Image": "sha256:" + "8" * 64,
        "Config": {
            "Image": image,
            "User": "65532:65532",
            "Entrypoint": ["/bin/sh"],
            "Cmd": [
                "-c",
                PRODUCER_GATE_WRAPPER,
                "no1-008a-gate",
                PRODUCER_GATE_TARGET,
                "--plan",
                "/plan/cell-plan.json",
                "--out",
                "/out",
            ],
        },
        "HostConfig": {
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "NetworkMode": "none",
            "SecurityOpt": [
                "no-new-privileges",
                "seccomp=/trusted/seccomp",
                "label=disable",
            ],
            "PidsLimit": 64,
            "Memory": 4294967296,
            "NanoCpus": 1000000000,
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=64m"},
        },
    }

    with pytest.raises(ValueError, match="security facts mismatch"):
        _docker_facts(
            inspected,
            image,
            "sha256:" + "8" * 64,
            Path("/trusted/seccomp"),
        )


def test_no1_008a_wrapper_forwards_decision_service_inputs(tmp_path: Path):
    # PR #1249 review 3744178808: the documented wrapper dropped required inputs.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "argv"
    python = fake_bin / "python3"
    python.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = - ]; then cat >/dev/null; exit 0; fi\n'
        'printf \'%s\\n\' "$@" > "$CAPTURE"\n'
    )
    python.chmod(0o755)
    realpath = fake_bin / "realpath"
    realpath.write_text(
        "#!/bin/sh\n"
        '[ "$1" = -e ] && shift\n'
        '[ "$1" = -- ] && shift\n'
        "printf '%s\\n' \"$1\"\n"
    )
    realpath.chmod(0o755)
    paths = {}
    for name in ("contracts", "staged"):
        paths[name] = tmp_path / name
        paths[name].mkdir()
    for name in (
        "authority.sock",
        "executor.sock",
        "approver.sock",
        "verifier.sock",
        "decision.sock",
        "decision.json",
        "config.json",
    ):
        paths[name] = tmp_path / name
        paths[name].write_bytes(b"{}")
    command = [
        "bash",
        "scripts/no1_008a_operator.sh",
        "run",
        "--contracts-dir",
        str(paths["contracts"]),
        "--authority-socket",
        str(paths["authority.sock"]),
        "--executor-socket",
        str(paths["executor.sock"]),
        "--approver-socket",
        str(paths["approver.sock"]),
        "--verifier-socket",
        str(paths["verifier.sock"]),
        "--decision-consumer-socket",
        str(paths["decision.sock"]),
        "--decision-contract",
        str(paths["decision.json"]),
        "--public-config",
        str(paths["config.json"]),
        "--staged-root",
        str(paths["staged"]),
        "--experiment-root",
        str(tmp_path / "experiment"),
    ]
    environment = {**os.environ, "CAPTURE": str(capture)}
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

    result = subprocess.run(command, env=environment, capture_output=True, text=True)

    assert result.returncode == 0
    argv = capture.read_text().splitlines()
    assert argv[argv.index("--decision-consumer-socket") + 1] == str(
        paths["decision.sock"]
    )
    assert argv[argv.index("--decision-contract") + 1] == str(paths["decision.json"])


def test_authority_materialized_source_is_immutable_and_producer_readable(
    tmp_path: Path,
):
    # PR #1249 review 3744178810: UID 65532 could not traverse root-only snapshots.
    import io
    import stat
    import tarfile

    from benchmarks.codegraph_compare.audit_authority_storage import (
        _materialize_source,
    )

    snapshot = tmp_path / "source.tar"
    payloads = {
        "pkg/main.py": ("100644", b"print('ok')\n"),
        "pkg/run.sh": ("100755", b"#!/bin/sh\nexit 0\n"),
    }
    with tarfile.open(snapshot, "w") as archive:
        for relative, (git_mode, payload) in payloads.items():
            info = tarfile.TarInfo(relative)
            info.size = len(payload)
            info.uid = info.gid = 0
            info.mode = 0o755 if git_mode == "100755" else 0o644
            archive.addfile(info, io.BytesIO(payload))
    destination = tmp_path / "source"
    inventory = json.dumps(
        {
            "eligibility": {
                "tracked_files": [
                    [
                        relative,
                        git_mode,
                        hashlib.sha1(
                            f"blob {len(payload)}\0".encode() + payload
                        ).hexdigest(),
                        len(payload),
                        hashlib.sha256(payload).hexdigest(),
                    ]
                    for relative, (git_mode, payload) in payloads.items()
                ]
            }
        }
    ).encode()

    _materialize_source(
        snapshot,
        destination,
        inventory_payload=inventory,
        ceiling=snapshot.stat().st_size,
    )

    assert {
        relative: stat.S_IMODE((destination / relative).stat().st_mode)
        for relative in payloads
    } == {"pkg/main.py": 0o444, "pkg/run.sh": 0o555}
    assert stat.S_IMODE((destination / "pkg").stat().st_mode) == 0o555
    assert stat.S_IMODE(destination.stat().st_mode) == 0o555


def test_stage_inventory_tree_uses_read_only_modes_from_git_inventory(
    tmp_path: Path,
):
    # PR #1249 review 3744439670: staged executable and regular blobs must be immutable.
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes
    from benchmarks.codegraph_compare.stage_inputs import stage_inventory_tree

    source = tmp_path / "checkout"
    source.mkdir()
    payloads = {
        "README.md": ("100644", b"fixture\n"),
        "bin/tool": ("100755", b"#!/bin/sh\n"),
    }
    records = []
    for relative, (mode, payload) in payloads.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        oid = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
        records.append(
            [relative, mode, oid, len(payload), hashlib.sha256(payload).hexdigest()]
        )
    inventory = tmp_path / "inventory.json"
    inventory.write_bytes(
        canonical_json_bytes({"eligibility": {"tracked_files": records}})
    )
    destination = tmp_path / "staged"

    stage_inventory_tree(source, destination, tmp_path / "source.tar", inventory)

    assert {
        relative: stat.S_IMODE((destination / relative).stat().st_mode)
        for relative in payloads
    } == {"README.md": 0o444, "bin/tool": 0o555}
    assert stat.S_IMODE((destination / "bin").stat().st_mode) == 0o555
    assert stat.S_IMODE(destination.stat().st_mode) == 0o555


def test_verifier_ledger_is_private_and_owned_by_service_uid(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744178813: verifier USER 903 must own its writable ledger.
    import stat

    from benchmarks.codegraph_compare.verifier_ledger import ChallengeLedger

    monkeypatch.setattr(ChallengeLedger, "_acquire_lease", lambda _self: None)
    ChallengeLedger(tmp_path / "ledger.sqlite")
    metadata = (tmp_path / "ledger.sqlite").stat()
    assert metadata.st_uid == os.geteuid()
    assert stat.S_IMODE(metadata.st_mode) == 0o600


def test_no1_008a_dockerfile_has_independent_decision_consumer_target():
    # PR #1249 review 3744178814: the final decision service was not buildable.
    dockerfile = Path("benchmarks/codegraph_compare/Dockerfile.no1-008a").read_text()
    target = dockerfile.split("FROM runtime AS decision-consumer\n", 1)[1]
    assert 'org.tree-sitter-analyzer.no1-008a.role="decision-consumer"' in target
    assert "USER 904:904" in target
    assert (
        'ENTRYPOINT ["python", "-m", '
        '"benchmarks.codegraph_compare.decision_consumer_service"]'
    ) in target


def _authority_runner_for_test(tmp_path: Path):
    import threading

    from benchmarks.codegraph_compare.audit_authority_runner import AuthorityRunner

    runner = AuthorityRunner.__new__(AuthorityRunner)
    runner._artifacts = tmp_path
    runner._semaphore = threading.BoundedSemaphore(1)
    runner._lock_path = tmp_path / ".authority.lock"
    runner._lock_path.write_bytes(b"")
    return runner


def test_authority_serializes_distinct_signed_jobs(tmp_path: Path):
    # PR #1249 review 3744178818: direct clients bypassed max_concurrency=1.
    import threading
    import time

    runner = _authority_runner_for_test(tmp_path)
    runner._sync_sealed_job = lambda _job_id, _result: None
    guard = threading.Lock()
    active = 0
    maximum = 0

    def execute(_contract):
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.05)
        with guard:
            active -= 1
        return {"ok": True}

    runner._execute = execute
    threads = [
        threading.Thread(target=runner, args=({"job_id": digit * 64},))
        for digit in ("1", "2")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert maximum == 1
    assert [
        (tmp_path / f"{digit * 64}.state").read_bytes() for digit in ("1", "2")
    ] == [b"SUCCESS\n", b"SUCCESS\n"]


def test_authority_fsyncs_parent_after_reservation_and_terminal_replace(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744178821: file fsync alone did not persist directory entries.
    from benchmarks.codegraph_compare import audit_authority_runner

    runner = _authority_runner_for_test(tmp_path)
    runner._execute = lambda _contract: {"ok": True}
    runner._sync_sealed_job = lambda _job_id, _result: None
    synced = []
    monkeypatch.setattr(
        audit_authority_runner, "_fsync_directory", lambda path: synced.append(path)
    )

    runner({"job_id": "3" * 64})

    assert synced == [tmp_path, tmp_path]


def test_operator_gives_authority_aggregate_remaining_timeout(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744178822: sealing time must not consume producer wall budget.
    from benchmarks.codegraph_compare import qualification_operator
    from benchmarks.codegraph_compare.receipt_v3 import (
        canonical_json_bytes,
        canonical_plan_hash,
    )
    from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS

    contracts_dir = tmp_path / "contracts"
    staged_root = tmp_path / "staged"
    contracts_dir.mkdir()
    staged_root.mkdir()
    plans = []
    contracts = []
    for ordinal, (repo, arm) in enumerate(EXPECTED_CELLS):
        plan = {
            "cell": {"repo_id": repo, "arm_id": arm, "attempt": 1},
            "wall_timeout_seconds": 10,
            "resource_ceilings": {"io_bytes": 32 * 1024 * 1024},
        }
        plan["plan_hash"] = canonical_plan_hash(plan)
        plans.append(plan)
        job_id = f"{ordinal + 1:064x}"
        contract = {
            "job_id": job_id,
            "cell": plan["cell"],
            "nonce": "a" * 64,
            "decision_id": "b" * 64,
            "expires_at_ns": 10**30,
        }
        contracts.append(contract)
        (contracts_dir / f"{ordinal}.json").write_bytes(canonical_json_bytes(contract))
        job = staged_root / job_id
        job.mkdir()
        (job / "plan.json").write_bytes(canonical_json_bytes(plan))
        (job / "inventory.json").write_bytes(canonical_json_bytes({"repo_id": repo}))
    decision = {
        "decision_id": "b" * 64,
        "expires_at_ns": 10**30,
        "plan_set_hash": "c" * 64,
        "cells": [
            {
                "repo_id": repo,
                "arm_id": arm,
                "plan_sha256": canonical_plan_hash(plan),
            }
            for (repo, arm), plan in zip(EXPECTED_CELLS, plans, strict=True)
        ],
    }
    decision_path = tmp_path / "decision.json"
    decision_path.write_bytes(canonical_json_bytes(decision))
    digest = hashlib.sha256(canonical_json_bytes(decision)).hexdigest()
    for contract in contracts:
        contract["decision_contract_sha256"] = digest
    # Rewrite after adding the common decision digest.
    for ordinal, contract in enumerate(contracts):
        (contracts_dir / f"{ordinal}.json").write_bytes(canonical_json_bytes(contract))
    public_config = tmp_path / "public.json"
    public_config.write_bytes(b"{}")
    monkeypatch.setattr(
        qualification_operator,
        "parse_public_config",
        lambda _raw: {
            "auditor": {"peer_uid": 0},
            "trusted": {
                "plan_set_hash": "c" * 64,
                "inventory_sha256": {
                    repo: hashlib.sha256(
                        canonical_json_bytes({"repo_id": repo})
                    ).hexdigest()
                    for repo, _arm in EXPECTED_CELLS
                },
                "verifier_runtime": {"measurement": {}},
            },
        },
    )
    monkeypatch.setattr(
        qualification_operator, "verify_decision_contract", lambda value: value
    )
    monkeypatch.setattr(
        qualification_operator, "verify_configured_plan_set", lambda *_args: None
    )
    monkeypatch.setattr(
        qualification_operator, "validate_producer_plan", lambda value: value
    )
    monkeypatch.setattr(
        qualification_operator, "validate_receipt_inventory", lambda value: value
    )
    monkeypatch.setattr(
        qualification_operator,
        "verify_contract",
        lambda request: request["contract"],
    )
    ticks = iter((100.0, 101.0))
    monkeypatch.setattr(
        qualification_operator,
        "time",
        SimpleNamespace(
            monotonic=lambda: next(ticks), time_ns=__import__("time").time_ns
        ),
    )
    observed = []

    def stop_after_authority(_contract, _socket, authority):
        observed.append(authority["wall_timeout_seconds"])
        raise RuntimeError("observed authority timeout")

    monkeypatch.setattr(qualification_operator, "run_cell", stop_after_authority)
    args = SimpleNamespace(
        public_config=str(public_config),
        contracts_dir=str(contracts_dir),
        decision_contract=str(decision_path),
        staged_root=str(staged_root),
        authority_socket=str(tmp_path / "authority.sock"),
    )

    with pytest.raises(RuntimeError, match="observed authority timeout"):
        qualification_operator._run_impl(args)

    assert observed == [1932]
    assert plans[0]["wall_timeout_seconds"] == 10


def test_receipt_image_provenance_excludes_post_decision_consumer():
    # PR #1249 review 3744178824: receipt-v3 signs exactly five pre-decision roles.
    from benchmarks.codegraph_compare.verifier_evidence import _receipt_images

    images = {
        role: f"sha256:{number:064x}"
        for number, role in enumerate(
            (
                "producer",
                "executor",
                "approver",
                "auditor",
                "verifier",
                "decision_consumer",
            ),
            start=1,
        )
    }

    assert _receipt_images({"images": images}) == {
        role: images[role]
        for role in ("producer", "executor", "approver", "auditor", "verifier")
    }


def test_authority_mounts_authenticated_plan_inputs_at_exact_read_only_targets():
    # PR #1249 review 3744178826: staged tool/config bytes must reach plan argv paths.
    from benchmarks.codegraph_compare.audit_authority_storage import (
        _producer_mount_targets,
    )

    plan = {
        "executions": [
            {
                "id": execution_id,
                "argv": [
                    "/tool/bin",
                    execution_id,
                    "--config",
                    "/config/pinned.json",
                    *(["--source", "/source"] if execution_id == "build" else []),
                ],
            }
            for execution_id in ("delete", "build", "health", "symbol", "call")
        ]
    }
    runner_source = Path(
        "benchmarks/codegraph_compare/audit_authority_runner.py"
    ).read_text()

    assert _producer_mount_targets(plan) == (
        "/source",
        "/tool/bin",
        "/config/pinned.json",
    )
    assert '(job / "tool", tool_target, True)' in runner_source
    assert '(job / "config", config_target, True)' in runner_source
    assert '(job / "seccomp", "/plan/seccomp.json", True)' in runner_source


def test_host_auditor_accepts_only_all_eight_exact_producer_bind_mounts(
    tmp_path: Path,
    monkeypatch,
):
    # PR #1249 review 3744261017: authenticated tool/config/seccomp mounts are mandatory.
    from benchmarks.codegraph_compare.host_auditor import _mounts
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    staged = tmp_path / "staged"
    artifact = tmp_path / "artifact"
    staged.mkdir()
    artifact.mkdir()
    source = artifact / "source"
    output = artifact / "producer-output"
    gate = artifact / "producer-launch-gate"
    source.mkdir()
    output.mkdir()
    os.mkfifo(gate, mode=0o444)
    plan = {
        "executions": [
            {
                "id": name,
                "argv": [
                    "/tool/bin",
                    name,
                    "--config",
                    "/config/pinned.json",
                    *(["--source", "/source"] if name == "build" else []),
                ],
            }
            for name in ("delete", "build", "health", "symbol", "call")
        ]
    }
    sources = {
        "/source": source,
        "/tool/bin": staged / "tool",
        "/config/pinned.json": staged / "config",
        "/plan/seccomp.json": staged / "seccomp",
        "/plan/cell-plan.json": staged / "plan.json",
        "/plan/inventory.json": staged / "inventory.json",
        "/run/no1-008a-launch-gate": gate,
        "/out": output,
    }
    for target in sources.values():
        if not target.exists():
            target.write_bytes(b"x")
    sources["/plan/cell-plan.json"].write_bytes(canonical_json_bytes(plan))
    inspected = {
        "Mounts": [
            {
                "Type": "bind",
                "Source": str(source_path),
                "Destination": target,
                "RW": target == "/out",
                "Propagation": "rprivate",
            }
            for target, source_path in sources.items()
        ]
    }

    real_lstat = os.lstat

    def authority_lstat(path):
        metadata = real_lstat(path)
        if Path(path) == gate:
            return SimpleNamespace(
                st_mode=metadata.st_mode, st_uid=0, st_nlink=metadata.st_nlink
            )
        return metadata

    monkeypatch.setattr(
        "benchmarks.codegraph_compare.host_auditor.os.lstat", authority_lstat
    )
    assert set(_mounts(inspected)) == set(sources)
    inspected["Mounts"][1]["Source"] = str(staged / "config")
    with pytest.raises(ValueError, match="authenticated mount source mismatch"):
        _mounts(inspected)


def test_authority_removes_ext4_lost_found_and_checks_payload_before_verity():
    # PR #1249 review 3744439674: mkfs lost+found must not alter the signed tree hash.
    source = Path("benchmarks/codegraph_compare/audit_authority_runner.py").read_text()

    commands = [
        '"mkfs.ext4",',
        '_run("debugfs", "-w", "-R", "rmdir lost+found", str(data))',
        "_assert_ext4_payload(",
        '"veritysetup", "format", str(data), str(hashes)',
    ]

    sealing = source[source.index("data_size, inode_count, payload_bytes =") :]
    assert [sealing.index(command) for command in commands] == sorted(
        sealing.index(command) for command in commands
    )


def test_authority_streams_repository_sized_source_archive_under_inventory_ceiling(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744261021: source snapshots are not receipt-sized messages.
    import io
    import tarfile

    from benchmarks.codegraph_compare import audit_authority_storage as storage
    from benchmarks.codegraph_compare.audit_authority_storage import (
        _materialize_source,
        _sha,
        _source_archive_ceiling,
    )
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    payload = b"x" * (17 * 1024 * 1024)
    inventory = canonical_json_bytes(
        {
            "eligibility": {
                "tracked_files": [
                    [
                        "large.bin",
                        "100644",
                        hashlib.sha1(
                            f"blob {len(payload)}\0".encode() + payload
                        ).hexdigest(),
                        len(payload),
                        hashlib.sha256(payload).hexdigest(),
                    ]
                ]
            }
        }
    )
    ceiling = _source_archive_ceiling(inventory)
    snapshot = tmp_path / "source.tar"
    with tarfile.open(snapshot, "w", format=tarfile.USTAR_FORMAT) as archive:
        info = tarfile.TarInfo("large.bin")
        info.size = len(payload)
        info.uid = info.gid = 0
        info.mode = 0o644
        archive.addfile(info, io.BytesIO(payload))

    destination = tmp_path / "source"
    monkeypatch.setattr(
        storage,
        "_read",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("source archive was buffered through _read")
        ),
    )
    digest = _sha(snapshot, limit=ceiling)
    _materialize_source(
        snapshot, destination, inventory_payload=inventory, ceiling=ceiling
    )

    assert digest == hashlib.sha256(snapshot.read_bytes()).hexdigest()
    assert (destination / "large.bin").stat().st_size == 17 * 1024 * 1024


def test_decision_ledger_requires_uid_904_private_writable_parent(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744261023: SQLite WAL needs a service-owned private parent.
    import stat

    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    parent = tmp_path / "ledger"
    parent.mkdir(mode=0o700)
    real_stat = consumer.os.stat

    def service_stat(path, *args, **kwargs):
        metadata = real_stat(path, *args, **kwargs)
        if Path(path) == parent:
            return SimpleNamespace(st_uid=904, st_mode=stat.S_IFDIR | 0o700)
        return metadata

    monkeypatch.setattr(consumer.os, "stat", service_stat)
    monkeypatch.setattr(
        consumer.os,
        "access",
        lambda path, mode: (path, mode) == (parent, os.W_OK | os.X_OK),
    )

    ledger = consumer.DecisionLedger(
        parent / "decisions.sqlite", _qualification_v3_public_config()
    )

    assert ledger.path == parent / "decisions.sqlite"
    assert stat.S_IMODE(ledger.path.stat().st_mode) == 0o600

    def root_stat(path, *args, **kwargs):
        metadata = real_stat(path, *args, **kwargs)
        if Path(path) == parent:
            return SimpleNamespace(st_uid=0, st_mode=stat.S_IFDIR | 0o700)
        return metadata

    monkeypatch.setattr(consumer.os, "stat", root_stat)
    with pytest.raises(ValueError, match="UID 904 private 0700"):
        consumer.DecisionLedger(
            parent / "other.sqlite", _qualification_v3_public_config()
        )


def test_decision_consumer_recomputes_ordered_exact14_config_plan_binding():
    # PR #1249 review 3744261026: direct consumers must enforce root config plans.
    from benchmarks.codegraph_compare.decision_consumer_service import (
        verify_configured_plan_set,
    )
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes
    from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS

    hashes = [f"{ordinal:064x}" for ordinal in range(1, 15)]
    plan_set_hash = hashlib.sha256(canonical_json_bytes(hashes)).hexdigest()
    contract = {
        "plan_set_hash": plan_set_hash,
        "cells": [
            {"repo_id": repo, "arm_id": arm, "plan_sha256": digest}
            for (repo, arm), digest in zip(EXPECTED_CELLS, hashes, strict=True)
        ],
    }
    config = {
        "trusted": {
            "plan_set_hash": plan_set_hash,
            "plan_hashes": {
                f"{repo}/{arm}": digest
                for (repo, arm), digest in zip(EXPECTED_CELLS, hashes, strict=True)
            },
        }
    }

    verify_configured_plan_set(contract, config)
    contract["cells"][13]["plan_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="root-config authorized"):
        verify_configured_plan_set(contract, config)


def test_verifier_manifest_parser_uses_64mib_protocol_not_receipt_limits():
    # PR #1249 review 3744261030: exact-14 manifests have independent frame bounds.
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes
    from benchmarks.codegraph_compare.verifier_service import _manifest_json_loads

    repeated_inventory = "x" * (17 * 1024 * 1024)
    manifest = {
        "operation": "verify-exact-14",
        "cells": [
            {
                "repo_id": f"repo-{ordinal}",
                "tracked_inventory": repeated_inventory if ordinal == 0 else "",
            }
            for ordinal in range(14)
        ],
    }
    payload = canonical_json_bytes(manifest)

    parsed = _manifest_json_loads(payload)

    assert len(payload) == 17_826_453
    assert len(parsed["cells"]) == 14


def test_authority_deadline_subtracts_docker_start_rpc_and_audit_time(monkeypatch):
    # PR #1249 review 3744261033: producer budget is Docker StartedAt-to-FinishedAt.
    from benchmarks.codegraph_compare import audit_authority_runner as runner

    clock = SimpleNamespace(
        time=lambda: 1_003.0,
        monotonic=lambda: 500.0,
        time_ns=lambda: 1_000_000_000,
    )
    monkeypatch.setattr(runner, "time", clock)
    process_timeouts = []

    class ImmediateProcess:
        returncode = 0

        def __init__(self, args):
            self.args = args

        def communicate(self, timeout):
            process_timeouts.append((tuple(self.args), timeout))
            return b"0\n", b""

    monkeypatch.setattr(
        runner.subprocess,
        "Popen",
        lambda args, **_kwargs: ImmediateProcess(args),
    )

    deadline = runner._docker_wall_deadline("1970-01-01T00:16:40Z", 10)
    exit_code = runner._wait_container("producer", deadline)
    runner._run("seal-command")

    extraction_calls = []
    monkeypatch.setattr(runner, "_hash_tree", lambda _path: "same")
    monkeypatch.setattr(
        runner,
        "_run",
        lambda *args, timeout: extraction_calls.append((args, timeout)) or b"",
    )
    runner._assert_ext4_payload(
        Path("data.img"),
        Path("core"),
        payload_bytes=64 * 1024 * 1024,
        contract_expires_at_ns=33_000_000_000,
    )

    assert deadline == 507.0
    assert exit_code == "0"
    assert process_timeouts == [
        (("docker", "wait", "producer"), 7.0),
        (("seal-command",), 120),
    ]
    extraction_command, extraction_timeout = extraction_calls[0]
    assert extraction_command[:2] == ("debugfs", "-R")
    assert extraction_command[2].startswith("rdump / ")
    assert extraction_command[3] == "data.img"
    assert extraction_timeout == 32.0


def test_decision_consumer_contains_four_malformed_connections_and_recovers(
    monkeypatch,
):
    # PR #1249 review 3744358507: per-connection failures must not drain workers.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    class Connection:
        def __init__(self, send_error=False):
            self.closed = False
            self.sent = []
            self.send_error = send_error

        def sendall(self, payload):
            if self.send_error:
                raise BrokenPipeError("peer disconnected")
            self.sent.append(payload)

        def close(self):
            self.closed = True

    key = __import__(
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        fromlist=["Ed25519PrivateKey"],
    ).Ed25519PrivateKey.from_private_bytes(b"\x11" * 32)
    connections = [
        Connection(),
        Connection(),
        Connection(),
        Connection(send_error=True),
    ]
    read_results = iter(
        (
            EOFError("truncated header"),
            ValueError("oversized frame"),
            ValueError("malformed JSON"),
            {"operation": "query-decision"},
        )
    )
    monkeypatch.setattr(consumer, "peer_allowed", lambda *_args: None)

    def read_request(*_args):
        result = next(read_results)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(consumer, "read_frame", read_request)
    monkeypatch.setattr(consumer, "consume_request", lambda *_args: {"ok": True})
    for connection in connections:
        consumer._serve_connection(connection, 901, {}, object(), key, {})

    healthy = Connection()
    monkeypatch.setattr(consumer, "read_frame", lambda *_args: {"operation": "query"})
    consumer._serve_connection(healthy, 901, {}, object(), key, {})

    assert [connection.closed for connection in connections] == [True, True, True, True]
    assert healthy.closed is True
    assert len(healthy.sent) == 1


def test_decision_consumer_contains_peer_and_handler_errors(monkeypatch):
    # PR #1249 review 3744358507: SO_PEERCRED and handler errors stay connection-local.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    class Connection:
        def __init__(self):
            self.closed = False
            self.sent = []

        def sendall(self, payload):
            self.sent.append(payload)

        def close(self):
            self.closed = True

    key = __import__(
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        fromlist=["Ed25519PrivateKey"],
    ).Ed25519PrivateKey.from_private_bytes(b"\x12" * 32)
    denied = Connection()
    monkeypatch.setattr(
        consumer,
        "peer_allowed",
        lambda *_args: (_ for _ in ()).throw(PermissionError("wrong UID")),
    )
    consumer._serve_connection(denied, 901, {}, object(), key, {})

    handled = Connection()
    monkeypatch.setattr(consumer, "peer_allowed", lambda *_args: None)
    monkeypatch.setattr(consumer, "read_frame", lambda *_args: {})
    monkeypatch.setattr(
        consumer,
        "consume_request",
        lambda *_args: (_ for _ in ()).throw(ValueError("bad decision")),
    )
    consumer._serve_connection(handled, 901, {}, object(), key, {})

    assert denied.closed is True
    assert denied.sent == []
    assert handled.closed is True
    assert len(handled.sent) == 1


def test_decision_consumer_rejects_wrong_private_key_before_ledger_or_listener(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744358513: a wrong key must not poison the one-shot ledger.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    public = tmp_path / "public.json"
    public.write_bytes(b"{}")
    launch_attestation = tmp_path / "launch.json"
    launch_attestation.write_bytes(b"{}")
    configured_key = __import__(
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        fromlist=["Ed25519PrivateKey"],
    ).Ed25519PrivateKey.from_private_bytes(b"\x66" * 32)
    monkeypatch.setattr(consumer.os, "geteuid", lambda: 904)
    monkeypatch.setattr(
        consumer,
        "parse_public_config",
        lambda _raw: {
            "decision_consumer": {
                "peer_uid": 904,
                "public_key_hex": configured_key.public_key().public_bytes_raw().hex(),
            },
            "trusted": {"decision_consumer_runtime": {"measurement": {}}},
        },
    )
    monkeypatch.setattr(consumer, "measure_runtime", lambda _value: {})
    monkeypatch.setattr(consumer, "wait_for_launch_release", lambda *_args: b"{}")
    monkeypatch.setattr(
        consumer, "verify_service_launch_attestation", lambda *_args: {}
    )
    descriptor = os.open(os.devnull, os.O_RDONLY)
    monkeypatch.setattr(
        consumer, "secure_key", lambda *_args: (descriptor, b"\x65" * 32)
    )
    monkeypatch.setattr(
        consumer,
        "DecisionLedger",
        lambda *_args: (_ for _ in ()).throw(AssertionError("ledger opened")),
    )

    with pytest.raises(SystemExit, match="does not match public config"):
        consumer.main(
            [
                "--socket",
                str(tmp_path / "decision.sock"),
                "--private-key",
                str(tmp_path / "key"),
                "--public-config",
                str(public),
                "--ledger",
                str(tmp_path / "ledger.sqlite"),
                "--launch-attestation",
                str(launch_attestation),
                "--launch-release",
                str(tmp_path / "RELEASE"),
                "--allowed-client-uid",
                "901",
            ]
        )


def test_operator_write_completes_short_writes_before_fsync(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744358510: a successful write retains the full envelope.
    from benchmarks.codegraph_compare import qualification_operator as operator

    real_write = os.write

    def short_write(descriptor, payload):
        return real_write(descriptor, payload[:3])

    monkeypatch.setattr(operator.os, "write", short_write)
    path = tmp_path / "evidence.json"
    operator._write(path, {"status": "SUCCESS"})

    assert path.read_bytes() == b'{"status":"SUCCESS"}\n'


def test_operator_write_rejects_zero_progress(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744358510: zero-byte writes cannot report operator success.
    from benchmarks.codegraph_compare import qualification_operator as operator

    monkeypatch.setattr(operator.os, "write", lambda *_args: 0)
    with pytest.raises(OSError, match="made no progress"):
        operator._write(tmp_path / "evidence.json", {"status": "SUCCESS"})


def test_launch_attestation_handoff_uses_private_role_owned_paths(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744358508: distinct service UIDs can read only their artifact.
    from benchmarks.codegraph_compare import service_runtime

    output = tmp_path / "handoff"
    public = tmp_path / "public.json"
    public.write_bytes(b"{}")
    descriptor = os.open(os.devnull, os.O_RDONLY)
    monkeypatch.setattr(service_runtime.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        service_runtime, "secure_key", lambda *_args: (descriptor, b"\x31" * 32)
    )
    monkeypatch.setattr(
        "benchmarks.codegraph_compare.verifier.parse_public_config", lambda _raw: {}
    )
    monkeypatch.setattr(
        service_runtime,
        "create_service_launch_attestation",
        lambda _container, role, *_args: {"role": role},
    )
    directory_owners = []
    file_owners = []
    monkeypatch.setattr(
        service_runtime.os,
        "chown",
        lambda path, uid, gid: directory_owners.append((Path(path).name, uid, gid)),
    )
    monkeypatch.setattr(
        service_runtime.os,
        "fchown",
        lambda _fd, uid, gid: file_owners.append((uid, gid)),
    )
    mappings = [
        item
        for role in ("executor", "approver", "auditor", "verifier", "decision_consumer")
        for item in ("--container", f"{role}=container-{role}")
    ]
    assert (
        service_runtime.main(
            [
                "attest-launch",
                "--public-config",
                str(public),
                "--private-key",
                "key",
                "--key-id",
                "launcher",
                "--output-dir",
                str(output),
                *mappings,
            ]
        )
        == 0
    )

    expected = {
        "executor": 901,
        "approver": 902,
        "auditor": 0,
        "verifier": 903,
        "decision_consumer": 904,
    }
    assert stat.S_IMODE(output.stat().st_mode) == 0o711
    assert {
        name: stat.S_IMODE((output / name).stat().st_mode) for name in expected
    } == dict.fromkeys(expected, 448)
    assert {
        name: stat.S_IMODE((output / name / "launch-attestation.json").stat().st_mode)
        for name in expected
    } == dict.fromkeys(expected, 256)
    assert directory_owners == [
        (name, expected[name], expected[name]) for name in sorted(expected)
    ]
    assert {
        name: stat.S_IMODE((output / name / "RELEASE").stat().st_mode)
        for name in expected
    } == dict.fromkeys(expected, 256)
    assert sorted(file_owners) == sorted(
        (uid, uid) for uid in expected.values() for _artifact in range(2)
    )


def test_producer_gate_releases_only_exact_signal(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744358517: producer commands wait for authority release.
    import threading

    from benchmarks.codegraph_compare import audit_authority_runner as runner

    gate = tmp_path / "gate"
    os.mkfifo(gate, mode=0o444)
    os.chmod(gate, 0o644)
    received = []
    reader = threading.Thread(target=lambda: received.append(gate.read_bytes()))
    reader.start()
    monkeypatch.setattr(runner, "_run", lambda *_args: b'[{"State":{"Running":true}}]')
    runner._release_producer_gate(gate, "container", __import__("time").monotonic() + 2)
    reader.join(timeout=2)

    assert received == [b"RELEASE\n"]


def test_producer_gate_fails_if_container_exits_before_release(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744358517: exit-before-gate is a terminal authority failure.
    import errno

    from benchmarks.codegraph_compare import audit_authority_runner as runner

    gate = tmp_path / "gate"
    os.mkfifo(gate, mode=0o444)
    monkeypatch.setattr(
        runner.os,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError(errno.ENXIO, "no reader")
        ),
    )
    monkeypatch.setattr(
        runner, "_run", lambda *_args, **_kwargs: b'[{"State":{"Running":false}}]'
    )
    with pytest.raises(ValueError, match="exited before launch gate"):
        runner._release_producer_gate(gate, "container", 10**30)


def test_producer_gate_readiness_timeout_is_terminal(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744358517: a missing gate reader cannot hang the reservation.
    import errno

    from benchmarks.codegraph_compare import audit_authority_runner as runner

    gate = tmp_path / "gate"
    os.mkfifo(gate, mode=0o444)
    monkeypatch.setattr(
        runner.os,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError(errno.ENXIO, "no reader")
        ),
    )
    monkeypatch.setattr(runner, "_run", lambda *_args: b'[{"State":{"Running":true}}]')
    calls = iter((0.0,))
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(calls, 11.0))
    with pytest.raises(TimeoutError, match="gate readiness expired"):
        runner._release_producer_gate(gate, "container", 10**30)


def test_verifier_ledger_consumed_transition_persists_canonical_envelope_atomically(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744400335: a committed CONSUMED fact must recover its envelope.
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes
    from benchmarks.codegraph_compare.verifier_ledger import ChallengeLedger

    monkeypatch.setattr(ChallengeLedger, "_acquire_lease", lambda _self: None)
    ledger = ChallengeLedger(tmp_path / "verifier.sqlite")
    manifest = "a" * 64
    challenge = ledger.begin(manifest)["challenge"]
    ledger.start_verifying(manifest, challenge)
    expected = canonical_json_bytes({"challenge": challenge, "signed": True})

    record, head, stored = ledger.finish_with_envelope(
        manifest, challenge, lambda _record, _head: expected
    )

    assert record["event"] == "CONSUMED"
    assert head == {"counter": record["counter"], "record_hash": record["record_hash"]}
    assert stored == expected
    assert ledger.verdict(manifest, challenge) == expected


def test_service_launch_release_is_blocked_until_private_release_exists(tmp_path: Path):
    # PR #1249 review 3744400323: services start blocked before exact-five attestation.
    import threading
    import time

    from benchmarks.codegraph_compare.service_runtime import wait_for_launch_release

    attestation = tmp_path / "launch-attestation.json"
    release = tmp_path / "RELEASE"
    attestation.write_bytes(b"{}")
    attestation.chmod(0o400)
    observed = []
    waiter = threading.Thread(
        target=lambda: observed.append(
            wait_for_launch_release(attestation, release, timeout_seconds=2)
        )
    )
    waiter.start()
    time.sleep(0.05)
    assert observed == []
    release.write_bytes(b"RELEASE\n")
    release.chmod(0o400)
    waiter.join(timeout=2)
    assert observed == [b"{}"]


def test_stage_copy_file_completes_short_writes(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744482394: staging must retain every byte after a short write.
    from benchmarks.codegraph_compare import stage_inputs

    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.write_bytes(b"trusted-stage-bytes")
    real_write = os.write

    def short_write(descriptor, payload):
        return real_write(descriptor, payload[:3])

    monkeypatch.setattr(stage_inputs.os, "write", short_write)
    stage_inputs.copy_file(source, destination)

    assert destination.read_bytes() == b"trusted-stage-bytes"


def test_stage_copy_file_rejects_zero_progress(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744482394: a zero-byte write cannot stage trusted input.
    from benchmarks.codegraph_compare import stage_inputs

    source = tmp_path / "source"
    source.write_bytes(b"trusted-stage-bytes")
    monkeypatch.setattr(stage_inputs.os, "write", lambda *_args: 0)

    with pytest.raises(OSError, match="staged input write made no progress"):
        stage_inputs.copy_file(source, tmp_path / "destination")


def test_public_config_v6_published_schema_accepts_runtime_config():
    # PR #1249 review 3744482399: trusted is the same closed object on both surfaces.
    from jsonschema import Draft202012Validator

    schema = json.loads(
        Path(
            "benchmarks/codegraph_compare/published_schemas/public-config-v6.schema.json"
        ).read_bytes()
    )
    config = _qualification_v3_public_config()

    assert list(Draft202012Validator(schema).iter_errors(config)) == []


def test_public_config_v6_schema_and_runtime_reject_extra_trusted_field():
    # PR #1249 review 3744482399: neither schema nor parser permits trusted extensions.
    import copy

    from jsonschema import Draft202012Validator

    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes
    from benchmarks.codegraph_compare.verifier import parse_public_config

    schema = json.loads(
        Path(
            "benchmarks/codegraph_compare/published_schemas/public-config-v6.schema.json"
        ).read_bytes()
    )
    config = copy.deepcopy(_qualification_v3_public_config())
    config["trusted"]["untrusted_extension"] = "0" * 64
    diagnostic = copy.deepcopy(config)
    diagnostic.pop("root_signature")

    with pytest.raises(
        ValueError, match="trusted config has unknown or missing fields"
    ):
        parse_public_config(canonical_json_bytes(diagnostic), diagnostic_mode=True)
    assert len(list(Draft202012Validator(schema).iter_errors(config))) == 1


def test_authority_runner_persists_response_before_success(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744482397: SUCCESS never precedes the durable signed response.
    runner = _authority_runner_for_test(tmp_path)
    runner._execute = lambda _contract: {"audit": {}, "artifacts": {}}
    runner._sync_sealed_job = lambda _job_id, _result: None
    job_id = "8" * 64
    events = []
    persist = runner._persist_response
    terminal = runner._terminal_state

    def record_persist(job, response):
        persist(job, response)
        events.append("response-fsync")

    def record_terminal(job, state, payload):
        events.append("success-replace")
        terminal(job, state, payload)

    monkeypatch.setattr(runner, "_persist_response", record_persist)
    monkeypatch.setattr(runner, "_terminal_state", record_terminal)
    reply = {"response": {"job_id": job_id}, "signature": "a" * 128}

    assert runner.run_transaction({"job_id": job_id}, lambda _result: reply) == reply
    assert events == ["response-fsync", "success-replace"]
    assert runner.query_response({"job_id": job_id}) == reply


def test_verifier_request_recovers_only_post_send_truncated_frame(monkeypatch):
    # PR #1249 review 3744482391: clean EOF after CONSUMED queries the exact verdict.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import verifier_service
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    key = Ed25519PrivateKey.from_private_bytes(b"\x55" * 32)
    config = _qualification_v3_public_config()
    digest_manifest = {
        "cells": [
            {
                "contract": {
                    "decision_id": "a" * 64,
                    "decision_contract_sha256": "b" * 64,
                }
            }
        ]
    }
    raw = canonical_json_bytes(digest_manifest)
    digest = hashlib.sha256(raw).hexdigest()
    challenge = "c" * 64
    measurement = config["trusted"]["verifier_runtime"]["measurement"]
    begin_signed = {
        "manifest_sha256": digest,
        "challenge": challenge,
        "ledger_counter": 1,
        "ledger_prev_hash": "0" * 64,
        "issued_at_ns": 7,
        "service_identity": measurement,
    }
    begin = {
        **begin_signed,
        "key_id": config["verifier"]["key_id"],
        "algorithm": "Ed25519",
        "signature": key.sign(
            verifier_service.CHALLENGE_DOMAIN + canonical_json_bytes(begin_signed)
        ).hex(),
    }
    calls = []

    def round_trip(*_args, **_kwargs):
        calls.append("round-trip")
        if len(calls) == 1:
            return begin
        raise verifier_service._PostSendTransportError("frame truncated")

    recovered = {"manifest_sha256": digest, "challenge": challenge}
    monkeypatch.setattr(verifier_service, "_round_trip", round_trip)
    monkeypatch.setattr(
        verifier_service,
        "query_verdict",
        lambda **_kwargs: calls.append("query-verdict") or recovered,
    )
    # Stop after proving selection of the persisted exact identity.
    with pytest.raises(ValueError, match="binding mismatch"):
        verifier_service.request_verdict(
            socket_path=Path("authority.sock"),
            manifest=digest_manifest,
            config=config,
            timeout=10,
        )

    assert calls == ["round-trip", "round-trip", "query-verdict"]


def test_verifier_request_does_not_recover_semantic_value_error(monkeypatch):
    # PR #1249 review 3744482391: semantic rejection is never converted into a query.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import verifier_service
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    key = Ed25519PrivateKey.from_private_bytes(b"\x55" * 32)
    config = _qualification_v3_public_config()
    manifest = {"cells": [{"contract": {}}]}
    digest = hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()
    begin_signed = {
        "manifest_sha256": digest,
        "challenge": "c" * 64,
        "ledger_counter": 1,
        "ledger_prev_hash": "0" * 64,
        "issued_at_ns": 7,
        "service_identity": config["trusted"]["verifier_runtime"]["measurement"],
    }
    begin = {
        **begin_signed,
        "key_id": config["verifier"]["key_id"],
        "algorithm": "Ed25519",
        "signature": key.sign(
            verifier_service.CHALLENGE_DOMAIN + canonical_json_bytes(begin_signed)
        ).hex(),
    }
    replies = iter((begin, ValueError("manifest frame must be a JSON object")))

    def round_trip(*_args, **_kwargs):
        value = next(replies)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(verifier_service, "_round_trip", round_trip)
    monkeypatch.setattr(
        verifier_service,
        "query_verdict",
        lambda **_kwargs: pytest.fail("semantic error queried persisted verdict"),
    )

    with pytest.raises(ValueError, match="manifest frame must be a JSON object"):
        verifier_service.request_verdict(
            socket_path=Path("authority.sock"),
            manifest=manifest,
            config=config,
            timeout=10,
        )


def test_verifier_begin_retries_one_lost_response(monkeypatch):
    # PR #1249 review 3744516421: BEGIN response loss recovers the manifest challenge.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import verifier_service
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    key = Ed25519PrivateKey.from_private_bytes(b"\x55" * 32)
    config = _qualification_v3_public_config()
    manifest = {"cells": [{"contract": {}}]}
    digest = hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()
    signed = {
        "manifest_sha256": digest,
        "challenge": "c" * 64,
        "ledger_counter": 1,
        "ledger_prev_hash": "0" * 64,
        "issued_at_ns": 7,
        "service_identity": config["trusted"]["verifier_runtime"]["measurement"],
    }
    begin = {
        **signed,
        "key_id": config["verifier"]["key_id"],
        "algorithm": "Ed25519",
        "signature": key.sign(
            verifier_service.CHALLENGE_DOMAIN + canonical_json_bytes(signed)
        ).hex(),
    }
    replies = iter(
        (
            verifier_service._PostSendTransportError("response lost"),
            begin,
            ValueError("semantic stop"),
        )
    )
    requests = []

    def round_trip(_path, request, _config, _timeout):
        requests.append(request["operation"])
        value = next(replies)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(verifier_service, "_round_trip", round_trip)

    with pytest.raises(ValueError, match="semantic stop"):
        verifier_service.request_verdict(
            socket_path=Path("verifier.sock"),
            manifest=manifest,
            config=config,
            timeout=10,
        )

    assert requests == ["begin-exact-14", "begin-exact-14", "verify-exact-14"]


def test_verifier_ledger_begin_is_manifest_idempotent(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744516421: a retry returns the already committed challenge.
    from benchmarks.codegraph_compare.verifier_ledger import ChallengeLedger

    monkeypatch.setattr(ChallengeLedger, "_acquire_lease", lambda _self: None)
    ledger = ChallengeLedger(tmp_path / "verifier.sqlite")

    first = ledger.begin("a" * 64)
    second = ledger.begin("a" * 64)

    assert second == first
    assert ledger.head()["counter"] == 1


def test_receipt_client_retries_one_lost_response(monkeypatch):
    # PR #1249 review 3744516423: immutable stateless signing survives response loss.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import receipt_v3_service as service
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    config = _qualification_v3_public_config()
    key = Ed25519PrivateKey.from_private_bytes(b"\x11" * 32)
    response = {
        "job_id": "7" * 64,
        "receipt": {"signed": True},
        "service_identity": config["trusted"]["executor_runtime"]["measurement"],
    }
    reply = {
        "response": response,
        "key_id": config["executor"]["key_id"],
        "algorithm": "Ed25519",
        "signature": key.sign(
            service.SERVICE_RESPONSE_DOMAIN + canonical_json_bytes(response)
        ).hex(),
    }
    frames = iter((ValueError("frame truncated"), reply))
    sockets = []

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 123, config["executor"]["peer_uid"], 123)

        def sendall(self, _payload):
            pass

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    def socket_factory(*_args):
        item = FakeSocket()
        sockets.append(item)
        return item

    def frame(*_args):
        value = next(frames)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(service.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(service.socket, "socket", socket_factory)
    monkeypatch.setattr(service, "_frame", frame)

    receipt = service.request_receipt(
        role="executor",
        socket_path=Path("executor.sock"),
        authority_response={"response": {"job_id": "7" * 64}},
        config=config,
        timeout=10,
    )

    assert receipt == {"signed": True}
    assert len(sockets) == 2


def test_receipt_client_does_not_retry_semantic_rejection(monkeypatch):
    # PR #1249 review 3744516423: service semantic errors remain terminal.
    from benchmarks.codegraph_compare import receipt_v3_service as service

    config = _qualification_v3_public_config()
    sockets = []

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 123, config["executor"]["peer_uid"], 123)

        def sendall(self, _payload):
            pass

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    def socket_factory(*_args):
        sockets.append(FakeSocket())
        return sockets[-1]

    monkeypatch.setattr(service.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(service.socket, "socket", socket_factory)
    monkeypatch.setattr(
        service, "_frame", lambda *_args: {"error": "ValueError", "reason": "bad job"}
    )

    with pytest.raises(ValueError, match="service rejected job: bad job"):
        service.request_receipt(
            role="executor",
            socket_path=Path("executor.sock"),
            authority_response={"response": {"job_id": "7" * 64}},
            config=config,
            timeout=10,
        )

    assert len(sockets) == 1


def test_receipt_client_bounds_response_loss_retry(monkeypatch):
    # PR #1249 review 3744516423: persistent response loss gets only one retry.
    from benchmarks.codegraph_compare import receipt_v3_service as service

    config = _qualification_v3_public_config()
    sockets = []

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 123, config["executor"]["peer_uid"], 123)

        def sendall(self, _payload):
            pass

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    def socket_factory(*_args):
        sockets.append(FakeSocket())
        return sockets[-1]

    monkeypatch.setattr(service.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(service.socket, "socket", socket_factory)
    monkeypatch.setattr(
        service,
        "_frame",
        lambda *_args: (_ for _ in ()).throw(ValueError("frame truncated")),
    )

    with pytest.raises(service._PostSendTransportError):
        service.request_receipt(
            role="executor",
            socket_path=Path("executor.sock"),
            authority_response={"response": {"job_id": "7" * 64}},
            config=config,
            timeout=10,
        )

    assert len(sockets) == 2


def test_receipt_client_retries_connect_failure_with_original_deadline(monkeypatch):
    # PR #1249 review 3744853007: transient pre-send failures get one bounded retry.
    from benchmarks.codegraph_compare import receipt_v3_service as service

    config = _qualification_v3_public_config()
    sockets = []
    observed_timeouts = []
    ticks = iter((100.0, 101.0, 102.0, 103.0, 104.0))

    class FakeSocket:
        def settimeout(self, timeout):
            observed_timeouts.append(timeout)

        def connect(self, _path):
            if len(sockets) == 1:
                raise ConnectionRefusedError("not listening")

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 123, config["executor"]["peer_uid"], 123)

        def sendall(self, _payload):
            pass

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    def socket_factory(*_args):
        sockets.append(FakeSocket())
        return sockets[-1]

    monkeypatch.setattr(service, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    monkeypatch.setattr(service.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(service.socket, "socket", socket_factory)
    monkeypatch.setattr(
        service, "_frame", lambda *_args: {"error": "ValueError", "reason": "bad job"}
    )

    with pytest.raises(ValueError, match="service rejected job: bad job"):
        service.request_receipt(
            role="executor",
            socket_path=Path("executor.sock"),
            authority_response={"response": {"job_id": "7" * 64}},
            config=config,
            timeout=10,
        )

    assert observed_timeouts == [9.0, 7.0]
    assert len(sockets) == 2


def test_receipt_client_retries_ambiguous_send_failure_once(monkeypatch):
    # PR #1249 review 3744853007: stateless signing makes a partial send retry safe.
    from benchmarks.codegraph_compare import receipt_v3_service as service

    config = _qualification_v3_public_config()
    sockets = []

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 123, config["executor"]["peer_uid"], 123)

        def sendall(self, _payload):
            raise BrokenPipeError("partial frame")

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    def socket_factory(*_args):
        sockets.append(FakeSocket())
        return sockets[-1]

    monkeypatch.setattr(service.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(service.socket, "socket", socket_factory)
    with pytest.raises(service._SendTransportError, match="transmission failed"):
        service.request_receipt(
            role="executor",
            socket_path=Path("executor.sock"),
            authority_response={"response": {"job_id": "7" * 64}},
            config=config,
            timeout=10,
        )

    assert len(sockets) == 2


def test_decision_issuer_separates_run_contract_directory(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744516427: operator input contains exactly run contracts.
    from benchmarks.codegraph_compare import decision_contract_issuer as issuer
    from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS

    descriptor = os.open(os.devnull, os.O_RDONLY)
    monkeypatch.setattr(issuer, "secure_key", lambda *_args: (descriptor, b"\x44" * 32))
    monkeypatch.setattr(
        issuer,
        "issue",
        lambda *_args, **_kwargs: (
            {"decision_id": "d" * 64},
            [
                {"cell": {"repo_id": repo, "arm_id": arm}}
                for repo, arm in EXPECTED_CELLS
            ],
        ),
    )
    output = tmp_path / "issued"

    result = issuer.main(
        [
            "--plans-dir",
            str(tmp_path),
            "--private-key",
            str(tmp_path / "unused.key"),
            "--output-dir",
            str(output),
        ]
    )

    assert result == 0
    assert sorted(path.name for path in output.glob("*.json")) == [
        "decision-contract.json"
    ]
    assert len(list((output / "run_contracts").glob("*.json"))) == 14


def test_decision_consumer_rejects_stale_verifier_runtime_identity():
    # PR #1249 review 3744516428: verdict runtime must match root-signed config.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    config = _qualification_v3_public_config()
    contract = {"decision_id": "d" * 64}
    envelope = {
        "manifest_sha256": "a" * 64,
        "decision_id": "d" * 64,
        "decision_contract_sha256": hashlib.sha256(
            consumer.canonical_json_bytes(contract)
        ).hexdigest(),
        "challenge": "b" * 64,
        "ledger_counter": 1,
        "ledger_prev_hash": "0" * 64,
        "issued_at_ns": 1,
        "verdict": {},
        "service_identity": {"stale": True},
        "consumption_record": {},
        "ledger_head": {},
        "key_id": config["verifier"]["key_id"],
        "algorithm": "Ed25519",
        "signature": "0" * 128,
    }

    with pytest.raises(ValueError, match="verifier identity mismatch"):
        consumer.verify_verdict_envelope(envelope, contract, config)


def test_service_launch_schema_matches_process_identity_shape():
    # PR #1249 review 3744516431: published process fields match _proc_identity().
    from jsonschema import Draft202012Validator

    schema = json.loads(
        Path(
            "benchmarks/codegraph_compare/published_schemas/service-launch-v1.schema.json"
        ).read_bytes()
    )
    process = {
        "host_pid": 123,
        "container_pid": 1,
        "starttime": "456",
        "cgroup": "0::/container",
        "executable": "/usr/bin/python3",
        "executable_sha256": "a" * 64,
        "cmdline": ["python", "-m", "service"],
        "namespaces": {
            name: f"{name}:[1]"
            for name in ("mnt", "pid", "net", "user", "uts", "ipc", "cgroup")
        },
        "capabilities": dict.fromkeys(
            ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"),
            "0000000000000000",
        ),
        "no_new_privs": "1",
        "seccomp": "2",
        "seccomp_filters": "1",
    }
    attestation = {
        "container_id": "b" * 64,
        "role": "verifier",
        "image_id": "sha256:" + "c" * 64,
        "cmd": ["python"],
        "entrypoint": None,
        "user": "903",
        "readonly_rootfs": True,
        "mounts": [],
        "network_mode": "none",
        "security_opt": [],
        "process": process,
    }
    envelope = {
        "attestation": attestation,
        "key_id": "auditor",
        "algorithm": "Ed25519",
        "signature": "d" * 128,
    }

    assert list(Draft202012Validator(schema).iter_errors(envelope)) == []


def test_source_archive_ceiling_matches_tarfile_record_algorithm(tmp_path: Path):
    # PR #1249 review 3744561292: the authority ceiling mirrors tarfile exactly.
    import io
    import tarfile

    from benchmarks.codegraph_compare.audit_authority_storage import (
        _source_archive_ceiling,
    )
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    sizes = (1, 513, 8193)
    records = []
    archive_path = tmp_path / "source.tar"
    with tarfile.open(archive_path, "w", format=tarfile.USTAR_FORMAT) as archive:
        for number, size in enumerate(sizes):
            payload = bytes([number + 1]) * size
            name = f"file-{number}"
            info = tarfile.TarInfo(name)
            info.size = size
            archive.addfile(info, io.BytesIO(payload))
            records.append(
                [
                    name,
                    "100644",
                    "a" * 40,
                    size,
                    hashlib.sha256(payload).hexdigest(),
                ]
            )
    inventory = canonical_json_bytes({"eligibility": {"tracked_files": records}})

    assert _source_archive_ceiling(inventory) == archive_path.stat().st_size


def test_aggregate_output_writer_retries_partial_writes(monkeypatch):
    # PR #1249 review 3744561299: a short write cannot truncate aggregate evidence.
    from benchmarks.codegraph_compare import verifier_aggregate

    observed = bytearray()

    def partial(_descriptor, payload):
        count = min(2, len(payload))
        observed.extend(payload[:count])
        return count

    monkeypatch.setattr(verifier_aggregate.os, "write", partial)
    verifier_aggregate._write_all(7, b"abcdef")

    assert bytes(observed) == b"abcdef"


def test_aggregate_output_writer_rejects_zero_progress(monkeypatch):
    # PR #1249 review 3744561299: zero-progress writes fail closed.
    from benchmarks.codegraph_compare import verifier_aggregate

    monkeypatch.setattr(verifier_aggregate.os, "write", lambda *_args: 0)

    with pytest.raises(OSError, match="made no progress"):
        verifier_aggregate._write_all(7, b"x")


def test_authority_mount_plan_rejects_nonexact_oracle_execution_id():
    # PR #1249 review 3744561306: receipt-v3 IDs are fixed before reservation.
    from benchmarks.codegraph_compare.audit_authority_storage import (
        _producer_mount_targets,
    )

    plan = {
        "executions": [
            {
                "id": execution_id,
                "argv": [
                    "/tool/bin",
                    execution_id,
                    "--config",
                    "/config/pinned.json",
                    *(["--source", "/source"] if execution_id == "build" else []),
                ],
            }
            for execution_id in ("delete", "build", "health", "symbol-query", "call")
        ]
    }

    with pytest.raises(ValueError, match="execution IDs are not exact"):
        _producer_mount_targets(plan)


def test_ext4_image_sizing_rejects_large_sparse_output(tmp_path: Path):
    # PR #1249 review 3744561310: sparse logical bytes cannot bypass output ceilings.
    from benchmarks.codegraph_compare.audit_authority_runner import _ext4_image_size

    core = tmp_path / "core"
    core.mkdir()
    (core / "sparse-index").write_bytes(b"")
    os.truncate(core / "sparse-index", 128 * 1024 * 1024)

    with pytest.raises(ValueError, match="authorized output ceiling"):
        _ext4_image_size(core, 64 * 1024 * 1024)


def test_ext4_image_sizing_uses_sealed_core_usage(tmp_path: Path):
    # PR #1249 review 3744561310: small outputs no longer allocate a fixed 1 GiB.
    from benchmarks.codegraph_compare.audit_authority_runner import _ext4_image_size

    core = tmp_path / "core"
    core.mkdir()
    (core / "index").mkdir()
    (core / "index" / "data").write_bytes(b"x")

    assert _ext4_image_size(core, 128 * 1024 * 1024) == 68 * 1024 * 1024


@pytest.mark.parametrize(
    ("statement", "message"),
    (
        ("UPDATE events SET counter=3 WHERE counter=2", "counter discontinuity"),
        (
            "UPDATE events SET prev_hash=printf('%064d',9) WHERE counter=2",
            "previous hash mismatch",
        ),
        (
            "UPDATE events SET record_hash=printf('%064d',8) WHERE counter=2",
            "record hash mismatch",
        ),
        ("UPDATE meta SET head_hash=printf('%064d',7)", "meta head mismatch"),
        ("UPDATE challenges SET state='CONSUMED'", "materialized state mismatch"),
    ),
)
def test_verifier_ledger_startup_rejects_persisted_chain_corruption(
    tmp_path: Path, monkeypatch, statement: str, message: str
):
    # PR #1249 review 3744588266: no lease may extend a corrupted durable chain.
    import sqlite3

    from benchmarks.codegraph_compare.verifier_ledger import ChallengeLedger

    leases = []
    monkeypatch.setattr(
        ChallengeLedger, "_acquire_lease", lambda _self: leases.append("lease")
    )
    path = tmp_path / "verifier.sqlite"
    ledger = ChallengeLedger(path)
    challenge = ledger.begin("a" * 64)["challenge"]
    ledger.start_verifying("a" * 64, challenge)
    db = sqlite3.connect(path)
    try:
        db.execute(statement)
        db.commit()
    finally:
        db.close()
    leases.clear()

    with pytest.raises(ValueError, match=message):
        ChallengeLedger(path)

    assert leases == []


def test_decision_receipt_rejects_stale_configured_service_identity():
    # PR #1249 review 3744588264: a retained key cannot authorize an old runtime.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import decision_consumer_service as consumer
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    config = _qualification_v3_public_config()
    contract = {"decision_id": "d" * 64}
    envelope = {"manifest_sha256": "e" * 64}
    body = {
        "schema_version": 1,
        "decision_id": contract["decision_id"],
        "decision_contract_sha256": hashlib.sha256(
            canonical_json_bytes(contract)
        ).hexdigest(),
        "manifest_sha256": envelope["manifest_sha256"],
        "verdict_status": "SETUP_QUALIFIED",
        "consumed_at_ns": 1,
        "service_identity": {"stale": True},
    }
    reply = {
        "receipt": body,
        "key_id": config["decision_consumer"]["key_id"],
        "algorithm": "Ed25519",
        "signature": Ed25519PrivateKey.from_private_bytes(b"\x66" * 32)
        .sign(consumer.RECEIPT_DOMAIN + canonical_json_bytes(body))
        .hex(),
    }

    with pytest.raises(ValueError, match="not bound"):
        consumer._verify_decision_receipt(reply, contract, envelope, config)


def test_operator_rejects_short_common_lifetime_before_first_cell(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744588269: closed serial budget failure consumes no job.
    from benchmarks.codegraph_compare import qualification_operator as operator
    from benchmarks.codegraph_compare.receipt_v3 import (
        canonical_json_bytes,
        canonical_plan_hash,
    )
    from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS

    now = 1_000_000_000_000
    expiry = now + 7_898 * 1_000_000_000 - 1
    contracts_dir = tmp_path / "contracts"
    staged_root = tmp_path / "staged"
    contracts_dir.mkdir()
    staged_root.mkdir()
    plans = []
    contracts = []
    for ordinal, (repo, arm) in enumerate(EXPECTED_CELLS):
        plan = {
            "cell": {"repo_id": repo, "arm_id": arm, "attempt": 1},
            "wall_timeout_seconds": 10,
            "resource_ceilings": {"io_bytes": 32 * 1024 * 1024},
        }
        plan["plan_hash"] = canonical_plan_hash(plan)
        plans.append(plan)
        job_id = f"{ordinal + 1:064x}"
        contract = {
            "job_id": job_id,
            "cell": plan["cell"],
            "nonce": "a" * 64,
            "decision_id": "b" * 64,
            "expires_at_ns": expiry,
        }
        contracts.append(contract)
        job = staged_root / job_id
        job.mkdir()
        (job / "plan.json").write_bytes(canonical_json_bytes(plan))
        (job / "inventory.json").write_bytes(canonical_json_bytes({"repo_id": repo}))
    decision = {
        "decision_id": "b" * 64,
        "expires_at_ns": expiry,
        "plan_set_hash": "c" * 64,
        "cells": [
            {
                "repo_id": repo,
                "arm_id": arm,
                "plan_sha256": canonical_plan_hash(plan),
            }
            for (repo, arm), plan in zip(EXPECTED_CELLS, plans, strict=True)
        ],
    }
    decision_path = tmp_path / "decision.json"
    decision_path.write_bytes(canonical_json_bytes(decision))
    digest = hashlib.sha256(canonical_json_bytes(decision)).hexdigest()
    for ordinal, contract in enumerate(contracts):
        contract["decision_contract_sha256"] = digest
        (contracts_dir / f"{ordinal}.json").write_bytes(canonical_json_bytes(contract))
    config_path = tmp_path / "public.json"
    config_path.write_bytes(b"{}")
    monkeypatch.setattr(
        operator,
        "parse_public_config",
        lambda _raw: {
            "auditor": {"peer_uid": 0},
            "trusted": {
                "plan_set_hash": "c" * 64,
                "inventory_sha256": {
                    repo: hashlib.sha256(
                        canonical_json_bytes({"repo_id": repo})
                    ).hexdigest()
                    for repo, _arm in EXPECTED_CELLS
                },
                "verifier_runtime": {"measurement": {}},
            },
        },
    )
    monkeypatch.setattr(operator, "verify_decision_contract", lambda value: value)
    monkeypatch.setattr(operator, "verify_configured_plan_set", lambda *_args: None)
    monkeypatch.setattr(operator, "validate_producer_plan", lambda value: value)
    monkeypatch.setattr(operator, "validate_receipt_inventory", lambda value: value)
    monkeypatch.setattr(
        operator, "verify_contract", lambda request: request["contract"]
    )
    monkeypatch.setattr(operator.time, "time_ns", lambda: now)
    callbacks = []
    monkeypatch.setattr(operator, "run_cell", lambda *_args: callbacks.append("cell"))
    args = SimpleNamespace(
        public_config=str(config_path),
        contracts_dir=str(contracts_dir),
        decision_contract=str(decision_path),
        staged_root=str(staged_root),
        authority_socket=str(tmp_path / "authority.sock"),
    )

    with pytest.raises(TimeoutError, match="closed serial budget"):
        operator._run_impl(args)

    assert callbacks == []


def test_decision_ledger_startup_rejects_corrupt_persisted_receipt(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744588266: decision SQLite is validated before listening.
    import sqlite3

    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    parent = tmp_path / "decision-ledger"
    parent.mkdir(mode=0o700)
    real_stat = consumer.os.stat

    def service_stat(path, *args, **kwargs):
        metadata = real_stat(path, *args, **kwargs)
        if Path(path) == parent:
            return SimpleNamespace(st_uid=904, st_mode=stat.S_IFDIR | 0o700)
        return metadata

    monkeypatch.setattr(consumer.os, "stat", service_stat)
    monkeypatch.setattr(consumer.os, "access", lambda *_args: True)
    path = parent / "decisions.sqlite"
    consumer.DecisionLedger(path, _qualification_v3_public_config())
    db = sqlite3.connect(path)
    try:
        db.execute(
            "INSERT INTO consumed VALUES(?,?,?,?,?)",
            ("a" * 64, "b" * 64, "c" * 64, 1, b"{}\n"),
        )
        db.commit()
    finally:
        db.close()

    with pytest.raises(ValueError, match="receipt is not canonical"):
        consumer.DecisionLedger(path, _qualification_v3_public_config())


def test_ext4_layout_reserves_exact_sealed_core_inodes(tmp_path: Path):
    # PR #1249 review 3744627741: byte sizing alone under-provisioned small-file inodes.
    from benchmarks.codegraph_compare.audit_authority_runner import _ext4_layout

    core = tmp_path / "core"
    core.mkdir()
    (core / "index").mkdir()
    (core / "one").write_bytes(b"")
    (core / "index" / "two").write_bytes(b"")

    assert _ext4_layout(core, 128 * 1024 * 1024) == (
        68 * 1024 * 1024,
        6,
        16 * 1024,
    )


def test_ext4_layout_rejects_core_above_entry_bound(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744627741: inode counting work has an authority-owned bound.
    from benchmarks.codegraph_compare import audit_authority_runner as authority

    core = tmp_path / "core"
    core.mkdir()
    (core / "one").write_bytes(b"")
    (core / "two").write_bytes(b"")
    monkeypatch.setattr(authority, "_MAX_SEALED_CORE_ENTRIES", 2)

    with pytest.raises(ValueError, match="entry count exceeds authority maximum"):
        authority._ext4_layout(core, 128 * 1024 * 1024)


def test_debugfs_timeout_scales_with_payload_and_contract_expiry(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744627743: extraction cannot inherit the fixed 120s default.
    from benchmarks.codegraph_compare import audit_authority_runner as authority

    observed = []
    monkeypatch.setattr(authority.time, "time_ns", lambda: 1_000_000_000)
    monkeypatch.setattr(authority, "_hash_tree", lambda _path: "same")
    monkeypatch.setattr(
        authority,
        "_run",
        lambda *args, timeout: observed.append((args, timeout)) or b"",
    )

    authority._assert_ext4_payload(
        tmp_path / "data.img",
        tmp_path / "core",
        payload_bytes=64 * 1024 * 1024,
        contract_expires_at_ns=33_000_000_000,
    )

    command, timeout = observed[0]
    assert command[:2] == ("debugfs", "-R")
    assert command[2].startswith("rdump / ")
    assert command[3] == str(tmp_path / "data.img")
    assert timeout == 32.0


def test_authority_preflight_rejects_ambiguous_mount_without_state(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744627747: plan mount errors must precede reservation.
    from benchmarks.codegraph_compare import audit_authority_runner as authority
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    job = tmp_path / "job"
    job.mkdir()
    plan = {
        "resource_ceilings": {"io_bytes": 1024},
        "executions": [
            {
                "id": execution_id,
                "argv": [
                    "/tool/bin",
                    execution_id,
                    "--config",
                    "/config.json",
                    *(
                        ["--source", "/source", "--source", "/source"]
                        if execution_id == "build"
                        else []
                    ),
                ],
            }
            for execution_id in ("delete", "build", "health", "symbol", "call")
        ],
    }
    (job / "plan.json").write_bytes(canonical_json_bytes(plan))
    runner = object.__new__(authority.AuthorityRunner)
    runner._artifacts = tmp_path
    runner._inputs = lambda _contract: (job, {}, {})
    runner._verify_staged = lambda *_args: 1
    monkeypatch.setattr(authority, "validate_producer_plan", lambda value: value)

    with pytest.raises(ValueError, match="source target is not exact"):
        runner.preflight({"job_id": "a" * 64})

    assert list(tmp_path.glob("*.state")) == []


def test_authority_cgroup_host_failure_precedes_running_reservation(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744853003: deterministic host failures cannot consume a job.
    from benchmarks.codegraph_compare import audit_authority_runner as authority

    job = tmp_path / "job"
    artifacts = tmp_path / "artifacts"
    job.mkdir()
    artifacts.mkdir()
    (job / "plan.json").write_text("{}")
    runner = object.__new__(authority.AuthorityRunner)
    runner._artifacts = artifacts
    runner._inputs = lambda _contract: (job, {}, {})
    runner._verify_staged = lambda *_args: 1
    monkeypatch.setattr(authority, "validate_producer_plan", lambda value: value)
    monkeypatch.setattr(authority, "_authorized_output_ceiling", lambda _plan: 1)
    monkeypatch.setattr(
        authority,
        "_producer_mount_targets",
        lambda _plan: ("/source", "/tool", "/config"),
    )
    monkeypatch.setattr(
        authority,
        "_run",
        lambda *_args: b'{"CgroupVersion":"2","CgroupDriver":"systemd"}',
    )

    with pytest.raises(ValueError, match="only cgroup-v2 cgroupfs Docker"):
        runner.preflight({"job_id": "a" * 64})

    assert list(artifacts.glob("*.state")) == []


def _mock_authority_cgroup_host(tmp_path: Path, monkeypatch):
    from benchmarks.codegraph_compare import audit_authority_runner as authority

    cgroup = tmp_path / "cgroup"
    cgroup.mkdir()
    (cgroup / "cgroup.controllers").write_text("cpu memory io pids")
    (cgroup / "cgroup.subtree_control").write_text("cpu memory io pids")
    monkeypatch.setattr(authority, "_CGROUP_ROOT", cgroup)
    monkeypatch.setattr(
        authority,
        "_run",
        lambda *_args: b'{"CgroupVersion":"2","CgroupDriver":"cgroupfs"}',
    )
    monkeypatch.setattr(authority.os, "access", lambda *_args: True)
    return authority, cgroup


def test_authority_requires_all_available_cgroup_controllers(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744853003: every producer controller must be available.
    authority, cgroup = _mock_authority_cgroup_host(tmp_path, monkeypatch)
    (cgroup / "cgroup.controllers").write_text("cpu memory pids")

    with pytest.raises(ValueError, match="controllers are unavailable"):
        authority._preflight_cgroup_host()


def test_authority_requires_all_delegated_cgroup_controllers(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744853003: every producer controller must be delegated.
    authority, cgroup = _mock_authority_cgroup_host(tmp_path, monkeypatch)
    (cgroup / "cgroup.subtree_control").write_text("cpu memory pids")

    with pytest.raises(ValueError, match="controllers are not delegated"):
        authority._preflight_cgroup_host()


def test_authority_requires_writable_cgroup_delegation(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744853003: the delegated hierarchy must accept a child.
    authority, _cgroup = _mock_authority_cgroup_host(tmp_path, monkeypatch)
    monkeypatch.setattr(authority.os, "access", lambda *_args: False)

    with pytest.raises(ValueError, match="delegation is not writable"):
        authority._preflight_cgroup_host()


def test_authority_response_recovery_uses_original_absolute_deadline(monkeypatch):
    # PR #1249 review 3744677879: recovery cannot renew a consumed request budget.
    from benchmarks.codegraph_compare import audit_authority_client as client

    observed = []
    ticks = iter((100.0, 101.0, 105.0))
    monkeypatch.setattr(client, "time", SimpleNamespace(monotonic=lambda: next(ticks)))

    def request(_request, _socket, _authority, timeout):
        observed.append(timeout)
        if len(observed) == 1:
            raise client._PostSendTransportError("lost")
        raise RuntimeError("recovery observed")

    monkeypatch.setattr(client, "_request_response", request)

    with pytest.raises(RuntimeError, match="recovery observed"):
        client.run_cell(
            {"job_id": "a" * 64},
            Path("/authority.sock"),
            {"wall_timeout_seconds": 10},
        )

    assert observed == [9.0, 5.0]


def test_authority_budget_includes_all_bounded_post_processing():
    # PR #1249 review 3744677882: preflight covers work after producer exit.
    from benchmarks.codegraph_compare.execution_budget import (
        authority_cell_budget_seconds,
    )

    assert (
        authority_cell_budget_seconds(
            {
                "wall_timeout_seconds": 10,
                "resource_ceilings": {"io_bytes": 32 * 1024 * 1024},
            }
        )
        == 1932
    )


def test_verifier_envelope_build_failure_durably_terminalizes_verifying(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744677886: an envelope persistence failure cannot strand VERIFYING.
    import sqlite3

    from benchmarks.codegraph_compare.verifier_ledger import ChallengeLedger

    monkeypatch.setattr(ChallengeLedger, "_acquire_lease", lambda _self: None)
    ledger = ChallengeLedger(tmp_path / "verifier.sqlite")
    manifest = "a" * 64
    challenge = ledger.begin(manifest)["challenge"]
    ledger.start_verifying(manifest, challenge)

    with pytest.raises(OSError, match="signing failed"):
        ledger.finish_with_envelope(
            manifest,
            challenge,
            lambda _record, _head: (_ for _ in ()).throw(OSError("signing failed")),
        )
    assert ledger.recover_envelope_or_fail(manifest, challenge) is None
    database = sqlite3.connect(ledger.path)
    try:
        state = database.execute(
            "SELECT state FROM challenges WHERE challenge=?", (challenge,)
        ).fetchone()[0]
    finally:
        database.close()

    assert state == "FAILED"


def test_streamed_blob_descriptor_does_not_use_read_bytes(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744677888: producer evidence descriptors are streamed from disk.
    from benchmarks.codegraph_compare.setup_qualification_executor import (
        _describe_blob,
    )

    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "stdout").write_bytes(b"abc" * 1024)
    monkeypatch.setattr(Path, "read_bytes", lambda _self: pytest.fail("buffered read"))

    assert _describe_blob(raw, "stdout") == {
        "path": "raw/stdout",
        "size_bytes": 3072,
        "sha256": hashlib.sha256(b"abc" * 1024).hexdigest(),
    }


def test_core_blob_bound_uses_signed_output_ceiling_not_legacy_512mib():
    # PR #1249 review 3744728241: valid large descriptors use the signed ceiling.
    from benchmarks.codegraph_compare.verifier_recompute import _core_blob_size

    size = 513 * 1024 * 1024
    plan = {"resource_ceilings": {"io_bytes": size}}

    assert _core_blob_size(plan, size) == 537_919_488
    with pytest.raises(ValueError, match="signed output ceiling"):
        _core_blob_size(plan, size + 1)


def test_shared_verifier_debugfs_timeout_uses_image_size_and_absolute_deadline(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744728245: all receipt/verifier extraction shares this path.
    from benchmarks.codegraph_compare import execution_budget, verifier

    image = tmp_path / "data.img"
    image.write_bytes(b"")
    os.truncate(image, 16 * 1024 * 1024 * 1024)
    observed = []
    monkeypatch.setattr(execution_budget.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(
        verifier.subprocess,
        "run",
        lambda *args, **kwargs: (
            observed.append(kwargs["timeout"]) or SimpleNamespace(returncode=0)
        ),
    )

    verifier._extract_ext4(image, tmp_path / "out", deadline_monotonic=200.0)

    assert observed == [100.0]


def test_exact14_manifest_preflight_counts_outer_json_escaping_and_rejects_ceiling(
    monkeypatch,
):
    # PR #1249 review 3744728248: frame failure must precede the first cell.
    from benchmarks.codegraph_compare import verifier_service

    cells = [({"p": '"'}, {"i": "\\"}, {"c": 1}) for _ in range(14)]

    assert verifier_service.exact14_manifest_preflight_bound(cells) == 29_364_798
    monkeypatch.setattr(verifier_service, "MAX_FRAME", 29_364_797)
    with pytest.raises(ValueError, match="protocol ceiling"):
        verifier_service.preflight_exact14_manifest(cells)


def test_decision_ledger_startup_verifies_persisted_receipt_signature(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744728250: logical receipt corruption fails before listen.
    import sqlite3

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import decision_consumer_service as consumer
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    parent = tmp_path / "signed-decision-ledger"
    parent.mkdir(mode=0o700)
    real_stat = consumer.os.stat

    def service_stat(path, *args, **kwargs):
        metadata = real_stat(path, *args, **kwargs)
        if Path(path) == parent:
            return SimpleNamespace(
                st_uid=904, st_mode=__import__("stat").S_IFDIR | 0o700
            )
        return metadata

    monkeypatch.setattr(consumer.os, "stat", service_stat)
    monkeypatch.setattr(consumer.os, "access", lambda *_args: True)
    config = _qualification_v3_public_config()
    path = parent / "decisions.sqlite"
    consumer.DecisionLedger(path, config)
    body = {
        "schema_version": 1,
        "decision_id": "a" * 64,
        "decision_contract_sha256": "d" * 64,
        "manifest_sha256": "c" * 64,
        "verdict_status": "SETUP_QUALIFIED",
        "consumed_at_ns": 1,
        "service_identity": config["trusted"]["decision_consumer_runtime"][
            "measurement"
        ],
    }
    signature = (
        Ed25519PrivateKey.from_private_bytes(b"\x66" * 32)
        .sign(consumer.RECEIPT_DOMAIN + canonical_json_bytes(body))
        .hex()
    )
    receipt = {
        "receipt": body,
        "key_id": config["decision_consumer"]["key_id"],
        "algorithm": "Ed25519",
        "signature": ("0" if signature[0] != "0" else "1") + signature[1:],
    }
    db = sqlite3.connect(path)
    try:
        db.execute(
            "INSERT INTO consumed VALUES(?,?,?,?,?)",
            ("a" * 64, "b" * 64, "c" * 64, 1, canonical_json_bytes(receipt)),
        )
        db.commit()
    finally:
        db.close()

    with pytest.raises(ValueError, match="signature invalid"):
        consumer.DecisionLedger(path, config)


def test_exact14_budget_uses_sealed_image_extractions_not_producer_wall():
    # PR #1249 review 3744776113: post-authority service work uses image bounds.
    from benchmarks.codegraph_compare.execution_budget import (
        exact14_execution_budget_seconds,
    )

    plans = {
        ("repo", "arm"): {
            "wall_timeout_seconds": 1,
            "resource_ceilings": {"io_bytes": 16 * 1024 * 1024},
        }
    }

    assert exact14_execution_budget_seconds(plans) == 3120


def test_live_output_size_ignores_disappearing_entry(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744776119: mutable producer trees race live accounting.
    from benchmarks.codegraph_compare import setup_qualification_executor as executor

    output = tmp_path / "output"
    output.mkdir()
    (output / "index.db").write_bytes(b"abc")
    real_lstat = executor.os.lstat

    def vanished(path):
        if Path(path).name == "index.db":
            raise FileNotFoundError(path)
        return real_lstat(path)

    monkeypatch.setattr(executor.os, "lstat", vanished)

    assert executor._output_size(output, strict=False) == 0


def test_live_output_size_charges_allocated_blocks_and_shared_metadata(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3745125491: empty and sparse output consumes live budget.
    from benchmarks.codegraph_compare import setup_qualification_executor as executor
    from benchmarks.codegraph_compare.execution_budget import (
        OUTPUT_ENTRY_METADATA_CHARGE_BYTES,
    )

    output = tmp_path / "output"
    output.mkdir()
    item = output / "item"
    item.touch()
    real_lstat = executor.os.lstat

    def allocated(path):
        metadata = real_lstat(path)
        if Path(path) == item:
            return SimpleNamespace(st_mode=metadata.st_mode, st_blocks=2)
        return metadata

    monkeypatch.setattr(executor.os, "lstat", allocated)

    assert executor._output_size(output) == 1024 + OUTPUT_ENTRY_METADATA_CHARGE_BYTES


def test_live_output_size_rejects_entry_count_above_shared_bound(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3745125491: every mutable-tree scan has bounded work.
    from benchmarks.codegraph_compare import setup_qualification_executor as executor

    output = tmp_path / "output"
    output.mkdir()
    (output / "one").touch()
    (output / "two").touch()
    monkeypatch.setattr(executor, "_MAX_OUTPUT_ENTRIES", 1)

    with pytest.raises(ValueError, match="entry count exceeds authority maximum"):
        executor._output_size(output, ceiling=1024 * 1024)


def test_live_output_size_enforces_signed_ceiling_during_scan(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3745125491: allocated output cannot grow past signed bytes.
    from benchmarks.codegraph_compare import setup_qualification_executor as executor

    output = tmp_path / "output"
    output.mkdir()
    item = output / "item"
    item.touch()
    real_lstat = executor.os.lstat

    def allocated(path):
        metadata = real_lstat(path)
        if Path(path) == item:
            return SimpleNamespace(st_mode=metadata.st_mode, st_blocks=2)
        return metadata

    monkeypatch.setattr(executor.os, "lstat", allocated)

    with pytest.raises(ValueError, match="exceeds signed I/O ceiling"):
        executor._output_size(output, ceiling=5119)


def test_terminal_output_size_rejects_disappearing_entry(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744776119: only the stable terminal snapshot is strict.
    from benchmarks.codegraph_compare import setup_qualification_executor as executor

    output = tmp_path / "output"
    output.mkdir()
    (output / "index.db").write_bytes(b"abc")
    real_lstat = executor.os.lstat

    def vanished(path):
        if Path(path).name == "index.db":
            raise FileNotFoundError(path)
        return real_lstat(path)

    monkeypatch.setattr(executor.os, "lstat", vanished)

    with pytest.raises(FileNotFoundError):
        executor._output_size(output)


def test_decision_ledger_rechecks_expiry_inside_transaction(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744776126: lock wait cannot permit post-expiry consumption.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    ledger = object.__new__(consumer.DecisionLedger)
    ledger.path = tmp_path / "decision.sqlite"
    captured = []
    monkeypatch.setattr(consumer.time, "time_ns", lambda: 100)

    with pytest.raises(TimeoutError, match="expired before consumption"):
        ledger.consume(
            {"decision_id": "a" * 64, "decision_nonce": "b" * 64, "expires_at_ns": 100},
            "c" * 64,
            lambda consumed_at: captured.append(consumed_at) or {},
        )

    assert captured == []


def test_decision_ledger_binds_receipt_and_row_to_transaction_timestamp(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744776126: one in-transaction timestamp binds durable facts.
    import sqlite3

    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    ledger = object.__new__(consumer.DecisionLedger)
    ledger.path = tmp_path / "decision.sqlite"
    database = sqlite3.connect(ledger.path)
    database.execute(
        "CREATE TABLE consumed(decision_id TEXT PRIMARY KEY,decision_nonce TEXT UNIQUE NOT NULL,manifest_sha256 TEXT NOT NULL,consumed_at_ns INTEGER NOT NULL,receipt_json BLOB NOT NULL)"
    )
    database.close()
    monkeypatch.setattr(consumer.time, "time_ns", lambda: 101)

    receipt = ledger.consume(
        {"decision_id": "a" * 64, "decision_nonce": "b" * 64, "expires_at_ns": 102},
        "c" * 64,
        lambda consumed_at: {"consumed_at_ns": consumed_at},
    )
    database = sqlite3.connect(ledger.path)
    try:
        row_time = database.execute(
            "SELECT consumed_at_ns FROM consumed WHERE decision_id=?", ("a" * 64,)
        ).fetchone()[0]
    finally:
        database.close()

    assert receipt["consumed_at_ns"] == 101
    assert row_time == 101


def test_decision_client_retries_one_presend_failure(monkeypatch):
    # PR #1249 review 3744776122: a zero-byte failure cannot imply consumption.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    config = _qualification_v3_public_config()
    attempts = []
    reply = {"durable": True}

    class FakeSocket:
        def __init__(self):
            self.number = len(attempts)
            attempts.append(self.number)

        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            if self.number == 0:
                raise ConnectionRefusedError("not listening")

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 1, config["decision_consumer"]["peer_uid"], 1)

        def send(self, payload):
            return len(payload)

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    monkeypatch.setattr(consumer.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(consumer.socket, "socket", lambda *_args: FakeSocket())
    monkeypatch.setattr(consumer, "read_frame", lambda *_args: reply)
    monkeypatch.setattr(
        consumer, "_verify_decision_receipt", lambda value, *_args: value
    )

    result = consumer.request_decision(
        socket_path=Path("/unused"),
        contract={"decision_id": "a" * 64},
        envelope={},
        config=config,
        timeout=1,
    )

    assert result == reply
    assert attempts == [0, 1]


def test_decision_client_queries_ambiguous_send_before_retrying_consume(monkeypatch):
    # PR #1249 review 3744776122: not-found recovery permits one bounded retry.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    config = _qualification_v3_public_config()
    operations = []
    replies = iter(
        (
            EOFError("lost consume response"),
            {"status": "not-found"},
            {"durable": True},
        )
    )

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 1, config["decision_consumer"]["peer_uid"], 1)

        def send(self, framed):
            operations.append(json.loads(framed[4:])["operation"])
            return len(framed)

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    def read_reply(*_args):
        value = next(replies)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(consumer.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(consumer.socket, "socket", lambda *_args: FakeSocket())
    monkeypatch.setattr(consumer, "read_frame", read_reply)
    monkeypatch.setattr(
        consumer, "_verify_decision_receipt", lambda value, *_args: value
    )

    result = consumer.request_decision(
        socket_path=Path("/unused"),
        contract={"decision_id": "a" * 64},
        envelope={},
        config=config,
        timeout=1,
    )

    assert result == {"durable": True}
    assert operations == ["consume-decision", "query-decision", "consume-decision"]


def test_decision_client_polls_in_progress_ambiguous_consume(monkeypatch):
    # PR #1249 review 3745125493: a delivered consume may still be verifying.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    config = _qualification_v3_public_config()
    operations = []
    replies = iter(
        (
            EOFError("lost consume response"),
            {"status": "in-progress"},
            {"status": "consumed", "receipt": {"durable": True}},
        )
    )

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 1, config["decision_consumer"]["peer_uid"], 1)

        def send(self, framed):
            operations.append(json.loads(framed[4:])["operation"])
            return len(framed)

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    def read_reply(*_args):
        value = next(replies)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(consumer.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(consumer.socket, "socket", lambda *_args: FakeSocket())
    monkeypatch.setattr(consumer, "read_frame", read_reply)
    monkeypatch.setattr(consumer.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        consumer, "_verify_decision_receipt", lambda value, *_args: value
    )

    result = consumer.request_decision(
        socket_path=Path("/unused"),
        contract={"decision_id": "a" * 64},
        envelope={},
        config=config,
        timeout=1,
    )

    assert result == {"durable": True}
    assert operations == ["consume-decision", "query-decision", "query-decision"]


def test_decision_client_recovers_receipt_after_retry_reports_consumed(monkeypatch):
    # PR #1249 review 3745125493: replay races must never lose a durable receipt.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    config = _qualification_v3_public_config()
    operations = []
    replies = iter(
        (
            EOFError("lost consume response"),
            {"status": "not-found"},
            {"error": "ValueError", "reason": "decision already consumed"},
            {"status": "in-progress"},
            {"status": "consumed", "receipt": {"durable": True}},
        )
    )

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 1, config["decision_consumer"]["peer_uid"], 1)

        def send(self, framed):
            operations.append(json.loads(framed[4:])["operation"])
            return len(framed)

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    def read_reply(*_args):
        value = next(replies)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(consumer.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(consumer.socket, "socket", lambda *_args: FakeSocket())
    monkeypatch.setattr(consumer, "read_frame", read_reply)
    monkeypatch.setattr(consumer.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        consumer, "_verify_decision_receipt", lambda value, *_args: value
    )

    result = consumer.request_decision(
        socket_path=Path("/unused"),
        contract={"decision_id": "a" * 64},
        envelope={},
        config=config,
        timeout=1,
    )

    assert result == {"durable": True}
    assert operations == [
        "consume-decision",
        "query-decision",
        "consume-decision",
        "query-decision",
        "query-decision",
    ]


def test_producer_plan_rejects_noncanonical_environment_digest_before_execution():
    # PR #1249 review 3744776130: stale execution digests fail producer preflight.
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes
    from benchmarks.codegraph_compare.setup_qualification_executor import (
        validate_producer_plan,
    )

    environment = {
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin",
    }
    ceilings = {
        "wall_ns": 1,
        "cpu_usec": 1,
        "io_bytes": 1,
        "memory_peak_bytes": 1,
        "pids_peak": 1,
    }
    resource_digest = hashlib.sha256(
        canonical_json_bytes({"wall_timeout_seconds": 1, "resource_ceilings": ceilings})
    ).hexdigest()
    plan = {
        "schema_version": 1,
        "cell": {"repo_id": "repo", "arm_id": "arm", "attempt": 1},
        "executions": [
            {
                "id": execution_id,
                "argv": ["/bin/tool"],
                "cwd": "/source",
                "environment_digest": "0" * 64,
                "query": {},
                "expected_result": {},
            }
            for execution_id in ("delete", "build", "health", "symbol", "call")
        ],
        "wall_timeout_seconds": 1,
        "environment": environment,
        "artifact_path": "artifact",
        "plan_hash": "a" * 64,
        "plan_set_hash": "b" * 64,
        "tool_sha256": "c" * 64,
        "config_sha256": "d" * 64,
        "image_digest": "sha256:" + "e" * 64,
        "seccomp_sha256": "f" * 64,
        "resource_plan_digest": resource_digest,
        "resource_ceilings": ceilings,
        "index_partition": {
            "indexed_paths": [],
            "excluded_paths": [],
            "parse_error_paths": [],
        },
        "oracle_statement": "exact",
    }

    with pytest.raises(ValueError, match="environment digest is not canonical"):
        validate_producer_plan(plan)


def test_exact14_manifest_preflight_rejects_node_budget_before_wire(monkeypatch):
    # PR #1249 review 3744822109: byte-fit manifests still need exact node accounting.
    from benchmarks.codegraph_compare import verifier_service

    cells = [({"p": 1}, {"i": 1}, {"c": 1}) for _ in range(14)]
    monkeypatch.setattr(verifier_service, "MANIFEST_MAX_NODES", 1_400_101)

    with pytest.raises(ValueError, match="complexity exceeds protocol ceiling"):
        verifier_service.preflight_exact14_manifest(cells)


def test_verifier_server_frame_deadline_scales_to_maximum_payload(monkeypatch):
    # PR #1249 review 3744822112: 512 MiB reads must not retain a fixed 10s budget.
    import struct

    from benchmarks.codegraph_compare import verifier_service

    deadlines = []

    def receive(_connection, size, deadline):
        deadlines.append(deadline)
        return struct.pack("!I", verifier_service.MAX_FRAME) if size == 4 else b"{}"

    monkeypatch.setattr(verifier_service, "recv_exact", receive)
    monkeypatch.setattr(verifier_service.time, "monotonic", lambda: 100.0)

    assert verifier_service._frame(object()) == {}
    assert deadlines == [110.0, 164.0]


def test_receipt_frame_preflight_rejects_approver_draft_ceiling(monkeypatch):
    # PR #1249 review 3744822118: all receipt frames must fit before authority use.
    from benchmarks.codegraph_compare import qualification_operator as operator

    plan = {"plan": "x"}
    inventory = {"eligibility": {"paths": ["a"]}}
    bounds = operator.preflight_receipt_service_frames(plan, inventory)
    monkeypatch.setattr(operator, "RECEIPT_MAX_MESSAGE", bounds["approver_request"] - 1)

    with pytest.raises(ValueError, match="receipt frame upper bound"):
        operator.preflight_receipt_service_frames(plan, inventory)


def test_receipt_inventory_rejects_missing_commit_before_signing():
    # PR #1249 review 3744887352: all inventories share the receipt validator.
    from benchmarks.codegraph_compare.receipt_inventory import (
        validate_receipt_inventory,
    )

    eligibility = dict(_qualification_v3_body()["source"]["eligibility"])
    del eligibility["commit"]

    with pytest.raises(ValueError, match="unknown or missing fields"):
        validate_receipt_inventory({"eligibility": eligibility})


def test_receipt_server_frame_deadline_scales_to_maximum_payload(monkeypatch):
    # PR #1249 review 3744887360: 16 MiB reads use the declared frame size.
    import struct

    from benchmarks.codegraph_compare import receipt_v3_service

    deadlines = []

    def receive(_connection, size, deadline):
        deadlines.append(deadline)
        return struct.pack("!I", receipt_v3_service.MAX_MESSAGE) if size == 4 else b"{}"

    monkeypatch.setattr(receipt_v3_service, "recv_exact", receive)
    monkeypatch.setattr(receipt_v3_service.time, "monotonic", lambda: 100.0)

    assert receipt_v3_service._frame(object()) == {}
    assert deadlines == [110.0, 116.0]


@pytest.mark.parametrize("failure", ["connect", "send"])
def test_authority_retries_transport_failure_under_original_deadline(
    monkeypatch, failure: str
):
    # PR #1249 reviews 3744915224: no authority retry may renew the cell budget.
    from benchmarks.codegraph_compare import audit_authority_client as client

    observed: list[tuple[str, float]] = []
    ticks = iter((100.0, 101.0, 105.0))
    monkeypatch.setattr(client, "time", SimpleNamespace(monotonic=lambda: next(ticks)))

    def request(payload, _socket, _authority, timeout):
        observed.append((payload["operation"], timeout))
        if len(observed) == 1:
            error = (
                client._PreSendTransportError("not connected")
                if failure == "connect"
                else client._SendTransportError("ambiguous send")
            )
            raise error
        raise RuntimeError("bounded retry observed")

    monkeypatch.setattr(client, "_request_response", request)

    with pytest.raises(RuntimeError, match="bounded retry observed"):
        client.run_cell(
            {"job_id": "a" * 64},
            Path("/authority.sock"),
            {"wall_timeout_seconds": 10},
        )

    expected_operation = "run-cell" if failure == "connect" else "query-job-response"
    assert observed == [("run-cell", 9.0), (expected_operation, 5.0)]


def test_verifier_begin_retries_pre_send_failure_under_original_deadline(monkeypatch):
    # PR #1249 review 3744915230: BEGIN connect failure is safe to retry once.
    from benchmarks.codegraph_compare import verifier_service

    requests: list[tuple[str, float]] = []
    ticks = iter((100.0, 101.0, 105.0))
    monkeypatch.setattr(
        verifier_service, "time", SimpleNamespace(monotonic=lambda: next(ticks))
    )

    def round_trip(_path, request, _config, timeout):
        requests.append((request["operation"], timeout))
        if len(requests) == 1:
            raise verifier_service._PreSendTransportError("not connected")
        raise RuntimeError("bounded retry observed")

    monkeypatch.setattr(verifier_service, "_round_trip", round_trip)

    with pytest.raises(RuntimeError, match="bounded retry observed"):
        verifier_service.request_verdict(
            socket_path=Path("/verifier.sock"),
            manifest={"cells": []},
            config={},
            timeout=10,
        )

    assert requests == [("begin-exact-14", 9.0), ("begin-exact-14", 5.0)]


@pytest.mark.parametrize("role", ["executor", "approver"])
def test_receipt_signer_rechecks_expired_deadline_before_signature(monkeypatch, role):
    # PR #1249 review 3744915233: completed semantic work cannot sign after expiry.
    from benchmarks.codegraph_compare import receipt_v3_signer as signer

    body = {"sealed": True}
    monkeypatch.setattr(signer, "_safe_path", lambda _path: Path("/sealed.img"))
    monkeypatch.setattr(signer, "_extract_ext4", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(signer, "_build_body", lambda *_args, **_kwargs: body)
    monkeypatch.setattr(signer, "_full_semantic_verify", lambda *_args, **_kwargs: body)
    monkeypatch.setattr(signer.time, "monotonic", lambda: 5.0)
    monkeypatch.setattr(
        signer,
        "create_executor_attestation",
        lambda *_args: pytest.fail("expired executor receipt was signed"),
    )
    monkeypatch.setattr(
        signer,
        "approve_executor_attestation",
        lambda *_args: pytest.fail("expired approver receipt was signed"),
    )
    args = SimpleNamespace(data_image="/sealed.img")
    config = {role: {"key_id": role}}
    draft = {"body": body} if role == "approver" else None

    with pytest.raises(TimeoutError, match=f"{role} receipt signing deadline expired"):
        signer.sign_verified_receipt(
            role=role,
            args=args,
            config=config,
            key=b"key",
            key_id=role,
            draft=draft,
            deadline_monotonic=5.0,
        )


def test_verifier_expired_after_semantics_transitions_failed_without_envelope(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744915235: expiry immediately before commit is FAILED.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import verifier_service
    from benchmarks.codegraph_compare.verifier_ledger import ChallengeLedger

    monkeypatch.setattr(ChallengeLedger, "_acquire_lease", lambda _self: None)
    ledger = ChallengeLedger(tmp_path / "deadline.sqlite")
    digest = "a" * 64
    challenge = ledger.begin(digest)["challenge"]
    ticks = iter((9, 10))
    monkeypatch.setattr(verifier_service.time, "monotonic_ns", lambda: next(ticks))
    monkeypatch.setattr(
        verifier_service,
        "_load_manifest",
        lambda *_args, **_kwargs: (
            {"cells": []},
            digest,
            challenge,
            "b" * 64,
            "c" * 64,
        ),
    )
    monkeypatch.setattr(verifier_service, "aggregate_verdict", lambda *_a, **_k: {})
    monkeypatch.setattr(verifier_service, "_validate_verdict_schema", lambda _v: None)

    with pytest.raises(TimeoutError, match="service contract deadline expired"):
        verifier_service._verify(
            {
                "manifest_sha256": digest,
                "challenge": challenge,
                "deadline_monotonic_ns": 10,
            },
            {},
            tmp_path,
            tmp_path,
            Ed25519PrivateKey.generate(),
            ledger,
            {},
        )
    database = sqlite3.connect(ledger.path)
    try:
        state = database.execute(
            "SELECT state FROM challenges WHERE challenge=?", (challenge,)
        ).fetchone()[0]
        verdict_count = database.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0]
    finally:
        database.close()

    assert (state, verdict_count) == ("FAILED", 0)


def test_operator_recomputes_configured_plan_set_before_authority_calls():
    # PR #1249 review 3744915238: stale aggregate hashes fail before cell consumption.
    source = Path("benchmarks/codegraph_compare/qualification_operator.py").read_text(
        encoding="utf-8"
    )

    assert source.count("verify_configured_plan_set(decision_contract, config)") == 1
    assert source.index(
        "verify_configured_plan_set(decision_contract, config)"
    ) < source.index("authority = run_cell(")


@pytest.mark.parametrize(
    "invalid",
    (
        "src,bad.py",
        "src/control\x1f.py",
        "src\\bad.py",
        "/src/bad.py",
        "src/./bad.py",
        "a" * 4097,
    ),
)
def test_receipt_inventory_enforces_published_relative_path(invalid: str):
    # PR #1249 review 3744944744: preflight must match published relativePath.
    from benchmarks.codegraph_compare.receipt_inventory import (
        validate_receipt_inventory,
    )

    eligibility = dict(_qualification_v3_body()["source"]["eligibility"])
    eligibility["eligible_paths"] = [invalid]

    with pytest.raises(ValueError, match="canonical relative path"):
        validate_receipt_inventory({"eligibility": eligibility})


def test_receipt_inventory_accepts_consistent_sha256_git_object_ids():
    # PR #1249 review 3744944747: SHA-256 Git repositories use 64-char OIDs.
    from benchmarks.codegraph_compare.receipt_inventory import (
        validate_receipt_inventory,
    )

    eligibility = dict(_qualification_v3_body()["source"]["eligibility"])
    eligibility["commit"] = "a" * 64
    eligibility["root_tree_id"] = "b" * 64
    eligibility["tracked_entries"] = [
        [path, mode, "c" * 64]
        for path, mode, _object_id in eligibility["tracked_entries"]
    ]
    eligibility["tracked_files"] = [
        [path, mode, "c" * 64, size, digest]
        for path, mode, _object_id, size, digest in eligibility["tracked_files"]
    ]

    validated = validate_receipt_inventory({"eligibility": eligibility})

    assert validated["root_tree_id"] == "b" * 64


def test_receipt_inventory_rejects_mixed_git_object_formats():
    # PR #1249 review 3744944747: every OID must match the root-tree algorithm.
    from benchmarks.codegraph_compare.receipt_inventory import (
        validate_receipt_inventory,
    )

    eligibility = dict(_qualification_v3_body()["source"]["eligibility"])
    eligibility["root_tree_id"] = "b" * 64

    with pytest.raises(ValueError, match="match root tree format"):
        validate_receipt_inventory({"eligibility": eligibility})


def test_verifier_file_hash_checks_absolute_deadline(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744944740: large evidence hashes cannot outlive service work.
    from benchmarks.codegraph_compare import verifier

    evidence = tmp_path / "evidence.bin"
    evidence.write_bytes(b"payload")
    monkeypatch.setattr(verifier.time, "monotonic", lambda: 10.0)

    with pytest.raises(TimeoutError, match="hashing deadline expired"):
        verifier._sha_file(evidence, deadline_monotonic=10.0)


def test_authority_cleanup_recovers_only_after_confirmed_absence(monkeypatch):
    # PR #1249 review 3744944754: ambiguous rm requires Docker+cgroup confirmation.
    from benchmarks.codegraph_compare import audit_authority_runner as authority

    calls = []

    def run(command, **_kwargs):
        calls.append(command)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(command, 120)
        return SimpleNamespace(
            returncode=1,
            stdout=b"",
            stderr=b"Error: No such object: producer",
        )

    monkeypatch.setattr(authority.subprocess, "run", run)

    authority._cleanup_producer("producer", Path("/missing/cgroup"))

    assert calls == [
        ["docker", "rm", "-f", "producer"],
        ["docker", "inspect", "producer"],
    ]


def test_authority_cleanup_unknown_state_is_process_fatal(monkeypatch):
    # PR #1249 review 3744944754: unconfirmed cleanup must fail-stop the service.
    from benchmarks.codegraph_compare import audit_authority_runner as authority

    ticks = iter((0.0, 0.0, 1.0, 1.0))
    monkeypatch.setattr(authority, "AUTHORITY_COMMAND_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(
        authority,
        "time",
        SimpleNamespace(
            monotonic=lambda: next(ticks),
            sleep=lambda _seconds: None,
        ),
    )
    monkeypatch.setattr(authority, "_docker_container_absent", lambda *_args: False)
    monkeypatch.setattr(
        authority.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )

    with pytest.raises(
        authority.AuthorityCleanupFatal,
        match="could not confirm Docker/cgroup absence",
    ):
        authority._cleanup_producer("producer", Path("/missing/cgroup"))


_mark_posix_qualification_section_tests()
