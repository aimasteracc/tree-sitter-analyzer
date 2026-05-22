#!/usr/bin/env python3
"""
AST Structured Diff — Tree-level code change understanding.

Compares two versions of source code at the AST node level rather than
text level, producing semantically meaningful diff results.

Unlike text diffs (unified diff), AST diffs understand:
- Function signature changes vs body changes
- Renamed variables vs moved code
- Added/removed parameters
- Changed return types
- Structural reordering

Equivalent to difftastic-level structural diffing, integrated with
tree-sitter-analyzer's multi-language support.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .core.parser import Parser
from .project_graph import _language_from_ext

logger = logging.getLogger(__name__)


class DiffKind(str, Enum):
    NODE_ADDED = "added"
    NODE_REMOVED = "removed"
    NODE_CHANGED = "changed"
    NODE_MOVED = "moved"
    NODE_RENAMED = "renamed"
    SIGNATURE_CHANGED = "signature_changed"
    BODY_CHANGED = "body_changed"
    UNCHANGED = "unchanged"


class ASTNodeKind(str, Enum):
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    VARIABLE = "variable"
    IMPORT = "import"
    PARAMETER = "parameter"
    DECORATOR = "decorator"
    RETURN = "return"
    EXPRESSION = "expression"
    BLOCK = "block"
    OTHER = "other"


_FUNCTION_NODES = frozenset({
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
})

_CLASS_NODES = frozenset({
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
})

_IMPORT_NODES = frozenset({
    "import_statement",
    "import_from_statement",
    "import_declaration",
    "require_statement",
    "use_declaration",
    "extern_crate_item",
    "package_declaration",
    "include_directive",
})

_VARIABLE_NODES = frozenset({
    "variable_declarator",
    "assignment_expression",
    "lexical_declaration",
    "variable_declaration",
    "const_declaration",
    "let_declaration",
})

_DECORATOR_NODES = frozenset({
    "decorator",
    "annotation",
    "attribute_item",
    "declaration_attribute",
    "decorator_statement",
})

_PARAM_NODES = frozenset({
    "parameters",
    "parameter_list",
    "argument_list",
})

_BLOCK_NODES = frozenset({
    "block",
    "statement_block",
    "compound_statement",
    "function_body",
    "body",
})


@dataclass
class ASTNodeInfo:
    node_type: str
    kind: ASTNodeKind
    name: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    text_hash: str
    text_preview: str
    children: list["ASTNodeInfo"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.node_type,
            "kind": self.kind.value,
            "name": self.name,
            "line": self.start_line,
            "end_line": self.end_line,
            "text_hash": self.text_hash[:12],
        }
        if self.text_preview:
            d["preview"] = self.text_preview
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


@dataclass
class ASTDiffHunk:
    diff_kind: DiffKind
    node_kind: ASTNodeKind
    old_node: ASTNodeInfo | None
    new_node: ASTNodeInfo | None
    summary: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "kind": self.diff_kind.value,
            "node_kind": self.node_kind.value,
            "summary": self.summary,
        }
        if self.old_node:
            d["old"] = self.old_node.to_dict()
        if self.new_node:
            d["new"] = self.new_node.to_dict()
        if self.details:
            d["details"] = self.details
        return d


@dataclass
class ASTDiffResult:
    old_file: str | None
    new_file: str | None
    language: str
    hunks: list[ASTDiffHunk] = field(default_factory=list)
    summary_stats: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "old_file": self.old_file,
            "new_file": self.new_file,
            "language": self.language,
            "hunks": [h.to_dict() for h in self.hunks],
            "summary": self.summary_stats,
        }


def _classify_node(node_type: str) -> ASTNodeKind:
    if node_type in _FUNCTION_NODES:
        return ASTNodeKind.FUNCTION
    if node_type in _CLASS_NODES:
        return ASTNodeKind.CLASS
    if node_type in _IMPORT_NODES:
        return ASTNodeKind.IMPORT
    if node_type in _VARIABLE_NODES:
        return ASTNodeKind.VARIABLE
    if node_type in _DECORATOR_NODES:
        return ASTNodeKind.DECORATOR
    if node_type in _PARAM_NODES:
        return ASTNodeKind.PARAMETER
    if node_type in _BLOCK_NODES:
        return ASTNodeKind.BLOCK
    return ASTNodeKind.OTHER


def _node_name(node: Any, source: str) -> str:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return source[name_node.start_byte:name_node.end_byte]
    for child in node.children:
        if child.type in ("identifier", "property_identifier", "field_identifier"):
            return source[child.start_byte:child.end_byte]
    return ""


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _preview(text: str, max_len: int = 80) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text


def _extract_node_info(node: Any, source: str, depth: int = 0) -> ASTNodeInfo | None:
    if node is None or depth > 30:
        return None

    node_type = node.type
    kind = _classify_node(node_type)

    text = source[node.start_byte:node.end_byte]
    name = _node_name(node, source)

    children: list[ASTNodeInfo] = []
    for child in node.children:
        child_info = _extract_node_info(child, source, depth + 1)
        if child_info is not None:
            children.append(child_info)

    return ASTNodeInfo(
        node_type=node_type,
        kind=kind,
        name=name,
        start_line=node.start_point[0] + 1,
        start_col=node.start_point[1],
        end_line=node.end_point[0] + 1,
        end_col=node.end_point[1],
        text_hash=_text_hash(text),
        text_preview=_preview(text),
        children=children,
    )


def _extract_top_level_nodes(tree: Any, source: str) -> list[ASTNodeInfo]:
    if tree is None:
        return []
    root = tree.root_node
    result: list[ASTNodeInfo] = []
    for child in root.children:
        info = _extract_node_info(child, source)
        if info is not None:
            result.append(info)
    return result


def _match_nodes(
    old_nodes: list[ASTNodeInfo],
    new_nodes: list[ASTNodeInfo],
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    matched: list[tuple[int, int]] = []
    old_matched: set[int] = set()
    new_matched: set[int] = set()

    name_map: dict[str, list[int]] = {}
    for i, n in enumerate(new_nodes):
        key = (n.kind, n.name)
        if n.name:
            name_map.setdefault(key, []).append(i)

    for oi, old_n in enumerate(old_nodes):
        if not old_n.name:
            continue
        key = (old_n.kind, old_n.name)
        candidates = name_map.get(key, [])
        for ni in candidates:
            if ni not in new_matched:
                matched.append((oi, ni))
                old_matched.add(oi)
                new_matched.add(ni)
                break

    for oi, old_n in enumerate(old_nodes):
        if oi in old_matched:
            continue
        if old_n.kind not in (ASTNodeKind.FUNCTION, ASTNodeKind.CLASS, ASTNodeKind.METHOD):
            continue
        best_ni = -1
        best_score = -1
        for ni, new_n in enumerate(new_nodes):
            if ni in new_matched:
                continue
            if new_n.kind != old_n.kind:
                continue
            child_overlap = _child_name_overlap(old_n, new_n)
            if child_overlap > best_score:
                best_score = child_overlap
                best_ni = ni
        if best_ni >= 0 and best_score > 0:
            matched.append((oi, best_ni))
            old_matched.add(oi)
            new_matched.add(best_ni)

    old_unmatched = [i for i in range(len(old_nodes)) if i not in old_matched]
    new_unmatched = [i for i in range(len(new_nodes)) if i not in new_matched]

    return matched, old_unmatched, new_unmatched


def _child_name_overlap(a: ASTNodeInfo, b: ASTNodeInfo) -> int:
    a_names = {c.name for c in a.children if c.name}
    b_names = {c.name for c in b.children if c.name}
    return len(a_names & b_names)


def _diff_matched_nodes(old_n: ASTNodeInfo, new_n: ASTNodeInfo) -> list[ASTDiffHunk]:
    hunks: list[ASTDiffHunk] = []

    if old_n.text_hash == new_n.text_hash:
        return hunks

    name_changed = old_n.name != new_n.name and old_n.name and new_n.name

    sig_fields = _extract_signature(old_n)
    new_sig = _extract_signature(new_n)
    sig_changed = sig_fields != new_sig

    body_changed = _body_hash_changed(old_n, new_n)

    if name_changed:
        hunks.append(ASTDiffHunk(
            diff_kind=DiffKind.NODE_RENAMED,
            node_kind=old_n.kind,
            old_node=old_n,
            new_node=new_n,
            summary=f"Renamed {old_n.kind.value}: '{old_n.name}' -> '{new_n.name}'",
        ))
    elif sig_changed and body_changed:
        hunks.append(ASTDiffHunk(
            diff_kind=DiffKind.SIGNATURE_CHANGED,
            node_kind=old_n.kind,
            old_node=old_n,
            new_node=new_n,
            summary=f"Signature + body changed for {old_n.kind.value} '{old_n.name}'",
            details=_sig_diff(sig_fields, new_sig),
        ))
    elif sig_changed:
        hunks.append(ASTDiffHunk(
            diff_kind=DiffKind.SIGNATURE_CHANGED,
            node_kind=old_n.kind,
            old_node=old_n,
            new_node=new_n,
            summary=f"Signature changed for {old_n.kind.value} '{old_n.name}'",
            details=_sig_diff(sig_fields, new_sig),
        ))
    elif body_changed:
        hunks.append(ASTDiffHunk(
            diff_kind=DiffKind.BODY_CHANGED,
            node_kind=old_n.kind,
            old_node=old_n,
            new_node=new_n,
            summary=f"Body changed in {old_n.kind.value} '{old_n.name}'",
        ))
    else:
        hunks.append(ASTDiffHunk(
            diff_kind=DiffKind.NODE_CHANGED,
            node_kind=old_n.kind,
            old_node=old_n,
            new_node=new_n,
            summary=f"{old_n.kind.value.title()} '{old_n.name}' changed",
        ))

    child_hunks = _diff_children(old_n, new_n)
    hunks.extend(child_hunks)

    return hunks


def _extract_signature(node: ASTNodeInfo) -> dict[str, Any]:
    sig: dict[str, Any] = {"name": node.name}
    for c in node.children:
        if c.kind == ASTNodeKind.PARAMETER:
            sig["params_hash"] = c.text_hash
            sig["params_preview"] = c.text_preview
            break
        if c.kind == ASTNodeKind.DECORATOR:
            sig.setdefault("decorators", []).append(c.text_hash)
    return sig


def _body_hash_changed(old_n: ASTNodeInfo, new_n: ASTNodeInfo) -> bool:
    old_body = _get_body_hash(old_n)
    new_body = _get_body_hash(new_n)
    if old_body is None and new_body is None:
        return old_n.text_hash != new_n.text_hash
    return old_body != new_body


def _get_body_hash(node: ASTNodeInfo) -> str | None:
    for c in node.children:
        if c.kind == ASTNodeKind.BLOCK:
            return c.text_hash
    return None


def _sig_diff(old_sig: dict[str, Any], new_sig: dict[str, Any]) -> dict[str, Any]:
    diff: dict[str, Any] = {}
    if old_sig.get("params_hash") != new_sig.get("params_hash"):
        diff["params_changed"] = True
        if old_sig.get("params_preview"):
            diff["old_params"] = old_sig["params_preview"]
        if new_sig.get("params_preview"):
            diff["new_params"] = new_sig["params_preview"]
    old_decs = old_sig.get("decorators", [])
    new_decs = new_sig.get("decorators", [])
    if old_decs != new_decs:
        diff["decorators_changed"] = True
    return diff


def _diff_children(old_n: ASTNodeInfo, new_n: ASTNodeInfo) -> list[ASTDiffHunk]:
    hunks: list[ASTDiffHunk] = []
    matched, old_rem, new_rem = _match_nodes(old_n.children, new_n.children)

    for oi, ni in matched:
        child_hunks = _diff_matched_nodes(old_n.children[oi], new_n.children[ni])
        hunks.extend(child_hunks)

    for oi in old_rem:
        c = old_n.children[oi]
        hunks.append(ASTDiffHunk(
            diff_kind=DiffKind.NODE_REMOVED,
            node_kind=c.kind,
            old_node=c,
            new_node=None,
            summary=f"Removed {c.kind.value} '{c.name or c.node_type}'",
        ))

    for ni in new_rem:
        c = new_n.children[ni]
        hunks.append(ASTDiffHunk(
            diff_kind=DiffKind.NODE_ADDED,
            node_kind=c.kind,
            old_node=None,
            new_node=c,
            summary=f"Added {c.kind.value} '{c.name or c.node_type}'",
        ))

    return hunks


def _compute_stats(hunks: list[ASTDiffHunk]) -> dict[str, int]:
    stats: dict[str, int] = {
        "total_changes": len(hunks),
        "added": 0,
        "removed": 0,
        "changed": 0,
        "renamed": 0,
        "signature_changed": 0,
        "body_changed": 0,
    }
    for h in hunks:
        k = h.diff_kind.value
        if k in stats:
            stats[k] += 1
        else:
            stats["changed"] += 1
    return stats


class ASTDiffer:
    """
    Structural AST diff engine.

    Compares two versions of source code at the AST level, producing
    semantically meaningful diff results that understand code structure
    (function signatures, bodies, classes, imports, etc.).
    """

    def __init__(self) -> None:
        self._parser = Parser()

    def diff_strings(
        self,
        old_source: str,
        new_source: str,
        language: str,
        old_file: str | None = None,
        new_file: str | None = None,
    ) -> ASTDiffResult:
        old_result = self._parser.parse_code(old_source, language)
        new_result = self._parser.parse_code(new_source, language)

        if not old_result.success and not new_result.success:
            return ASTDiffResult(
                old_file=old_file,
                new_file=new_file,
                language=language,
                hunks=[ASTDiffHunk(
                    diff_kind=DiffKind.NODE_CHANGED,
                    node_kind=ASTNodeKind.OTHER,
                    old_node=None,
                    new_node=None,
                    summary="Both sources failed to parse",
                )],
            )

        old_nodes = _extract_top_level_nodes(old_result.tree, old_source) if old_result.success else []
        new_nodes = _extract_top_level_nodes(new_result.tree, new_source) if new_result.success else []

        hunks = self._diff_node_lists(old_nodes, new_nodes)
        stats = _compute_stats(hunks)

        return ASTDiffResult(
            old_file=old_file,
            new_file=new_file,
            language=language,
            hunks=hunks,
            summary_stats=stats,
        )

    def diff_files(
        self,
        old_path: str,
        new_path: str,
        language: str | None = None,
    ) -> ASTDiffResult:
        if language is None:
            language = _language_from_ext(new_path)
        if language is None:
            language = _language_from_ext(old_path)
        if language is None:
            return ASTDiffResult(
                old_file=old_path,
                new_file=new_path,
                language="unknown",
                hunks=[ASTDiffHunk(
                    diff_kind=DiffKind.NODE_CHANGED,
                    node_kind=ASTNodeKind.OTHER,
                    old_node=None,
                    new_node=None,
                    summary="Unsupported language",
                )],
            )

        try:
            with open(old_path, encoding="utf-8", errors="replace") as f:
                old_source = f.read()
        except OSError:
            old_source = ""

        try:
            with open(new_path, encoding="utf-8", errors="replace") as f:
                new_source = f.read()
        except OSError:
            new_source = ""

        return self.diff_strings(
            old_source, new_source, language,
            old_file=old_path, new_file=new_path,
        )

    def diff_string_pairs(
        self,
        pairs: list[tuple[str, str, str]],
        language: str,
    ) -> list[ASTDiffResult]:
        results: list[ASTDiffResult] = []
        for old_src, new_src, label in pairs:
            result = self.diff_strings(old_src, new_src, language, old_file=label, new_file=label)
            results.append(result)
        return results

    def _diff_node_lists(
        self,
        old_nodes: list[ASTNodeInfo],
        new_nodes: list[ASTNodeInfo],
    ) -> list[ASTDiffHunk]:
        hunks: list[ASTDiffHunk] = []
        matched, old_rem, new_rem = _match_nodes(old_nodes, new_nodes)

        for oi, ni in matched:
            child_hunks = _diff_matched_nodes(old_nodes[oi], new_nodes[ni])
            hunks.extend(child_hunks)

        for oi in old_rem:
            n = old_nodes[oi]
            hunks.append(ASTDiffHunk(
                diff_kind=DiffKind.NODE_REMOVED,
                node_kind=n.kind,
                old_node=n,
                new_node=None,
                summary=f"Removed {n.kind.value} '{n.name or n.node_type}'",
            ))

        for ni in new_rem:
            n = new_nodes[ni]
            hunks.append(ASTDiffHunk(
                diff_kind=DiffKind.NODE_ADDED,
                node_kind=n.kind,
                old_node=None,
                new_node=n,
                summary=f"Added {n.kind.value} '{n.name or n.node_type}'",
            ))

        return hunks
