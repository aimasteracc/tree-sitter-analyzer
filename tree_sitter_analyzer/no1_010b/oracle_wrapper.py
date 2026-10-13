"""NO1-010B 受信 oracle wrapper（RFC-0026 §3, C19）；以文件路径独立运行。

用法：``python -I -u oracle_wrapper.py <oracle.py> <control.json>``。

wrapper 把 *加载* 与 *执行* 分开，并把结局写入 runner 指定的控制文件，而不是让
runner 解析原始退出码：

- ``load_error``：oracle 模块导入/语法/类型错误，或缺少可调用的 ``main``；
- ``execution_error``：``main()`` 抛出任何异常或返回非 0；
- ``completed``：``main()`` 返回 0，附带其捕获的 stdout，由 runner 解析声明行。

进程被硬退出（如 ``os._exit``）时不会写出控制记录，runner 将其记为执行错误。
本文件刻意不导入 ``tree_sitter_analyzer``：它只依赖标准库，运行于 ``-I`` 隔离模式。
没有内核沙箱时，同进程内的候选代码仍可伪造控制文件——因此 verifier 在沙箱实现前
从不把 PASS 作为终态。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys


def _emit(control_path: str, phase: str, stdout: str = "", detail: str = "") -> None:
    payload = {"phase": phase, "stdout": stdout, "detail": detail}
    with open(control_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


def main(argv: list[str]) -> int:
    oracle_path, control_path = argv[1], argv[2]
    captured = io.StringIO()
    try:
        spec = importlib.util.spec_from_file_location("no1_010b_oracle", oracle_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load oracle {oracle_path}")
        module = importlib.util.module_from_spec(spec)
        with contextlib.redirect_stdout(captured):
            spec.loader.exec_module(module)
        entry = getattr(module, "main", None)
        if not callable(entry):
            raise TypeError("oracle defines no callable main()")
    except BaseException as exc:  # noqa: BLE001 - 任何加载失败都是 ORACLE_LOAD_ERROR
        _emit(control_path, "load_error", detail=repr(exc))
        return 0
    try:
        with contextlib.redirect_stdout(captured):
            code = entry()
    except BaseException as exc:  # noqa: BLE001 - 加载后的任何异常都是执行错误
        _emit(control_path, "execution_error", detail=repr(exc))
        return 0
    if code != 0:
        _emit(control_path, "execution_error", detail=f"main() returned {code!r}")
        return 0
    _emit(control_path, "completed", stdout=captured.getvalue())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
