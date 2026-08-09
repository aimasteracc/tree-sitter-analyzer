"""Behavioral tests for the one-shot production dispatch subsystem."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from benchmarks.codegraph_compare.canary_evidence import create_canary_manifest
from benchmarks.codegraph_compare.production_anchor import (
    AnchorKey,
    prepare_attestation,
)
from benchmarks.codegraph_compare.production_dispatch import (
    ProductionDispatchRequestV1,
    ProviderRequestGate,
    ProviderRunFailure,
    ProviderRunResult,
    dispatch_once,
    issue_provider_reservation_receipt,
    load_journal_event_v1,
    load_production_dispatch_receipt_v1,
)
from benchmarks.codegraph_compare.production_judge import submit_verdict
from benchmarks.codegraph_compare.production_trust import (
    OperatorTrustConfigV1,
    ProductionRunSpecV1,
    capture_ledger_identity,
)

NOW = 1_900_000_000
SPEND = AnchorKey(b"s" * 32)
JUDGE = AnchorKey(b"j" * 32)
DIGEST = "e" * 64


def _inputs(tmp_path: Path, *, journal_parent: Path | None = None):
    manifest = create_canary_manifest(
        benchmark_git_sha="git",
        benchmark_version="v1",
        model="frozen-model",
        agent_cli_fingerprint="cli",
        gin_commit="gin",
        gin_source_fingerprint="a" * 64,
        canary_prompt_sha256="b" * 64,
        launch_config_hashes={"tsa-warm": "c" * 64, "codegraph-warm": "d" * 64},
        timeout_seconds=30,
        seed=7,
    )
    cell = manifest.cells[0]
    journal = ((journal_parent or tmp_path) / "journal").resolve()
    evidence = (tmp_path / "evidence").resolve()
    ledger = (tmp_path / "global-ledger").resolve()
    ledger.mkdir()
    spec = ProductionRunSpecV1(
        manifest.manifest_hash,
        cell.cell_id,
        manifest.model,
        manifest.canary_prompt_sha256,
        dict(manifest.launch_config_hashes)[cell.arm],
        "f" * 64,
        3.0,
        100,
        1,
        "one-shot-nonce",
        NOW + 100,
        str(journal),
        str(evidence),
        str(ledger),
        **capture_ledger_identity(ledger),
    )
    operator = tmp_path / "operator"
    operator.mkdir()
    spend_path = operator / "spend.key"
    spend_path.write_text(SPEND.raw.hex())
    judge_path = operator / "judge.key"
    judge_path.write_text(JUDGE.raw.hex())
    store = operator / "roles.json"
    store.write_text("{}")
    provider_path = operator / "provider.key"
    provider_path.write_text((b"p" * 32).hex())
    config = OperatorTrustConfigV1(
        store,
        spend_path,
        evidence,
        frozenset({"anchor-custodian", "budget-gateway", "evidence-collector"}),
        True,
        True,
        True,
        True,
        True,
        True,
        "provider",
        judge_path,
        "spend-2026",
        "judge-2026",
        journal,
        ledger,
        provider_path,
    )
    request = ProductionDispatchRequestV1(
        manifest, spec, 0, 30, DIGEST, journal, evidence
    )
    attestation = prepare_attestation(
        spec.spec_hash,
        spec.nonce,
        spec.expires_at_unix,
        SPEND,
        budget_enforcement_mode="provider",
        now_unix=NOW,
        key_id="spend-2026",
    )
    judge = submit_verdict(
        "ACCEPT", DIGEST, spec.spec_hash, JUDGE, now_unix=NOW, key_id="judge-2026"
    )
    return request, config, attestation, judge


def _state(request: ProductionDispatchRequestV1):
    return lambda: (
        request.spec.launch_identity_sha256,
        request.spec.workspace_baseline_sha256,
    )


def _result(**changes):
    values = {
        "provider_request_count": 1,
        "input_tokens": 10,
        "output_tokens": 20,
        "cost_usd": 0.25,
        "termination_reason": "completed",
        "transcript": b"partial transcript",
        "tool_receipt": b"tool receipt",
        "wait_completed": True,
        "usage_complete": True,
    }
    values.update(changes)
    return ProviderRunResult(**values)


def _provider(request, **changes):
    return _result(
        provider_reservation_receipt=issue_provider_reservation_receipt(
            request.spec, "provider-reservation-1", b"p" * 32
        ),
        **changes,
    )


def test_success_consumes_reservation_before_exactly_one_callback(tmp_path: Path):
    request, config, attestation, judge = _inputs(tmp_path)
    observations = []

    def runner(_request, gate):
        observations.append((request.journal_root / "000-reserved.json").is_file())
        return gate.call(_request)

    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=runner,
        provider_call=lambda request: _provider(request),
        clock=lambda: NOW,
        current_state=_state(request),
    )
    assert observations == [True]
    assert receipt.status == "PASS"
    assert receipt.model_callbacks_invoked == 1
    assert receipt.provider_requests == 1
    assert receipt.terminal_durable is True
    assert receipt.evidence_level == "E0"
    assert receipt.winner is None
    assert receipt.dominance_allowed is False
    assert receipt.publishable is False


def test_second_consumption_invokes_zero_callbacks(tmp_path: Path):
    request, config, attestation, judge = _inputs(tmp_path)
    calls = []

    def runner(_request, gate):
        calls.append("call")
        return gate.call(_request)

    first = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=runner,
        provider_call=lambda request: _provider(request),
        clock=lambda: NOW,
        current_state=_state(request),
    )
    second = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=runner,
        provider_call=lambda request: _provider(request),
        clock=lambda: NOW,
        current_state=_state(request),
    )
    assert first.model_callbacks_invoked == 1
    assert second.model_callbacks_invoked == 0
    assert calls == ["call"]


def test_non_single_request_is_rejected_before_callback(tmp_path: Path):
    request, config, attestation, judge = _inputs(tmp_path)
    bad = replace(request, spec=replace(request.spec, request_limit=2))
    receipt = dispatch_once(
        bad,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=lambda request, gate: gate.call(request),
        provider_call=lambda request: _provider(request),
        clock=lambda: NOW,
        current_state=_state(bad),
    )
    assert receipt.violations == ("REQUEST_LIMIT_NOT_ONE",)
    assert receipt.model_callbacks_invoked == 0
    assert receipt.reservation_durable is False


def test_expiry_after_reservation_is_terminal_without_callback(tmp_path: Path):
    request, config, attestation, judge = _inputs(tmp_path)
    ticks = iter((NOW, request.spec.expires_at_unix, request.spec.expires_at_unix))
    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=lambda request, gate: gate.call(request),
        provider_call=lambda request: _provider(request),
        clock=lambda: next(ticks),
        current_state=_state(request),
    )
    assert receipt.status == "INVALID"
    assert receipt.model_callbacks_invoked == 0
    assert receipt.violations == ("RUN_SPEC_EXPIRED", "RUN_SPEC_EXPIRED")
    assert receipt.reservation_durable is True
    assert receipt.terminal_durable is True


def test_workspace_change_after_callback_invalidates_result(tmp_path: Path):
    request, config, attestation, judge = _inputs(tmp_path)
    states = iter(
        (
            (
                request.spec.launch_identity_sha256,
                request.spec.workspace_baseline_sha256,
            ),
            (
                request.spec.launch_identity_sha256,
                request.spec.workspace_baseline_sha256,
            ),
            (request.spec.launch_identity_sha256, "0" * 64),
        )
    )
    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=lambda request, gate: gate.call(request),
        provider_call=lambda request: _provider(request),
        clock=lambda: NOW,
        current_state=lambda: next(states),
    )
    assert receipt.status == "INVALID"
    assert receipt.violations == ("LIVE_WORKSPACE_MISMATCH",)
    assert receipt.model_callbacks_invoked == 1


def test_timeout_failure_preserves_partial_evidence_and_terminal(tmp_path: Path):
    request, config, attestation, judge = _inputs(tmp_path)
    partial = _result(
        input_tokens=None,
        output_tokens=None,
        cost_usd=None,
        termination_reason="timeout-killed-waited",
        kill_attempted=True,
        usage_complete=False,
    )

    def runner(request, gate):
        return gate.call(request)

    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=runner,
        provider_call=lambda request: (_ for _ in ()).throw(
            ProviderRunFailure("timeout", partial)
        ),
        clock=lambda: NOW,
        current_state=_state(request),
    )
    assert receipt.status == "INVALID"
    assert receipt.violations == (
        "PROVIDER_FAILURE:timeout",
        "USAGE_MISSING_OR_INVALID",
    )
    assert receipt.model_callbacks_invoked == 1
    assert receipt.provider_requests == 1
    assert receipt.evidence_digest is not None
    assert (
        request.evidence_root / request.spec.cell_id / "transcript"
    ).read_bytes() == b"partial transcript"
    assert receipt.terminal_durable is True


def test_unknown_nonfinite_usage_fails_closed(tmp_path: Path):
    request, config, attestation, judge = _inputs(tmp_path)
    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=lambda request, gate: gate.call(request),
        provider_call=lambda request: _provider(request, cost_usd=float("nan")),
        clock=lambda: NOW,
        current_state=_state(request),
    )
    assert receipt.status == "INVALID"
    assert receipt.model_callbacks_invoked == 1
    assert receipt.evidence_digest is not None
    assert receipt.terminal_durable is True
    assert receipt.violations == ("USAGE_MISSING_OR_INVALID",)


def test_dispatcher_gate_rejects_second_request_before_provider_call(tmp_path: Path):
    request, _, _, _ = _inputs(tmp_path)
    calls = []
    gate = ProviderRequestGate(lambda _: calls.append("called") or _provider(request))
    gate.call(request)
    with pytest.raises(RuntimeError, match="PROVIDER_REQUEST_LIMIT_REACHED"):
        gate.call(request)
    assert calls == ["called"]


def test_bool_request_count_and_float_tokens_are_invalid(tmp_path: Path):
    request, config, attestation, judge = _inputs(tmp_path)
    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=lambda current, gate: gate.call(current),
        provider_call=lambda current: _provider(
            current, provider_request_count=True, input_tokens=1.5
        ),
        clock=lambda: NOW,
        current_state=_state(request),
    )
    assert receipt.status == "INVALID"
    assert receipt.violations == ("USAGE_MISSING_OR_INVALID",)


def test_global_claim_blocks_replay_after_local_roots_are_removed(tmp_path: Path):
    import shutil

    request, config, attestation, judge = _inputs(tmp_path)
    calls = []
    kwargs = {
        "evidence_bundle_root": tmp_path / "bundle",
        "runner": lambda current, gate: gate.call(current),
        "provider_call": lambda current: calls.append("called") or _provider(current),
        "clock": lambda: NOW,
        "current_state": _state(request),
    }
    first = dispatch_once(request, config, attestation, judge, **kwargs)
    shutil.rmtree(request.journal_root)
    shutil.rmtree(request.evidence_root)
    second = dispatch_once(request, config, attestation, judge, **kwargs)
    assert first.status == "PASS"
    assert second.status == "NOT_EVALUATED"
    assert calls == ["called"]


def test_evidence_root_symlink_swap_is_invalid_and_cannot_escape(tmp_path: Path):
    import shutil

    request, config, attestation, judge = _inputs(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()

    def provider(current):
        shutil.rmtree(current.evidence_root)
        current.evidence_root.symlink_to(outside, target_is_directory=True)
        return _provider(current)

    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=lambda current, gate: gate.call(current),
        provider_call=provider,
        clock=lambda: NOW,
        current_state=_state(request),
    )
    assert receipt.status == "INVALID"
    assert tuple(outside.iterdir()) == ()


def test_journal_signed_path_swap_is_invalid_and_not_durable(tmp_path: Path):
    # Incident 2026-07-03: a runner could hide the journal and still receive PASS.
    request, config, attestation, judge = _inputs(tmp_path)
    moved = tmp_path / "moved-journal"
    replacement = tmp_path / "replacement-journal"
    replacement.mkdir()

    def provider(current):
        current.journal_root.rename(moved)
        current.journal_root.symlink_to(replacement, target_is_directory=True)
        return _provider(current)

    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=lambda current, gate: gate.call(current),
        provider_call=provider,
        clock=lambda: NOW,
        current_state=_state(request),
    )
    terminal = load_journal_event_v1((moved / "999-terminal.json").read_text())
    assert receipt.status == "INVALID"
    assert receipt.reservation_durable is False
    assert receipt.terminal_durable is False
    assert receipt.violations == (
        "TERMINAL_WRITE_FAILED:RuntimeError:Journal root inode changed",
    )
    assert terminal["status"] == "UNKNOWN"
    assert tuple(replacement.iterdir()) == ()


def test_journal_parent_path_swap_is_invalid_and_not_durable(tmp_path: Path):
    # Incident 2026-07-03: journal durability also depends on its pinned parent.
    signed_parent = tmp_path / "signed-parent"
    request, config, attestation, judge = _inputs(
        tmp_path, journal_parent=signed_parent
    )
    moved_parent = tmp_path / "moved-parent"

    def provider(current):
        signed_parent.rename(moved_parent)
        signed_parent.mkdir()
        (signed_parent / "journal").mkdir()
        return _provider(current)

    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=lambda current, gate: gate.call(current),
        provider_call=provider,
        clock=lambda: NOW,
        current_state=_state(request),
    )
    terminal = load_journal_event_v1(
        (moved_parent / "journal" / "999-terminal.json").read_text()
    )
    assert receipt.status == "INVALID"
    assert receipt.reservation_durable is False
    assert receipt.terminal_durable is False
    assert receipt.violations == (
        "TERMINAL_WRITE_FAILED:RuntimeError:Journal parent inode changed",
    )
    assert terminal["status"] == "UNKNOWN"
    assert tuple(path.name for path in signed_parent.iterdir()) == ("journal",)


def test_strict_wire_rejects_duplicate_receipt_and_event_keys():
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_production_dispatch_receipt_v1('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_journal_event_v1(
            '{"schema_version":1,"event":"RESERVED","event":"TERMINAL"}'
        )


def test_hanging_reservation_is_recovered_as_terminal_unknown(tmp_path: Path):
    import json

    request, config, attestation, judge = _inputs(tmp_path)
    request.journal_root.mkdir()
    (request.journal_root / "000-reserved.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "event": "RESERVED",
                "envelope_hash": request.envelope_hash,
                "spec_hash": request.spec.spec_hash,
                "nonce": request.spec.nonce,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=lambda current, gate: gate.call(current),
        provider_call=lambda current: _provider(current),
        clock=lambda: NOW,
        current_state=_state(request),
    )
    terminal = load_journal_event_v1(
        (request.journal_root / "999-terminal.json").read_text()
    )
    assert receipt.status == "NOT_EVALUATED"
    assert terminal["status"] == "UNKNOWN"
    assert terminal["violations"] == ["RECOVERED_HANGING_CLAIM"]


@pytest.mark.parametrize(
    ("mutation", "replacement_key", "expected_violations"),
    (
        (
            "spend-material",
            SPEND.raw,
            ("PROVIDER_RECEIPT_KEY_CHANGED", "PROVIDER_RESERVATION_INVALID"),
        ),
        (
            "judge-material",
            JUDGE.raw,
            ("PROVIDER_RECEIPT_KEY_CHANGED", "PROVIDER_RESERVATION_INVALID"),
        ),
        ("renamed-path", b"p" * 32, ("PROVIDER_RECEIPT_KEY_CHANGED",)),
        ("symlink-path", b"p" * 32, ("PROVIDER_RECEIPT_KEY_CHANGED",)),
    ),
)
def test_provider_key_callback_mutation_is_invalid(
    tmp_path: Path,
    mutation: str,
    replacement_key: bytes,
    expected_violations: tuple[str, ...],
):
    # Incident NO1-003D zero2: callbacks must not replace their receipt verifier.
    request, config, attestation, judge = _inputs(tmp_path)
    provider_path = config.pinned_provider_receipt_key
    assert provider_path is not None

    def provider(current):
        if mutation in ("spend-material", "judge-material"):
            provider_path.write_text(replacement_key.hex())
        elif mutation == "renamed-path":
            provider_path.rename(provider_path.with_suffix(".original"))
            provider_path.write_text(replacement_key.hex())
        else:
            provider_path.rename(provider_path.with_suffix(".original"))
            replacement = provider_path.with_suffix(".replacement")
            replacement.write_text(replacement_key.hex())
            provider_path.symlink_to(replacement)
        return _result(
            provider_reservation_receipt=issue_provider_reservation_receipt(
                current.spec, "provider-reservation-1", replacement_key
            )
        )

    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=lambda current, gate: gate.call(current),
        provider_call=provider,
        clock=lambda: NOW,
        current_state=_state(request),
    )
    assert receipt.status == "INVALID"
    assert receipt.violations == expected_violations
    assert receipt.model_callbacks_invoked == 1


def test_provider_key_mutation_immediately_before_callback_blocks_callback(
    tmp_path: Path,
):
    # Incident NO1-003D zero2: the gate must re-read the key before callback entry.
    request, config, attestation, judge = _inputs(tmp_path)
    provider_path = config.pinned_provider_receipt_key
    assert provider_path is not None
    provider_calls = []

    def runner(current, gate):
        provider_path.write_text(SPEND.raw.hex())
        return gate.call(current)

    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=runner,
        provider_call=lambda current: (
            provider_calls.append(current) or _provider(current)
        ),
        clock=lambda: NOW,
        current_state=_state(request),
    )
    assert receipt.status == "INVALID"
    assert receipt.violations == (
        "PROVIDER_EXCEPTION:RuntimeError:provider receipt key changed before callback",
        "PROVIDER_RECEIPT_KEY_CHANGED",
    )
    assert receipt.model_callbacks_invoked == 0
    assert provider_calls == []


def test_provider_key_mutation_after_gate_return_is_invalid(tmp_path: Path):
    # Incident NO1-003D zero3: runner code executes after the provider gate returns.
    request, config, attestation, judge = _inputs(tmp_path)
    provider_path = config.pinned_provider_receipt_key
    assert provider_path is not None

    def runner(current, gate):
        result = gate.call(current)
        provider_path.write_text(SPEND.raw.hex())
        return result

    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=runner,
        provider_call=lambda current: _provider(current),
        clock=lambda: NOW,
        current_state=_state(request),
    )
    assert receipt.status == "INVALID"
    assert receipt.violations == ("PROVIDER_RECEIPT_KEY_CHANGED",)
    assert receipt.model_callbacks_invoked == 1


def test_same_signed_ledger_path_recreated_is_rejected(tmp_path: Path):
    # Incident NO1-003D zero3: a path string is not a persistent ledger identity.
    import shutil

    request, config, attestation, judge = _inputs(tmp_path)
    first = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=lambda current, gate: gate.call(current),
        provider_call=lambda current: _provider(current),
        clock=lambda: NOW,
        current_state=_state(request),
    )
    shutil.rmtree(request.journal_root)
    shutil.rmtree(request.evidence_root)
    moved = config.global_nonce_ledger_root.with_name("old-ledger")
    config.global_nonce_ledger_root.rename(moved)
    config.global_nonce_ledger_root.mkdir()
    callbacks = []
    second = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=lambda current, gate: gate.call(current),
        provider_call=lambda current: callbacks.append(current) or _provider(current),
        clock=lambda: NOW,
        current_state=_state(request),
    )
    assert first.status == "PASS"
    assert second.status == "INVALID"
    assert second.model_callbacks_invoked == 0
    assert callbacks == []
    assert second.violations[0].startswith(
        "RESERVATION_DURABILITY_UNKNOWN:RuntimeError:"
    )


@pytest.mark.parametrize("bad_reservation_id", [None, True, 7, "", "../x"])
def test_provider_receipt_rejects_noncanonical_reservation_identity(
    tmp_path: Path, bad_reservation_id: object
):
    # Incident NO1-003D zero3: signed malformed receipt identities remain malformed.
    request, config, attestation, judge = _inputs(tmp_path)
    valid = issue_provider_reservation_receipt(
        request.spec, "provider-reservation-1", b"p" * 32
    )
    malformed = replace(valid, reservation_id=bad_reservation_id)
    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=lambda current, gate: gate.call(current),
        provider_call=lambda current: _result(provider_reservation_receipt=malformed),
        clock=lambda: NOW,
        current_state=_state(request),
    )
    assert receipt.status == "INVALID"
    assert receipt.violations == ("PROVIDER_RESERVATION_INVALID",)


def test_wire_loaders_reject_noncanonical_and_invalid_invariants(tmp_path: Path):
    # Incident NO1-003D zero3: parsed equivalence is weaker than canonical bytes.
    import json

    request, config, attestation, judge = _inputs(tmp_path)
    receipt = dispatch_once(
        request,
        config,
        attestation,
        judge,
        evidence_bundle_root=tmp_path / "bundle",
        runner=lambda current, gate: gate.call(current),
        provider_call=lambda current: _provider(current),
        clock=lambda: NOW,
        current_state=_state(request),
    )
    with pytest.raises(ValueError, match="not canonical"):
        load_production_dispatch_receipt_v1(" " + receipt.to_json())
    bad = receipt.to_wire_dict()
    bad["model_callbacks_invoked"] = 2
    with pytest.raises(ValueError, match="exact integer 0 or 1"):
        load_production_dispatch_receipt_v1(
            json.dumps(bad, sort_keys=True, separators=(",", ":"))
        )
    bad = receipt.to_wire_dict()
    bad["reservation_durable"] = False
    with pytest.raises(ValueError, match="PASS receipt"):
        load_production_dispatch_receipt_v1(
            json.dumps(bad, sort_keys=True, separators=(",", ":"))
        )
    event = {
        "schema_version": 1,
        "event": "RESERVED",
        "envelope_hash": "a" * 64,
        "spec_hash": 7,
        "nonce": None,
    }
    with pytest.raises(ValueError, match="reservation event identity invalid"):
        load_journal_event_v1(json.dumps(event, sort_keys=True, separators=(",", ":")))
