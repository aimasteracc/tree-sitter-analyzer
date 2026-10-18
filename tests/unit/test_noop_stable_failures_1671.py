"""#1671：只有稳定失败（与活动版本相同）的零变化刷新不发布新版本。

dogfood 第 8 轮：本仓库含缺少可选语法的文件（swift、lua），每次
``index action=cache mode=index`` 都报告 ``errors: 3``，#1631 的零变化判定因而
从不成立：每次刷新都复制并发布一份 343 MB 的新版本、耗时约 70 秒，并让下一次
``nav callers`` 重建内存图。

“稳定”的精确定义：同一文件、同一内容摘要、同一失败原因，与活动版本记录的
稳定失败逐项相同。文件字节变化、失败原因变化、失败消失、增删文件、仅元数据
变化都不是零变化，照常发布（RFC-0030：证据基于内容摘要，绝不只看路径）。
"""

from __future__ import annotations

import os
import sqlite3
from types import SimpleNamespace

import pytest

_A = "from b import beta\n\n\ndef alpha():\n    return beta()\n"
_A_EDITED = "from b import beta\n\n\ndef alpha_edited():\n    return beta()\n"
_B = "def beta():\n    return 3\n"
_BROKEN = "def broken():\n    return 4\n"
_REASON = 'Swift grammar not installed — pip install "tree-sitter-analyzer[swift]"'
_OTHER_REASON = "parse failed: syntax error at line 1"


@pytest.fixture
def failure():
    """注入的稳定失败：``reason`` 为 None 时 broken.py 正常解析。"""
    return SimpleNamespace(reason=_REASON)


@pytest.fixture
def root(tmp_path, monkeypatch, failure):
    from tree_sitter_analyzer.core.parser import Parser
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    project = tmp_path / "project"
    project.mkdir()
    (project / "a.py").write_text(_A, encoding="utf-8")
    (project / "b.py").write_text(_B, encoding="utf-8")
    (project / "broken.py").write_text(_BROKEN, encoding="utf-8")
    original = Parser.parse_code

    def parse_code(self, source_code, language, filename=None, *args, **kwargs):
        if (
            failure.reason is not None
            and filename is not None
            and os.path.basename(filename) == "broken.py"
        ):
            return SimpleNamespace(success=False, error_message=failure.reason)
        return original(self, source_code, language, filename, *args, **kwargs)

    monkeypatch.setattr(Parser, "parse_code", parse_code)
    auto_index_guard.reset()
    yield str(project)
    auto_index_guard.reset()


@pytest.fixture
def copies(monkeypatch):
    """记录私有副本的创建次数（每次 ``begin`` 都复制整份父版本）。"""
    from tree_sitter_analyzer.cache.generation_store import GenerationStore

    calls: list[str] = []
    original = GenerationStore.begin

    def begin(self, candidate):
        calls.append(str(self.root))
        return original(self, candidate)

    monkeypatch.setattr(GenerationStore, "begin", begin)
    return calls


def _index_project(root):
    from tree_sitter_analyzer.ast_cache import ASTCache

    cache = ASTCache(root)
    try:
        result = cache.index_project(workers=0)
    finally:
        cache.close()
    return result["published"], result.get("publication_reason")


def _sync(root):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.incremental_sync import IncrementalSync
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    scope = make_source_scope_descriptor()
    cache = ASTCache(root)
    try:
        result = IncrementalSync(cache).sync(
            max_files=scope.certification_max_files,
            exclude_patterns=scope.effective_excludes,
            source_scope=scope,
        )
    finally:
        cache.close()
    return result.published, result.publication_reason


_ROUTES = {"index_project": _index_project, "sync": _sync}


def _active(root) -> str:
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    location = resolve_index_location(root)
    selector = location.selector
    assert (location.published, type(selector).__name__) == (
        True,
        "GenerationSelector",
    )
    return str(getattr(selector, "generation_id", ""))


def _symbols(root) -> list[str]:
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    path = resolve_index_location(root).path
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        return [
            row[0]
            for row in connection.execute(
                "SELECT name FROM ast_symbol_rows ORDER BY name"
            )
        ]
    finally:
        connection.close()


def _write(root, name, text, *, bump_ns=2_000_000_000):
    path = os.path.join(root, name)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(text)
    info = os.stat(path)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + bump_ns))


def _established(root, route):
    """首次发布后再刷新一次，得到一个记录了稳定失败的活动版本。"""
    refresh = _ROUTES[route]
    first = refresh(root)
    assert first[0] is True
    return refresh


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_noop_refresh_with_only_stable_failures_does_not_publish(
    root, route, copies
) -> None:
    refresh = _established(root, route)
    active = _active(root)
    copies.clear()

    second = refresh(root)
    third = refresh(root)

    # 不发布、活动版本不变，且根本没有复制父版本（零变化只付遍历与摘要的成本）。
    assert (second, third, _active(root), copies) == (
        (False, "INDEX_UNCHANGED"),
        (False, "INDEX_UNCHANGED"),
        active,
        [],
    )


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_noop_refresh_of_complete_index_does_not_copy(root, route, copies) -> None:
    # 负对照：没有失败文件的已认证版本，零变化刷新同样不复制、不发布。
    os.remove(os.path.join(root, "broken.py"))
    refresh = _established(root, route)
    active = _active(root)
    copies.clear()

    assert (refresh(root), _active(root), copies) == (
        (False, "INDEX_UNCHANGED"),
        active,
        [],
    )


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_changed_bytes_of_the_failing_file_publish(root, route) -> None:
    # 同一文件、同一原因，但内容摘要不同：不是同一个稳定失败。
    refresh = _established(root, route)
    active = _active(root)
    _write(root, "broken.py", _BROKEN + "\n# edited\n")

    assert refresh(root) == (True, None)
    assert _active(root) != active


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_changed_failure_reason_publishes_then_settles(root, route, failure) -> None:
    # 同一字节、不同原因（如换了解析器或语法包）：发布一次，之后新原因成为稳定失败。
    refresh = _established(root, route)
    active = _active(root)
    failure.reason = _OTHER_REASON

    assert refresh(root) == (True, None)
    changed = _active(root)
    assert changed != active
    assert (refresh(root), _active(root)) == ((False, "INDEX_UNCHANGED"), changed)


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_resolved_failure_publishes_the_file(root, route, failure) -> None:
    # 语法包装好了：同一字节现在能解析，必须发布并入索引。
    refresh = _established(root, route)
    failure.reason = None

    assert refresh(root) == (True, None)
    assert "broken" in _symbols(root)


@pytest.mark.parametrize("route", sorted(_ROUTES))
@pytest.mark.parametrize("change", ["edit", "add", "delete", "touch"])
def test_source_changes_beside_a_stable_failure_publish(root, route, change) -> None:
    refresh = _established(root, route)
    active = _active(root)
    if change == "edit":
        _write(root, "a.py", _A_EDITED)
    elif change == "add":
        _write(root, "c.py", "def gamma():\n    return 5\n")
    elif change == "delete":
        os.remove(os.path.join(root, "b.py"))
    else:
        # 只改 mtime：内容摘要相同，但索引记录的元数据必须与磁盘一致。
        _write(root, "a.py", _A)

    published = refresh(root)

    assert published == (True, None)
    assert _active(root) != active


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_extractor_version_bump_publishes(root, route, monkeypatch) -> None:
    from tree_sitter_analyzer.cache import indexer

    refresh = _established(root, route)
    monkeypatch.setattr(
        indexer,
        "_AST_CACHE_EXTRACTOR_VERSION",
        indexer._AST_CACHE_EXTRACTOR_VERSION + 1,
    )

    assert refresh(root) == (True, None)


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_single_file_write_drops_the_stable_failure_record(root, route) -> None:
    # 单文件写入（不跑完整调用图流水线）产生的版本不能继承父版本的稳定失败记录：
    # 否则其后的零变化判定会把未经回填的图当作已收敛的结果永久保留。
    from tree_sitter_analyzer.ast_cache import ASTCache

    refresh = _established(root, route)
    _write(root, "a.py", _A_EDITED)
    cache = ASTCache(root)
    try:
        assert cache.index_file(os.path.join(root, "a.py"))["status"] == "indexed"
    finally:
        cache.close()
    after_single = _active(root)

    assert refresh(root) == (True, None)
    assert _active(root) != after_single
    assert refresh(root) == (False, "INDEX_UNCHANGED")


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_same_metadata_different_bytes_publish(root, route) -> None:
    # 同样大小、同样 mtime、不同字节：只有内容摘要能看出变化（RFC-0030）。
    refresh = _established(root, route)
    path = os.path.join(root, "b.py")
    info = os.stat(path)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(_B.replace("3", "7"))
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
    assert os.stat(path).st_size == info.st_size

    assert refresh(root) == (True, None)


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_single_file_write_on_a_complete_parent_is_refreshed(root, route) -> None:
    # 已认证父版本之后经单文件路由写入的版本不带收敛记录：其后的刷新必须照常
    # 运行（重新盖清单），不能把单文件写入留下的清单当作零变化保留。
    from tree_sitter_analyzer.ast_cache import ASTCache

    os.remove(os.path.join(root, "broken.py"))
    refresh = _established(root, route)
    _write(root, "b.py", _B + "\n\ndef beta2():\n    return beta()\n")
    cache = ASTCache(root)
    try:
        assert cache.index_file(os.path.join(root, "b.py"))["status"] == "indexed"
    finally:
        cache.close()
    after_single = _active(root)

    assert refresh(root) == (True, None)
    assert _active(root) != after_single
    assert refresh(root) == (False, "INDEX_UNCHANGED")


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_line_ending_change_with_same_mtime_publishes(root, route) -> None:
    # 只换行符不同：归一化后的内容摘要相同，但大小不同；索引记录的大小必须更新。
    refresh = _established(root, route)
    path = os.path.join(root, "b.py")
    info = os.stat(path)
    with open(path, "rb") as stream:
        data = stream.read()
    toggled = (
        data.replace(b"\r\n", b"\n")
        if b"\r\n" in data
        else data.replace(b"\n", b"\r\n")
    )
    with open(path, "wb") as stream:
        stream.write(toggled)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
    assert os.stat(path).st_size != info.st_size

    assert refresh(root) == (True, None)


def test_failed_certification_is_not_a_noop(root, monkeypatch) -> None:
    # 清单盖戳失败的运行不签发收敛记录：其后的零变化刷新必须照常运行并重新盖戳。
    from tree_sitter_analyzer import index_snapshot_schema

    os.remove(os.path.join(root, "broken.py"))
    refresh = _established(root, "index_project")
    original = index_snapshot_schema.stamp_full_index_manifest

    def refuse(*_args, **_kwargs):
        raise RuntimeError("stamp refused for the test")

    monkeypatch.setattr(index_snapshot_schema, "stamp_full_index_manifest", refuse)
    _write(root, "b.py", _B + "\n\ndef beta3():\n    return 9\n")
    refresh(root)
    monkeypatch.setattr(index_snapshot_schema, "stamp_full_index_manifest", original)

    assert refresh(root) == (True, None)
    assert refresh(root) == (False, "INDEX_UNCHANGED")


@pytest.mark.parametrize("failing", [True, False])
def test_changed_source_scope_publishes(root, failing) -> None:
    # 范围描述（排除模式）不同，即使选中文件相同，清单与记录也必须按新范围重签。
    from tree_sitter_analyzer.ast_cache import ASTCache

    if not failing:
        os.remove(os.path.join(root, "broken.py"))
    _established(root, "index_project")
    cache = ASTCache(root)
    try:
        result = cache.index_project(
            workers=0, exclude_patterns=frozenset({"no_such_dir/*"})
        )
    finally:
        cache.close()

    assert (result["published"], result.get("publication_reason")) == (True, None)


@pytest.mark.parametrize("mode", ["full", "incremental"])
def test_refresh_after_full_index_is_a_noop(root, mode, copies) -> None:
    # dogfood 第 8 轮的复现步骤：先 ``index action=full``，再零变化的
    # ``index action=cache mode=index``——后者不得复制、不得发布。
    import asyncio

    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    built = asyncio.run(CodeGraphFullIndexTool(root).execute({"mode": mode}))
    assert built["published"] is True
    active = _active(root)
    copies.clear()

    assert (_index_project(root), _active(root), copies) == (
        (False, "INDEX_UNCHANGED"),
        active,
        [],
    )


def test_noop_against_a_superseded_parent_is_not_reported_unchanged(
    root, monkeypatch
) -> None:
    # 比较完成后、返回之前另一写入者发布了更新的版本：不能报告“与活动版本相同”。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache import generation_noop_precheck

    _established(root, "index_project")
    original = generation_noop_precheck._evidence
    interleaved: list[bool] = []

    def then_publish(*args, **kwargs):
        evidence = original(*args, **kwargs)
        if not interleaved:
            interleaved.append(True)
            _write(root, "c.py", "def gamma():\n    return 5\n")
            # 另一写入者经同步路由发布（项目索引路由持有同进程写锁）。
            assert _sync(root) == (True, None)
        return evidence

    monkeypatch.setattr(generation_noop_precheck, "_evidence", then_publish)
    cache = ASTCache(root)
    try:
        result = cache.index_project(workers=0)
    except Exception as exc:  # 准入拒绝以类型化异常越过 Python 入口
        result = {"error": type(exc).__name__}
    finally:
        cache.close()

    assert result.get("publication_reason") != "INDEX_UNCHANGED"


def test_unchanged_mcp_refresh_reports_stable_failures(root) -> None:
    # MCP 答复如实说明：未发布、原因 INDEX_UNCHANGED，且稳定失败仍计入 errors。
    import asyncio

    from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

    tool = ASTCacheTool(root)
    first = asyncio.run(tool.execute({"mode": "index"}))
    second = asyncio.run(tool.execute({"mode": "index"}))

    assert (first["published"], first["errors"]) == (True, 1)
    assert (
        second["published"],
        second["publication_reason"],
        second["errors"],
        second["indexed"],
    ) == (False, "INDEX_UNCHANGED", 1, 0)
    assert second["summary_line"].startswith("ast_cache index project files=0 ")
