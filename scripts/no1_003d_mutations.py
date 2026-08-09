"""Executable NO1-003D authority and binding mutation gate."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from dataclasses import replace
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from benchmarks.codegraph_compare.production_authorities import (
    EvidenceAuthorityReceiptV1,
    ProviderReservationReceiptV1,
    ProviderUsageReceiptV1,
)
from benchmarks.codegraph_compare.production_dispatch import dispatch_once

ROOT = Path(__file__).resolve().parents[1]


def _fixture_module():
    spec = importlib.util.spec_from_file_location(
        "no1_dispatch_fixture", ROOT / "tests/unit/test_production_dispatch.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("dispatcher fixture unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(module, root: Path, name: str, mutate):
    case = root / name
    case.mkdir()
    request, config, attestation, judge, authorities = module._inputs(case)
    kwargs = module._kwargs(request, authorities)
    mutate(module, authorities, kwargs)
    receipt = dispatch_once(request, config, attestation, judge, **kwargs)
    if receipt.status == "PASS" or receipt.evidence_level != "E0":
        raise AssertionError(f"{name} crossed fail-closed boundary: {receipt}")
    print(
        json.dumps(
            {
                "scenario": name,
                "status": receipt.status,
                "terminal": receipt.terminal_durable,
            },
            sort_keys=True,
        )
    )


def _provider_mutator(field, value, *, usage=True, rogue=False):
    def mutate(m, a, kwargs):
        original = a.supervised

        def attacked(*args):
            result = original(*args)
            old = (
                result.provider_usage_receipt
                if usage
                else result.provider_reservation_receipt
            )
            fields = old.signed_fields()
            fields[field] = value(old) if callable(value) else value
            key = Ed25519PrivateKey.generate() if rogue else a.provider
            receipt_type = (
                ProviderUsageReceiptV1 if usage else ProviderReservationReceiptV1
            )
            bad = m._signed(key, receipt_type, **fields)
            return replace(
                result,
                **(
                    {"provider_usage_receipt": bad}
                    if usage
                    else {"provider_reservation_receipt": bad}
                ),
            )

        kwargs["transport_authority"] = attacked

    return mutate


def _provider_bad_signature(m, a, kwargs):
    original = a.supervised

    def attacked(*args):
        result = original(*args)
        bad = replace(result.provider_usage_receipt, signature_ed25519="0" * 128)
        return replace(result, provider_usage_receipt=bad)

    kwargs["transport_authority"] = attacked


def _terminal_mutator(field, value, *, rogue=False, corrupt=False):
    def mutate(m, a, kwargs):
        original = a.terminal

        def attacked(*args):
            receipt = original(*args)
            fields = receipt.signed_fields()
            fields[field] = value(receipt) if callable(value) else value
            key = Ed25519PrivateKey.generate() if rogue else a.evidence
            bad = m._signed(key, EvidenceAuthorityReceiptV1, **fields)
            return replace(bad, signature_ed25519="0" * 128) if corrupt else bad

        kwargs["evidence_authority"] = attacked

    return mutate


def run_gate(root: Path) -> None:
    m = _fixture_module()
    scenarios = {
        "usage_bool_request_count": _provider_mutator("provider_request_count", True),
        "usage_float_input_tokens": _provider_mutator("input_tokens", 1.5),
        "provider_wrong_role": _provider_mutator(
            "issuer_role", "nonce-claim-authority"
        ),
        "provider_wrong_key_id": _provider_mutator("key_id", "wrong-provider"),
        "provider_wrong_signature": _provider_bad_signature,
        "provider_cross_spec": _provider_mutator("spec_hash", "a" * 64),
        "provider_cross_nonce": _provider_mutator("nonce", "other-nonce"),
        "provider_cross_reservation": _provider_mutator(
            "reservation_id", "other-reservation"
        ),
        "evidence_wrong_role": _terminal_mutator(
            "issuer_role", "nonce-claim-authority"
        ),
        "evidence_wrong_key_id": _terminal_mutator("key_id", "wrong-evidence"),
        "evidence_wrong_signature": _terminal_mutator(
            "terminal_id", "changed", corrupt=True
        ),
        "terminal_evidence_digest": _terminal_mutator("evidence_digest", "a" * 64),
        "terminal_usage_hash": _terminal_mutator(
            "provider_usage_receipt_sha256", "b" * 64
        ),
        "terminal_claim_id": _terminal_mutator("claim_id", "other-claim"),
        "terminal_nonce": _terminal_mutator("nonce", "other-nonce"),
        "terminal_status": _terminal_mutator(
            "terminal_status",
            lambda r: "INVALID" if r.terminal_status == "PASS" else "PASS",
        ),
    }
    for name, mutate in scenarios.items():
        _run(m, root, name, mutate)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="no1-003d-mutations-") as work:
        run_gate(Path(work).resolve())
    print(
        json.dumps(
            {"gate": "NO1-003D", "status": "PASS", "scenarios": 16}, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
