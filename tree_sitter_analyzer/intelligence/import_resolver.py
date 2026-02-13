#!/usr/bin/env python3
"""
Python Import Resolver for Code Intelligence Graph.

Resolves Python import statements to actual file paths within a project,
distinguishing between internal (project) and external (stdlib/third-party) imports.
"""

from __future__ import annotations

from pathlib import Path
from .models import ResolvedImport


# Common stdlib top-level modules (subset for fast lookup)
_STDLIB_MODULES = frozenset({
    "abc", "aifc", "argparse", "array", "ast", "asyncio", "atexit",
    "base64", "binascii", "bisect", "builtins", "bz2",
    "calendar", "cgi", "cmd", "code", "codecs", "collections",
    "colorsys", "compileall", "concurrent", "configparser", "contextlib",
    "contextvars", "copy", "copyreg", "cProfile", "csv", "ctypes",
    "dataclasses", "datetime", "dbm", "decimal", "difflib", "dis",
    "distutils", "doctest",
    "email", "encodings", "enum", "errno",
    "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch",
    "fractions", "ftplib", "functools",
    "gc", "getopt", "getpass", "gettext", "glob", "grp", "gzip",
    "hashlib", "heapq", "hmac", "html", "http",
    "idlelib", "imaplib", "importlib", "inspect", "io", "ipaddress",
    "itertools",
    "json",
    "keyword",
    "lib2to3", "linecache", "locale", "logging", "lzma",
    "mailbox", "math", "mimetypes", "mmap", "multiprocessing",
    "netrc", "numbers",
    "operator", "optparse", "os",
    "pathlib", "pdb", "pickle", "pickletools", "pipes", "pkgutil",
    "platform", "plistlib", "poplib", "posixpath", "pprint",
    "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr",
    "pydoc",
    "queue",
    "random", "re", "readline", "reprlib", "resource", "rlcompleter",
    "runpy",
    "sched", "secrets", "select", "selectors", "shelve", "shlex",
    "shutil", "signal", "site", "smtplib", "sndhdr", "socket",
    "socketserver", "sqlite3", "ssl", "stat", "statistics",
    "string", "stringprep", "struct", "subprocess", "sunau",
    "symtable", "sys", "sysconfig", "syslog",
    "tabnanny", "tarfile", "tempfile", "termios", "test",
    "textwrap", "threading", "time", "timeit", "tkinter", "token",
    "tokenize", "tomllib", "trace", "traceback", "tracemalloc", "tty",
    "turtle", "turtledemo", "types", "typing",
    "unicodedata", "unittest", "urllib", "uuid",
    "venv",
    "warnings", "wave", "weakref", "webbrowser", "winreg", "winsound",
    "wsgiref",
    "xml", "xmlrpc",
    "zipapp", "zipfile", "zipimport", "zlib",
    # Common underscore modules
    "_thread", "__future__",
})


class PythonImportResolver:
    """Resolves Python import statements to actual project files."""

    def resolve_import(
        self,
        module_name: str,
        imported_names: list[str],
        source_file: str,
        project_root: str,
        is_relative: bool = False,
    ) -> ResolvedImport:
        """
        Resolve a Python import to an actual file path.

        Args:
            module_name: The module name (e.g., "src.auth.service" or ".token")
            imported_names: Names imported from the module
            source_file: Path of the file containing the import
            project_root: Project root directory
            is_relative: Whether this is a relative import

        Returns:
            ResolvedImport with resolution result
        """
        if not module_name:
            return ResolvedImport(
                module_name="",
                resolved_path="",
                imported_names=imported_names,
                is_external=True,
                is_resolved=False,
            )

        # Handle relative imports
        if is_relative or module_name.startswith("."):
            return self._resolve_relative(
                module_name, imported_names, source_file, project_root
            )

        # Check if it's a known stdlib/external module
        top_level = module_name.split(".")[0]
        if top_level in _STDLIB_MODULES:
            return ResolvedImport(
                module_name=module_name,
                resolved_path="",
                imported_names=imported_names,
                is_external=True,
                is_resolved=True,
            )

        # Try to resolve as internal project module
        resolved = self._resolve_absolute(
            module_name, imported_names, project_root
        )
        if resolved.is_resolved:
            return resolved

        # If not found in project, treat as external (third-party)
        return ResolvedImport(
            module_name=module_name,
            resolved_path="",
            imported_names=imported_names,
            is_external=True,
            is_resolved=True,
        )

    def _resolve_absolute(
        self,
        module_name: str,
        imported_names: list[str],
        project_root: str,
    ) -> ResolvedImport:
        """Resolve an absolute import within the project."""
        parts = module_name.split(".")
        root = Path(project_root)

        # Try as a direct file: src/auth/service.py
        file_path = root.joinpath(*parts)
        py_file = file_path.with_suffix(".py")
        if py_file.is_file():
            return ResolvedImport(
                module_name=module_name,
                resolved_path=str(py_file),
                imported_names=imported_names,
                is_external=False,
                is_resolved=True,
            )

        # Try as a package: src/auth/__init__.py
        init_file = file_path / "__init__.py"
        if init_file.is_file():
            return ResolvedImport(
                module_name=module_name,
                resolved_path=str(init_file),
                imported_names=imported_names,
                is_external=False,
                is_resolved=True,
            )

        # Not found in project
        return ResolvedImport(
            module_name=module_name,
            resolved_path="",
            imported_names=imported_names,
            is_external=False,
            is_resolved=False,
        )

    def _resolve_relative(
        self,
        module_name: str,
        imported_names: list[str],
        source_file: str,
        project_root: str,
    ) -> ResolvedImport:
        """Resolve a relative import."""
        source_dir = Path(source_file).parent

        # Count leading dots
        dots = 0
        for ch in module_name:
            if ch == ".":
                dots += 1
            else:
                break

        # Navigate up directories
        base_dir = source_dir
        for _ in range(dots - 1):
            base_dir = base_dir.parent

        # Get remaining module path
        remaining = module_name[dots:]

        if remaining:
            parts = remaining.split(".")
            target_path = base_dir.joinpath(*parts)
        else:
            target_path = base_dir

        # Try as file
        py_file = target_path.with_suffix(".py")
        if py_file.is_file():
            return ResolvedImport(
                module_name=module_name,
                resolved_path=str(py_file),
                imported_names=imported_names,
                is_external=False,
                is_resolved=True,
            )

        # Try as package
        init_file = target_path / "__init__.py"
        if init_file.is_file():
            return ResolvedImport(
                module_name=module_name,
                resolved_path=str(init_file),
                imported_names=imported_names,
                is_external=False,
                is_resolved=True,
            )

        # For 'from . import X', X might be a file in the directory
        if not remaining and imported_names:
            for name in imported_names:
                candidate = base_dir / f"{name}.py"
                if candidate.is_file():
                    return ResolvedImport(
                        module_name=module_name,
                        resolved_path=str(candidate),
                        imported_names=imported_names,
                        is_external=False,
                        is_resolved=True,
                    )

        return ResolvedImport(
            module_name=module_name,
            resolved_path="",
            imported_names=imported_names,
            is_external=False,
            is_resolved=False,
        )
