"""原生文件发现与符号核验的完整性和边界。"""

import pytest

from tree_sitter_analyzer.source_lines import scan_symbol_lines, workspace_files


def scan(root, symbol="target", **kwargs):
    return scan_symbol_lines(
        symbol,
        [str(root)],
        case_sensitive=kwargs.get("case_sensitive", False),
        word_match=kwargs.get("word_match", True),
        include_globs=kwargs.get("include_globs", ["**/*.py"]),
        exclude_globs=kwargs.get("exclude_globs", []),
        timeout=kwargs.get("timeout", 5),
    )


def test_nested_ignore_negation_and_hidden_files(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / ".gitignore").write_text("*.log\nskip/\n", encoding="utf-8")
    (tmp_path / "sub/.gitignore").write_text("!keep.log\n", encoding="utf-8")
    (tmp_path / "skip").mkdir()
    for name in [
        "a.py",
        "a.log",
        ".secret.py",
        "sub/keep.log",
        "sub/hide.log",
        "skip/b.py",
    ]:
        (tmp_path / name).write_text("target()\n", encoding="utf-8")
    assert [
        p.relative_to(tmp_path).as_posix() for p in workspace_files([str(tmp_path)])
    ] == ["a.py", "sub/keep.log"]


def test_overlapping_roots_never_duplicate_files(tmp_path):
    (tmp_path / "sub").mkdir()
    path = tmp_path / "sub/a.py"
    path.write_text("target()\n", encoding="utf-8")
    assert list(workspace_files([str(tmp_path), str(tmp_path / "sub")])) == [path]


def test_missing_root_is_an_error(tmp_path):
    with pytest.raises(OSError, match="SOURCE_ROOT_UNAVAILABLE"):
        list(workspace_files([str(tmp_path / "missing")]))


def test_symlink_files_and_directories_are_not_followed(tmp_path):
    inside = tmp_path / "inside"
    inside.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("target()", encoding="utf-8")
    (inside / "linked").symlink_to(outside, target_is_directory=True)
    (inside / "file.py").symlink_to(outside / "secret.py")
    assert list(workspace_files([str(inside)])) == []
    with pytest.raises(OSError, match="SOURCE_ROOT_SYMLINK"):
        list(workspace_files([str(inside / "linked")]))


@pytest.mark.parametrize(
    "symbol,case,word,expected",
    [
        ("target", False, True, [1, 2]),
        ("Target", False, True, [2]),
        ("target", True, True, [1]),
        ("target", False, False, [1, 2, 3]),
        ("变量", False, True, [4]),
    ],
)
def test_smart_case_word_boundaries_and_unicode(tmp_path, symbol, case, word, expected):
    (tmp_path / "a.py").write_text(
        "target()\nTarget()\nmytarget()\n变量()\n", encoding="utf-8"
    )
    assert [
        hit["line"]
        for hit in scan(tmp_path, symbol, case_sensitive=case, word_match=word)
    ] == expected


def test_globs_binary_files_and_original_line_numbers(tmp_path):
    (tmp_path / "a.py").write_text("nothing\n  target()\n", encoding="utf-8")
    (tmp_path / "skip.py").write_text("target()", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("target()", encoding="utf-8")
    (tmp_path / "binary.py").write_bytes(b"target()\x00")
    assert scan(tmp_path, exclude_globs=["**/skip.py"]) == [
        {"file": str(tmp_path / "a.py"), "line": 2, "text": "  target()"}
    ]


def test_timeout_does_not_return_partial_matches(tmp_path):
    (tmp_path / "a.py").write_text("target()", encoding="utf-8")
    with pytest.raises(TimeoutError, match="SOURCE_DISCOVERY_BUDGET_EXCEEDED"):
        scan(tmp_path, timeout=0)


def test_full_count_is_independent_of_display_limit(tmp_path, monkeypatch):
    import asyncio
    import subprocess

    from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool

    monkeypatch.setattr(
        subprocess, "Popen", lambda *args, **kwargs: pytest.fail("核验不得启动外部进程")
    )
    (tmp_path / "a.py").write_text("target()\n" * 150, encoding="utf-8")
    result = asyncio.run(
        TraceImpactTool(str(tmp_path)).execute({"symbol": "target", "max_results": 3})
    )
    assert result["call_count"] == 150
    assert len(result["usages"]) == 3
    assert result["truncated"] is True


def test_oversized_source_refuses_incomplete_success(tmp_path, monkeypatch):
    import tree_sitter_analyzer.source_lines as native

    monkeypatch.setattr(native, "_MAX_FILE_BYTES", 8)
    (tmp_path / "a.py").write_text("target()\n", encoding="utf-8")
    with pytest.raises(TimeoutError, match="SOURCE_FILE_BUDGET_EXCEEDED"):
        scan(tmp_path)


@pytest.mark.parametrize(
    "budget,limit,error",
    [
        ("_MAX_ENTRIES", 1, "SOURCE_DISCOVERY_BUDGET_EXCEEDED"),
        ("_MAX_TOTAL_BYTES", 8, "SOURCE_SCAN_BUDGET_EXCEEDED"),
        ("_MAX_MATCHES", 1, "SOURCE_MATCH_BUDGET_EXCEEDED"),
    ],
)
def test_exhausted_budget_never_returns_partial_results(
    tmp_path, monkeypatch, budget, limit, error
):
    import tree_sitter_analyzer.source_lines as native

    monkeypatch.setattr(native, budget, limit)
    for name in ["a.py", "b.py"]:
        (tmp_path / name).write_text("target()", encoding="utf-8")
    with pytest.raises(TimeoutError, match=error):
        scan(tmp_path)


def test_directory_read_error_is_reported(tmp_path, monkeypatch):
    import tree_sitter_analyzer.source_lines as native

    def failed_walk(*args, onerror, **kwargs):
        onerror(PermissionError("unreadable directory"))

    monkeypatch.setattr(native.os, "walk", failed_walk)
    with pytest.raises(PermissionError, match="unreadable directory"):
        list(workspace_files([str(tmp_path)]))


def test_file_replaced_with_nonregular_entry_is_rejected(tmp_path, monkeypatch):
    import stat
    from types import SimpleNamespace

    import tree_sitter_analyzer.source_lines as native

    (tmp_path / "a.py").write_text("target()", encoding="utf-8")
    with monkeypatch.context() as patcher:
        patcher.setattr(
            native.os, "fstat", lambda _: SimpleNamespace(st_mode=stat.S_IFIFO)
        )
        with pytest.raises(OSError, match="SOURCE_FILE_CHANGED"):
            scan(tmp_path)


def test_discovery_excludes_nonregular_entries(tmp_path, monkeypatch):
    import stat
    from pathlib import Path
    from types import SimpleNamespace

    special = tmp_path / "pipe.py"
    special.write_text("", encoding="utf-8")
    original_stat = Path.stat

    def entry_stat(path, *args, **kwargs):
        if path == special:
            return SimpleNamespace(st_mode=stat.S_IFIFO)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", entry_stat)
    assert list(workspace_files([str(tmp_path)])) == []
