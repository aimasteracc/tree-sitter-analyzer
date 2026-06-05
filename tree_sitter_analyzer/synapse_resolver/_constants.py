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
        "strip", "lstrip", "rstrip", "lower", "upper", "title", "capitalize",
        "casefold", "swapcase", "split", "rsplit", "splitlines", "join",
        "startswith", "endswith", "replace", "find", "rfind", "index", "rindex",
        "count", "format", "format_map", "encode", "decode", "zfill", "ljust",
        "rjust", "center", "partition", "rpartition", "expandtabs", "translate",
        "maketrans", "removeprefix", "removesuffix", "isdigit", "isalpha",
        "isalnum", "isspace", "isupper", "islower", "istitle", "isnumeric",
        "isdecimal", "isidentifier", "isprintable", "isascii",
    }
)
_PATH_METHODS = frozenset(
    {
        "write_text", "read_text", "write_bytes", "read_bytes", "mkdir",
        "exists", "is_file", "is_dir", "is_symlink", "is_absolute", "glob",
        "rglob", "resolve", "absolute", "relative_to", "with_suffix",
        "with_name", "with_stem", "iterdir", "unlink", "rmdir", "touch",
        "rename", "replace", "samefile", "expanduser", "as_posix", "as_uri",
        "joinpath", "stat", "lstat", "chmod", "lchmod", "symlink_to",
        "hardlink_to", "owner", "group", "readlink", "match",
    }
)
_DICT_LIST_SET_METHODS = frozenset(
    {
        "items", "keys", "values", "get", "setdefault", "update", "pop",
        "popitem", "fromkeys", "append", "extend", "insert", "remove", "sort",
        "reverse", "add", "discard", "union", "intersection", "difference",
        "symmetric_difference", "issubset", "issuperset", "isdisjoint",
        "copy", "clear", "count", "index",
    }
)
_REGEX_METHODS = frozenset(
    {
        "group", "groups", "groupdict", "match", "fullmatch", "search",
        "findall", "finditer", "sub", "subn", "split", "span", "start", "end",
        "expand",
    }
)
_ARGPARSE_METHODS = frozenset(
    {
        "add_argument", "add_subparsers", "add_parser", "parse_args",
        "parse_known_args", "set_defaults", "get_default",
        "add_argument_group", "add_mutually_exclusive_group", "print_help",
        "print_usage", "error", "format_help",
    }
)
_DATETIME_METHODS = frozenset(
    {
        "isoformat", "strftime", "strptime", "total_seconds", "timestamp",
        "astimezone", "replace", "date", "time", "weekday", "isoweekday",
        "fromtimestamp", "fromisoformat", "utcnow", "now", "today",
    }
)
_MISC_METHODS = frozenset(
    {
        # contextlib / io / common protocol methods that recur as bare names.
        "write", "writelines", "read", "readline", "readlines", "seek", "tell",
        "flush", "close", "fileno", "getvalue",
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


__all__ = ["BUILTINS_PY", "STDLIB_METHODS_PY", "STDLIB_NAMES_PY"]
