"""#1596：RFC-0028 §1.2 作用域守卫只计入“可能点名目标”的未解析调用点。

实测（dogfood 第 3/4 轮）：模块级函数 18/18、12/12 永远答 ``unknown``，即使
确实无人引用——声明文件里任意一个 ``"\\n".join`` / ``header.get`` 都被当作
可能指向它的调用。属性名与目标名不同的调用点不可能调用目标：经由别名、回调或
字典到达目标都需要一次按名引用，而 0 调用方时非调用引用门（#1593）会扫描它。
计算式分发（``getattr(x, name)``、``HANDLERS[name]``、``globals()[...]``）
不点名任何符号，仍然保留守卫。
"""

from __future__ import annotations

import re

import pytest

from tree_sitter_analyzer.mcp.tools.callers_checks import (
    REQUIRED_CHECKS,
    Ledger,
    prove,
    prove_edges,
)
from tree_sitter_analyzer.mcp.tools.callers_decorators import DECORATED_REASON
from tree_sitter_analyzer.mcp.tools.callers_dispatch import (
    NAMES_OTHER_REASON,
    could_name_target,
    partition_by_target,
    trailing_segment,
)
from tree_sitter_analyzer.mcp.tools.callers_outcomes import Checked, checked
from tree_sitter_analyzer.mcp.tools.callers_reasons import COMPLETENESS_REASONS
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
    return await _index_files(root, {"mod.py": source})


async def _index_files(root, files: dict[str, str]) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel_path, text in {"store.py": _AMBIGUOUS, **files}.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 20}
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
async def test_other_names_no_longer_gate_when_callers_exist(tmp_path) -> None:
    # #1643（取代 #1596 的“有调用方时保持原守卫”）：非调用引用门现在对有调用方的
    # 答案同样运行，因此按名收窄；名字不同的调用点被排除，列表即为普查。
    root = await _index(tmp_path, _PLAIN + "\n\ndef user():\n    return lonely([])\n")

    result = await _callers(root, "lonely")

    assert (result["caller_count"], result["completeness"]) == (1, "complete")
    assert result["unresolved_in_declaring_files"] == 0
    assert result["excluded_by_reason"] == {NAMES_OTHER_REASON: 3}


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
    "import functools\n\n"
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
        # #1632：标记只作用于被调用的尾段；尾段 `.run` / `.get` 不可能是目标。
        ("getattr(importlib.import_module(m), c).run", False),
        ("HANDLERS[name]", True),
        ('HANDLERS["read"]', True),
        ('globals()["x"]', True),
        ("vars(obj).get", False),
        ("received[0].get", False),
        ('getattr(index, "action_map", {}).get', False),
        ('d["a.b"].get', False),
        ("x[0].lonely", True),
        ("self.handlers[name]", True),
        ("obj.__getattribute__(name)", True),
        # 经 `call` / `apply` / `__call__` 转发时，被调用的仍是计算出的对象。
        ("HANDLERS[name].__call__", True),
        ("handlers[name].call", True),
        ("getattr(m, name).apply", True),
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


# ---------------------------------------------------------------------------
# #1596 / #1614 / #1623：dogfood 第 5 轮（2026-10-16）的危险假“不存在”形状。
# #1614 让它们答成 `complete, 0`，#1626 因此回滚；重新落地时每一种都必须不是
# `complete, 0`。对照组仍须答 `complete, 0`（有用性）。
# ---------------------------------------------------------------------------

#: 目标函数：函数体只有一个无关的未解析调用。
_TARGET = 'def target(items):\n    return "x".join(items)\n'

#: 模块作用域调用形状（#1622）：调用方应列为 ``<module>``。
_MODULE_SCOPE = {
    "assignment": _TARGET + "\n\nX = target([])\n",
    "class_body": _TARGET + "\n\nclass Holder:\n    attr = target([])\n",
    "if_main": _TARGET + '\n\nif __name__ == "__main__":\n    target([])\n',
    "lambda": _TARGET + "\n\nRUN = lambda: target([])\n",
    "comprehension": _TARGET + "\n\nVALUES = [target([]) for _ in range(2)]\n",
    "decorator_argument": (
        _TARGET + "\n\ndef deco(value):\n    return lambda fn: fn\n\n\n"
        "@deco(target([]))\ndef other():\n    return 1\n"
    ),
}

#: 项目内的登记器：把函数存进注册表，之后以名字不同的 ``handler()`` 分发。
_REGISTRY = (
    "HANDLERS = []\n\n\n"
    "def register(*names):\n"
    "    def wrap(func):\n"
    "        HANDLERS.append(func)\n"
    "        return func\n"
    "    return wrap\n\n\n"
    "def fire():\n"
    "    for handler in HANDLERS:\n"
    "        handler([])\n"
)

#: 装饰器登记形状（#1623）：旧的逐行扫描看不到前两种，按裸名豁免了第三种。
_DECORATED = {
    "multi_line": _REGISTRY + '\n\n@register(\n    "multi",\n)\n' + _TARGET,
    "comment_separated": _REGISTRY + '\n\n@register("x")\n# 说明\n' + _TARGET,
    "project_cache": (
        "HANDLERS = []\n\n\n"
        "def cache(fn):\n"
        "    HANDLERS.append(fn)\n"
        "    return fn\n\n\n"
        "@cache\n" + _TARGET
    ),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", sorted(_MODULE_SCOPE))
async def test_module_scope_call_lists_module_caller(tmp_path, shape: str) -> None:
    # #1622/#1628：模块作用域调用点计为 `<module>` 调用方，不再是 `complete, 0`。
    root = await _index_files(tmp_path, {"mod.py": _MODULE_SCOPE[shape]})

    result = await _callers(root, "target")

    assert result["caller_count"] == 1
    assert [c["name"] for c in result["callers"]] == ["<module>"]


#: 装饰器工厂 `@mod.factory("x")`：导入时调用 factory，并登记 handler。
_FACTORY_FILES = {
    "mod.py": (
        "REGISTRY = {}\n\n\n"
        "def factory(name):\n"
        "    def wrap(fn):\n"
        "        REGISTRY[name] = fn\n"
        "        return fn\n"
        "    return wrap\n"
    ),
    "user.py": 'import mod\n\n\n@mod.factory("x")\ndef handler():\n    return 1\n',
}


@pytest.mark.asyncio
async def test_decorator_factory_lists_module_caller(tmp_path) -> None:
    # #1622/#1628：`@mod.factory("x")` 在导入时调用 factory。
    root = await _index_files(tmp_path, _FACTORY_FILES)

    result = await _callers(root, "factory")

    assert result["caller_count"] == 1
    assert [c["name"] for c in result["callers"]] == ["<module>"]


@pytest.mark.asyncio
async def test_handler_registered_by_decorator_factory_is_unknown(tmp_path) -> None:
    # #1623：被 `@mod.factory("x")` 登记的 handler，装饰器可能登记它。
    root = await _index_files(tmp_path, _FACTORY_FILES)

    result = await _callers(root, "handler")

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reason"] == DECORATED_REASON


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", sorted(_DECORATED))
async def test_registering_decorator_shapes_block_complete(
    tmp_path, shape: str
) -> None:
    # #1623：装饰器从 AST 读取；项目自定义的 `cache` 不是 functools.cache。
    root = await _index_files(tmp_path, {"mod.py": _DECORATED[shape]})

    result = await _callers(root, "target")

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reason"] == DECORATED_REASON


#: 字符串与配置文件中的引用（#1624/#1629）：grep 能找到，absence 不得更弱。
_TEXT_REFERENCES = {
    "toml_entry_point": {
        "pyproject.toml": '[project.scripts]\ntool = "pkg.mod:target"\n',
    },
    "colon_string": {
        "loader.py": 'SPEC = "pkg.mod:target"\n',
    },
    "exec_string": {
        "runner.py": 'exec("mod.target([])")\n',
    },
    "workflow_yml": {
        ".github/workflows/ci.yml": "jobs:\n  t:\n    steps:\n"
        "      - run: python -c 'import mod; mod.target([])'\n",
    },
}


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", sorted(_TEXT_REFERENCES))
async def test_text_references_block_complete(tmp_path, shape: str) -> None:
    # #1624/#1629：入口点、导入串、exec 串、workflow 中的名字都是可能的引用。
    root = await _index_files(tmp_path, {"mod.py": _TARGET, **_TEXT_REFERENCES[shape]})

    result = await _callers(root, "target")

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reason"] == "NON_CALL_REFERENCES"
    assert result["non_call_references"] == 1


@pytest.mark.asyncio
async def test_unreferenced_function_with_unrelated_calls_answers_complete(
    tmp_path,
) -> None:
    # #1596 对照组：只有 `"x".join` / `d.get` 这类无关未解析调用，答 complete。
    plain = _TARGET + '\n\ndef reader(d):\n    return d.get("k")\n'
    root = await _index_files(tmp_path, {"mod.py": plain})

    result = await _callers(root, "target")

    assert (result["caller_count"], result["completeness"]) == (0, "complete")
    assert result["completeness_reason"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "decorated",
    [
        "import functools\n\n\n@functools.lru_cache(maxsize=1)\n",
        "from functools import lru_cache\n\n\n@lru_cache\n",
        "import functools as ft\n\n\n@ft.lru_cache(\n    maxsize=None,\n)\n",
    ],
)
async def test_known_wrapper_decorator_keeps_complete(tmp_path, decorated: str) -> None:
    # #1623 对照组：经导入解析到 functools.lru_cache，只包装不登记，仍答 complete。
    root = await _index_files(tmp_path, {"mod.py": decorated + _TARGET})

    result = await _callers(root, "target")

    assert (result["caller_count"], result["completeness"]) == (0, "complete")
    assert result["completeness_reason"] is None


# ---------------------------------------------------------------------------
# #1632：dogfood 第 6 轮。(1) 调用边层的非 complete 答案带原因码；
# (2) 计算式分发标记只作用于被调用的尾段，`received[0].get()` 不再守卫。
# ---------------------------------------------------------------------------

#: 尾段是普通属性名的调用：前缀里有 `[` / `getattr(`，但被调用的 `.get` 不可能是目标。
_TRAILING_PLAIN = (
    _TARGET + "\n\ndef reader(received, index):\n"
    "    first = received[0].get()\n"
    '    return first, getattr(index, "action_map", {}).get()\n'
)
#: 被调用的就是计算结果本身：仍须守卫。
_TRAILING_COMPUTED = {
    "getattr_call": "import sys\n\n\n" + _TARGET + "\n\ndef run(name):\n"
    "    mod = sys.modules[__name__]\n    return getattr(mod, name)()\n",
    "subscript_call": "HANDLERS = {}\n\n\n" + _TARGET + "\n\ndef run(name):\n"
    "    return HANDLERS[name]()\n",
    "forwarded_call": "HANDLERS = {}\n\n\n" + _TARGET + "\n\ndef run(name):\n"
    "    return HANDLERS[name].__call__()\n",
}


@pytest.mark.asyncio
async def test_plain_trailing_segment_does_not_gate(tmp_path) -> None:
    # #1632：`received[0].get` / `getattr(i, "a", {}).get` 调用的是 `.get`，不是目标。
    root = await _index_files(tmp_path, {"mod.py": _TRAILING_PLAIN})

    result = await _callers(root, "target")

    assert (result["caller_count"], result["completeness"]) == (0, "complete")
    assert (result["completeness_reason"], result["completeness_reasons"]) == (None, [])
    assert [s["callee"] for s in result["excluded_sites"]] == [
        '"x".join',
        "received[0].get",
        'getattr(index, "action_map", {}).get',
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", sorted(_TRAILING_COMPUTED))
async def test_computed_trailing_segment_still_gates(tmp_path, shape: str) -> None:
    # #1632：`getattr(m, name)()`、`HANDLERS[name]()` 与经 `__call__` 转发的调用仍守卫。
    root = await _index_files(tmp_path, {"mod.py": _TRAILING_COMPUTED[shape]})

    result = await _callers(root, "target")

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reason"] == "UNRESOLVED_IN_DECLARING_FILE"
    assert result["unresolved_in_declaring_files"] == 1


@pytest.mark.asyncio
async def test_unresolved_inbound_carries_its_reason(tmp_path) -> None:
    # #1632：接收者未知的 `d.get()` 是指向 `Store.get` 的未解析入边。
    root = await _index_files(
        tmp_path, {"mod.py": "def use(d):\n    return d.get(1)\n"}
    )

    result = await _callers(root, "Store.get")

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reason"] == "UNRESOLVED_INBOUND"
    assert result["completeness_reasons"] == ["UNRESOLVED_INBOUND", "NAME_ONLY_INBOUND"]


@pytest.mark.asyncio
async def test_lower_bound_caller_list_carries_its_reason(tmp_path) -> None:
    # #1632：有调用方时 `incomplete` 同样必须点名缺口（第 6 轮 28/30 为 null）。
    # #1643：计算式分发仍可能点名目标，守卫保留（名字不同的调用点已不再守卫）。
    dispatch = "\n\nHANDLERS = {}\n\n\ndef run(name):\n    return HANDLERS[name]()\n"
    root = await _index(
        tmp_path, _PLAIN + "\n\ndef user():\n    return lonely([])\n" + dispatch
    )

    result = await _callers(root, "lonely")

    assert (result["caller_count"], result["completeness"]) == (1, "incomplete")
    assert result["completeness_reasons"] == ["UNRESOLVED_IN_DECLARING_FILE"]


@pytest.mark.asyncio
async def test_empty_evidence_base_carries_its_reason(tmp_path) -> None:
    # #1632：图里没有任何调用边时，0 无法区分“无人调用”与“从未填充”。
    path = tmp_path / "mod.py"
    path.write_text("def alone():\n    return 1\n", encoding="utf-8")
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    await CodeGraphFullIndexTool(str(tmp_path)).execute({"mode": "full"})

    result = await _callers(str(tmp_path), "alone")

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reasons"] == ["EMPTY_EVIDENCE_BASE"]


@pytest.mark.asyncio
async def test_unreadable_guard_carries_its_reason(tmp_path, monkeypatch) -> None:
    # #1632：声明文件守卫读取失败是 unknown，并以 UNCHECKED 原因码点名。
    from tree_sitter_analyzer.mcp.tools import callers_tool

    root = await _index(tmp_path, _PLAIN)
    monkeypatch.setattr(callers_tool, "_declaring_file_unresolved", lambda *_: None)

    result = await _callers(root, "lonely")

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reasons"] == ["UNRESOLVED_INBOUND_UNCHECKED"]


#: #1632 不变式所覆盖的本文件全部夹具（每组一个项目）。
_INVARIANT_PROJECTS = {
    "plain": {"mod.py": _PLAIN},
    "dispatch": {"mod.py": _DISPATCH},
    "alias": {"mod.py": _ALIAS},
    "registered": {"mod.py": _REGISTERED},
    "factory": _FACTORY_FILES,
    "trailing_plain": {"mod.py": _TRAILING_PLAIN},
    **{f"module_{k}": {"mod.py": v} for k, v in _MODULE_SCOPE.items()},
    **{f"decorated_{k}": {"mod.py": v} for k, v in _DECORATED.items()},
    **{f"computed_{k}": {"mod.py": v} for k, v in _TRAILING_COMPUTED.items()},
    **{f"text_{k}": {"mod.py": _TARGET, **v} for k, v in _TEXT_REFERENCES.items()},
}
#: 原因码闭集（与 docs/agent-envelope-contract.md 的表一致）。
_CLOSED_REASONS = {
    "UNRESOLVED_INBOUND_UNCHECKED",
    "NAME_ONLY_INBOUND_UNCHECKED",
    "UNATTRIBUTED_CALL_SITES_UNCHECKED",
    "UNRESOLVED_INBOUND",
    "UNRESOLVED_IN_DECLARING_FILE",
    "NAME_ONLY_INBOUND",
    "UNATTRIBUTED_CALL_SITES",
    "EMPTY_EVIDENCE_BASE",
    "SOURCE_INDEX_MISMATCH",
    "SOURCE_SCOPE_UNKNOWN",
    "MISSING_INDEX",
    "SYMBOL_NOT_DEFINED",
    "SYMBOL_IN_EXCLUDED_FILE",
    "SYMBOL_DEFINITION_UNCHECKED",
    "UNINDEXED_SOURCE_FILES",
    "UNINDEXED_SOURCE_UNCHECKED",
    "NON_CALL_REFERENCES",
    "NON_CALL_REFERENCES_UNCHECKED",
    "ACCESSOR_NOT_CALL_EDGES",
    "ACCESSOR_UNCHECKED",
    "DECORATOR_MAY_REGISTER",
}


def _reason_offence(result: dict) -> str | None:
    """违反 #1632 不变式时返回说明；否则 None。"""
    reason, reasons = result["completeness_reason"], result["completeness_reasons"]
    if result["completeness"] == "complete":
        return None if (reason, reasons) == (None, []) else "complete with a reason"
    if reason is None or reasons[:1] != [reason]:
        return f"{result['completeness']} without a primary reason"
    unknown = sorted(set(reasons) - _CLOSED_REASONS)
    return f"reasons outside the closed set: {unknown}" if unknown else None


@pytest.mark.asyncio
@pytest.mark.parametrize("project", sorted(_INVARIANT_PROJECTS))
async def test_every_non_complete_answer_names_a_closed_reason(
    tmp_path, project: str
) -> None:
    # #1632 不变式：夹具中每个函数 / 方法的答案，非 complete 必有闭集内的主因。
    files = _INVARIANT_PROJECTS[project]
    root = await _index_files(tmp_path, files)
    names = {"Store.get", "Store.join", "Cache.get", "get", "join"}
    for text in files.values():
        names.update(re.findall(r"^\s*def (\w+)", text, flags=re.MULTILINE))

    offences = {}
    for name in sorted(names):
        result = await _callers(root, name)
        offence = _reason_offence(result) or _evidence_offence(result)
        if offence is not None:
            offences[name] = offence

    assert offences == {}


#: #1706：主因 -> 承载其证据位置的字段（``next_step`` 须点名其中第一个位置）。
_SITE_EVIDENCE = {
    "UNRESOLVED_INBOUND": "unresolved_inbound_sites",
    "UNRESOLVED_IN_DECLARING_FILE": "unresolved_sites",
    "NAME_ONLY_INBOUND": "name_only_sites",
    "NON_CALL_REFERENCES": "non_call_reference_sites",
}


def _evidence_offence(result: dict) -> str | None:
    """#1706 契约：非 complete 的答案带主因的证据，且 next_step 点名它（有无调用方都一样）。"""
    if result["completeness"] == "complete":
        return None
    reason = result["completeness_reason"]
    step = result.get("next_step") or ""
    if not step or step.startswith("Review callers above"):
        return f"{reason}: generic or missing next_step"
    field = _SITE_EVIDENCE.get(reason)
    if field is None:
        return None
    sites = result.get(field) or []
    if not sites:
        return f"{reason}: {field} is empty"
    first = f"{sites[0]['file']}:{sites[0]['line']}"
    return None if first in step else f"{reason}: next_step does not name {first}"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("received[0].get", "get"),
        ('getattr(x, "a.b").get', "get"),
        ("x?.run", "run"),
        ("lonely", "lonely"),
        ("make(", None),
        ("a)b.c", None),
        ('d["x].y', None),
    ],
)
def test_trailing_segment_splits_at_the_last_top_level_dot(text, expected) -> None:
    # #1632：括号与引号内的 `.` 不切分；不配对时无法判定。
    assert trailing_segment(text) == expected


def test_closed_reason_set_matches_the_source_of_truth() -> None:
    # #1632：测试中的闭集与 callers_reasons.COMPLETENESS_REASONS 完全一致。
    assert set(COMPLETENESS_REASONS) == _CLOSED_REASONS


_SCOPE = ("f", None)


def _edges(callers, unresolved, declaring, name_only, unattributed, empty) -> Ledger:
    """RFC-0040：按旧 EdgeEvidence 的六个输入构造调用边层检查记录。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import _edge_ledger

    return _edge_ledger(
        _SCOPE,
        unresolved_inbound=unresolved,
        unresolved_in_declaring_files=declaring,
        name_only_inbound=name_only,
        name_only_check=None,
        unattributed_call_sites=unattributed,
        empty_evidence_base=empty,
    )


def _all_review_checks_pass(ledger: Ledger) -> Ledger:
    return ledger.record_all(
        (spec.name, Checked(_SCOPE))
        for spec in REQUIRED_CHECKS
        if spec.layer == "review"
    )


@pytest.mark.parametrize(
    ("edges", "expected"),
    [
        ((0, 0, 0, 0, 2, False), ("incomplete", ("UNATTRIBUTED_CALL_SITES",))),
        (
            (0, None, 0, 1, 0, True),
            (
                "unknown",
                (
                    "UNRESOLVED_INBOUND_UNCHECKED",
                    "NAME_ONLY_INBOUND",
                    "EMPTY_EVIDENCE_BASE",
                ),
            ),
        ),
        ((3, 1, 0, 0, 0, False), ("incomplete", ("UNRESOLVED_INBOUND",))),
        ((0, 0, 0, 0, 0, False), ("complete", ())),
    ],
)
def test_edge_completeness_lists_every_applicable_reason(edges, expected) -> None:
    # #1632：主因在首位；全部成立的原因按固定顺序列出。
    proof = prove_edges(_edges(*edges), edges[0])
    assert (proof.completeness, proof.reasons) == expected


def test_absence_gate_reason_replaces_empty_edge_reasons() -> None:
    # #1632：复核门只在调用边层为 complete 时运行，其原因即为唯一原因。
    clean = _all_review_checks_pass(_edges(0, 0, 0, 0, 0, False))
    found = clean.record("non_call_references", checked(_SCOPE, "NON_CALL_REFERENCES"))
    assert prove(found, 0).reasons == ("NON_CALL_REFERENCES",)
    assert (prove(clean, 0).completeness, prove(clean, 0).reasons) == ("complete", ())
