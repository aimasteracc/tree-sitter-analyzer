"""Go edge extractor — import-based dependency analysis."""
from __future__ import annotations

import re

from .base import EdgeExtractor

# Go stdlib packages (common ones)
_STDLIB_PACKAGES: frozenset[str] = frozenset(
    {
        "fmt", "os", "io", "strings", "strconv", "math", "time",
        "net", "net/http", "net/url", "encoding/json", "encoding/xml",
        "encoding/csv", "context", "sync", "errors", "log", "path",
        "filepath", "bufio", "bytes", "regexp", "sort", "testing",
        "runtime", "reflect", "unicode", "crypto", "hash", "database",
        "html", "text", "archive", "compress", "debug", "mime",
        "syscall", "unsafe", "builtin", "container", "crypto/md5",
        "crypto/sha256", "crypto/sha512", "crypto/rand",
    }
)


def _is_stdlib(import_path: str) -> bool:
    """Check if a Go import path is from the standard library."""
    top = import_path.split("/")[0]
    return top in _STDLIB_PACKAGES or "." not in import_path


class GoEdgeExtractor(EdgeExtractor):
    """Go: extract import-based dependencies, filtering stdlib."""

    def extract(
        self,
        source: str,
        src_name: str,
        project_root: str,
    ) -> list[tuple[str, str]]:
        edges: list[tuple[str, str]] = []

        # Single imports: import "path"
        for m in re.finditer(r"import\s+[\"\`]([^\"\`]+)[\"\`]", source):
            imp_path = m.group(1)
            if not _is_stdlib(imp_path):
                pkg_name = imp_path.rsplit("/", 1)[-1]
                edges.append((src_name, pkg_name))

        # Multi-line imports: import ( ... )
        for block in re.finditer(r"import\s*\((.*?)\)", source, re.DOTALL):
            block_text = block.group(1)
            for m in re.finditer(r"[\"\`]([^\"\`]+)[\"\`]", block_text):
                imp_path = m.group(1)
                if not _is_stdlib(imp_path):
                    pkg_name = imp_path.rsplit("/", 1)[-1]
                    edges.append((src_name, pkg_name))

        # Aliased imports: import alias "path"
        for m in re.finditer(r"import\s+(\w+)\s+[\"\`]([^\"\`]+)[\"\`]", source):
            alias = m.group(1)
            imp_path = m.group(2)
            if not _is_stdlib(imp_path):
                edges.append((src_name, alias))

        return edges
