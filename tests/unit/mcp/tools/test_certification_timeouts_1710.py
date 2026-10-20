"""#1710：认证捕获超时的记忆——只跳过注定超时的捕获，答案与认证状态不变。

跳过捕获与捕获超时走同一条未认证回退路径，所以答案逐字节相同；记忆从不让答案
变成“已认证”。状态（索引身份、已索引文件与其目录的 stat）一变就重新尝试。
每个键成分都做过变异检验：强制“总是命中”会让这里至少一个测试变红。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools import certification_timeouts as timeouts

_AN_HOUR_NS = 3600 * 1_000_000_000
_DEADLINE = "INDEX_SNAPSHOT_DEADLINE"


def _backdate(path: Path, offset_ns: int = _AN_HOUR_NS) -> None:
    stamp = time.time_ns() - offset_ns
    os.utime(path, ns=(stamp, stamp))


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(timeouts.DIR_ENV, str(tmp_path / "timeouts"))
    timeouts.clear()
    yield
    timeouts.clear()


async def _index(root: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    result = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert result["published"] is True


_WIDGET = (
    "class Widget:\n"
    "    def unused(self):\n"
    "        return 0\n\n"
    "    def used(self):\n"
    "        return 1\n\n\n"
    "def run(w):\n"
    "    return w.used()\n"
)


@pytest.fixture
async def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "widget.py").write_text(_WIDGET, encoding="utf-8")
    (root / "pkg" / "helper.py").write_text("def helper():\n    return 3\n")
    await _index(root)
    for path in (root / "widget.py", root / "pkg" / "helper.py", root / "pkg", root):
        _backdate(path)
    return root


def _new_process() -> None:
    timeouts.clear()


# --------------------------------------------------------------------------- #
# 记忆本身
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_a_recorded_timeout_is_skipped_until_the_state_changes(project) -> None:
    assert timeouts.should_skip(str(project)) is False

    timeouts.record(str(project), _DEADLINE)

    assert timeouts.should_skip(str(project)) is True
    _new_process()
    assert timeouts.should_skip(str(project)) is True  # 落盘记录


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["add_file", "delete_file", "add_directory", "rename"]
)
async def test_any_change_to_the_file_set_retries_the_capture(
    project, change: str
) -> None:
    timeouts.record(str(project), _DEADLINE)
    if change == "add_file":
        (project / "pkg" / "caller.py").write_text("x = 1\n")
    elif change == "delete_file":
        (project / "pkg" / "helper.py").unlink()
    elif change == "add_directory":
        (project / "newdir").mkdir()
    else:
        (project / "pkg" / "helper.py").rename(project / "pkg" / "helper2.py")

    assert timeouts.should_skip(str(project)) is False
    _new_process()
    assert timeouts.should_skip(str(project)) is False


@pytest.mark.asyncio
async def test_a_content_edit_without_refresh_keeps_skipping_until_reindexed(
    project,
) -> None:
    # 源码与索引戳记不一致时认证本就无法完成；刷新改变索引身份才重新尝试。
    timeouts.record(str(project), _DEADLINE)
    (project / "pkg" / "helper.py").write_text("def helper():\n    return 4\n")

    assert timeouts.should_skip(str(project)) is True
    await _index(project)
    assert timeouts.should_skip(str(project)) is False


@pytest.mark.asyncio
async def test_a_reindexed_project_retries_the_capture(project) -> None:
    timeouts.record(str(project), _DEADLINE)
    await _index(project)

    assert timeouts.should_skip(str(project)) is False


@pytest.mark.asyncio
async def test_the_key_includes_the_code_fingerprint(project, monkeypatch) -> None:
    import tree_sitter_analyzer.source_fingerprint as fingerprint

    timeouts.record(str(project), _DEADLINE)
    monkeypatch.setattr(fingerprint, "source_fingerprint", lambda: "other-code")

    assert timeouts.should_skip(str(project)) is False


@pytest.mark.asyncio
async def test_the_capture_is_retried_after_the_retry_interval(
    project, monkeypatch
) -> None:
    timeouts.record(str(project), _DEADLINE)
    later = time.time() + timeouts.RETRY_SECONDS + 1
    monkeypatch.setattr(timeouts, "_now", lambda: later)

    assert timeouts.should_skip(str(project)) is False


@pytest.mark.asyncio
async def test_a_completed_capture_clears_the_record(project, tmp_path) -> None:
    timeouts.record(str(project), _DEADLINE)

    timeouts.record(str(project), None)

    assert timeouts.should_skip(str(project)) is False
    assert list((tmp_path / "timeouts").glob("*.json")) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["CALL_GRAPH_INCOMPLETE", "SOURCE_INDEX_MISMATCH"])
async def test_only_deadline_failures_are_recorded(project, reason: str) -> None:
    timeouts.record(str(project), reason)

    assert timeouts.should_skip(str(project)) is False


@pytest.mark.asyncio
async def test_a_record_for_another_root_or_format_is_ignored(
    project, tmp_path
) -> None:
    timeouts.record(str(project), _DEADLINE)
    (stored,) = list((tmp_path / "timeouts").glob("*.json"))
    payload = json.loads(stored.read_text(encoding="utf-8"))
    for changed in (
        {**payload, "root": str(tmp_path)},
        {**payload, "format": timeouts.FORMAT + 1},
        {**payload, "key": 7},
        {**payload, "recorded_at": "now"},
    ):
        stored.write_text(json.dumps(changed), encoding="utf-8")
        _new_process()
        assert timeouts.should_skip(str(project)) is False, changed
    stored.write_text("not json", encoding="utf-8")
    _new_process()
    assert timeouts.should_skip(str(project)) is False


@pytest.mark.asyncio
async def test_with_the_store_off_the_record_is_in_process_only(
    project, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv(timeouts.DIR_ENV, "off")
    timeouts.record(str(project), _DEADLINE)

    assert timeouts.should_skip(str(project)) is True
    assert not (tmp_path / "timeouts").exists()
    _new_process()
    assert timeouts.should_skip(str(project)) is False


def test_no_index_is_never_recorded(tmp_path: Path) -> None:
    timeouts.record(str(tmp_path), _DEADLINE)

    assert timeouts.should_skip(str(tmp_path)) is False
    assert timeouts.evidence_key(str(tmp_path)) is None


# --------------------------------------------------------------------------- #
# 端到端：nav callers 的答案与认证状态
# --------------------------------------------------------------------------- #


def _without_timing(response: dict) -> dict:
    return {key: value for key, value in response.items() if "elapsed" not in key}


async def _callers(root: Path, name: str) -> dict:
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    return await CodeGraphCallersTool(str(root)).execute(
        {"function_name": name, "include_bodies": False}
    )


@pytest.fixture
def timing_out_captures(monkeypatch) -> list[int]:
    """让每次认证捕获都像超时一样失败，并统计尝试次数。"""
    from tree_sitter_analyzer import index_snapshot

    attempts: list[int] = []

    def deadline(project_root, *, pin=False, deadline=None):
        attempts.append(1)
        return index_snapshot._unknown(_DEADLINE)

    monkeypatch.setattr(index_snapshot, "_capture_existing_snapshot", deadline)
    return attempts


@pytest.mark.asyncio
async def test_a_timed_out_capture_is_not_attempted_again(
    project, timing_out_captures
) -> None:
    first = await _callers(project, "Widget.used")
    second = await _callers(project, "Widget.used")
    _new_process()
    third = await _callers(project, "Widget.used")

    assert len(timing_out_captures) == 1
    assert _without_timing(first) == _without_timing(second) == _without_timing(third)


@pytest.mark.asyncio
async def test_skipped_answers_equal_attempted_answers(
    project, timing_out_captures, monkeypatch
) -> None:
    for name in ("Widget.unused", "Widget.used", "helper", "run", "missing_name"):
        timeouts.clear()
        monkeypatch.setenv(timeouts.DIR_ENV, "off")
        attempted = await _callers(project, name)
        skipped = await _callers(project, name)
        assert _without_timing(attempted) == _without_timing(skipped), name


@pytest.mark.asyncio
async def test_a_new_file_after_a_timeout_attempts_the_capture_again(
    project, timing_out_captures
) -> None:
    await _callers(project, "Widget.used")
    (project / "pkg" / "caller.py").write_text("def go(w):\n    return w.used()\n")

    await _callers(project, "Widget.used")

    assert len(timing_out_captures) == 2


@pytest.mark.asyncio
async def test_a_capture_that_completes_still_certifies(project, monkeypatch) -> None:
    # 记忆只针对期限类失败：能完成的捕获照常给出认证读取。
    from tree_sitter_analyzer import index_snapshot

    entered: list[str] = []
    original = index_snapshot.certified_index_read

    def spy(root: str):
        entered.append(root)
        return original(root)

    monkeypatch.setattr(index_snapshot, "certified_index_read", spy)
    await _callers(project, "Widget.used")
    await _callers(project, "Widget.used")

    assert entered == [str(project), str(project)]
    assert timeouts.should_skip(str(project)) is False


# --------------------------------------------------------------------------- #
# 落盘层与证据的失败路径
# --------------------------------------------------------------------------- #


def test_store_dir_switches(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(timeouts.STORE_ENV, "off")
    assert timeouts.store_dir() is None
    monkeypatch.delenv(timeouts.STORE_ENV)
    monkeypatch.delenv(timeouts.DIR_ENV)
    assert (
        timeouts.store_dir()
        == Path.home() / ".tsa" / "cache" / "certification-timeouts"
    )


@pytest.mark.asyncio
async def test_an_unreadable_index_is_never_recorded(project, monkeypatch) -> None:
    from tree_sitter_analyzer.mcp.tools import relation_freshness

    monkeypatch.setattr(
        relation_freshness, "index_identity", lambda _root: ("db", "g", "unreadable")
    )
    timeouts.record(str(project), _DEADLINE)

    assert timeouts.evidence_key(str(project)) is None
    assert timeouts.should_skip(str(project)) is False


@pytest.mark.asyncio
async def test_an_unreadable_file_list_is_never_recorded(project, monkeypatch) -> None:
    monkeypatch.setattr(timeouts, "_indexed_files", lambda _root: None)

    assert timeouts.evidence_key(str(project)) is None


@pytest.mark.asyncio
async def test_a_store_write_failure_keeps_the_in_process_record(
    project, monkeypatch
) -> None:
    def refuse(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(timeouts.os, "replace", refuse)
    timeouts.record(str(project), _DEADLINE)

    assert timeouts.should_skip(str(project)) is True
    _new_process()
    assert timeouts.should_skip(str(project)) is False


@pytest.mark.asyncio
async def test_a_completed_capture_in_a_new_process_removes_the_stored_record(
    project, tmp_path
) -> None:
    timeouts.record(str(project), _DEADLINE)
    _new_process()

    timeouts.record(str(project), None)

    assert list((tmp_path / "timeouts").glob("*.json")) == []


@pytest.mark.asyncio
async def test_a_record_that_cannot_be_removed_is_ignored(project, monkeypatch) -> None:
    timeouts.record(str(project), _DEADLINE)

    def refuse(self, *args, **kwargs):
        raise OSError("locked")

    monkeypatch.setattr(timeouts.Path, "unlink", refuse)
    timeouts.record(str(project), None)  # 不抛出

    assert timeouts.should_skip(str(project)) is False


def test_the_file_list_of_a_missing_index_is_none(tmp_path: Path) -> None:
    assert timeouts._indexed_files(str(tmp_path)) is None
