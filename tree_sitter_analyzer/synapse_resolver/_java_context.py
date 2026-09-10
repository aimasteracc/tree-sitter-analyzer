"""Context construction for Java call-target resolution."""

from __future__ import annotations

from dataclasses import dataclass, field

from ._imports import ImportEntry
from ._java_imports import _PACKAGE_MARKER


@dataclass
class JavaResolverContext:
    """Per-index Java resolution maps, keyed by project-relative file path."""

    package_to_files: dict[str, list[str]] = field(default_factory=dict)
    fqn_to_file: dict[str, str] = field(default_factory=dict)
    simple_to_fqn_by_file: dict[str, dict[str, str]] = field(default_factory=dict)
    static_imports_by_file: dict[str, dict[str, str]] = field(default_factory=dict)
    wildcard_pkgs_by_file: dict[str, list[str]] = field(default_factory=dict)
    file_package: dict[str, str] = field(default_factory=dict)
    file_class_methods: dict[str, dict[str, dict[str, int]]] = field(
        default_factory=dict
    )
    file_symbols: dict[str, list[tuple[str, str, int]]] = field(default_factory=dict)
    global_name_table: dict[str, list[tuple[str, int]]] = field(default_factory=dict)
    file_languages: dict[str, str] = field(default_factory=dict)


def _collect_import_maps(
    ctx: JavaResolverContext,
    caller_file: str,
    entries: list[ImportEntry],
) -> None:
    simple_map: dict[str, str] = {}
    static_map: dict[str, str] = {}
    wildcards: list[str] = []
    for entry in entries:
        if entry.local_name == _PACKAGE_MARKER:
            ctx.file_package[caller_file] = entry.module_path
        elif entry.is_star:
            wildcards.append(entry.module_path)
        elif entry.local_name:
            simple_map.setdefault(entry.local_name, entry.module_path)
            owner = entry.module_path.rsplit(".", 1)[0]
            static_map.setdefault(entry.local_name, owner)
    if simple_map:
        ctx.simple_to_fqn_by_file[caller_file] = simple_map
    if static_map:
        ctx.static_imports_by_file[caller_file] = static_map
    if wildcards:
        ctx.wildcard_pkgs_by_file[caller_file] = wildcards


def _register_packages(ctx: JavaResolverContext) -> None:
    for file_path, package in ctx.file_package.items():
        ctx.package_to_files.setdefault(package, []).append(file_path)


def _register_types(
    ctx: JavaResolverContext,
    file_symbols: dict[str, list[tuple[str, str, int]]],
) -> None:
    for file_path, symbols in file_symbols.items():
        package = ctx.file_package.get(file_path, "")
        for name, kind, _symbol_id in symbols:
            if kind == "class":
                fqn = f"{package}.{name}" if package else name
                ctx.fqn_to_file.setdefault(fqn, file_path)


def build_java_context(
    imports_by_file: dict[str, list[ImportEntry]],
    file_symbols: dict[str, list[tuple[str, str, int]]],
    file_class_methods: dict[str, dict[str, dict[str, int]]],
    global_name_table: dict[str, list[tuple[str, int]]],
    file_languages: dict[str, str] | None = None,
) -> JavaResolverContext:
    """Build the immutable-per-pass maps consumed by the Java cascade."""
    ctx = JavaResolverContext(
        file_class_methods=file_class_methods,
        file_symbols=file_symbols,
        global_name_table=global_name_table,
        file_languages=file_languages or {},
    )
    for caller_file, entries in imports_by_file.items():
        _collect_import_maps(ctx, caller_file, entries)
    _register_packages(ctx)
    _register_types(ctx, file_symbols)
    return ctx


__all__ = ["JavaResolverContext", "build_java_context"]
