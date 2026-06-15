"""SQL element validation and recovery — extracted from sql_plugin/extractor.py.

r37av (dogfood): tool self-scan flagged ``validate_and_fix_elements`` as
143 lines / nesting depth 7. The function mixed four concerns: phantom
detection, name fixing (trigger + function), deduplication, missing-view
recovery. Refactor splits along those seams. Behaviour preserved.
"""

import re
from typing import Any

from ...models import SQLView
from ...utils import log_debug
from .identifier_validator import is_valid_identifier

_GARBAGE_FUNCTION_NAMES = frozenset({"AUTO_INCREMENT", "KEY", "PRIMARY", "FOREIGN"})
_TRIGGER_NAME_REGEX = re.compile(
    r"CREATE\s+TRIGGER\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE
)
_FUNCTION_NAME_REGEX = re.compile(
    r"CREATE\s+FUNCTION\s+(?:[a-zA-Z_][a-zA-Z0-9_]*\.)*([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)
_CREATE_VIEW_LINE_REGEX = re.compile(
    r"^\s*CREATE\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+AS",
    re.IGNORECASE | re.MULTILINE,
)
_VIEW_SOURCE_TABLES_REGEX = re.compile(
    r"(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE
)


def validate_and_fix_elements(
    elements: list[Any],
    source_code: str,
) -> list[Any]:
    """Post-process elements to fix parsing errors caused by platform-specific behavior.

    Returns a new validated list (input list is not mutated except for
    in-place name fixes on individual element objects — preserved from
    the pre-r37av behavior).
    """
    validated: list[Any] = []
    seen_names: set[tuple[Any, str, Any]] = set()

    for elem in elements:
        if _is_phantom_element(elem):
            continue
        if not _fix_element_name(elem):
            continue
        if not _record_unique(elem, seen_names):
            continue
        validated.append(elem)

    if source_code:
        _recover_missing_views(source_code, validated)

    return validated


def _is_phantom_element(elem: Any) -> bool:
    """Drop trigger/function elements whose raw_text doesn't match their type."""
    elem_type = getattr(elem, "sql_element_type", None)
    raw_text = getattr(elem, "raw_text", None)
    if not elem_type or not raw_text:
        return False
    raw_text_stripped = raw_text.strip()
    if elem_type.value == "trigger":
        if not re.search(r"CREATE\s+TRIGGER", raw_text_stripped, re.IGNORECASE):
            log_debug(f"Removing phantom trigger: {elem.name} (content mismatch)")
            return True
    elif elem_type.value == "function":
        if not re.search(r"CREATE\s+FUNCTION", raw_text_stripped, re.IGNORECASE):
            log_debug(f"Removing phantom function: {elem.name} (content mismatch)")
            return True
    return False


def _fix_element_name(elem: Any) -> bool:
    """Fix wrong names in-place. Return False to drop the element entirely."""
    elem_type = getattr(elem, "sql_element_type", None)
    raw_text = getattr(elem, "raw_text", None)
    if not elem_type or not raw_text:
        return True

    if elem_type.value == "trigger":
        _fix_trigger_name(elem)
        return True
    if elem_type.value == "function":
        return _fix_function_name(elem)
    return True


def _fix_trigger_name(elem: Any) -> None:
    """Overwrite ``elem.name`` with the regex-extracted CREATE TRIGGER name."""
    trigger_match = _TRIGGER_NAME_REGEX.search(elem.raw_text)
    if not trigger_match:
        return
    correct_name = trigger_match.group(1)
    if elem.name != correct_name and is_valid_identifier(correct_name):
        log_debug(f"Fixing trigger name: {elem.name} -> {correct_name}")
        elem.name = correct_name


def _fix_function_name(elem: Any) -> bool:
    """Fix function name in-place. Return False if the element should be dropped."""
    name_upper = (elem.name or "").upper()
    if name_upper in _GARBAGE_FUNCTION_NAMES:
        func_match = _FUNCTION_NAME_REGEX.search(elem.raw_text)
        if func_match:
            correct_name = func_match.group(1)
            log_debug(f"Fixing garbage function name: {elem.name} -> {correct_name}")
            elem.name = correct_name
        else:
            log_debug(f"Removing garbage function name: {elem.name}")
            return False

    gen_match = _FUNCTION_NAME_REGEX.search(elem.raw_text)
    if gen_match:
        correct_name = gen_match.group(1)
        if elem.name != correct_name and is_valid_identifier(correct_name):
            log_debug(f"Fixing function name: {elem.name} -> {correct_name}")
            elem.name = correct_name
    return True


def _record_unique(
    elem: Any,
    seen_names: set[tuple[Any, str, Any]],
) -> bool:
    """Track ``(type, name, start_line)`` triples — return False on duplicates."""
    key = (getattr(elem, "sql_element_type", None), elem.name, elem.start_line)
    if key in seen_names:
        return False
    seen_names.add(key)
    return True


def _recover_missing_views(source_code: str, validated: list[Any]) -> None:
    """Append SQLView entries for views found in raw SQL that weren't extracted."""
    existing_views = {
        e.name
        for e in validated
        if hasattr(e, "sql_element_type") and e.sql_element_type.value == "view"
    }

    for match in _CREATE_VIEW_LINE_REGEX.finditer(source_code):
        view_name = match.group(1)
        if view_name in existing_views or not is_valid_identifier(view_name):
            continue
        log_debug(f"Recovering missing view: {view_name}")
        view = _build_recovered_view(source_code, match, view_name)
        validated.append(view)
        existing_views.add(view_name)


def _build_recovered_view(
    source_code: str,
    match: re.Match[str],
    view_name: str,
) -> SQLView:
    """Assemble a SQLView from a regex hit on the raw source."""
    start_pos = match.start()
    start_line = source_code.count("\n", 0, start_pos) + 1

    view_context = source_code[start_pos:]
    semicolon_match = re.search(r";", view_context)
    if semicolon_match:
        end_pos = start_pos + semicolon_match.end()
        end_line = source_code.count("\n", 0, end_pos) + 1
        table_search_window = view_context[: semicolon_match.end()]
    else:
        end_line = start_line + 5
        table_search_window = view_context[:500]

    source_tables = _VIEW_SOURCE_TABLES_REGEX.findall(table_search_window)

    return SQLView(
        name=view_name,
        start_line=start_line,
        end_line=end_line,
        raw_text=f"CREATE VIEW {view_name} ...",
        language="sql",
        source_tables=sorted(set(source_tables)),
        dependencies=sorted(set(source_tables)),
    )
