"""#1657：构图内的解析记忆不得改变任何一条边的解析结果。

``_static_targets`` 按边的解析字段与调用方文件记忆，全局兜底按（裸名、调用方语言、
调用方是否测试文件）记忆。每种输入维度都有一对只在该维度上不同、解析结果也不同
的边：键漏掉任一维度，后解析的那条就会拿到先解析那条的结果。
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

import pytest

from tree_sitter_analyzer.cached_edge_resolution import CachedEdgeResolver
from tree_sitter_analyzer.call_graph import FunctionRef
from tree_sitter_analyzer.callee_resolution import CalleeResolver

_FUNCS = [
    FunctionRef("lib/only.py", "only", 1, "python"),
    FunctionRef("tests/test_only.py", "only", 1, "python"),
    FunctionRef("web/app.js", "only", 1, "javascript"),
    FunctionRef("a.py", "helper", 1, "python"),
    FunctionRef("c.py", "helper", 1, "python"),
    FunctionRef("a.py", "use", 5, "python"),
    FunctionRef("c.py", "use", 5, "python"),
    FunctionRef("base.py", "run", 1, "python", receiver="Base"),
    FunctionRef("base.py", "hook", 5, "python", receiver="Base"),
    FunctionRef("base.py", "hook", 10, "python", receiver="Sub"),
    FunctionRef("lib/only.py", "get", 10, "python", receiver="Store"),
    FunctionRef("lib/other.py", "get", 10, "python", receiver="Cache"),
    FunctionRef("prod/user.py", "main", 1, "python"),
    FunctionRef("web/use.js", "main", 1, "javascript"),
]


def _indexes() -> tuple[dict[str, list[FunctionRef]], dict[str, list[FunctionRef]]]:
    by_name: dict[str, list[FunctionRef]] = defaultdict(list)
    by_file: dict[str, list[FunctionRef]] = defaultdict(list)
    for ref in _FUNCS:
        by_name[ref.name].append(ref)
        by_file[ref.file_path].append(ref)
    return by_name, by_file


def _edge(
    caller_file: str,
    callee: str,
    *,
    full: str = "",
    resolution: str = "unknown",
    resolved: str = "",
    line: int = 3,
) -> dict[str, Any]:
    """与 ``get_call_edges`` 同形的一行。"""
    return {
        "caller_name": "main",
        "caller_file": caller_file,
        "caller_line": 1,
        "callee_name": callee,
        "callee_full": full or callee,
        "callee_line": line,
        "file_path": caller_file,
        "language": "javascript" if caller_file.endswith(".js") else "python",
        "callee_resolution": resolution,
        "callee_resolved_file": resolved,
    }


#: (边, 调用方外围类)。成对的边只在一个输入维度上不同，而解析结果不同。
_EDGES: list[tuple[dict[str, Any], str | None]] = [
    # 全局兜底：调用方是否测试文件（测试替身只在测试调用方可见）。
    (_edge("prod/user.py", "only"), None),
    (_edge("tests/test_user.py", "only"), None),
    # 全局兜底：调用方语言。
    (_edge("web/use.js", "only"), None),
    (_edge("prod/user.py", "only", line=9), None),
    # 本地档：只差调用方文件。
    (_edge("a.py", "helper"), None),
    (_edge("c.py", "helper"), None),
    # 持久化解析：只差解析到的文件。
    (
        _edge(
            "prod/user.py",
            "get",
            full="s.get",
            resolution="project",
            resolved="lib/only.py",
        ),
        None,
    ),
    (
        _edge(
            "prod/user.py",
            "get",
            full="s.get",
            resolution="project",
            resolved="lib/other.py",
        ),
        None,
    ),
    # 只差解析种类。
    (_edge("prod/user.py", "get", full="s.get", resolution="builtin"), None),
    (_edge("prod/user.py", "get", full="s.get"), None),
    # 自身分派：静态部分相同，调用方外围类不同。
    (_edge("base.py", "hook", full="self.hook"), "Base"),
    (_edge("base.py", "hook", full="self.hook"), "Sub"),
    (_edge("base.py", "hook", full="self.hook"), None),
    # 只差限定名（接收者把全局候选收窄到不同的类）。
    (_edge("prod/user.py", "get", full="Store.get"), None),
    (_edge("prod/user.py", "get", full="Cache.get"), None),
]


class _Subclasses:
    def subclasses(self, class_name: str) -> set[str]:
        return {"Sub"} if class_name == "Base" else set()


def _resolver(*, memoize: bool) -> CachedEdgeResolver:
    by_name, by_file = _indexes()
    return CachedEdgeResolver(
        functions_by_name=by_name,
        functions_by_file=by_file,
        file_import_map={},
        subclasses=_Subclasses(),  # type: ignore[arg-type]
        memoize=memoize,
    )


def _answers(resolver: CachedEdgeResolver, order: list[int]) -> dict[int, Any]:
    answers = {}
    for index in order:
        edge, caller_class = _EDGES[index]
        targets = resolver.resolve(edge, edge["caller_file"], caller_class)
        answers[index] = (
            [ref.to_dict() for ref in targets.certain],
            [ref.to_dict() for ref in targets.possible],
        )
    return answers


def _orders() -> list[list[int]]:
    forward = list(range(len(_EDGES)))
    rng = random.Random(1657)
    shuffled = [rng.sample(forward, len(forward)) for _ in range(6)]
    return [forward, forward[::-1], *shuffled]


def test_fixture_pairs_really_resolve_differently() -> None:
    # 前提：成对的边在无记忆时确实得到不同答案，否则下面的比较什么也证明不了。
    plain = _answers(_resolver(memoize=False), list(range(len(_EDGES))))
    for left, right in ((0, 1), (0, 2), (4, 5), (6, 7), (8, 9), (10, 11), (13, 14)):
        assert plain[left] != plain[right], (left, right)


@pytest.mark.parametrize("order", _orders())
def test_memoized_resolution_equals_plain_resolution(order: list[int]) -> None:
    plain = _answers(_resolver(memoize=False), order)
    memoized = _answers(_resolver(memoize=True), order)
    assert memoized == plain


def test_memo_is_used_for_repeated_inputs() -> None:
    resolver = _resolver(memoize=True)
    _answers(resolver, list(range(len(_EDGES))) * 2)
    assert resolver._static_memo is not None
    assert 0 < len(resolver._static_memo) < len(_EDGES)
    assert resolver.callee_resolver._global_memo


def test_global_memo_is_opt_in() -> None:
    by_name, by_file = _indexes()
    plain = CalleeResolver(
        functions_by_name=by_name, functions_by_file=by_file, name_to_source={}
    )
    plain.resolve_items("only", "prod/user.py")
    assert plain._global_memo is None
