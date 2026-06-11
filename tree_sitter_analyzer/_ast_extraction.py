"""AST symbol-extraction helpers for ASTCache.

These module-level functions are isolated here so that:
  1. ast_cache.py stays under the 500-line limit
  2. _worker_index_file is picklable by multiprocessing.Pool without
     pulling in the entire ASTCache class and its imports
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from typing import Any

from .constants import EXCLUDE_DIRS
from .core.parser import Parser

# ---------------------------------------------------------------------------
# FTS5 probe
# ---------------------------------------------------------------------------


def _has_fts5(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute(
            "SELECT fts5 FROM pragma_compile_options WHERE fts5 = 'ENABLE_FTS5'"
        )
        return True
    except sqlite3.OperationalError:
        try:
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
            conn.execute("DROP TABLE IF EXISTS _fts5_probe")
            return True
        except sqlite3.OperationalError:
            return False


# ---------------------------------------------------------------------------
# File-walk constants
# ---------------------------------------------------------------------------

# Shared exclude set (incl. C#/Java/Rust/Go build-artifact dirs) — see
# constants.EXCLUDE_DIRS. Indexing must skip bin/obj/packages/target/etc or
# `index full` hangs on compiled-language projects.
_EXCLUDE_DIRS = EXCLUDE_DIRS


# ---------------------------------------------------------------------------
# Multiprocessing worker — must stay at module level so it is picklable
# ---------------------------------------------------------------------------

_worker_parser: Parser | None = None


def _init_worker_parser() -> None:
    global _worker_parser
    _worker_parser = Parser()


def _worker_index_file(args: tuple[str, str, str]) -> dict[str, Any]:
    """Worker used by ``ASTCache._index_parallel`` via a process pool.

    Must be module-level so pickle can resolve it across spawn.
    Returns a dict with status/symbols/imports/structure/call_edges.
    Tree-sitter ``Tree`` objects are NEVER returned — they are C objects
    that cannot be pickled; the worker discards them after extraction.
    """
    global _worker_parser
    abs_path, project_root, language = args
    rel_path = os.path.relpath(abs_path, project_root).replace("\\", "/")
    try:
        stat = os.stat(abs_path)
        with open(abs_path, encoding="utf-8", errors="replace") as f:
            source_code = f.read()
    except OSError as exc:
        return {
            "status": "io_error",
            "rel_path": rel_path,
            "abs_path": abs_path,
            "reason": str(exc),
        }
    if _worker_parser is None:
        _worker_parser = Parser()
    result = _worker_parser.parse_file(abs_path, language)
    if not result.success:
        return {
            "status": "parse_failed",
            "rel_path": rel_path,
            "abs_path": abs_path,
            "reason": result.error_message or "parse failed",
        }
    symbols = _extract_symbols(result.tree, source_code, language)
    imports = _extract_imports(symbols)
    structure = _extract_structure(symbols)
    call_edges = _extract_call_edges(result.tree, source_code, language, symbols)
    return {
        "status": "ok",
        "rel_path": rel_path,
        "abs_path": abs_path,
        "language": language,
        "content_hash": _content_hash(source_code),
        "mtime_ns": int(stat.st_mtime_ns),
        "file_size": int(stat.st_size),
        "symbols_count": len(symbols.get("symbols", [])),
        "symbols_json": json.dumps(symbols, ensure_ascii=False),
        "imports_json": json.dumps(imports, ensure_ascii=False),
        "structure_json": json.dumps(structure, ensure_ascii=False),
        "call_edges_json": json.dumps(call_edges, ensure_ascii=False),
        "symbol_rows": [
            (
                sym.get("name", sym.get("text", "")),
                sym.get("kind", "unknown"),
                sym.get("line", 0),
                sym.get("end_line", 0),
            )
            for sym in symbols.get("symbols", [])
        ],
    }


# ---------------------------------------------------------------------------
# Content hashing
# ---------------------------------------------------------------------------


def _content_hash(source: str | bytes) -> str:
    if isinstance(source, str):
        source = source.encode("utf-8", errors="replace")
    return hashlib.sha256(source).hexdigest()


# ---------------------------------------------------------------------------
# Symbol extraction — tree-walker + node-type sets
# ---------------------------------------------------------------------------

_FUNCTION_LIKE = frozenset(
    {
        "function_definition",
        "function_declaration",
        "method_definition",
        "arrow_function",
        "generator_function_declaration",
        "function_item",
        "method_declaration",
        "constructor_declaration",
        "lambda_expression",
        "anonymous_function",
        "class_method",
        "member_function",
        "function_declarator",
        "declaration",
        "init_declarator",
    }
)

_CLASS_LIKE = frozenset(
    {
        "class_definition",
        "class_declaration",
        "class",
        "interface_declaration",
        "struct_item",
        "enum_declaration",
        "enum",
        "trait_declaration",
        "impl_item",
        "struct_declaration",
        "type_declaration",
    }
)

_IMPORT_LIKE = frozenset(
    {
        "import_statement",
        "import_from_statement",
        "import_declaration",
        "require_statement",
        "use_declaration",
        "extern_crate_item",
        "package_declaration",
        "include_directive",
    }
)

_VAR_DECL_LIKE = frozenset(
    {
        "variable_declarator",
        "assignment_expression",
        "lexical_declaration",
        "variable_declaration",
        "const_declaration",
        "let_declaration",
    }
)

_COMPLEXITY_NODE_TYPES: dict[str, set[str]] = {
    "python": {
        "if_statement",
        "elif_clause",
        "for_statement",
        "while_statement",
        "except_clause",
        "boolean_operator",
        "conditional_expression",
        "list_comprehension",
        "set_comprehension",
        "dict_comprehension",
        "generator_expression",
        "match_statement",
        "case_clause",
    },
    "javascript": {
        "if_statement",
        "else_clause",
        "for_statement",
        "for_in_statement",
        "for_of_statement",
        "while_statement",
        "do_statement",
        "catch_clause",
        "ternary_expression",
        "switch_case",
        "switch_default",
        "logical_expression",
        "conditional_expression",
    },
    "typescript": {
        "if_statement",
        "else_clause",
        "for_statement",
        "for_in_statement",
        "for_of_statement",
        "while_statement",
        "do_statement",
        "catch_clause",
        "ternary_expression",
        "switch_case",
        "switch_default",
        "logical_expression",
        "conditional_expression",
    },
    "java": {
        "if_statement",
        "else_clause",
        "for_statement",
        "enhanced_for_statement",
        "while_statement",
        "do_statement",
        "catch_clause",
        "ternary_expression",
        "switch_block_statement_group",
        "logical_expression",
        "conditional_expression",
    },
    "go": {
        "if_statement",
        "else_clause",
        "for_statement",
        "expression_switch_case",
        "type_switch_case",
        "select_case",
        "binary_expression",
    },
    "rust": {
        "if_expression",
        "else_clause",
        "for_expression",
        "while_expression",
        "loop_expression",
        "match_arm",
        "binary_expression",
    },
    "c": {
        "if_statement",
        "else_clause",
        "for_statement",
        "while_statement",
        "do_statement",
        "switch_case",
        "binary_expression",
        "conditional_expression",
    },
    "cpp": {
        "if_statement",
        "else_clause",
        "for_statement",
        "while_statement",
        "do_statement",
        "switch_case",
        "binary_expression",
        "conditional_expression",
        "range_based_for_statement",
        "catch_clause",
    },
}


def _node_text(node: Any, source: str) -> str:
    """Extract the source text of a tree-sitter node.

    🚨 BUG history: tree-sitter exposes ``start_byte`` / ``end_byte`` as
    UTF-8 BYTE offsets. The old implementation sliced ``source`` (a
    ``str``) using those byte values, which is correct for pure-ASCII
    files but silently shifts by N chars after each multi-byte glyph.

    Fix: prefer ``node.text`` (returned as ``bytes`` by tree-sitter, the
    canonical source-of-truth). Fall back to slicing the encoded source
    so legacy callers still work when ``node.text`` is unavailable.
    """
    if node is None:
        return ""
    text_attr = getattr(node, "text", None)
    if isinstance(text_attr, bytes):
        try:
            return text_attr.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            return ""
    if isinstance(text_attr, str):
        return text_attr
    try:
        return source.encode("utf-8")[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )
    except (IndexError, TypeError, UnicodeDecodeError):
        return ""


def _count_nodes(node: Any) -> int:
    count = 1
    for child in node.children:
        count += _count_nodes(child)
    return count


def _count_decision_points(node: Any, language: str) -> dict[str, int]:
    lang = language.lower()
    if lang in ("tsx", "jsx"):
        lang = "typescript"
    types = _COMPLEXITY_NODE_TYPES.get(lang)
    if not types:
        return {}
    counts: dict[str, int] = {}
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type in types:
            counts[current.type] = counts.get(current.type, 0) + 1
        for child in current.children:
            stack.append(child)
    return counts


def _find_parent_class(node: Any, source: str) -> str | None:
    parent = node.parent
    while parent:
        if parent.type in _CLASS_LIKE:
            name_node = parent.child_by_field_name("name")
            if name_node:
                return _node_text(name_node, source)
        parent = parent.parent
    return None


def _extract_parent_classes(node: Any, source: str, language: str) -> list[str]:
    """Extract base class names from a class definition node."""
    parents: list[str] = []
    try:
        if language == "python":
            parents.extend(
                _node_text(arg, source)
                for child in node.children
                if child.type == "argument_list"
                for arg in child.children
                if arg.type in ("identifier", "attribute", "type")
            )
        elif language in ("javascript", "typescript"):
            parents.extend(
                _node_text(hc, source)
                for child in node.children
                if child.type == "class_heritage"
                for hc in child.children
                if hc.type in ("identifier", "member_expression")
            )
        elif language == "java":
            parents.extend(
                _node_text(sc, source)
                for child in node.children
                if child.type == "superclass"
                for sc in child.children
                if sc.type == "type_identifier"
            )
            parents.extend(
                _node_text(tc, source)
                for child in node.children
                if child.type == "super_interfaces"
                for si in child.children
                if si.type == "type_list"
                for tc in si.children
                if tc.type == "type_identifier"
            )
        elif language in ("c", "cpp"):
            parents.extend(
                _node_text(bc, source)
                for child in node.children
                if child.type == "base_class_clause"
                for bc in child.children
                if bc.type in ("type_identifier", "qualified_identifier")
            )
    except Exception:  # nosec B110
        pass
    return parents


def _c_function_def_name(node: Any, source: str) -> str | None:
    """Recover the name of a C ``function_definition`` node.

    A tree-sitter C ``function_definition`` does NOT expose a ``name`` field —
    the identifier lives under its ``function_declarator``, which may itself be
    wrapped in one or more ``pointer_declarator`` / ``parenthesized_declarator``
    layers. For a plain pointer-returning function (``void *malloc(...)``) one
    ``pointer_declarator`` wraps the ``function_declarator``. For a function that
    *returns a function pointer* (``int (*factory(void))(int)``) the name lives
    in an INNER ``function_declarator`` nested inside a ``parenthesized_declarator``
    — so we must keep descending past the outermost ``function_declarator`` until
    we reach the identifier itself. Return the innermost declarator identifier
    text, or ``None`` when it cannot be recovered.

    This is what lets C free functions reach ``ast_symbol_rows`` so the synapse
    C resolver's ownership gate (``_project_owns``) sees project-defined libc
    names (e.g. a custom ``malloc``) and does NOT misclassify them as ``stdlib``.
    """
    return _c_declarator_name(node.child_by_field_name("declarator"), source, 0)


# Declarator wrappers a C function name can be nested under, ordered so the
# common cases stay shallow. ``parenthesized_declarator`` does NOT expose a
# ``declarator`` field, so it is handled by scanning children explicitly.
_C_DECLARATOR_WRAPPERS = (
    "function_declarator",
    "pointer_declarator",
    "array_declarator",
)


def _c_declarator_name(declarator: Any, source: str, depth: int) -> str | None:
    """Descend a C declarator chain to its innermost identifier.

    Handles pointer / array / function declarator wrappers (which expose a
    ``declarator`` field) and ``parenthesized_declarator`` (which does not — its
    inner declarator is an unnamed child). Bounded to avoid pathological depth.
    """
    if declarator is None or depth > 16:
        return None
    dtype = declarator.type
    if dtype in ("identifier", "field_identifier", "type_identifier"):
        text = _node_text(declarator, source)
        return text or None
    if dtype == "parenthesized_declarator":
        for child in declarator.children:
            if child.type in _C_DECLARATOR_WRAPPERS or child.type.endswith(
                "identifier"
            ):
                name = _c_declarator_name(child, source, depth + 1)
                if name is not None:
                    return name
        return None
    if dtype in _C_DECLARATOR_WRAPPERS:
        return _c_declarator_name(
            declarator.child_by_field_name("declarator"), source, depth + 1
        )
    return None


def _walk_for_symbols(
    node: Any,
    source: str,
    symbols: list[dict[str, Any]],
    language: str,
    depth: int = 0,
) -> None:
    if depth > 20:
        return
    node_type = node.type
    name_node = node.child_by_field_name("name")
    # C ``function_definition`` nodes carry their identifier under
    # ``function_declarator`` (no ``name`` field), so recover it explicitly —
    # otherwise ordinary C free functions never reach ``ast_symbol_rows`` and the
    # synapse C resolver's project-ownership gate cannot shadow the libc tier.
    func_name: str | None = None
    if node_type in _FUNCTION_LIKE:
        if name_node is not None:
            func_name = _node_text(name_node, source)
        elif node_type == "function_definition" and language == "c":
            func_name = _c_function_def_name(node, source)
    if func_name is not None:
        name = func_name
        params_node = node.child_by_field_name("parameters")
        params = _node_text(params_node, source) if params_node else ""
        dp = _count_decision_points(node, language)
        sym: dict[str, Any] = {
            "kind": "function",
            "name": name,
            "line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "params": params,
            "language": language,
        }
        if dp:
            sym["decision_points"] = dp
        parent_cls = _find_parent_class(node, source)
        if parent_cls:
            sym["kind"] = "method"
            sym["class"] = parent_cls
        symbols.append(sym)
    elif node_type in _CLASS_LIKE and name_node is not None:
        name = _node_text(name_node, source)
        parents = _extract_parent_classes(node, source, language)
        cls_sym: dict[str, Any] = {
            "kind": "class",
            "name": name,
            "line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "language": language,
        }
        if parents:
            cls_sym["parents"] = parents
        symbols.append(cls_sym)
    elif node_type in _IMPORT_LIKE:
        symbols.append(
            {
                "kind": "import",
                "text": _node_text(node, source),
                "line": node.start_point[0] + 1,
                "language": language,
            }
        )
    elif node_type in _VAR_DECL_LIKE and name_node is not None:
        name = _node_text(name_node, source)
        if not name.startswith("_") or depth < 3:
            symbols.append(
                {
                    "kind": "variable",
                    "name": name,
                    "line": node.start_point[0] + 1,
                    "language": language,
                }
            )
    for child in node.children:
        _walk_for_symbols(child, source, symbols, language, depth + 1)


def _extract_symbols(tree: Any, source_code: str, language: str) -> dict[str, Any]:
    symbols: list[dict[str, Any]] = []
    if tree is None:
        return {"symbols": symbols, "node_count": 0}
    root = tree.root_node
    _walk_for_symbols(root, source_code, symbols, language)
    return {"symbols": symbols, "node_count": _count_nodes(root)}


def _extract_imports(symbols: dict[str, Any]) -> list[str]:
    return [s["text"] for s in symbols.get("symbols", []) if s.get("kind") == "import"]


def _extract_structure(symbols: dict[str, Any]) -> dict[str, Any]:
    functions = []
    classes = []
    for s in symbols.get("symbols", []):
        if s["kind"] in ("function", "method"):
            functions.append({"name": s["name"], "line": s["line"]})
        elif s["kind"] == "class":
            classes.append({"name": s["name"], "line": s["line"]})
    return {"functions": functions, "classes": classes}


def _extract_call_edges(
    tree: Any, source_code: str, language: str, symbols: dict[str, Any]
) -> list[dict[str, Any]]:
    """Extract call edges from the AST using shared function-call helpers."""
    if tree is None:
        return []
    from .function_extraction import walk_tree

    definitions, calls = walk_tree(tree.root_node, source_code, language)

    file_funcs: dict[str, tuple[int, int]] = {}
    for d in definitions:
        file_funcs[d["name"]] = (d["start_line"], d.get("end_line", d["start_line"]))

    edges: list[dict[str, Any]] = []
    for call in calls:
        call_line = call["line"]
        caller_name = ""
        caller_line = 0
        best_range = -1
        for fname, (start, end) in file_funcs.items():
            if start <= call_line <= end:
                span = end - start
                # Pick the innermost (narrowest) enclosing function.
                # Nested defs share the same call line but the inner has a
                # smaller span; without this the outer always wins because
                # dict iteration order is outer-first (issue #452).
                if best_range < 0 or span < best_range:
                    best_range = span
                    caller_name = fname
                    caller_line = start
        callee_name = call.get("name", "")
        callee_full = call.get("full_name", callee_name)
        callee_line = call_line
        edges.append(
            {
                "caller_name": caller_name,
                "caller_line": caller_line,
                "callee_name": callee_name,
                "callee_full": callee_full,
                "callee_line": callee_line,
            }
        )
    return edges
