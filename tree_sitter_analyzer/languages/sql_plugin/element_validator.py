"""SQL element validation and recovery — extracted from sql_plugin/extractor.py."""

import re
from typing import Any

from ...models import SQLView
from ...utils import log_debug
from .identifier_validator import is_valid_identifier


def validate_and_fix_elements(
    elements: list[Any],
    source_code: str,
) -> list[Any]:
    """Post-process elements to fix parsing errors caused by platform-specific behavior."""
    validated = []
    seen_names: set[tuple[Any, str, Any]] = set()

    for elem in elements:
        elem_type = getattr(elem, "sql_element_type", None)

        # 1. Check for Phantom Elements (Mismatch between Type and Content)
        if elem_type and elem.raw_text:
            raw_text_stripped = elem.raw_text.strip()
            is_valid = True

            if elem_type.value == "trigger":
                if not re.search(r"CREATE\s+TRIGGER", raw_text_stripped, re.IGNORECASE):
                    log_debug(
                        f"Removing phantom trigger: {elem.name} (content mismatch)"
                    )
                    is_valid = False

            elif elem_type.value == "function":
                if not re.search(
                    r"CREATE\s+FUNCTION", raw_text_stripped, re.IGNORECASE
                ):
                    log_debug(
                        f"Removing phantom function: {elem.name} (content mismatch)"
                    )
                    is_valid = False

            if not is_valid:
                continue

        # 2. Fix Names
        if elem_type and elem.raw_text:
            if elem_type.value == "trigger":
                trigger_match = re.search(
                    r"CREATE\s+TRIGGER\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                    elem.raw_text,
                    re.IGNORECASE,
                )
                if trigger_match:
                    correct_name = trigger_match.group(1)
                    if elem.name != correct_name and is_valid_identifier(correct_name):
                        log_debug(f"Fixing trigger name: {elem.name} -> {correct_name}")
                        elem.name = correct_name

            elif elem_type.value == "function":
                if elem.name and elem.name.upper() in (
                    "AUTO_INCREMENT",
                    "KEY",
                    "PRIMARY",
                    "FOREIGN",
                ):
                    func_match = re.search(
                        r"CREATE\s+FUNCTION\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                        elem.raw_text,
                        re.IGNORECASE,
                    )
                    if func_match:
                        correct_name = func_match.group(1)
                        log_debug(
                            f"Fixing garbage function name: {elem.name} -> {correct_name}"
                        )
                        elem.name = correct_name
                    else:
                        log_debug(f"Removing garbage function name: {elem.name}")
                        continue

                gen_match = re.search(
                    r"CREATE\s+FUNCTION\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                    elem.raw_text,
                    re.IGNORECASE,
                )
                if gen_match:
                    correct_name = gen_match.group(1)
                    if elem.name != correct_name and is_valid_identifier(correct_name):
                        log_debug(
                            f"Fixing function name: {elem.name} -> {correct_name}"
                        )
                        elem.name = correct_name

        # Deduplication
        key = (getattr(elem, "sql_element_type", None), elem.name, elem.start_line)
        if key in seen_names:
            continue
        seen_names.add(key)

        validated.append(elem)

    # Recover missing Views
    if source_code:
        existing_views = {
            e.name
            for e in validated
            if hasattr(e, "sql_element_type") and e.sql_element_type.value == "view"
        }

        view_matches = re.finditer(
            r"^\s*CREATE\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+AS",
            source_code,
            re.IGNORECASE | re.MULTILINE,
        )

        for match in view_matches:
            view_name = match.group(1)
            if view_name not in existing_views and is_valid_identifier(view_name):
                log_debug(f"Recovering missing view: {view_name}")

                start_pos = match.start()
                start_line = source_code.count("\n", 0, start_pos) + 1

                view_context = source_code[start_pos:]
                semicolon_match = re.search(r";", view_context)
                if semicolon_match:
                    end_pos = start_pos + semicolon_match.end()
                    end_line = source_code.count("\n", 0, end_pos) + 1
                else:
                    end_line = start_line + 5

                source_tables = []
                table_matches = re.findall(
                    r"(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                    view_context[: semicolon_match.end() if semicolon_match else 500],
                    re.IGNORECASE,
                )
                source_tables.extend(table_matches)

                view = SQLView(
                    name=view_name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=f"CREATE VIEW {view_name} ...",
                    language="sql",
                    source_tables=sorted(set(source_tables)),
                    dependencies=sorted(set(source_tables)),
                )
                validated.append(view)
                existing_views.add(view_name)

    return validated
