"""Shared callee resolution over pre-built function and import indices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .languages.language_family import language_from_path, languages_compatible
from .utils.test_detection import is_test_file


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
            # Global fallback is a last-resort bare-name match across the whole
            # project. Gate it to the caller file's own language: a Python
            # ``config.get(...)`` must never bind to a JavaScript ``get`` just
            # because no Python ``get`` exists — that produced cross-language
            # false callees (and inlined foreign-language bodies into the
            # response, both wrong and token-bloat). When the source language is
            # unknown, keep the un-gated behaviour.
            #
            # Builtin-receiver gate (path 3, issue #447): this path receives only
            # the bare callee name without the qualifier/receiver context. The
            # inverted gate (fire only when receiver IS in BUILTIN_TYPE_NAMES_PY)
            # requires knowing the receiver — unavailable here. However, path 3 is
            # a bare-name global fallback: it is only reached for UNQUALIFIED calls
            # (``get()`` with no receiver). Qualified calls (``result.get``,
            # ``store.get``) have a receiver in callee_full that is processed by
            # the synapse cascade (path 1) and second-pass resolver (path 2), both
            # of which carry the inverted gate. Therefore path 3 does not gate on
            # builtin receiver type — it already lacks the data to do so, and the
            # callers that reach it have no receiver anyway.
            source_lang = self._source_language(source_file)
            globals_ = [
                func
                for func in self._functions_by_name.get(base_name, [])
                if not (
                    source_lang
                    and _item_language(func)
                    and not languages_compatible(source_lang, _item_language(func))
                )
            ]
            # Demote test-only shadows for a non-test caller: a production call
            # must not bind to a test mock (e.g. ``fts_search`` -> FallbackCache)
            # just because the test def is enumerated first. A test caller may
            # legitimately reference a test helper, so only filter for non-test
            # callers and only when a non-test def actually exists.
            if not is_test_file(source_file):
                non_test = [f for f in globals_ if not is_test_file(_item_file(f))]
                if non_test:
                    globals_ = non_test
            for func in globals_:
                _append_resolution(results, seen, func, 0.5, keep_items=keep_items)

        return results

    def _source_language(self, source_file: str) -> str:
        """Best-effort language of ``source_file``.

        Prefer an indexed function's language; fall back to the file extension
        so module-level calls in a file with no function symbols are still gated
        (Codex P2 #301 — an empty language here would re-open the ungated
        cross-language fallback).
        """
        for func in self._functions_by_file.get(source_file, []):
            lang = _item_language(func)
            if lang:
                return lang
        return language_from_path(source_file)

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


def _item_language(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("language", "") or "")
    return str(getattr(item, "language", "") or "")


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
