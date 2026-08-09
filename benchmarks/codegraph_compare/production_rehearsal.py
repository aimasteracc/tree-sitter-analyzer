"""Zero-cost offline rehearsal for the NO1-002C/002D trust chain.

This module never imports an agent adapter or dispatches a model request.  It
uses an ephemeral rehearsal-only anchor and spec for one fail-closed denial probe
and one explicitly bound v2 fixture probe. The latter traverses attestation,
judge, spec, and evidence-digest binding without consuming callback eligibility.
"""

from __future__ import annotations

import argparse
import json
import secrets
import stat
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from benchmarks.codegraph_compare.canary_evidence import canonical_sha256
from benchmarks.codegraph_compare.production_anchor import (
    AnchorKey,
    prepare_attestation,
    verify_attestation,
)
from benchmarks.codegraph_compare.production_collector import EvidenceCollector
from benchmarks.codegraph_compare.production_judge import (
    submit_verdict,
    verify_judge_record,
)
from benchmarks.codegraph_compare.production_trust import (
    OperatorTrustConfigV1,
    ProductionRunSpecV1,
    qualify_production_trust_v2,
)

_PROTOCOL = "NO1-003B-OFFLINE"
_ROLES = frozenset({"anchor-custodian", "budget-gateway", "evidence-collector"})


@dataclass(frozen=True)
class OfflineRehearsalReceipt:
    schema_version: int
    protocol: str
    status: str
    execution_mode: str
    spec_hash: str
    evidence_digest: str
    artifact_count: int
    attestation_verified: bool
    synthetic_judge_signature_verified: bool
    independent_judge_available: bool
    denial_probe_qualification_status: str
    denial_probe_violations: tuple[str, ...]
    bound_fixture_qualification_status: str
    bound_fixture_violations: tuple[str, ...]
    bound_fixture_probe_assumes_independent_judge: bool
    bound_fixture_gate_eligible: bool
    production_dispatch_allowed: bool
    model_callbacks_invoked: int
    provider_requests: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    evidence_level: str
    winner: None
    dominance_allowed: bool
    publishable: bool


def run_offline_rehearsal(
    work_root: Path, *, now_unix: int | None = None
) -> OfflineRehearsalReceipt:
    """Exercise denial and bound-fixture trust paths without network or callbacks."""

    if work_root.exists():
        raise ValueError("offline rehearsal work root must not pre-exist")
    # macOS temporary roots commonly arrive through /var -> /private/var.
    # Resolve the fresh child once so trust validation sees one physical path.
    work_root = work_root.resolve(strict=False)
    now = int(time.time()) if now_unix is None else now_unix
    if type(now) is not int or now <= 0:
        raise ValueError("now_unix must be a positive integer")

    operator_root = work_root / "operator"
    bundle_root = work_root / "untrusted-bundle"
    qualification_root = work_root / "qualification-evidence"
    production_artifact_root = (work_root / "unused-production-artifacts").resolve()
    production_journal_root = (work_root / "unused-production-journal").resolve()
    global_ledger_root = (work_root / "operator-global-ledger").resolve()
    operator_root.mkdir(parents=True, mode=0o700)
    global_ledger_root.mkdir(mode=0o700)
    bundle_root.mkdir(mode=0o700)

    key = AnchorKey(raw=secrets.token_bytes(32))
    judge_key = AnchorKey(raw=secrets.token_bytes(32))
    anchor_path = operator_root / "ephemeral-rehearsal-anchor.key"
    judge_path = operator_root / "ephemeral-rehearsal-judge.key"
    trust_store = operator_root / "trust-store.json"
    anchor_path.write_text(key.raw.hex(), encoding="utf-8")
    judge_path.write_text(judge_key.raw.hex(), encoding="utf-8")
    anchor_path.chmod(0o400)
    judge_path.chmod(0o400)
    trust_store.write_text('{"protocol":"NO1-003B-OFFLINE"}\n', encoding="utf-8")
    trust_store.chmod(0o400)

    nonce = secrets.token_hex(16)
    spec = ProductionRunSpecV1(
        manifest_hash=canonical_sha256(
            {"protocol": _PROTOCOL, "mode": "offline-rehearsal", "nonce": nonce}
        ),
        cell_id="offline-rehearsal-only",
        model="offline-fixture-no-model",
        prompt_sha256=canonical_sha256("NO MODEL CALL"),
        launch_identity_sha256=canonical_sha256("NO AGENT ADAPTER"),
        workspace_baseline_sha256=canonical_sha256("SYNTHETIC WORKSPACE"),
        budget_ceiling_usd=3.0,
        token_limit=1,
        request_limit=1,
        nonce=nonce,
        expires_at_unix=now + 600,
        journal_root=str(production_journal_root),
        evidence_root=str(production_artifact_root),
        global_nonce_ledger_root=str(global_ledger_root),
    )
    attestation = prepare_attestation(
        spec.spec_hash,
        spec.nonce,
        spec.expires_at_unix,
        key,
        budget_enforcement_mode="provider",
        now_unix=now,
        key_id="rehearsal-spend",
    )
    verify_attestation(
        attestation,
        key,
        spec.spec_hash,
        spec.nonce,
        spec.expires_at_unix,
        now_unix=now,
    )

    collector = EvidenceCollector(qualification_root)
    collector.collect(
        "offline-rehearsal-only",
        "transcript",
        b'{"model_calls":0,"provider_requests":0,"status":"SYNTHETIC"}\n',
    )
    collector.collect(
        "offline-rehearsal-only",
        "usage",
        b'{"cost_usd":0.0,"input_tokens":0,"output_tokens":0}\n',
    )
    collection = collector.finalize()
    if any(
        stat.S_IMODE(Path(item.path).stat().st_mode) & stat.S_IWUSR
        for item in collection.artifacts
    ):
        raise RuntimeError("offline rehearsal collector did not seal every artifact")

    judge = submit_verdict(
        "ACCEPT",
        collection.ledger_sha256,
        spec.spec_hash,
        judge_key,
        judge_note="offline rehearsal fixture only; not production evidence",
        now_unix=now,
        key_id="rehearsal-judge",
    )
    verify_judge_record(judge, judge_key)
    config = OperatorTrustConfigV1(
        trust_store=trust_store,
        pinned_anchor=anchor_path,
        pinned_judge=anchor_path,
        immutable_artifact_root=production_artifact_root,
        trusted_roles=_ROLES,
        provider_budget_enforced=True,
        append_only_ledger=True,
        immutable_collector=True,
        isolated_execution=True,
        verification_to_use_closed=True,
        # A same-process rehearsal signature is deliberately not independent.
        independent_judge=False,
        budget_enforcement_mode="provider",
        spend_key_id="rehearsal-spend",
        judge_key_id="rehearsal-judge",
        immutable_journal_root=production_journal_root,
        global_nonce_ledger_root=global_ledger_root,
        pinned_provider_receipt_key=anchor_path,
    )
    qualification = qualify_production_trust_v2(
        spec,
        config,
        attestation,
        judge,
        evidence_bundle_root=bundle_root,
        now_unix=now,
        expected_evidence_digest=collection.ledger_sha256,
    )
    expected_violations = (
        "ROLE_KEYS_NOT_INDEPENDENT",
        "ROLE_KEY_MATERIAL_NOT_INDEPENDENT",
    )
    if (
        qualification.status != "NOT_EVALUATED"
        or qualification.violations != expected_violations
        or qualification.model_callbacks_allowed
    ):
        raise RuntimeError(
            "offline trust rehearsal did not fail closed: "
            + ",".join(qualification.violations)
        )

    # A second, explicitly fixture-bound probe assumes the independent-judge bit
    # solely to traverse v2 attestation, judge, spec, and evidence-digest binding.
    # Eligibility is observed but never consumed by a dispatch callback.
    bound_qualification = qualify_production_trust_v2(
        spec,
        replace(config, pinned_judge=judge_path, independent_judge=True),
        attestation,
        judge,
        evidence_bundle_root=bundle_root,
        now_unix=now,
        expected_evidence_digest=collection.ledger_sha256,
    )
    if (
        bound_qualification.status != "ACCEPT"
        or bound_qualification.violations
        or not bound_qualification.model_callbacks_allowed
    ):
        raise RuntimeError(
            "offline bound fixture did not traverse trust bindings: "
            + ",".join(bound_qualification.violations)
        )

    # The same-key judge record is synthetic and not production-independent.
    # Neither qualification result is connected to an adapter or provider callback.
    return OfflineRehearsalReceipt(
        schema_version=1,
        protocol=_PROTOCOL,
        status="PASS",
        execution_mode="offline-rehearsal",
        spec_hash=spec.spec_hash,
        evidence_digest=collection.ledger_sha256,
        artifact_count=collection.artifact_count,
        attestation_verified=True,
        synthetic_judge_signature_verified=True,
        independent_judge_available=False,
        denial_probe_qualification_status=qualification.status,
        denial_probe_violations=qualification.violations,
        bound_fixture_qualification_status=bound_qualification.status,
        bound_fixture_violations=bound_qualification.violations,
        bound_fixture_probe_assumes_independent_judge=True,
        bound_fixture_gate_eligible=bound_qualification.model_callbacks_allowed,
        production_dispatch_allowed=False,
        model_callbacks_invoked=0,
        provider_requests=0,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        evidence_level="E0",
        winner=None,
        dominance_allowed=False,
        publishable=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--work-root",
        type=Path,
        required=True,
        help="fresh directory used for synthetic, model-free trust artifacts",
    )
    args = parser.parse_args(argv)
    receipt = run_offline_rehearsal(args.work_root)
    print(json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
