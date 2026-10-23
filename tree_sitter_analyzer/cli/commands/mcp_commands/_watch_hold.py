"""#1685：CLI 的 ``watch_start`` 驻留到 Ctrl-C，退出前按身份停止 watcher。

``--watch`` / ``--ast-cache --ast-cache-mode watch_start`` 原先在一次性 CLI 进程里
启动 watcher 后立即返回：进程随即退出，守护线程在任意位置被杀死（可能正在
同步写入），答复中的 ``status: started`` 并不成立。在同一进程内调用 ``main()``
（测试、嵌入）时，watcher 则被遗留下来，继续对项目根做启动对齐同步：CI 上
它在 pytest worker 中索引整个仓库，其写入被之后打桩
``_reset_incoming_edge_resolutions`` 的测试计入（#1685 的 12-16 次调用，路径全是
仓库自身的 ``tests/unit/no1_010b/*``）。

现在与 ``--knowledge-graph-watch`` 一致：答复照常输出后驻留，Ctrl-C 时停止
watcher 并等待后台工作结束；停止超时如实返回非零。
"""

from __future__ import annotations

import sys
import time
from typing import Any

#: 驻留循环的唤醒间隔（只影响 Ctrl-C 的响应延迟）。
_HOLD_TICK_SECONDS = 1.0


def wait_until_interrupted() -> None:
    """阻塞到 Ctrl-C（``KeyboardInterrupt``）；测试以注入替换此函数。"""
    while True:
        time.sleep(_HOLD_TICK_SECONDS)


def hold_cli_watcher(tool: Any, result: dict[str, Any], *, hold: bool = True) -> int:
    """驻留已启动的 watcher；返回退出码（停止未完成为 1）。

    ``hold=False`` 只停止不驻留（输出答复失败时由调用方使用）。
    """
    if result.get("status") != "started":
        return 0
    if hold:
        print("Watcher running; press Ctrl-C to stop.", file=sys.stderr, flush=True)
        try:
            wait_until_interrupted()
        except KeyboardInterrupt:
            pass
    try:
        tool.shutdown_application_watcher()
    except TimeoutError as exc:
        print(f"watch_stop: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0
