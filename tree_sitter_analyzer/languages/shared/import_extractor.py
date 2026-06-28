"""Shared import extraction utilities for language plugins.

Provides ImportRecord and three extraction functions that handle the three
most common import patterns across languages:
  - Qualified: ``import a.b.c`` / ``import java.util.List``
  - From-import: ``from a.b import c`` / ``import { X } from "m"``
  - Namespace/alias: ``use std::collections::HashMap`` / ``import X as Y``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ImportRecord:
    """A normalized import extracted from an AST node.

    Attributes:
        module: The imported module/package path (e.g. ``"os.path"``).
        names: The specific names imported from the module.
            Empty list for whole-module imports (``import os``).
        alias: An optional alias for the import (``import numpy as np`` → ``"np"``).
        raw_text: The verbatim source text of the import statement.
        line: 1-indexed source line where the import appears.
    """

    module: str
    names: list[str] = field(default_factory=list)
    alias: str = ""
    raw_text: str = ""
    line: int = 0
    is_wildcard: bool = False


def extract_qualified_import(node: Any, source_bytes: bytes) -> ImportRecord | None:
    """Extract a whole-module (qualified) import statement.

    Handles patterns like:
    - Python: ``import os``, ``import os.path``
    - Java: ``import java.util.List;``
    - Scala: ``import scala.collection.mutable``

    The node is expected to expose a ``name`` field or contain a dotted
    identifier as its first meaningful child. Returns None if extraction
    fails.

    Args:
        node: A tree-sitter import-statement node.
        source_bytes: The full source file as UTF-8-encoded bytes.

    Returns:
        An ImportRecord with ``module`` set and empty ``names`` list,
        or None when the node does not carry extractable module information.
    """
    from .traversal import node_range, node_text

    try:
        start_line, _ = node_range(node)
        raw = node_text(node, source_bytes)

        # Prefer the ``name`` field (Python, Java, Scala grammars expose it)
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            module = node_text(name_node, source_bytes)
            return ImportRecord(
                module=module,
                raw_text=raw,
                line=start_line,
            )

        # Fallback: use the full node text, stripping the leading "import" keyword
        text = raw.strip()
        if text.lower().startswith("import "):
            module = text[7:].rstrip(";").strip()
        else:
            module = text
        return ImportRecord(module=module, raw_text=raw, line=start_line)
    except Exception:
        return None


def extract_from_import(node: Any, source_bytes: bytes) -> ImportRecord | None:
    """Extract a from-import statement.

    Handles patterns like:
    - Python: ``from os.path import join, exists``
    - ES6/TypeScript: ``import { useState, useEffect } from "react"``
    - Rust: ``use std::io::{self, Write};``

    Returns None if extraction fails.

    Args:
        node: A tree-sitter from-import or named-import node.
        source_bytes: The full source file as UTF-8-encoded bytes.

    Returns:
        An ImportRecord with ``module`` and ``names`` populated,
        or None on failure.
    """
    from .traversal import node_range, node_text

    try:
        start_line, _ = node_range(node)
        raw = node_text(node, source_bytes)

        # Try ``module_name`` field (Python grammar)
        mod_node = node.child_by_field_name("module_name")
        if mod_node is None:
            # Try ``source`` field (TypeScript/JS grammar: import { X } from "y")
            mod_node = node.child_by_field_name("source")

        module = node_text(mod_node, source_bytes).strip("\"'") if mod_node else ""

        # Collect imported names from ``name`` field or named imports
        names: list[str] = []
        # Python: import_from_statement has ``name`` repeated fields
        for child in getattr(node, "children", []):
            if child.type in (
                "dotted_name",
                "aliased_import",
                "identifier",
                "import_specifier",
            ):
                name_text = node_text(child, source_bytes)
                if name_text and name_text not in ("from", "import", module):
                    names.append(name_text)

        return ImportRecord(
            module=module,
            names=names,
            raw_text=raw,
            line=start_line,
        )
    except Exception:
        return None


def extract_namespace_import(node: Any, source_bytes: bytes) -> ImportRecord | None:
    """Extract a namespace or aliased import statement.

    Handles patterns like:
    - Python: ``import numpy as np``
    - Java/Kotlin: ``import static org.junit.Assert.*``
    - Rust: ``use std::collections::HashMap;``
    - C#: ``using System.Collections.Generic;``

    Returns None if extraction fails.

    Args:
        node: A tree-sitter use/import declaration node.
        source_bytes: The full source file as UTF-8-encoded bytes.

    Returns:
        An ImportRecord with ``module`` and optionally ``alias`` set,
        or None on failure.
    """
    from .traversal import node_range, node_text

    try:
        start_line, _ = node_range(node)
        raw = node_text(node, source_bytes)

        # Rust: ``use_declaration`` has a single ``argument`` field
        arg_node = node.child_by_field_name("argument")
        if arg_node is not None:
            module = node_text(arg_node, source_bytes).rstrip(";").strip()
            return ImportRecord(module=module, raw_text=raw, line=start_line)

        # C#: ``using_directive`` — strip "using" keyword and semicolon
        text = raw.strip()
        if text.lower().startswith("using "):
            module = text[6:].rstrip(";").strip()
        elif text.lower().startswith("use "):
            module = text[4:].rstrip(";").strip()
        else:
            module = text

        # Check for "as" alias
        alias = ""
        if " as " in module:
            parts = module.rsplit(" as ", 1)
            module = parts[0].strip()
            alias = parts[1].strip()

        return ImportRecord(module=module, alias=alias, raw_text=raw, line=start_line)
    except Exception:
        return None
