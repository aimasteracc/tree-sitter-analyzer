"""Contract: rfcs/README.md index agrees with the RFC files (CLAUDE.md §11).

The index is the public claim of what each RFC's status is; the RFC file's own
``Status`` line is the evidence. They must not drift silently:

* every ``rfcs/NNNN-*.md`` (except the ``0000`` template) appears in the index;
* every index row links an existing file, or is explicitly ``removed (<sha>)``
  with no link and no file;
* every RFC ``Status`` value starts with one closed-set keyword, and the index
  status starts with the same keyword (text after the keyword is free
  annotation in both places).
"""

from __future__ import annotations

import re
from pathlib import Path

RFC_ROOT = Path(__file__).parents[2] / "rfcs"
README_PATH = RFC_ROOT / "README.md"
INDEX_HEADER = "| RFC | Title | Status |"
LINKED_CELL = re.compile(r"^\[(?P<num>\d{4})\]\((?P<file>\d{4}-[^)]+\.md)\)$")
PLAIN_CELL = re.compile(r"^(?P<num>\d{4})$")
REMOVED_STATUS = re.compile(r"^removed \([0-9a-f]{7,40}\)$")
STATUS_PREFIX = "- **Status**:"
STATUS_KEYWORDS = (
    "draft",
    "accepted",
    "implemented",
    "rejected",
    "superseded",
    "removed",
)
LEADING_WORD = re.compile(r"^[\s*`]*([A-Za-z]+)")


def _keyword(status: str) -> str | None:
    """Return the closed-set status keyword the value starts with, else None."""
    match = LEADING_WORD.match(status)
    word = match[1].casefold() if match else None
    return word if word in STATUS_KEYWORDS else None


def _index_rows() -> list[tuple[str, str | None, str]]:
    """Return (number, linked file or None, status) for the contiguous index table."""
    lines = README_PATH.read_text(encoding="utf-8").splitlines()
    start = lines.index(INDEX_HEADER) + 2  # skip header + separator
    rows: list[tuple[str, str | None, str]] = []
    for line in lines[start:]:
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        assert len(cells) == 3, f"index row must have 3 cells: {line!r}"
        linked = LINKED_CELL.match(cells[0])
        plain = PLAIN_CELL.match(cells[0])
        assert linked or plain, f"unrecognised RFC cell: {cells[0]!r}"
        if linked:
            rows.append((linked["num"], linked["file"], cells[2]))
        else:
            assert plain is not None
            rows.append((plain["num"], None, cells[2]))
    return rows


def _rfc_files() -> dict[str, str]:
    return {
        path.name[:4]: path.name
        for path in RFC_ROOT.glob("[0-9][0-9][0-9][0-9]-*.md")
        if not path.name.startswith("0000-")
    }


def _file_status(file_name: str) -> str:
    """Return the ``Status`` value, joining indented continuation lines."""
    lines = (RFC_ROOT / file_name).read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith(STATUS_PREFIX):
            parts = [line[len(STATUS_PREFIX) :]]
            for continuation in lines[index + 1 :]:
                if not continuation.startswith((" ", "\t")) or not continuation.strip():
                    break
                parts.append(continuation)
            return " ".join(parts)
    raise AssertionError(f"{file_name} has no '{STATUS_PREFIX}' line")


def test_index_numbers_are_unique() -> None:
    numbers = [num for num, _, _ in _index_rows()]
    duplicates = sorted({num for num in numbers if numbers.count(num) > 1})
    assert duplicates == []


def test_every_rfc_file_is_indexed_with_a_link() -> None:
    linked = {file for _, file, _ in _index_rows() if file is not None}
    missing = sorted(set(_rfc_files().values()) - linked)
    assert missing == []


def test_every_index_row_links_an_existing_file_or_is_marked_removed() -> None:
    files = _rfc_files()
    problems: list[str] = []
    for num, file, status in _index_rows():
        if file is None:
            if not REMOVED_STATUS.match(status):
                problems.append(f"{num}: unlinked row not marked 'removed (<sha>)'")
            if num in files:
                problems.append(f"{num}: marked removed but {files[num]} exists")
        elif not (RFC_ROOT / file).is_file():
            problems.append(f"{num}: dead link {file}")
        elif file[:4] != num:
            problems.append(f"{num}: link number mismatch {file}")
    assert problems == []


def test_every_rfc_status_line_starts_with_a_keyword() -> None:
    missing = {
        file: _file_status(file).strip()
        for file in _rfc_files().values()
        if _keyword(_file_status(file)) is None
    }
    assert missing == {}


def test_index_status_keyword_equals_rfc_status_keyword() -> None:
    mismatches = {
        num: (_keyword(status), _keyword(_file_status(file)))
        for num, file, status in _index_rows()
        if file is not None
        and (RFC_ROOT / file).is_file()
        and _keyword(status) != _keyword(_file_status(file))
    }
    assert mismatches == {}
