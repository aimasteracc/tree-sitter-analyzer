#!/usr/bin/env python3
"""
AST Structured Diff — Tree-level code change understanding.

Compares two versions of a file at the AST level, identifying added,
removed, and modified structural elements (functions, classes, imports,
variables). Unlike text-based diff, this understands that renaming a
function or changing a parameter list is a *modification*, not a
delete+add pair.

Parity: difftastic-level semantic diff built on tree-sitter ASTs.
"""

from __future__ import annotations

import logging
import subprocess  # nosec B404 - used for safe git CLI calls only
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .core.parser import Parser
from .project_graph import _language_from_ext

logger = logging.getLogger(__name__)


class DiffKind(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


class NodeType(str, Enum):
    FUNCTION = "function"
    CLASS = "class"
    IMPORT = "import"
    VARIABLE = "variable"
    METHOD = "method"


@dataclass(frozen=True, slots=True)
class ASTNode:
    node_type: NodeType
    name: str
    start_line: int
    end_line: int
    text: str
    params: str = ""
    parent_class: str | None = None

    def identity_key(self) -> str:
        if self.parent_class:
            return f"{self.node_type.value}:{self.parent_class}.{self.name}"
        return f"{self.node_type.value}:{self.name}"


@dataclass
class ASTDiffEntry:
    kind: DiffKind
    node_type: NodeType
    name: str
    start_line_old: int | None = None
    end_line_old: int | None = None
    start_line_new: int | None = None
    end_line_new: int | None = None
    text_old: str = ""
    text_new: str = ""
    parent_class: str | None = None
    params_old: str = ""
    params_new: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "kind": self.kind.value,
            "node_type": self.node_type.value,
            "name": self.name,
        }
        if self.parent_class:
            d["parent_class"] = self.parent_class
        if self.start_line_old is not None:
            d["start_line_old"] = self.start_line_old
        if self.end_line_old is not None:
            d["end_line_old"] = self.end_line_old
        if self.start_line_new is not None:
            d["start_line_new"] = self.start_line_new
        if self.end_line_new is not None:
            d["end_line_new"] = self.end_line_new
        if self.kind == DiffKind.MODIFIED:
            if self.params_old != self.params_new:
                d["params_old"] = self.params_old
                d["params_new"] = self.params_new
        return d


@dataclass
class ASTDiffResult:
    file_path: str
    language: str
    changes: list[ASTDiffEntry] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        if self.error:
            return {
                "file_path": self.file_path,
                "language": self.language,
                "success": False,
                "error": self.error,
            }
        return {
            "file_path": self.file_path,
            "language": self.language,
            "success": True,
            "summary": self.summary,
            "changes": [c.to_dict() for c in self.changes],
        }


_FUNC_DEF_TYPES = frozenset(
    {
        "function_definition",
        "function_declaration",
        "method_definition",
        "arrow_function",
        "generator_function_declaration",
        "function_item",
        "method_declaration",
        "constructor_declaration",
        "class_method",
        "member_function",
        "function_declarator",
    }
)

_CLASS_DEF_TYPES = frozenset(
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

_IMPORT_TYPES = frozenset(
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

_VAR_DECL_TYPES = frozenset(
    {
        "lexical_declaration",
        "variable_declaration",
        "const_declaration",
        "let_declaration",
        "var_declaration",
    }
)


def _node_text(node: Any, source: str) -> str:
    if node is None:
        return ""
    try:
        return source[node.start_byte : node.end_byte]
    except (IndexError, TypeError):
        return ""


def _get_name(node: Any, source: str) -> str:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return _node_text(name_node, source)
    for child in node.children:
        if child.type in ("identifier", "property_identifier"):
            text = child.text
            return text.decode("utf-8") if isinstance(text, bytes) else str(text)
    return ""


def _get_params(node: Any, source: str) -> str:
    params_node = node.child_by_field_name("parameters")
    if params_node is not None:
        return _node_text(params_node, source)
    return ""


def _find_parent_class(node: Any) -> str | None:
    current = node.parent
    while current is not None:
        if current.type in _CLASS_DEF_TYPES:
            for child in current.children:
                if child.type in ("identifier", "type_identifier"):
                    text = child.text
                    return (
                        text.decode("utf-8") if isinstance(text, bytes) else str(text)
                    )
        current = current.parent
    return None


def extract_nodes(tree: Any, source: str, language: str) -> list[ASTNode]:
    if tree is None:
        return []
    nodes: list[ASTNode] = []
    _walk_for_nodes(tree.root_node, source, language, nodes, None)
    return nodes


def _walk_for_nodes(
    node: Any,
    source: str,
    language: str,
    nodes: list[ASTNode],
    parent_class: str | None,
    depth: int = 0,
) -> None:
    if depth > 25 or not hasattr(node, "type"):
        return

    node_type = node.type
    cls = _find_parent_class(node) or parent_class

    if node_type in _FUNC_DEF_TYPES:
        name = _get_name(node, source)
        if name:
            ntype = NodeType.METHOD if cls else NodeType.FUNCTION
            nodes.append(
                ASTNode(
                    node_type=ntype,
                    name=name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    text=_node_text(node, source),
                    params=_get_params(node, source),
                    parent_class=cls,
                )
            )
        for child in node.children:
            _walk_for_nodes(child, source, language, nodes, cls, depth + 1)
        return

    if node_type in _CLASS_DEF_TYPES:
        name = _get_name(node, source)
        if name:
            nodes.append(
                ASTNode(
                    node_type=NodeType.CLASS,
                    name=name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    text=_node_text(node, source),
                    parent_class=None,
                )
            )
        for child in node.children:
            _walk_for_nodes(child, source, language, nodes, name, depth + 1)
        return

    if node_type in _IMPORT_TYPES:
        nodes.append(
            ASTNode(
                node_type=NodeType.IMPORT,
                name=_node_text(node, source),
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                text=_node_text(node, source),
            )
        )
        for child in node.children:
            _walk_for_nodes(child, source, language, nodes, cls, depth + 1)
        return

    if node_type in _VAR_DECL_TYPES:
        for child in node.children:
            if child.type in ("variable_declarator", "identifier"):
                vn = child.child_by_field_name("name")
                if vn is None:
                    vn = child
                name = _node_text(vn, source)
                if name and not name.startswith("_"):
                    nodes.append(
                        ASTNode(
                            node_type=NodeType.VARIABLE,
                            name=name,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            text=_node_text(node, source),
                            parent_class=cls,
                        )
                    )
                break

    for child in node.children:
        _walk_for_nodes(child, source, language, nodes, cls, depth + 1)


def _text_content_key(node: ASTNode) -> str:
    if node.node_type == NodeType.IMPORT:
        return node.text.strip()
    parts = [node.name]
    if node.params:
        parts.append(node.params)
    return "|".join(parts)


def compute_diff(
    old_nodes: list[ASTNode],
    new_nodes: list[ASTNode],
) -> list[ASTDiffEntry]:
    changes: list[ASTDiffEntry] = []

    old_by_key: dict[str, list[ASTNode]] = {}
    for n in old_nodes:
        old_by_key.setdefault(n.identity_key(), []).append(n)

    new_by_key: dict[str, list[ASTNode]] = {}
    for n in new_nodes:
        new_by_key.setdefault(n.identity_key(), []).append(n)

    matched_old: set[tuple[str, int]] = set()
    matched_new: set[tuple[str, int]] = set()

    for key, new_list in new_by_key.items():
        old_list = old_by_key.get(key, [])
        for ni, new_n in enumerate(new_list):
            matched = False
            for oi, old_n in enumerate(old_list):
                if (key, oi) in matched_old:
                    continue
                content_key_old = _text_content_key(old_n)
                content_key_new = _text_content_key(new_n)
                if content_key_old == content_key_new:
                    matched_old.add((key, oi))
                    matched_new.add((key, ni))
                    matched = True
                    break
                else:
                    matched_old.add((key, oi))
                    matched_new.add((key, ni))
                    changes.append(
                        ASTDiffEntry(
                            kind=DiffKind.MODIFIED,
                            node_type=new_n.node_type,
                            name=new_n.name,
                            start_line_old=old_n.start_line,
                            end_line_old=old_n.end_line,
                            start_line_new=new_n.start_line,
                            end_line_new=new_n.end_line,
                            text_old=old_n.text,
                            text_new=new_n.text,
                            parent_class=new_n.parent_class,
                            params_old=old_n.params,
                            params_new=new_n.params,
                        )
                    )
                    matched = True
                    break
            if not matched and (key, ni) not in matched_new:
                changes.append(
                    ASTDiffEntry(
                        kind=DiffKind.ADDED,
                        node_type=new_n.node_type,
                        name=new_n.name,
                        start_line_new=new_n.start_line,
                        end_line_new=new_n.end_line,
                        text_new=new_n.text,
                        parent_class=new_n.parent_class,
                        params_new=new_n.params,
                    )
                )

    for key, old_list in old_by_key.items():
        for oi, old_n in enumerate(old_list):
            if (key, oi) not in matched_old:
                changes.append(
                    ASTDiffEntry(
                        kind=DiffKind.REMOVED,
                        node_type=old_n.node_type,
                        name=old_n.name,
                        start_line_old=old_n.start_line,
                        end_line_old=old_n.end_line,
                        text_old=old_n.text,
                        parent_class=old_n.parent_class,
                        params_old=old_n.params,
                    )
                )

    changes.sort(key=lambda c: c.start_line_new or c.start_line_old or 0)
    return changes


def _compute_summary(changes: list[ASTDiffEntry]) -> dict[str, int]:
    s: dict[str, int] = {"added": 0, "removed": 0, "modified": 0, "unchanged": 0}
    for c in changes:
        k = c.kind.value
        s[k] = s.get(k, 0) + 1
    return s


class ASTDiffer:
    """Compare two versions of source code at the AST level."""

    def __init__(self) -> None:
        self._parser = Parser()

    def diff_strings(
        self,
        old_source: str,
        new_source: str,
        language: str,
        file_path: str = "",
    ) -> ASTDiffResult:
        old_result = self._parser.parse_code(old_source, language, filename=file_path)
        new_result = self._parser.parse_code(new_source, language, filename=file_path)

        if not old_result.success and not new_result.success:
            return ASTDiffResult(
                file_path=file_path,
                language=language,
                error="Both versions failed to parse",
            )
        if not old_result.success:
            return ASTDiffResult(
                file_path=file_path,
                language=language,
                error=f"Old version parse error: {old_result.error_message}",
            )
        if not new_result.success:
            return ASTDiffResult(
                file_path=file_path,
                language=language,
                error=f"New version parse error: {new_result.error_message}",
            )

        old_nodes = extract_nodes(old_result.tree, old_source, language)
        new_nodes = extract_nodes(new_result.tree, new_source, language)
        changes = compute_diff(old_nodes, new_nodes)
        summary = _compute_summary(changes)

        return ASTDiffResult(
            file_path=file_path,
            language=language,
            changes=changes,
            summary=summary,
        )

    def diff_file_revisions(
        self,
        file_path: str,
        old_ref: str = "HEAD~1",
        new_ref: str = "HEAD",
    ) -> ASTDiffResult:
        language = _language_from_ext(file_path)
        if language is None:
            return ASTDiffResult(
                file_path=file_path,
                language="unknown",
                error=f"Unsupported file type: {file_path}",
            )

        old_source = _git_show(file_path, old_ref)
        new_source = _git_show(file_path, new_ref)

        if old_source is None and new_source is None:
            return ASTDiffResult(
                file_path=file_path,
                language=language,
                error=f"Could not read file from git at {old_ref} or {new_ref}",
            )

        if old_source is None:
            old_source = ""
        if new_source is None:
            new_source = ""

        return self.diff_strings(old_source, new_source, language, file_path)

    def diff_file_against_git(
        self,
        file_path: str,
        ref: str = "HEAD",
    ) -> ASTDiffResult:
        language = _language_from_ext(file_path)
        if language is None:
            return ASTDiffResult(
                file_path=file_path,
                language="unknown",
                error=f"Unsupported file type: {file_path}",
            )

        old_source = _git_show(file_path, ref)
        if old_source is None:
            old_source = ""

        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                new_source = f.read()
        except OSError as e:
            return ASTDiffResult(
                file_path=file_path,
                language=language,
                error=f"Cannot read file: {e}",
            )

        return self.diff_strings(old_source, new_source, language, file_path)


def _git_show(file_path: str, ref: str) -> str | None:
    try:
        # ``git show <ref>:<path>`` — both args originate from the caller's
        # CLI/MCP arguments which go through SecurityValidator path checks
        # before we ever reach here. We always pass a fixed argv list (no
        # shell), and the timeout caps any runaway.
        # nosec: B603 trusted argv. B607 git-on-PATH is the convention for
        # every dev tool in this repo; full-path lookup hard-codes a Linux
        # /usr/bin/git that doesn't exist on macOS/Windows dev machines.
        result = subprocess.run(  # nosec B603 B607
            ["git", "show", f"{ref}:{file_path}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
