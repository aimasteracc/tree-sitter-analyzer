"""#1737 等价门：发布路径改用捕获时的候选行打戳、免路径解析校验、gitignore 快速
路径与惰性语言上下文之后，八类编辑后的刷新结果仍须等于同一源码的全新重建。

两条刷新路线（``index_project`` / ``sync``）各跑一遍；测试进程默认开启完整认证
校验（``TSA_CERTIFICATION_VERIFY=full``，见 ``tests/conftest.py``），发布失败会
直接抛出。比较使用 ``_index_canonical_dump`` 的规范化转储。
"""

from __future__ import annotations

import os
import time

import pytest

from tests.unit._index_canonical_dump import dump_differences
from tests.unit.test_refresh_equivalence_1671 import (
    _FILES,
    _index_project,
    _published_dump,
    _sync,
    _wipe_index,
    _write,
    root,  # noqa: F401 - 复用同一夹具（含稳定失败文件）
)


def _rewrite_same_bytes(project: str, name: str) -> None:
    path = os.path.join(project, name)
    with open(path, "rb") as stream:
        data = stream.read()
    with open(path, "wb") as stream:
        stream.write(data)
    # #1707：竞争窗口内的 mtime 不记入 stat 证据（安全方向，下次刷新重新哈希），
    # 与 #1671 夹具一致，把 mtime 移到窗口之外再比较。
    past = time.time_ns() - 3_600_000_000_000
    os.utime(path, ns=(past, past))


def _apply(project: str, kind: str) -> None:
    core = _FILES["pkg/core.py"]
    if kind == "body_edit":
        _write(project, "pkg/core.py", core.replace("return 1", "return 2"))
    elif kind == "add_function":
        _write(project, "pkg/core.py", core + "\n\ndef extra():\n    return helper()\n")
    elif kind == "remove_called_function":
        # api.py 仍调用 helper：其入边须与全新重建同样变为未解析。
        _write(project, "pkg/core.py", core.split("\n\n\ndef helper")[0] + "\n")
    elif kind == "add_file":
        _write(
            project,
            "pkg/extra.py",
            "from pkg.core import helper\n\n\ndef more():\n    return helper()\n",
        )
    elif kind == "delete_file":
        os.remove(os.path.join(project, "pkg/api.py"))
    elif kind == "rename_file":
        os.replace(
            os.path.join(project, "pkg/api.py"),
            os.path.join(project, "pkg/service.py"),
        )
        _write(project, "app.py", _FILES["app.py"].replace("pkg.api", "pkg.service"))
    elif kind == "same_bytes_rewrite":
        _rewrite_same_bytes(project, "pkg/core.py")
        _rewrite_same_bytes(project, "app.py")
    elif kind == "gitignore_excludes_file":
        _write(project, ".gitignore", "pkg/api.py\n")
    else:  # pragma: no cover - 参数表与分支一一对应
        raise AssertionError(kind)


_KINDS = [
    "body_edit",
    "add_function",
    "remove_called_function",
    "add_file",
    "delete_file",
    "rename_file",
    "same_bytes_rewrite",
    "gitignore_excludes_file",
]


# slow_ok：每个用例做三次真实刷新（含一次全新重建）并转储两份完整索引。
@pytest.mark.slow_ok
@pytest.mark.parametrize("route", ["index_project", "sync"])
@pytest.mark.parametrize("kind", _KINDS)
def test_refresh_after_each_edit_kind_equals_a_fresh_rebuild(
    root,  # noqa: F811
    route,
    kind,
) -> None:
    refresh = _index_project if route == "index_project" else _sync
    refresh(root)
    refresh(root)  # 父版本带稳定失败记录，零变化判定可用
    _apply(root, kind)
    refresh(root)
    refreshed = _published_dump(root)

    _wipe_index(root)
    refresh(root)
    rebuilt = _published_dump(root)

    assert dump_differences(refreshed, rebuilt) == {}
    assert refreshed["ast_index"]
