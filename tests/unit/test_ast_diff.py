"""Tests for AST structured diff engine and MCP tool."""

from __future__ import annotations

from tree_sitter_analyzer.ast_diff import (
    ASTDiffEntry,
    ASTDiffer,
    ASTDiffResult,
    ASTNode,
    DiffKind,
    NodeType,
    _text_content_key,
    compute_diff,
    extract_nodes,
)
from tree_sitter_analyzer.core.parser import Parser

# ---------------------------------------------------------------------------
# extract_nodes
# ---------------------------------------------------------------------------


def _parse_and_extract(source: str, language: str = "python") -> list[ASTNode]:
    parser = Parser()
    result = parser.parse_code(source, language)
    assert result.success, f"Parse failed: {result.error_message}"
    return extract_nodes(result.tree, source, language)


class TestExtractNodes:
    def test_python_functions(self):
        src = "def foo():\n    pass\n\ndef bar(x):\n    return x\n"
        nodes = _parse_and_extract(src)
        funcs = [n for n in nodes if n.node_type == NodeType.FUNCTION]
        assert len(funcs) == 2
        assert funcs[0].name == "foo"
        assert funcs[1].name == "bar"
        assert funcs[1].params == "(x)"

    def test_python_class_with_methods(self):
        src = (
            "class MyClass:\n"
            "    def method_a(self):\n"
            "        pass\n"
            "    def method_b(self, x):\n"
            "        return x\n"
        )
        nodes = _parse_and_extract(src)
        classes = [n for n in nodes if n.node_type == NodeType.CLASS]
        methods = [n for n in nodes if n.node_type == NodeType.METHOD]
        assert len(classes) == 1
        assert classes[0].name == "MyClass"
        assert len(methods) == 2
        assert methods[0].name == "method_a"
        assert methods[0].parent_class == "MyClass"
        assert methods[1].name == "method_b"
        assert methods[1].parent_class == "MyClass"

    def test_python_imports(self):
        src = "import os\nimport sys\nfrom pathlib import Path\n"
        nodes = _parse_and_extract(src)
        imports = [n for n in nodes if n.node_type == NodeType.IMPORT]
        assert len(imports) == 3

    def test_empty_source(self):
        src = ""
        nodes = _parse_and_extract(src)
        assert nodes == []

    def test_javascript_function(self):
        src = "function hello(name) {\n  return 'Hello ' + name;\n}\n"
        nodes = _parse_and_extract(src, "javascript")
        funcs = [n for n in nodes if n.node_type == NodeType.FUNCTION]
        assert len(funcs) == 1
        assert funcs[0].name == "hello"


# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------


class TestComputeDiff:
    def test_added_function(self):
        old_nodes = []
        new_nodes = [
            ASTNode(
                node_type=NodeType.FUNCTION,
                name="foo",
                start_line=1,
                end_line=2,
                text="def foo(): pass",
            ),
        ]
        changes = compute_diff(old_nodes, new_nodes)
        assert len(changes) == 1
        assert changes[0].kind == DiffKind.ADDED
        assert changes[0].name == "foo"

    def test_removed_function(self):
        old_nodes = [
            ASTNode(
                node_type=NodeType.FUNCTION,
                name="foo",
                start_line=1,
                end_line=2,
                text="def foo(): pass",
            ),
        ]
        new_nodes = []
        changes = compute_diff(old_nodes, new_nodes)
        assert len(changes) == 1
        assert changes[0].kind == DiffKind.REMOVED

    def test_modified_function(self):
        old_nodes = [
            ASTNode(
                node_type=NodeType.FUNCTION,
                name="foo",
                start_line=1,
                end_line=2,
                text="def foo(x): return x",
                params="(x)",
            ),
        ]
        new_nodes = [
            ASTNode(
                node_type=NodeType.FUNCTION,
                name="foo",
                start_line=1,
                end_line=2,
                text="def foo(x, y): return x + y",
                params="(x, y)",
            ),
        ]
        changes = compute_diff(old_nodes, new_nodes)
        assert len(changes) == 1
        assert changes[0].kind == DiffKind.MODIFIED
        assert changes[0].params_old == "(x)"
        assert changes[0].params_new == "(x, y)"

    def test_unchanged_function(self):
        node = ASTNode(
            node_type=NodeType.FUNCTION,
            name="foo",
            start_line=1,
            end_line=2,
            text="def foo(): pass",
        )
        changes = compute_diff([node], [node])
        assert len(changes) == 0

    def test_mixed_changes(self):
        old_nodes = [
            ASTNode(
                node_type=NodeType.FUNCTION,
                name="foo",
                start_line=1,
                end_line=2,
                text="def foo(): pass",
            ),
            ASTNode(
                node_type=NodeType.CLASS,
                name="Bar",
                start_line=4,
                end_line=6,
                text="class Bar: pass",
            ),
        ]
        new_nodes = [
            ASTNode(
                node_type=NodeType.FUNCTION,
                name="foo",
                start_line=1,
                end_line=3,
                text="def foo(x):\n    return x",
                params="(x)",
            ),
            ASTNode(
                node_type=NodeType.FUNCTION,
                name="baz",
                start_line=5,
                end_line=6,
                text="def baz(): pass",
            ),
        ]
        changes = compute_diff(old_nodes, new_nodes)
        kinds = {c.kind for c in changes}
        assert DiffKind.MODIFIED in kinds
        assert DiffKind.ADDED in kinds
        assert DiffKind.REMOVED in kinds

    def test_method_in_class(self):
        old_nodes = [
            ASTNode(
                node_type=NodeType.METHOD,
                name="method",
                start_line=2,
                end_line=3,
                text="def method(self): pass",
                parent_class="MyClass",
            ),
        ]
        new_nodes = [
            ASTNode(
                node_type=NodeType.METHOD,
                name="method",
                start_line=2,
                end_line=4,
                text="def method(self, x):\n    return x",
                params="(self, x)",
                parent_class="MyClass",
            ),
        ]
        changes = compute_diff(old_nodes, new_nodes)
        assert len(changes) == 1
        assert changes[0].kind == DiffKind.MODIFIED
        assert changes[0].parent_class == "MyClass"

    def test_import_added(self):
        old_nodes = [
            ASTNode(
                node_type=NodeType.IMPORT,
                name="import os",
                start_line=1,
                end_line=1,
                text="import os",
            ),
        ]
        new_nodes = [
            ASTNode(
                node_type=NodeType.IMPORT,
                name="import os",
                start_line=1,
                end_line=1,
                text="import os",
            ),
            ASTNode(
                node_type=NodeType.IMPORT,
                name="import sys",
                start_line=2,
                end_line=2,
                text="import sys",
            ),
        ]
        changes = compute_diff(old_nodes, new_nodes)
        assert len(changes) == 1
        assert changes[0].kind == DiffKind.ADDED


# ---------------------------------------------------------------------------
# ASTDiffer integration
# ---------------------------------------------------------------------------


class TestASTDiffer:
    def test_diff_strings_add_function(self):
        differ = ASTDiffer()
        old = ""
        new = "def hello():\n    print('hello')\n"
        result = differ.diff_strings(old, new, "python", "test.py")
        assert result.error is None
        assert result.summary["added"] >= 1
        added = [c for c in result.changes if c.kind == DiffKind.ADDED]
        assert any(c.name == "hello" for c in added)

    def test_diff_strings_remove_function(self):
        differ = ASTDiffer()
        old = "def hello():\n    pass\n\ndef world():\n    pass\n"
        new = "def hello():\n    pass\n"
        result = differ.diff_strings(old, new, "python", "test.py")
        assert result.error is None
        removed = [c for c in result.changes if c.kind == DiffKind.REMOVED]
        assert any(c.name == "world" for c in removed)

    def test_diff_strings_modify_params(self):
        differ = ASTDiffer()
        old = "def foo(x):\n    return x\n"
        new = "def foo(x, y):\n    return x + y\n"
        result = differ.diff_strings(old, new, "python", "test.py")
        assert result.error is None
        modified = [c for c in result.changes if c.kind == DiffKind.MODIFIED]
        assert len(modified) >= 1
        m = modified[0]
        assert m.name == "foo"
        assert m.params_old == "(x)"
        assert m.params_new == "(x, y)"

    def test_diff_strings_class_changes(self):
        differ = ASTDiffer()
        old = "class OldClass:\n    pass\n"
        new = "class NewClass:\n    def method(self):\n        pass\n"
        result = differ.diff_strings(old, new, "python", "test.py")
        assert result.error is None
        names = {c.name for c in result.changes}
        assert "OldClass" in names or any(
            c.kind == DiffKind.REMOVED and c.name == "OldClass" for c in result.changes
        )

    def test_diff_strings_unchanged(self):
        src = "def foo():\n    pass\n"
        differ = ASTDiffer()
        result = differ.diff_strings(src, src, "python", "test.py")
        assert result.error is None
        assert result.summary.get("added", 0) == 0
        assert result.summary.get("removed", 0) == 0
        assert result.summary.get("modified", 0) == 0

    def test_diff_strings_parse_error_both(self):
        differ = ASTDiffer()
        old = "\x00\x01\x02"
        new = "\x03\x04\x05"
        result = differ.diff_strings(old, new, "python", "bad.py")
        assert result.error is not None or result.changes == []

    def test_diff_result_to_dict_success(self):
        differ = ASTDiffer()
        result = differ.diff_strings("", "def f(): pass\n", "python", "t.py")
        d = result.to_dict()
        assert d["success"] is True
        assert "summary" in d
        assert "changes" in d

    def test_diff_result_to_dict_error(self):
        result = ASTDiffResult(file_path="x.py", language="python", error="bad")
        d = result.to_dict()
        assert d["success"] is False
        assert d["error"] == "bad"

    def test_diff_entry_to_dict(self):
        entry = ASTDiffEntry(
            kind=DiffKind.ADDED,
            node_type=NodeType.FUNCTION,
            name="foo",
            start_line_new=1,
            end_line_new=3,
        )
        d = entry.to_dict()
        assert d["kind"] == "added"
        assert d["node_type"] == "function"
        assert d["name"] == "foo"
        assert d["start_line_new"] == 1

    def test_diff_entry_to_dict_modified_with_params(self):
        entry = ASTDiffEntry(
            kind=DiffKind.MODIFIED,
            node_type=NodeType.FUNCTION,
            name="foo",
            start_line_old=1,
            end_line_old=2,
            start_line_new=1,
            end_line_new=3,
            params_old="(x)",
            params_new="(x, y)",
        )
        d = entry.to_dict()
        assert d["params_old"] == "(x)"
        assert d["params_new"] == "(x, y)"

    def test_diff_entry_to_dict_with_parent_class(self):
        entry = ASTDiffEntry(
            kind=DiffKind.MODIFIED,
            node_type=NodeType.METHOD,
            name="method",
            parent_class="MyClass",
        )
        d = entry.to_dict()
        assert d["parent_class"] == "MyClass"


# ---------------------------------------------------------------------------
# ASTNode identity_key
# ---------------------------------------------------------------------------


class TestASTNode:
    def test_identity_key_plain(self):
        n = ASTNode(
            node_type=NodeType.FUNCTION,
            name="foo",
            start_line=1,
            end_line=2,
            text="def foo(): pass",
        )
        assert n.identity_key() == "function:foo"

    def test_identity_key_with_class(self):
        n = ASTNode(
            node_type=NodeType.METHOD,
            name="bar",
            start_line=2,
            end_line=3,
            text="def bar(self): pass",
            parent_class="Cls",
        )
        assert n.identity_key() == "method:Cls.bar"

    def test_text_content_key_import(self):
        n = ASTNode(
            node_type=NodeType.IMPORT,
            name="import os",
            start_line=1,
            end_line=1,
            text="import os\n",
        )
        assert _text_content_key(n) == "import os"

    def test_text_content_key_function(self):
        n = ASTNode(
            node_type=NodeType.FUNCTION,
            name="foo",
            start_line=1,
            end_line=2,
            text="def foo(x): pass",
            params="(x)",
        )
        assert _text_content_key(n) == "foo|(x)"
