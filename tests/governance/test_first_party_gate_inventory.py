#!/usr/bin/env python3
"""RFC-0028 §3.2 — the first-party gate inventory, derived from the live config.

§3.2 scopes itself "precisely, because 'every blocking gate' is unimplementable":
third-party hooks are out of scope because a pinned `rev` bump is their review
surface, and the first-party local hooks are in scope. That scope is a claim
about `.pre-commit-config.yaml`, so it is checked against that file rather than
restated — and checked against the RFC's own table, so the spec cannot drift from
the configuration it describes.

Writing this immediately found such a drift: **the RFC names six local hooks and
the configuration declares seven.** The unnamed one, `test-encoding-ratchet`, is
itself a ratchet — the same class as `weak-assertion-ratchet`, whose dead-detector
defect §3.2 records as #1.

A hook whose `entry` points at a script that does not exist is a gate that cannot
gate, so each entry's target is asserted to resolve.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / ".pre-commit-config.yaml"
RFC_PATH = PROJECT_ROOT / "rfcs" / "0028-measuring-claimed-properties.md"

#: A path-shaped token in a hook entry: the thing the hook actually runs.
_ENTRY_TARGET = re.compile(r"\S+\.(?:py|sh)\b")


def _local_hooks() -> dict[str, str]:
    """``{hook_id: entry}`` for every first-party (``repo: local``) hook."""
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    hooks: dict[str, str] = {}
    for repo in config.get("repos", []):
        if repo.get("repo") != "local":
            continue
        for hook in repo.get("hooks", []):
            hooks[str(hook["id"])] = str(hook.get("entry", ""))
    return hooks


def _rfc_scoped_hooks() -> set[str]:
    """Hook names the RFC's §3.2 scope table claims are in scope."""
    text = RFC_PATH.read_text(encoding="utf-8")
    section = text.split("§3.2 therefore scopes to the", 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"\|\s*`([a-z0-9-]+)`\s*\|", section))


def test_the_inventory_is_not_vacuous() -> None:
    hooks = _local_hooks()
    assert len(hooks) >= 6, (
        f"only {len(hooks)} local hooks found in {CONFIG_PATH.name}; the parse or "
        "the configuration changed shape and the assertions below mean nothing"
    )
    assert _rfc_scoped_hooks(), (
        "no hook names parsed out of the RFC section; the table format changed "
        "and the drift check below is vacuous"
    )


def test_every_local_hook_runs_something_that_exists() -> None:
    """A hook whose entry resolves to nothing is a gate that cannot gate."""
    missing: list[str] = []
    for hook_id, entry in sorted(_local_hooks().items()):
        match = _ENTRY_TARGET.search(entry)
        assert match is not None, (
            f"{hook_id}: entry {entry!r} names no .py/.sh target, so this test "
            "cannot verify it runs anything — teach the parser or fix the hook"
        )
        target = PROJECT_ROOT / match.group(0)
        if not target.exists():
            missing.append(f"{hook_id} -> {match.group(0)}")
    assert missing == [], "these first-party hooks run a target that does not exist:\n  " + "\n  ".join(missing)


def test_the_rfc_scope_matches_the_live_configuration() -> None:
    """§3.2's scope is a claim about this file; hold the spec to it.

    This is the assertion that catches a hook added to the configuration without
    a scope decision — and the one that would have caught the seventh hook, which
    went unnamed while §3.2 described its own scope as stated precisely.
    """
    live = set(_local_hooks())
    scoped = _rfc_scoped_hooks()

    assert scoped == live, (
        "RFC-0028 §3.2's scope table and the live pre-commit configuration "
        "disagree. Third-party hooks stay out of scope; a first-party hook does "
        "not, because §3.2's requirements are owed by exactly this set.\n"
        f"  in config but not scoped: {sorted(live - scoped)}\n"
        f"  scoped but not in config: {sorted(scoped - live)}"
    )


def test_every_scoped_gate_names_pre_commit_as_its_enforcement_layer() -> None:
    """§3.2 requires the enforcement layer be named, and measured it is pre-commit.

    CI cannot block a merge here (no `required_status_checks` on `develop`), so a
    gate is enforced by the hook that runs it. Every scoped gate is by definition
    in that file, which is what makes the naming dischargeable at all; this pins
    that the file is still where they live rather than a prose list elsewhere.
    """
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    stages = {
        str(hook["id"]): hook.get("stages")
        for repo in config.get("repos", [])
        if repo.get("repo") == "local"
        for hook in repo.get("hooks", [])
    }
    blocked = [name for name, stage in sorted(stages.items()) if stage and "pre-commit" not in stage]
    assert blocked == [], (
        "these first-party gates do not run at pre-commit, so nothing enforces "
        f"them: {blocked}"
    )
