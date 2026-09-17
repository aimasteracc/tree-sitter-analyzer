#!/usr/bin/env python3
"""RFC-0028 §3.1 的孤立工具处置登记。

每个不可达工具只能选择接线、删除或带明确到期版本的弃用。这里保存已经落地的
处置记录；实时可达性由独立契约验证。抽象类依靠结构特征豁免，不能通过名称白名单
绕过检查。弃用到期后，:func:`expired_dispositions` 必须使契约失败，直到对应代码被
真正接线或删除。
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


#: RFC-0028 §3.1 测得且仍需保留审计记录的工具类处置。
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
            "PLAN_RENAME_IS_PREVIEW_ONLY, never forwarded. v1.29.5 additionally "
            "publishes edit action=rename / --rename for explicit preview or apply."
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
    # ---- 已接入健康门面的工具 ------------------------------------------
    "UnreachableCodeTool": Disposition(
        kind="wire",
        reason=(
            "Published in v1.29.5 as health action=unreachable / --unreachable-code. "
            "This analyzes unreachable statements inside functions, not external "
            "callers or function-level dead-code reachability. The old deprecation "
            "rationale incorrectly attributed dead_code_analyzer limitations to it."
        ),
    ),
    "MiddlewareDetectorTool": Disposition(
        kind="wire",
        reason=(
            "Published in v1.29.5 as health action=middleware / --detect-middleware. "
            "Complements route discovery with middleware/interceptor chains; "
            "RFC-0027/0028 release integration records the existing public routes."
        ),
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
