"""Tests for the Hyphae evaluator over a fake edges-backed ASTCache."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.hyphae.evaluator import Evaluator
from tree_sitter_analyzer.hyphae.parser import HyphaeSyntaxError, parse


class FakeCache:
    """ASTCache stand-in backed by in-memory symbols + edges fixtures."""

    def __init__(self, functions, classes, edges):
        self._functions = functions
        self._classes = classes
        self._edges = edges  # list of {kind, caller_name, callee_name, file_path}

    def get_functions(self):
        return list(self._functions)

    def get_symbols_by_kind(self, kind, limit=50000):
        if kind == "class":
            return list(self._classes)
        return []

    def search_symbols_cascade(self, query, limit=100):
        pool = self._functions + self._classes
        return [s for s in pool if s.get("name") == query]

    def query_edges(self, kind, caller_name=None, callee_name=None, limit=10000):
        out = []
        for e in self._edges:
            if e["kind"] != kind:
                continue
            if caller_name is not None and e.get("caller_name") != caller_name:
                continue
            if callee_name is not None and e.get("callee_name") != callee_name:
                continue
            out.append(e)
        return out


def _names(rows):
    return sorted(r["name"] for r in rows)


def _fixture():
    functions = [
        {
            "name": "save",
            "file": "svc/UserService.java",
            "line": 10,
            "language": "java",
            "class": "UserService",
        },
        {
            "name": "delete",
            "file": "svc/UserService.java",
            "line": 20,
            "language": "java",
            "class": "UserService",
        },
        {
            "name": "find",
            "file": "svc/UserRepo.java",
            "line": 55,
            "language": "java",
            "class": "UserRepo",
        },
        {
            "name": "helper",
            "file": "util/Helpers.java",
            "line": 100,
            "language": "java",
            "class": None,
        },
    ]
    classes = [
        {
            "name": "UserService",
            "file": "svc/UserService.java",
            "line": 5,
            "language": "java",
            "kind": "class",
        },
        {
            "name": "UserRepo",
            "file": "svc/UserRepo.java",
            "line": 50,
            "language": "java",
            "kind": "class",
        },
        {
            "name": "BaseService",
            "file": "svc/BaseService.java",
            "line": 1,
            "language": "java",
            "kind": "class",
        },
    ]
    edges = [
        {
            "kind": "calls",
            "caller_name": "save",
            "callee_name": "find",
            "file_path": "svc/UserService.java",
        },
        {
            "kind": "calls",
            "caller_name": "delete",
            "callee_name": "helper",
            "file_path": "svc/UserService.java",
        },
        {
            "kind": "contains",
            "caller_name": "UserService",
            "callee_name": "save",
            "file_path": "svc/UserService.java",
        },
        {
            "kind": "contains",
            "caller_name": "UserService",
            "callee_name": "delete",
            "file_path": "svc/UserService.java",
        },
        {
            "kind": "contains",
            "caller_name": "UserRepo",
            "callee_name": "find",
            "file_path": "svc/UserRepo.java",
        },
        {
            "kind": "extends",
            "caller_name": "UserService",
            "callee_name": "BaseService",
            "file_path": "svc/UserService.java",
        },
        {
            "kind": "imports",
            "caller_name": "",
            "callee_name": "com.acme.Repo",
            "file_path": "svc/UserService.java",
        },
    ]
    return Evaluator(FakeCache(functions, classes, edges))


# -- base ----------------------------------------------------------------------
def test_name_lookup():
    assert _names(_fixture().eval(parse("#save"))) == ["save"]


def test_kind_method_requires_class_field():
    got = _names(_fixture().eval(parse(".method")))
    assert "helper" not in got and "save" in got and "find" in got


def test_kind_class_enumerates_class_symbols():
    got = _names(_fixture().eval(parse(".class")))
    assert got == ["BaseService", "UserRepo", "UserService"]


def test_kind_interface_aliases_class():
    # .interface maps to class enumeration in the MVP.
    assert "UserService" in _names(_fixture().eval(parse(".interface")))


# -- edge pseudo-classes -------------------------------------------------------
def test_calls_edge_driven():
    got = _names(_fixture().eval(parse(".method:calls(#find)")))
    assert got == ["save"]


def test_callees_edge_driven():
    # methods that find is called-from? callees(#save) = what save calls = find
    got = _names(_fixture().eval(parse("*:callees(#save)")))
    assert "find" in got


def test_extends_edge():
    got = _names(_fixture().eval(parse(".class:extends(#BaseService)")))
    assert got == ["UserService"]


def test_implements_aliases_extends():
    got = _names(_fixture().eval(parse(".class:implements(#BaseService)")))
    assert got == ["UserService"]


# -- structural pseudo-classes -------------------------------------------------
def test_has_via_contains_edge():
    got = _names(_fixture().eval(parse(".class:has(#save)")))
    assert got == ["UserService"]


def test_first_child_per_class():
    got = _names(_fixture().eval(parse(".method:first-child")))
    # save (first in UserService), find (only/first in UserRepo)
    assert got == ["find", "save"]


def test_nth_child_second():
    got = _names(_fixture().eval(parse(".method:nth-child(2)")))
    assert got == ["delete"]


def test_only_child():
    got = _names(_fixture().eval(parse(".method:only-child")))
    assert got == ["find"]  # UserRepo has a single method


def test_imports_file_level():
    got = _names(_fixture().eval(parse(".method:imports(com.acme.Repo)")))
    # methods in svc/UserService.java (which imports com.acme.Repo)
    assert "save" in got and "delete" in got
    assert "find" not in got


# -- filters -------------------------------------------------------------------
def test_not_excludes():
    got = _names(_fixture().eval(parse(".method:calls(#find):not(#save)")))
    assert got == []


def test_in_path_filter():
    got = _names(_fixture().eval(parse(".method:in(svc/)")))
    assert "helper" not in got and "save" in got


def test_attribute_file_filter():
    got = _names(_fixture().eval(parse(".method[file=UserService]")))
    assert got == ["delete", "save"]


# -- combinators ---------------------------------------------------------------
def test_child_combinator():
    got = _names(_fixture().eval(parse("#UserService > .method")))
    assert got == ["delete", "save"]


def test_selector_list_union():
    assert _names(_fixture().eval(parse("#save, #find"))) == ["find", "save"]


# -- error handling ------------------------------------------------------------
def test_unknown_pseudo_raises():
    with pytest.raises(HyphaeSyntaxError):
        _fixture().eval(parse(".method:bogus(#x)"))


def test_nth_child_requires_number():
    with pytest.raises(HyphaeSyntaxError):
        _fixture().eval(parse(".method:nth-child(#x)"))
