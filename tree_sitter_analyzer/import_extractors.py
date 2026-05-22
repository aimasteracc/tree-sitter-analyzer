"""Import extraction functions for Python, JS/TS, Go, Rust, C/C++, Java, C#, Kotlin, Swift, Ruby, PHP — extracted from project_graph.py."""

from typing import Any

_GO_STD = {
    "fmt",
    "os",
    "io",
    "strings",
    "strconv",
    "math",
    "time",
    "net",
    "net/http",
    "encoding/json",
    "encoding/xml",
    "encoding/csv",
    "path",
    "path/filepath",
    "log",
    "errors",
    "context",
    "sync",
    "bufio",
    "bytes",
    "regexp",
    "sort",
    "crypto",
    "crypto/md5",
    "crypto/sha256",
    "database/sql",
    "html/template",
    "text/template",
    "testing",
    "runtime",
    "reflect",
    "unicode",
    "unicode/utf8",
    "flag",
    "runtime/debug",
    "archive/zip",
    "compress/gzip",
}

_RUST_STD_CRATES = {
    "std",
    "core",
    "alloc",
    "proc_macro",
    "test",
}

_STDLIB_TOP_LEVEL = {
    "os",
    "sys",
    "re",
    "json",
    "math",
    "time",
    "datetime",
    "collections",
    "itertools",
    "functools",
    "typing",
    "io",
    "pathlib",
    "hashlib",
    "random",
    "string",
    "textwrap",
    "logging",
    "argparse",
    "subprocess",
    "shutil",
    "tempfile",
    "unittest",
    "pytest",
    "warnings",
    "traceback",
    "abc",
    "base64",
    "csv",
    "enum",
    "dataclasses",
    "contextlib",
    "copy",
    "configparser",
    "importlib",
    "ast",
    "inspect",
    "operator",
    "struct",
    "weakref",
    "array",
    "queue",
    "socket",
    "http",
    "urllib",
    "email",
    "html",
    "xml",
    "sqlite3",
    "hmac",
    "secrets",
}

_JS_BUILTIN = {
    "fs",
    "path",
    "http",
    "https",
    "os",
    "util",
    "stream",
    "events",
    "crypto",
    "buffer",
    "child_process",
    "cluster",
    "dgram",
    "dns",
    "net",
    "querystring",
    "readline",
    "repl",
    "tls",
    "url",
    "v8",
    "vm",
    "zlib",
    "assert",
    "console",
    "process",
    "timers",
    "module",
    "perf_hooks",
}

_CSHARP_STD_NAMESPACES = {
    "System",
    "System.Collections",
    "System.Collections.Generic",
    "System.IO",
    "System.Linq",
    "System.Net",
    "System.Net.Http",
    "System.Threading",
    "System.Threading.Tasks",
    "System.Text",
    "System.Text.Json",
    "System.Text.RegularExpressions",
    "System.Diagnostics",
    "System.Reflection",
    "System.Globalization",
    "System.Math",
    "System.Console",
    "System.String",
    "System.DateTime",
    "System.Guid",
    "System.Exception",
    "System.Action",
    "System.Func",
    "System.Convert",
    "System.Environment",
    "System.Array",
    "System.Collections.Concurrent",
    "System.Security",
    "System.Security.Cryptography",
    "System.Runtime",
    "System.Xml",
    "System.Data",
}

_KOTLIN_STD_ROOTS = {
    "kotlin",
    "kotlinx",
    "java",
    "javax",
}

_SWIFT_STD_MODULES = {
    "Foundation",
    "UIKit",
    "SwiftUI",
    "CoreData",
    "CoreGraphics",
    "CoreImage",
    "CoreLocation",
    "CoreAnimation",
    "AVFoundation",
    "Photos",
    "MapKit",
    "WebKit",
    "StoreKit",
    "SpriteKit",
    "SceneKit",
    "Metal",
    "MetalKit",
    "MetalPerformanceShaders",
    "Accelerate",
    "CryptoKit",
    "Combine",
    "Network",
    "Security",
    "Swift",
    "Observation",
    "RegexBuilder",
    "OSLog",
    "Testing",
    "XCTest",
}

_RUBY_STDLIB = {
    "json",
    "csv",
    "yaml",
    "uri",
    "net/http",
    "net/https",
    "open-uri",
    "fileutils",
    "tmpdir",
    "tempfile",
    "pathname",
    "date",
    "time",
    "timeout",
    "thread",
    "mutex_m",
    "monitor",
    "socket",
    "io/console",
    "stringio",
    "strscan",
    "logger",
    "optparse",
    "shellwords",
    "benchmark",
    "digest",
    "openssl",
    "securerandom",
    "base64",
    "zlib",
    "cgi",
    "erb",
    "rexml",
    "rss",
    "singleton",
    "forwardable",
    "observer",
    "pp",
    "prettyprint",
    "set",
    "tsort",
    "matrix",
    "bigdecimal",
    "nmatrix",
    "minitest",
    "test/unit",
    "rspec",
}


def walk_imports(
    node: Any, source: str, language: str, imports: list[dict[str, Any]]
) -> None:
    """Walk the AST to collect import statements."""
    try:
        if language in ("python",):
            _extract_python_imports(node, source, imports)
        elif language in ("javascript", "typescript"):
            _extract_js_imports(node, source, imports)
        elif language == "go":
            _extract_go_imports(node, source, imports)
        elif language == "rust":
            _extract_rust_imports(node, source, imports)
        elif language in ("c", "cpp"):
            _extract_cpp_imports(node, source, imports)
        elif language == "java":
            _extract_java_imports(node, source, imports)
        elif language in ("csharp", "c_sharp", "cs"):
            _extract_csharp_imports(node, source, imports)
        elif language == "kotlin":
            _extract_kotlin_imports(node, source, imports)
        elif language == "swift":
            _extract_swift_imports(node, source, imports)
        elif language == "ruby":
            _extract_ruby_imports(node, source, imports)
        elif language == "php":
            _extract_php_imports(node, source, imports)
    except Exception:  # nosec B110
        pass

    children = getattr(node, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            walk_imports(child, source, language, imports)


# Extract elements from AST: extract_python_import_simple
def extract_python_import_simple(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Handle: import os, sys"""
    for child in node.children:
        if getattr(child, "type", None) != "dotted_name":
            continue
        name = _node_text(child, source)
        if not name or name.split(".")[0] in _STDLIB_TOP_LEVEL:
            continue
        imports.append(
            {
                "module_name": name,
                "resolved_path": name.replace(".", "/") + ".py",
                "names": [name],
                "is_relative": False,
                "language": "python",
            }
        )


# Extract elements from AST: extract_python_import_from
def extract_python_import_from(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Handle: from [.][.]module import name1, name2

    Two shapes are emitted:
    1. ``from <prefix>module import a, b`` → one entry whose
       ``module_name`` is ``<prefix>module`` and ``names`` are the
       imported symbols.
    2. ``from . import a, b`` / ``from .. import a, b`` (no dotted name
       inside the ``relative_import``) → one entry **per imported
       name**, with ``module_name = <prefix><name>``. Each ``name`` is
       a candidate submodule of the current package; the resolver tries
       both ``<pkg>/<name>.py`` and ``<pkg>/<name>/__init__.py``. This
       matches Python's import semantics — ``from . import sub``
       imports the ``sub`` submodule (or, if there is no such
       submodule, the attribute ``sub`` from the current package's
       ``__init__.py``).
    """
    module_name = ""
    dots_prefix = ""
    imported_names: list[str] = []

    for child in node.children:
        ct = getattr(child, "type", None)

        if ct == "relative_import":
            for sub in child.children:
                st = getattr(sub, "type", None)
                if st == "import_prefix":
                    dots_prefix = _node_text(sub, source)
                elif st == "dotted_name":
                    module_name = _node_text(sub, source)

        elif ct == "dotted_name":
            if not module_name and not dots_prefix:
                module_name = _node_text(child, source)
            else:
                imported_names.append(_node_text(child, source))

        elif ct == "aliased_import":
            imported_names.extend(_extract_import_names(child, source))

    # Case 2: ``from . import x, y`` — relative_import had no
    # dotted_name, so ``module_name`` is empty but ``dots_prefix`` is
    # set. Emit one entry per imported name treating each as a
    # candidate submodule of the current package.
    if dots_prefix and not module_name:
        for name in imported_names:
            full_module = dots_prefix + name
            imports.append(
                {
                    "module_name": full_module,
                    "resolved_path": full_module.replace(".", "/") + ".py",
                    "names": [name],
                    "is_relative": True,
                    "language": "python",
                }
            )
        return

    if not module_name:
        return

    full_module = dots_prefix + module_name
    if not dots_prefix and module_name.split(".")[0] in _STDLIB_TOP_LEVEL:
        return

    imports.append(
        {
            "module_name": full_module,
            "resolved_path": full_module.replace(".", "/") + ".py"
            if full_module
            else "",
            "names": imported_names,
            "is_relative": bool(dots_prefix),
            "language": "python",
        }
    )


# Extract elements from AST: _extract_python_imports
def _extract_python_imports(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Extract Python import statements."""
    node_type = getattr(node, "type", None)

    if node_type == "import_statement":
        extract_python_import_simple(node, source, imports)
    elif node_type == "import_from_statement":
        extract_python_import_from(node, source, imports)


# Extract elements from AST: extract_js_imports
def extract_js_imports(node: Any, source: str, imports: list[dict[str, Any]]) -> None:
    """Extract JS/TS import/require statements."""
    node_type = getattr(node, "type", None)

    if node_type == "import_statement":
        # import { foo } from './bar'
        module_path = None
        for child in node.children:
            if getattr(child, "type", None) == "string":
                raw = _node_text(child, source).strip("'\"")
                if not raw.startswith(".") and not raw.startswith("/"):
                    if raw in _JS_BUILTIN:
                        continue
                module_path = raw

        if module_path:
            imports.append(
                {
                    "module_name": module_path,
                    "resolved_path": module_path,
                    "names": [],
                    "is_relative": module_path.startswith("."),
                    "language": "javascript",
                }
            )

    elif node_type == "call_expression":
        # r37cg (dogfood): extracted to flatten the require('./foo') walk
        # from depth 7 to 3.
        _collect_require_call_imports(node, source, imports)


# Extract elements from AST: _extract_import_names
def _collect_require_call_imports(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Walk a JS ``require('mod')`` call node, appending non-builtin imports.

    r37cg (dogfood): extracted from ``_extract_js_imports`` to flatten its
    7-deep nesting (elif → if → if → for → if → if → append).
    """
    func = node.child_by_field_name("function")
    if not (func and _node_text(func, source) == "require"):
        return
    args_node = node.child_by_field_name("arguments")
    if not (args_node and hasattr(args_node, "children")):
        return
    for child in args_node.children:
        if getattr(child, "type", None) != "string":
            continue
        raw = _node_text(child, source).strip("'\"")
        if raw in _JS_BUILTIN:
            continue
        imports.append(
            {
                "module_name": raw,
                "resolved_path": raw,
                "names": [],
                "is_relative": raw.startswith("."),
                "language": "javascript",
            }
        )


def _extract_import_names(names_node: Any, source: str) -> list[str]:
    """Extract individual names from an import_list or aliased_import node."""
    names = []
    if hasattr(names_node, "children"):
        for child in names_node.children:
            ct = getattr(child, "type", None)
            if ct == "dotted_name" or ct == "identifier":
                text = _node_text(child, source)
                if text and text != ",":
                    names.append(text)
            elif ct == "aliased_import":
                # Handle 'foo as bar'
                for sub in child.children:
                    st = getattr(sub, "type", None)
                    if st in ("dotted_name", "identifier"):
                        names.append(_node_text(sub, source))
    return names


# Extract elements from AST: _extract_js_imports
def _extract_js_imports(node: Any, source: str, imports: list[dict[str, Any]]) -> None:
    """Extract JS/TS import/require statements."""
    extract_js_imports(node, source, imports)


def _node_text(node: Any, source: str) -> str:
    """Safely extract text from a Tree-sitter node."""
    try:
        start = node.start_byte
        end = node.end_byte
        if (
            start is not None
            and end is not None
            and start < end <= len(source.encode("utf-8", errors="replace"))
        ):
            return source.encode("utf-8", errors="replace")[start:end].decode(
                "utf-8", errors="replace"
            )
        return ""
    except Exception:
        return ""


def _extract_go_imports(node: Any, source: str, imports: list[dict[str, Any]]) -> None:
    """Extract Go import declarations.

    Handles:
        import "fmt"
        import . "pkg"
        import alias "pkg"
        import (
            "fmt"
            "os"
        )
    """
    node_type = getattr(node, "type", None)
    if node_type != "import_declaration":
        return

    specs: list[Any] = []
    for child in node.children:
        ct = getattr(child, "type", None)
        if ct == "import_spec":
            specs.append(child)
        elif ct == "import_spec_list":
            for sub in child.children:
                if getattr(sub, "type", None) == "import_spec":
                    specs.append(sub)

    for spec in specs:
        path = None
        for ch in spec.children:
            ct = getattr(ch, "type", None)
            if ct == "interpreted_string_literal":
                raw = _node_text(ch, source).strip('"')
                if raw.split("/")[-1] not in _GO_STD and raw not in _GO_STD:
                    path = raw
        if path:
            imports.append(
                {
                    "module_name": path,
                    "resolved_path": path + ".go" if not path.endswith(".go") else path,
                    "names": [],
                    "is_relative": path.startswith("./") or path.startswith("../"),
                    "language": "go",
                }
            )


def _extract_rust_imports(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Extract Rust use declarations.

    Handles:
        use std::collections::HashMap;
        use crate::module::Item;
        use super::sibling;
        use mod::{Item1, Item2};
    """
    node_type = getattr(node, "type", None)
    if node_type != "use_declaration":
        return

    raw = _node_text(node, source)
    path = _parse_rust_use_path(raw)
    if not path:
        return

    root_crate = path.split("::")[0]
    if root_crate in _RUST_STD_CRATES:
        return

    is_local = root_crate in ("crate", "super", "self")
    imports.append(
        {
            "module_name": path,
            "resolved_path": path.replace("::", "/"),
            "names": [],
            "is_relative": is_local,
            "language": "rust",
        }
    )


def _parse_rust_use_path(raw: str) -> str | None:
    """Parse the module path from a Rust use statement."""
    stripped = raw.strip()
    if stripped.startswith("use "):
        stripped = stripped[4:]
    stripped = stripped.rstrip(";").strip()

    if "{" in stripped:
        stripped = stripped[: stripped.index("{")].strip()
        if stripped.endswith("::"):
            stripped = stripped[:-2]
    if not stripped:
        return None

    for prefix in ("crate::", "super::", "self::"):
        if stripped.startswith(prefix):
            return stripped

    parts = stripped.split("::")
    if len(parts) >= 1 and parts[0].isidentifier():
        return stripped
    return None


def _extract_cpp_imports(node: Any, source: str, imports: list[dict[str, Any]]) -> None:
    """Extract C/C++ #include directives.

    Handles:
        #include <stdio.h>
        #include "myheader.h"
        #include <vector>
    """
    node_type = getattr(node, "type", None)
    if node_type != "preproc_include":
        return

    for child in node.children:
        ct = getattr(child, "type", None)
        if ct == "string_literal":
            raw = _node_text(child, source).strip('"')
            if raw:
                imports.append(
                    {
                        "module_name": raw,
                        "resolved_path": raw,
                        "names": [],
                        "is_relative": True,
                        "language": "cpp",
                    }
                )
                return
        if ct == "system_lib_string":
            raw = _node_text(child, source).strip("<>")
            if raw:
                imports.append(
                    {
                        "module_name": raw,
                        "resolved_path": raw,
                        "names": [],
                        "is_relative": False,
                        "language": "cpp",
                    }
                )
                return


def _extract_java_imports(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Extract Java import declarations.

    Handles:
        import java.util.List;
        import static org.junit.Assert.*;
        import com.example.MyClass;
    """
    node_type = getattr(node, "type", None)
    if node_type != "import_declaration":
        return

    raw = _node_text(node, source).strip()
    if not raw.startswith("import"):
        return

    path = raw
    path = path.rstrip(";").strip()
    if path.startswith("import static "):
        path = path[len("import static ") :]
    elif path.startswith("import "):
        path = path[len("import ") :]

    path = path.strip()
    if not path:
        return

    if path.endswith(".*"):
        path = path[:-2]

    root_pkg = path.split(".")[0]
    _JAVA_STD_ROOTS = {
        "java",
        "javax",
        "sun",
        "com.sun",
        "org.w3c",
        "org.xml",
        "org.ietf",
        "org.omg",
    }
    if any(root_pkg == r or path.startswith(r + ".") for r in _JAVA_STD_ROOTS):
        return

    imports.append(
        {
            "module_name": path,
            "resolved_path": path.replace(".", "/") + ".java",
            "names": [],
            "is_relative": False,
            "language": "java",
        }
    )


def _extract_csharp_imports(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Extract C# using directives.

    Handles:
        using System;
        using MyApp.Services;
        using static System.Math;
    """
    node_type = getattr(node, "type", None)
    if node_type != "using_directive":
        return

    name_parts: list[str] = []
    for child in node.children:
        ct = getattr(child, "type", None)
        if ct == "identifier":
            name_parts.append(_node_text(child, source))
        elif ct == "qualified_name":
            for sub in child.children:
                st = getattr(sub, "type", None)
                if st == "identifier":
                    name_parts.append(_node_text(sub, source))

    if not name_parts:
        return

    namespace = ".".join(name_parts)
    root = name_parts[0]
    if root in _CSHARP_STD_NAMESPACES or namespace in _CSHARP_STD_NAMESPACES:
        return

    imports.append(
        {
            "module_name": namespace,
            "resolved_path": namespace.replace(".", "/") + ".cs",
            "names": [],
            "is_relative": False,
            "language": "csharp",
        }
    )


def _extract_kotlin_imports(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Extract Kotlin import declarations.

    Handles:
        import kotlin.collections.List
        import com.example.app.Data
        import com.example.utils.*
    """
    node_type = getattr(node, "type", None)
    if node_type != "import":
        return

    raw = _node_text(node, source).strip()
    if not raw.startswith("import "):
        return

    path = raw[len("import ") :].strip().rstrip(";")
    if path.endswith(".*"):
        path = path[:-2]

    path = path.strip()
    if not path:
        return

    root = path.split(".")[0]
    if root in _KOTLIN_STD_ROOTS:
        return

    imports.append(
        {
            "module_name": path,
            "resolved_path": path.replace(".", "/") + ".kt",
            "names": [],
            "is_relative": False,
            "language": "kotlin",
        }
    )


def _extract_swift_imports(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Extract Swift import declarations.

    Handles:
        import Foundation
        import MyFramework
    """
    node_type = getattr(node, "type", None)
    if node_type != "import_declaration":
        return

    for child in node.children:
        ct = getattr(child, "type", None)
        if ct == "identifier":
            module = _node_text(child, source)
            if module in _SWIFT_STD_MODULES:
                return
            imports.append(
                {
                    "module_name": module,
                    "resolved_path": module,
                    "names": [],
                    "is_relative": False,
                    "language": "swift",
                }
            )
            return


def _extract_ruby_imports(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Extract Ruby require/require_relative calls.

    Handles:
        require 'json'
        require_relative 'my_lib'
    """
    node_type = getattr(node, "type", None)
    if node_type != "call":
        return

    func = (
        node.child_by_field_name("function")
        if hasattr(node, "child_by_field_name")
        else None
    )
    if not func:
        return

    func_name = _node_text(func, source)
    is_relative = func_name == "require_relative"
    if func_name not in ("require", "require_relative"):
        return

    args_node = (
        node.child_by_field_name("arguments")
        if hasattr(node, "child_by_field_name")
        else None
    )
    if not args_node or not hasattr(args_node, "children"):
        return

    for child in args_node.children:
        ct = getattr(child, "type", None)
        if ct in ("string", "string_content"):
            raw = _node_text(child, source).strip("'\"")
            if func_name == "require" and raw in _RUBY_STDLIB:
                return
            if raw:
                resolved = raw
                if not resolved.endswith(".rb"):
                    resolved = raw + ".rb"
                imports.append(
                    {
                        "module_name": raw,
                        "resolved_path": resolved,
                        "names": [],
                        "is_relative": is_relative,
                        "language": "ruby",
                    }
                )
                return


def _extract_php_imports(node: Any, source: str, imports: list[dict[str, Any]]) -> None:
    """Extract PHP use declarations (namespace imports).

    Handles:
        use App\\Services\\UserService;
        use function App\\Utils\\helper;
        use App\\Models\\User as UserModel;
    """
    node_type = getattr(node, "type", None)
    if node_type != "namespace_use_declaration":
        return

    raw = _node_text(node, source).strip()
    if not raw.startswith("use "):
        return

    path = raw[len("use ") :].strip().rstrip(";")

    if path.startswith("function "):
        path = path[len("function ") :].strip()
    elif path.startswith("const "):
        path = path[len("const ") :].strip()

    if " as " in path:
        path = path[: path.index(" as ")].strip()

    path = path.strip()
    if not path:
        return

    root = path.split("\\")[0]
    _PHP_STD_ROOTS = {"PHP", "php"}
    if root in _PHP_STD_ROOTS:
        return

    imports.append(
        {
            "module_name": path.replace("\\", "/"),
            "resolved_path": path.replace("\\", "/") + ".php",
            "names": [],
            "is_relative": False,
            "language": "php",
        }
    )
