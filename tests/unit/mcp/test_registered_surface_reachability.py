#!/usr/bin/env python3
"""RFC-0028 §3.1 — every tool class is reachable, or has a landing disposition.

The disposition registry (``mcp/tool_dispositions.py``) resolved the six orphans
measured on 2026-08-19, and ``test_tool_dispositions.py`` verifies those six
claims.  Neither catches a **seventh**: a tool class added later that is built,
tested, and registered nowhere has no disposition to check and no test that
notices.  This file closes that gap by enumerating every class rather than
consulting a list of names — the same defect #2 the RFC describes, where a test
pinned the orphan state as expected.

An allowlist is deliberately not an available answer.  A class is exempt only
structurally — ``abc``-abstract, or no concrete ``execute`` — and an unreachable
class must carry a disposition that has actually landed:

* ``wire``      — the route itself is the proof, so an unreachable ``wire`` fails;
* ``delete``    — the class was to be removed, so a surviving ``delete`` fails;
* ``deprecate`` — permitted only until its named removal version ships, which
  ``test_tool_dispositions.py`` already fails on.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from pathlib import Path

from tree_sitter_analyzer.mcp.tool_dispositions import TOOL_DISPOSITIONS

PROJECT_ROOT = Path(__file__).resolve().parents[3]

#: The six names §3.1 measured.  They are asserted to be *in the enumeration*
#: below, so a broken walk cannot make this gate vacuously green.
_MEASURED_ORPHANS = (
    "CodeGraphPRReviewTool",
    "CodeGraphRefactorTool",
    "GetProjectSummaryTool",
    "MiddlewareDetectorTool",
    "UniversalAnalyzeTool",
    "UnreachableCodeTool",
)


def _tool_classes() -> dict[str, type]:
    """Every importable ``BaseMCPTool`` subclass, keyed by class name.

    Import failures are collected rather than swallowed: a module that cannot be
    imported is not evidence that its tools are fine, and skipping it would let
    an orphan hide behind an unrelated breakage.
    """
    import tree_sitter_analyzer.mcp.tools as tools_pkg
    from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool

    failures: list[str] = []
    for module in pkgutil.iter_modules(tools_pkg.__path__):
        qualified = f"{tools_pkg.__name__}.{module.name}"
        try:
            importlib.import_module(qualified)
        except Exception as exc:  # noqa: BLE001 — reported, never swallowed
            failures.append(f"{qualified}: {type(exc).__name__}: {exc}")
    assert failures == [], f"tool modules failed to import: {failures}"

    found: dict[str, type] = {}

    def walk(cls: type) -> None:
        for subclass in cls.__subclasses__():
            if subclass.__name__ in found:
                continue
            found[subclass.__name__] = subclass
            walk(subclass)

    walk(BaseMCPTool)
    return found


def _reachable_class_names(project_root: str) -> set[str]:
    """Class names reachable from the live registry, by MRO.

    Reachability counts a registered *subclass*: ``edit action=pr`` holds a
    ``_PRReviewViaFacade`` instance, not a ``CodeGraphPRReviewTool`` one, so a
    gate comparing class identity reports a wired route as an orphan forever.

    Bespoke routes are included as well as ``action_map`` ones. ``nav
    action=callers`` is a closure rather than a map entry, so a walk that stops
    at ``action_map`` reports a live route as an orphan — which is why the
    disposition test's version, scoped to the six names it checks, cannot be
    reused unsized here.
    """
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    tools, _lookup = create_tool_registry(project_root)
    reachable: set[str] = set()
    for _name, tool in tools:
        inners = [tool]
        inners.extend(getattr(tool, "action_map", {}).values())
        inners.extend(getattr(tool, "_bespoke_inners", []))
        for inner in inners:
            reachable.update(base.__name__ for base in type(inner).__mro__)
    return reachable


def _is_exempt(cls: type) -> bool:
    """Structural exemption: ``abc``-abstract, or no concrete ``execute``.

    Deliberately not a list of three names.  Naming the abstract bases is the
    allowlist pattern under another label, and it would silently stop exempting
    the next base class someone adds.
    """
    if inspect.isabstract(cls):
        return True
    execute = getattr(cls, "execute", None)
    return execute is None or getattr(execute, "__isabstractmethod__", False)


def test_the_gate_enumerates_a_non_trivial_surface() -> None:
    """A walk that found nothing would make every assertion below vacuous."""
    classes = _tool_classes()

    assert len(classes) > 20, (
        f"only {len(classes)} tool classes enumerated; the walk is probably "
        "importing nothing and the reachability gate below means nothing"
    )
    missing = [name for name in _MEASURED_ORPHANS if name not in classes]
    assert missing == [], (
        f"the enumeration no longer sees {missing}; §3.1's measured surface "
        "cannot be verified from it"
    )
    # The registry walk must find a live surface, or every "unreachable" verdict
    # below is an artefact of an empty walk.
    reachable = _reachable_class_names(str(PROJECT_ROOT))
    assert len(reachable) > 20, (
        f"the registry walk found only {len(reachable)} reachable class names; "
        "an empty walk would report every tool as an orphan"
    )


def test_every_tool_class_is_reachable_or_dispositioned() -> None:
    reachable = _reachable_class_names(str(PROJECT_ROOT))

    offenders: list[str] = []
    for name, cls in sorted(_tool_classes().items()):
        if _is_exempt(cls) or name in reachable:
            continue
        disposition = TOOL_DISPOSITIONS.get(name)
        if disposition is None:
            offenders.append(
                f"{name}: built but reachable from nothing, and undispositioned"
            )
        elif disposition.kind == "wire":
            offenders.append(
                f"{name}: disposition claims wire, but the class is unreachable"
            )
        elif disposition.kind == "delete":
            offenders.append(
                f"{name}: disposition claims delete, but the class still exists"
            )
        # deprecate is permitted while its removal version has not shipped;
        # test_tool_dispositions.py fails once it has.

    assert offenders == [], (
        "RFC-0028 §3.1 registered-surface reachability is red. Every entry needs "
        "a landing disposition — wire it, delete it, or deprecate it with a "
        "named removal version. An allowlist entry is not a disposition:\n  "
        + "\n  ".join(offenders)
    )
