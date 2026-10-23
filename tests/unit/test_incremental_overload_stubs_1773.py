"""#1773：增量更新调用图同样由唯一的实现代表 ``@overload`` 存根（等于全新构图）。"""

from __future__ import annotations

import os

import pytest

from tests.unit.test_incremental_call_graph_1723 import (  # noqa: F401 — autouse fixture
    _established,
    _fresh_state,
    _normalised,
    _refresh_and_take_increment,
    _warm_enabled,
)
from tests.unit.test_scoped_backfill_1696 import _write_tree

_PLAIN = (
    "class Pipeline:\n"
    "    def constrain(self, c):\n"
    "        return self\n\n"
    "    def gt(self, v):\n"
    "        return self.constrain(v)\n"
)
_OVERLOADED = (
    "from typing import overload\n\n\n"
    "class Pipeline:\n"
    "    @overload\n"
    "    def constrain(self, c: int) -> 'Pipeline': ...\n"
    "    @overload\n"
    "    def constrain(self, c: str) -> 'Pipeline': ...\n"
    "    def constrain(self, c):\n"
    "        return self\n\n"
    "    def gt(self, v):\n"
    "        return self.constrain(v)\n"
)


@pytest.mark.slow_ok
def test_adding_overload_stubs_updates_the_graph_like_a_fresh_build(tmp_path) -> None:
    root = tmp_path / "project"
    _write_tree(root)
    path = root / "pkg" / "pipe.py"
    path.write_text(_PLAIN, encoding="utf-8")
    _established(root)
    path.write_text(_OVERLOADED, encoding="utf-8")
    info = os.stat(path)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 2**31))

    outcome, incremental = _refresh_and_take_increment(root)

    assert outcome.get("incremental", {}).get("applied") is True, outcome
    assert _normalised(incremental) == _normalised(_fresh_state(str(root)))
    lines = sorted(
        ref.start_line
        for ref in incremental["_func_by_file"]["pkg/pipe.py"]
        if ref.name == "constrain"
    )
    assert lines == [9]
    callers = {
        caller.name
        for target, refs in incremental["_callers"].items()
        if target.name == "constrain"
        for caller in refs
    }
    assert callers == {"gt"}
