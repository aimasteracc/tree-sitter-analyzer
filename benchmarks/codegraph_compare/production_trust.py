"""Fail-closed production trust qualification for the NO1-002C canary.

This module validates only operator-controlled configuration and immutable
references.  It deliberately cannot sign attestations, reserve spend, collect
evidence, or dispatch a model request; those responsibilities belong to the
independent services described by issue #1223.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

from benchmarks.codegraph_compare.canary_evidence import canonical_sha256

SCHEMA_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_ROLES = frozenset(
    {"anchor-custodian", "budget-gateway", "evidence-collector"}
)


def _nonempty(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _digest(value: object, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True)
class ProductionRunSpecV1:
    manifest_hash: str
    cell_id: str
    model: str
    prompt_sha256: str
    launch_identity_sha256: str
    workspace_baseline_sha256: str
    budget_ceiling_usd: float
    token_limit: int
    request_limit: int
    nonce: str
    expires_at_unix: int

    @property
    def spec_hash(self) -> str:
        validate_production_run_spec(self)
        return canonical_sha256(
            {
                "schema_version": SCHEMA_VERSION,
                "manifest_hash": self.manifest_hash,
                "cell_id": self.cell_id,
                "model": self.model,
                "prompt_sha256": self.prompt_sha256,
                "launch_identity_sha256": self.launch_identity_sha256,
                "workspace_baseline_sha256": self.workspace_baseline_sha256,
                "budget_ceiling_usd": self.budget_ceiling_usd,
                "token_limit": self.token_limit,
                "request_limit": self.request_limit,
                "nonce": self.nonce,
                "expires_at_unix": self.expires_at_unix,
            }
        )


@dataclass(frozen=True)
class OperatorTrustConfigV1:
    """References supplied out of band; never serialized into evidence bundles."""

    trust_store: Path
    pinned_anchor: Path
    immutable_artifact_root: Path
    trusted_roles: frozenset[str]
    provider_budget_enforced: bool
    append_only_ledger: bool
    immutable_collector: bool
    isolated_execution: bool
    verification_to_use_closed: bool
    independent_judge: bool
    # "provider": real provider-side spend reservation (preferred).
    # "client-process-kill": subprocess timeout + post-run usage verification.
    # The latter is documented as a limitation when Codex CLI lacks a reservation API.
    budget_enforcement_mode: str = "provider"
    pinned_judge: Path | None = None
    spend_key_id: str = "legacy-spend-key"
    judge_key_id: str = "legacy-judge-key"


@dataclass(frozen=True)
class ProductionQualification:
    status: str
    violations: tuple[str, ...]
    spec_hash: str | None
    model_callbacks_allowed: bool


def validate_production_run_spec(spec: object) -> None:
    if type(spec) is not ProductionRunSpecV1:
        raise ValueError("run spec must be an exact ProductionRunSpecV1")
    _digest(spec.manifest_hash, "manifest_hash")
    _nonempty(spec.cell_id, "cell_id")
    _nonempty(spec.model, "model")
    _digest(spec.prompt_sha256, "prompt_sha256")
    _digest(spec.launch_identity_sha256, "launch_identity_sha256")
    _digest(spec.workspace_baseline_sha256, "workspace_baseline_sha256")
    if (
        type(spec.budget_ceiling_usd) is not float
        or not math.isfinite(spec.budget_ceiling_usd)
        or spec.budget_ceiling_usd <= 0
    ):
        raise ValueError("budget_ceiling_usd must be finite and positive")
    for label, value in (
        ("token_limit", spec.token_limit),
        ("request_limit", spec.request_limit),
        ("expires_at_unix", spec.expires_at_unix),
    ):
        if type(value) is not int or value <= 0:
            raise ValueError(f"{label} must be a positive integer")
    _nonempty(spec.nonce, "nonce")


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _has_symlink_component(path: Path) -> bool:
    absolute = _absolute_lexical(path)
    return any(candidate.is_symlink() for candidate in (absolute, *absolute.parents))


def _trusted_external_file(path: Path, bundle_root: Path, label: str) -> str | None:
    lexical = _absolute_lexical(path)
    bundle_lexical = _absolute_lexical(bundle_root)
    if lexical == bundle_lexical or bundle_lexical in lexical.parents:
        return f"{label.upper()}_BUNDLE_CONTROLLED"
    if _has_symlink_component(path):
        return f"{label.upper()}_SYMLINK"
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return f"{label.upper()}_UNAVAILABLE"
    bundle = bundle_root.resolve(strict=False)
    if not resolved.is_file():
        return f"{label.upper()}_NOT_FILE"
    if resolved == bundle or bundle in resolved.parents:
        return f"{label.upper()}_BUNDLE_CONTROLLED"
    return None


def qualify_production_trust(
    spec: object,
    config: OperatorTrustConfigV1 | None,
    *,
    evidence_bundle_root: Path,
    now_unix: int,
) -> ProductionQualification:
    """Return a fail-closed qualification without invoking production services."""

    try:
        validate_production_run_spec(spec)
    except (AttributeError, TypeError, ValueError) as error:
        return ProductionQualification(
            "INVALID", (f"RUN_SPEC_INVALID:{error}",), None, False
        )
    assert type(spec) is ProductionRunSpecV1
    spec_hash = spec.spec_hash
    if config is None:
        return ProductionQualification(
            "NOT_EVALUATED", ("OPERATOR_TRUST_CONFIG_UNAVAILABLE",), spec_hash, False
        )

    violations: list[str] = []
    for path, label in (
        (config.trust_store, "trust_store"),
        (config.pinned_anchor, "pinned_anchor"),
    ):
        violation = _trusted_external_file(path, evidence_bundle_root, label)
        if violation is not None:
            violations.append(violation)
    artifact_lexical = _absolute_lexical(config.immutable_artifact_root)
    bundle_lexical = _absolute_lexical(evidence_bundle_root)
    if artifact_lexical == bundle_lexical or bundle_lexical in artifact_lexical.parents:
        violations.append("ARTIFACT_ROOT_BUNDLE_CONTROLLED")
    elif _has_symlink_component(config.immutable_artifact_root):
        violations.append("ARTIFACT_ROOT_SYMLINK")
    if config.immutable_artifact_root.exists():
        violations.append("ARTIFACT_ROOT_PREEXISTS")
    if config.trusted_roles != _REQUIRED_ROLES:
        violations.append("TRUST_ROLES_INCOMPLETE")
    for enabled, violation in (
        (config.provider_budget_enforced, "PROVIDER_BUDGET_GATEWAY_UNAVAILABLE"),
        (config.append_only_ledger, "APPEND_ONLY_LEDGER_UNAVAILABLE"),
        (config.immutable_collector, "IMMUTABLE_COLLECTOR_UNAVAILABLE"),
        (config.isolated_execution, "ISOLATED_EXECUTION_UNAVAILABLE"),
        (config.verification_to_use_closed, "VERIFICATION_TO_USE_OPEN"),
        (config.independent_judge, "INDEPENDENT_JUDGE_UNAVAILABLE"),
    ):
        if enabled is not True:
            violations.append(violation)
    if type(now_unix) is not int or now_unix < 0:
        violations.append("TRUSTED_CLOCK_INVALID")
    elif spec.expires_at_unix <= now_unix:
        violations.append("RUN_SPEC_EXPIRED")

    if violations:
        return ProductionQualification(
            "NOT_EVALUATED", tuple(violations), spec_hash, False
        )
    return ProductionQualification(
        "NOT_EVALUATED",
        ("SIGNED_ATTESTATIONS_AND_JUDGE_VERDICT_REQUIRED",),
        spec_hash,
        False,
    )


def qualify_production_trust_v2(
    spec: object,
    config: OperatorTrustConfigV1 | None,
    attestation: object,
    judge_record: object,
    *,
    evidence_bundle_root: Path,
    now_unix: int,
    expected_evidence_digest: str,
) -> ProductionQualification:
    """Extended qualification that enables model_callbacks_allowed when all trust
    gates are satisfied.

    Spend and Judge keys are loaded exclusively from independently pinned config
    paths (never caller arguments), with distinct roles and key IDs.

    The judge record's evidence_digest is compared against expected_evidence_digest
    so that an authentic ACCEPT from an earlier or unrelated run cannot be replayed.

    The attestation's budget_enforcement_mode must match config.budget_enforcement_mode;
    mismatches are rejected regardless of whether both values are individually valid.

    Budget enforcement note: when config.budget_enforcement_mode is
    "client-process-kill", provider-side spend reservation is unavailable
    (Codex CLI limitation — issue #1223).  Client-side process kill and
    post-run usage verification are the accepted alternative per the maintainer
    decision recorded 2026-08-07.

    Args:
        spec: A ProductionRunSpecV1 instance.
        config: An OperatorTrustConfigV1 (operator-controlled, never bundle-provided).
        attestation: A SpendAttestation issued by the Anchor Custodian.
        judge_record: A JudgeRecord signed by the Judge.
        evidence_bundle_root: Path that must not contain the trust store or anchor.
        now_unix: Current Unix time for expiry checks.
        expected_evidence_digest: SHA-256 that judge_record.evidence_digest must equal.

    Returns:
        ProductionQualification with model_callbacks_allowed=True only on full ACCEPT.
    """
    from benchmarks.codegraph_compare.production_anchor import (
        AnchorKey,
        SpendAttestation,
        verify_attestation,
    )
    from benchmarks.codegraph_compare.production_judge import (
        JudgeRecord,
        verify_judge_record,
    )

    # Validate run spec.
    try:
        validate_production_run_spec(spec)
    except (AttributeError, TypeError, ValueError) as error:
        return ProductionQualification(
            "INVALID", (f"RUN_SPEC_INVALID:{error}",), None, False
        )
    assert type(spec) is ProductionRunSpecV1
    spec_hash = spec.spec_hash

    if config is None:
        return ProductionQualification(
            "NOT_EVALUATED", ("OPERATOR_TRUST_CONFIG_UNAVAILABLE",), spec_hash, False
        )

    # Production qualification requires two independently pinned role keys.
    try:
        anchor_key = AnchorKey.from_file(config.pinned_anchor)
        if config.pinned_judge is None:
            raise ValueError("pinned judge key is required")
        judge_key = AnchorKey.from_file(config.pinned_judge)
    except Exception as error:
        return ProductionQualification(
            "NOT_EVALUATED", (f"ROLE_KEY_UNAVAILABLE:{error}",), spec_hash, False
        )

    if not isinstance(attestation, SpendAttestation):
        return ProductionQualification(
            "NOT_EVALUATED",
            ("ATTESTATION_MISSING_OR_WRONG_TYPE",),
            spec_hash,
            False,
        )
    if not isinstance(judge_record, JudgeRecord):
        return ProductionQualification(
            "NOT_EVALUATED",
            ("JUDGE_RECORD_MISSING_OR_WRONG_TYPE",),
            spec_hash,
            False,
        )

    # Re-implement trust config validation inline (without calling the base function)
    # so that client-process-kill mode is handled explicitly rather than via flag mutation.
    violations: list[str] = []
    assert config.pinned_judge is not None
    for path, label in (
        (config.trust_store, "trust_store"),
        (config.pinned_anchor, "pinned_anchor"),
        (config.pinned_judge, "pinned_judge"),
    ):
        violation = _trusted_external_file(path, evidence_bundle_root, label)
        if violation is not None:
            violations.append(violation)
    if config.pinned_judge is not None:
        try:
            if config.pinned_anchor.resolve(strict=True) == config.pinned_judge.resolve(
                strict=True
            ):
                violations.append("ROLE_KEYS_NOT_INDEPENDENT")
        except OSError:
            pass
    if config.spend_key_id == config.judge_key_id:
        violations.append("ROLE_KEY_IDS_NOT_INDEPENDENT")
    artifact_lexical = _absolute_lexical(config.immutable_artifact_root)
    bundle_lexical = _absolute_lexical(evidence_bundle_root)
    if artifact_lexical == bundle_lexical or bundle_lexical in artifact_lexical.parents:
        violations.append("ARTIFACT_ROOT_BUNDLE_CONTROLLED")
    elif _has_symlink_component(config.immutable_artifact_root):
        violations.append("ARTIFACT_ROOT_SYMLINK")
    if config.immutable_artifact_root.exists():
        violations.append("ARTIFACT_ROOT_PREEXISTS")
    if config.trusted_roles != _REQUIRED_ROLES:
        violations.append("TRUST_ROLES_INCOMPLETE")
    # Budget enforcement: provider-side preferred; client-process-kill explicitly accepted.
    if config.budget_enforcement_mode not in ("provider", "client-process-kill"):
        violations.append(
            f"UNKNOWN_BUDGET_ENFORCEMENT_MODE:{config.budget_enforcement_mode!r}"
        )
    elif (
        config.budget_enforcement_mode == "provider"
        and config.provider_budget_enforced is not True
    ):
        violations.append("PROVIDER_BUDGET_GATEWAY_UNAVAILABLE")
    for enabled, violation in (
        (config.append_only_ledger, "APPEND_ONLY_LEDGER_UNAVAILABLE"),
        (config.immutable_collector, "IMMUTABLE_COLLECTOR_UNAVAILABLE"),
        (config.isolated_execution, "ISOLATED_EXECUTION_UNAVAILABLE"),
        (config.verification_to_use_closed, "VERIFICATION_TO_USE_OPEN"),
    ):
        if enabled is not True:
            violations.append(violation)
    if type(now_unix) is not int or now_unix < 0:
        violations.append("TRUSTED_CLOCK_INVALID")
    elif spec.expires_at_unix <= now_unix:
        violations.append("RUN_SPEC_EXPIRED")

    if violations:
        return ProductionQualification(
            "NOT_EVALUATED", tuple(violations), spec_hash, False
        )

    # Verify attestation HMAC and binding.
    attest_violations: list[str] = []
    try:
        verify_attestation(
            attestation,
            anchor_key,
            spec_hash,
            spec.nonce,
            spec.expires_at_unix,
            now_unix=now_unix,
        )
    except Exception as error:
        attest_violations.append(f"ATTESTATION_INVALID:{error}")

    if attestation.issuer_role != "spend-authorizer":
        attest_violations.append("ATTESTATION_ROLE_MISMATCH")
    if attestation.key_id != config.spend_key_id:
        attest_violations.append("ATTESTATION_KEY_ID_MISMATCH")

    # Attestation budget mode must match config — prevents mode substitution.
    if (
        not attest_violations
        and attestation.budget_enforcement_mode != config.budget_enforcement_mode
    ):
        attest_violations.append(
            f"BUDGET_MODE_MISMATCH:"
            f"attestation={attestation.budget_enforcement_mode!r}:"
            f"config={config.budget_enforcement_mode!r}"
        )

    # Verify judge record HMAC, verdict, and evidence binding.
    try:
        verify_judge_record(judge_record, judge_key)
        if judge_record.issuer_role != "independent-judge":
            attest_violations.append("JUDGE_ROLE_MISMATCH")
        elif judge_record.key_id != config.judge_key_id:
            attest_violations.append("JUDGE_KEY_ID_MISMATCH")
        elif judge_record.verdict != "ACCEPT":
            attest_violations.append(f"JUDGE_VERDICT_NOT_ACCEPT:{judge_record.verdict}")
        elif judge_record.evidence_digest != expected_evidence_digest:
            attest_violations.append(
                "JUDGE_EVIDENCE_DIGEST_MISMATCH:"
                f"expected={expected_evidence_digest[:16]}...:"
                f"got={judge_record.evidence_digest[:16]}..."
            )
        elif judge_record.spec_hash != spec_hash:
            attest_violations.append(
                "JUDGE_SPEC_HASH_MISMATCH:"
                f"expected={spec_hash[:16]}...:"
                f"got={judge_record.spec_hash[:16]}..."
            )
    except Exception as error:
        attest_violations.append(f"JUDGE_RECORD_INVALID:{error}")

    if attest_violations:
        return ProductionQualification(
            "NOT_EVALUATED", tuple(attest_violations), spec_hash, False
        )

    return ProductionQualification("ACCEPT", (), spec_hash, True)
