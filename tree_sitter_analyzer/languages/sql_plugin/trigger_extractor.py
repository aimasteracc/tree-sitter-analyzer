"""Enhanced SQL trigger extraction — extracted from sql_plugin/extractor.py."""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from ...models import SQLTrigger
from ...utils import log_debug
from .identifier_validator import is_valid_identifier


def extract_sql_triggers(
    source_code: str,
    sql_elements: list,
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

    for match in trigger_matches:
        trigger_name = match.group(1)

        if trigger_name in processed_triggers:
            continue

        if not is_valid_identifier(trigger_name):
            continue

        if len(trigger_name) <= 2:
            continue

        if trigger_name.upper() in (
            "KEY",
            "AUTO_INCREMENT",
            "PRIMARY",
            "FOREIGN",
            "INDEX",
            "UNIQUE",
        ):
            continue

        processed_triggers.add(trigger_name)

        start_line = source_code[: match.start()].count("\n") + 1

        trigger_start_pos = match.start()
        end_pattern = re.compile(r"\bEND\s*;", re.IGNORECASE)
        end_match = end_pattern.search(source_code, trigger_start_pos)

        if end_match:
            end_line = source_code[: end_match.end()].count("\n") + 1
            trigger_text = source_code[trigger_start_pos : end_match.end()]
        else:
            end_line = start_line + 20
            trigger_text = source_code[trigger_start_pos : trigger_start_pos + 500]

        trigger_timing, trigger_event, table_name = extract_trigger_metadata(
            trigger_text
        )

        try:
            trigger = SQLTrigger(
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
            sql_elements.append(trigger)
        except Exception as e:
            log_debug(f"Failed to extract enhanced trigger: {e}")


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
