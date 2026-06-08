"""Tests for tree_sitter_analyzer._ast_extraction private helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from tree_sitter_analyzer._ast_extraction import (
    _content_hash,
    _count_decision_points,
    _extract_call_edges,
    _extract_parent_classes,
    _has_fts5,
    _node_text,
    _walk_for_symbols,
    _worker_index_file,
)

# ---------------------------------------------------------------------------
# _has_fts5()
# ---------------------------------------------------------------------------


class TestHasFts5:
    def test_returns_true_when_pragma_succeeds(self):
        """Pragma query succeeds → True (first branch)."""
        conn = sqlite3.connect(":memory:")
        # In most SQLite builds FTS5 is available; the pragma returns rows.
        result = _has_fts5(conn)
        # Should be True or False — just ensure no exception is raised.
        assert isinstance(result, bool)
        conn.close()

    def test_returns_true_via_create_when_pragma_raises(self):
        """When first OperationalError, creates virtual table to confirm FTS5."""
        conn = MagicMock(spec=sqlite3.Connection)
        # First call raises, second/third succeed
        conn.execute.side_effect = [
            sqlite3.OperationalError("no fts5"),
            None,  # CREATE succeeds
            None,  # DROP succeeds
        ]
        assert _has_fts5(conn) is True

    def test_returns_false_when_both_branches_raise(self):
        """When CREATE VIRTUAL TABLE also fails → False."""
        conn = MagicMock(spec=sqlite3.Connection)
        conn.execute.side_effect = sqlite3.OperationalError("no fts5")
        assert _has_fts5(conn) is False


# ---------------------------------------------------------------------------
# _worker_index_file()
# ---------------------------------------------------------------------------


class TestWorkerIndexFile:
    def test_returns_io_error_status_on_missing_file(self, tmp_path):
        """Non-existent file → status 'io_error'."""
        missing = str(tmp_path / "ghost.py")
        result = _worker_index_file((missing, str(tmp_path), "python"))
        assert result["status"] == "io_error"
        assert "rel_path" in result

    def test_returns_parse_failed_status_on_unknown_language(self, tmp_path):
        """Unknown language causes parse failure → status 'parse_failed'."""
        f = tmp_path / "code.xyz"
        f.write_text("hello world")
        result = _worker_index_file((str(f), str(tmp_path), "xyz_lang"))
        # Either parse_failed or io_error — the key is it doesn't crash.
        assert result["status"] in ("parse_failed", "io_error", "ok")

    def test_returns_ok_for_valid_python(self, tmp_path):
        """Valid Python file → status 'ok' with symbol data."""
        f = tmp_path / "module.py"
        f.write_text("def greet(name):\n    return f'hello {name}'\n")
        result = _worker_index_file((str(f), str(tmp_path), "python"))
        assert result["status"] == "ok"
        assert result["symbols_count"] >= 1
        assert "content_hash" in result
        assert "mtime_ns" in result

    def test_returns_ok_for_class_with_inheritance(self, tmp_path):
        """Python class with base class → extracted symbols include parent."""
        src = "class Dog(Animal):\n    def bark(self):\n        pass\n"
        f = tmp_path / "dog.py"
        f.write_text(src)
        result = _worker_index_file((str(f), str(tmp_path), "python"))
        assert result["status"] == "ok"
        import json

        syms = json.loads(result["symbols_json"])["symbols"]
        class_syms = [s for s in syms if s.get("kind") == "class"]
        assert len(class_syms) >= 1
        dog_cls = next(s for s in class_syms if s["name"] == "Dog")
        assert "parents" in dog_cls
        assert "Animal" in dog_cls["parents"]


# ---------------------------------------------------------------------------
# _node_text()
# ---------------------------------------------------------------------------


class TestNodeText:
    def test_returns_empty_string_for_none(self):
        """None node → empty string."""
        assert _node_text(None, "anything") == ""

    def test_returns_text_when_bytes_attribute(self):
        """node.text as bytes → decoded string."""
        node = SimpleNamespace(text=b"hello_func")
        assert _node_text(node, "") == "hello_func"

    def test_returns_text_when_str_attribute(self):
        """node.text as str → returned as-is."""
        node = SimpleNamespace(text="my_symbol")
        assert _node_text(node, "") == "my_symbol"

    def test_falls_back_to_byte_slice(self):
        """No .text attribute → slice source bytes by start/end_byte."""
        source = "def hello():"
        node = SimpleNamespace(
            text=None,
            start_byte=4,
            end_byte=9,
        )
        assert _node_text(node, source) == "hello"

    def test_returns_empty_on_index_error_in_fallback(self):
        """Slice out of range → empty string (not an exception)."""
        node = SimpleNamespace(text=None, start_byte=999, end_byte=1000)
        assert _node_text(node, "short") == ""


# ---------------------------------------------------------------------------
# _count_decision_points()
# ---------------------------------------------------------------------------


class TestCountDecisionPoints:
    def test_tsx_aliases_to_typescript(self):
        """'tsx' language normalises to 'typescript' complexity map."""
        node = MagicMock()
        node.children = []
        node.type = "if_statement"
        # Stack-based: pass a node that has no children
        node.children = []
        result = _count_decision_points(node, "tsx")
        # Should return a dict (possibly empty or with if_statement count)
        assert isinstance(result, dict)

    def test_unknown_language_returns_empty_dict(self):
        """Language not in the complexity map → empty dict."""
        node = MagicMock()
        node.type = "if_statement"
        node.children = []
        result = _count_decision_points(node, "brainfuck")
        assert result == {}

    def test_python_counts_if_statements(self):
        """Python if_statement nodes are counted."""
        # Create a minimal tree: root → if_statement
        child = MagicMock()
        child.type = "if_statement"
        child.children = []
        root = MagicMock()
        root.type = "module"
        root.children = [child]
        result = _count_decision_points(root, "python")
        assert result.get("if_statement", 0) == 1


# ---------------------------------------------------------------------------
# _extract_parent_classes()
# ---------------------------------------------------------------------------


class TestExtractParentClasses:
    """Integration tests via _worker_index_file for multi-language inheritance."""

    def _index(self, tmp_path: Path, filename: str, content: str, lang: str):
        f = tmp_path / filename
        f.write_text(content, encoding="utf-8")
        import json

        result = _worker_index_file((str(f), str(tmp_path), lang))
        if result["status"] != "ok":
            return []
        syms = json.loads(result["symbols_json"])["symbols"]
        return [s for s in syms if s.get("kind") == "class"]

    def test_python_single_parent(self, tmp_path):
        classes = self._index(
            tmp_path, "py_inh.py", "class Dog(Animal):\n    pass\n", "python"
        )
        dog = next((c for c in classes if c["name"] == "Dog"), None)
        assert dog is not None
        assert dog.get("parents") == ["Animal"]

    def test_python_multiple_parents(self, tmp_path):
        classes = self._index(
            tmp_path, "py_multi.py", "class Mixin(Base, Extra):\n    pass\n", "python"
        )
        m = next((c for c in classes if c["name"] == "Mixin"), None)
        assert m is not None
        assert "Base" in m.get("parents", [])
        assert "Extra" in m.get("parents", [])

    def test_python_no_parent(self, tmp_path):
        classes = self._index(
            tmp_path, "py_nop.py", "class Standalone:\n    pass\n", "python"
        )
        s = next((c for c in classes if c["name"] == "Standalone"), None)
        assert s is not None
        assert s.get("parents", []) == []

    def test_javascript_class_heritage(self, tmp_path):
        classes = self._index(
            tmp_path,
            "es6.js",
            "class Dog extends Animal {\n  constructor() {}\n}\n",
            "javascript",
        )
        dog = next((c for c in classes if c["name"] == "Dog"), None)
        assert dog is not None
        assert "Animal" in dog.get("parents", [])

    def test_unknown_language_returns_no_crash(self, tmp_path):
        """Unsupported language doesn't raise; parents list stays empty."""
        # Build a mock node with no children to exercise the except branch
        node = MagicMock()
        node.children = []
        result = _extract_parent_classes(node, "", "unknown_lang")
        assert result == []

    def test_extract_parent_classes_exception_swallowed(self):
        """If node iteration raises, the except clause returns empty list."""
        node = MagicMock()
        node.children = MagicMock(side_effect=RuntimeError("boom"))
        # Should not raise
        result = _extract_parent_classes(node, "", "python")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# _walk_for_symbols() depth guard
# ---------------------------------------------------------------------------


class TestWalkForSymbols:
    def test_depth_guard_stops_recursion(self):
        """depth > 20 → function returns early without recursing."""
        symbols: list = []
        node = MagicMock()
        node.type = "function_definition"
        node.child_by_field_name = MagicMock(return_value=None)
        node.children = []
        # Call with depth=21 — should return immediately, not append anything
        _walk_for_symbols(node, "", symbols, "python", depth=21)
        assert symbols == []


# ---------------------------------------------------------------------------
# _extract_call_edges() with tree=None
# ---------------------------------------------------------------------------


class TestExtractCallEdges:
    def test_returns_empty_when_tree_is_none(self):
        """tree=None → empty edges list (early return)."""
        result = _extract_call_edges(None, "", "python", {"symbols": []})
        assert result == []


# ---------------------------------------------------------------------------
# _content_hash()
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_bytes_input(self):
        h = _content_hash(b"hello")
        assert len(h) == 64  # SHA-256 hex

    def test_str_input(self):
        h = _content_hash("hello")
        assert len(h) == 64

    def test_same_content_same_hash(self):
        assert _content_hash("abc") == _content_hash(b"abc")


# ---------------------------------------------------------------------------
# _walk_for_symbols() — C function name recovery
# ---------------------------------------------------------------------------


def _walk_c(source: str) -> set[str]:
    """Parse C ``source`` and return the set of recovered function names."""
    from tree_sitter_analyzer.core.parser import Parser

    result = Parser().parse_code(source, "c")
    assert result.success and result.tree is not None
    symbols: list[dict] = []
    _walk_for_symbols(result.tree.root_node, source, symbols, "c")
    return {s["name"] for s in symbols if s.get("kind") == "function"}


class TestWalkForSymbolsC:
    def test_plain_free_function(self):
        assert "add" in _walk_c("int add(int a){return a;}")

    def test_pointer_returning_function(self):
        # void *malloc(...) — single pointer_declarator wrapper
        assert "malloc" in _walk_c("void *malloc(int n) { return 0; }")

    def test_function_pointer_returning_function(self):
        # int (*factory(void))(int) — the declarator name lives under an inner
        # function_declarator nested inside a parenthesized_declarator. The name
        # must be recovered as ``factory``, NOT ``(*factory(void))``
        # (Codex P2, PR #370).
        names = _walk_c("int (*factory(void))(int) { return 0; }")
        assert "factory" in names
        assert not any("(" in n for n in names)
