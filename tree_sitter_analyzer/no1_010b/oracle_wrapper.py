"""NO1-010B oracle wrapper（RFC-0026 §3, C19）；以文件路径独立运行。

用法：``python -I -u oracle_wrapper.py <oracle.py> <control.json> <capture.log>``。

wrapper 把 *加载* 与 *执行* 分开，并把阶段写入 runner 指定的控制文件，而不是让
runner 解析原始退出码：

- ``load_error``：oracle 模块导入/语法/类型错误，或缺少可调用的 ``main``；
- ``execution_error``：``main()`` 抛出任何异常或返回非 0；
- ``completed``：``main()`` 返回 0；runner 再按 B0 规则解析捕获流中的声明行。

导入 oracle 之前，wrapper 用 ``os.dup2`` 把 OS 级 fd 1 与 fd 2 重定向到同一个捕获
文件，因此 ``print``、``os.write(1, ...)``、stderr 与子进程输出按写入顺序合流；
结果行之后的任何诊断都使声明非最终，按 B0 规则记为协议错误。

注意：corpus 中的 oracle 在 *模块作用域* 导入候选模块，所以候选代码的导入失败
表现为 ``load_error``；在 ``main()`` 内部才导入候选的 oracle 会把同一缺陷表现为
``execution_error``（REVIEW-10，暂不处理）。

进程被硬退出（如 ``os._exit``）时不会写出控制记录，runner 将其记为执行错误。
本文件刻意不导入 ``tree_sitter_analyzer``：它只依赖标准库，运行于 ``-I`` 隔离模式。

**这不是可信边界**：oracle 与候选代码在同一进程内运行，没有内核沙箱时候选代码
可以伪造捕获流（如替换 ``sys.stdout``）、改写控制文件或硬退出。因此 verifier
把本 wrapper 得出的一切判定都标为 provisional（``terminal`` 为 ``None``）。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

_DETAIL_MAX_CHARS = 2000


def _emit(control_path: str, phase: str, detail: str = "") -> None:
    payload = {"phase": phase, "detail": detail[:_DETAIL_MAX_CHARS]}
    with open(control_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


def _capture_fds(capture_path: str) -> None:
    """把 fd 1/2 合并重定向到捕获文件；之后的所有输出都进入同一条流。"""
    sys.stdout.flush()
    sys.stderr.flush()
    fd = os.open(capture_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.close(fd)


def _flush_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:  # noqa: BLE001 - 候选可能已替换或关闭流
            pass


def main(argv: list[str]) -> int:
    oracle_path, control_path, capture_path = argv[1], argv[2], argv[3]
    _capture_fds(capture_path)
    try:
        spec = importlib.util.spec_from_file_location("no1_010b_oracle", oracle_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load oracle {oracle_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        entry = getattr(module, "main", None)
        if not callable(entry):
            raise TypeError("oracle defines no callable main()")
    except BaseException as exc:  # noqa: BLE001 - 任何加载失败都是 ORACLE_LOAD_ERROR
        _emit(control_path, "load_error", detail=repr(exc))
        return 0
    try:
        code = entry()
    except BaseException as exc:  # noqa: BLE001 - 加载后的任何异常都是执行错误
        _emit(control_path, "execution_error", detail=repr(exc))
        return 0
    finally:
        _flush_streams()
    if code != 0:
        _emit(control_path, "execution_error", detail=f"main() returned {code!r}")
        return 0
    _emit(control_path, "completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
