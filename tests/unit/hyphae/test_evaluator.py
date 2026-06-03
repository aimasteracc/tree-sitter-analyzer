"""Tests for the Hyphae evaluator over a fake ASTCache."""

from __future__ import annotations

from tree_sitter_analyzer.hyphae.evaluator import Evaluator
from tree_sitter_analyzer.hyphae.parser import parse


class FakeCache:
    """Minimal ASTCache stand-in driven by in-memory fixtures."""

    def __init__(self, functions, callers=None, callees=None):
        self._functions = functions
        self._callers = callers or {}
        self._callees = callees or {}

    def get_functions(self):
        return list(self._functions)

    def search_symbols_cascade(self, query, limit=100):
        return [f for f in self._functions if f.get("name") == query]

    def query_callers(self, name, file=None):
        return self._callers.get(name, [])

    def query_callees(self, name, file=None):
        return self._callees.get(name, [])


def _names(rows):
    return sorted(r["name"] for r in rows)


def _fixture():
    funcs = [
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
            "name": "helper",
            "file": "util/Helpers.java",
            "line": 5,
            "language": "java",
            "class": None,
        },
        {
            "name": "find",
            "file": "svc/UserRepo.java",
            "line": 8,
            "language": "java",
            "class": "UserRepo",
        },
    ]
    # save() and find() call UserRepo; delete() does not.
    callers = {
        "UserRepo": [
            {
                "caller_name": "save",
                "caller_file": "svc/UserService.java",
                "caller_line": 10,
            },
            {
                "caller_name": "find",
                "caller_file": "svc/UserRepo.java",
                "caller_line": 8,
            },
        ],
    }
    callees = {
        "save": [
            {
                "callee_name": "UserRepo",
                "callee_file": "svc/UserRepo.java",
                "callee_line": 1,
            },
        ],
    }
    return Evaluator(FakeCache(funcs, callers, callees))


def test_name_lookup():
    ev = _fixture()
    assert _names(ev.eval(parse("#save"))) == ["save"]


def test_kind_method_requires_class_field():
    ev = _fixture()
    # .method = functions with a class; helper (class=None) excluded.
    got = _names(ev.eval(parse(".method")))
    assert "helper" not in got
    assert "save" in got and "find" in got


def test_calls_reverse_driven():
    ev = _fixture()
    # .method:calls(#UserRepo) → methods that call UserRepo = save, find.
    got = _names(ev.eval(parse(".method:calls(#UserRepo)")))
    assert got == ["find", "save"]
    assert "delete" not in got


def test_attribute_file_filter():
    ev = _fixture()
    got = _names(ev.eval(parse(".method[file=UserService]")))
    assert got == ["delete", "save"]


def test_not_pseudo_excludes():
    ev = _fixture()
    # .method:calls(#UserRepo):not(#find) → save only.
    got = _names(ev.eval(parse(".method:calls(#UserRepo):not(#find)")))
    assert got == ["save"]


def test_in_path_filter():
    ev = _fixture()
    got = _names(ev.eval(parse(".method:in(svc/)")))
    assert "helper" not in got
    assert "save" in got


def test_child_combinator_via_class_field():
    ev = _fixture()
    # #UserService > .method → methods whose class is UserService.
    # (#UserService resolves via search; add it as a symbol.)
    ev._cache._functions.append(
        {
            "name": "UserService",
            "file": "svc/UserService.java",
            "line": 1,
            "class": None,
        }
    )
    got = _names(ev.eval(parse("#UserService > .method")))
    assert got == ["delete", "save"]


def test_selector_list_union():
    ev = _fixture()
    got = _names(ev.eval(parse("#save, #delete")))
    assert got == ["delete", "save"]
