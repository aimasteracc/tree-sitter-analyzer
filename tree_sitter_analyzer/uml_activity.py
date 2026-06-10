#!/usr/bin/env python3
"""Activity diagram (control-flow graph) walker for P2-A of RFC-0015.

Builds a structural CFG from a single Python function body using tree-sitter.
One public entry point: build_activity_cfg(function_name, file_path, max_nodes).

Design decisions:
- Python only for this phase; the node-type map (_PY_CFG_NODE_TYPES) is language-
  keyed so other languages can register mappings later without touching the walker.
- Requires a disk read + one tree-sitter parse per call (AST bodies are NOT
  cache-resident). Cost: typically < 50ms for a single file.
- Empty/unparseable functions return verdict="NOT_FOUND" — never garbage nodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class CFGNode:
    """A single node in the control-flow graph."""

    node_id: str
    label: str
    kind: (
        str  # "entry", "condition", "loop", "return", "raise", "try", "except", "exit"
    )


@dataclass
class CFGEdge:
    """A directed edge between two CFG nodes."""

    source_id: str
    target_id: str
    label: str = ""


@dataclass
class ActivityCFG:
    """Result of an activity-diagram walk."""

    nodes: list[CFGNode] = field(default_factory=list)
    edges: list[CFGEdge] = field(default_factory=list)
    truncated: bool = False
    error: str = ""


# ---------------------------------------------------------------------------
# Language-keyed node-type maps
# future languages register here: _CFG_NODE_TYPES["go"] = {...}
# ---------------------------------------------------------------------------

_CFG_NODE_TYPES: dict[str, set[str]] = {
    "python": {
        "if_statement",
        "for_statement",
        "while_statement",
        "try_statement",
        "return_statement",
        "raise_statement",
    },
}


def _node_text(node: Any, max_len: int = 40) -> str:
    """Decode a tree-sitter node's text, capped at max_len chars."""
    try:
        raw = node.text
        if raw is None:
            return ""
        text: str = raw.decode("utf-8", errors="replace").strip()
        if len(text) > max_len:
            text = text[:max_len] + "…"
        return text
    except Exception:
        return ""


def _condition_text(node: Any) -> str:
    """Extract condition text from an if/while/for node.

    For ``for_statement`` both sides of the ``in`` keyword are captured so the
    label reads ``item in items`` rather than just the left-hand binding.
    For ``if`` / ``while`` the first non-keyword, non-body child is returned.
    """
    if node.type == "for_statement":
        # Tree-sitter structure: for <left> in <right> : <body>
        parts_left: list[str] = []
        parts_right: list[str] = []
        seen_in = False
        for child in node.children:
            if child.type in ("for", ":", "block", "body"):
                continue
            if child.type == "in":
                seen_in = True
                continue
            text = _node_text(child, 40)
            if not text:
                continue
            if seen_in:
                parts_right.append(text)
            else:
                parts_left.append(text)
        left = " ".join(parts_left)
        right = " ".join(parts_right)
        if left and right:
            return f"{left} in {right}"
        return left or right or _node_text(node, 40)

    for child in node.children:
        if child.type not in (":", "body", "block", "else_clause", "elif_clause"):
            text = _node_text(child, 40)
            if text and text not in ("if", "elif", "while", "for", "in"):
                return text
    return _node_text(node, 40)


# ---------------------------------------------------------------------------
# Public entry point: _parse_file_for_activity
# (function name deliberately importable so tests can monkeypatch it)
# ---------------------------------------------------------------------------


def _parse_file_for_activity(
    file_path: str, language: str = "python"
) -> tuple[Any, bytes] | None:
    """Parse *file_path* with tree-sitter and return (tree_root, source_bytes).

    Returns None when the file does not exist, the language is unsupported,
    or the parser fails. ONE parse per call — callers MUST NOT call this in a
    loop for the same file (rule-11 invariant).
    """
    from .core.parser import Parser

    parser = Parser()
    result = parser.parse_file(file_path, language)
    if not result.success or result.tree is None:
        return None
    raw_source = result.source_code
    source_bytes: bytes = (
        raw_source.encode("utf-8", errors="replace")
        if isinstance(raw_source, str)
        else raw_source
    )
    return result.tree.root_node, source_bytes


def _find_function_node(root: Any, function_name: str) -> Any | None:
    """DFS preorder search for a function_definition node named *function_name*.

    Traversal is preorder (parent checked before children), so the first
    match encountered wins.  For bare names (e.g. ``"helper"``) this picks
    the outermost definition; for qualified names (e.g. ``"outer.inner"``)
    the call is delegated to :func:`_find_nested_function_node` which walks
    each scope component in sequence.

    Supports qualified lookup: ``"outer.inner"`` splits into ``["outer",
    "inner"]`` and searches for ``inner`` only inside the body of ``outer``.
    """
    if "." in function_name:
        parts = function_name.split(".", 1)
        outer_node = _find_function_node(root, parts[0])
        if outer_node is None:
            return None
        return _find_function_node(outer_node, parts[1])

    if root is None:
        return None
    # tree-sitter node kinds for function definitions
    func_kinds = {"function_definition", "async_function_definition"}
    if root.type in func_kinds:
        # function name is the first identifier child
        for child in root.children:
            if child.type == "identifier":
                try:
                    name = child.text.decode("utf-8", errors="replace")
                except Exception:
                    name = ""
                if name == function_name:
                    return root
                break  # identifier found but name mismatch — skip subtree
    for child in root.children:
        found = _find_function_node(child, function_name)
        if found is not None:
            return found
    return None


# ---------------------------------------------------------------------------
# CFG walker
# ---------------------------------------------------------------------------


class _CFGWalker:
    """Stateful walker that builds a CFG from a tree-sitter function body."""

    def __init__(self, function_name: str, max_nodes: int) -> None:
        self._function_name = function_name
        self._max_nodes = max_nodes
        self._nodes: list[CFGNode] = []
        self._edges: list[CFGEdge] = []
        self._counter = 0
        self._truncated = False
        # Maps source node_id → label to apply on the NEXT edge from that node.
        # Used to attach |True|/|False| labels from condition nodes: set before
        # walking a branch and consumed on the first _add_edge from that node.
        self._pending_edge_label: dict[str, str] = {}

    def _new_id(self, kind: str) -> str:
        self._counter += 1
        return f"{kind}_{self._counter}"

    def _add_node(self, label: str, kind: str) -> CFGNode | None:
        if len(self._nodes) >= self._max_nodes:
            self._truncated = True
            return None
        node = CFGNode(
            node_id=self._new_id(kind),
            label=label,
            kind=kind,
        )
        self._nodes.append(node)
        return node

    def _add_edge(self, source: CFGNode, target: CFGNode, label: str = "") -> None:
        # Consume any pending label for this source node (set by _handle_if for
        # True/False branch tagging) when no explicit label is provided.
        if not label:
            label = self._pending_edge_label.pop(source.node_id, "")
        self._edges.append(CFGEdge(source.node_id, target.node_id, label))

    def build(self, func_node: Any) -> ActivityCFG:
        """Walk function body and build the CFG. Returns ActivityCFG."""
        entry = self._add_node(self._function_name, "entry")
        if entry is None:
            return ActivityCFG(truncated=True)

        # Walk the body — body is typically a "block" child
        body_node = None
        for child in func_node.children:
            if child.type in ("block", "body"):
                body_node = child
                break
        if body_node is None:
            # No block found (e.g. single-line function): walk direct children
            body_node = func_node

        last_nodes = self._walk_body(body_node, [entry])

        # Implicit exit if any paths fall off the end
        if last_nodes:
            # Only add exit if not all paths end in a return/raise
            non_terminal = [n for n in last_nodes if n.kind not in ("return", "raise")]
            if non_terminal:
                exit_node = self._add_node("exit", "exit")
                if exit_node is not None:
                    for pred in non_terminal:
                        self._add_edge(pred, exit_node)

        return ActivityCFG(
            nodes=self._nodes,
            edges=self._edges,
            truncated=self._truncated,
        )

    def _walk_body(self, body_node: Any, incoming: list[CFGNode]) -> list[CFGNode]:
        """Walk statement children, threading incoming/outgoing node sets.

        Returns the list of "live" nodes at the end of this block (nodes that
        are not terminal — i.e., not all paths from them lead to return/raise).
        """
        current = list(incoming)
        for child in body_node.children:
            if self._truncated:
                break
            new_current = self._handle_statement(child, current)
            if new_current is not None:
                current = new_current
        return current

    def _handle_statement(
        self, node: Any, incoming: list[CFGNode]
    ) -> list[CFGNode] | None:
        """Process one AST node. Returns updated live set, or None to skip."""
        kind = node.type

        if kind == "if_statement":
            return self._handle_if(node, incoming)
        if kind in ("for_statement", "while_statement"):
            return self._handle_loop(node, incoming, kind)
        if kind == "try_statement":
            return self._handle_try(node, incoming)
        if kind == "return_statement":
            # tree-sitter return_statement text already contains the "return"
            # keyword (e.g. "return x"), so use the raw text directly.
            ret = self._add_node(_node_text(node, 20), "return")
            if ret is not None:
                for pred in incoming:
                    self._add_edge(pred, ret)
            return []  # terminal: no outgoing paths
        if kind == "raise_statement":
            # tree-sitter raise_statement text already contains the "raise"
            # keyword (e.g. "raise ValueError('err')").
            raise_node = self._add_node(_node_text(node, 20), "raise")
            if raise_node is not None:
                for pred in incoming:
                    self._add_edge(pred, raise_node)
            return []  # terminal
        return None  # skip uninteresting nodes

    def _handle_if(self, node: Any, incoming: list[CFGNode]) -> list[CFGNode]:
        cond_text = _condition_text(node)
        cond = self._add_node(cond_text, "condition")
        if cond is None:
            return incoming
        for pred in incoming:
            self._add_edge(pred, cond)

        # Walk the true branch (first "block" child).
        # Set a pending "True" label on cond so the first edge FROM cond into
        # the true-body block is labeled |True|.  The pending label is consumed
        # by _add_edge on first use and is not propagated further.
        true_live: list[CFGNode] = []
        false_live: list[CFGNode] = [cond]

        children = list(node.children)
        i = 0
        while i < len(children):
            child = children[i]
            if child.type == "block":
                # True branch
                self._pending_edge_label[cond.node_id] = "True"
                true_live = self._walk_body(child, [cond])
                i += 1
                break
            i += 1
        # Rest: elif_clause / else_clause
        while i < len(children):
            child = children[i]
            if child.type == "elif_clause":
                elif_cond_text = _condition_text(child)
                elif_node = self._add_node(elif_cond_text, "condition")
                if elif_node is not None:
                    for pred in false_live:
                        self._add_edge(pred, elif_node, "False")
                    # Walk the elif body with |True| pending
                    for subchild in child.children:
                        if subchild.type == "block":
                            self._pending_edge_label[elif_node.node_id] = "True"
                            true_live.extend(self._walk_body(subchild, [elif_node]))
                    false_live = [elif_node] if elif_node else false_live
            elif child.type == "else_clause":
                for subchild in child.children:
                    if subchild.type == "block":
                        # Set pending "False" on the condition/elif that leads here
                        for pred in false_live:
                            self._pending_edge_label[pred.node_id] = "False"
                        else_live = self._walk_body(subchild, false_live)
                        false_live = []  # consumed
                        true_live.extend(else_live)
            i += 1

        # No-else case: the condition itself is in false_live.  Any subsequent
        # statement that receives cond as a predecessor will be labeled "False"
        # via the pending-edge-label mechanism.
        for pred in false_live:
            if pred.kind == "condition":
                self._pending_edge_label[pred.node_id] = "False"

        return true_live + false_live

    def _handle_loop(
        self, node: Any, incoming: list[CFGNode], kind: str
    ) -> list[CFGNode]:
        loop_label = _condition_text(node)
        loop_kind = "loop"
        loop_node = self._add_node(loop_label, loop_kind)
        if loop_node is None:
            return incoming
        for pred in incoming:
            self._add_edge(pred, loop_node)
        # Walk the loop body (for "break" detection: break/continue are left as
        # terminal nodes — dominance analysis is out of scope per RFC-0015)
        for child in node.children:
            if child.type in ("block", "body"):
                self._walk_body(child, [loop_node])
                break
        return [loop_node]  # after the loop, execution continues

    def _handle_try(self, node: Any, incoming: list[CFGNode]) -> list[CFGNode]:
        try_node = self._add_node("try", "try")
        if try_node is None:
            return incoming
        for pred in incoming:
            self._add_edge(pred, try_node)

        outgoing: list[CFGNode] = []
        # Track whether we actually processed any branches (vs. empty try body).
        branches_processed = False
        for child in node.children:
            if child.type == "block":
                branches_processed = True
                outgoing.extend(self._walk_body(child, [try_node]))
            elif child.type == "except_clause":
                # Except handler: create a node for each except clause
                exc_text = ""
                for subchild in child.children:
                    if subchild.type not in ("except", ":", "block"):
                        exc_text = _node_text(subchild, 30)
                        break
                label = f"except {exc_text}".strip()
                exc_node = self._add_node(label, "except")
                if exc_node is not None:
                    self._add_edge(try_node, exc_node)
                    for subchild in child.children:
                        if subchild.type == "block":
                            branches_processed = True
                            outgoing.extend(self._walk_body(subchild, [exc_node]))

        # Return [] when all branches terminated (outgoing is empty but we DID
        # process branches), to prevent a false try→exit edge.
        # Return [try_node] only when no branch body was found at all.
        if branches_processed:
            return outgoing  # may be [] when every branch ends in return/raise
        return [try_node]


# ---------------------------------------------------------------------------
# Top-level function called by UMLExporter.activity_diagram
# ---------------------------------------------------------------------------


def build_activity_cfg(
    function_name: str,
    file_path: str,
    max_nodes: int = 50,
    language: str = "python",
) -> ActivityCFG:
    """Parse *file_path* and build a CFG for *function_name*.

    Cost: ONE disk read + ONE tree-sitter parse (rule-11 invariant).

    Returns ActivityCFG with error="" on success, or error="NOT_FOUND" /
    error="PARSE_FAILED" on failure — never raises.
    """
    if not Path(file_path).exists():
        return ActivityCFG(error="NOT_FOUND:file_missing")

    parse_result = _parse_file_for_activity(file_path, language)
    if parse_result is None:
        return ActivityCFG(error="PARSE_FAILED")

    root, _source = parse_result
    func_node = _find_function_node(root, function_name)
    if func_node is None:
        return ActivityCFG(error="NOT_FOUND:function_missing")

    walker = _CFGWalker(function_name, max_nodes)
    cfg = walker.build(func_node)

    # "Empty body" detection: only entry + exit nodes (no CFG-meaningful nodes).
    # An entry+exit pair with no condition/loop/return/raise/try/except nodes
    # means the function body was all pass/docstring/assignments with no
    # control-flow. Return NOT_FOUND so callers get a useful "stub" message.
    meaningful_kinds = {"condition", "loop", "return", "raise", "try", "except"}
    has_meaningful = any(n.kind in meaningful_kinds for n in cfg.nodes)
    if not has_meaningful and not cfg.truncated:
        return ActivityCFG(error="NOT_FOUND:empty_body")

    return cfg
