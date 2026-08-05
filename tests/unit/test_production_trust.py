"""Behavioral tests for the NO1-002D production trust boundary."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from benchmarks.codegraph_compare.production_trust import (
    OperatorTrustConfigV1,
    ProductionRunSpecV1,
    qualify_production_trust,
)


def _spec() -> ProductionRunSpecV1:
    return ProductionRunSpecV1(
        manifest_hash="a" * 64,
        cell_id="tsa-warm-canary",
        model="gpt-production",
        prompt_sha256="b" * 64,
        launch_identity_sha256="c" * 64,
        workspace_baseline_sha256="d" * 64,
        budget_ceiling_usd=3.0,
        token_limit=100_000,
        request_limit=2,
        nonce="judge-issued-nonce",
        expires_at_unix=2_000_000_000,
    )


def _config(tmp_path: Path, bundle: Path) -> OperatorTrustConfigV1:
    operator = tmp_path / "operator"
    operator.mkdir()
    trust_store = operator / "trust-store.json"
    anchor = operator / "anchor.json"
    trust_store.write_text("{}\n", encoding="utf-8")
    anchor.write_text("{}\n", encoding="utf-8")
    return OperatorTrustConfigV1(
        trust_store=trust_store,
        pinned_anchor=anchor,
        immutable_artifact_root=tmp_path / "collector" / "new-run",
        trusted_roles=frozenset(
            {"anchor-custodian", "budget-gateway", "evidence-collector"}
        ),
        provider_budget_enforced=True,
        append_only_ledger=True,
        immutable_collector=True,
        isolated_execution=True,
        verification_to_use_closed=True,
        independent_judge=True,
    )


def test_missing_operator_configuration_blocks_every_model_callback(tmp_path: Path):
    # Issue #1223: bundle-only qualification must never enable production.
    result = qualify_production_trust(
        _spec(), None, evidence_bundle_root=tmp_path, now_unix=1_900_000_000
    )

    assert result.status == "NOT_EVALUATED"
    assert result.violations == ("OPERATOR_TRUST_CONFIG_UNAVAILABLE",)
    assert result.model_callbacks_allowed is False


def test_bundle_provided_trust_store_is_rejected(tmp_path: Path):
    # Issue #1223: bundled keys and TOFU are forbidden.
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    config = _config(tmp_path, bundle)
    bundled_store = bundle / "trust-store.json"
    bundled_store.write_text("{}\n", encoding="utf-8")

    result = qualify_production_trust(
        _spec(),
        replace(config, trust_store=bundled_store),
        evidence_bundle_root=bundle,
        now_unix=1_900_000_000,
    )

    assert result.violations == ("TRUST_STORE_BUNDLE_CONTROLLED",)
    assert result.model_callbacks_allowed is False


def test_expired_spec_is_rejected_by_trusted_clock(tmp_path: Path):
    # Issue #1223: expired attestations must fail closed.
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    config = _config(tmp_path, bundle)

    result = qualify_production_trust(
        _spec(), config, evidence_bundle_root=bundle, now_unix=2_000_000_000
    )

    assert result.violations == ("RUN_SPEC_EXPIRED",)
    assert result.model_callbacks_allowed is False


def test_precreated_artifact_root_is_rejected(tmp_path: Path):
    # Issue #1223: collectors must create a fresh externally controlled root.
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    config = _config(tmp_path, bundle)
    config.immutable_artifact_root.mkdir(parents=True)

    result = qualify_production_trust(
        _spec(), config, evidence_bundle_root=bundle, now_unix=1_900_000_000
    )

    assert result.violations == ("ARTIFACT_ROOT_PREEXISTS",)
    assert result.model_callbacks_allowed is False


def test_complete_external_configuration_still_requires_signed_judge_evidence(
    tmp_path: Path,
):
    # Issue #1223: local configuration alone cannot self-qualify production.
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    config = _config(tmp_path, bundle)

    result = qualify_production_trust(
        _spec(), config, evidence_bundle_root=bundle, now_unix=1_900_000_000
    )

    assert result.status == "NOT_EVALUATED"
    assert result.violations == ("SIGNED_ATTESTATIONS_AND_JUDGE_VERDICT_REQUIRED",)
    assert result.model_callbacks_allowed is False
