import shutil
import tempfile
import threading
from dataclasses import replace
from pathlib import Path

import benchmarks.codegraph_compare.production_dispatch as pd
from benchmarks.codegraph_compare.production_dispatch import (
    dispatch_once,
)
from benchmarks.codegraph_compare.production_judge import submit_verdict

ns = {}
exec(Path("tests/unit/test_production_dispatch.py").read_text(), ns)
_inputs = ns["_inputs"]
_state = ns["_state"]
_provider = ns["_provider"]
NOW = ns["NOW"]
SPEND = ns["SPEND"]


def run(req, cfg, att, jdg, provider=None):
    calls = []

    def call(current):
        calls.append(1)
        return (provider or _provider)(current)

    receipt = dispatch_once(
        req,
        cfg,
        att,
        jdg,
        evidence_bundle_root=req.journal_root.parent / "bundle",
        runner=lambda current, gate: gate.call(current),
        provider_call=call,
        clock=lambda: NOW,
        current_state=_state(req),
    )
    return receipt, calls


# same-root race
root = Path(tempfile.mkdtemp()).resolve()
req, cfg, att, jdg = _inputs(root)
barrier = threading.Barrier(2)
got = []


def worker():
    barrier.wait()
    got.append(run(req, cfg, att, jdg))


ts = [threading.Thread(target=worker) for _ in range(2)]
[x.start() for x in ts]
[x.join() for x in ts]
print(
    "same_root_concurrency",
    sorted((r.status, r.model_callbacks_invoked) for r, _ in got),
    "calls",
    sum(len(c) for _, c in got),
)
# signed roots reject fresh substitution
root = Path(tempfile.mkdtemp()).resolve()
req, cfg, att, jdg = _inputs(root)
r1, c1 = run(req, cfg, att, jdg)
req2 = replace(req, journal_root=root / "journal2", evidence_root=root / "evidence2")
cfg2 = replace(
    cfg,
    immutable_journal_root=req2.journal_root,
    immutable_artifact_root=req2.evidence_root,
)
r2, c2 = run(req2, cfg2, att, jdg)
print(
    "fresh_root_replay",
    r1.status,
    r2.status,
    "callbacks",
    len(c1) + len(c2),
    r2.violations,
)
# identical role material
root = Path(tempfile.mkdtemp()).resolve()
req, cfg, att, _ = _inputs(root)
cfg.pinned_judge.write_text(SPEND.raw.hex())
judge = submit_verdict(
    "ACCEPT",
    req.qualification_evidence_digest,
    req.spec.spec_hash,
    SPEND,
    now_unix=NOW,
    key_id=cfg.judge_key_id,
)
r, c = run(req, cfg, att, judge)
print("same_key_material", r.status, r.violations, "callbacks", len(c))
# exact ints
root = Path(tempfile.mkdtemp()).resolve()
req, cfg, att, jdg = _inputs(root)
r, c = run(
    req,
    cfg,
    att,
    jdg,
    lambda current: _provider(
        current, provider_request_count=True, input_tokens=1.5, output_tokens=2.5
    ),
)
print("bool_float", r.status, r.violations)
# symlink swap
root = Path(tempfile.mkdtemp()).resolve()
req, cfg, att, jdg = _inputs(root)
outside = root / "outside"
outside.mkdir()


def swap(current):
    shutil.rmtree(current.evidence_root)
    current.evidence_root.symlink_to(outside, target_is_directory=True)
    return _provider(current)


r, c = run(req, cfg, att, jdg, swap)
print("symlink_swap", r.status, "outside", list(outside.rglob("*")), r.violations)
# partial reservation fsync uncertainty terminalizes UNKNOWN

root = Path(tempfile.mkdtemp()).resolve()
req, cfg, att, jdg = _inputs(root)
orig = pd._Journal.write


def partial(self, name, value):
    if name == "000-reserved.json":
        fd = __import__("os").open(
            name,
            __import__("os").O_WRONLY
            | __import__("os").O_CREAT
            | __import__("os").O_EXCL,
            0o400,
            dir_fd=self.fd,
        )
        __import__("os").close(fd)
        raise OSError("simulated fsync-after-visible")
    return orig(self, name, value)


pd._Journal.write = partial
try:
    r, c = run(req, cfg, att, jdg)
finally:
    pd._Journal.write = orig
print(
    "partial_reservation",
    r.status,
    r.reservation_durable,
    r.terminal_durable,
    (req.journal_root / "999-terminal.json").exists(),
    r.violations,
)

# same signed ledger path cannot be replayed after rename/recreate
root = Path(tempfile.mkdtemp()).resolve()
req, cfg, att, jdg = _inputs(root)
r1, c1 = run(req, cfg, att, jdg)
shutil.rmtree(req.journal_root)
shutil.rmtree(req.evidence_root)
cfg.global_nonce_ledger_root.rename(root / "old-global-ledger")
cfg.global_nonce_ledger_root.mkdir()
r2, c2 = run(req, cfg, att, jdg)
print(
    "same_signed_ledger_recreate",
    r1.status,
    r2.status,
    "callbacks",
    len(c1) + len(c2),
    r2.violations,
)

# runner cannot swap the provider key after gate.call returns
root = Path(tempfile.mkdtemp()).resolve()
req, cfg, att, jdg = _inputs(root)
provider_path = cfg.pinned_provider_receipt_key
assert provider_path is not None
calls = []


def post_gate_runner(current, gate):
    result = gate.call(current)
    provider_path.write_text(SPEND.raw.hex())
    return result


r = dispatch_once(
    req,
    cfg,
    att,
    jdg,
    evidence_bundle_root=root / "bundle",
    runner=post_gate_runner,
    provider_call=lambda current: calls.append(1) or _provider(current),
    clock=lambda: NOW,
    current_state=_state(req),
)
print("provider_after_gate_swap", r.status, r.violations, "callbacks", len(calls))
