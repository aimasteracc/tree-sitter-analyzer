"""#1772：非测试调用方的未证明接收者 ``x.m()``，测试文件里的同名方法同样是可能目标。

全局档为非测试调用方剔除测试里的同名定义，只用于挑选确定目标；可能集合保留它们。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from tree_sitter_analyzer.cached_edge_resolution import CachedEdgeResolver
from tree_sitter_analyzer.call_graph import FunctionRef

_STUB = FunctionRef("pkg/__init__.py", "new_validator", 5, "python", "PluginProtocol")
_IMPL = FunctionRef("tests/test_plugins.py", "new_validator", 5, "python", "Plugin1")
_HELPER_SRC = FunctionRef("pkg/helpers.py", "helper", 1, "python")
_HELPER_TEST = FunctionRef("tests/test_helpers.py", "helper", 1, "python")


def _resolver() -> CachedEdgeResolver:
    by_name: dict[str, list[FunctionRef]] = defaultdict(list)
    by_file: dict[str, list[FunctionRef]] = defaultdict(list)
    for ref in (_STUB, _IMPL, _HELPER_SRC, _HELPER_TEST):
        by_name[ref.name].append(ref)
        by_file[ref.file_path].append(ref)
    return CachedEdgeResolver(
        functions_by_name=dict(by_name),
        functions_by_file=dict(by_file),
        file_import_map={},
    )


def _edge(full: str) -> dict[str, Any]:
    return {
        "caller_name": "build",
        "caller_file": "pkg/use.py",
        "caller_line": 1,
        "callee_name": full.rsplit(".", 1)[-1],
        "callee_full": full,
        "callee_line": 9,
        "file_path": "pkg/use.py",
        "language": "python",
        "callee_resolution": "unknown",
        "callee_resolved_file": "",
        "receiver_binding": None,
    }


def test_an_unproven_receiver_keeps_the_test_implementation_possible() -> None:
    targets = _resolver().resolve(_edge("plugin.new_validator"), "pkg/use.py")

    assert targets.certain == []
    assert set(targets.possible) == {_STUB, _IMPL}


def test_a_class_receiver_still_binds_to_the_source_definition() -> None:
    targets = _resolver().resolve(_edge("PluginProtocol.new_validator"), "pkg/use.py")

    assert targets.certain == [_STUB]
    assert _IMPL not in targets.possible


def test_a_bare_call_from_source_still_skips_the_test_shadow() -> None:
    targets = _resolver().resolve(_edge("helper"), "pkg/use.py")

    assert targets.certain == [_HELPER_SRC]
    assert _HELPER_TEST not in targets.possible
