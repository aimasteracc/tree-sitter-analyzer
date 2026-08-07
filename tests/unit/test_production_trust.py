"""Behavioral tests for the NO1-002D production trust boundary."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from benchmarks.codegraph_compare.production_anchor import (
    AnchorKey,
    prepare_attestation,
)
from benchmarks.codegraph_compare.production_judge import submit_verdict
from benchmarks.codegraph_compare.production_trust import (
    OperatorTrustConfigV1,
    ProductionRunSpecV1,
    qualify_production_trust,
    qualify_production_trust_v2,
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


def test_bundle_symlink_ancestor_cannot_escape_trust_store_control(tmp_path: Path):
    # Issue #1223 / PR #1226: resolve-before-containment enabled ancestor escape.
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    config = _config(tmp_path, bundle)
    external = tmp_path / "external"
    external.mkdir()
    escaped_store = external / "trust-store.json"
    escaped_store.write_text("{}\n", encoding="utf-8")
    (bundle / "keys").symlink_to(external, target_is_directory=True)

    result = qualify_production_trust(
        _spec(),
        replace(config, trust_store=bundle / "keys" / "trust-store.json"),
        evidence_bundle_root=bundle,
        now_unix=1_900_000_000,
    )

    assert result.violations == ("TRUST_STORE_BUNDLE_CONTROLLED",)


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


def test_bundle_symlink_ancestor_cannot_redirect_artifact_root(tmp_path: Path):
    # Issue #1223 / PR #1226: a fresh final path can still have a symlink ancestor.
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    config = _config(tmp_path, bundle)
    external = tmp_path / "external-collector"
    external.mkdir()
    (bundle / "collector").symlink_to(external, target_is_directory=True)

    result = qualify_production_trust(
        _spec(),
        replace(
            config,
            immutable_artifact_root=bundle / "collector" / "new-run",
        ),
        evidence_bundle_root=bundle,
        now_unix=1_900_000_000,
    )

    assert result.violations == ("ARTIFACT_ROOT_BUNDLE_CONTROLLED",)


def test_non_v1_run_spec_returns_invalid_instead_of_raising(tmp_path: Path):
    # Issue #1223 / PR #1226: malformed boundary input must fail closed.
    result = qualify_production_trust(
        None, None, evidence_bundle_root=tmp_path, now_unix=1_900_000_000
    )

    assert result.status == "INVALID"
    assert result.violations == (
        "RUN_SPEC_INVALID:run spec must be an exact ProductionRunSpecV1",
    )
    assert result.model_callbacks_allowed is False


def test_integer_budget_is_not_a_canonical_v1_run_spec(tmp_path: Path):
    # Issue #1223 / PR #1226: JSON 3 and 3.0 must not hash as different specs.
    result = qualify_production_trust(
        replace(_spec(), budget_ceiling_usd=3),
        None,
        evidence_bundle_root=tmp_path,
        now_unix=1_900_000_000,
    )

    assert result.status == "INVALID"
    assert result.violations == (
        "RUN_SPEC_INVALID:budget_ceiling_usd must be finite and positive",
    )


def test_subclass_cannot_extend_v1_attestation_hash(tmp_path: Path):
    # Issue #1223 / PR #1226: V1 hashes must bind exactly the frozen field set.
    class ExtendedSpec(ProductionRunSpecV1):
        pass

    result = qualify_production_trust(
        ExtendedSpec(**_spec().__dict__),
        None,
        evidence_bundle_root=tmp_path,
        now_unix=1_900_000_000,
    )

    assert result.status == "INVALID"
    assert result.spec_hash is None


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


# ── qualify_production_trust_v2 (self-implemented trust roles) ────────────────


def _anchor_key() -> AnchorKey:
    return AnchorKey(raw=b"anchor-key-material-32bytes!!!!!")


def _v2_config(tmp_path: Path, bundle: Path) -> OperatorTrustConfigV1:
    base = _config(tmp_path, bundle)
    return replace(
        base,
        provider_budget_enforced=False,
        budget_enforcement_mode="client-process-kill",
    )


def test_v2_returns_accept_with_valid_attestation_and_judge_record(
    tmp_path: Path,
) -> None:
    # Issue #1223: signed attestation + ACCEPT judge record enables model calls.
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    spec = _spec()
    config = _v2_config(tmp_path, bundle)
    key = _anchor_key()
    now = 1_900_000_000

    attestation = prepare_attestation(
        spec.spec_hash,
        spec.nonce,
        spec.expires_at_unix,
        key,
        budget_enforcement_mode="client-process-kill",
        now_unix=now,
    )
    judge = submit_verdict("ACCEPT", "a" * 64, key, now_unix=now)

    result = qualify_production_trust_v2(
        spec,
        config,
        attestation,
        judge,
        evidence_bundle_root=bundle,
        now_unix=now,
        anchor_key=key,
    )

    assert result.status == "ACCEPT"
    assert result.violations == ()
    assert result.model_callbacks_allowed is True


def test_v2_reject_verdict_blocks_model_callbacks(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    spec = _spec()
    config = _v2_config(tmp_path, bundle)
    key = _anchor_key()
    now = 1_900_000_000

    attestation = prepare_attestation(
        spec.spec_hash, spec.nonce, spec.expires_at_unix, key, now_unix=now
    )
    judge = submit_verdict("REJECT", "a" * 64, key, now_unix=now)

    result = qualify_production_trust_v2(
        spec,
        config,
        attestation,
        judge,
        evidence_bundle_root=bundle,
        now_unix=now,
        anchor_key=key,
    )

    assert result.status == "NOT_EVALUATED"
    assert any("JUDGE_VERDICT_NOT_ACCEPT" in v for v in result.violations)
    assert result.model_callbacks_allowed is False


def test_v2_missing_attestation_blocks_model_callbacks(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    spec = _spec()
    config = _v2_config(tmp_path, bundle)
    key = _anchor_key()
    judge = submit_verdict("ACCEPT", "a" * 64, key, now_unix=1_900_000_000)

    result = qualify_production_trust_v2(
        spec,
        config,
        None,
        judge,
        evidence_bundle_root=bundle,
        now_unix=1_900_000_000,
        anchor_key=key,
    )

    assert result.model_callbacks_allowed is False
    assert "ATTESTATION_MISSING_OR_WRONG_TYPE" in result.violations


def test_v2_wrong_anchor_key_blocks_model_callbacks(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    spec = _spec()
    config = _v2_config(tmp_path, bundle)
    key = _anchor_key()
    now = 1_900_000_000

    attestation = prepare_attestation(
        spec.spec_hash, spec.nonce, spec.expires_at_unix, key, now_unix=now
    )
    judge = submit_verdict("ACCEPT", "a" * 64, key, now_unix=now)
    wrong_key = AnchorKey(raw=b"z" * 32)

    result = qualify_production_trust_v2(
        spec,
        config,
        attestation,
        judge,
        evidence_bundle_root=bundle,
        now_unix=now,
        anchor_key=wrong_key,
    )

    assert result.model_callbacks_allowed is False
    assert any("ATTESTATION_INVALID" in v for v in result.violations)


def test_v2_config_alone_still_requires_attestations(tmp_path: Path) -> None:
    # Regression: v2 must not grant model_callbacks when attestation/judge absent.
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    spec = _spec()
    config = _config(tmp_path, bundle)

    result = qualify_production_trust_v2(
        spec,
        config,
        None,
        None,
        evidence_bundle_root=bundle,
        now_unix=1_900_000_000,
        anchor_key=None,
    )

    assert result.model_callbacks_allowed is False
