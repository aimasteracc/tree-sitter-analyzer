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


__all__ = ["BUILTINS_PY", "STDLIB_NAMES_PY"]
