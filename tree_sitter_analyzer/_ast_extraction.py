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
import re
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
        # Issue #532: Ruby uses ``method`` / ``singleton_method`` node types;
        # without these, Ruby methods were invisible in symbols_json so the
        # class_inspect_tool showed 0 methods for every Ruby class.
        "method",
        "singleton_method",
    }
)

_ENUM_LIKE = frozenset(
    {
        "enum_declaration",
        "enum",
    }
)

_CLASS_LIKE = frozenset(
    {
        "class_definition",
        "class_declaration",
        "class",
        "interface_declaration",
        "struct_item",
        "trait_declaration",
        "impl_item",
        "struct_declaration",
        "type_declaration",
    }
    | _ENUM_LIKE
)

_SCALA_CLASS_LIKE = frozenset(
    {
        "object_definition",
        "trait_definition",
        "enum_definition",
        "given_definition",
        "type_definition",
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
        "variable_assignment",
    }
)

# Issue #610 — Python module-level constants. tree-sitter-python emits
# ``assignment`` nodes (with a ``left`` field, not ``name``), so they never
# matched _VAR_DECL_LIKE and were invisible to ast_symbol_rows. Scope rule
# (approved on #610): module-scope simple assignments whose target is
# const-style, annotated (``x: T = ...``), or a dunder (``^__\w+__$``) —
# emitted as kind="constant".
# Const-style name pattern used by the Go (#613) rule: requires ≥2 chars
# (``+``) to avoid capturing single-letter package-level vars like ``var F``.
_CONST_STYLE_NAME = re.compile(r"^_?[A-Z][A-Z0-9_]+$")
# Issue #793 — Python-only pattern: single-letter ALL_CAPS names (N, A, X …)
# are valid Python constants (e.g. ``N = 100``) and must be captured.
# Uses ``*`` (zero-or-more) so a single uppercase letter matches.
_PY_CONST_STYLE_NAME = re.compile(r"^_?[A-Z][A-Z0-9_]*$")
_PY_DUNDER_NAME = re.compile(r"^__\w+__$")

# Node types that open a non-module scope: an ``assignment`` nested under any
# of these is a class attribute or function local, not a module constant.
_PY_SCOPE_BODY_NODES = frozenset({"function_definition", "class_definition"})

# Issue #613 — Go package-level constants, same shape as #610. tree-sitter-go
# puts names on ``const_spec``/``var_spec`` children (repeated ``name`` field);
# the const_declaration/var_declaration wrappers carry no ``name`` field, so
# they never produced rows via _VAR_DECL_LIKE.
_GO_CONST_LIKE = frozenset({"const_declaration", "var_declaration"})

# Nodes that open a function scope in Go: const/var declarations nested under
# any of these are locals, not package constants (Go analogue of
# _PY_SCOPE_BODY_NODES, feeding the same top-down ``enclosed`` flag).
_GO_SCOPE_BODY_NODES = frozenset(
    {"function_declaration", "method_declaration", "func_literal"}
)


def _go_package_constants(node: Any, source: str) -> list[dict[str, Any]]:
    """Return kind="constant" symbols for a package-scope Go const/var
    declaration, or [] when nothing matches the #613 scope rule.

    The caller guarantees package scope (no enclosing function body).
    Asymmetry (deliberate): every ``const`` spec name is captured — Go consts
    are constants by definition, the compiler enforces immutability, so no
    name-pattern gate is needed. A package-level ``var`` is mutable state, so
    var_spec names count only when const-style (the #612 pattern) — the
    author signalling a constant by convention (e.g. MAX_RETRIES). The blank
    identifier ``_`` is skipped — it is not a referenceable name.
    """
    require_const_style = node.type == "var_declaration"
    specs: list[Any] = []
    for child in node.children:
        if child.type in ("const_spec", "var_spec"):
            specs.append(child)
        elif child.type == "var_spec_list":
            specs.extend(c for c in child.children if c.type == "var_spec")
    out: list[dict[str, Any]] = []
    for spec in specs:
        for ident in spec.children_by_field_name("name"):
            if ident.type != "identifier":
                continue  # separator tokens can appear in the field list
            name = _node_text(ident, source)
            if name == "_":
                continue
            if require_const_style and not _CONST_STYLE_NAME.match(name):
                continue
            out.append(
                {
                    "kind": "constant",
                    "name": name,
                    "line": spec.start_point[0] + 1,
                    "end_line": spec.end_point[0] + 1,
                    "language": "go",
                }
            )
    return out


# Issue #613 — Rust const/static items, same shape as #610/#615. tree-sitter-
# rust emits ``const_item``/``static_item`` (with a ``name`` field), but
# neither type is in _VAR_DECL_LIKE (which carries Go's ``const_declaration``,
# not Rust's node names), so they never produced rows. ALL names are captured
# — Rust const/static are language-level constants/globals (rustc lints
# non_upper_case_globals), so no const-style name gate is needed; this mirrors
# the Go const reasoning. ``static mut`` counts too: still a named crate-level
# global. Associated consts in impl/trait bodies ARE captured (deliberate):
# they are compiler-enforced constants addressable as ``Type::CONST``, unlike
# the Python class attributes #612 excludes — and impl/trait bodies are
# ``declaration_list`` nodes, not function scopes, so the ``enclosed``
# mechanism keeps them naturally.
_RUST_CONST_LIKE = frozenset({"const_item", "static_item"})

# Nodes that open a function scope in Rust: const/static items nested under
# any of these are function-locals, not module constants (Rust analogue of
# _PY_SCOPE_BODY_NODES / _GO_SCOPE_BODY_NODES, feeding the same top-down
# ``enclosed`` flag). mod/impl/trait bodies are ``declaration_list`` — module
# scope — and deliberately absent.
_RUST_SCOPE_BODY_NODES = frozenset({"function_item", "closure_expression", "block"})

# Issue #624 — PHP const declarations, same shape as #610/#615/#618.
# tree-sitter-php emits ``const_declaration`` (the node type already sits in
# _VAR_DECL_LIKE via Go's grammar) but the names live on ``const_element``
# children which carry NO ``name`` field — the identifier is a bare ``name``
# child — so the _VAR_DECL_LIKE name gate never matched and no rows were
# produced. ALL names are captured — PHP ``const`` is compiler-enforced
# immutable, so no const-style name gate (mirrors the Go/Rust reasoning).
# Class/interface/trait/enum consts ARE captured (deliberate): addressable as
# ``Config::MAX_USERS`` like Rust associated consts; their bodies are
# declaration_list / enum_declaration_list nodes, not function scopes, so the
# ``enclosed`` mechanism keeps them naturally. ``define()`` calls are
# function_call_expression nodes — runtime registration whose name is a
# string argument, not a declaration — and stay out of scope.

# Nodes that open a function scope in PHP (PHP analogue of the other
# _*_SCOPE_BODY_NODES sets, feeding the same top-down ``enclosed`` flag).
# PHP has no legal function-scope const, but tree-sitter-php parses one
# permissively as const_declaration, so the gate is still required. Braced
# namespace bodies are ``compound_statement`` nodes — the gate keys on the
# function/closure declaration node types (not compound_statement) precisely
# so namespace-scope consts stay captured.
_PHP_SCOPE_BODY_NODES = frozenset(
    {
        "function_definition",
        "method_declaration",
        "anonymous_function",
        "arrow_function",
    }
)

# Issue #626 — JS/TS function-local variables were OVER-captured: every
# ``variable_declarator`` with a ``name`` field became a kind="variable" row
# regardless of scope, so function locals (``const id = req.params.id``)
# polluted FTS and symbol search (−57% JS / −54% TS variable rows on the
# in-repo corpus). Inverse of the constants family (#612/#615/#618/#625):
# the same language-gated top-down ``enclosed`` flag, used here to SKIP rows
# instead of adding them. Module/top-level declarators stay captured —
# const+let+var, NO const-style name gate (this is a contraction of the
# pre-existing kind="variable" contract, not a constants feature).
#
# ``statement_block`` is deliberately ABSENT: module-level ``if``/``try``
# bodies are statement_blocks outside any function node — including it would
# break the #612 guarantee that if/try-wrapped module declarators stay
# captured. TS namespace bodies (``internal_module`` / ``module`` /
# ``ambient_declaration``) are not function scopes either, so namespace-level
# declarators stay captured naturally (PHP #624 namespace precedent).
# ``function`` is the anonymous-function-expression node of older grammar
# versions; in current grammars it only matches the bare ``function`` keyword
# token, which is harmless (keyword tokens have no children).
_JSTS_SCOPE_BODY_NODES = frozenset(
    {
        "function_declaration",
        "function_expression",
        "function",
        "arrow_function",
        "method_definition",
        "generator_function",
        "generator_function_declaration",
        "class_static_block",
        # Declarations inside error-recovered regions have undecidable scope
        # (.tsx is parsed with the typescript grammar, so JSX can shatter
        # function bodies into ERROR nodes) — better unindexed than wrong
        # (Codex P2 on #629; defensive hardening, 4 JSX shapes probed clean).
        "ERROR",
    }
)

# Issue #626 (Java half) — same over-capture disease: every Java
# ``variable_declarator`` became a kind="variable" row, so method/ctor/
# lambda/initializer locals polluted FTS and symbol search (−69% Java
# variable rows on the in-repo corpus). Class fields and interface constants
# stay captured: they route ``class_body > field_declaration`` /
# ``interface_body > constant_declaration`` and NEVER through any node in
# this set — ``block`` is safe for Java because fields never sit inside a
# block node (live-parse verified), while the instance initializer is a bare
# ``block`` child of ``class_body``, which is exactly why ``block`` is here.
# ``constructor_declaration`` gates ctor locals (their body is a
# ``constructor_body``, not a ``block``); ``compact_constructor_declaration``
# covers record compact ctors; ``lambda_expression`` covers lambdas hanging
# off FIELD initializers (lambdas in methods are already inside the method).
# ``ERROR`` per the #629 hardening precedent: declarations inside
# error-recovered regions have undecidable scope — better unindexed than a
# lambda local masquerading as a field.
_JAVA_SCOPE_BODY_NODES = frozenset(
    {
        "method_declaration",
        "constructor_declaration",
        "compact_constructor_declaration",
        "lambda_expression",
        "static_initializer",
        "block",
        "ERROR",
    }
)

# Issue #628 (C#) — same over-capture disease as #626: every C#
# ``variable_declarator`` became a kind="variable" row, so method/ctor/
# dtor/local-fn/lambda/accessor/operator locals polluted FTS and symbol
# search. Class/interface/record fields (const, static readonly, plain)
# stay captured: they route ``declaration_list > field_declaration`` and
# NEVER through any node in this set (live-parse verified).
#
# Unlike Java, ``block`` is deliberately ABSENT: C# top-level statements
# (C# 9 top-level programs) put blocks at compilation-unit level
# (``block < if_statement < global_statement``), so a block-keyed set
# would drop if/try-wrapped top-level declarators and break the #612
# module-scope guarantee. Function-keying is complete anyway: every
# local's ancestry passes through one of these declaration nodes.
# ``accessor_declaration`` gates property/indexer/event get/set/init/
# add/remove bodies (their bodies are plain ``block``s);
# ``local_function_statement`` is itself redundant under a method but
# kept for explicitness (and gates top-level local functions);
# ``lambda_expression`` / ``anonymous_method_expression`` cover lambdas
# and ``delegate`` bodies hanging off FIELD initializers (lambdas in
# methods are already inside the method). ``ERROR`` per the #629
# hardening precedent: declarations inside error-recovered regions have
# undecidable scope — better unindexed than a local masquerading as a
# field.
_CSHARP_SCOPE_BODY_NODES = frozenset(
    {
        "method_declaration",
        "constructor_declaration",
        "destructor_declaration",
        "operator_declaration",
        "conversion_operator_declaration",
        "local_function_statement",
        "accessor_declaration",
        "lambda_expression",
        "anonymous_method_expression",
        "ERROR",
    }
)

# #961: Scala method bodies must mark their descendants as enclosed so a
# method-local ``given``/``type`` is NOT emitted as a top-level class-like
# symbol (mirrors the scala_plugin path, which ``continue``s instead of
# descending into ``function_definition``/``function_declaration``). The
# scope node itself is enough — gating on it makes the body container
# (``block`` / ``indented_block``) and everything below it enclosed.
_SCALA_SCOPE_BODY_NODES = frozenset(
    {
        "function_definition",
        "function_declaration",
    }
)


def _php_constants(node: Any, source: str) -> list[dict[str, Any]]:
    """Return kind="constant" symbols for a PHP const_declaration, one row
    per ``const_element`` (``const A = 1, B = 2;`` yields two rows).

    The caller guarantees the declaration is not enclosed in a function
    body (#624 scope rule).
    """
    out: list[dict[str, Any]] = []
    for child in node.children:
        if child.type != "const_element":
            continue
        name_node = next((c for c in child.children if c.type == "name"), None)
        if name_node is None:
            continue
        out.append(
            {
                "kind": "constant",
                "name": _node_text(name_node, source),
                "line": child.start_point[0] + 1,
                "end_line": child.end_point[0] + 1,
                "language": "php",
            }
        )
    return out


def _python_module_constant(node: Any, source: str) -> dict[str, Any] | None:
    """Return a kind="constant" symbol for a module-scope Python assignment,
    or None when the node does not match the #610 scope rule.

    The caller guarantees module scope (no enclosing function/class body);
    this helper checks target shape and naming/annotation rules only.
    """
    left = node.child_by_field_name("left")
    if left is None or left.type != "identifier":
        return None  # tuple/attribute/subscript targets are out of scope
    if node.child_by_field_name("right") is None:
        return None  # bare annotation (``x: int``) — not a definition site
    name = _node_text(left, source)
    annotated = node.child_by_field_name("type") is not None
    if not (
        annotated or _PY_CONST_STYLE_NAME.match(name) or _PY_DUNDER_NAME.match(name)
    ):
        return None
    return {
        "kind": "constant",
        "name": name,
        "line": node.start_point[0] + 1,
        "end_line": node.end_point[0] + 1,
        "language": "python",
    }


# Issue #614 — RFC-0016 prerequisite. symbols_json must carry enough text to
# build the embedding/BM25 input "{kind} {name}({params}) -> {return_type}\n
# {docstring}". Docstrings are much larger than names, so serialized values
# are capped at 500 chars (stated cap; index-size impact measured on #614).
_DOCSTRING_MAX_CHARS = 500


def _python_docstring(node: Any, source: str) -> str | None:
    """Return the PEP 257 docstring of a Python function/class node, or None.

    The first statement of the ``body`` block must be an expression statement
    whose sole expression is a string literal. Quote delimiters are excluded
    by reading the ``string_content`` children. Python-only this PR — other
    languages keep docs in comments, which need per-language helpers (#614
    follow-up). Result is stripped and capped at ``_DOCSTRING_MAX_CHARS``;
    whitespace-only docstrings yield None so absent stays absent.
    """
    body = node.child_by_field_name("body")
    if body is None or not body.named_children:
        return None
    first = body.named_children[0]
    if first.type != "expression_statement" or not first.named_children:
        return None
    string_node = first.named_children[0]
    if string_node.type == "string":
        string_parts = [string_node]
    elif string_node.type == "concatenated_string":
        # Adjacent literals ('a' 'b') fold into __doc__ — a legal PEP 257
        # docstring; tree-sitter wraps them in concatenated_string
        # (Codex P2 on #621).
        string_parts = [c for c in string_node.named_children if c.type == "string"]
    else:
        return None
    content = "".join(
        _node_text(child, source)
        for part in string_parts
        for child in part.children
        if child.type == "string_content"
    ).strip()
    if not content:
        return None
    return content[:_DOCSTRING_MAX_CHARS]


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
    """Count AST nodes iteratively to avoid RecursionError on deeply-nested trees."""
    count = 0
    stack = [node]
    while stack:
        current = stack.pop()
        count += 1
        for child in current.children:
            stack.append(child)
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
    """Walk up the parent chain to find the innermost enclosing class-like
    container, returning its name.

    Special cases:
    - ``impl_item`` (Rust): exposes the implemented type in the ``type``
      field (e.g. ``Container<T>`` or ``User``), NOT a ``name`` field.
      Strip any generic parameters so ``Container<T>`` → ``"Container"``.
    """
    parent = node.parent
    while parent:
        if parent.type in _CLASS_LIKE:
            if parent.type == "impl_item":
                # Rust impl block: the implemented type is in the ``type`` field.
                type_node = parent.child_by_field_name("type")
                if type_node is not None:
                    raw = _node_text(type_node, source)
                    # Strip generic parameters: "Container<T>" → "Container"
                    return raw.split("<")[0].strip() or None
            else:
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


def _bash_subscript_base(subscript: Any) -> Any:
    """Return the base ``variable_name`` node of a Bash ``subscript`` target.

    For ``arr[0]=x`` tree-sitter-bash nests the base variable under the
    subscript's ``name`` field (``arr``). Fall back to the first
    ``variable_name`` / ``word`` child if the field is absent.
    """
    base = subscript.child_by_field_name("name")
    if base is not None:
        return base
    for child in subscript.children:
        if child.type in ("variable_name", "word"):
            return child
    return None


def _scala_symbol_from_node(node: Any, source: str) -> dict[str, Any] | None:
    node_type = node.type
    if node_type not in _SCALA_CLASS_LIKE:
        return None
    name = _scala_symbol_name(node, source)
    if not name:
        return None
    return {
        "kind": "enum" if node_type == "enum_definition" else "class",
        "name": name,
        "line": node.start_point[0] + 1,
        "end_line": node.end_point[0] + 1,
        "language": "scala",
    }


def _scala_symbol_name(node: Any, source: str) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return _node_text(name_node, source)
    for child in node.children:
        if child.type in ("identifier", "type_identifier"):
            return _node_text(child, source)
    if node.type == "given_definition":
        type_name = _scala_given_type_text(node, source)
        if type_name:
            return f"given {type_name}"
        return f"anonymous_given_{node.start_point[0] + 1}"
    return None


def _scala_given_type_text(node: Any, source: str) -> str | None:
    for child in node.children:
        if child.type in (
            "generic_type",
            "type_identifier",
            "stable_type_identifier",
            "tuple_type",
            "function_type",
        ):
            return _node_text(child, source)
    return None


_WALK_MAX_DEPTH = (
    100  # #779: DoS protection — functions nested beyond this are dropped.
)


def _walk_for_symbols(
    node: Any,
    source: str,
    symbols: list[dict[str, Any]],
    language: str,
    depth: int = 0,
    enclosed: bool = False,
    _truncated_flag: list[bool] | None = None,
) -> None:
    """Walk the AST collecting symbol dicts.

    ``enclosed`` tracks (top-down, no parent walking) whether *node* sits
    inside a Python function/class body (#610), a Go function body (#613),
    a Rust function/closure body (#613), a PHP function/closure body
    (#624), a JS/TS function/method/static-block body (#626), a Java
    method/ctor/lambda/initializer body (#626 Java half), or a C#
    method/ctor/dtor/local-fn/lambda/accessor/operator body (#628) —
    module/package-constant capture must fire at top-level scope only,
    including ``if``/``try``-wrapped module-level assignments, and
    JS/TS/Java/C# function-local declarators must NOT produce
    kind="variable" rows.

    ``_truncated_flag`` is an optional single-element list.  When the depth
    guard fires the list is set to ``[True]`` so the caller can detect that
    deeply nested functions were silently dropped (#779).
    """
    if depth > _WALK_MAX_DEPTH:
        if _truncated_flag is not None:
            _truncated_flag[0] = True
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
        # #614: return_type where the grammar exposes the field (python/rust/
        # typescript use "return_type"; absent field → key absent, no noise).
        return_type_node = node.child_by_field_name("return_type")
        if return_type_node is not None:
            # TS/TSX expose a type_annotation node whose text is ": string" —
            # strip the annotation prefix so consumers compare bare types
            # (Codex P2 on #621; mirrors the TS signature helpers).
            sym["return_type"] = _node_text(return_type_node, source).lstrip(": ")
        if language == "python":
            doc = _python_docstring(node, source)
            if doc is not None:
                sym["docstring"] = doc
        parent_cls = _find_parent_class(node, source)
        if parent_cls:
            sym["kind"] = "method"
            sym["class"] = parent_cls
        symbols.append(sym)
    elif language == "scala" and node_type in _SCALA_CLASS_LIKE and not enclosed:
        # #961: ``not enclosed`` keeps a method-local ``given``/``type`` out of
        # the top-level symbol set (CLI/plugin already excludes it; the
        # ast_cache path must match — otherwise CLI vs MCP diverge).
        scala_sym = _scala_symbol_from_node(node, source)
        if scala_sym is not None:
            symbols.append(scala_sym)
    elif node_type in _CLASS_LIKE and name_node is not None:
        name = _node_text(name_node, source)
        parents = _extract_parent_classes(node, source, language)
        cls_sym: dict[str, Any] = {
            "kind": "enum" if node_type in _ENUM_LIKE else "class",
            "name": name,
            "line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "language": language,
        }
        if parents:
            cls_sym["parents"] = parents
        if language == "python":
            doc = _python_docstring(node, source)
            if doc is not None:
                cls_sym["docstring"] = doc
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
    elif (
        node_type in _VAR_DECL_LIKE
        and name_node is not None
        # #626/#628: JS/TS/Java/C# function-local declarators are not
        # cross-file symbols — skip them. The ast_cache path only ever
        # delivers the language ids "javascript"/"typescript"/"java"/
        # "csharp" for this family (.jsx → "javascript", .tsx →
        # "typescript", .java → "java", .cs → "csharp"), so gating on
        # these ids is complete.
        and not (
            language in ("javascript", "typescript", "java", "csharp") and enclosed
        )
        # #949 Codex P2: ``FOO=bar make`` makes tree-sitter-bash emit
        # ``FOO=bar`` as a variable_assignment *child of a command* node — a
        # transient per-command env override, not a script-level variable.
        # Skip those; only standalone assignments (parent is the
        # program/compound/list) are real symbols.
        and not (
            node_type == "variable_assignment"
            and node.parent is not None
            and node.parent.type == "command"
        )
    ):
        # Bash array/associative assignments (``arr[0]=x``) expose the target
        # as a ``subscript`` node, not a bare ``variable_name``. Unwrap to the
        # base variable so the symbol is the variable name, not ``arr[0]``.
        if name_node.type == "subscript":
            name_node = _bash_subscript_base(name_node)
        name = _node_text(name_node, source) if name_node is not None else ""
        if name and (not name.startswith("_") or depth < 3):
            symbols.append(
                {
                    "kind": "variable",
                    "name": name,
                    "line": node.start_point[0] + 1,
                    "language": language,
                }
            )
    elif node_type == "assignment" and language == "python" and not enclosed:
        const_sym = _python_module_constant(node, source)
        if const_sym is not None:
            symbols.append(const_sym)
    elif node_type in _GO_CONST_LIKE and language == "go" and not enclosed:
        symbols.extend(_go_package_constants(node, source))
    elif (
        node_type in _RUST_CONST_LIKE
        and language == "rust"
        and not enclosed
        and name_node is not None
        # `const _: usize = ...;` compile-time assertions: `_` is not a
        # referenceable symbol (Codex P2 on #618; mirrors the Go blank rule)
        and _node_text(name_node, source) != "_"
    ):
        symbols.append(
            {
                "kind": "constant",
                "name": _node_text(name_node, source),
                "line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "language": "rust",
            }
        )
    elif node_type == "const_declaration" and language == "php" and not enclosed:
        symbols.extend(_php_constants(node, source))
    # Language-gated: Rust needs "block" in its scope set (const-initializer
    # block expressions, Codex P2 on #618), but Python's if/try bodies are
    # also "block" nodes — a shared set would break the #612 guarantee that
    # if/try-wrapped module assignments stay captured.
    child_enclosed = enclosed or (
        (language == "python" and node_type in _PY_SCOPE_BODY_NODES)
        or (language == "go" and node_type in _GO_SCOPE_BODY_NODES)
        or (language == "rust" and node_type in _RUST_SCOPE_BODY_NODES)
        or (language == "php" and node_type in _PHP_SCOPE_BODY_NODES)
        or (
            language in ("javascript", "typescript")
            and node_type in _JSTS_SCOPE_BODY_NODES
        )
        or (language == "java" and node_type in _JAVA_SCOPE_BODY_NODES)
        or (language == "csharp" and node_type in _CSHARP_SCOPE_BODY_NODES)
        or (language == "scala" and node_type in _SCALA_SCOPE_BODY_NODES)
    )
    for child in node.children:
        _walk_for_symbols(
            child, source, symbols, language, depth + 1, child_enclosed, _truncated_flag
        )


def _extract_symbols(tree: Any, source_code: str, language: str) -> dict[str, Any]:
    symbols: list[dict[str, Any]] = []
    if tree is None:
        return {"symbols": symbols, "node_count": 0, "truncated_depth": False}
    root = tree.root_node
    truncated_flag: list[bool] = [False]
    _walk_for_symbols(
        root, source_code, symbols, language, _truncated_flag=truncated_flag
    )
    return {
        "symbols": symbols,
        "node_count": _count_nodes(root),
        "truncated_depth": truncated_flag[0],
    }


def _extract_imports(symbols: dict[str, Any]) -> list[str]:
    return [s["text"] for s in symbols.get("symbols", []) if s.get("kind") == "import"]


def _extract_structure(symbols: dict[str, Any]) -> dict[str, Any]:
    functions = []
    classes = []
    for s in symbols.get("symbols", []):
        if s["kind"] in ("function", "method"):
            functions.append({"name": s["name"], "line": s["line"]})
        elif s["kind"] in ("class", "enum"):
            classes.append({"name": s["name"], "line": s["line"]})
    return {"functions": functions, "classes": classes}


def _extract_call_edges(
    tree: Any, source_code: str, language: str, symbols: dict[str, Any]
) -> list[dict[str, Any]]:
    """Extract call edges from the AST using shared function-call helpers.

    Containment is column-aware: when a call and a nested function definition
    share the same start/end line (compact brace style), line-only containment
    incorrectly attributes sibling calls to the nested function.  We compare
    (line, col) tuples lexicographically so that a call at column C that lies
    beyond the nested function's end column is correctly attributed to the outer
    enclosing function (Codex P2 / issue #484).
    """
    if tree is None:
        return []
    from .function_extraction import walk_tree

    definitions, calls = walk_tree(tree.root_node, source_code, language)

    # (name, start_line, start_col, end_line, end_col, start_line_raw) per
    # definition.  A LIST, not a name-keyed dict: same-named methods in
    # different classes (two ``execute`` defs) must keep BOTH spans, or calls
    # inside the earlier one lose attribution and become ghost
    # caller_name=''/caller_line=0 edges (issue #638).
    # start_line_raw is kept separately for caller_line output (unchanged API).
    file_funcs: list[tuple[str, int, int, int, int, int]] = []
    for d in definitions:
        sl = d["start_line"]
        sc = d.get("start_col", 0)
        el = d.get("end_line", sl)
        ec = d.get("end_col", 0)
        file_funcs.append((d["name"], sl, sc, el, ec, sl))

    edges: list[dict[str, Any]] = []
    for call in calls:
        call_line = call["line"]
        call_col = call.get("col", 0)
        caller_name = ""
        caller_line = 0
        best_span: tuple[int, int] | None = None
        for fname, sl, sc, el, ec, raw_start in file_funcs:
            # Column-aware containment: (call_line, call_col) must be strictly
            # inside [start_point .. end_point] expressed as (line, col) pairs.
            # Uses lexicographic comparison so single-line functions work too.
            after_start = (call_line, call_col) >= (sl, sc)
            before_end = (call_line, call_col) <= (el, ec)
            if not (after_start and before_end):
                continue
            # Among all containing functions pick the innermost (smallest span).
            # Span is (line_span, col_span): line span first, then column span
            # as a tiebreaker for same-line (compact brace-style) functions.
            line_span = el - sl
            col_span = ec - sc if el == sl else 0  # only meaningful for 1-liners
            span: tuple[int, int] = (line_span, col_span)
            if best_span is None or span < best_span:
                best_span = span
                caller_name = fname
                caller_line = raw_start
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
