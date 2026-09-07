"""Issue #1376：records 行为组，原测试 AST 保持不变。"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from benchmarks.codegraph_compare import analyze as compare_analyze
from benchmarks.codegraph_compare import evaluate as compare_evaluate
from tests.unit._benchmark_harness_matrix_helpers import _v1_eval, _v1_manifest, _v1_run


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
