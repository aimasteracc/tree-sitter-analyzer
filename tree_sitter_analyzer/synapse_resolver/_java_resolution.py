"""Ordered Java call-target resolution stages."""

from __future__ import annotations

from typing import TypeAlias

from ._java_constants import (
    EXTERNAL_METHODS_JAVA,
    JAVA_LANG_TYPES,
    STDLIB_METHODS_JAVA,
    is_jdk_prefix,
)
from ._java_context import JavaResolverContext

Resolution: TypeAlias = tuple[int | None, str, str]


def _split_receiver(callee_full: str, callee_name: str) -> tuple[str, str]:
    full = callee_full or callee_name
    if "." not in full:
        return "", full or callee_name
    receiver, simple = full.rsplit(".", 1)
    return receiver, simple


def _lookup_in_file(
    ctx: JavaResolverContext,
    file_path: str,
    simple: str,
) -> int | None:
    for name, kind, symbol_id in ctx.file_symbols.get(file_path, []):
        if name == simple and kind in ("function", "method", "class"):
            return symbol_id
    return None


def _resolve_local(
    ctx: JavaResolverContext,
    caller_file: str,
    receiver: str,
    simple: str,
) -> Resolution | None:
    if receiver not in ("", "this", "super"):
        return None
    symbol_id = _lookup_in_file(ctx, caller_file, simple)
    if symbol_id is not None:
        return symbol_id, "local", caller_file
    for methods in ctx.file_class_methods.get(caller_file, {}).values():
        method_id = methods.get(simple)
        if method_id is not None:
            return method_id, "local", caller_file
    return None


def _resolve_static_import(
    ctx: JavaResolverContext,
    caller_file: str,
    receiver: str,
    simple: str,
) -> Resolution | None:
    if receiver:
        return None
    owner_fqn = ctx.static_imports_by_file.get(caller_file, {}).get(simple)
    if not owner_fqn:
        return None
    target = ctx.fqn_to_file.get(owner_fqn)
    if target:
        return _lookup_in_file(ctx, target, simple), "project", target
    return None, "external", ""


def _receiver_type_names(receiver: str) -> tuple[str, str]:
    head = receiver.split(".", 1)[0]
    tail = receiver.rsplit(".", 1)[-1] if "." in receiver else receiver
    return head, tail


def _resolve_direct_fqn(
    ctx: JavaResolverContext,
    receiver: str,
    simple: str,
) -> Resolution | None:
    target = ctx.fqn_to_file.get(receiver)
    if target is None:
        return None
    return _lookup_in_file(ctx, target, simple), "project", target


def _resolve_type_import(
    ctx: JavaResolverContext,
    caller_file: str,
    type_names: tuple[str, str],
    simple: str,
) -> Resolution | None:
    imports = ctx.simple_to_fqn_by_file.get(caller_file, {})
    for type_name in type_names:
        fqn = imports.get(type_name)
        if not fqn:
            continue
        target = ctx.fqn_to_file.get(fqn)
        if target:
            return _lookup_in_file(ctx, target, simple), "project", target
        return None, "external", ""
    return None


def _resolve_same_package(
    ctx: JavaResolverContext,
    caller_file: str,
    type_names: tuple[str, str],
    simple: str,
) -> Resolution | None:
    package = ctx.file_package.get(caller_file, "")
    if not package:
        return None
    for type_name in type_names:
        target = ctx.fqn_to_file.get(f"{package}.{type_name}")
        if target:
            return _lookup_in_file(ctx, target, simple), "project", target
    return None


def _resolve_wildcard(
    ctx: JavaResolverContext,
    caller_file: str,
    type_name: str,
    simple: str,
) -> Resolution | None:
    for package in ctx.wildcard_pkgs_by_file.get(caller_file, []):
        target = ctx.fqn_to_file.get(f"{package}.{type_name}")
        if target:
            return _lookup_in_file(ctx, target, simple), "project", target
        if is_jdk_prefix(package + "."):
            return None, "external", ""
    return None


def _resolve_jdk_receiver(receiver: str, head: str) -> Resolution | None:
    if is_jdk_prefix(receiver + ".") or is_jdk_prefix(receiver):
        return None, "external", ""
    if head in JAVA_LANG_TYPES:
        return None, "external", ""
    return None


def _resolve_qualified(
    ctx: JavaResolverContext,
    caller_file: str,
    receiver: str,
    simple: str,
) -> Resolution | None:
    if not receiver or receiver in ("this", "super"):
        return None
    head, tail = _receiver_type_names(receiver)
    stages = (
        lambda: _resolve_direct_fqn(ctx, receiver, simple),
        lambda: _resolve_type_import(ctx, caller_file, (head, tail), simple),
        lambda: _resolve_same_package(ctx, caller_file, (head, tail), simple),
        lambda: _resolve_wildcard(ctx, caller_file, head, simple),
        lambda: _resolve_jdk_receiver(receiver, head),
    )
    for stage in stages:
        result = stage()
        if result is not None:
            return result
    return None


def _resolve_single_global(
    ctx: JavaResolverContext,
    receiver: str,
    simple: str,
) -> Resolution | None:
    if receiver:
        return None
    candidates = ctx.global_name_table.get(simple, [])
    if len(candidates) != 1:
        return None
    target_file, symbol_id = candidates[0]
    return symbol_id, "project", target_file


def _project_owns(ctx: JavaResolverContext, simple: str) -> bool:
    from ..languages.language_family import languages_compatible

    for owner_file, _symbol_id in ctx.global_name_table.get(simple, []):
        owner_language = ctx.file_languages.get(owner_file, "")
        if not owner_language or languages_compatible("java", owner_language):
            return True
    return False


def _resolve_known_method(
    ctx: JavaResolverContext,
    simple: str,
) -> Resolution | None:
    if simple in STDLIB_METHODS_JAVA and not _project_owns(ctx, simple):
        return None, "stdlib", ""
    if simple in EXTERNAL_METHODS_JAVA and not _project_owns(ctx, simple):
        return None, "external", ""
    return None


def resolve_java_callee(
    callee_name: str,
    callee_full: str,
    caller_file: str,
    ctx: JavaResolverContext,
) -> Resolution:
    """Resolve a Java call through the historical ordered 10-stage cascade."""
    receiver, simple = _split_receiver(callee_full, callee_name)
    stages = (
        lambda: _resolve_local(ctx, caller_file, receiver, simple),
        lambda: _resolve_static_import(ctx, caller_file, receiver, simple),
        lambda: _resolve_qualified(ctx, caller_file, receiver, simple),
        lambda: _resolve_single_global(ctx, receiver, simple),
        lambda: _resolve_known_method(ctx, simple),
    )
    for stage in stages:
        result = stage()
        if result is not None:
            return result
    return None, "unknown", ""


__all__ = ["resolve_java_callee"]
