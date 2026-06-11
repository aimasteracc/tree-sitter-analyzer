"""Stdlib + builtin allowlists for the Synapse resolver.

Kept in a dedicated module so the big literal sets don't push the main
resolver over the 500-line file rule.
"""

from __future__ import annotations

import sys


def _python_stdlib_names() -> frozenset[str]:
    """Top-level Python stdlib module names.

    Prefers ``sys.stdlib_module_names`` (CPython 3.10+); merges in a
    curated fallback so older runtimes still match common cases.
    """
    names: set[str] = set()
    if hasattr(sys, "stdlib_module_names"):
        names.update(sys.stdlib_module_names)
    names.update(_FALLBACK_STDLIB)
    return frozenset(names)


_FALLBACK_STDLIB = frozenset(
    {
        "abc",
        "argparse",
        "array",
        "ast",
        "asyncio",
        "base64",
        "bisect",
        "builtins",
        "calendar",
        "collections",
        "concurrent",
        "configparser",
        "contextlib",
        "copy",
        "csv",
        "dataclasses",
        "datetime",
        "decimal",
        "difflib",
        "enum",
        "errno",
        "fnmatch",
        "functools",
        "gc",
        "glob",
        "gzip",
        "hashlib",
        "heapq",
        "hmac",
        "html",
        "http",
        "importlib",
        "inspect",
        "io",
        "ipaddress",
        "itertools",
        "json",
        "logging",
        "math",
        "mimetypes",
        "multiprocessing",
        "operator",
        "os",
        "pathlib",
        "pickle",
        "platform",
        "posixpath",
        "pprint",
        "queue",
        "random",
        "re",
        "shelve",
        "shutil",
        "signal",
        "socket",
        "sqlite3",
        "ssl",
        "stat",
        "statistics",
        "string",
        "struct",
        "subprocess",
        "sys",
        "tempfile",
        "textwrap",
        "threading",
        "time",
        "tomllib",
        "traceback",
        "types",
        "typing",
        "unicodedata",
        "unittest",
        "urllib",
        "uuid",
        "warnings",
        "weakref",
        "xml",
        "zipfile",
        "zlib",
    }
)


STDLIB_NAMES_PY: frozenset[str] = _python_stdlib_names()


# Python builtin callables — never resolve to a project file.
BUILTINS_PY: frozenset[str] = frozenset(
    {
        "abs",
        "all",
        "any",
        "ascii",
        "bin",
        "bool",
        "bytearray",
        "bytes",
        "callable",
        "chr",
        "classmethod",
        "compile",
        "complex",
        "delattr",
        "dict",
        "dir",
        "divmod",
        "enumerate",
        "eval",
        "exec",
        "filter",
        "float",
        "format",
        "frozenset",
        "getattr",
        "globals",
        "hasattr",
        "hash",
        "help",
        "hex",
        "id",
        "input",
        "int",
        "isinstance",
        "issubclass",
        "iter",
        "len",
        "list",
        "locals",
        "map",
        "max",
        "memoryview",
        "min",
        "next",
        "object",
        "oct",
        "open",
        "ord",
        "pow",
        "print",
        "property",
        "range",
        "repr",
        "reversed",
        "round",
        "set",
        "setattr",
        "slice",
        "sorted",
        "staticmethod",
        "str",
        "sum",
        "super",
        "tuple",
        "type",
        "vars",
        "zip",
        "__import__",
        "Exception",
        "ValueError",
        "TypeError",
        "KeyError",
        "IndexError",
        "RuntimeError",
        "StopIteration",
        "AttributeError",
        "NotImplementedError",
        "FileNotFoundError",
        "OSError",
        "IOError",
        "ImportError",
    }
)


# ---------------------------------------------------------------------------
# RFC-0004: well-known stdlib/builtin METHOD names.
#
# The builtin/stdlib classifier above keys on *function* names (``len``) and
# top-level *module* names (``os``); it never matches a bare *method* name like
# ``write_text`` or ``strip``, so those call edges fall through to ``unknown``.
# This curated table is consulted by the cascade's FINAL tier
# (``_try_stdlib_method``) — AFTER every project-binding rule — to classify such
# names as ``stdlib`` when (and only when) the project defines no method of that
# name. Grouped by owning type for auditability. High-recall, not exhaustive.
# ---------------------------------------------------------------------------
_STR_METHODS = frozenset(
    {
        "strip",
        "lstrip",
        "rstrip",
        "lower",
        "upper",
        "title",
        "capitalize",
        "casefold",
        "swapcase",
        "split",
        "rsplit",
        "splitlines",
        "join",
        "startswith",
        "endswith",
        "replace",
        "find",
        "rfind",
        "index",
        "rindex",
        "count",
        "format",
        "format_map",
        "encode",
        "decode",
        "zfill",
        "ljust",
        "rjust",
        "center",
        "partition",
        "rpartition",
        "expandtabs",
        "translate",
        "maketrans",
        "removeprefix",
        "removesuffix",
        "isdigit",
        "isalpha",
        "isalnum",
        "isspace",
        "isupper",
        "islower",
        "istitle",
        "isnumeric",
        "isdecimal",
        "isidentifier",
        "isprintable",
        "isascii",
    }
)
_PATH_METHODS = frozenset(
    {
        "write_text",
        "read_text",
        "write_bytes",
        "read_bytes",
        "mkdir",
        "exists",
        "is_file",
        "is_dir",
        "is_symlink",
        "is_absolute",
        "glob",
        "rglob",
        "resolve",
        "absolute",
        "relative_to",
        "with_suffix",
        "with_name",
        "with_stem",
        "iterdir",
        "unlink",
        "rmdir",
        "touch",
        "rename",
        "replace",
        "samefile",
        "expanduser",
        "as_posix",
        "as_uri",
        "joinpath",
        "stat",
        "lstat",
        "chmod",
        "lchmod",
        "symlink_to",
        "hardlink_to",
        "owner",
        "group",
        "readlink",
        "match",
    }
)
_DICT_LIST_SET_METHODS = frozenset(
    {
        "items",
        "keys",
        "values",
        "get",
        "setdefault",
        "update",
        "pop",
        "popitem",
        "fromkeys",
        "append",
        "extend",
        "insert",
        "remove",
        "sort",
        "reverse",
        "add",
        "discard",
        "union",
        "intersection",
        "difference",
        "symmetric_difference",
        "issubset",
        "issuperset",
        "isdisjoint",
        "copy",
        "clear",
        "count",
        "index",
    }
)
_REGEX_METHODS = frozenset(
    {
        "group",
        "groups",
        "groupdict",
        "match",
        "fullmatch",
        "search",
        "findall",
        "finditer",
        "sub",
        "subn",
        "split",
        "span",
        "start",
        "end",
        "expand",
    }
)
_ARGPARSE_METHODS = frozenset(
    {
        "add_argument",
        "add_subparsers",
        "add_parser",
        "parse_args",
        "parse_known_args",
        "set_defaults",
        "get_default",
        "add_argument_group",
        "add_mutually_exclusive_group",
        "print_help",
        "print_usage",
        "error",
        "format_help",
    }
)
_DATETIME_METHODS = frozenset(
    {
        "isoformat",
        "strftime",
        "strptime",
        "total_seconds",
        "timestamp",
        "astimezone",
        "replace",
        "date",
        "time",
        "weekday",
        "isoweekday",
        "fromtimestamp",
        "fromisoformat",
        "utcnow",
        "now",
        "today",
    }
)
_MISC_METHODS = frozenset(
    {
        # contextlib / io / common protocol methods that recur as bare names.
        "write",
        "writelines",
        "read",
        "readline",
        "readlines",
        "seek",
        "tell",
        "flush",
        "close",
        "fileno",
        "getvalue",
    }
)

STDLIB_METHODS_PY: frozenset[str] = (
    _STR_METHODS
    | _PATH_METHODS
    | _DICT_LIST_SET_METHODS
    | _REGEX_METHODS
    | _ARGPARSE_METHODS
    | _DATETIME_METHODS
    | _MISC_METHODS
)


# ---------------------------------------------------------------------------
# RFC-0005: well-known EXTERNAL (third-party) library METHOD names.
#
# These are method names that are overwhelmingly associated with test-framework
# libraries (pytest, hypothesis, unittest.mock) and whose appearance as bare
# call edges almost certainly means the caller is invoking a third-party library,
# not a project-defined method.
#
# Consulted by the cascade's ``_try_external_method`` tier — placed AFTER
# ``_try_stdlib_method`` — to classify such names as ``external`` when (and only
# when) the project defines no compatible-language method of that name.  Grouped
# by owning library for auditability.  High-recall, conservative — only names
# that are overwhelmingly test-framework.  Ambiguous/generic names (``settings``,
# ``debug``, ``draw``, ``execute``, ``language``) that projects commonly define
# are deliberately EXCLUDED; the project-ownership gate protects other names.
#
# Rationale on ``setattr`` (688 occurrences in the gap): it is the BUILTIN
# ``setattr`` called as ``monkeypatch.setattr(...)`` — the qualifier makes
# ``_try_builtin`` (which requires no qualifier) skip it.  Since ``setattr``
# is genuinely a Python builtin (already in BUILTINS_PY), classifying it
# ``external`` here would be misleading.  It is therefore left as a known
# residual for a future ``_try_builtin_method`` tier or receiver-type inference.
# ---------------------------------------------------------------------------

# pytest — fixture methods and helpers
_PYTEST_METHODS = frozenset(
    {
        "raises",  # pytest.raises(...)
        "skip",  # pytest.skip(...)
        "skipif",  # pytest.mark.skipif / @pytest.mark.skipif
        "parametrize",  # @pytest.mark.parametrize
        "fixture",  # @pytest.fixture
        "mark",  # pytest.mark
        "approx",  # pytest.approx(...)
        "warns",  # pytest.warns(...)
        "deprecated_call",  # pytest.deprecated_call(...)
        "readouterr",  # capsys.readouterr() / capfd.readouterr()
        "monkeypatch",  # monkeypatch fixture (as receiver name)
    }
)

# hypothesis — core strategies and decorators
_HYPOTHESIS_METHODS = frozenset(
    {
        "given",  # @given(...)
        "integers",  # st.integers(...)
        "sampled_from",  # st.sampled_from(...)
        "characters",  # st.characters(...)
        "text",  # st.text(...)
        "floats",  # st.floats(...)
        "lists",  # st.lists(...)
        "dictionaries",  # st.dictionaries(...)
        "tuples",  # st.tuples(...)
        "booleans",  # st.booleans(...)
        "composite",  # @st.composite
        "assume",  # assume(...)
        "note",  # note(...)
        "target",  # target(...)
        "event",  # event(...)
        "reproduce_failure",  # @reproduce_failure(...)
    }
)

# unittest.mock — mock assertion and configuration methods
_MOCK_METHODS = frozenset(
    {
        "assert_called_once_with",  # mock.assert_called_once_with(...)
        "assert_called_once",  # mock.assert_called_once()
        "assert_called_with",  # mock.assert_called_with(...)
        "assert_called",  # mock.assert_called()
        "assert_not_called",  # mock.assert_not_called()
        "assert_any_call",  # mock.assert_any_call(...)
        "assert_has_calls",  # mock.assert_has_calls(...)
        "call_args_list",  # mock.call_args_list
        "mock_calls",  # mock.mock_calls
        "reset_mock",  # mock.reset_mock()
        "configure_mock",  # mock.configure_mock(...)
        "MagicMock",  # MagicMock(...) — constructor but used as call
        "patch",  # @patch(...) / patch(...)
        "call",  # call(...) — mock call object
    }
)

EXTERNAL_METHODS_PY: frozenset[str] = (
    _PYTEST_METHODS | _HYPOTHESIS_METHODS | _MOCK_METHODS
)


# ---------------------------------------------------------------------------
# RFC-0007: Python builtin names that legitimately appear WITH a qualifier.
#
# ``_try_builtin`` classifies bare builtins (no qualifier), so
# ``setattr(obj, 'x', 1)`` → builtin.  But ``monkeypatch.setattr(...)`` has
# a qualifier, causing ``_try_builtin`` to return None and the edge to fall
# through to ``unknown``.
#
# This frozenset covers builtin names whose QUALIFIED usage (receiver.name)
# is still overwhelmingly the Python builtin — NOT a method defined by the
# project.  Only names whose qualified form is almost exclusively the builtin
# are included; generic names that projects commonly define as methods are
# deliberately EXCLUDED.
#
# Consulted by ``_try_builtin_method``, placed AFTER ``_try_external_method``
# in the cascade, gated by the same language-aware project-ownership check
# as RFC-0004/0005 tiers.
#
# Conservative by design — four attribute-inspection builtins dominate the
# 688-edge residual (setattr alone is 688); anything else would risk
# mis-classifying legitimate project methods.
# ---------------------------------------------------------------------------
BUILTIN_QUALIFIED_PY: frozenset[str] = frozenset(
    {
        "setattr",  # monkeypatch.setattr(obj, 'attr', val) — 688 edges
        "getattr",  # obj.getattr(name, default) — receiver-qualified variant
        "hasattr",  # obj.hasattr(name) — receiver-qualified variant
        "delattr",  # obj.delattr(name) — receiver-qualified variant
    }
)


# ---------------------------------------------------------------------------
# Python builtin container/type names that the extractor can infer as the
# receiver type when it sees a literal or constructor assignment, e.g.
# ``result = {}`` -> receiver type ``dict``, ``items = []`` -> ``list``.
#
# Used by ``_try_unique_method`` and ``_is_obvious_external`` to gate the
# builtin-receiver guard: a qualifier that IS one of these names is positively
# inferred as a builtin container -- binding its methods to a project symbol is
# wrong. A qualifier that is NOT here (e.g. ``store``, ``cache``) is an
# untyped receiver and must be allowed through to normal candidate selection
# (restores the ``store.get -> DataStore.get`` case, issue #447 adversarial P1).
# ---------------------------------------------------------------------------
BUILTIN_TYPE_NAMES_PY: frozenset[str] = frozenset(
    {
        "dict",
        "list",
        "set",
        "str",
        "tuple",
        "bytes",
        "bytearray",
        "frozenset",
        "int",
        "float",
        "bool",
    }
)


__all__ = [
    "BUILTIN_QUALIFIED_PY",
    "BUILTIN_TYPE_NAMES_PY",
    "BUILTINS_PY",
    "EXTERNAL_METHODS_PY",
    "STDLIB_METHODS_PY",
    "STDLIB_NAMES_PY",
]
