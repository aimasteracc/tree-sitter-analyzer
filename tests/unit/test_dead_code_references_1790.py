"""#1790：作为值使用的函数被误报为死代码。

存进分发表、作为实参传入、被装饰器登记、或由运行时隐式调用的函数都是活的；
模块路径无法解析的文件（``agent-tasks/``）里的结论为低置信度。
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.call_graph import CallGraph, FunctionRef
from tree_sitter_analyzer.dead_code_analyzer import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    LOW_CONFIDENCE_UNRESOLVED_MODULE,
    filter_value_referenced,
    find_transitive_dead_code,
)
from tree_sitter_analyzer.dead_code_references import (
    build_reference_index,
    module_path_unresolvable,
)

_SCENARIOS = """
    def _is_decidable(result):
        return bool(result)

    def _unused_helper():
        return 1

    def cold_start_tsa(repo):
        return {"ok": _is_decidable(repo)}

    def cold_start_baseline(repo):
        return {"ok": _is_decidable(repo)}

    SCENARIOS = {
        "cold-start": {"tsa": cold_start_tsa, "baseline": cold_start_baseline},
    }
"""

_RUNNER = """
    from scenarios import SCENARIOS

    def main():
        return SCENARIOS["cold-start"]["tsa"]("repo")

    if __name__ == "__main__":
        main()
"""


def _write(root: Path, rel: str, source: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source), encoding="utf-8")


def _dead(root: Path) -> dict[str, object]:
    return {
        item.function.name: item
        for item in find_transitive_dead_code(CallGraph(str(root)))
    }


@pytest.mark.parametrize("folder", ["agent-tasks", "agent_tasks"])
def test_dispatch_table_and_direct_call_alive_in_any_directory(
    tmp_path: Path, folder: str
) -> None:
    _write(tmp_path, f"benchmarks/{folder}/scenarios.py", _SCENARIOS)
    _write(tmp_path, f"benchmarks/{folder}/bench_runner.py", _RUNNER)

    dead = _dead(tmp_path)

    assert set(dead) == {"_unused_helper"}


def test_hyphenated_directory_findings_are_low_confidence(tmp_path: Path) -> None:
    _write(tmp_path, "benchmarks/agent-tasks/scenarios.py", _SCENARIOS)
    _write(tmp_path, "pkg/mod.py", "def orphan():\n    return 1\n")

    dead = _dead(tmp_path)

    hyphenated = dead["_unused_helper"]
    assert hyphenated.confidence == CONFIDENCE_LOW
    assert hyphenated.confidence_reason == LOW_CONFIDENCE_UNRESOLVED_MODULE
    assert dead["orphan"].confidence == CONFIDENCE_HIGH
    assert dead["orphan"].confidence_reason is None
    # 高置信度排在前面，展示上限不会把它们挤掉。
    ordered = find_transitive_dead_code(CallGraph(str(tmp_path)))
    assert ordered[0].confidence == CONFIDENCE_HIGH


@pytest.mark.parametrize(
    "container",
    [
        "TABLE = [handler_a, handler_b]",
        "TABLE = (handler_a, handler_b)",
        "TABLE = {handler_a, handler_b}",
        "TABLE = {'a': handler_a, 'b': handler_b}",
    ],
)
def test_functions_in_container_literals_are_alive(
    tmp_path: Path, container: str
) -> None:
    _write(
        tmp_path,
        "pkg/registry.py",
        f"""
        def handler_a():
            return 1

        def handler_b():
            return 2

        def really_unused():
            return 3

        {container}
        """,
    )

    assert set(_dead(tmp_path)) == {"really_unused"}


def test_function_passed_as_argument_is_alive(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "pkg/service.py",
        """
        import json
        import threading

        def _reject_constant(value):
            raise ValueError(value)

        def main():
            def worker():
                return 1

            thread = threading.Thread(target=worker)
            thread.start()
            return json.loads("{}", parse_constant=_reject_constant)
        """,
    )

    assert _dead(tmp_path) == {}


def test_reference_from_dead_function_does_not_revive_target(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "pkg/service.py",
        """
        def _callback():
            return 1

        def dead_registrar(register):
            return register(_callback)
        """,
    )

    assert set(_dead(tmp_path)) == {"_callback", "dead_registrar"}


def test_cross_file_attribute_and_alias_references_are_alive(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "pkg/client.py",
        """
        def exchange(request):
            return request

        class Box:
            @property
            def size(self):
                return 1
        """,
    )
    _write(
        tmp_path,
        "pkg/auditor.py",
        """
        from pkg.client import exchange as _authority

        def main(box):
            return _authority(box.size)
        """,
    )

    assert _dead(tmp_path) == {}


def test_implicit_entries_decorators_and_module_scope_calls_are_alive(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "pkg/runtime.py",
        """
        import ast

        app = object()

        class Runner:
            def __init__(self):
                self._ready = _prepare()

            def __call__(self):
                return 1

        class Visitor(ast.NodeVisitor):
            def visit_Call(self, node):
                return node

        @app.route("/x")
        def route_handler():
            return 1

        @staticmethod
        def only_static():
            return 1

        def _prepare():
            return True

        def _configure():
            return True

        CONFIG = _configure()
        """,
    )

    assert set(_dead(tmp_path)) == {"only_static"}


def test_genuinely_unused_function_is_still_reported(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "pkg/mod.py",
        """
        def main():
            return used()

        def used():
            return 1

        def unused_root():
            return unused_leaf()

        def unused_leaf():
            return 2
        """,
    )

    dead = _dead(tmp_path)

    assert set(dead) == {"unused_root", "unused_leaf"}
    assert dead["unused_root"].reason == "no_callers_has_dead_callees"
    assert dead["unused_leaf"].reason == "unreachable_from_entry"
    assert {item.confidence for item in dead.values()} == {CONFIDENCE_HIGH}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("benchmarks/agent-tasks/scenarios.py", True),
        ("benchmarks\\agent-tasks\\scenarios.py", True),
        ("pkg/my-module.py", True),
        ("pkg/2fast.py", True),
        ("benchmarks/agent_tasks/scenarios.py", False),
        ("pkg/__init__.py", False),
        ("web/agent-tasks/app.ts", False),
    ],
)
def test_module_path_unresolvable(path: str, expected: bool) -> None:
    assert module_path_unresolvable(path) is expected


def test_reference_scan_ignores_calls_definitions_and_assignment_targets(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "pkg/mod.py",
        """
        def target():
            return 1

        def caller():
            target = 2
            return target()
        """,
    )
    funcs = CallGraph(str(tmp_path)).function_refs()
    target = next(f for f in funcs if f.name == "target")

    index = build_reference_index(tmp_path, funcs, [target])

    assert index.referenced() == frozenset()


def test_filter_value_referenced_drops_used_orphans(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "pkg/mod.py",
        """
        def in_table():
            return 1

        def orphan():
            return 2

        class Thing:
            def __init__(self):
                pass

        TABLE = [in_table]
        """,
    )
    graph = CallGraph(str(tmp_path))
    orphans = [
        f
        for f in graph.function_refs()
        if not graph.caller_refs_of(f) and not graph.callee_refs_of(f)
    ]

    kept = filter_value_referenced(graph, orphans)

    assert [f.name for f in kept] == ["orphan"]


def test_mock_graph_without_project_root_skips_reference_scan() -> None:
    from unittest.mock import MagicMock

    orphan = FunctionRef("m.py", "orphan", 1, "python")
    graph = MagicMock()
    graph.function_refs.return_value = [orphan]
    graph.reachable_callee_refs_of.return_value = []
    graph.callee_refs_of.return_value = []
    graph.caller_refs_of.return_value = []

    dead = find_transitive_dead_code(graph)

    assert [item.function.name for item in dead] == ["orphan"]


def test_mcp_tool_reports_confidence(tmp_path: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.dead_code_tool import CodeGraphDeadCodeTool

    _write(tmp_path, "benchmarks/agent-tasks/scenarios.py", _SCENARIOS)
    _write(tmp_path, "pkg/mod.py", "def orphan():\n    return 1\n")

    result = asyncio.run(
        CodeGraphDeadCodeTool(str(tmp_path)).execute({"mode": "dead_functions"})
    )

    by_name = {item["name"]: item for item in result["dead_functions"]}
    assert set(by_name) == {"orphan", "_unused_helper"}
    assert by_name["orphan"]["confidence"] == "high"
    assert by_name["_unused_helper"]["confidence"] == "low"
    assert by_name["_unused_helper"]["confidence_reason"] == (
        "module_path_unresolvable"
    )
    assert result["stats"]["dead_functions_high_confidence"] == 1
    assert result["stats"]["dead_functions_low_confidence"] == 1
    assert "confidence=low" in result["next_step"]


def _load_priority_module() -> object:
    path = (
        Path(__file__).resolve().parents[2] / "scripts" / "_dogfood_sprint_priority.py"
    )
    spec = importlib.util.spec_from_file_location("_dogfood_priority_1790", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dogfood_priority_ignores_low_confidence_findings() -> None:
    priority = _load_priority_module()
    low_only = {
        "data": {
            "dead_functions": [{"name": "_unused_helper", "confidence": "low"}],
            "stats": {"dead_functions_high_confidence": 0},
        }
    }
    mixed = {
        "data": {
            "dead_functions": [
                {"name": "orphan", "confidence": "high"},
                {"name": "_unused_helper", "confidence": "low"},
            ],
            "stats": {"dead_functions_high_confidence": 7},
        }
    }

    assert priority._dead_code_items(low_only) == []  # type: ignore[attr-defined]
    items = priority._dead_code_items(mixed)  # type: ignore[attr-defined]
    assert items[0]["title"] == "7 potentially dead function(s) detected"
    assert items[0]["details"] == "orphan"


def test_js_constructor_is_implicit_and_other_languages_are_not() -> None:
    from tree_sitter_analyzer.dead_code_analyzer import _is_implicit_entry

    assert _is_implicit_entry(FunctionRef("a.ts", "constructor", 1, "typescript"))
    assert not _is_implicit_entry(FunctionRef("a.ts", "helper", 1, "typescript"))
    assert not _is_implicit_entry(FunctionRef("a.go", "__init__", 1, "go"))


def test_graph_without_callees_map_or_missing_root_still_reports() -> None:
    from unittest.mock import MagicMock

    orphan = FunctionRef("m.py", "orphan", 1, "python")
    graph = MagicMock()
    graph.project_root = "Z:/definitely/not/a/dir/1790"
    graph.callees_map.side_effect = RuntimeError("no map")
    graph.function_refs.return_value = [orphan]
    graph.reachable_callee_refs_of.return_value = []
    graph.callee_refs_of.return_value = []
    graph.caller_refs_of.return_value = []

    dead = find_transitive_dead_code(graph)

    assert [item.function.name for item in dead] == ["orphan"]


def test_reference_index_edges_decorators_and_unparsable_sources(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "pkg/mod.py",
        """
        HANDLERS = {}

        @HANDLERS[0]
        def subscript_decorated():
            return 1

        def holder():
            return [stored]

        def stored():
            return 2
        """,
    )
    _write(tmp_path, "pkg/broken.py", "def broken(:\n    return stored\n")
    _write(tmp_path, "pkg/.hidden.py", "VALUE = stored\n")
    funcs = CallGraph(str(tmp_path)).function_refs()
    candidates = [f for f in funcs if f.name in ("subscript_decorated", "stored")]

    index = build_reference_index(tmp_path, funcs, candidates)

    by_name = {f.name: f for f in funcs}
    assert index.registered == frozenset({by_name["subscript_decorated"]})
    assert by_name["stored"] in index.edges[by_name["holder"]]
    assert by_name["stored"] in index.referenced()
    assert build_reference_index(tmp_path, funcs, []).referenced() == frozenset()


def test_module_path_unresolvable_empty_path() -> None:
    assert module_path_unresolvable("./.py") is True
    assert module_path_unresolvable("") is False
