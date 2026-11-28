"""#1896: a Python method a subclass inherits as another base's method.

.. code-block:: python

    # pkg/a.py
    class A:
        def m(self): ...

    # pkg/i.py
    class I:
        def m(self): raise NotImplementedError
        def run(self): return self.m()

    # pkg/b.py
    class B(A, I): ...          # MRO: B, A, I

``B().run()`` runs ``A.m``, but the call edge of ``self.m()`` in ``I.run`` is
bound to ``I.m``, so ``A.m`` answered ``complete`` with 0 callers. The
``supertype_dispatch`` check now walks the project subclasses of the declaring
class (:mod:`.callers_py_subtypes`).
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools import (
    callers_py_class_index,
    callers_py_subtypes,
    callers_py_supertypes,
)
from tree_sitter_analyzer.mcp.tools.callers_java_overrides import OVERRIDE_REASON
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_A = "class A:\n    def m(self):\n        return 1\n"
_I = (
    "class I:\n"
    "    def m(self):\n"
    "        raise NotImplementedError\n"
    "\n"
    "    def run(self):\n"
    "        return self.m()\n"
)
_B = "from pkg.a import A\nfrom pkg.i import I\n\n\nclass B(A, I):\n    pass\n"
_MAIN = "def main():\n    return helper()\n\n\ndef helper():\n    return 1\n"
#: The issue's repro.
_REPRO = {
    "pkg/__init__.py": "",
    "pkg/a.py": _A,
    "pkg/i.py": _I,
    "pkg/b.py": _B,
    "main.py": _MAIN,
}


async def _index(root, files: dict[str, str]) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    _write(root, files)
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 40}
    )
    assert indexed["published"] is True
    return str(root)


def _write(root, files: dict[str, str]) -> str:
    callers_py_supertypes.clear_parsed()
    callers_py_class_index.clear_indexes()
    for rel_path, text in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return str(root)


async def _callers(root: str, name: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "include_bodies": False}
    )


async def _answer(tmp_path, files: dict[str, str], name: str = "A.m") -> dict:
    return await _callers(await _index(tmp_path, files), name)


def _blocked(result: dict) -> None:
    assert result["caller_count"] == 0
    assert result["completeness"] == "unknown", result
    assert result["completeness_reasons"] == [OVERRIDE_REASON], result


# --- the issue ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_repro_inherited_implementation_is_not_complete(tmp_path) -> None:
    result = await _answer(tmp_path, _REPRO)

    _blocked(result)
    assert "`B`" in result["next_step"]
    assert "`I.m`" in result["next_step"]
    assert "pkg/i.py:6" in result["next_step"]


@pytest.mark.asyncio
async def test_listed_callers_are_not_complete_either(tmp_path) -> None:
    files = {
        **_REPRO,
        "main.py": "from pkg.a import A\n\n\ndef main():\n    return A().m()\n",
    }

    result = await _answer(tmp_path, files)

    assert result["caller_count"] == 1
    assert result["completeness"] == "incomplete", result
    assert result["completeness_reasons"] == [OVERRIDE_REASON]


@pytest.mark.asyncio
async def test_call_in_a_base_inheriting_the_name_is_found(tmp_path) -> None:
    files = {
        **_REPRO,
        "pkg/i.py": (
            "class I:\n    def m(self):\n        raise NotImplementedError\n\n\n"
            "class I2(I):\n    def run(self):\n        return self.m()\n"
        ),
        "pkg/b.py": _B.replace("import I", "import I2").replace(", I)", ", I2)"),
    }

    result = await _answer(tmp_path, files)

    _blocked(result)
    assert "pkg/i.py:8" in result["next_step"]


@pytest.mark.asyncio
async def test_typed_receiver_of_the_other_base_is_found(tmp_path) -> None:
    files = {
        **_REPRO,
        "pkg/i.py": "class I:\n    def m(self):\n        raise NotImplementedError\n",
        "use.py": "from pkg.i import I\n\n\ndef use(x: I):\n    return x.m()\n",
    }

    result = await _answer(tmp_path, files)

    # The receiver is not bound (an unresolved inbound edge already blocks).
    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert "use.py:5" in result["next_step"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("b_text", "extra"),
    [
        # transitive: B inherits A through M
        (
            "from pkg.a import A\nfrom pkg.i import I\n\n\nclass M(A):\n    pass\n\n\n"
            "class B(M, I):\n    pass\n",
            {},
        ),
        # an aliased import
        (
            "from pkg.a import A as Base\nfrom pkg.i import I\n\n\n"
            "class B(Base, I):\n    pass\n",
            {},
        ),
        # a module attribute
        ("import pkg.a\nfrom pkg.i import I\n\n\nclass B(pkg.a.A, I):\n    pass\n", {}),
        # a renamed re-export
        (
            "from pkg import Base, I\n\n\nclass B(Base, I):\n    pass\n",
            {"pkg/__init__.py": "from pkg.a import A as Base\nfrom pkg.i import I\n"},
        ),
        # the other base comes second, the declaring class first, through a package
        (
            "from pkg import A, I\n\n\nclass B(I, A):\n    pass\n",
            {"pkg/__init__.py": "from pkg.a import A\nfrom pkg.i import I\n"},
        ),
    ],
)
async def test_subclass_shapes_are_found(tmp_path, b_text: str, extra) -> None:
    files = {**_REPRO, "pkg/b.py": b_text, **extra}

    result = await _answer(tmp_path, files)

    _blocked(result)


@pytest.mark.asyncio
async def test_subscripted_generic_declaring_class_is_followed(tmp_path) -> None:
    files = {
        **_REPRO,
        "pkg/a.py": (
            "from typing import Generic, TypeVar\nT = TypeVar('T')\n\n\n"
            "class A(Generic[T]):\n    def m(self):\n        return 1\n"
        ),
        "pkg/b.py": _B.replace("(A, I)", "(A[int], I)"),
    }

    result = await _answer(tmp_path, files)

    _blocked(result)
    assert "`B`" in result["next_step"]


@pytest.mark.asyncio
async def test_unfollowable_base_naming_the_class_blocks(tmp_path) -> None:
    files = {
        **_REPRO,
        "pkg/b.py": (
            "from pkg.a import A\nfrom pkg.i import I\n\n\ndef mix(c):\n    return c\n\n\n"
            "class B(mix(A), I):\n    pass\n"
        ),
    }

    result = await _answer(tmp_path, files)

    _blocked(result)
    assert "mix(A)" in result["next_step"]


# --- negatives: the answer stays complete --------------------------------------


@pytest.mark.asyncio
async def test_other_base_without_the_name_stays_complete(tmp_path) -> None:
    files = {
        **_REPRO,
        "pkg/i.py": "class I:\n    def other(self):\n        return 0\n",
        # a same-named method, called through self, in a class outside B's MRO
        "z.py": "class Z:\n    def m(self):\n        return 0\n\n    def run(self):\n"
        "        return self.m()\n",
    }

    result = await _answer(tmp_path, files)

    assert result["completeness"] == "complete", result


@pytest.mark.asyncio
async def test_site_outside_every_dangerous_mro_stays_complete(tmp_path) -> None:
    files = {
        **_REPRO,
        "pkg/i.py": "class I:\n    def m(self):\n        raise NotImplementedError\n",
        "z.py": "class Z:\n    def m(self):\n        return 0\n\n    def run(self):\n"
        "        return self.m()\n",
    }

    result = await _answer(tmp_path, files)

    assert result["completeness"] == "complete", result


@pytest.mark.asyncio
async def test_no_call_named_like_it_stays_complete(tmp_path) -> None:
    files = {
        **_REPRO,
        "pkg/i.py": "class I:\n    def m(self):\n        raise NotImplementedError\n",
    }

    result = await _answer(tmp_path, files)

    assert result["completeness"] == "complete", result


@pytest.mark.asyncio
async def test_mangled_private_name_stays_complete(tmp_path) -> None:
    files = {
        **_REPRO,
        "pkg/a.py": _A.replace("def m", "def __m"),
        "pkg/i.py": _I.replace("m(self)", "__m(self)").replace(
            "self.m()", "self.__m()"
        ),
    }

    result = await _answer(tmp_path, files, "A.__m")

    assert result["completeness"] == "complete", result


@pytest.mark.asyncio
async def test_unrelated_class_of_the_same_name_is_not_a_subclass(tmp_path) -> None:
    files = {
        **_REPRO,
        "other/__init__.py": "",
        "other/a.py": "class A:\n    pass\n",
        "pkg/b.py": _B.replace("from pkg.a import A", "from other.a import A"),
    }

    result = await _answer(tmp_path, files)

    assert result["completeness"] == "complete", result


# --- fail closed --------------------------------------------------------------


@pytest.mark.asyncio
async def test_too_many_subclasses_block(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(callers_py_subtypes, "_MAX_SUBCLASSES", 0)

    result = await _answer(tmp_path, _REPRO)

    _blocked(result)
    assert "too many subclasses" in result["next_step"]


@pytest.mark.asyncio
async def test_unparsable_file_naming_the_class_blocks(tmp_path) -> None:
    files = {**_REPRO, "bad.py": "from pkg.a import A\nclass Bad(A:\n"}

    result = await _answer(tmp_path, files)

    _blocked(result)
    assert "bad.py" in result["next_step"]


@pytest.mark.asyncio
async def test_unknown_base_of_a_subclass_blocks(tmp_path) -> None:
    files = {
        **_REPRO,
        "pkg/i.py": "class I:\n    def other(self):\n        return 0\n",
        "z.py": "class Z:\n    def m(self):\n        return 0\n\n    def run(self):\n"
        "        return self.m()\n",
        "pkg/b.py": (
            "from pkg.a import A\n\n\ndef mix():\n    return object\n\n\n"
            "class B(A, mix()):\n    pass\n"
        ),
    }

    result = await _answer(tmp_path, files)

    _blocked(result)
    assert "mix()" in result["next_step"]


# --- the module, on a minimal index ------------------------------------------------


class _Cache:
    """Python files, symbol rows and call edges, in memory."""

    def __init__(self, files, symbols=(), edges=()) -> None:
        import sqlite3

        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE ast_index (file_path TEXT, language TEXT)")
        self.conn.execute(
            "CREATE TABLE ast_symbol_rows (id INTEGER PRIMARY KEY, name TEXT, "
            "kind TEXT, file_path TEXT, line INTEGER)"
        )
        self.conn.execute(
            "CREATE TABLE edges (kind TEXT, callee_name TEXT, file_path TEXT, "
            "line INTEGER, callee_full TEXT, callee_resolution TEXT, "
            "callee_resolved_file TEXT, callee_symbol_id INTEGER, language TEXT)"
        )
        for rel in files:
            self.conn.execute("INSERT INTO ast_index VALUES (?, 'python')", (rel,))
        for row in symbols:
            self.conn.execute(
                "INSERT INTO ast_symbol_rows (id, name, kind, file_path, line) "
                "VALUES (?, ?, ?, ?, ?)",
                row,
            )
        for row in edges:
            self.conn.execute(
                "INSERT INTO edges VALUES ('calls', ?, ?, ?, ?, ?, ?, ?, 'python')", row
            )

    def get_conn(self):
        return self.conn


#: ``A.m`` (id 1), ``I.m`` (id 2); ``self.m()`` in ``I.run`` bound to ``I.m``.
_SYMBOLS = [(1, "m", "method", "pkg/a.py", 2), (2, "m", "method", "pkg/i.py", 2)]
_SELF_SITE = ("m", "pkg/i.py", 6, "self.m", "local", "pkg/i.py", 2)


def _find(tmp_path, files=_REPRO, edges=(_SELF_SITE,), symbols=_SYMBOLS, cache=None):
    root = _write(tmp_path, files)
    if cache is None:
        cache = _Cache([rel for rel in files if rel.endswith(".py")], symbols, edges)
    return callers_py_subtypes.python_subtype_finding(
        root, "pkg/a.py", 2, "m", cache, lambda: frozenset()
    )


def test_finding_names_the_subclass_the_base_and_the_site(tmp_path) -> None:
    found = _find(tmp_path)

    assert found is not None
    assert found.reason == OVERRIDE_REASON
    assert "class `A` (pkg/a.py:1) has subtype `B`" in found.describe()
    assert "`I.m` (pkg/i.py:1)" in found.describe()
    assert "pkg/i.py:6" in found.describe()


@pytest.mark.parametrize(
    "edge",
    [
        ("m", "x.py", 1, "m", "unknown", "", None),  # a plain call
        ("m", "x.py", 1, "x.m", "external", "", None),  # outside the project
        ("m", "x.py", 1, "x.m", "local", "pkg/a.py", 1),  # bound here
        ("m", "x.py", 1, "x.m", "project", "pkg/a.py", None),  # one `m` in its file
    ],
)
def test_edges_that_cannot_dispatch_elsewhere_pass(tmp_path, edge) -> None:
    assert _find(tmp_path, edges=[edge]) is None


def test_bound_receiver_of_the_other_base_is_a_site(tmp_path) -> None:
    edge = ("m", "use.py", 5, "x.m", "annotated_receiver", "pkg/i.py", 2)

    found = _find(tmp_path, edges=[edge])

    assert found is not None
    assert "use.py:5" in found.describe()


def test_unbound_receiver_is_a_site(tmp_path) -> None:
    found = _find(tmp_path, edges=[("m", "use.py", 5, "x.m", "unknown", "", None)])

    assert found is not None
    assert found.describe().endswith("may dispatch here: use.py:5")


def test_receiver_bound_outside_the_mro_passes(tmp_path) -> None:
    files = {**_REPRO, "z.py": "class Z:\n    def m(self):\n        return 0\n"}
    symbols = [*_SYMBOLS, (3, "m", "method", "z.py", 2)]
    edge = ("m", "use.py", 5, "x.m", "annotated_receiver", "z.py", 3)

    assert _find(tmp_path, files, [edge], symbols) is None


def test_unknown_bound_symbol_is_a_site(tmp_path) -> None:
    edge = ("m", "use.py", 5, "x.m", "project", "gone.py", 99)

    found = _find(tmp_path, edges=[edge])

    assert found is not None
    assert found.describe().endswith("may dispatch here: use.py:5")


def test_unreadable_edges_fail(tmp_path) -> None:
    cache = _Cache(list(_REPRO))
    cache.conn.execute("DROP TABLE edges")

    found = _find(tmp_path, cache=cache)

    assert found is not None
    assert "could not be read" in found.describe()


def test_unlisted_files_fail(tmp_path) -> None:
    cache = _Cache(list(_REPRO), _SYMBOLS, [_SELF_SITE])
    cache.conn.execute("DROP TABLE ast_index")

    found = _find(tmp_path, cache=cache)

    assert found is not None
    assert "could not be listed" in found.describe()


def test_unreadable_listed_file_fails(tmp_path) -> None:
    cache = _Cache([*_REPRO, "gone.py"], _SYMBOLS, [_SELF_SITE])

    found = _find(tmp_path, cache=cache)

    assert found is not None
    assert "gone.py" in found.describe()


def test_unparsable_file_not_naming_the_class_passes(tmp_path) -> None:
    files = {
        **_REPRO,
        "pkg/i.py": "class I:\n    def other(self):\n        return 0\n",
        "bad.py": "class Bad(Other:\n",
    }

    assert _find(tmp_path, files) is None


def test_metaclass_keyword_of_a_subclass_that_cannot_be_followed_fails(
    tmp_path,
) -> None:
    files = {
        **_REPRO,
        "pkg/b.py": _B.replace("(A, I)", "(A, I, metaclass=make())"),
    }

    found = _find(tmp_path, files)

    assert found is not None
    assert "metaclass=make()" in found.describe()


def test_class_without_the_member_is_not_checked(tmp_path) -> None:
    root = _write(tmp_path, _REPRO)
    cache = _Cache(list(_REPRO), _SYMBOLS, [_SELF_SITE])

    assert (
        callers_py_subtypes.python_subtype_finding(
            root, "main.py", 1, "main", cache, lambda: frozenset()
        )
        is None
    )
    assert (
        callers_py_subtypes.python_subtype_finding(
            root, "gone.py", 1, "m", cache, lambda: frozenset()
        )
        is None
    )


def test_index_is_built_once_per_state(tmp_path, monkeypatch) -> None:
    builds: list[int] = []
    real = callers_py_class_index.build

    def counting(*args, **kwargs):
        builds.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(callers_py_class_index, "build", counting)
    monkeypatch.setattr(callers_py_class_index, "_RACY_NS", 0)
    cache = _Cache(list(_REPRO), _SYMBOLS, [_SELF_SITE])

    assert _find(tmp_path, cache=cache) is not None
    root = str(tmp_path)
    assert callers_py_subtypes.python_subtype_finding(
        root, "pkg/a.py", 2, "m", cache, lambda: frozenset()
    )
    assert len(builds) == 1

    (tmp_path / "pkg" / "b.py").write_text(
        "from pkg.a import A\n\n\nclass B(A):\n    pass\n", encoding="utf-8"
    )
    callers_py_supertypes.clear_parsed()
    assert (
        callers_py_subtypes.python_subtype_finding(
            root, "pkg/a.py", 2, "m", cache, lambda: frozenset()
        )
        is None
    )
    assert len(builds) == 2


def test_racy_index_is_not_kept(tmp_path, monkeypatch) -> None:
    builds: list[int] = []
    real = callers_py_class_index.build

    def counting(*args, **kwargs):
        builds.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(callers_py_class_index, "build", counting)
    cache = _Cache(list(_REPRO), _SYMBOLS, [_SELF_SITE])

    _find(tmp_path, cache=cache)
    callers_py_subtypes.python_subtype_finding(
        str(tmp_path), "pkg/a.py", 2, "m", cache, lambda: frozenset()
    )

    assert len(builds) == 2


def test_metaclass_naming_the_class_is_not_a_subclass(tmp_path) -> None:
    files = {
        **_REPRO,
        "pkg/b.py": (
            "from pkg.a import A\n\n\ndef make(base):\n    return type\n\n\n"
            "class K(metaclass=make(A)):\n    pass\n"
        ),
    }

    assert _find(tmp_path, files) is None


# --- the class index, directly --------------------------------------------------------


def _class_index(tmp_path, files):
    root = _write(tmp_path, files)
    return callers_py_class_index.build(root, sorted(files))


def test_unparsable_file_renaming_the_class_fails(tmp_path) -> None:
    files = {**_REPRO, "bad.py": "from pkg.a import A as Z\nclass Bad(:\n"}

    found = _find(tmp_path, files)

    assert found is not None
    assert "bad.py" in found.describe()


def test_value_bound_to_the_class_blocks(tmp_path) -> None:
    files = {
        **_REPRO,
        "pkg/b.py": (
            "import pkg.a\nfrom pkg.i import I\n\nAlias = pkg.a.A\nAlias = Alias\n\n\n"
            "class B(Alias, I):\n    pass\n"
        ),
    }

    found = _find(tmp_path, files)

    assert found is not None
    assert "`Alias`" in found.describe()


def test_unlocatable_class_has_an_unknown_base(tmp_path) -> None:
    index = _class_index(tmp_path, _REPRO)

    (base,) = index.bases(("pkg/a.py", 99, 0), lambda: frozenset())
    assert isinstance(base, callers_py_class_index.Unknown)
    assert index.klass(("gone.py", 1, 0)) is None
    assert index.class_at("pkg/a.py", 2, "nope") is None


def test_recursion_in_a_base_is_unknown(tmp_path, monkeypatch) -> None:
    index = _class_index(tmp_path, _REPRO)

    def deep(*_args, **_kwargs):
        raise RecursionError

    monkeypatch.setattr(callers_py_class_index, "_eval", deep)
    monkeypatch.setattr(callers_py_class_index, "_keyword_problem", deep)
    files = {**_REPRO, "pkg/b.py": _B.replace("(A, I)", "(A, metaclass=M)")}
    index = _class_index(tmp_path, files)

    bases = index.bases(("pkg/b.py", 5, 0), lambda: frozenset())

    assert [base.why for base in bases] == [
        "a base too deeply nested to follow",
        "a class keyword the index cannot follow",
    ]


def test_base_in_an_unindexed_file_ends_the_ancestry(tmp_path) -> None:
    index = _class_index(tmp_path, {k: v for k, v in _REPRO.items() if k != "pkg/a.py"})
    (tmp_path / "pkg" / "a.py").write_text(_A, encoding="utf-8")
    index.unreadable.clear()
    index._files["pkg/a.py"] = None

    found = index.ancestors(("pkg/b.py", 5, 0), lambda: frozenset())

    assert isinstance(found, tuple)
    assert "not indexed" in found[1].why


def test_indexes_of_other_roots_are_evicted(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(callers_py_class_index, "_INDEXES_MAX", 1)
    monkeypatch.setattr(callers_py_class_index, "_RACY_NS", 0)
    cache = _Cache(list(_REPRO))
    one = _write(tmp_path / "one", _REPRO)
    two = _write(tmp_path / "two", _REPRO)

    callers_py_class_index.project_index(one, cache)
    callers_py_class_index.project_index(two, cache)

    assert list(callers_py_class_index._INDEXES) == [two]
    assert isinstance(callers_py_class_index.project_index(one, None), str)


def test_no_index_fails(tmp_path) -> None:
    root = _write(tmp_path, _REPRO)

    found = callers_py_subtypes.python_subtype_finding(
        root, "pkg/a.py", 2, "m", None, lambda: frozenset()
    )

    assert found is not None
    assert "index could not be read" in found.describe()


def test_unreadable_binding_is_a_site(tmp_path) -> None:
    class _Flaky(_Cache):
        def get_conn(self):
            conn = self.conn

            class _Conn:
                def execute(self, sql, *args):
                    if "WHERE id = ?" in sql:
                        raise RuntimeError("gone")
                    return conn.execute(sql, *args)

            return _Conn()

    edge = ("m", "use.py", 5, "x.m", "annotated_receiver", "z.py", 3)
    cache = _Flaky(list(_REPRO), _SYMBOLS, [edge])

    found = _find(tmp_path, cache=cache)

    assert found is not None
    assert found.describe().endswith("may dispatch here: use.py:5")
