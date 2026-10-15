"""#1596：RFC-0028 §1.2 作用域守卫只计入“可能点名目标”的未解析调用点。

实测（dogfood 第 3/4 轮）：模块级函数 18/18、12/12 永远答 ``unknown``，即使
确实无人引用——声明文件里任意一个 ``"\\n".join`` / ``header.get`` 都被当作
可能指向它的调用。属性名与目标名不同的调用点不可能调用目标：经由别名、回调或
字典到达目标都需要一次按名引用，而 0 调用方时非调用引用门（#1593）会扫描它。
计算式分发（``getattr(x, name)``、``HANDLERS[name]``、``globals()[...]``）
不点名任何符号，仍然保留守卫。
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_dispatch import (
    DECORATED_REASON,
    NAMES_OTHER_REASON,
    could_name_target,
    partition_by_target,
)
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

#: 只有内建/局部变量属性调用的模块：没有任何东西能点名 ``lonely``。
_PLAIN = (
    "def lonely(items):\n"
    '    return "x".join(items)\n\n\n'
    "def reader(d, header):\n"
    '    value = d.get("k")\n'
    '    return header.get("h"), value\n'
)
#: 含反射分发的模块：``getattr(mod, name)()`` 可能就是 ``lonely`` 的调用方。
_DISPATCH = (
    "import sys\n\n\n"
    "def lonely(items):\n"
    '    return "x".join(items)\n\n\n'
    "def dispatch(name):\n"
    "    mod = sys.modules[__name__]\n"
    "    return getattr(mod, name)()\n"
)
#: 别名调用：``alias()`` 名字不同，但 ``alias = lonely`` 是一次按名引用。
_ALIAS = (
    "def lonely(items):\n"
    '    return "x".join(items)\n\n\n'
    "def run(items):\n"
    "    alias = lonely\n"
    "    return alias(items)\n"
)


#: 项目内两处同名 `get` / `join`：属性调用无法绑定，记为未解析（复现 dogfood 现象）。
_AMBIGUOUS = (
    "class Store:\n"
    "    def get(self, k):\n"
    "        return k\n\n"
    "    def join(self, xs):\n"
    "        return xs\n\n\n"
    "class Cache:\n"
    "    def get(self, k):\n"
    "        return k\n\n"
    "    def join(self, xs):\n"
    "        return xs\n"
)


async def _index(root, source: str) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (root / "mod.py").write_text(source, encoding="utf-8")
    (root / "store.py").write_text(_AMBIGUOUS, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True
    return str(root)


async def _callers(root: str, name: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "include_bodies": False}
    )


@pytest.mark.asyncio
async def test_unreferenced_module_function_answers_complete(tmp_path) -> None:
    # #1596：未解析调用只有 `"x".join` / `d.get` / `header.get`，均不可能点名 lonely。
    root = await _index(tmp_path, _PLAIN)

    result = await _callers(root, "lonely")

    assert (result["caller_count"], result["completeness"]) == (0, "complete")
    assert result["completeness_reason"] is None
    assert result["unresolved_in_declaring_files"] == 0
    assert result["unresolved_sites"] == []
    # 被排除的点仍可审计：§1.3 要求“不是普查”的反面也能复核。
    assert result["excluded_by_reason"] == {NAMES_OTHER_REASON: 3}
    assert [s["callee"] for s in result["excluded_sites"]] == [
        '"x".join',
        "d.get",
        "header.get",
    ]


@pytest.mark.asyncio
async def test_other_names_still_gate_when_callers_exist(tmp_path) -> None:
    # #1596：有调用方时非调用引用门不运行，因此不按名收窄，原守卫保持不变。
    root = await _index(tmp_path, _PLAIN + "\n\ndef user():\n    return lonely([])\n")

    result = await _callers(root, "lonely")

    assert (result["caller_count"], result["completeness"]) == (1, "incomplete")
    assert result["unresolved_in_declaring_files"] == 3
    assert result["excluded_by_reason"] == {}


@pytest.mark.asyncio
async def test_reflective_dispatch_in_declaring_file_keeps_the_guard(
    tmp_path,
) -> None:
    # #1596：`getattr(mod, name)()` 的名字是计算出来的，可能就是 lonely。
    root = await _index(tmp_path, _DISPATCH)

    result = await _callers(root, "lonely")

    assert result["completeness"] == "unknown"
    assert [s["mechanism"] for s in result["unresolved_sites"]] == ["reflection"]


@pytest.mark.asyncio
async def test_aliased_call_is_caught_by_the_reference_gate(tmp_path) -> None:
    # #1596：名字不同的 `alias()` 不再守卫文件，但 `alias = lonely` 是非调用引用。
    root = await _index(tmp_path, _ALIAS)

    result = await _callers(root, "lonely")

    assert result["completeness"] == "unknown"
    assert result["completeness_reason"] == "NON_CALL_REFERENCES"
    assert result["non_call_reference_sites"] == [{"file": "mod.py", "line": 6}]


#: 注册表分发：`@register` 登记后由名字不同的 `handler()` 调用。
_REGISTERED = (
    "HANDLERS = []\n\n\n"
    "def register(func):\n"
    "    HANDLERS.append(func)\n"
    "    return func\n\n\n"
    "@register\n"
    "def lonely(items):\n"
    '    return "x".join(items)\n\n\n'
    "@functools.lru_cache(maxsize=1)\n"
    "def cached(items):\n"
    "    return items\n\n\n"
    "def fire(items):\n"
    "    for handler in HANDLERS:\n"
    "        handler(items)\n"
)


@pytest.mark.asyncio
async def test_registering_decorator_blocks_complete(tmp_path) -> None:
    # #1596：`@register` 可能把目标登记进注册表，0 调用方不是不存在的证据。
    root = await _index(tmp_path, _REGISTERED)

    result = await _callers(root, "lonely")

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reason"] == DECORATED_REASON
    assert result["next_step"] == (
        "No resolved caller for 'lonely', but it is decorated with `@register`, "
        "which may register it for dispatch the call graph does not record, so "
        "this is not evidence of absence."
    )


@pytest.mark.asyncio
async def test_passive_decorator_keeps_complete(tmp_path) -> None:
    # #1596：`lru_cache` 只包装、不登记，真正无人调用时仍答 complete。
    root = await _index(tmp_path, _REGISTERED)

    result = await _callers(root, "cached")

    assert (result["caller_count"], result["completeness"]) == (0, "complete")


@pytest.mark.parametrize(
    ("callee", "expected"),
    [
        ('"\\n".join', False),
        ("header.get", False),
        ("self.handle", False),
        ("extractors.run", False),
        ("local_helper", False),
        ("make().run", False),
        ("lonely", True),
        ("self.lonely", True),
        ("pkg.mod.lonely", True),
        ("make().lonely", True),
        ('getattr(mod, "lonely")', True),
        ('getattr(mod, "other")', False),
        ("getattr(mod, name)", True),
        ("getattr(importlib.import_module(m), c).run", True),
        ("HANDLERS[name]", True),
        ('HANDLERS["read"]', True),
        ('globals()["x"]', True),
        ("vars(obj).get", True),
        ("make()()", True),
        ("", True),
    ],
)
def test_could_name_target_matches_name_or_computed_dispatch(
    callee: str, expected: bool
) -> None:
    # #1596：同名，或名字在运行时计算出来，才可能指向目标。
    assert could_name_target(callee, "lonely") is expected


def test_partition_moves_other_names_to_excluded_without_mutating() -> None:
    # #1596：被排除的点带上原因码，原始列表保持不变。
    sites = [
        {"file": "m.py", "line": 3, "callee": "d.get", "classification": "unresolved"},
        {
            "file": "m.py",
            "line": 5,
            "callee": "HANDLERS[k]",
            "classification": "unresolved",
        },
    ]

    kept, excluded = partition_by_target(sites, "lonely")

    assert kept == [sites[1]]
    assert excluded == [
        {
            "file": "m.py",
            "line": 3,
            "callee": "d.get",
            "classification": "excluded",
            "reason_code": NAMES_OTHER_REASON,
        }
    ]
    assert sites[0]["classification"] == "unresolved"
