#!/usr/bin/env python3
"""RFC-0022 P0.4 adapter-route strace target (zero-write certification).

A fresh-exec target for the pinned Linux strace authority: it runs the
real Phase-A diff route — the read-existing producer (registry read-only
create, acquire, publish) followed by the diff-snapshot consumers
(``edit.constraints`` NO_CONFIG path, ``edit.ast_diff``, and
``edit.classify``) against a prepared git fixture — and reports a
deterministic JSON summary on stdout. The authority certifies that the
whole process tree (including every git descendant) makes no filesystem
write attempt; ``outcome=clean`` with zero violations is the RFC-0022
P0.4 adapter-route certification.

The target is never an authority itself: it only exercises the exact
route invocation set and prints a deterministic JSON summary.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys


def _produce(root: str) -> tuple[dict[str, object], str]:
    """Run the P0.4 producer route; return (deterministic identity, id)."""
    # Diagnostic: surface the raise-site traceback of capture failures.
    import traceback

    import tree_sitter_analyzer.diff_snapshot_registry as _registry

    _original_snapshot_error = _registry.snapshot_error

    def _snapshot_error_spy(code: str):
        if code == "DIFF_SNAPSHOT_GIT_ERROR":
            traceback.print_exc(file=sys.stderr)
        return _original_snapshot_error(code)

    _registry.snapshot_error = _snapshot_error_spy
    from tree_sitter_analyzer.diff_snapshot_registry import REGISTRY, reset_registry

    reset_registry()
    created = REGISTRY.create(root, "diff", [], readonly=True)
    if not created.get("success"):
        return {"error": created.get("error_code", "CAPTURE_ERROR")}, ""
    consumer, error = REGISTRY.acquire(str(created["diff_snapshot_id"]), root)
    if error is not None or consumer is None:
        return {"error": error or "ACQUIRE_ERROR"}, ""
    try:
        publish_error = REGISTRY.validate_publish(consumer)
        if publish_error is not None:
            return ({"error": publish_error},)
        # The snapshot id is a per-run secret token; only deterministic
        # fields may appear in the pinned summary.
        identity = {
            "source_generation": consumer.snapshot.source_generation,
            "records": len(consumer.snapshot.files),
            "patch_size": len(consumer.snapshot.normalized_patch),
            "scope": [
                path
                for path in consumer.snapshot.assessed_scope_paths
                if path in ("base.py", "new.py")
            ],
        }
        return identity, consumer.snapshot.snapshot_id
    finally:
        consumer.release()


async def _consume(root: str, snapshot_id: str) -> dict[str, object]:
    """Run the three diff-snapshot consumers against the produced snapshot."""
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(root)
    scope = ["base.py", "new.py"]
    consumers: dict[str, object] = {}
    for action, arguments in (
        (
            "constraints",
            {
                "diff_snapshot_id": snapshot_id,
                "scope_paths": scope,
                "persist": False,
                "access_mode": "read_existing",
                "output_format": "json",
            },
        ),
        (
            "ast_diff",
            {
                "diff_snapshot_id": snapshot_id,
                "file_path": "base.py",
                "access_mode": "read_existing",
                "output_format": "json",
            },
        ),
        (
            "classify",
            {
                "diff_snapshot_id": snapshot_id,
                "file_path": "base.py",
                "access_mode": "read_existing",
                "output_format": "json",
            },
        ),
    ):
        result = await facade.execute({"action": action, **arguments})
        consumers[action] = {
            "success": bool(result.get("success")),
            "access_state": result.get("access_state"),
        }
    return consumers


def main(argv: list[str] | None = None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args(argv)
    identity, snapshot_id = _produce(args.root)
    if "error" in identity:
        print(json.dumps(identity))
        return 1
    consumers = asyncio.run(_consume(args.root, snapshot_id))
    payload = {**identity, "consumers": consumers}
    if any(not item.get("success") for item in consumers.values()):
        print(json.dumps(payload))
        return 1
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
