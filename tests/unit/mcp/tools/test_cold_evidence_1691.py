"""#1691：冷进程的首个 ``nav callers`` 不再重付完整性证据——答案不得改变。

* 遍历证据落盘（``walk_evidence_store``）：新进程（这里用新的
  ``ProjectWalkCache`` 实例模拟）只在每条 ``lstat`` 证据重新复核一致时复用；
  新文件、删除文件、``.gitignore`` 改写、键（代码指纹 / 参数）变化都使其失效，
  竞争窗口内的遍历从不落盘，损坏的文件当作未命中。
* 注释 / 字符串剥离换用首字符可跳过的展开循环正则：匹配位置与分类必须与原
  正则逐个相同（这里用原正则作参照，对随机与刁钻输入逐一比对）。
"""

from __future__ import annotations

import os
import random
import re
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools import (
    callers_absence,
    evidence_file_cache,
    project_walk_cache,
    walk_evidence_store,
)
from tree_sitter_analyzer.mcp.tools.project_walk_cache import ProjectWalkCache

_AN_HOUR_NS = 3600 * 1_000_000_000
_KEY = ("excluded", 100, 200)


def _backdate(path: Path, offset_ns: int = _AN_HOUR_NS) -> None:
    stamp = time.time_ns() - offset_ns
    os.utime(path, ns=(stamp, stamp))


def _backdate_tree(root: Path, offset_ns: int = _AN_HOUR_NS) -> None:
    for current, dirs, files in os.walk(root, topdown=False):
        if ".ast-cache" in Path(current).parts:
            continue
        for name in files:
            _backdate(Path(current) / name, offset_ns)
        for name in dirs:
            if name != ".ast-cache":
                _backdate(Path(current) / name, offset_ns)
    _backdate(root, offset_ns)


def _counting_walker(root: Path, calls: list[int]):
    """遍历 ``root``（跳过点目录、按 ``.gitignore`` 的 ``*.ext`` 规则过滤）。"""

    def walker(visited: list[str]) -> list[str]:
        calls.append(1)
        ignore = root / ".gitignore"
        patterns = ignore.read_text().split() if ignore.exists() else []
        found: list[str] = []
        for current, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            relative = os.path.relpath(current, root)
            visited.append("" if relative == "." else relative)
            found.extend(
                os.path.join(current, name)
                for name in sorted(files)
                if not any(Path(name).match(pattern) for pattern in patterns)
                and not name.startswith(".")
            )
        return found

    return walker


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / ".ast-cache").mkdir()
    (root / "a.py").write_text("a\n")
    (root / "pkg" / "b.py").write_text("b\n")
    (root / "pkg" / "c.log").write_text("log\n")
    (root / ".gitignore").write_text("*.log\n")
    _backdate_tree(root)
    return root


def _stored_files(root: Path) -> list[Path]:
    return sorted((root / ".ast-cache" / walk_evidence_store.DIR_NAME).glob("walk-*"))


def _fresh_process_walk(root: Path, calls: list[int]) -> tuple[str, ...]:
    """新的记忆实例（如同新进程）走一次，返回结果。"""
    return ProjectWalkCache(persist=True).walk(
        str(root), _KEY, "", _counting_walker(root, calls)
    )


def test_a_new_process_reuses_the_stored_walk(tree: Path) -> None:
    calls: list[int] = []
    first = _fresh_process_walk(tree, calls)
    assert len(_stored_files(tree)) == 1

    second = _fresh_process_walk(tree, calls)

    assert second == first
    assert len(calls) == 1


def test_the_stored_walk_misses_after_a_new_file(tree: Path) -> None:
    calls: list[int] = []
    _fresh_process_walk(tree, calls)

    (tree / "pkg" / "new.py").write_text("n\n")
    result = _fresh_process_walk(tree, calls)

    assert str(tree / "pkg" / "new.py") in result
    assert len(calls) == 2


def test_the_stored_walk_misses_after_a_deleted_file(tree: Path) -> None:
    calls: list[int] = []
    _fresh_process_walk(tree, calls)

    (tree / "pkg" / "b.py").unlink()
    result = _fresh_process_walk(tree, calls)

    assert str(tree / "pkg" / "b.py") not in result
    assert len(calls) == 2


def test_the_stored_walk_misses_after_a_gitignore_edit(tree: Path) -> None:
    calls: list[int] = []
    first = _fresh_process_walk(tree, calls)
    assert str(tree / "pkg" / "c.log") not in first
    directory_before = os.lstat(tree).st_mtime_ns

    # 只改写规则文件内容：目录 mtime 不变，规则文件自身的 lstat 必须使其失效。
    (tree / ".gitignore").write_text("*.tmp\n")
    assert os.lstat(tree).st_mtime_ns == directory_before
    result = _fresh_process_walk(tree, calls)

    assert str(tree / "pkg" / "c.log") in result
    assert len(calls) == 2


def test_an_edited_file_keeps_the_stored_walk_and_its_result(tree: Path) -> None:
    # 遍历只列出名字：改写已有文件的内容不改变结果，复用的结果与重走的相同。
    calls: list[int] = []
    first = _fresh_process_walk(tree, calls)

    (tree / "a.py").write_text("edited\n")
    reused = _fresh_process_walk(tree, calls)

    assert reused == first == tuple(_counting_walker(tree, [])([]))
    assert len(calls) == 1


def test_a_racy_walk_is_never_stored(tree: Path) -> None:
    (tree / "pkg" / "fresh.py").write_text("f\n")  # pkg 的 mtime 落入竞争窗口
    calls: list[int] = []

    _fresh_process_walk(tree, calls)
    _fresh_process_walk(tree, calls)

    assert _stored_files(tree) == []
    assert len(calls) == 2


def test_the_stored_walk_is_keyed_on_the_walk_parameters(tree: Path) -> None:
    calls: list[int] = []
    walker = _counting_walker(tree, calls)
    ProjectWalkCache(persist=True).walk(str(tree), ("budget", 1), "", walker)

    ProjectWalkCache(persist=True).walk(str(tree), ("budget", 2), "", walker)

    assert len(calls) == 2


def test_the_stored_walk_is_keyed_on_the_code_fingerprint(
    tree: Path, monkeypatch
) -> None:
    import tree_sitter_analyzer.source_fingerprint as fingerprint

    calls: list[int] = []
    _fresh_process_walk(tree, calls)

    monkeypatch.setattr(fingerprint, "source_fingerprint", lambda: "other-code")
    _fresh_process_walk(tree, calls)

    assert len(calls) == 2


def test_the_stored_walk_is_keyed_on_the_start_directory(tree: Path) -> None:
    calls: list[int] = []
    walker = _counting_walker(tree, calls)
    ProjectWalkCache(persist=True).walk(str(tree), _KEY, "", walker)

    ProjectWalkCache(persist=True).walk(str(tree), _KEY, "pkg", walker)

    assert len(calls) == 2


def test_a_corrupt_stored_walk_is_a_miss(tree: Path) -> None:
    calls: list[int] = []
    first = _fresh_process_walk(tree, calls)
    (stored,) = _stored_files(tree)
    stored.write_bytes(b"\x00not marshal")

    result = _fresh_process_walk(tree, calls)

    assert result == first
    assert len(calls) == 2


def test_a_stored_walk_with_another_key_text_is_a_miss(tree: Path) -> None:
    import marshal

    calls: list[int] = []
    _fresh_process_walk(tree, calls)
    (stored,) = _stored_files(tree)
    _format, _text, evidence, paths = marshal.loads(stored.read_bytes())
    stored.write_bytes(marshal.dumps((_format, "another key", evidence, paths)))

    _fresh_process_walk(tree, calls)

    assert len(calls) == 2


def test_the_store_can_be_turned_off(tree: Path, monkeypatch) -> None:
    monkeypatch.setenv(walk_evidence_store.ENV_VAR, "off")
    calls: list[int] = []

    _fresh_process_walk(tree, calls)
    _fresh_process_walk(tree, calls)

    assert _stored_files(tree) == []
    assert len(calls) == 2


def test_nothing_is_stored_without_an_ast_cache_directory(tree: Path) -> None:
    (tree / ".ast-cache").rmdir()
    calls: list[int] = []

    _fresh_process_walk(tree, calls)

    assert not (tree / ".ast-cache").exists()


def test_an_in_process_cache_without_persist_never_touches_the_store(
    tree: Path,
) -> None:
    calls: list[int] = []
    ProjectWalkCache().walk(str(tree), _KEY, "", _counting_walker(tree, calls))

    assert _stored_files(tree) == []


def test_old_stored_walks_are_pruned(tree: Path) -> None:
    walker = _counting_walker(tree, [])
    for budget in range(walk_evidence_store.KEEP + 3):
        ProjectWalkCache(persist=True).walk(str(tree), ("budget", budget), "", walker)

    assert len(_stored_files(tree)) == walk_evidence_store.KEEP


# --------------------------------------------------------------------------- #
# 端到端：真实索引上，新进程复用落盘遍历的答案 == 关闭落盘层时的答案
# --------------------------------------------------------------------------- #


async def _full_index(root: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True


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
async def indexed_root(tmp_path):
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "widget.py").write_text(_WIDGET, encoding="utf-8")
    (root / "pkg" / "helper.py").write_text("def helper():\n    return 3\n")
    await _full_index(root)
    _backdate_tree(root)
    _new_process()
    yield root
    _new_process()


def _new_process() -> None:
    """清空全部进程内证据记忆：之后的调用如同新进程的首个调用。"""
    from tree_sitter_analyzer.cache import query_cost
    from tree_sitter_analyzer.mcp.tools import relation_freshness, unindexed_sources

    evidence_file_cache.FILE_CACHE.clear()
    project_walk_cache.WALK_CACHE.clear()
    relation_freshness._IDENTITY_MEMO.clear()
    query_cost._HOLDS_ROWS_MEMO.clear()
    unindexed_sources._CLASSIFIED_MEMO.clear()


def _without_timing(response: dict) -> dict:
    return {key: value for key, value in response.items() if "elapsed" not in key}


async def _callers(root: Path, name: str) -> dict:
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    return await CodeGraphCallersTool(str(root)).execute(
        {"function_name": name, "include_bodies": False}
    )


async def _unstored_callers(root: Path, name: str, monkeypatch) -> dict:
    """关闭落盘层、清空进程内记忆后的答案（即 #1691 之前冷进程的计算）。"""
    _new_process()
    with monkeypatch.context() as patch:
        patch.setenv(walk_evidence_store.ENV_VAR, "off")
        return await _callers(root, name)


@pytest.fixture
def walk_count(monkeypatch) -> list[int]:
    from tree_sitter_analyzer import index_candidate_walker

    calls: list[int] = []
    original = index_candidate_walker.walk_candidate_entries

    def counting(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(index_candidate_walker, "walk_candidate_entries", counting)
    return calls


@pytest.mark.asyncio
async def test_new_process_answers_from_the_stored_walk(
    indexed_root, walk_count, monkeypatch
) -> None:
    walked_answers = 0
    for name in ("Widget.unused", "Widget.used", "helper", "missing_name"):
        await _callers(indexed_root, name)
        _new_process()
        walk_count.clear()
        cold = await _callers(indexed_root, name)
        stored_walks = len(walk_count)
        unstored = await _unstored_callers(indexed_root, name, monkeypatch)
        assert _without_timing(cold) == _without_timing(unstored), name
        if cold.get("unindexed_source_files") == []:
            # 这个答案经过了未入索引文件门：新进程只复核证据，不再遍历。
            walked_answers += 1
            assert stored_walks == 0, name
    assert walked_answers >= 2


@pytest.mark.asyncio
async def test_new_file_invalidates_the_stored_walk(
    indexed_root, walk_count, monkeypatch
) -> None:
    warm = await _callers(indexed_root, "Widget.unused")
    assert (warm["completeness"], warm["completeness_reason"]) == ("complete", None)

    (indexed_root / "pkg" / "caller.py").write_text("def go(w):\n    w.unused()\n")
    _new_process()
    walk_count.clear()
    result = await _callers(indexed_root, "Widget.unused")

    assert walk_count, "the stored walk must not be reused after a new file"
    assert result["completeness_reason"] == "UNINDEXED_SOURCE_FILES"
    assert result["unindexed_source_files"] == ["pkg/caller.py"]
    assert _without_timing(result) == _without_timing(
        await _unstored_callers(indexed_root, "Widget.unused", monkeypatch)
    )


@pytest.mark.asyncio
async def test_gitignore_change_invalidates_the_stored_walk(
    indexed_root, monkeypatch
) -> None:
    (indexed_root / ".gitignore").write_text("ignored_*.py\n")
    (indexed_root / "ignored_caller.py").write_text("def go(w):\n    w.unused()\n")
    _backdate_tree(indexed_root)
    warm = await _callers(indexed_root, "Widget.unused")
    assert warm["completeness_reason"] is None

    (indexed_root / ".gitignore").write_text("nothing_matches_*.py\n")
    _new_process()
    result = await _callers(indexed_root, "Widget.unused")

    assert result["completeness_reason"] == "UNINDEXED_SOURCE_FILES"
    assert result["unindexed_source_files"] == ["ignored_caller.py"]
    assert _without_timing(result) == _without_timing(
        await _unstored_callers(indexed_root, "Widget.unused", monkeypatch)
    )


@pytest.mark.asyncio
async def test_deleted_and_edited_files_answer_as_without_the_store(
    indexed_root, monkeypatch
) -> None:
    await _callers(indexed_root, "Widget.unused")
    helper = indexed_root / "pkg" / "helper.py"
    helper.write_text("def helper(w):\n    return w.unused\n")
    _new_process()
    edited = await _callers(indexed_root, "Widget.unused")
    assert edited["completeness_reason"] == "SOURCE_INDEX_MISMATCH"
    assert _without_timing(edited) == _without_timing(
        await _unstored_callers(indexed_root, "Widget.unused", monkeypatch)
    )

    helper.unlink()
    _new_process()
    deleted = await _callers(indexed_root, "Widget.unused")
    assert _without_timing(deleted) == _without_timing(
        await _unstored_callers(indexed_root, "Widget.unused", monkeypatch)
    )


# --------------------------------------------------------------------------- #
# 剥离器的正则：与原正则逐个匹配相同
# --------------------------------------------------------------------------- #

#: #1691 之前的写法（参照）：注释为组 1，字符串为组 2。
_PY_REFERENCE = re.compile(
    r"(#[^\n]*)"
    r"|(\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?'''|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*')"
)
_C_REFERENCE = re.compile(
    r"(//[^\n]*|/\*[\s\S]*?\*/)" r"|(\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*')"
)

_TRICKY = [
    "",
    '"""',
    '""""',
    '"""""',
    '""""""',
    '"""a""""',
    "'''a''''b'''",
    '"a\\"b"',
    '"a\\\nb"',
    '"unterminated\nx = 1',
    "'\\\\'",
    "'\\'",
    "# c 'q' \"q\"\nx = 'a#b'",
    'f"{x!r}" + rb"\\x" + u\'y\'',
    '"""doc\n>>> f()\n"""\n',
    "/* a */ /** b **/ /*/ c */ /* * / */ // d\n'e' \"f\"",
    "/* unterminated\n x",
    "/**/ /***/ /*a*b*/",
    "x = '''\n'''''' '''",
    "\"\\",
    "'\\\n'",
]


def _spans(pattern: re.Pattern[str], text: str, reference: bool) -> list:
    if reference:
        return [(m.span(), m.group(2) is not None) for m in pattern.finditer(text)]
    return [(m.span(), m.group(0)[0] in "\"'") for m in pattern.finditer(text)]


def _random_texts(seed: int, count: int) -> list[str]:
    rng = random.Random(seed)
    alphabet = ['"', "'", "\\", "\n", "#", "/", "*", "a", " ", "f", "(", "x"]
    weights = [6, 6, 3, 3, 2, 3, 3, 4, 3, 1, 1, 1]
    return [
        "".join(rng.choices(alphabet, weights, k=rng.randint(0, 60)))
        for _ in range(count)
    ]


@pytest.mark.parametrize(
    ("new", "reference"),
    [
        (callers_absence._PY_LEXEME, _PY_REFERENCE),
        (callers_absence._C_LEXEME, _C_REFERENCE),
    ],
    ids=["python", "c-family"],
)
def test_lexeme_matches_equal_the_reference_regex(new, reference) -> None:
    texts = _TRICKY + _random_texts(1691, 4000)
    differing = [
        text
        for text in texts
        if _spans(new, text, False) != _spans(reference, text, True)
    ]
    assert differing == []


def test_lexeme_regexes_start_every_branch_with_a_literal() -> None:
    # 首字符集优化的前提：不把分支包进分组（否则 re 逐位置尝试整个交替）。
    for pattern in (callers_absence._PY_LEXEME, callers_absence._C_LEXEME):
        assert pattern.groups == 0


def _reference_strip(text: str, language: str, bare: str | None) -> str:
    """#1691 之前的剥离（参照正则 + 组 2 判定字符串），其余逻辑相同。"""
    from tree_sitter_analyzer.mcp.tools.absence_text_refs import string_code

    lexeme = _PY_REFERENCE if language == "python" else _C_REFERENCE

    def _replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if match.group(2) is not None:
            quote = 3 if token[:3] in ('"""', "'''") else 1
            body = token[quote:-quote]
            if re.fullmatch(r"[A-Za-z_$][\w$]*", body):
                return f" {body} "
            prefix = text[max(0, match.start() - 2) : match.start()]
            if "f" in prefix.lower():
                return token
            docstring = quote == 3 and language == "python"
            kept = string_code(text, match.span(), body, docstring, bare)
            if kept is not None:
                return kept
        return "\n" * token.count("\n")

    return lexeme.sub(_replace, text)


_SOURCE = (
    'def f():\n    """Run g.\n\n    >>> g()\n    """\n'
    "    h = 'g'  # g\n    exec(\"g()\")\n    s = \"call o.g() now\"\n"
    "    t = 'the g word'\n    return \"pkg.mod:g\"\n"
)


@pytest.mark.parametrize("language", ["python", "java"])
@pytest.mark.parametrize("bare", [None, "g", "o", "word", "absent"])
def test_strip_output_equals_the_reference(language: str, bare: str | None) -> None:
    for text in [_SOURCE, *_TRICKY, *_random_texts(16910, 300)]:
        assert callers_absence._strip_comments_and_prose(
            text, language, bare
        ) == _reference_strip(text, language, bare)
