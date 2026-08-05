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
