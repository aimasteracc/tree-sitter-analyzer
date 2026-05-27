"""Selection predicates for the codegraph_query chain DSL."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from typing import Any

from ._codegraph_query_dsl import _ChainStep


def filter_symbols(
    symbols: list[dict[str, Any]],
    step: _ChainStep,
    *,
    invert: bool = False,
) -> list[dict[str, Any]]:
    """Filter a symbol selection using literal chain predicates."""
    predicate = _compile_symbol_predicate(step)
    if predicate is None:
        return list(symbols)
    return [
        symbol
        for symbol in symbols
        if (not predicate(symbol) if invert else predicate(symbol))
    ]


def is_test_or_fixture_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    name = os.path.basename(normalized)
    return bool(
        "/test/" in normalized
        or "/tests/" in normalized
        or "/__tests__/" in normalized
        or "/fixtures/" in normalized
        or name.startswith("test_")
        or "_test." in name
        or name.endswith((".test.ts", ".test.tsx", ".test.js", ".spec.ts", ".spec.js"))
    )


def is_generated_or_vendor_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    return any(part in normalized for part in ("/vendor/", "/gen/", "/generated/"))


def _compile_symbol_predicate(
    step: _ChainStep,
) -> Callable[[dict[str, Any]], bool] | None:
    case_sensitive = bool(step.kwargs.get("case", False))
    regex = _compile_regex(step.kwargs.get("regex"), case_sensitive=case_sensitive)
    has_predicate = regex is not None
    field_predicates = _field_predicates(step, case_sensitive=case_sensitive)
    has_predicate = has_predicate or bool(field_predicates)
    test_value = _optional_bool(step.kwargs.get("test"))
    generated_value = _optional_bool(step.kwargs.get("generated"))
    has_predicate = (
        has_predicate or test_value is not None or generated_value is not None
    )
    if not has_predicate:
        return None

    def predicate(symbol: dict[str, Any]) -> bool:
        if not _fields_match(symbol, field_predicates):
            return False
        if regex and not _regex_matches_symbol(regex, symbol):
            return False
        file_path = str(symbol.get("file") or "")
        if test_value is not None and is_test_or_fixture_path(file_path) != test_value:
            return False
        if (
            generated_value is not None
            and is_generated_or_vendor_path(file_path) != generated_value
        ):
            return False
        return True

    return predicate


def _field_predicates(
    step: _ChainStep,
    *,
    case_sensitive: bool,
) -> list[tuple[str, Any, bool]]:
    fields: list[tuple[str, Any, bool]] = []
    for field in ("name", "kind", "language"):
        if field in step.kwargs:
            fields.append((field, step.kwargs[field], case_sensitive))
    for field in ("file", "path"):
        if field in step.kwargs:
            fields.append(("file", step.kwargs[field], case_sensitive))
    return fields


def _fields_match(
    symbol: dict[str, Any],
    predicates: list[tuple[str, Any, bool]],
) -> bool:
    return all(
        _text_matches(
            str(symbol.get(field) or ""),
            expected,
            case_sensitive=case_sensitive,
        )
        for field, expected, case_sensitive in predicates
    )


def _compile_regex(value: Any, *, case_sensitive: bool) -> re.Pattern[str] | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError("filter() regex must be a non-empty string")
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        return re.compile(value, flags)
    except re.error as exc:
        raise ValueError(f"filter() invalid regex: {exc}") from exc


def _text_matches(value: str, expected: Any, *, case_sensitive: bool) -> bool:
    if isinstance(expected, list):
        return any(
            _text_matches(value, item, case_sensitive=case_sensitive)
            for item in expected
        )
    if not isinstance(expected, str) or not expected:
        return True
    if case_sensitive:
        return expected in value
    return expected.lower() in value.lower()


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _regex_matches_symbol(regex: re.Pattern[str], symbol: dict[str, Any]) -> bool:
    return any(
        regex.search(str(symbol.get(field) or ""))
        for field in ("name", "kind", "file", "language")
    )


__all__ = ["filter_symbols", "is_generated_or_vendor_path", "is_test_or_fixture_path"]
