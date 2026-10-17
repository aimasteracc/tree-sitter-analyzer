"""把持久化的 CALLS 边绑定到内存调用图中的目标函数（#1559 / #1560）。

旧实现按**裸名**重新解析每条缓存边，全局兜底会匹配所有同名函数，于是
``x.publish()`` 同时挂到 ``GenerationStore.publish`` 和 ``IndexSnapshotRegistry.publish``，
``_FIELD_TOP_N.get`` 挂到项目里每一个 ``get``——这些猜测被当作确定的边返回。

本模块的规则（产品承诺：绝不自信地出错，不确定就说不知道）：

1. 边上带有持久化解析（``callee_resolution`` 为 ``project`` / ``local``，且
   ``callee_resolved_file`` 中存在同名函数）时，只绑定到该文件中的目标；同文件
   多个同名候选时用接收者（``callee_full`` 的限定符）收窄；该文件中没有同名
   函数时，沿包再导出与基类找唯一定义（#1578）。
2. 持久化解析为 ``builtin`` / ``stdlib`` / ``external`` 时不是项目函数，不建边。
3. 其余情况沿用本地 / import 两档高置信解析；全局兜底只在**唯一**候选、且调用
   无接收者、接收者为 ``self`` 一类、或接收者正是候选所属类时才绑定。
4. 无法确定的边不建边，候选只作为 ``possible``（供死代码可达性保守使用），
   而完整性由 RFC-0028 的未解析计数如实报告。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .call_graph_self_dispatch import (
    OWN_INSTANCE_QUALIFIERS,
    override_candidates,
    own_class_target,
)
from .callee_resolution import CalleeResolver

if TYPE_CHECKING:
    from .cached_reexport_binding import PackageReexportBinder
    from .call_graph import FunctionRef
    from .call_graph_self_dispatch import SubclassIndex

#: 持久化解析已确定为非项目目标的取值（RFC-0004/0005/0007）。
_NON_PROJECT_RESOLUTIONS = frozenset({"builtin", "stdlib", "external"})
#: 持久化解析已确定为项目内目标的取值。
_PROJECT_RESOLUTIONS = frozenset({"project", "local"})
#: 指向调用者自身实例 / 类的接收者：唯一的全局候选（如 mixin 方法）可以绑定。
_SELF_QUALIFIERS = frozenset({"self", "cls", "this", "super", "super()"})
#: ``super`` 接收者：指向基类，而不是外围类自己的方法（#1635）。
_SUPER_QUALIFIERS = frozenset({"super", "super()"})


@dataclass(frozen=True)
class EdgeTargets:
    """一条缓存边的解析结果。

    ``certain`` 是确定的目标，会成为调用图中的边；``possible`` 是无法区分的
    同名候选，不进入调用方 / 被调用方列表。
    """

    certain: list[FunctionRef] = field(default_factory=list)
    possible: list[FunctionRef] = field(default_factory=list)


class CachedEdgeResolver:
    """按上面的规则解析 ``get_call_edges`` 返回的一行。"""

    def __init__(
        self,
        *,
        functions_by_name: dict[str, list[FunctionRef]],
        functions_by_file: dict[str, list[FunctionRef]],
        file_import_map: dict[str, dict[str, str]],
        reexport_binder: PackageReexportBinder | None = None,
        subclasses: SubclassIndex | None = None,
    ) -> None:
        self._functions_by_file = functions_by_file
        self._functions_by_name = functions_by_name
        self._reexport_binder = reexport_binder
        self._subclasses = subclasses
        self._resolver = CalleeResolver(
            functions_by_name=functions_by_name,
            functions_by_file=functions_by_file,
            name_to_source=file_import_map,
        )

    @property
    def callee_resolver(self) -> CalleeResolver:
        """底层的裸名解析器（与 :class:`CallGraph` 共用）。"""
        return self._resolver

    def resolve(
        self, edge: dict[str, Any], caller_file: str, caller_class: str | None = None
    ) -> EdgeTargets:
        """返回 ``edge`` 的确定目标与模糊候选。

        ``caller_class`` 为调用方的外围类（#1635）：``self.m()`` 绑定到它自己的
        ``m``，其子类的覆写记为可能目标。
        """
        targets = self._static_targets(edge, caller_file)
        full_name = str(edge.get("callee_full") or "") or str(
            edge.get("callee_name") or ""
        )
        qualifier, base_name = _split_qualifier(full_name)
        if not caller_class:
            return targets
        if qualifier in _SUPER_QUALIFIERS:
            # ``super().m()`` 从不调用外围类自己的 ``m``。
            return EdgeTargets(
                certain=[r for r in targets.certain if r.receiver != caller_class],
                possible=[r for r in targets.possible if r.receiver != caller_class],
            )
        if qualifier not in OWN_INSTANCE_QUALIFIERS:
            return targets
        return self._self_dispatch(targets, base_name, qualifier, caller_class)

    def _self_dispatch(
        self, targets: EdgeTargets, base_name: str, qualifier: str, caller_class: str
    ) -> EdgeTargets:
        """#1635：外围类自己的方法是确定目标，其余同名候选与子类覆写是可能目标。"""
        certain, possible = list(targets.certain), list(targets.possible)
        if len(certain) != 1:
            own = own_class_target(certain + possible, qualifier, caller_class)
            if own is not None:
                possible = [ref for ref in certain + possible if ref != own]
                certain = [own]
        if self._subclasses is not None:
            for ref in override_candidates(
                self._subclasses,
                self._functions_by_name,
                base_name,
                qualifier,
                caller_class,
            ):
                if ref not in certain and ref not in possible:
                    possible.append(ref)
        return EdgeTargets(certain=certain, possible=possible)

    def _static_targets(self, edge: dict[str, Any], caller_file: str) -> EdgeTargets:
        """按持久化解析与本地 / import / 全局兜底给出目标（与调用方类无关）。"""
        callee_name = str(edge.get("callee_name") or "")
        full_name = str(edge.get("callee_full") or "") or callee_name
        qualifier, base_name = _split_qualifier(full_name)
        resolution = edge.get("callee_resolution")
        if resolution in _NON_PROJECT_RESOLUTIONS:
            return EdgeTargets()
        if resolution in _PROJECT_RESOLUTIONS:
            resolved_file = str(edge.get("callee_resolved_file") or "")
            persisted = self._persisted_targets(base_name, qualifier, resolved_file)
            if persisted is None:
                persisted = self._reexported_targets(
                    base_name, qualifier, resolved_file
                )
            if persisted is not None:
                return persisted
        return self._inferred_targets(full_name, qualifier, caller_file)

    def _persisted_targets(
        self, base_name: str, qualifier: str, resolved_file: str
    ) -> EdgeTargets | None:
        """持久化解析指向的文件中的同名函数；文件里没有同名函数时返回 ``None``。"""
        candidates = [
            ref
            for ref in self._functions_by_file.get(resolved_file, [])
            if ref.name == base_name
        ]
        if not candidates:
            return None
        narrowed = _narrow_by_receiver(candidates, qualifier)
        if len(narrowed) == 1:
            return EdgeTargets(certain=narrowed)
        return EdgeTargets(possible=narrowed)

    def _reexported_targets(
        self, base_name: str, qualifier: str, resolved_file: str
    ) -> EdgeTargets | None:
        """#1578：沿包再导出与基类找到 ``接收者类型.方法`` 的唯一定义。"""
        if self._reexport_binder is None or not qualifier:
            return None
        bound = self._reexport_binder.bind(
            resolved_file, _receiver_name(qualifier), base_name, self._functions_by_file
        )
        return EdgeTargets(certain=bound) if len(bound) == 1 else None

    def _inferred_targets(
        self, full_name: str, qualifier: str, caller_file: str
    ) -> EdgeTargets:
        """没有可用的持久化解析：本地 / import 两档，然后是唯一候选的全局兜底。"""
        certain = [
            ref
            for ref, _confidence in self._resolver.resolve_items(
                full_name, caller_file, include_global=False
            )
        ]
        if certain and qualifier in _SELF_QUALIFIERS:
            # self / cls / super：由 ``resolve`` 按调用方的外围类分派（#1635）。
            return EdgeTargets(certain=certain)
        if certain:
            # #1621：本地 / import 档命中多个同名定义（`obj.hook()` 与同文件的
            # `A.hook`、`B.hook`）时无法确定是哪一个。接收者名恰是某个类时收窄；
            # 仍不唯一就只记为 possible，不再把每个候选都当作确定的被调方。
            scoped = _narrow_by_receiver(certain, qualifier)
            if len(scoped) == 1:
                return EdgeTargets(certain=scoped)
            return EdgeTargets(possible=scoped)
        globals_ = [
            ref
            for ref, _confidence in self._resolver.resolve_items(
                full_name, caller_file, include_local=False, include_import=False
            )
        ]
        narrowed = _narrow_by_receiver(globals_, qualifier)
        if len(narrowed) == 1 and _qualifier_admits_global(qualifier, narrowed[0]):
            return EdgeTargets(certain=narrowed)
        return EdgeTargets(possible=globals_)


def _split_qualifier(name: str) -> tuple[str, str]:
    if "." in name:
        qualifier, base_name = name.rsplit(".", 1)
        return qualifier, base_name
    return "", name


def _receiver_name(qualifier: str) -> str:
    return qualifier.rsplit(".", 1)[-1]


def _narrow_by_receiver(
    candidates: list[FunctionRef], qualifier: str
) -> list[FunctionRef]:
    """接收者名恰好是某个候选所属类时，只保留这些候选。"""
    if not qualifier:
        return candidates
    receiver = _receiver_name(qualifier)
    matches = [ref for ref in candidates if ref.receiver == receiver]
    return matches or candidates


def _qualifier_admits_global(qualifier: str, ref: FunctionRef) -> bool:
    """唯一的全局候选能否绑定：只有接收者不会指向别的类型时才可以。

    ``d.get`` / ``xs.append`` 的接收者类型未知，即使项目里只有一个 ``get``
    也不能断定调用的就是它（#1560）。
    """
    if not qualifier or qualifier in _SELF_QUALIFIERS:
        return True
    return ref.receiver == _receiver_name(qualifier)
