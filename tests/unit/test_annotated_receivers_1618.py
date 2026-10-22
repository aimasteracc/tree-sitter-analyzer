"""#1618 / RFC-0038：接收者类型由注解给出时，调用归属到注解所指类的方法。

经公开的 ``nav callers``（``CodeGraphCallersTool``）在已索引的夹具上验证：每一种
类型来源都增加调用方；负对照确保错误类型、联合类型、未注解与被重新绑定的接收者
不被归属，子类覆写不会因为基类注解的边而答 ``complete``。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_STORE = (
    "class GenerationStore:\n"
    "    def publish(self, item):\n"
    "        return item\n\n\n"
    "class Other:\n"
    "    def publish(self, item):\n"
    "        return item\n\n\n"
    "class FakeStore(GenerationStore):\n"
    "    def publish(self, item):\n"
    "        return None\n"
)
_FACTORY = (
    "from store import GenerationStore\n\n\n"
    "def project_store(root) -> GenerationStore:\n"
    "    return build(root)\n\n\n"
    "def maybe_store(root) -> 'GenerationStore | None':\n"
    "    return None\n"
)
_USERS = (
    "from typing import Optional\n\n"
    "import factory\n"
    "from factory import project_store\n"
    "from store import GenerationStore, Other\n\n\n"
    "def by_param(store: GenerationStore):\n"
    "    store.publish(1)\n\n\n"
    "def by_local():\n"
    "    store: GenerationStore = make_any()\n"
    "    store.publish(2)\n\n\n"
    "def by_return(root):\n"
    "    store = project_store(root)\n"
    "    store.publish(3)\n\n\n"
    "def by_module_return(root):\n"
    "    store = factory.maybe_store(root)\n"
    "    store.publish(4)\n\n\n"
    "def by_optional(store: Optional[GenerationStore]):\n"
    "    if store is not None:\n"
    "        store.publish(5)\n\n\n"
    "class Owner:\n"
    "    cached: GenerationStore\n\n"
    "    def __init__(self, store: GenerationStore, other):\n"
    "        self._store = store\n"
    "        self._made = GenerationStore()\n"
    "        self._typed: GenerationStore = other\n\n"
    "    def flush(self):\n"
    "        self._store.publish(6)\n\n"
    "    def flush_made(self):\n"
    "        self._made.publish(7)\n\n"
    "    def flush_typed(self):\n"
    "        self._typed.publish(8)\n\n"
    "    def flush_cached(self):\n"
    "        self.cached.publish(9)\n\n"
    "    @property\n"
    "    def prop(self) -> GenerationStore:\n"
    "        return self._store\n\n"
    "    def via_prop(self):\n"
    "        self.prop.publish(10)\n\n\n"
    "def wrong_type(o: Other):\n"
    "    o.publish(11)\n\n\n"
    "def union(s: 'GenerationStore | Other'):\n"
    "    s.publish(12)\n\n\n"
    "def unannotated(s):\n"
    "    s.publish(13)\n\n\n"
    "def rebound(root, other):\n"
    "    store = project_store(root)\n"
    "    store = other\n"
    "    store.publish(14)\n\n\n"
    "def shadowed(store: GenerationStore, items):\n"
    "    return [store.publish(x) for store in items]\n"
)

#: 正向来源：调用方名 → 类型来源。
_POSITIVE = {
    "by_param": "param",
    "by_local": "local",
    "by_return": "return",
    "by_module_return": "return",
    "by_optional": "param",
    "flush": "attribute",
    "flush_made": "attribute",
    "flush_typed": "attribute",
    "flush_cached": "attribute",
    "via_prop": "attribute",
}
_NEGATIVE = ("wrong_type", "union", "unannotated", "rebound", "shadowed")


def _def_line(source: str, name: str) -> int:
    for number, text in enumerate(source.splitlines(), start=1):
        if text.lstrip().startswith(f"def {name}("):
            return number
    raise AssertionError(f"no def {name}")


@pytest.fixture
async def store_root(tmp_path: Path) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "store.py").write_text(_STORE, encoding="utf-8")
    (tmp_path / "factory.py").write_text(_FACTORY, encoding="utf-8")
    (tmp_path / "users.py").write_text(_USERS, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True
    return str(tmp_path)


async def _callers(root: str, name: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "include_bodies": False}
    )


def _by_name(result: dict) -> dict[str, dict]:
    return {entry["name"]: entry for entry in result["callers"]}


@pytest.mark.asyncio
async def test_every_annotation_source_adds_a_caller(store_root: str) -> None:
    result = await _callers(store_root, "GenerationStore.publish")

    callers = _by_name(result)
    assert {name: callers[name]["line"] for name in _POSITIVE if name in callers} == {
        name: _def_line(_USERS, name) for name in _POSITIVE
    }


@pytest.mark.asyncio
async def test_annotated_callers_carry_provenance(store_root: str) -> None:
    result = await _callers(store_root, "GenerationStore.publish")

    callers = _by_name(result)
    assert {
        name: (
            callers[name].get("resolution_kind"),
            callers[name].get("type_source"),
            callers[name].get("receiver_type"),
            callers[name].get("confidence"),
        )
        for name in _POSITIVE
        if name in callers
    } == {
        name: ("annotated_receiver", source, "GenerationStore", 0.8)
        for name, source in _POSITIVE.items()
    }


@pytest.mark.asyncio
async def test_negative_receivers_are_not_attributed(store_root: str) -> None:
    result = await _callers(store_root, "GenerationStore.publish")

    assert set(_by_name(result)) & set(_NEGATIVE) == set()
    # 联合类型、未注解与被重新绑定的接收者仍未解析，答复不是普查。
    assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_wrong_type_receiver_binds_to_its_own_class(store_root: str) -> None:
    result = await _callers(store_root, "Other.publish")

    callers = _by_name(result)
    assert set(callers) == {"wrong_type"}
    assert callers["wrong_type"]["resolution_kind"] == "annotated_receiver"
    assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_override_is_not_complete_on_base_typed_edges(store_root: str) -> None:
    # `store: GenerationStore` 在运行时可能是 FakeStore：覆写方不得据此答 complete。
    result = await _callers(store_root, "FakeStore.publish")

    assert result["caller_count"] == 0
    assert result["completeness"] != "complete"
    assert result["completeness_reasons"]


_REGISTRY = (
    "class IndexSnapshotRegistry:\n"
    "    def publish(self, entry):\n"
    "        return entry\n"
)
_DRAIN = (
    "from registry import IndexSnapshotRegistry\n\n\n"
    "def drain(registry: IndexSnapshotRegistry, entry):\n"
    "    registry.publish(entry)\n\n\n"
    "class Pump:\n"
    "    def __init__(self, registry: IndexSnapshotRegistry):\n"
    "        self.registry = registry\n\n"
    "    def run(self, entry):\n"
    "        self.registry.publish(entry)\n"
)


@pytest.mark.asyncio
async def test_fully_annotated_target_without_overrides_is_complete(
    tmp_path: Path,
) -> None:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "registry.py").write_text(_REGISTRY, encoding="utf-8")
    (tmp_path / "drain.py").write_text(_DRAIN, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True

    result = await _callers(str(tmp_path), "IndexSnapshotRegistry.publish")

    assert {(c["name"], c["line"]) for c in result["callers"]} == {
        ("drain", 4),
        ("run", 12),
    }
    assert (result["completeness"], result["completeness_reasons"]) == (
        "complete",
        [],
    )


def test_extractor_version_is_bumped_for_receiver_hints() -> None:
    from tree_sitter_analyzer import ast_cache
    from tree_sitter_analyzer.cache import indexer

    assert (
        ast_cache._AST_CACHE_EXTRACTOR_VERSION,
        indexer._AST_CACHE_EXTRACTOR_VERSION,
        # v40 引入接收者线索；v41（#1669）在其上停止按唯一方法名绑定。
        # v42（#1670）在其上记录改名导入的来源。
    ) == (47, 47)


@pytest.mark.asyncio
async def test_bare_name_query_carries_provenance(store_root: str) -> None:
    # SQL 路径（裸名）同样标注经注解绑定的调用方。
    result = await _callers(store_root, "publish")

    callers = _by_name(result)
    assert callers["by_param"]["resolution_kind"] == "annotated_receiver"
    assert "resolution_kind" not in callers["unannotated"]
    assert result["completeness"] != "complete"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("GenerationStore", "GenerationStore"),
        ("'GenerationStore'", "GenerationStore"),
        ("Optional[store.GenerationStore]", "store.GenerationStore"),
        ("typing.Optional['GenerationStore']", "GenerationStore"),
        ("GenerationStore | None", "GenerationStore"),
        ("None | GenerationStore", "GenerationStore"),
        ("Union[GenerationStore, None]", "GenerationStore"),
        ("GenerationStore | Other", None),
        ("Union[GenerationStore, Other]", None),
        ("list[GenerationStore]", None),
        ("type[GenerationStore]", None),
        ("Any", None),
        ("str", None),
        ("Self", "Self"),
    ],
)
def test_normalize_annotation(text: str, expected: str | None) -> None:
    from tree_sitter_analyzer.synapse_resolver._annotated import normalize_annotation

    assert normalize_annotation(text) == expected


def _function_hints(source: str) -> dict:
    import tree_sitter
    import tree_sitter_python

    from tree_sitter_analyzer.receiver_hints import function_receiver_hints

    parser = tree_sitter.Parser(tree_sitter.Language(tree_sitter_python.language()))
    tree = parser.parse(source.encode("utf-8"))
    func = next(c for c in tree.root_node.children if c.type == "function_definition")
    return function_receiver_hints(func)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def f(x: T):\n    x.m()\n", {"x": {"source": "param", "type": "T"}}),
        (
            "def f():\n    x: T = g()\n    x.m()\n",
            {"x": {"source": "local", "type": "T"}},
        ),
        (
            "def f():\n    x = None\n    x = make()\n    x.m()\n",
            {"x": {"source": "local", "returns_of": "make"}},
        ),
        (
            "def f():\n    x = await make()\n",
            {"x": {"source": "local", "returns_of": "make"}},
        ),
        ("def f(x: T, y: U):\n    global x\n", {"y": {"source": "param", "type": "U"}}),
        ("def f(x: T, xs):\n    return [x for x in xs]\n", {}),
        ("def f(x: T):\n    return lambda x: x.m()\n", {}),
        ("def f():\n    x = make()\n    x = other()\n", {}),
        ("def f():\n    x = make()\n    for x in y:\n        pass\n", {}),
        ("def f():\n    x, y = make()\n", {}),
        ("def f():\n    with make() as x:\n        pass\n", {}),
        ("def f(x):\n    x = make()\n", {}),
        ("def f():\n    x = Thing()\n", {}),
        ("def f(x: T, x2: U):\n    del x2\n", {"x": {"source": "param", "type": "T"}}),
    ],
)
def test_function_receiver_hints(source: str, expected: dict) -> None:
    assert _function_hints(source) == expected


_HOLDER = (
    "from registry import IndexSnapshotRegistry\n\n"
    "REGISTRY = IndexSnapshotRegistry()\n\n\n"
    "def local_use(entry):\n"
    "    REGISTRY.publish(entry)\n\n\n"
    "def shadowed_use(REGISTRY, entry):\n"
    "    REGISTRY.publish(entry)\n"
)
_CLIENT = (
    "import holder\n"
    "from holder import REGISTRY\n\n\n"
    "def via_alias(entry):\n"
    "    holder.REGISTRY.publish(entry)\n\n\n"
    "def via_import(entry):\n"
    "    REGISTRY.publish(entry)\n\n\n"
    "def via_local_import(entry):\n"
    "    import holder as owner\n\n"
    "    owner.REGISTRY.publish(entry)\n"
)


@pytest.mark.asyncio
async def test_module_level_singleton_receivers(tmp_path: Path) -> None:
    # `REGISTRY = IndexSnapshotRegistry()`：同模块、`alias.REGISTRY`、`from m import REGISTRY`。
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "registry.py").write_text(_REGISTRY, encoding="utf-8")
    (tmp_path / "holder.py").write_text(_HOLDER, encoding="utf-8")
    (tmp_path / "client.py").write_text(_CLIENT, encoding="utf-8")
    # 第二个 `publish`：未注解的接收者不能凭“项目里唯一的同名方法”绑定。
    (tmp_path / "other.py").write_text(
        "class Other:\n    def publish(self, entry):\n        return entry\n",
        encoding="utf-8",
    )
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True

    result = await _callers(str(tmp_path), "IndexSnapshotRegistry.publish")

    callers = _by_name(result)
    assert {name: callers[name]["type_source"] for name in callers} == {
        "local_use": "module",
        "via_alias": "module",
        "via_import": "module",
        "via_local_import": "module",
    }
    # 负对照：参数 `REGISTRY` 遮蔽模块变量，仍未解析，答复不是普查。
    assert result["completeness"] != "complete"


def _module(source: str):
    import tree_sitter
    import tree_sitter_python

    from tree_sitter_analyzer.receiver_module_hints import module_hints

    parser = tree_sitter.Parser(tree_sitter.Language(tree_sitter_python.language()))
    return module_hints(parser.parse(source.encode("utf-8")).root_node)


def test_module_hints_shapes_and_controls() -> None:
    from tree_sitter_analyzer.receiver_module_hints import module_call_hint

    module = _module(
        "import os\n"
        "import pkg.owner as owner\n"
        "from pkg import THING\n"
        "from json import decoder\n"
        "REG = Registry()\n"
        "TYPED: Store = make()\n"
        "MADE = build()\n"
        "MIXED = build()\n"
        "MIXED = other()\n"
        "LAZY = None\n"
        "LAZY = Registry()\n"
        "MOVED = Registry()\n"
        "def reset():\n"
        "    global MOVED\n"
        "    MOVED = None\n"
    )

    assert module.variables == {
        "REG": {"source": "module", "type": "Registry"},
        "TYPED": {"source": "module", "type": "Store"},
        "MADE": {"source": "module", "returns_of": "build"},
        "LAZY": {"source": "module", "type": "Registry"},
    }
    none: frozenset[str] = frozenset()
    assert module_call_hint("REG", module, none) == module.variables["REG"]
    assert module_call_hint("REG", module, frozenset({"REG"})) is None
    assert module_call_hint("THING", module, none) == {
        "source": "module",
        "imported": "THING",
    }
    assert module_call_hint("owner.REGISTRY", module, none) == {
        "source": "module",
        "module_attr": "owner.REGISTRY",
    }
    assert module_call_hint("os.path", module, none) is None
    assert module_call_hint("decoder", module, none) is None
    assert module_call_hint("MOVED", module, none) is None
