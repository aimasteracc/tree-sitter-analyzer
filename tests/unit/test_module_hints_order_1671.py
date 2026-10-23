"""#1671 等价门：模块级接收者提示的顺序必须与进程哈希种子无关。

``module_types`` 写入 ``symbols_json``；按集合顺序输出时，同一份源码在两个
进程中提取得到不同的索引行，增量刷新的结果因而不等于全新重建（本仓库实测
226 个文件不同）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

_SOURCE = "\n".join(
    f"NAME_{index:02d} = frozenset({{'{index}'}})" for index in range(40)
)

_PROGRAM = """
import json, sys
from tree_sitter_analyzer.core.parser import Parser
from tree_sitter_analyzer.receiver_module_hints import module_hints
tree = Parser().parse_code(sys.stdin.read(), "python", filename="m.py").tree
print(json.dumps(list(module_hints(tree.root_node).variables)))
"""


def _order(seed: str) -> list[str]:
    completed = subprocess.run(
        [sys.executable, "-c", _PROGRAM],
        input=_SOURCE,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONHASHSEED": seed},
        check=True,
        timeout=120,
    )
    return list(json.loads(completed.stdout))


# slow_ok：两次子进程（不同 PYTHONHASHSEED）才能复现进程间的集合顺序差异。
@pytest.mark.slow_ok
def test_module_hint_order_is_sorted_under_any_hash_seed() -> None:
    expected = [f"NAME_{index:02d}" for index in range(40)]

    assert (_order("1"), _order("2")) == (expected, expected)
