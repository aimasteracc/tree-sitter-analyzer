"""Go import extractor."""

from typing import Any

from ._shared import _node_text

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


def _parse_go_spec(spec: Any, source: str) -> dict[str, Any] | None:
    """Return import dict from a single Go import_spec node, or None to skip."""
    path = None
    for ch in spec.children:
        if getattr(ch, "type", None) != "interpreted_string_literal":
            continue
        raw = _node_text(ch, source).strip('"')
        last_part = raw.split("/")[-1]
        if last_part not in _GO_STD and raw not in _GO_STD:
            path = raw
    if path is None:
        return None
    resolved = path if path.endswith(".go") else path + ".go"
    is_rel = path.startswith("./") or path.startswith("../")
    return {
        "module_name": path,
        "resolved_path": resolved,
        "names": [],
        "is_relative": is_rel,
        "language": "go",
    }


def _collect_go_specs(child: Any) -> list[Any]:
    """Collect import_spec children from an import_spec_list node."""
    return [
        sub for sub in child.children if getattr(sub, "type", None) == "import_spec"
    ]


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
            specs.extend(_collect_go_specs(child))

    for spec in specs:
        entry = _parse_go_spec(spec, source)
        if entry is not None:
            imports.append(entry)
