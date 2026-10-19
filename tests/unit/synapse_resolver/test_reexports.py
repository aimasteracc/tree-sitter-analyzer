"""再导出追踪（``_reexports``）的单元规则：只在目标文件没有定义时才沿导入继续找。"""

from __future__ import annotations

from tree_sitter_analyzer.synapse_resolver import resolve_callee
from tree_sitter_analyzer.synapse_resolver._context import ResolverContext
from tree_sitter_analyzer.synapse_resolver._imports import ImportEntry
from tree_sitter_analyzer.synapse_resolver._reexports import (
    MAX_HOPS,
    follow_reexports,
    imported_entry,
    resolve_reexported_name,
)


def _entry(file_path: str, local: str, alias_of: str = "", star: bool = False):
    return ImportEntry(
        file_path=file_path,
        language="python",
        module_path=".x",
        local_name=local,
        is_relative=True,
        is_star=star,
        alias_of=alias_of,
        line=1,
    )


def _ctx(**kw) -> ResolverContext:
    defaults = {
        "project_root": "/repo",
        "cache": None,
        "file_languages": {"user.py": "python"},
        "file_symbols": {"impl.py": [("helper", "function", 7)]},
        "name_to_source": {
            "user.py": {"helper": "facade.py", "direct": "impl.py"},
            "facade.py": {"helper": "impl.py"},
        },
        "imports_by_file": {
            "user.py": [_entry("user.py", "helper")],
            "facade.py": [_entry("facade.py", "helper")],
        },
    }
    defaults.update(kw)
    return ResolverContext(**defaults)


def test_reexport_resolves_to_the_definition() -> None:
    assert resolve_reexported_name("helper", "user.py", _ctx()) == (7, "impl.py")
    # 无解析器的级联同样落到定义文件。
    resolved = resolve_callee("helper", "user.py", _ctx())
    assert (resolved.resolution, resolved.resolved_file, resolved.callee_symbol_id) == (
        "project",
        "impl.py",
        7,
    )


def test_reexport_leaves_direct_and_renamed_imports_alone() -> None:
    ctx = _ctx(
        file_symbols={"impl.py": [("helper", "function", 7)], "facade.py": []},
        name_to_source={"user.py": {"helper": "impl.py", "g": "facade.py"}},
        imports_by_file={"user.py": [_entry("user.py", "g", alias_of="helper")]},
    )
    # 目标文件自己定义了它：不是再导出。
    assert resolve_reexported_name("helper", "user.py", ctx) is None
    # 改名导入交给别名规则。
    assert resolve_reexported_name("g", "user.py", ctx) is None
    assert resolve_reexported_name("missing", "user.py", ctx) is None
    # 再导出链断开（再导出文件里既没有定义也没有导入）：交回原有级联。
    dangling = _ctx(name_to_source={"user.py": {"helper": "facade.py"}})
    assert resolve_reexported_name("helper", "user.py", dangling) is None


def test_follow_reexports_stops_on_broken_or_cyclic_chains() -> None:
    renamed = _ctx(
        file_symbols={"impl.py": [("real", "function", 3)]},
        name_to_source={"facade.py": {"public": "impl.py"}},
        imports_by_file={"facade.py": [_entry("facade.py", "public", alias_of="real")]},
    )
    assert follow_reexports(renamed, "facade.py", "public") == (3, "impl.py", "real")
    broken = _ctx(name_to_source={})
    assert follow_reexports(broken, "facade.py", "helper") is None
    cyclic = _ctx(
        file_symbols={},
        name_to_source={"a.py": {"f": "b.py"}, "b.py": {"f": "a.py"}},
        imports_by_file={},
    )
    assert follow_reexports(cyclic, "a.py", "f") is None
    selfref = _ctx(file_symbols={}, name_to_source={"a.py": {"f": "a.py"}})
    assert follow_reexports(selfref, "a.py", "f") is None
    assert MAX_HOPS == 4


def test_imported_entry_skips_star_imports() -> None:
    ctx = _ctx(
        imports_by_file={"user.py": [_entry("user.py", "helper", star=True)]},
    )
    assert imported_entry(ctx, "user.py", "helper") is None
    assert imported_entry(ctx, "user.py", "other") is None


def test_qualified_or_bound_imports_keep_the_file_level_resolution() -> None:
    from tree_sitter_analyzer.synapse_resolver import _reexported_or

    ctx = _ctx()
    qualified = _reexported_or("helper", "mod", "user.py", ctx, None, "facade.py")
    bound = _reexported_or("helper", "", "user.py", ctx, 5, "facade.py")

    assert (qualified.resolved_file, qualified.callee_symbol_id) == ("facade.py", None)
    assert (bound.resolved_file, bound.callee_symbol_id) == ("facade.py", 5)
