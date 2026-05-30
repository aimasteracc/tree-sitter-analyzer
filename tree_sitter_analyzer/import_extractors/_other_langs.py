"""Import extractors for C#, Kotlin, Swift, Ruby, and PHP."""

from typing import Any

from ._shared import _node_text

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


def _csharp_qualified_name_parts(node: Any, source: str) -> list[str]:
    """Collect identifier parts from a C# qualified_name node."""
    parts = []
    for sub in node.children:
        if getattr(sub, "type", None) == "identifier":
            parts.append(_node_text(sub, source))
    return parts


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
            name_parts.extend(_csharp_qualified_name_parts(child, source))

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


def _ruby_call_function_name(node: Any, source: str) -> str | None:
    """Return the function-name text from a Ruby ``call`` node, or ``None``."""
    if not hasattr(node, "child_by_field_name"):
        return None
    func = node.child_by_field_name("function")
    if not func:
        return None
    return _node_text(func, source)


def _ruby_call_string_arg(node: Any, source: str) -> str | None:
    """Return the first ``string``/``string_content`` arg text (quotes stripped)."""
    if not hasattr(node, "child_by_field_name"):
        return None
    args_node = node.child_by_field_name("arguments")
    if not args_node or not hasattr(args_node, "children"):
        return None
    for child in args_node.children:
        ct = getattr(child, "type", None)
        if ct in ("string", "string_content"):
            raw = _node_text(child, source).strip("'\"")
            if raw:
                return raw
    return None


def _extract_ruby_imports(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Extract Ruby require/require_relative calls.

    Handles:
        require 'json'
        require_relative 'my_lib'
    """
    if getattr(node, "type", None) != "call":
        return

    func_name = _ruby_call_function_name(node, source)
    if func_name not in ("require", "require_relative"):
        return

    raw = _ruby_call_string_arg(node, source)
    if raw is None:
        return
    if func_name == "require" and raw in _RUBY_STDLIB:
        return

    resolved = raw if raw.endswith(".rb") else raw + ".rb"
    imports.append(
        {
            "module_name": raw,
            "resolved_path": resolved,
            "names": [],
            "is_relative": func_name == "require_relative",
            "language": "ruby",
        }
    )


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
