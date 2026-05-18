"""SQL trigger extraction helpers."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

from ...models import Function, SQLTrigger
from ...utils import log_debug
from .identifier_validator import is_valid_identifier

_ENHANCED_RESERVED_TRIGGER_NAMES = {
    "KEY",
    "AUTO_INCREMENT",
    "PRIMARY",
    "FOREIGN",
    "INDEX",
    "UNIQUE",
}

_LEGACY_RESERVED_TRIGGER_NAMES = _ENHANCED_RESERVED_TRIGGER_NAMES | {
    "PRICE",
    "QUANTITY",
    "TOTAL",
    "SUM",
    "COUNT",
    "AVG",
    "MAX",
    "MIN",
    "CONSTRAINT",
    "CHECK",
    "DEFAULT",
    "REFERENCES",
    "ON",
    "UPDATE",
    "DELETE",
    "INSERT",
    "BEFORE",
    "AFTER",
    "INSTEAD",
    "OF",
}


@dataclass(slots=True)
class _SQLTriggerExtractionContext:
    source_code: str
    sql_elements: list
    processed_triggers: set[str]
    trigger_factory: Callable[..., SQLTrigger]
    is_valid_identifier_fn: Callable[[str], bool]


def extract_sql_triggers(
    source_code: str,
    sql_elements: list,
    *,
    trigger_factory: Callable[..., SQLTrigger] = SQLTrigger,
    is_valid_identifier_fn: Callable[[str], bool] = is_valid_identifier,
) -> None:
    """Extract CREATE TRIGGER statements with enhanced metadata."""
    if not source_code:
        log_debug("WARNING: source_code is empty in extract_sql_triggers")
        return

    processed_triggers: set[str] = set()
    trigger_pattern = re.compile(
        r"CREATE\s+TRIGGER\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE | re.MULTILINE
    )
    trigger_matches = list(trigger_pattern.finditer(source_code))
    log_debug(f"Found {len(trigger_matches)} CREATE TRIGGER statements in source")

    context = _SQLTriggerExtractionContext(
        source_code=source_code,
        sql_elements=sql_elements,
        processed_triggers=processed_triggers,
        trigger_factory=trigger_factory,
        is_valid_identifier_fn=is_valid_identifier_fn,
    )
    for match in trigger_matches:
        _append_sql_trigger_match(match, context)


def _append_sql_trigger_match(
    match: re.Match[str],
    context: _SQLTriggerExtractionContext,
) -> None:
    """Append one enhanced SQL trigger from a regex match when it is valid."""
    trigger_name = match.group(1)
    if not _is_valid_enhanced_trigger_name(
        trigger_name,
        context.processed_triggers,
        context.is_valid_identifier_fn,
    ):
        return

    context.processed_triggers.add(trigger_name)
    start_line, end_line, trigger_text = _trigger_text_span(context.source_code, match)
    trigger_timing, trigger_event, table_name = extract_trigger_metadata(trigger_text)

    try:
        context.sql_elements.append(
            context.trigger_factory(
                name=trigger_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=trigger_text,
                language="sql",
                table_name=table_name,
                trigger_timing=trigger_timing,
                trigger_event=trigger_event,
                dependencies=[table_name] if table_name else [],
            )
        )
    except Exception as e:
        log_debug(f"Failed to extract enhanced trigger: {e}")


def _is_valid_enhanced_trigger_name(
    trigger_name: str,
    processed_triggers: set[str],
    is_valid_identifier_fn: Callable[[str], bool],
) -> bool:
    """Return whether a regex trigger name should become an SQLTrigger."""
    return (
        trigger_name not in processed_triggers
        and is_valid_identifier_fn(trigger_name)
        and len(trigger_name) > 2
        and trigger_name.upper() not in _ENHANCED_RESERVED_TRIGGER_NAMES
    )


def _trigger_text_span(
    source_code: str,
    match: re.Match[str],
) -> tuple[int, int, str]:
    """Return start line, end line, and raw trigger text for a match."""
    start_line = source_code[: match.start()].count("\n") + 1
    trigger_start_pos = match.start()
    end_match = re.search(r"\bEND\s*;", source_code[trigger_start_pos:], re.IGNORECASE)

    if end_match:
        trigger_end = trigger_start_pos + end_match.end()
        end_line = source_code[:trigger_end].count("\n") + 1
        trigger_text = source_code[trigger_start_pos:trigger_end]
    else:
        end_line = start_line + 20
        trigger_text = source_code[trigger_start_pos : trigger_start_pos + 500]
    return start_line, end_line, trigger_text


def extract_trigger_metadata(
    trigger_text: str,
) -> tuple[str | None, str | None, str | None]:
    """Extract trigger timing, event, and target table."""
    timing = None
    event = None
    table_name = None

    timing_match = re.search(r"(BEFORE|AFTER)", trigger_text, re.IGNORECASE)
    if timing_match:
        timing = timing_match.group(1).upper()

    event_match = re.search(r"(INSERT|UPDATE|DELETE)", trigger_text, re.IGNORECASE)
    if event_match:
        event = event_match.group(1).upper()

    table_match = re.search(
        r"ON\s+([a-zA-Z_][a-zA-Z0-9_]*)", trigger_text, re.IGNORECASE
    )
    if table_match:
        table_name = table_match.group(1)

    return timing, event, table_name


def extract_legacy_triggers(
    root_node: tree_sitter.Node,
    functions: list[Function],
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
    is_valid_identifier_fn: Callable[[str], bool],
) -> None:
    """Extract CREATE TRIGGER statements as generic Function elements."""
    for node in traverse_nodes(root_node):
        if node.type != "ERROR":
            continue
        _append_legacy_triggers_from_error_node(
            node,
            functions,
            get_node_text,
            is_valid_identifier_fn,
        )


def _append_legacy_triggers_from_error_node(
    node: tree_sitter.Node,
    functions: list[Function],
    get_node_text: Callable[..., str],
    is_valid_identifier_fn: Callable[[str], bool],
) -> None:
    """Append legacy Function trigger elements from one ERROR node."""
    node_text = get_node_text(node)
    if not node_text:
        return

    node_text_upper = node_text.upper()
    if "CREATE" not in node_text_upper or "TRIGGER" not in node_text_upper:
        return

    matches = re.finditer(
        r"CREATE\s+TRIGGER\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)",
        node_text,
        re.IGNORECASE,
    )
    for match in matches:
        _append_legacy_trigger_match(
            node,
            node_text,
            match,
            functions,
            is_valid_identifier_fn,
        )


def _append_legacy_trigger_match(
    node: tree_sitter.Node,
    node_text: str,
    match: re.Match[str],
    functions: list[Function],
    is_valid_identifier_fn: Callable[[str], bool],
) -> None:
    """Append one legacy trigger Function from a regex match when it is valid."""
    trigger_name = match.group(1)
    if not _is_valid_legacy_trigger_name(trigger_name, is_valid_identifier_fn):
        return

    try:
        newlines_before = node_text[: match.start()].count("\n")
        functions.append(
            Function(
                name=trigger_name,
                start_line=node.start_point[0] + 1 + newlines_before,
                end_line=node.end_point[0] + 1,
                raw_text=node_text,
                language="sql",
            )
        )
    except Exception as e:
        log_debug(f"Failed to extract trigger: {e}")


def _is_valid_legacy_trigger_name(
    trigger_name: str,
    is_valid_identifier_fn: Callable[[str], bool],
) -> bool:
    """Return whether a legacy Function trigger name is usable."""
    return (
        bool(trigger_name)
        and is_valid_identifier_fn(trigger_name)
        and trigger_name.upper() not in _LEGACY_RESERVED_TRIGGER_NAMES
    )
