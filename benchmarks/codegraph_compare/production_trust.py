"""Fail-closed production trust qualification for the NO1-002C canary.

This module validates only operator-controlled configuration and immutable
references.  It deliberately cannot sign attestations, reserve spend, collect
evidence, or dispatch a model request; those responsibilities belong to the
independent services described by issue #1223.
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from benchmarks.codegraph_compare.production_run_spec import (
    ProductionRunSpecV1,
    capture_ledger_identity,
    load_production_run_spec_v1,
    validate_production_run_spec,
)

__all__ = [
    "ProductionRunSpecV1",
    "capture_ledger_identity",
    "load_production_run_spec_v1",
    "validate_production_run_spec",
]

_REQUIRED_ROLES = frozenset(
    {"anchor-custodian", "budget-gateway", "evidence-collector"}
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
    immutable_journal_root: Path | None = None
    global_nonce_ledger_root: Path | None = None
    pinned_provider_receipt_key: Path | None = None
    provider_receipt_role: str = "provider-budget-gateway"
    provider_receipt_key_id: str = "legacy-provider-receipt-key"
    pinned_claim_authority_key: Path | None = None
    claim_authority_key_id: str = "claim-authority-v1"
    pinned_evidence_authority_key: Path | None = None
    evidence_authority_key_id: str = "evidence-authority-v1"


@dataclass(frozen=True)
class OperatorKeyPin:
    """Immutable identity and material captured from an operator key file."""

    path: str
    device: int
    inode: int
    material: bytes
    material_sha256: str


@dataclass(frozen=True)
class ProductionQualification:
    status: str
    violations: tuple[str, ...]
    spec_hash: str | None
    model_callbacks_allowed: bool
    provider_receipt_key: OperatorKeyPin | None = None
    spend_key_sha256: str | None = None
    judge_key_sha256: str | None = None
    claim_authority_key: OperatorKeyPin | None = None
    evidence_authority_key: OperatorKeyPin | None = None


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _has_symlink_component(path: Path) -> bool:
    absolute = _absolute_lexical(path)
    return any(candidate.is_symlink() for candidate in (absolute, *absolute.parents))


def _read_operator_key(path: Path) -> OperatorKeyPin:
    """Read a key through a pinned regular-file descriptor, rejecting path races."""

    if _has_symlink_component(path):
        raise ValueError(f"operator key path contains a symlink: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"operator key is not a regular file: {path}")
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            encoded = stream.read()
        after = os.fstat(descriptor)
        path_stat = os.stat(path, follow_symlinks=False)
    finally:
        os.close(descriptor)
    identity = (before.st_dev, before.st_ino)
    if identity != (after.st_dev, after.st_ino) or identity != (
        path_stat.st_dev,
        path_stat.st_ino,
    ):
        raise ValueError(f"operator key path identity changed while reading: {path}")
    if _has_symlink_component(path):
        raise ValueError(f"operator key path became a symlink: {path}")
    try:
        material = bytes.fromhex(encoded.decode("utf-8").strip())
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError(f"operator key must be hex-encoded: {path}") from error
    if len(material) < 32:
        raise ValueError(f"operator key must contain at least 32 bytes: {path}")
    return OperatorKeyPin(
        str(_absolute_lexical(path)),
        before.st_dev,
        before.st_ino,
        material,
        hashlib.sha256(material).hexdigest(),
    )


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
    """Verify independently pinned roles and signed production admission."""
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
        anchor_pin = _read_operator_key(config.pinned_anchor)
        anchor_key = AnchorKey(anchor_pin.material)
        if config.pinned_judge is None:
            raise ValueError("pinned judge key is required")
        judge_pin = _read_operator_key(config.pinned_judge)
        judge_key = AnchorKey(judge_pin.material)
        if config.pinned_provider_receipt_key is None:
            raise ValueError("pinned provider receipt key is required")
        provider_pin = _read_operator_key(config.pinned_provider_receipt_key)
        claim_pin = (
            None
            if config.pinned_claim_authority_key is None
            else _read_operator_key(config.pinned_claim_authority_key)
        )
        evidence_pin = (
            None
            if config.pinned_evidence_authority_key is None
            else _read_operator_key(config.pinned_evidence_authority_key)
        )
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
    assert config.pinned_provider_receipt_key is not None
    role_paths = [
        (config.trust_store, "trust_store"),
        (config.pinned_anchor, "pinned_anchor"),
        (config.pinned_judge, "pinned_judge"),
        (config.pinned_provider_receipt_key, "pinned_provider_receipt_key"),
    ]
    if config.pinned_claim_authority_key is not None:
        role_paths.append(
            (config.pinned_claim_authority_key, "pinned_claim_authority_key")
        )
    if config.pinned_evidence_authority_key is not None:
        role_paths.append(
            (config.pinned_evidence_authority_key, "pinned_evidence_authority_key")
        )
    for path, label in role_paths:
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
    # Different filenames and IDs are not independent when the secret/public
    # material is identical.  Compare a one-way fingerprint, never raw keys.
    material_fingerprints = [
        anchor_pin.material_sha256,
        judge_pin.material_sha256,
        provider_pin.material_sha256,
    ]
    material_fingerprints.extend(
        pin.material_sha256 for pin in (claim_pin, evidence_pin) if pin is not None
    )
    if len(set(material_fingerprints)) != len(material_fingerprints):
        violations.append("ROLE_KEY_MATERIAL_NOT_INDEPENDENT")
    role_ids = ["spend-authorizer", "independent-judge", config.provider_receipt_role]
    if claim_pin is not None:
        role_ids.append("nonce-claim-authority")
    if evidence_pin is not None:
        role_ids.append("immutable-evidence-authority")
    if (
        len(set(role_ids)) != len(role_ids)
        or config.provider_receipt_role != "provider-budget-gateway"
    ):
        violations.append("ROLE_IDENTITIES_NOT_INDEPENDENT")
    key_ids = [config.spend_key_id, config.judge_key_id, config.provider_receipt_key_id]
    if claim_pin is not None:
        key_ids.append(config.claim_authority_key_id)
    if evidence_pin is not None:
        key_ids.append(config.evidence_authority_key_id)
    if len(set(key_ids)) != len(key_ids):
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
    # No trustworthy process supervisor exists in this library boundary.  A
    # client runner may not attest its own kill/wait state.  Production accepts
    # only a provider-enforced reservation gateway.
    if config.budget_enforcement_mode != "provider":
        violations.append("UNTRUSTED_CLIENT_PROCESS_SUPERVISION")
    elif config.provider_budget_enforced is not True:
        violations.append("PROVIDER_BUDGET_GATEWAY_UNAVAILABLE")
    expected_roots = (
        (
            config.immutable_artifact_root,
            spec.evidence_root,
            "EVIDENCE_ROOT_NOT_OPERATOR_BOUND",
        ),
        (
            config.immutable_journal_root,
            spec.journal_root,
            "JOURNAL_ROOT_NOT_OPERATOR_BOUND",
        ),
        (
            config.global_nonce_ledger_root,
            spec.global_nonce_ledger_root,
            "GLOBAL_LEDGER_ROOT_NOT_OPERATOR_BOUND",
        ),
    )
    for configured, signed, violation in expected_roots:
        if configured is None or str(configured.resolve(strict=False)) != signed:
            violations.append(violation)
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

    return ProductionQualification(
        "ACCEPT",
        (),
        spec_hash,
        True,
        provider_pin,
        anchor_pin.material_sha256,
        judge_pin.material_sha256,
        claim_pin,
        evidence_pin,
    )
