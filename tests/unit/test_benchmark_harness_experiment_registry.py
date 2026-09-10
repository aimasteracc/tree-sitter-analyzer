"""Issue #1376：test_benchmark_harness_experiment_registry 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit._benchmark_harness_matrix_helpers import (
    _registry_for,
    _v1_eval,
    _v1_manifest,
    _v1_run,
)


class TestBenchmarkExperimentIntegrity:
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
