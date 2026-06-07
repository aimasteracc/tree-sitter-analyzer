"""CSV cell sanitization shared across formatters.

Python 3.10's ``csv.writer`` raises ``_csv.Error: need to escape, but no
escapechar set`` when a field contains a control character it cannot quote
(notably a NULL byte); 3.11+ does not. Setting ``escapechar`` silences the
error but doubles literal backslashes in ordinary fields (``C:\\tmp`` ->
``C:\\\\tmp``), a format regression for normal input such as Windows paths and
regex strings.

The correct fix is to strip the C0/DEL control characters that CSV cannot
represent — they never legitimately appear in source-code symbol names or
text — while leaving the dialect (and therefore backslashes and quoting)
untouched.

``\\t`` and ``\\n`` are preserved: ``csv.writer`` quotes them correctly on
every supported Python version (verified on 3.10 and 3.11). ``\\r`` is **not**
preserved — on Python 3.10 a bare carriage return is written *unquoted* and the
result fails to read back (``_csv.Error: new-line character seen in unquoted
field``), so it is stripped along with the other unrepresentable controls.
"""

from __future__ import annotations

from typing import Any

# C0 controls (0x00-0x1F) and DEL (0x7F), except tab and line feed, which
# csv.writer quotes correctly on all supported Python versions. Carriage
# return is NOT excepted: Python 3.10 emits a bare \r unquoted, producing an
# unreadable CSV, so it is stripped too.
_REMOVE = set(range(0x20)) | {0x7F}
_REMOVE.discard(0x09)  # tab
_REMOVE.discard(0x0A)  # line feed
_TRANSLATION = dict.fromkeys(_REMOVE)


def csv_safe_cell(value: Any) -> Any:
    """Strip CSV-unrepresentable control characters from a string cell.

    Non-string values are returned unchanged so numeric columns keep their
    type for ``csv.writer``.
    """
    if isinstance(value, str):
        return value.translate(_TRANSLATION)
    return value


def csv_safe_row(row: list[Any]) -> list[Any]:
    """Return a copy of ``row`` with every string cell sanitized."""
    return [csv_safe_cell(cell) for cell in row]
