"""Issue #1376：test_benchmark_harness_canary_protocol 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.unit._benchmark_harness_smoke_helpers import TestGinSmokeManifestExecution


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
        journal = json.loads(
            (tmp_path / "canary-journal.json").read_text(encoding="utf-8")
        )
        journal_transcript = next(
            artifact
            for artifact in journal["result"]["artifacts"]
            if artifact["kind"] == "transcript"
        )
        assert journal_transcript["evidence_path"] == transcript_artifact.evidence_path

    def test_cost_survives_transcript_hash_failure_in_terminal_journal(self, tmp_path):
        runner, state = self._runner(tmp_path, transcript_missing=True)

        result = runner.execute()
        journal = json.loads(
            (tmp_path / "canary-journal.json").read_text(encoding="utf-8")
        )

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
