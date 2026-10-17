"""#1643：有调用方时，声明文件守卫同样按名收窄，并由同一组复核门兜底。

dogfood 第 7 轮：34 个被调用的模块级函数中 31 个答 ``incomplete`` /
``UNRESOLVED_IN_DECLARING_FILE``，其中 30 个的调用方列表其实已是全集——留在守卫
里的只是 ``record.get``、``"\\n".join``、``Path(...).resolve`` 这类名字不同的调用。
#1596 的收窄只在 0 调用方时运行，因为它依赖非调用引用门（别名、回调、容器）；
本修复让收窄在有调用方时也运行，并在收窄确实排除了调用点时同样执行该门。

负对照：同名的未解析调用、仅同名入边（importlib 加载的模块）、计算式分发、
别名 / 回调 / ``import ... as``、登记型装饰器——都必须保持 ``incomplete``。
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_dispatch import NAMES_OTHER_REASON
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

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
#: 声明文件：目标 `lonely` 旁边只有名字不同的未解析调用。
_PLAIN = (
    "def lonely(items):\n"
    '    return "x".join(items)\n\n\n'
    "def reader(d, header):\n"
    '    value = d.get("k")\n'
    '    return header.get("h"), value\n'
)
_SAME_FILE_CALLER = "\n\ndef user():\n    return lonely([])\n"
_CROSS_FILE_CALLER = "from mod import lonely\n\n\ndef use():\n    return lonely([])\n"


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


# ---------------------------------------------------------------------------
# 正例：留在守卫里的调用点都不可能点名目标，调用方列表即为普查。
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_file_caller_with_unrelated_calls_answers_complete(tmp_path) -> None:
    # #1643：`"x".join` / `d.get` / `header.get` 不可能调用 lonely。
    root = await _index_files(tmp_path, {"mod.py": _PLAIN + _SAME_FILE_CALLER})

    result = await _callers(root, "lonely")

    assert (result["caller_count"], result["completeness"]) == (1, "complete")
    assert (result["completeness_reason"], result["completeness_reasons"]) == (None, [])
    assert [c["name"] for c in result["callers"]] == ["user"]
    assert result["unresolved_in_declaring_files"] == 0
    assert result["unresolved_sites"] == []
    assert result["excluded_by_reason"] == {NAMES_OTHER_REASON: 3}
    # 复核门确实运行过：它的证据字段随答案给出。
    assert result["non_call_references"] == 0


@pytest.mark.asyncio
async def test_cross_file_imported_caller_answers_complete(tmp_path) -> None:
    # #1643：`from mod import lonely` 只是绑定同名，调用本身已有调用边。
    root = await _index_files(
        tmp_path, {"mod.py": _PLAIN, "client.py": _CROSS_FILE_CALLER}
    )

    result = await _callers(root, "lonely")

    assert (result["caller_count"], result["completeness"]) == (1, "complete")
    assert [(c["file"], c["name"]) for c in result["callers"]] == [("client.py", "use")]
    assert result["non_call_references"] == 0


@pytest.mark.asyncio
async def test_multiline_import_binding_is_not_a_reference(tmp_path) -> None:
    # #1643：括号内跨行的导入名同样只是绑定。
    client = (
        "from mod import (\n    reader,\n    lonely,\n)\n\n\n"
        "def use():\n    return lonely([]), reader({}, {})\n"
    )
    root = await _index_files(tmp_path, {"mod.py": _PLAIN, "client.py": client})

    result = await _callers(root, "lonely")

    assert (result["caller_count"], result["completeness"]) == (1, "complete")


# ---------------------------------------------------------------------------
# 负对照：任何真实的、可能指向目标的未解析或仅同名入边都让答案停在 incomplete。
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unresolved_same_name_call_keeps_incomplete(tmp_path) -> None:
    # #1643 负对照：`obj.lonely()` 的接收者未知，可能就是目标。
    source = (
        _PLAIN + _SAME_FILE_CALLER + "\n\ndef other(obj):\n    return obj.lonely()\n"
    )
    root = await _index_files(tmp_path, {"mod.py": source})

    result = await _callers(root, "lonely")

    assert result["completeness"] == "incomplete"
    assert result["completeness_reason"] in {
        "UNRESOLVED_INBOUND",
        "UNRESOLVED_IN_DECLARING_FILE",
        "NAME_ONLY_INBOUND",
    }


@pytest.mark.asyncio
async def test_importlib_loaded_attribute_call_keeps_name_only(tmp_path) -> None:
    # #1643 负对照（第 7 轮 `collector.digest_bytes`）：经 importlib 加载的模块
    # 上的同名调用无法绑定到目标，只能凭名字匹配，不得宣称 complete。
    support = (
        "import hashlib\n\n\n"
        "def digest_bytes(data):\n"
        "    return hashlib.sha256(data).hexdigest()\n\n\n"
        "def bundle(blob):\n"
        "    return digest_bytes(blob)\n"
    )
    loader = (
        "import importlib.util\n\n\n"
        "def _load():\n"
        '    spec = importlib.util.spec_from_file_location("c", "support.py")\n'
        "    module = importlib.util.module_from_spec(spec)\n"
        "    spec.loader.exec_module(module)\n"
        "    return module\n\n\n"
        "def test_digest():\n"
        "    collector = _load()\n"
        '    assert collector.digest_bytes(b"x")\n'
    )
    # 第二处同名定义让 `collector.digest_bytes` 无法唯一绑定（第 7 轮的真实情形）。
    other = "def digest_bytes(data):\n    return data\n"
    root = await _index_files(
        tmp_path, {"support.py": support, "test_c.py": loader, "other.py": other}
    )

    result = await _callers(root, "digest_bytes")

    assert result["completeness"] == "incomplete"
    # `test_digest` 仅凭同名匹配列出，因此列表只是下界。
    assert sorted(c["name"] for c in result["callers"]) == ["bundle", "test_digest"]
    assert result["completeness_reasons"] == ["NAME_ONLY_INBOUND"]


@pytest.mark.asyncio
async def test_unique_importlib_attribute_call_is_listed(tmp_path) -> None:
    # #1643：名字唯一时 `collector.digest_bytes(...)` 已绑定为调用边并列出，
    # complete 是真实的普查而不是漏报。
    support = (
        "def digest_bytes(data):\n    return data\n\n\n"
        "def bundle(blob):\n    return digest_bytes(blob)\n"
    )
    loader = (
        "import importlib\n\n\n"
        "def test_digest():\n"
        '    collector = importlib.import_module("support")\n'
        '    assert collector.digest_bytes(b"x")\n'
    )
    root = await _index_files(tmp_path, {"support.py": support, "test_c.py": loader})

    result = await _callers(root, "digest_bytes")

    assert sorted(c["name"] for c in result["callers"]) == ["bundle", "test_digest"]
    assert result["completeness"] == "complete"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dispatch",
    [
        "import sys\n\n\ndef run(name):\n"
        "    return getattr(sys.modules[__name__], name)()\n",
        "HANDLERS = {}\n\n\ndef run(name):\n    return HANDLERS[name]()\n",
    ],
)
async def test_computed_dispatch_keeps_incomplete(tmp_path, dispatch: str) -> None:
    # #1643 负对照：计算式分发不点名任何符号，可能就是目标的调用方。
    source = _PLAIN + _SAME_FILE_CALLER + "\n\n" + dispatch
    root = await _index_files(tmp_path, {"mod.py": source})

    result = await _callers(root, "lonely")

    assert (result["caller_count"], result["completeness"]) == (1, "incomplete")
    assert result["completeness_reason"] == "UNRESOLVED_IN_DECLARING_FILE"
    assert result["unresolved_in_declaring_files"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("extra", "line"),
    [
        # 别名：`alias()` 名字不同，`alias = lonely` 是按名引用。
        ("\n\ndef run(items):\n    alias = lonely\n    return alias(items)\n", 15),
        # 回调：`map(lonely, ...)` 传递引用，调用由 map 发生。
        ("\n\ndef run(xs):\n    return list(map(lonely, xs))\n", 15),
    ],
)
async def test_non_call_reference_keeps_incomplete(tmp_path, extra, line) -> None:
    # #1643 负对照：收窄依赖非调用引用门；门找到引用时答案仍是下界。
    source = _PLAIN + _SAME_FILE_CALLER + extra
    root = await _index_files(tmp_path, {"mod.py": source})

    result = await _callers(root, "lonely")

    assert (result["caller_count"], result["completeness"]) == (1, "incomplete")
    assert result["completeness_reasons"] == ["NON_CALL_REFERENCES"]
    assert result["non_call_reference_sites"] == [{"file": "mod.py", "line": line}]


@pytest.mark.asyncio
async def test_import_alias_keeps_incomplete(tmp_path) -> None:
    # #1643 负对照：`import ... as lo` 之后的 `lo()` 名字不同，导入行就是引用。
    client = "from mod import lonely as lo\n\n\ndef use():\n    return lo([])\n"
    source = _PLAIN + _SAME_FILE_CALLER
    root = await _index_files(tmp_path, {"mod.py": source, "client.py": client})

    result = await _callers(root, "lonely")

    assert result["completeness"] == "incomplete"
    assert result["completeness_reasons"] == ["NON_CALL_REFERENCES"]
    assert {"file": "client.py", "line": 1} in result["non_call_reference_sites"]


@pytest.mark.asyncio
async def test_registering_decorator_keeps_incomplete(tmp_path) -> None:
    # #1643 负对照：`@register` 可能把目标登记进注册表，由名字不同的调用分发。
    source = (
        "HANDLERS = []\n\n\n"
        "def register(func):\n"
        "    HANDLERS.append(func)\n"
        "    return func\n\n\n"
        "@register\n" + _PLAIN + _SAME_FILE_CALLER
    )
    root = await _index_files(tmp_path, {"mod.py": source})

    result = await _callers(root, "lonely")

    assert (result["caller_count"], result["completeness"]) == (1, "incomplete")
    assert result["completeness_reasons"] == ["DECORATOR_MAY_REGISTER"]


@pytest.mark.asyncio
async def test_reexport_only_function_is_not_a_confident_absence(tmp_path) -> None:
    # #1643 负对照：0 调用方时 `__init__` 的再导出仍是引用——它可能是仓库外
    # 调用的公开 API，"0 个调用方、complete" 会被当作可删除的死代码。
    root = await _index_files(
        tmp_path,
        {"pkg/mod.py": _PLAIN, "pkg/__init__.py": "from .mod import lonely\n"},
    )

    result = await _callers(root, "lonely")

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reasons"] == ["NON_CALL_REFERENCES"]
    assert result["non_call_reference_sites"] == [
        {"file": "pkg/__init__.py", "line": 1}
    ]
