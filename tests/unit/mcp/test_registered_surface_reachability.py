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

import ast
import importlib
import inspect
import pkgutil
from pathlib import Path

from tree_sitter_analyzer.mcp.tool_dispositions import (
    TOOL_DISPOSITIONS,
    Disposition,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]

TOOLS_PACKAGE_DIR = PROJECT_ROOT / "tree_sitter_analyzer" / "mcp" / "tools"

#: §3.1 测得且在 v2 删除到期弃用项后仍应出现在枚举中的工具类。
_MEASURED_ORPHANS = (
    "CodeGraphPRReviewTool",
    "CodeGraphRefactorTool",
    "GetProjectSummaryTool",
    "MiddlewareDetectorTool",
    "UnreachableCodeTool",
)

#: Classes the registry itself instantiates.  Pinned exactly, so an empty or
#: partial registry walk fails here rather than reporting every tool as an
#: orphan below.
_REGISTERED_TOOL_CLASSES = frozenset({"FacadeTool", "_StrictEditFacade"})


def _tool_module_names() -> set[str]:
    """Qualified names of the modules this gate imports, and only those."""
    import tree_sitter_analyzer.mcp.tools as tools_pkg

    return {
        f"{tools_pkg.__name__}.{module.name}"
        for module in pkgutil.iter_modules(tools_pkg.__path__)
    }


def _tool_classes() -> dict[str, type]:
    """Every ``BaseMCPTool`` subclass a tool module declares, by class name.

    Scoped to module-level classes the tool modules define.  Two things are
    excluded, both for the same reason — they make the enumeration depend on
    what else the process has already done rather than on the product:

    * test doubles (``_FakeInner``, ``_StubTool``, the probes in
      ``test_facade_tool``).  ``BaseMCPTool.__subclasses__()`` is process-wide,
      so an unfiltered walk collects them as soon as their test module is
      imported; the same tree yielded 87 classes in isolation and 98 under a
      full parallel run.
    * classes a factory creates on first call, such as ``_PRReviewViaFacade``.
      They are real product classes, but they exist only once something has
      asked for them, so the count would depend on test order.  The registry
      tests cover those routes; this gate covers the declared surface.

    Import failures are collected rather than swallowed: a module that cannot be
    imported is not evidence that its tools are fine, and skipping it would let
    an orphan hide behind an unrelated breakage.
    """
    imported = _tool_module_names()
    from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool

    failures: list[str] = []
    for qualified in sorted(imported):
        try:
            importlib.import_module(qualified)
        except Exception as exc:  # noqa: BLE001 — reported, never swallowed
            failures.append(f"{qualified}: {type(exc).__name__}: {exc}")
    assert failures == [], f"tool modules failed to import: {failures}"

    found: dict[str, type] = {}

    def walk(cls: type) -> None:
        for subclass in cls.__subclasses__():
            if subclass.__module__ in imported and (
                subclass.__qualname__ == subclass.__name__
            ):
                found[subclass.__name__] = subclass
            walk(subclass)

    walk(BaseMCPTool)
    return found


def _declared_tool_class_names() -> set[str]:
    """Tool classes the tool modules declare at module level, read statically.

    The import walk above must agree with this exactly.  It is the same
    question — which classes exist — answered from the source instead of from
    whatever happened to be imported, so agreement proves the walk is complete
    and that nothing outside the tool modules leaked into it.  Classes defined
    inside a factory are excluded: they do not exist until the factory runs.
    """
    bases: dict[str, set[str]] = {}
    for path in sorted(TOOLS_PACKAGE_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                bases[node.name] = {
                    base.id for base in node.bases if isinstance(base, ast.Name)
                }

    declared = {name for name, base in bases.items() if "BaseMCPTool" in base}
    while True:
        derived = {
            name
            for name, base in bases.items()
            if name not in declared and base & declared
        }
        if not derived:
            return declared
        declared |= derived


def _reachable_class_names(project_root: str) -> tuple[set[str], set[str]]:
    """Reachable class names from the live registry, and its own tool classes.

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
    registered: set[str] = set()
    for _name, tool in tools:
        registered.add(type(tool).__name__)
        inners = [tool]
        inners.extend(getattr(tool, "action_map", {}).values())
        inners.extend(getattr(tool, "_bespoke_inners", []))
        for inner in inners:
            reachable.update(base.__name__ for base in type(inner).__mro__)
    return reachable, registered


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
    """The walk must find the whole declared surface, and nothing else.

    Set equality against the source rather than a size bound: a bound wide
    enough to absorb the process-wide subclass tree also absorbs a walk that
    imported a quarter of the modules, and it cannot see a stray test double.
    """
    classes = _tool_classes()

    declared = _declared_tool_class_names()
    assert set(classes) == declared, (
        "the import walk and the tool modules disagree about which tool classes "
        f"exist. Only in the source: {sorted(declared - set(classes))}. Only in "
        f"the walk: {sorted(set(classes) - declared)}. A name the walk cannot "
        "see is either a module that failed to import or a class that does not "
        "exist; a name the source does not declare is a leak into the walk."
    )
    missing = [name for name in _MEASURED_ORPHANS if name not in classes]
    assert missing == [], (
        f"the enumeration no longer sees {missing}; §3.1's measured surface "
        "cannot be verified from it"
    )
    # The registry walk must find a live surface, or every "unreachable" verdict
    # below is an artefact of an empty walk.
    reachable, registered = _reachable_class_names(str(PROJECT_ROOT))
    assert registered == _REGISTERED_TOOL_CLASSES, (
        f"the registry exposed {sorted(registered)}, not the pinned public "
        "surface; update the pin deliberately if the facade set changed"
    )
    assert registered <= reachable, (
        f"the registry walk did not reach {sorted(registered - reachable)}; an "
        "empty MRO walk would report every tool as an orphan"
    )


def _offender_reason(
    name: str,
    *,
    exempt: bool,
    reachable: bool,
    disposition: Disposition | None,
) -> str | None:
    """Why ``name`` is an unresolved orphan, or ``None`` when it is not.

    Pure, so §3.1's zero-caller signal can be tested directly for the property it
    must keep: the verdict is a **hard binary**. A genuine orphan is an offender,
    and there is no "unknown" or "indeterminate" outcome that could let this gate
    go green while detecting nothing.

    That matters because of §3.1's exemption from §1's ratchet. The cheapest way
    to maximise §1's ratchet is to answer ``unknown`` whenever a file contains a
    dynamic construct — and dynamic construction is exactly how these subjects
    are built (a facade assembled by a function-local import, an ``importlib``
    import). Under that implementation a genuine orphan would read as
    indeterminate, §3.1 would silently stop detecting anything, and **both gates
    would be green**: a fresh instance of this RFC's own defect shape.
    """
    if exempt or reachable:
        return None
    if disposition is None:
        return f"{name}: built but reachable from nothing, and undispositioned"
    if disposition.kind == "wire":
        return f"{name}: disposition claims wire, but the class is unreachable"
    if disposition.kind == "delete":
        return f"{name}: disposition claims delete, but the class still exists"
    # deprecate is permitted while its removal version has not shipped;
    # test_tool_dispositions.py fails once it has.
    return None


def test_every_tool_class_is_reachable_or_dispositioned() -> None:
    reachable, _registered = _reachable_class_names(str(PROJECT_ROOT))

    offenders: list[str] = []
    for name, cls in sorted(_tool_classes().items()):
        reason = _offender_reason(
            name,
            exempt=_is_exempt(cls),
            reachable=name in reachable,
            disposition=TOOL_DISPOSITIONS.get(name),
        )
        if reason is not None:
            offenders.append(reason)

    assert offenders == [], (
        "RFC-0028 §3.1 registered-surface reachability is red. Every entry needs "
        "a landing disposition — wire it, delete it, or deprecate it with a "
        "named removal version. An allowlist entry is not a disposition:\n  "
        + "\n  ".join(offenders)
    )


def test_the_zero_caller_signal_is_a_hard_binary() -> None:
    """§3.1's exemption from §1's ratchet, asserted.

    A genuine orphan — not exempt, not reachable, undispositioned — must produce
    a verdict. If this ever became an ``unknown``/indeterminate outcome, §3.1
    would stop detecting orphans while staying green, and §1 would have softened
    the very signal §3.1 relies on.
    """
    reason = _offender_reason(
        "SomeNewlyAddedTool", exempt=False, reachable=False, disposition=None
    )
    assert reason is not None, (
        "a genuine orphan produced no verdict; a soft outcome here means the "
        "reachability gate can go green while detecting nothing"
    )
    softened = ("unknown", "indeterminate", "incomplete", "unclear", "partial")
    assert not any(word in reason.lower() for word in softened), (
        f"the verdict borrowed §1's vocabulary ({reason!r}); §3.1's zero must "
        "stay a zero and a completeness field is not a licence to soften it"
    )


def test_the_only_soft_outcome_is_a_live_deprecation() -> None:
    """Pins the two-sided boundary so neither direction can drift.

    Exempting everything would make the gate vacuous; soft-verdicting everything
    would make it useless.
    """
    assert _offender_reason("T", exempt=True, reachable=False, disposition=None) is None
    assert _offender_reason("T", exempt=False, reachable=True, disposition=None) is None
    for kind in ("wire", "delete"):
        disposition = Disposition(kind=kind, reason="x")
        assert (
            _offender_reason(
                "T", exempt=False, reachable=False, disposition=disposition
            )
            is not None
        )
    deprecated = Disposition(kind="deprecate", reason="x", remove_in="99.0.0")
    assert (
        _offender_reason("T", exempt=False, reachable=False, disposition=deprecated)
        is None
    )
