"""Rust import extractor."""

from typing import Any

from ._shared import _node_text

_RUST_STD_CRATES = {
    "std",
    "core",
    "alloc",
    "proc_macro",
    "test",
}


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
