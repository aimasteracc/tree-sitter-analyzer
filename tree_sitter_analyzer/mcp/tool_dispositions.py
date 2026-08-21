#!/usr/bin/env python3
"""Orphan dispositions — RFC-0028 §3.1's mandatory disposition rule.

§3.1 measured six concrete ``BaseMCPTool`` subclasses reachable from nothing and
then made a prediction about the implementer: *"an implementer facing six red
rows will add an allowlist of six entries, tick the box, and thereby manufacture
a new pinned-orphan-state test — the exact anti-pattern this item exists to
kill."* So every orphan resolves into exactly one of three dispositions, and
**an allowlist entry is not one of them**:

``wire``
    Register it in the facade it belongs to. Recorded here for the audit trail;
    the route itself is the proof.
``delete``
    No consumer, no plan — remove the tool and its tests.
``deprecate``
    Keep it, mark it deprecated with a **named removal version**, and let the
    invariant **fail once that version ships**. That last clause is what makes
    this different from an allowlist: :func:`expired_dispositions` turns the
    deadline into a test failure, so a deprecation cannot quietly become
    permanent.

This module is data plus one predicate. RFC-0028's reachability gate itself is
deliberately NOT implemented here — it belongs to RFC-0028's own
implementation, and would fail on merge by design until every disposition has
landed. Dispositions first, gate second.

Abstract bases (``FacadeTool``, ``MCPTool``, ``_CallTreeBase``) are absent on
purpose: their exemption is **structural** — a class is exempt iff it is
``abc``-abstract or has no concrete ``execute`` — and naming them here would be
the allowlist pattern again.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DispositionKind = Literal["wire", "delete", "deprecate"]


@dataclass(frozen=True)
class Disposition:
    """What was decided about one unreachable tool class, and why."""

    kind: DispositionKind
    reason: str
    #: Required for ``deprecate``, forbidden otherwise. When the running
    #: version reaches this, the deprecation has expired and must be resolved.
    remove_in: str | None = None

    def __post_init__(self) -> None:
        if self.kind == "deprecate" and not self.remove_in:
            raise ValueError("a deprecate disposition requires remove_in")
        if self.kind != "deprecate" and self.remove_in:
            raise ValueError(f"remove_in applies only to deprecate, not {self.kind}")


#: ``{class_name: Disposition}`` for every tool class RFC-0028 §3.1 measured as
#: unreachable on 2026-08-19, plus the one the measurement got wrong.
TOOL_DISPOSITIONS: dict[str, Disposition] = {
    # ---- wired by this change (RFC-0027 §L7/§L8) -------------------------
    "GetProjectSummaryTool": Disposition(
        kind="wire",
        reason=(
            "The project card — purpose, top languages, entry points, module "
            "descriptions. Wired as project action=card / --project-card. Its "
            "v1.x name get_project_summary is back in LEGACY_TOOL_MAP, which "
            "also repairs build_project_index's dead next_step."
        ),
    ),
    "CodeGraphRefactorTool": Disposition(
        kind="wire",
        reason=(
            "A true minimal rename edit set with 15 passing tests and no "
            "surface. Wired as edit action=plan_rename / --plan-rename, pinned "
            "to preview: apply-like arguments are rejected with "
            "PLAN_RENAME_IS_PREVIEW_ONLY, never forwarded."
        ),
    ),
    # ---- already reachable; the audit measured a subclass, not the class --
    "CodeGraphPRReviewTool": Disposition(
        kind="wire",
        reason=(
            "NOT an orphan. Reachable as edit action=pr via the "
            "_PRReviewViaFacade subclass in edit_facade.py, and present in "
            "LEGACY_TOOL_MAP as codegraph_pr_review with the --pr-review CLI "
            "flag. §3.1's measurement counted class identity, so a facade that "
            "registers a *subclass* reads as unregistered. RFC-0028's gate must "
            "treat a class as reachable when it or any subclass is registered, "
            "or it will report this false positive forever."
        ),
    ),
    # ---- deprecate with an expiry ----------------------------------------
    "UnreachableCodeTool": Disposition(
        kind="deprecate",
        reason=(
            "Deliberately NOT wired. Statement-level unreachable-code "
            "detection overlaps health action=dead, and the analyzer it sits "
            "on documents an 'external callers' safeguard at "
            "dead_code_analyzer.py:172 that is not implemented — so any "
            "library public API called only from outside the tree is reported "
            "dead. Registering it would put a known false-positive generator "
            "on the agent-facing surface under an authoritative label. Wire it "
            "only after the safeguard lands; delete it if the safeguard is "
            "abandoned."
        ),
        remove_in="1.33.0",
    ),
    "MiddlewareDetectorTool": Disposition(
        kind="deprecate",
        reason=(
            "Wiring is real work, not this PR's. detect_middleware genuinely "
            "complements health action=routes, but RFC-0027's Three-Surface "
            "table has no row for it, so registering it would add an "
            "unspecified MCP action plus a CLI twin without an RFC — which the "
            "RFC process requires for any facade-or-tool addition. Deprecated "
            "with an expiry so the deadline forces a decision instead of "
            "letting it sit."
        ),
        remove_in="1.33.0",
    ),
    "UniversalAnalyzeTool": Disposition(
        kind="deprecate",
        reason=(
            "Superseded. It duplicates AnalyzeCodeStructureTool (structure "
            "action=analyze) down to sharing "
            "analyze_code_structure_helpers.convert_analysis_result_to_"
            "structure_dict, and is instantiated on the server object without "
            "ever being listed as a tool. Delete is the right end state, but "
            "it still has live consumers in tests/unit/security/"
            "test_security_integration.py and examples/"
            "security_integration_demo.py, so removing it is its own change."
        ),
        remove_in="1.33.0",
    ),
}


def _version_tuple(version: str) -> tuple[int, ...]:
    """Parse ``"1.30.0"`` into ``(1, 30, 0)``, ignoring any suffix."""
    head = version.split("+", 1)[0].split("-", 1)[0]
    parts: list[int] = []
    for chunk in head.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def expired_dispositions(current_version: str) -> list[str]:
    """Return the class names whose deprecation deadline has arrived.

    This is the clause that stops a deprecation from becoming a permanent
    allowlist entry: once ``current_version >= remove_in``, the name is
    returned and the test asserting an empty result goes red.
    """
    current = _version_tuple(current_version)
    return sorted(
        name
        for name, disposition in TOOL_DISPOSITIONS.items()
        if disposition.kind == "deprecate"
        and disposition.remove_in is not None
        and current >= _version_tuple(disposition.remove_in)
    )
