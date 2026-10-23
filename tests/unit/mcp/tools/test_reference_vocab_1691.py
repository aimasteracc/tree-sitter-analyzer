"""#1691：非调用引用扫描的词表（``reference_vocab``）——只会读得更少，答案不变。

新进程只在 stat 证据重新复核一致时，凭词表跳过不含名字的文件；编辑、新增、删除
文件，竞争窗口内的读取，代码指纹变化与损坏的落盘文件都回到照常读取。每个键都做过
变异检验：强制“总是命中”会让这里至少一个测试变红。
"""

from __future__ import annotations

import os
import random
import re
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools import evidence_file_cache, walk_evidence_store

_AN_HOUR_NS = 3600 * 1_000_000_000


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


# --------------------------------------------------------------------------- #
# 非调用引用扫描的词表：不含名字的文件不再打开，答案不变
# --------------------------------------------------------------------------- #


def test_vocabulary_answers_exactly_the_byte_prefilter() -> None:
    from tree_sitter_analyzer.mcp.tools.reference_vocab import searchable, vocabulary

    rng = random.Random(1691)
    alphabet = [
        b"a",
        b"b",
        b"_",
        b"$",
        b"1",
        b" ",
        b".",
        b"\n",
        b"\xc3",
        b"\xa9",
        b"(",
        b"\0",
    ]
    word_bytes = [b"a", b"b", b"_", b"$", b"1", b"\xc3", b"\xa9"]
    for _ in range(3000):
        data = b"".join(rng.choices(alphabet, k=rng.randint(0, 40)))
        words = set(re.findall(rb"[A-Za-z0-9_$\x80-\xff]+", data))
        assert vocabulary(data) == b"\0".join(sorted(words))
        needle = b"".join(rng.choices(word_bytes, k=rng.randint(1, 4)))
        assert searchable(needle)
        assert (needle in data) == (needle in vocabulary(data)), (data, needle)
    assert not searchable(b"a.b") and not searchable(b"") and searchable(b"caf\xc3\xa9")


def _scan_files(root: Path, names: list[str], needle: bytes):
    from tree_sitter_analyzer.mcp.tools.callers_absence import _files_containing

    files = [(name, "python") for name in names]
    return _files_containing(str(root), files, needle, time.monotonic() + 30)


@pytest.fixture
def vocab_tree(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / ".ast-cache").mkdir(parents=True)
    (root / "a.py").write_text("def size():\n    return 1\n")
    (root / "b.py").write_text("x = other\n")
    (root / "c.py").write_text("y = w.size  # uses size\n")
    _backdate_tree(root)
    return root


@pytest.fixture
def opened(monkeypatch) -> list[str]:
    """记录经 ``FILE_CACHE`` 打开的文件。"""
    calls: list[str] = []
    original = evidence_file_cache.FILE_CACHE.read_stamped

    def spy(path: str):
        calls.append(os.path.basename(path))
        return original(path)

    monkeypatch.setattr(evidence_file_cache.FILE_CACHE, "read_stamped", spy)
    return calls


def _new_scan_process() -> None:
    from tree_sitter_analyzer.mcp.tools import reference_vocab

    evidence_file_cache.FILE_CACHE.clear()
    reference_vocab.clear()


def _hit_names(hits) -> list[str]:
    return sorted(rel for rel, _language, _data, _stamp in hits)


def test_a_new_process_skips_files_its_vocabulary_rules_out(
    vocab_tree: Path, opened: list[str]
) -> None:
    names = ["a.py", "b.py", "c.py"]
    first = _scan_files(vocab_tree, names, b"size")
    assert _hit_names(first) == ["a.py", "c.py"]
    assert sorted(opened) == names

    _new_scan_process()
    opened.clear()
    second = _scan_files(vocab_tree, names, b"size")

    assert second == first
    assert sorted(opened) == ["a.py", "c.py"]  # b.py 不含名字，不再打开


def test_an_edited_file_is_read_again(vocab_tree: Path, opened: list[str]) -> None:
    names = ["a.py", "b.py", "c.py"]
    _scan_files(vocab_tree, names, b"size")
    # 同样大小、新的 mtime：证据不同，必须照常读取并看到新加入的名字。
    (vocab_tree / "b.py").write_text("x = size\n")
    _backdate(vocab_tree / "b.py", 2 * _AN_HOUR_NS)

    _new_scan_process()
    opened.clear()
    hits = _scan_files(vocab_tree, names, b"size")

    assert _hit_names(hits) == ["a.py", "b.py", "c.py"]
    assert "b.py" in opened


def test_a_new_file_is_read(vocab_tree: Path) -> None:
    names = ["a.py", "b.py", "c.py"]
    _scan_files(vocab_tree, names, b"size")
    (vocab_tree / "d.py").write_text("z = size\n")
    _backdate(vocab_tree / "d.py")

    _new_scan_process()
    hits = _scan_files(vocab_tree, [*names, "d.py"], b"size")

    assert _hit_names(hits) == ["a.py", "c.py", "d.py"]


def test_a_deleted_file_still_makes_the_scan_unknown(vocab_tree: Path) -> None:
    names = ["a.py", "b.py", "c.py"]
    _scan_files(vocab_tree, names, b"size")
    (vocab_tree / "b.py").unlink()

    _new_scan_process()

    assert _scan_files(vocab_tree, names, b"size") is None


def test_a_racy_read_is_never_recorded(vocab_tree: Path, opened: list[str]) -> None:
    (vocab_tree / "b.py").write_text("x = other\n")  # mtime 落入竞争窗口
    names = ["a.py", "b.py", "c.py"]
    _scan_files(vocab_tree, names, b"size")

    _new_scan_process()
    opened.clear()
    _scan_files(vocab_tree, names, b"size")

    assert "b.py" in opened


def test_the_vocabulary_store_is_keyed_on_the_code_fingerprint(
    vocab_tree: Path, opened: list[str], monkeypatch
) -> None:
    import tree_sitter_analyzer.source_fingerprint as fingerprint

    names = ["a.py", "b.py", "c.py"]
    _scan_files(vocab_tree, names, b"size")
    monkeypatch.setattr(fingerprint, "source_fingerprint", lambda: "other-code")

    _new_scan_process()
    opened.clear()
    _scan_files(vocab_tree, names, b"size")

    assert sorted(opened) == names


def test_a_corrupt_vocabulary_store_is_empty(
    vocab_tree: Path, opened: list[str]
) -> None:
    names = ["a.py", "b.py", "c.py"]
    first = _scan_files(vocab_tree, names, b"size")
    store = vocab_tree / ".ast-cache" / walk_evidence_store.DIR_NAME
    (stored,) = sorted(store.glob("vocab-*.bin"))
    stored.write_bytes(b"\x00not marshal")

    _new_scan_process()
    opened.clear()
    second = _scan_files(vocab_tree, names, b"size")

    assert second == first
    assert sorted(opened) == names


def test_a_needle_with_non_word_bytes_reads_every_file(
    vocab_tree: Path, opened: list[str]
) -> None:
    names = ["a.py", "b.py", "c.py"]
    _scan_files(vocab_tree, names, b"size")

    _new_scan_process()
    opened.clear()
    hits = _scan_files(vocab_tree, names, b"w.size")

    assert _hit_names(hits) == ["c.py"]
    assert sorted(opened) == names


def test_the_vocabulary_store_can_be_turned_off(vocab_tree: Path, monkeypatch) -> None:
    monkeypatch.setenv(walk_evidence_store.ENV_VAR, "off")

    _scan_files(vocab_tree, ["a.py", "b.py"], b"size")

    store = vocab_tree / ".ast-cache" / walk_evidence_store.DIR_NAME
    assert not list(store.glob("vocab-*.bin"))


def test_an_edited_file_is_relearned(vocab_tree: Path, opened: list[str]) -> None:
    names = ["a.py", "b.py", "c.py"]
    _scan_files(vocab_tree, names, b"size")
    (vocab_tree / "b.py").write_text("x = changed\n")
    _backdate(vocab_tree / "b.py", 2 * _AN_HOUR_NS)
    _new_scan_process()
    _scan_files(vocab_tree, names, b"size")  # 证据不同：重读并记下新词表

    _new_scan_process()
    opened.clear()
    _scan_files(vocab_tree, names, b"size")

    assert sorted(opened) == ["a.py", "c.py"]


def test_vocabulary_store_rejects_malformed_payloads(vocab_tree: Path) -> None:
    import marshal

    from tree_sitter_analyzer.mcp.tools import reference_vocab

    _scan_files(vocab_tree, ["a.py"], b"size")
    store = vocab_tree / ".ast-cache" / walk_evidence_store.DIR_NAME
    (stored,) = sorted(store.glob("vocab-*.bin"))
    _format, text, entries = marshal.loads(stored.read_bytes())
    (path,) = entries
    good = entries[path]
    root = os.path.abspath(str(vocab_tree))
    malformed = [
        (_format, text, {path: (good[0][:4], good[1])}),
        (_format, text, {path: (good[0], "not bytes")}),
        (_format, text, {path: good[0]}),
        (_format, text, {1: good}),
        (_format, "other key", {path: good}),
        (_format, text, [path]),
        (_format + 1, text, {path: good}),
    ]
    for payload in malformed:
        stored.write_bytes(marshal.dumps(payload))
        assert reference_vocab._load(root) == {}, payload
    stored.write_bytes(marshal.dumps((_format, text, {path: good, 7: good})))
    assert reference_vocab._load(root) == {path: good}


def test_vocabulary_store_without_ast_cache_stays_in_process(tmp_path: Path) -> None:
    from tree_sitter_analyzer.mcp.tools import reference_vocab

    (tmp_path / "a.py").write_text("x = 1\n")
    _backdate(tmp_path / "a.py")

    assert _hit_names(_scan_files(tmp_path, ["a.py"], b"size")) == []
    assert len(reference_vocab.for_root(str(tmp_path))) == 1
    assert not (tmp_path / ".ast-cache").exists()


def test_vocabulary_store_write_failure_is_silent(
    vocab_tree: Path, monkeypatch
) -> None:
    from tree_sitter_analyzer.mcp.tools import reference_vocab

    def refuse(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(reference_vocab.os, "replace", refuse)

    assert _hit_names(_scan_files(vocab_tree, ["a.py", "b.py"], b"size")) == ["a.py"]
    store = vocab_tree / ".ast-cache" / walk_evidence_store.DIR_NAME
    assert sorted(path.name for path in store.iterdir()) == []


def test_vocabulary_store_trims_to_entries_used_by_this_process(
    vocab_tree: Path, monkeypatch
) -> None:
    import marshal

    from tree_sitter_analyzer.mcp.tools import reference_vocab

    _scan_files(vocab_tree, ["a.py", "b.py", "c.py"], b"size")
    _new_scan_process()
    monkeypatch.setattr(reference_vocab, "MAX_TOTAL_BYTES", 0)
    (vocab_tree / "a.py").write_text("def size():\n    return 2\n")
    _backdate(vocab_tree / "a.py", 2 * _AN_HOUR_NS)

    _scan_files(vocab_tree, ["a.py"], b"size")

    store = vocab_tree / ".ast-cache" / walk_evidence_store.DIR_NAME
    (stored,) = sorted(store.glob("vocab-*.bin"))
    entries = marshal.loads(stored.read_bytes())[2]
    assert sorted(os.path.basename(path) for path in entries) == ["a.py"]


def test_vocabulary_store_keeps_the_two_newest_files(vocab_tree: Path) -> None:
    from tree_sitter_analyzer.mcp.tools import reference_vocab

    store = vocab_tree / ".ast-cache" / walk_evidence_store.DIR_NAME
    store.mkdir()
    for index in range(4):
        old = store / f"vocab-old{index}.bin"
        old.write_bytes(b"x")
        _backdate(old, (index + 2) * _AN_HOUR_NS)

    _scan_files(vocab_tree, ["a.py"], b"size")

    assert len(list(store.glob("vocab-*.bin"))) == reference_vocab.KEEP
    assert (store / "vocab-old0.bin").exists()
