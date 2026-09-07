"""Issue #1376：test_benchmark_harness_experiment_integrity 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import pytest

from tests.unit._benchmark_harness_matrix_helpers import (
    _registry_for,
    _v1_eval,
    _v1_manifest,
    _v1_paths_hash,
    _v1_run,
)


class TestBenchmarkExperimentIntegrity:
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

        # Issue #1201: 绑定索引的 manifest 必须连同其哈希一起规范化。
        assert "INVALID_MANIFEST_STRUCTURE" not in {
            item.code for item in verdict.violations
        }
