"""Tests for AST structured diff engine (ast_diff module)."""

import pytest

from tree_sitter_analyzer.ast_diff import (
    ASTDiffer,
    ASTDiffHunk,
    ASTNodeKind,
    DiffKind,
    _classify_node,
    _compute_stats,
    _extract_signature,
    _match_nodes,
    _text_hash,
)


@pytest.fixture
def differ():
    return ASTDiffer()


class TestClassifyNode:
    def test_function_types(self):
        assert _classify_node("function_definition") == ASTNodeKind.FUNCTION
        assert _classify_node("function_declaration") == ASTNodeKind.FUNCTION
        assert _classify_node("method_definition") == ASTNodeKind.FUNCTION

    def test_class_types(self):
        assert _classify_node("class_definition") == ASTNodeKind.CLASS
        assert _classify_node("class_declaration") == ASTNodeKind.CLASS

    def test_import_types(self):
        assert _classify_node("import_statement") == ASTNodeKind.IMPORT
        assert _classify_node("import_from_statement") == ASTNodeKind.IMPORT

    def test_other(self):
        assert _classify_node("if_statement") == ASTNodeKind.OTHER
        assert _classify_node("expression_statement") == ASTNodeKind.OTHER


class TestTextHash:
    def test_deterministic(self):
        assert _text_hash("hello") == _text_hash("hello")

    def test_different(self):
        assert _text_hash("abc") != _text_hash("xyz")


class TestComputeStats:
    def test_empty(self):
        assert _compute_stats([]) == {
            "total_changes": 0,
            "added": 0,
            "removed": 0,
            "changed": 0,
            "renamed": 0,
            "signature_changed": 0,
            "body_changed": 0,
        }

    def test_mixed(self):
        hunks = [
            ASTDiffHunk(DiffKind.NODE_ADDED, ASTNodeKind.FUNCTION, None, None, ""),
            ASTDiffHunk(DiffKind.NODE_REMOVED, ASTNodeKind.CLASS, None, None, ""),
            ASTDiffHunk(DiffKind.BODY_CHANGED, ASTNodeKind.FUNCTION, None, None, ""),
        ]
        stats = _compute_stats(hunks)
        assert stats["added"] == 1
        assert stats["removed"] == 1
        assert stats["body_changed"] == 1
        assert stats["total_changes"] == 3


class TestMatchNodes:
    def test_match_by_name(self):
        from tree_sitter_analyzer.ast_diff import ASTNodeInfo

        old = [
            ASTNodeInfo(
                node_type="function_definition",
                kind=ASTNodeKind.FUNCTION,
                name="foo",
                start_line=1,
                start_col=0,
                end_line=5,
                end_col=0,
                text_hash="a",
                text_preview="def foo(): pass",
            )
        ]
        new = [
            ASTNodeInfo(
                node_type="function_definition",
                kind=ASTNodeKind.FUNCTION,
                name="foo",
                start_line=1,
                start_col=0,
                end_line=5,
                end_col=0,
                text_hash="b",
                text_preview="def foo(): return 1",
            )
        ]
        matched, old_rem, new_rem = _match_nodes(old, new)
        assert len(matched) == 1
        assert len(old_rem) == 0
        assert len(new_rem) == 0

    def test_no_match(self):
        from tree_sitter_analyzer.ast_diff import ASTNodeInfo

        old = [
            ASTNodeInfo(
                node_type="function_definition",
                kind=ASTNodeKind.FUNCTION,
                name="foo",
                start_line=1,
                start_col=0,
                end_line=5,
                end_col=0,
                text_hash="a",
                text_preview="def foo(): pass",
            )
        ]
        new = [
            ASTNodeInfo(
                node_type="function_definition",
                kind=ASTNodeKind.FUNCTION,
                name="bar",
                start_line=1,
                start_col=0,
                end_line=5,
                end_col=0,
                text_hash="b",
                text_preview="def bar(): pass",
            )
        ]
        matched, old_rem, new_rem = _match_nodes(old, new)
        assert len(matched) == 0
        assert len(old_rem) == 1
        assert len(new_rem) == 1


class TestDiffStrings:
    def test_identical_code(self, differ):
        code = "def hello():\n    print('hello')\n"
        result = differ.diff_strings(code, code, "python")
        assert len(result.hunks) == 0

    def test_added_function(self, differ):
        old = "def foo():\n    pass\n"
        new = "def foo():\n    pass\n\ndef bar():\n    pass\n"
        result = differ.diff_strings(old, new, "python")
        assert result.summary_stats["added"] == 1
        added_kinds = [
            h.node_kind for h in result.hunks if h.diff_kind == DiffKind.NODE_ADDED
        ]
        assert ASTNodeKind.FUNCTION in added_kinds

    def test_removed_function(self, differ):
        old = "def foo():\n    pass\n\ndef bar():\n    pass\n"
        new = "def foo():\n    pass\n"
        result = differ.diff_strings(old, new, "python")
        assert result.summary_stats["removed"] == 1

    def test_changed_body(self, differ):
        old = "def greet():\n    print('hello')\n"
        new = "def greet():\n    print('world')\n"
        result = differ.diff_strings(old, new, "python")
        assert len(result.hunks) == 11
        body_hunks = [h for h in result.hunks if h.diff_kind == DiffKind.BODY_CHANGED]
        assert len(body_hunks) == 1

    def test_changed_signature(self, differ):
        old = "def add(a, b):\n    return a + b\n"
        new = "def add(a, b, c):\n    return a + b + c\n"
        result = differ.diff_strings(old, new, "python")
        assert len(result.hunks) == 22

    def test_added_class(self, differ):
        old = "x = 1\n"
        new = "class Foo:\n    pass\n"
        result = differ.diff_strings(old, new, "python")
        assert result.summary_stats["added"] == 1

    def test_javascript_diff(self, differ):
        old = "function add(a, b) {\n  return a + b;\n}\n"
        new = "function add(a, b, c) {\n  return a + b + c;\n}\n"
        result = differ.diff_strings(old, new, "javascript")
        assert len(result.hunks) == 20

    def test_import_added(self, differ):
        old = "def foo():\n    pass\n"
        new = "import os\n\ndef foo():\n    pass\n"
        result = differ.diff_strings(old, new, "python")
        assert result.summary_stats["added"] == 1

    def test_both_parse_fail(self, differ):
        result = differ.diff_strings("", "", "python")
        assert len(result.hunks) == 0

    def test_to_dict_roundtrip(self, differ):
        old = "def foo():\n    pass\n"
        new = "def foo():\n    return 1\n"
        result = differ.diff_strings(
            old, new, "python", old_file="a.py", new_file="a.py"
        )
        d = result.to_dict()
        assert "hunks" in d
        assert "summary" in d
        assert d["language"] == "python"
        assert d["old_file"] == "a.py"


class TestDiffFiles:
    def test_diff_same_file(self, differ, tmp_path):
        code = "def hello():\n    print('hello')\n"
        p = tmp_path / "test.py"
        p.write_text(code)
        result = differ.diff_files(str(p), str(p))
        assert len(result.hunks) == 0

    def test_diff_changed_file(self, differ, tmp_path):
        old_p = tmp_path / "old.py"
        new_p = tmp_path / "new.py"
        old_p.write_text("def foo():\n    pass\n", newline="\n")
        new_p.write_text("def foo():\n    return 1\n", newline="\n")
        result = differ.diff_files(str(old_p), str(new_p))
        assert len(result.hunks) == 11

    def test_diff_unsupported_language(self, differ, tmp_path):
        old_p = tmp_path / "old.xyz"
        new_p = tmp_path / "new.xyz"
        old_p.write_text("hello")
        new_p.write_text("world")
        result = differ.diff_files(str(old_p), str(new_p))
        assert result.language == "unknown"

    def test_diff_nonexistent_file(self, differ, tmp_path):
        new_p = tmp_path / "new.py"
        new_p.write_text("def foo():\n    pass\n", newline="\n")
        result = differ.diff_files("/nonexistent/file.py", str(new_p))
        assert result.summary_stats["added"] == 1


class TestDiffStringPairs:
    def test_batch_diff(self, differ):
        pairs = [
            ("def a(): pass\n", "def a(): return 1\n", "a.py"),
            ("x = 1\n", "x = 2\n", "b.py"),
        ]
        results = differ.diff_string_pairs(pairs, "python")
        assert len(results) == 2
        assert all(r.language == "python" for r in results)


class TestExtractSignature:
    def test_basic(self):
        from tree_sitter_analyzer.ast_diff import ASTNodeInfo

        node = ASTNodeInfo(
            node_type="function_definition",
            kind=ASTNodeKind.FUNCTION,
            name="foo",
            start_line=1,
            start_col=0,
            end_line=3,
            end_col=0,
            text_hash="abc",
            text_preview="def foo(x): pass",
            children=[
                ASTNodeInfo(
                    node_type="parameters",
                    kind=ASTNodeKind.PARAMETER,
                    name="",
                    start_line=1,
                    start_col=8,
                    end_line=1,
                    end_col=11,
                    text_hash="p1",
                    text_preview="(x)",
                ),
            ],
        )
        sig = _extract_signature(node)
        assert sig["name"] == "foo"
        assert sig["params_hash"] == "p1"
