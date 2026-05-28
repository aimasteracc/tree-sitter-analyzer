"""Shared callee resolution over pre-built function and import indices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CalleeResolution:
    file: str
    confidence: float
    item: Any | None = None


class CalleeResolver:
    """Resolve call targets using local, import, then global project matches."""

    def __init__(
        self,
        *,
        functions_by_name: dict[str, list[Any]],
        functions_by_file: dict[str, list[Any]],
        name_to_source: dict[str, dict[str, str]],
    ) -> None:
        self._functions_by_name = functions_by_name
        self._functions_by_file = functions_by_file
        self._name_to_source = name_to_source

    def resolve_items(
        self,
        callee_name: str,
        source_file: str,
        *,
        include_local: bool = True,
        include_import: bool = True,
        include_global: bool = True,
    ) -> list[tuple[Any, float]]:
        return [
            (resolved.item, resolved.confidence)
            for resolved in self._resolve(
                callee_name,
                source_file,
                keep_items=True,
                include_local=include_local,
                include_import=include_import,
                include_global=include_global,
            )
            if resolved.item is not None
        ]

    def resolve_first_item(
        self,
        callee_name: str,
        source_file: str,
        *,
        include_local: bool = True,
        include_import: bool = True,
        include_global: bool = True,
    ) -> tuple[Any, float] | None:
        qualifier, base_name = _split_qualifier(callee_name)

        if include_local:
            for func in self._functions_by_file.get(source_file, []):
                if _item_name(func) == base_name:
                    return func, 1.0

        target_file = self._import_target(source_file, base_name, qualifier)
        if include_import and target_file:
            for func in self._functions_by_file.get(target_file, []):
                if _item_name(func) == base_name:
                    return func, 0.9

        if include_global:
            candidates = self._functions_by_name.get(base_name, [])
            if candidates:
                return candidates[0], 0.5

        return None

    def resolve_files(
        self,
        callee_name: str,
        source_file: str,
        *,
        include_unmatched_import: bool = False,
        include_local: bool = True,
        include_import: bool = True,
        include_global: bool = True,
    ) -> list[tuple[str, float]]:
        return [
            (resolved.file, resolved.confidence)
            for resolved in self._resolve(
                callee_name,
                source_file,
                keep_items=False,
                include_unmatched_import=include_unmatched_import,
                include_local=include_local,
                include_import=include_import,
                include_global=include_global,
            )
        ]

    def resolve_first_file(
        self,
        callee_name: str,
        source_file: str,
        *,
        include_unmatched_import: bool = False,
        include_local: bool = True,
        include_import: bool = True,
        include_global: bool = True,
    ) -> tuple[str, float] | None:
        first = self.resolve_first_item(
            callee_name,
            source_file,
            include_local=include_local,
            include_import=include_import,
            include_global=include_global,
        )
        if first is not None:
            item, confidence = first
            return _item_file(item), confidence
        if include_import and include_unmatched_import:
            qualifier, base_name = _split_qualifier(callee_name)
            target_file = self._import_target(source_file, base_name, qualifier)
            if target_file:
                return target_file, 0.7
        return None

    def _resolve(
        self,
        callee_name: str,
        source_file: str,
        *,
        keep_items: bool,
        include_unmatched_import: bool = False,
        include_local: bool = True,
        include_import: bool = True,
        include_global: bool = True,
    ) -> list[CalleeResolution]:
        qualifier, base_name = _split_qualifier(callee_name)
        results: list[CalleeResolution] = []
        seen: set[str] = set()

        if include_local:
            for func in self._functions_by_file.get(source_file, []):
                if _item_name(func) == base_name:
                    _append_resolution(results, seen, func, 1.0, keep_items=keep_items)

        target_file = self._import_target(source_file, base_name, qualifier)
        if include_import and target_file:
            matched_import = False
            for func in self._functions_by_file.get(target_file, []):
                if _item_name(func) == base_name:
                    matched_import = True
                    _append_resolution(results, seen, func, 0.9, keep_items=keep_items)
            if include_unmatched_import and not matched_import:
                _append_file_resolution(results, seen, target_file, 0.7)

        if include_global and not results:
            for func in self._functions_by_name.get(base_name, []):
                _append_resolution(results, seen, func, 0.5, keep_items=keep_items)

        return results

    def _import_target(
        self,
        source_file: str,
        base_name: str,
        qualifier: str,
    ) -> str:
        name_sources = self._name_to_source.get(source_file, {})
        return name_sources.get(base_name) or name_sources.get(
            qualifier or base_name, ""
        )


def _split_qualifier(callee_name: str) -> tuple[str, str]:
    if "." in callee_name:
        qualifier, short_name = callee_name.rsplit(".", 1)
        return qualifier, short_name
    return "", callee_name


def _item_name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("name", ""))
    return str(getattr(item, "name", ""))


def _item_file(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("file", item.get("file_path", "")))
    return str(getattr(item, "file", getattr(item, "file_path", "")))


def _append_resolution(
    results: list[CalleeResolution],
    seen: set[str],
    item: Any,
    confidence: float,
    *,
    keep_items: bool,
) -> None:
    file_path = _item_file(item)
    key = _item_key(item)
    if key in seen:
        return
    seen.add(key)
    results.append(
        CalleeResolution(
            file=file_path,
            confidence=confidence,
            item=item if keep_items else None,
        )
    )


def _append_file_resolution(
    results: list[CalleeResolution],
    seen: set[str],
    file_path: str,
    confidence: float,
) -> None:
    if file_path in seen:
        return
    seen.add(file_path)
    results.append(CalleeResolution(file=file_path, confidence=confidence))


def _item_key(item: Any) -> str:
    if hasattr(item, "qualified_name"):
        return str(item.qualified_name())
    file_path = _item_file(item)
    line = getattr(item, "line", getattr(item, "start_line", ""))
    if isinstance(item, dict):
        line = item.get("line", item.get("start_line", ""))
    return f"{file_path}:{_item_name(item)}:{line}"
