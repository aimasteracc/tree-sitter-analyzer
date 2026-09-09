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


def test_exclude_globs_apply_to_root_files(tmp_path):
    (tmp_path / "skip.py").write_text("target()", encoding="utf-8")
    assert scan(tmp_path, exclude_globs=["**/skip.py"]) == []


def test_already_negated_exclude_globs_are_preserved(tmp_path):
    # 2026-09-09：旧调用方会传入已经带有 ! 的排除模式。
    (tmp_path / "skip.py").write_text("target()", encoding="utf-8")
    assert scan(tmp_path, exclude_globs=["!**/skip.py"]) == []


def test_nonmatching_extensions_are_excluded(tmp_path):
    (tmp_path / "notes.txt").write_text("target()", encoding="utf-8")
    assert scan(tmp_path) == []


def test_binary_files_are_excluded(tmp_path):
    (tmp_path / "binary.py").write_bytes(b"target()\x00")
    assert scan(tmp_path) == []


def test_source_positions_preserve_line_number_and_indent(tmp_path):
    (tmp_path / "a.py").write_text("nothing\n  target()\n", encoding="utf-8")
    assert scan(tmp_path) == [
        {"file": str(tmp_path / "a.py"), "line": 2, "text": "  target()"}
    ]


def test_timeout_does_not_return_partial_matches(tmp_path):
    (tmp_path / "a.py").write_text("target()", encoding="utf-8")
    with pytest.raises(TimeoutError, match="SOURCE_DISCOVERY_BUDGET_EXCEEDED"):
        scan(tmp_path, timeout=0)


def test_full_count_is_independent_of_display_limit(tmp_path, monkeypatch):
    import asyncio
    import subprocess
    import sys

    from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool

    original = subprocess.Popen

    def own_worker_only(argv, *args, **kwargs):
        assert argv == [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            "-m",
            "tree_sitter_analyzer.source_lines",
        ]
        return original(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", own_worker_only)
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


@pytest.mark.parametrize("root", ["", " "])
def test_empty_roots_do_not_expand_to_working_directory(root):
    # 2026-09-09：逗号分隔根列表的空分量不能偷偷引入工作目录。
    with pytest.raises(OSError, match="SOURCE_ROOT_EMPTY"):
        list(workspace_files([root]))


def test_symlinked_ancestor_returns_canonical_paths(tmp_path):
    # 2026-09-09：macOS 的 /var 与 /private/var 必须使用同一套路径表示。
    real = tmp_path / "real"
    project = real / "project"
    project.mkdir(parents=True)
    file = project / "a.py"
    file.write_text("target()", encoding="utf-8")
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    assert list(workspace_files([str(alias / "project")])) == [file.resolve()]


def test_blocking_worker_is_killed_at_deadline(tmp_path, monkeypatch):
    # 2026-09-09：模拟文件系统读取一直不返回，父进程仍必须结束请求并回收工作进程。
    import subprocess
    import sys
    import time

    import tree_sitter_analyzer.source_lines as native

    original = subprocess.Popen
    processes = []

    def blocked_worker(argv, **kwargs):
        process = original(
            [sys.executable, "-I", "-c", "import time; time.sleep(60)"], **kwargs
        )
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", blocked_worker)
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="SOURCE_SCAN_BUDGET_EXCEEDED"):
        native.scan_symbol_lines_bounded("target", [str(tmp_path)], timeout=0.1)
    # 时间不可精确固定；上限包含 0.1 秒请求预算、一秒回收预算与调度余量。
    assert time.monotonic() - started < 3
    assert processes[0].poll() is not None


def test_worker_module_json_protocol(tmp_path, monkeypatch, capsys):
    import io
    import json
    import runpy
    import sys

    (tmp_path / "a.py").write_text("target()", encoding="utf-8")
    request = {
        "symbol": "target",
        "roots": [str(tmp_path)],
        "case_sensitive": True,
        "word_match": True,
        "include_globs": ["**/*.py"],
        "exclude_globs": [],
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request)))
    # 模块入口与隔离 Python 进程使用同一协议；临时移除缓存避免 runpy 的重复导入警告。
    monkeypatch.delitem(sys.modules, "tree_sitter_analyzer.source_lines")
    runpy.run_module("tree_sitter_analyzer.source_lines", run_name="__main__")
    assert json.loads(capsys.readouterr().out) == {
        "matches": [{"file": str(tmp_path / "a.py"), "line": 1, "text": "target()"}]
    }


@pytest.mark.parametrize(
    "response,exit_code,error_type,error",
    [
        ('{"matches": []}', 3, OSError, "SOURCE_WORKER_FAILED"),
        (
            '{"error": "SOURCE_ROOT_UNAVAILABLE", "timeout": false}',
            0,
            OSError,
            "SOURCE_ROOT_UNAVAILABLE",
        ),
        (
            '{"error": "SOURCE_SCAN_BUDGET_EXCEEDED", "timeout": true}',
            0,
            TimeoutError,
            "SOURCE_SCAN_BUDGET_EXCEEDED",
        ),
        ('{"matches": null}', 0, OSError, "SOURCE_WORKER_INVALID_RESPONSE"),
    ],
)
def test_worker_failure_is_never_reported_as_empty_success(
    tmp_path, monkeypatch, response, exit_code, error_type, error
):
    from unittest.mock import Mock

    import tree_sitter_analyzer.source_lines as native

    process = Mock(returncode=exit_code)
    process.communicate.return_value = (response, "")
    monkeypatch.setattr(native.subprocess, "Popen", Mock(return_value=process))
    with pytest.raises(error_type, match=error):
        native.scan_symbol_lines_bounded("target", [str(tmp_path)])


def test_unfinished_worker_cleanup_is_reported(tmp_path, monkeypatch):
    import subprocess
    from unittest.mock import Mock

    import tree_sitter_analyzer.source_lines as native

    process = Mock()
    process.communicate.side_effect = subprocess.TimeoutExpired("worker", 1)
    monkeypatch.setattr(native.subprocess, "Popen", Mock(return_value=process))
    with pytest.raises(OSError, match="SOURCE_WORKER_CLEANUP_FAILED"):
        native.scan_symbol_lines_bounded("target", [str(tmp_path)])
    process.kill.assert_called_once_with()
    assert process.communicate.call_args.kwargs == {"timeout": 1}


@pytest.mark.parametrize(
    "timeout,root_suffix,expected",
    [
        (5, "missing", {"error": "SOURCE_ROOT_UNAVAILABLE", "timeout": False}),
        (0, "", {"error": "SOURCE_DISCOVERY_BUDGET_EXCEEDED", "timeout": True}),
    ],
)
def test_worker_protocol_preserves_scan_errors(
    tmp_path, monkeypatch, capsys, timeout, root_suffix, expected
):
    import io
    import json

    import tree_sitter_analyzer.source_lines as native

    request = {
        "symbol": "target",
        "roots": [str(tmp_path / root_suffix)],
        "case_sensitive": True,
        "word_match": True,
        "include_globs": [],
        "exclude_globs": [],
        "timeout": timeout,
    }
    monkeypatch.setattr(native.sys, "stdin", io.StringIO(json.dumps(request)))
    native._main()
    assert json.loads(capsys.readouterr().out) == expected


def test_worker_protocol_rejects_oversized_payload(tmp_path, monkeypatch, capsys):
    import io
    import json

    import tree_sitter_analyzer.source_lines as native

    (tmp_path / "a.py").write_text("target()\n" * 100, encoding="utf-8")
    request = {
        "symbol": "target",
        "roots": [str(tmp_path)],
        "case_sensitive": True,
        "word_match": True,
        "include_globs": [],
        "exclude_globs": [],
    }
    monkeypatch.setattr(native, "_MAX_RESPONSE_BYTES", 128)
    monkeypatch.setattr(native.sys, "stdin", io.StringIO(json.dumps(request)))
    native._main()
    assert json.loads(capsys.readouterr().out) == {
        "error": "SOURCE_RESPONSE_BUDGET_EXCEEDED",
        "timeout": True,
    }


def test_isolated_worker_preserves_unicode_paths_and_symbols(tmp_path):
    from tree_sitter_analyzer.source_lines import scan_symbol_lines_bounded

    path = tmp_path / "名字.py"
    path.write_text("变量()\n", encoding="utf-8")
    assert scan_symbol_lines_bounded(
        "变量",
        [str(tmp_path)],
        case_sensitive=True,
        word_match=True,
        include_globs=[],
        exclude_globs=[],
    ) == [{"file": str(path), "line": 1, "text": "变量()"}]


@pytest.mark.asyncio
async def test_trace_never_rereads_hits_in_parent_process(tmp_path, monkeypatch):
    # 2026-09-09：注释过滤不能在有界扫描之后重新阻塞 MCP 主进程。
    import tree_sitter_analyzer.mcp.tools.trace_impact_tool as trace

    (tmp_path / "a.py").write_text("# target()\ntarget()\n", encoding="utf-8")
    monkeypatch.setattr(
        trace,
        "_file_non_code_lines",
        lambda path: pytest.fail("主进程不得重读命中文件"),
    )
    result = await trace.TraceImpactTool(str(tmp_path)).execute({"symbol": "target"})
    assert result["success"] is True
    assert result["call_count"] == 1
    assert result["usages"][0]["line"] == 2


def test_worker_protocol_classifies_code_and_comments(tmp_path, monkeypatch, capsys):
    import io
    import json

    import tree_sitter_analyzer.source_lines as native

    path = tmp_path / "a.py"
    path.write_text("# target()\ntarget()\n", encoding="utf-8")
    request = {
        "symbol": "target",
        "roots": [str(tmp_path)],
        "case_sensitive": True,
        "word_match": True,
        "include_globs": [],
        "exclude_globs": [],
        "classify_source": True,
    }
    monkeypatch.setattr(native.sys, "stdin", io.StringIO(json.dumps(request)))
    native._main()
    matches = json.loads(capsys.readouterr().out)["matches"]
    assert [(m["line"], m["_source_match"]) for m in matches] == [(1, False), (2, True)]


def test_classified_worker_response_requires_boolean_classification(
    tmp_path, monkeypatch
):
    from unittest.mock import Mock

    import tree_sitter_analyzer.source_lines as native

    process = Mock(returncode=0)
    process.communicate.return_value = ('{"matches": [{"file": "a.py"}]}', "")
    monkeypatch.setattr(native.subprocess, "Popen", Mock(return_value=process))
    with pytest.raises(OSError, match="SOURCE_WORKER_INVALID_RESPONSE"):
        native.scan_symbol_lines_bounded(
            "target", [str(tmp_path)], classify_source=True
        )
