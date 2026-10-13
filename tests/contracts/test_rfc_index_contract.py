"""契约：rfcs/README.md 索引必须与 RFC 文件一致（CLAUDE.md §11）。

索引是每个 RFC 状态的公开声明，RFC 文件自身的 ``Status`` 行是证据，二者不得静默漂移：

* 每个 ``rfcs/NNNN-*.md``（``0000`` 模板除外）都出现在索引中，且编号前缀唯一；
* 每个索引行要么链接到存在的文件，要么显式标注 ``removed (<sha>)`` 且无链接、无文件；
* 每个 RFC 的 ``Status`` 值以封闭集合中的一个关键字开头，索引状态以同一关键字开头
  （关键字之后的文字在两处均为自由注释）。
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

RFC_ROOT = Path(__file__).parents[2] / "rfcs"
README_PATH = RFC_ROOT / "README.md"
INDEX_HEADER = "| RFC | Title | Status |"
LINKED_CELL = re.compile(r"^\[(?P<num>\d{4})\]\((?P<file>\d{4}-[^)]+\.md)\)$")
PLAIN_CELL = re.compile(r"^(?P<num>\d{4})$")
REMOVED_STATUS = re.compile(r"^removed \([0-9a-f]{7,40}\)$")
STATUS_PREFIX = "- **Status**:"
# 与 rfcs/README.md 记载的生命周期一致，另加本仓库用于已删除 RFC 的 removed。
STATUS_KEYWORDS = (
    "draft",
    "accepted",
    "implemented",
    "rejected",
    "withdrawn",
    "superseded",
    "removed",
)
LEADING_WORD = re.compile(r"^[\s*`]*([A-Za-z]+)")


def _keyword(status: str) -> str | None:
    """返回状态值开头的封闭集合关键字；不在集合内则返回 None。"""
    match = LEADING_WORD.match(status)
    word = match[1].casefold() if match else None
    return word if word in STATUS_KEYWORDS else None


def _index_rows() -> list[tuple[str, str | None, str]]:
    """返回连续索引表中的 (编号, 链接文件或 None, 状态) 行。"""
    lines = README_PATH.read_text(encoding="utf-8").splitlines()
    start = lines.index(INDEX_HEADER) + 2  # 跳过表头与分隔行
    rows: list[tuple[str, str | None, str]] = []
    for line in lines[start:]:
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        assert len(cells) == 3, f"index row must have 3 cells: {line!r}"
        linked = LINKED_CELL.match(cells[0])
        plain = PLAIN_CELL.match(cells[0])
        if linked:
            rows.append((linked["num"], linked["file"], cells[2]))
        elif plain:
            rows.append((plain["num"], None, cells[2]))
        else:
            raise AssertionError(f"unrecognised RFC cell: {cells[0]!r}")
    return rows


def _rfc_file_names() -> list[str]:
    """返回全部 RFC 文件名（不按编号折叠，以便发现编号冲突）。"""
    return sorted(
        path.name
        for path in RFC_ROOT.glob("[0-9][0-9][0-9][0-9]-*.md")
        if not path.name.startswith("0000-")
    )


def _file_status(file_name: str) -> str:
    """返回 ``Status`` 值，并拼接缩进的续行。"""
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
    counts = Counter(num for num, _, _ in _index_rows())
    assert sorted(num for num, count in counts.items() if count > 1) == []


def test_rfc_file_number_prefixes_are_unique() -> None:
    # rfcs/README.md 规定编号冲突时后合并者改号；两个同号文件必须被拦下。
    counts = Counter(name[:4] for name in _rfc_file_names())
    assert sorted(num for num, count in counts.items() if count > 1) == []


def test_every_rfc_file_is_indexed_with_a_link() -> None:
    linked = {file for _, file, _ in _index_rows() if file is not None}
    assert sorted(set(_rfc_file_names()) - linked) == []


def test_every_index_row_links_an_existing_file_or_is_marked_removed() -> None:
    numbers = {name[:4] for name in _rfc_file_names()}
    problems: list[str] = []
    for num, file, status in _index_rows():
        if file is None:
            if not REMOVED_STATUS.match(status):
                problems.append(f"{num}: unlinked row not marked 'removed (<sha>)'")
            if num in numbers:
                problems.append(f"{num}: marked removed but an RFC file exists")
        elif not (RFC_ROOT / file).is_file():
            problems.append(f"{num}: dead link {file}")
        elif file[:4] != num:
            problems.append(f"{num}: link number mismatch {file}")
    assert problems == []


def test_every_rfc_status_line_starts_with_a_keyword() -> None:
    missing = {
        file: _file_status(file).strip()
        for file in _rfc_file_names()
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
