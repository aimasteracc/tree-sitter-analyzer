"""RFC-0026 §3 C19：oracle wrapper 的控制记录与合流捕获（进程内直接调用）。

生产中 wrapper 以 ``python -I`` 子进程运行，覆盖率无法追踪；这里在测试进程内
直接调用 ``main``。wrapper 会 ``dup2`` 进程的 fd 1/2，因此夹具先保存原 fd、把
``sys.stdout``/``sys.stderr`` 指向真实 fd（与生产相同，绕开 pytest 的捕获对象），
结束后无条件还原。每个测试只断言一个精确的控制记录或捕获内容。
"""

from __future__ import annotations

import io
import json
import os
import runpy
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from tree_sitter_analyzer.no1_010b import oracle_wrapper

DETAIL_MAX_CHARS = 2000


def _unbuffered(fd: int) -> io.TextIOWrapper:
    """仿照生产的 ``python -u``：直通真实 fd、无缓冲，写入顺序即落盘顺序。"""
    raw = open(fd, "wb", buffering=0, closefd=False)  # noqa: SIM115
    return io.TextIOWrapper(raw, encoding="utf-8", write_through=True)


@contextmanager
def _real_fds() -> Iterator[None]:
    """让 wrapper 的 fd 重定向可逆：保存 fd 1/2 与 sys 流，结束后无条件还原。

    必须在测试调用阶段内使用（不能做成夹具）：pytest 在每个阶段开始时都会把
    ``sys.stdout`` 重新换成自己的捕获对象，夹具里的替换到调用阶段已失效。
    """
    saved_fds = (os.dup(1), os.dup(2))
    saved_streams = (sys.stdout, sys.stderr)
    out, err = _unbuffered(1), _unbuffered(2)
    sys.stdout, sys.stderr = out, err
    try:
        yield
    finally:
        for stream in (out, err):
            try:
                stream.close()  # closefd=False：只关闭包装对象，fd 本身保留
            except (OSError, ValueError):
                pass
        sys.stdout, sys.stderr = saved_streams
        for target, original in zip((1, 2), saved_fds, strict=True):
            os.dup2(original, target)
            os.close(original)


def _wrap(argv: list[str]) -> int:
    with _real_fds():
        return oracle_wrapper.main(argv)


def _run(tmp_path: Path, source: str, name: str = "oracle.py") -> dict[str, str]:
    oracle = tmp_path / name
    oracle.write_bytes(source.encode("utf-8"))
    control = tmp_path / "control.json"
    argv = ["oracle_wrapper.py", str(oracle), str(control), str(tmp_path / "cap.log")]
    assert _wrap(argv) == 0
    return json.loads(control.read_text(encoding="utf-8"))


def _capture(tmp_path: Path) -> bytes:
    return (tmp_path / "cap.log").read_bytes()


def test_main_returning_zero_is_completed(tmp_path: Path) -> None:
    record = _run(tmp_path, "def main():\n    return 0\n")
    assert record == {"phase": "completed", "detail": ""}


def test_print_stderr_and_fd_writes_merge_in_order(tmp_path: Path) -> None:
    source = (
        "import os, sys\n\n\n"
        "def main():\n"
        "    print('one')\n"
        "    print('two', file=sys.stderr)\n"
        "    os.write(1, b'three\\n')\n"
        "    return 0\n"
    )
    _run(tmp_path, source)
    # 按空白切分：只断言合流顺序，不依赖 Windows 文本流的换行翻译。
    assert _capture(tmp_path).split() == [b"one", b"two", b"three"]


def test_syntax_error_is_load_error(tmp_path: Path) -> None:
    source = "def main(:\n    return 0\n"
    record = _run(tmp_path, source)
    # 以相同文件名编译同一源码，得到与 importlib 加载时完全相同的 SyntaxError。
    with pytest.raises(SyntaxError) as raised:
        compile(source.encode("utf-8"), str(tmp_path / "oracle.py"), "exec")
    assert record == {"phase": "load_error", "detail": repr(raised.value)}


def test_missing_main_is_load_error(tmp_path: Path) -> None:
    record = _run(tmp_path, "VALUE = 1\n")
    assert record == {
        "phase": "load_error",
        "detail": "TypeError('oracle defines no callable main()')",
    }


def test_non_python_oracle_path_is_load_error(tmp_path: Path) -> None:
    # 无 .py 后缀时 importlib 找不到 loader：spec 为 None 也是加载错误。
    record = _run(tmp_path, "def main():\n    return 0\n", name="oracle.txt")
    oracle = tmp_path / "oracle.txt"
    assert record == {
        "phase": "load_error",
        "detail": repr(ImportError(f"cannot load oracle {oracle}")),
    }


def test_module_scope_exception_is_load_error(tmp_path: Path) -> None:
    record = _run(tmp_path, "raise RuntimeError('import boom')\n")
    assert record == {
        "phase": "load_error",
        "detail": "RuntimeError('import boom')",
    }


def test_main_raising_is_execution_error(tmp_path: Path) -> None:
    record = _run(tmp_path, "def main():\n    raise ValueError('bad')\n")
    assert record == {"phase": "execution_error", "detail": "ValueError('bad')"}


def test_main_calling_sys_exit_is_execution_error(tmp_path: Path) -> None:
    # SystemExit 也是 BaseException：sys.exit(0) 不能冒充正常完成。
    record = _run(tmp_path, "import sys\n\n\ndef main():\n    sys.exit(0)\n")
    assert record == {"phase": "execution_error", "detail": "SystemExit(0)"}


def test_main_returning_nonzero_is_execution_error(tmp_path: Path) -> None:
    record = _run(tmp_path, "def main():\n    return 3\n")
    assert record == {"phase": "execution_error", "detail": "main() returned 3"}


def test_main_returning_none_is_execution_error(tmp_path: Path) -> None:
    record = _run(tmp_path, "def main():\n    pass\n")
    assert record == {"phase": "execution_error", "detail": "main() returned None"}


def test_detail_is_truncated_to_the_limit(tmp_path: Path) -> None:
    record = _run(tmp_path, "def main():\n    raise ValueError('x' * 5000)\n")
    expected = repr(ValueError("x" * 5000))[:DETAIL_MAX_CHARS]
    assert record == {"phase": "execution_error", "detail": expected}


def test_closed_stdout_does_not_break_completion(tmp_path: Path) -> None:
    # 候选可能关闭 sys.stdout；收尾 flush 的异常被吞掉，控制记录照常写出。
    source = "import sys\n\n\ndef main():\n    sys.stdout.close()\n    return 0\n"
    assert _run(tmp_path, source) == {"phase": "completed", "detail": ""}


def test_script_entry_point_exits_with_main_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    oracle = tmp_path / "oracle.py"
    oracle.write_bytes(b"def main():\n    return 0\n")
    control = tmp_path / "control.json"
    argv = ["oracle_wrapper.py", str(oracle), str(control), str(tmp_path / "c.log")]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exited, _real_fds():
        runpy.run_path(oracle_wrapper.__file__, run_name="__main__")
    assert (exited.value.code, json.loads(control.read_text())["phase"]) == (
        0,
        "completed",
    )
