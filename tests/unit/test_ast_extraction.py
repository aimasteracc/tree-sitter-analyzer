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


class TestCDeclaratorName:
    """Edge cases of the C declarator-name descent helper."""

    def test_none_declarator_returns_none(self):
        from tree_sitter_analyzer._ast_extraction import _c_declarator_name

        assert _c_declarator_name(None, "", 0) is None

    def test_depth_guard_returns_none(self):
        from tree_sitter_analyzer._ast_extraction import _c_declarator_name

        # depth past the bound short-circuits even with a real node
        node = SimpleNamespace(type="identifier")
        assert _c_declarator_name(node, "x", 99) is None

    def test_unknown_declarator_type_returns_none(self):
        from tree_sitter_analyzer._ast_extraction import _c_declarator_name

        node = SimpleNamespace(type="abstract_declarator", children=[])
        assert _c_declarator_name(node, "", 0) is None

    def test_parenthesized_without_name_returns_none(self):
        from tree_sitter_analyzer._ast_extraction import _c_declarator_name

        # parenthesized_declarator whose children carry no name-bearing node
        paren = SimpleNamespace(
            type="parenthesized_declarator",
            children=[SimpleNamespace(type="(", children=[])],
        )
        assert _c_declarator_name(paren, "", 0) is None


# ---------------------------------------------------------------------------
# Issue #532: nested-container method ownership (Ruby + Rust)
# ---------------------------------------------------------------------------


def _symbols_for(source: str, lang: str) -> list[dict]:
    """Parse source and return all symbols from _extract_symbols."""

    from tree_sitter_analyzer._ast_extraction import _extract_symbols
    from tree_sitter_analyzer.core.parser import Parser

    result = Parser().parse_code(source, lang)
    if not result.success or result.tree is None:
        return []
    syms = _extract_symbols(result.tree, source, lang)
    return syms["symbols"]


class TestNestedContainerMethodOwnership:
    """Issue #532 — methods inside nested containers must be attributed to
    the INNERMOST container in the symbols DB path (_walk_for_symbols)."""

    # ---- Ruby ----

    def test_ruby_module_nested_class_methods_attributed_correctly(self):
        """Methods inside a class nested in a module must get the CLASS as
        their owner, not the module, AND must appear at all (Ruby ``method``
        node type was missing from _FUNCTION_LIKE)."""
        code = """\
module Authentication
  class User
    def initialize(name)
      @name = name
    end
    def full_name
      @name
    end
  end
  class AdminUser
    def login
      true
    end
  end
end
"""
        syms = _symbols_for(code, "ruby")
        methods = [s for s in syms if s["kind"] in ("function", "method")]
        classes = {s["name"] for s in syms if s["kind"] == "class"}

        # Classes must be visible
        assert "User" in classes
        assert "AdminUser" in classes

        # Methods must be extracted (was 0 before fix — "method" missing from _FUNCTION_LIKE)
        assert len(methods) == 3

        # Each method must be attributed to its direct owner class, NOT the module
        owners = {m["name"]: m.get("class") for m in methods}
        assert owners.get("initialize") == "User"
        assert owners.get("full_name") == "User"
        assert owners.get("login") == "AdminUser"

    # ---- Rust ----

    def test_rust_impl_generic_methods_attributed_to_struct(self):
        """Methods inside impl<T> Container<T> must be attributed to Container,
        not left unowned (_find_parent_class must read impl_item's type field)."""
        code = """\
pub struct Container<T> {
    items: Vec<T>,
}

impl<T> Container<T> {
    pub fn new() -> Self {
        Container { items: Vec::new() }
    }
    pub fn push(&mut self, item: T) {
        self.items.push(item);
    }
}
"""
        syms = _symbols_for(code, "rust")
        methods = [s for s in syms if s["kind"] in ("function", "method")]

        # Both functions must appear
        assert len(methods) == 2

        # Both must be attributed to Container (stripped of generics)
        owners = {m["name"]: m.get("class") for m in methods}
        assert owners.get("new") == "Container"
        assert owners.get("push") == "Container"

    def test_rust_plain_impl_methods_attributed_to_struct(self):
        """Plain impl User (no generics) must attribute methods to User."""
        code = """\
struct User {
    name: String,
}

impl User {
    fn greet(&self) -> String {
        format!("Hello, {}", self.name)
    }
}
"""
        syms = _symbols_for(code, "rust")
        methods = [s for s in syms if s["kind"] in ("function", "method")]
        assert len(methods) == 1
        assert methods[0].get("class") == "User"


# ---------------------------------------------------------------------------
# Issue #610: Python module-level constants indexed as kind="constant"
# ---------------------------------------------------------------------------


_CONST_SRC = """\
_STOP_WORDS = frozenset({"the"})
CONFIG: dict = {}
__version__ = "1.0"
logger = get_logger()
paths: list = []
bare_decl: int

if True:
    WRAPPED_FLAG = 1


class Settings:
    TIMEOUT = 30


def setup():
    RETRIES = 3
"""


class TestPythonModuleConstants:
    """Issue #610 — module-level const-style / annotated / dunder assignments
    must reach ast_symbol_rows as kind="constant"."""

    def _constants(self) -> dict[str, dict]:
        syms = _symbols_for(_CONST_SRC, "python")
        return {s["name"]: s for s in syms if s["kind"] == "constant"}

    def test_exactly_the_five_module_constants_extracted(self):
        consts = self._constants()
        assert sorted(consts) == [
            "CONFIG",
            "WRAPPED_FLAG",
            "_STOP_WORDS",
            "__version__",
            "paths",
        ]

    def test_const_style_name_lines_pinned(self):
        consts = self._constants()
        assert consts["_STOP_WORDS"]["line"] == 1
        assert consts["_STOP_WORDS"]["end_line"] == 1
        assert consts["CONFIG"]["line"] == 2
        assert consts["__version__"]["line"] == 3
        assert consts["WRAPPED_FLAG"]["line"] == 9
        assert all(c["language"] == "python" for c in consts.values())

    def test_annotated_lowercase_assignment_extracted(self):
        # `paths: list = []` — annotated module assignment counts even when
        # the name is not const-style (deliberate typed API surface).
        assert "paths" in self._constants()

    def test_lowercase_unannotated_assignment_not_extracted(self):
        # `logger = get_logger()` — mutable module state, excluded by scope rule.
        syms = _symbols_for(_CONST_SRC, "python")
        logger_kinds = [s["kind"] for s in syms if s.get("name") == "logger"]
        assert logger_kinds == []

    def test_bare_annotation_without_value_not_extracted(self):
        # `bare_decl: int` has no right-hand side — not a definition site.
        assert "bare_decl" not in self._constants()

    def test_class_body_all_caps_not_extracted(self):
        # Settings.TIMEOUT is a class attribute, not a module constant.
        assert "TIMEOUT" not in self._constants()

    def test_function_body_all_caps_not_extracted(self):
        # RETRIES lives in a function body — module-level only.
        assert "RETRIES" not in self._constants()

    def test_non_python_assignment_unaffected(self):
        # JS module-level const keeps its pre-existing kind="variable" path.
        syms = _symbols_for("const MAX_SIZE = 10;\n", "javascript")
        kinds = {s["name"]: s["kind"] for s in syms if "name" in s}
        assert kinds == {"MAX_SIZE": "variable"}

    def test_chained_assignment_captures_both_names(self):
        syms = _symbols_for("A_ONE = B_TWO = 5\n", "python")
        consts = sorted(s["name"] for s in syms if s["kind"] == "constant")
        assert consts == ["A_ONE", "B_TWO"]

    def test_tuple_target_not_extracted(self):
        # Non-simple targets (tuple unpacking) are excluded by the scope rule.
        syms = _symbols_for("X_A, Y_B = 1, 2\n", "python")
        assert [s for s in syms if s["kind"] == "constant"] == []


# ---------------------------------------------------------------------------
# Issue #613: Go package-level constants indexed as kind="constant"
# ---------------------------------------------------------------------------


_GO_CONST_SRC = """\
package main

const A = 1

const (
	B = 2
	C = 3
)

const lowercaseConst = 4

var MAX_RETRIES = 5

var lowercase_var = "x"

var (
	GROUP_VAR = 1
	other     = 2
)

var _ = sideEffect()

func f() {
	const LOCAL_CONST = 9
	var LOCAL_VAR = 10
	_ = LOCAL_CONST
	_ = LOCAL_VAR
}
"""


class TestGoPackageConstants:
    """Issue #613 — Go package-level const specs (all of them — Go consts are
    constants by compiler definition) and const-style package vars must reach
    ast_symbol_rows as kind="constant"; function-locals must not."""

    def _constants(self) -> dict[str, dict]:
        syms = _symbols_for(_GO_CONST_SRC, "go")
        return {s["name"]: s for s in syms if s["kind"] == "constant"}

    def test_exactly_the_six_package_constants_extracted(self):
        consts = self._constants()
        assert sorted(consts) == [
            "A",
            "B",
            "C",
            "GROUP_VAR",
            "MAX_RETRIES",
            "lowercaseConst",
        ]

    def test_grouped_const_block_captures_both_names_lines_pinned(self):
        consts = self._constants()
        assert consts["B"]["line"] == 6
        assert consts["B"]["end_line"] == 6
        assert consts["C"]["line"] == 7
        assert consts["C"]["end_line"] == 7
        assert all(c["language"] == "go" for c in consts.values())

    def test_lowercase_const_included_no_pattern_gate(self):
        # Go consts are constants by definition (compiler-enforced
        # immutability) — no const-style name gate, unlike package vars.
        assert "lowercaseConst" in self._constants()

    def test_package_var_const_style_included(self):
        consts = self._constants()
        assert consts["MAX_RETRIES"]["line"] == 12
        assert consts["GROUP_VAR"]["line"] == 17

    def test_lowercase_package_var_excluded(self):
        # Package vars are mutable state; only const-style names (the author
        # signalling a constant by convention) count — asymmetry vs const.
        syms = _symbols_for(_GO_CONST_SRC, "go")
        assert [s["kind"] for s in syms if s.get("name") == "lowercase_var"] == []
        assert [s["kind"] for s in syms if s.get("name") == "other"] == []

    def test_blank_identifier_excluded(self):
        # `var _ = sideEffect()` — the blank identifier is not referenceable.
        assert "_" not in self._constants()

    def test_function_local_const_and_var_excluded(self):
        consts = self._constants()
        assert "LOCAL_CONST" not in consts
        assert "LOCAL_VAR" not in consts

    def test_method_and_func_literal_locals_excluded(self):
        src = (
            "package main\n\n"
            "type S struct{}\n\n"
            "func (s S) m() {\n"
            "\tconst METHOD_CONST = 1\n"
            "\t_ = METHOD_CONST\n"
            "}\n\n"
            "var F = func() {\n"
            "\tconst CLOSURE_CONST = 2\n"
            "\t_ = CLOSURE_CONST\n"
            "}\n"
        )
        syms = _symbols_for(src, "go")
        consts = sorted(s["name"] for s in syms if s["kind"] == "constant")
        assert consts == []

    def test_multi_name_const_spec_captures_all_names(self):
        syms = _symbols_for("package main\n\nconst P1, Q2 = 1, 2\n", "go")
        consts = sorted(s["name"] for s in syms if s["kind"] == "constant")
        assert consts == ["P1", "Q2"]

    def test_typed_const_and_iota_block_captured(self):
        src = (
            "package main\n\n"
            "const Typed int = 7\n\n"
            "const (\n"
            "\tKindA = iota\n"
            "\tKindB\n"
            ")\n"
        )
        syms = _symbols_for(src, "go")
        consts = sorted(s["name"] for s in syms if s["kind"] == "constant")
        assert consts == ["KindA", "KindB", "Typed"]


# ---------------------------------------------------------------------------
# Issue #613: Rust const/static items indexed as kind="constant"
# ---------------------------------------------------------------------------


_RUST_CONST_SRC = """\
const MAX: u32 = 10;

static GLOBAL: &str = "x";

static mut COUNTER: i32 = 0;

const lowercase_const: u32 = 4;

mod m {
    const NESTED: u32 = 1;
    static NESTED_STATIC: u8 = 2;
}

fn f() {
    const LOCAL_CONST: u32 = 9;
    static LOCAL_STATIC: u32 = 8;
    let _ = LOCAL_CONST;
}

struct S;

impl S {
    const ASSOC: u32 = 5;

    fn m(&self) {
        const METHOD_CONST: u32 = 1;
        let _ = METHOD_CONST;
    }
}

trait T {
    const TRAIT_CONST: u32 = 6;
}
"""


class TestRustConstants:
    """Issue #613 — Rust const_item/static_item must reach ast_symbol_rows as
    kind="constant" (ALL names — Rust const/static are language-level
    constants/globals, the compiler lints non-upper-case ones, so no
    name-pattern gate; mirrors the Go const reasoning from #615).
    Function-locals must not appear. Associated consts (impl/trait body) ARE
    captured: unlike Python class attributes (mutable state, excluded by
    #612), a Rust associated const is a compiler-enforced constant
    referenceable as ``Type::CONST`` — the ``enclosed`` mechanism captures
    them naturally because impl/trait bodies are not function scopes."""

    def _constants(self) -> dict[str, dict]:
        syms = _symbols_for(_RUST_CONST_SRC, "rust")
        return {s["name"]: s for s in syms if s["kind"] == "constant"}

    def test_exactly_the_eight_constants_extracted(self):
        consts = self._constants()
        assert sorted(consts) == [
            "ASSOC",
            "COUNTER",
            "GLOBAL",
            "MAX",
            "NESTED",
            "NESTED_STATIC",
            "TRAIT_CONST",
            "lowercase_const",
        ]

    def test_module_scope_const_and_static_lines_pinned(self):
        consts = self._constants()
        assert consts["MAX"]["line"] == 1
        assert consts["MAX"]["end_line"] == 1
        assert consts["GLOBAL"]["line"] == 3
        assert consts["GLOBAL"]["end_line"] == 3
        assert all(c["language"] == "rust" for c in consts.values())

    def test_static_mut_captured(self):
        # `static mut` is still a crate-level global the compiler names in
        # SCREAMING_SNAKE; mirroring Go consts, no mutability gate.
        assert self._constants()["COUNTER"]["line"] == 5

    def test_lowercase_const_included_no_pattern_gate(self):
        # Rust const/static are constants by definition — rustc lints
        # non_upper_case_globals, so a name-pattern gate adds nothing.
        assert "lowercase_const" in self._constants()

    def test_mod_nested_const_and_static_captured(self):
        # mod bodies are declaration_list (module scope), consistent with
        # the #596 mod-container treatment — NESTED/NESTED_STATIC count.
        consts = self._constants()
        assert consts["NESTED"]["line"] == 10
        assert consts["NESTED_STATIC"]["line"] == 11

    def test_function_local_const_and_static_excluded(self):
        consts = self._constants()
        assert "LOCAL_CONST" not in consts
        assert "LOCAL_STATIC" not in consts
        assert "METHOD_CONST" not in consts

    def test_associated_consts_captured_decision_pinned(self):
        # Decision (#613): associated consts in impl/trait bodies ARE
        # captured — compiler-enforced constants addressable as S::ASSOC /
        # T::TRAIT_CONST, not mutable attributes.
        consts = self._constants()
        assert consts["ASSOC"]["line"] == 23
        assert consts["TRAIT_CONST"]["line"] == 32

    def test_closure_local_const_excluded(self):
        src = (
            "fn outer() {\n"
            "    let c = |x: i32| {\n"
            "        const CLOSURE_CONST: i32 = 1;\n"
            "        x + CLOSURE_CONST\n"
            "    };\n"
            "    let _ = c;\n"
            "}\n"
        )
        syms = _symbols_for(src, "rust")
        consts = sorted(s["name"] for s in syms if s["kind"] == "constant")
        assert consts == []


class TestRustConstantsCodexP2s:
    """Codex P2s on #618: block-local nested consts and anonymous const _."""

    def _constant_names(self, src: str) -> list[str]:
        syms = _symbols_for(src, "rust")
        return [s["name"] for s in syms if s["kind"] == "constant"]

    def test_const_initializer_block_inner_const_excluded(self):
        src = "const OUTER: i32 = { const INNER: i32 = 1; INNER };\n"
        assert self._constant_names(src) == ["OUTER"]

    def test_anonymous_const_skipped(self):
        src = "const _: usize = 1;\nconst REAL: usize = 2;\n"
        assert self._constant_names(src) == ["REAL"]

    def test_python_if_wrapped_module_constant_still_captured(self):
        """Guard the #612 guarantee the language-gated scope sets protect:
        Python if-wrapped module constants stay captured even though Rust's
        scope set now contains "block"."""
        src = "import sys\nif sys.platform == 'win32':\n    SEP = chr(92)\n"
        syms = _symbols_for(src, "python")
        names = [s["name"] for s in syms if s["kind"] == "constant"]
        assert names == ["SEP"]


# ---------------------------------------------------------------------------
# Issue #624: PHP const declarations indexed as kind="constant"
# ---------------------------------------------------------------------------


_PHP_CONST_SRC = """\
<?php
const MAX = 1;

const A = 1, B = 2;

define('LEGACY_MODE', true);

class Config {
    const MAX_USERS = 1000;
    public const X = 2;
    final public const FLAG = 5;
}

interface Shape {
    const SIDES = 0;
}

trait Loggable {
    const TRAIT_C = 4;
}

enum Suit: int {
    case Hearts = 1;
    const ENUM_C = 9;
}

function f() {
    const ILLEGAL_LOCAL = 7;
    define('RUNTIME_FLAG', 1);
}

$pad = new class {
    const ANON_C = 3;
};
"""


class TestPhpConstants:
    """Issue #624 — PHP const declarations must reach ast_symbol_rows as
    kind="constant" (ALL names — PHP ``const`` is compiler-enforced
    immutable, no name-pattern gate; mirrors the Go #615 / Rust #618
    reasoning). Class/interface/trait/enum consts ARE captured: addressable
    as ``Config::MAX_USERS``, like Rust associated consts — their bodies are
    declaration_list / enum_declaration_list nodes, so the ``enclosed``
    mechanism keeps them naturally. ``define()`` calls are
    function_call_expression nodes (runtime registration, not declarations)
    and stay out — as do function-body consts (illegal PHP that
    tree-sitter-php still parses as const_declaration)."""

    def _constants(self) -> dict[str, dict]:
        syms = _symbols_for(_PHP_CONST_SRC, "php")
        return {s["name"]: s for s in syms if s["kind"] == "constant"}

    def test_exactly_the_ten_constants_extracted(self):
        consts = self._constants()
        assert sorted(consts) == [
            "A",
            "ANON_C",
            "B",
            "ENUM_C",
            "FLAG",
            "MAX",
            "MAX_USERS",
            "SIDES",
            "TRAIT_C",
            "X",
        ]

    def test_top_level_const_lines_pinned(self):
        consts = self._constants()
        assert consts["MAX"]["line"] == 2
        assert consts["MAX"]["end_line"] == 2
        assert all(c["language"] == "php" for c in consts.values())

    def test_multi_element_declaration_one_row_each(self):
        # `const A = 1, B = 2;` — one const_declaration, two const_element
        # children; each element is its own row (mirrors Go spec handling).
        consts = self._constants()
        assert consts["A"]["line"] == 4
        assert consts["B"]["line"] == 4

    def test_class_consts_captured_decision_pinned(self):
        # Decision (#624): class consts ARE captured — compiler-enforced
        # constants addressable as Config::MAX_USERS, like Rust associated
        # consts (#618), unlike the mutable Python class attributes #612
        # excludes. Modifiers (public / final public) do not change capture.
        consts = self._constants()
        assert consts["MAX_USERS"]["line"] == 9
        assert consts["X"]["line"] == 10
        assert consts["FLAG"]["line"] == 11

    def test_interface_trait_enum_consts_captured(self):
        consts = self._constants()
        assert consts["SIDES"]["line"] == 15
        assert consts["TRAIT_C"]["line"] == 19
        assert consts["ENUM_C"]["line"] == 24

    def test_enum_case_is_not_a_const_row(self):
        # enum cases are enum_case nodes, not const_element — a different
        # construct, out of #624 scope (no kind="constant" row).
        assert "Hearts" not in self._constants()

    def test_define_calls_excluded_decision_pinned(self):
        # Decision (#624): define() is a function_call_expression — runtime
        # registration whose name is a string argument (possibly dynamic),
        # not a declaration. Not indexed.
        consts = self._constants()
        assert "LEGACY_MODE" not in consts
        assert "RUNTIME_FLAG" not in consts

    def test_function_body_const_excluded(self):
        # PHP has no function-scope const (compile error), but
        # tree-sitter-php parses it permissively as const_declaration —
        # the enclosed gate must keep it out.
        assert "ILLEGAL_LOCAL" not in self._constants()

    def test_top_level_anonymous_class_const_captured(self):
        # Decision (#624): a top-level anonymous-class const is still a
        # compiler-enforced class const (addressable via the instance);
        # captured. Inside a function body it is excluded like any other
        # function-enclosed const (next test).
        assert self._constants()["ANON_C"]["line"] == 33

    def test_closure_and_function_nested_consts_excluded(self):
        src = (
            "<?php\n"
            "$c = function () {\n"
            "    const CLOSURE_LOCAL = 1;\n"
            "};\n"
            "function g() {\n"
            "    $y = new class {\n"
            "        const FN_ANON = 2;\n"
            "    };\n"
            "}\n"
        )
        syms = _symbols_for(src, "php")
        assert [s["name"] for s in syms if s["kind"] == "constant"] == []

    def test_braced_namespace_const_captured(self):
        # Braced namespace bodies are compound_statement nodes — the scope
        # gate uses function/closure node types (not compound_statement)
        # precisely so namespace-scope consts stay captured.
        src = "<?php\nnamespace App {\n    const NS_CONST = 1;\n}\n"
        syms = _symbols_for(src, "php")
        names = [s["name"] for s in syms if s["kind"] == "constant"]
        assert names == ["NS_CONST"]


class _PhpStubNode:
    """Minimal node stand-in (explicit parent, no MagicMock chains)."""

    def __init__(self, type_, children=(), fields=None):
        self.type = type_
        self.children = list(children)
        self._fields = fields or {}
        self.parent = None
        self.start_point = (0, 0)
        self.end_point = (0, 0)

    def child_by_field_name(self, name):
        return self._fields.get(name)


class TestPhpConstantsGuards:
    """Cover defensive branches unreachable from valid PHP source (codecov)."""

    def test_nameless_const_element_skipped(self):
        from tree_sitter_analyzer._ast_extraction import _php_constants

        nameless = _PhpStubNode("const_element", children=[])
        decl = _PhpStubNode("const_declaration", children=[nameless])
        assert _php_constants(decl, "") == []

    def test_php_helper_name_field_fast_path(self):
        from tree_sitter_analyzer.languages.php_helpers import (
            _build_php_constant_variable,
        )

        name = _PhpStubNode("name")
        element = _PhpStubNode("const_element", fields={"name": name})
        decl = _PhpStubNode("const_declaration", children=[element])
        var = _build_php_constant_variable(
            decl, element, "", lambda n: "FAST", lambda n: [], lambda n: []
        )
        assert var is not None
        assert var.name == "FAST"


# ---------------------------------------------------------------------------
# Issue #626: JS/TS function-local variables no longer over-captured
# ---------------------------------------------------------------------------


_JSTS_JS_SRC = """\
const TOP_CONST = 1;
let topLet = 2;
var topVar = 3;
if (flag) { const ifWrapped = 4; }
try { const tryWrapped = 5; } catch (e) { const catchLocal = 6; }
function f() { const localInFunc = 7; var hoisted = 8; }
const fexpr = function () { const localInFexpr = 9; };
const arrow = () => { const localInArrow = 10; };
function* gen() { const localInGen = 11; }
const genExpr = function* () { const localInGenExpr = 12; };
class C {
  m() { const localInMethod = 13; }
  static { const staticBlockLocal = 14; }
}
"""

_JSTS_TS_SRC = """\
const TOP_CONST = 1;
let topLet = 2;
var topVar = 3;
namespace NS {
  const nsConst = 4;
  export const NS_EXPORTED = 5;
}
module M { const mConst = 6; }
declare module "ext" { const ambientConst: number; }
function f(): void { const localInFunc = 7; }
class C { m(): void { const localInMethod = 8; } }
const arrow = (): void => { const localInArrow = 9; };
"""


class TestJsTsLocalVariableContraction:
    """Issue #626 — JS/TS function-local declarators must NOT reach
    ast_symbol_rows; module/top-level (incl. if/try-wrapped, #612 guarantee)
    and TS namespace-level declarators stay kind="variable"."""

    def _variables(self, src: str, lang: str) -> list[str]:
        return sorted(
            s["name"] for s in _symbols_for(src, lang) if s["kind"] == "variable"
        )

    def test_js_exactly_the_module_level_declarators_survive(self):
        # catchLocal: a module-level catch block is a statement_block outside
        # any function — kept by design (statement_block deliberately absent
        # from the scope set, preserving the #612 if/try guarantee).
        assert self._variables(_JSTS_JS_SRC, "javascript") == [
            "TOP_CONST",
            "arrow",
            "catchLocal",
            "fexpr",
            "genExpr",
            "ifWrapped",
            "topLet",
            "topVar",
            "tryWrapped",
        ]

    def test_js_function_and_generator_locals_dropped(self):
        names = self._variables(_JSTS_JS_SRC, "javascript")
        for local in (
            "localInFunc",
            "hoisted",
            "localInFexpr",
            "localInGen",
            "localInGenExpr",
        ):
            assert local not in names

    def test_js_arrow_method_and_static_block_locals_dropped(self):
        names = self._variables(_JSTS_JS_SRC, "javascript")
        for local in ("localInArrow", "localInMethod", "staticBlockLocal"):
            assert local not in names

    def test_ts_module_and_namespace_level_declarators_survive(self):
        assert self._variables(_JSTS_TS_SRC, "typescript") == [
            "NS_EXPORTED",
            "TOP_CONST",
            "ambientConst",
            "arrow",
            "mConst",
            "nsConst",
            "topLet",
            "topVar",
        ]

    def test_ts_locals_dropped(self):
        names = self._variables(_JSTS_TS_SRC, "typescript")
        for local in ("localInFunc", "localInMethod", "localInArrow"):
            assert local not in names

    def test_tsx_maps_to_typescript_language_id(self):
        # The ast_cache path only ever delivers "javascript"/"typescript" for
        # this family — .tsx (and .jsx -> "javascript") included — so the
        # language gate on those two ids covers every indexed file.
        from tree_sitter_analyzer._lang_extension_map import EXT_TO_LANG

        assert EXT_TO_LANG[".tsx"] == "typescript"
        assert EXT_TO_LANG[".jsx"] == "javascript"

    def test_tsx_shaped_source_contracts_under_typescript_id(self):
        # JSX-free .tsx content goes down the identical typescript path.
        # (Known limitation, NOT pinned: .tsx WITH JSX is parsed by the
        # typescript grammar — ERROR recovery flattens function bodies, so
        # locals in broken regions may survive; pre-existing, outside #626.)
        src = "const TOP = 1;\nfunction Comp() { const inner = 2; }\n"
        assert self._variables(src, "typescript") == ["TOP"]

    def test_java_locals_now_contracted_too(self):
        # Re-pinned when the Java half of #626 landed (extractor v9): Java
        # method locals are dropped as well — full Java surface pinned in
        # TestJavaLocalVariableContraction below.
        src = "class A { void m() { int local = 1; } }\n"
        assert self._variables(src, "java") == []


class TestJsTsErrorRegionHardening:
    """Codex P2 on #629: declarations inside error-recovered regions have
    undecidable scope — they must not be emitted (better unindexed than a
    function-local masquerading as a module symbol)."""

    def test_declaration_inside_error_node_not_emitted(self):
        # Deliberately broken TSX-ish source that forces ERROR recovery at
        # the point of the declaration.
        src = "const Comp = () => {\n  const Math = 1;\n  return <div//;\n};\nconst TOP = 2;\n"
        syms = _symbols_for(src, "typescript")
        names = [s["name"] for s in syms if s["kind"] == "variable"]
        assert "Math" not in names
        assert "TOP" in names


# ---------------------------------------------------------------------------
# Issue #626 (Java half): function-local variables no longer over-captured
# ---------------------------------------------------------------------------


_JAVA_626_SRC = """\
interface Iface {
    int IFACE_CONST = 99;
}

record Rec(int x) {
    static final int REC_CONST = 7;
    Rec {
        int compactCtorLocal = 100;
    }
}

class A {
    static final int STATIC_FINAL = 1;
    int plainField = 2;
    static int staticField = 3;
    Runnable fieldLambda = () -> { int lambdaFieldLocal = 4; };

    static { int staticInitLocal = 5; }
    { int instanceInitLocal = 6; }
    A() { int ctorLocal = 7; }

    void m() {
        int local = 10;
        for (int i = 0; i < 3; i++) { int loopBody = 11; }
        try { int tryLocal = 12; } catch (Exception e) { int catchLocal = 13; }
    }
}
"""


class TestJavaLocalVariableContraction:
    """Issue #626 (Java half) — method/ctor/compact-ctor/lambda/initializer
    locals must NOT reach ast_symbol_rows; class fields (incl. record
    constants) and interface constants stay kind="variable". Fields are safe
    from the ``block`` scope node: they route ``class_body >
    field_declaration`` and never through a ``block`` (live-parse verified)."""

    def _variables(self, src: str, lang: str) -> list[str]:
        return sorted(
            s["name"] for s in _symbols_for(src, lang) if s["kind"] == "variable"
        )

    def test_java_exactly_fields_and_constants_survive(self):
        assert self._variables(_JAVA_626_SRC, "java") == [
            "IFACE_CONST",
            "REC_CONST",
            "STATIC_FINAL",
            "fieldLambda",
            "plainField",
            "staticField",
        ]

    def test_java_method_ctor_and_compact_ctor_locals_dropped(self):
        names = self._variables(_JAVA_626_SRC, "java")
        for local in (
            "local",
            "i",
            "loopBody",
            "tryLocal",
            "catchLocal",
            "ctorLocal",
            "compactCtorLocal",
        ):
            assert local not in names

    def test_java_lambda_and_initializer_locals_dropped(self):
        # lambdaFieldLocal sits in a lambda hanging off a FIELD initializer —
        # the only shape where ``lambda_expression`` (not method/block) is the
        # gating scope node; the field holder itself stays captured.
        names = self._variables(_JAVA_626_SRC, "java")
        for local in ("lambdaFieldLocal", "staticInitLocal", "instanceInitLocal"):
            assert local not in names

    def test_csharp_locals_now_contracted_too(self):
        # Re-pinned when the C# follow-up (#628) landed (extractor v10): C#
        # method locals are dropped as well — full C# surface pinned in
        # TestCSharpLocalVariableContraction below.
        src = "class A { void M() { int local = 1; } }\n"
        assert self._variables(src, "csharp") == []


class TestJavaErrorRegionHardening:
    """#629 ERROR-hardening precedent applied to Java: declarations inside
    error-recovered regions have undecidable scope — they must not be emitted
    (better unindexed than a lambda local masquerading as a field)."""

    def test_declaration_inside_error_node_not_emitted(self):
        # Unterminated lambda-in-field shatters the class into an ERROR node;
        # 'leaked' currently surfaces as ERROR > local_variable_declaration
        # (live-parse verified) — it must produce no row.
        src = "class A {\n  Runnable r = () -> {\n    int leaked = 1;\n"
        syms = _symbols_for(src, "java")
        assert [s["name"] for s in syms if s["kind"] == "variable"] == []


# ---------------------------------------------------------------------------
# Issue #628 (C#): function-local variables no longer over-captured
# ---------------------------------------------------------------------------


_CSHARP_628_SRC = """\
using System;

int topLevelVar = 1;
var topLevelVar2 = "x";
if (topLevelVar > 0) { int topLevelIfLocal = 2; }
try { int topTryLocal = 3; } catch (Exception e) { int topCatchLocal = 4; }

interface IFace {
    const int IFACE_CONST = 99;
}

record Rec(int X) {
    public static readonly int REC_CONST = 7;
}

class A {
    const int CONST_FIELD = 1;
    static readonly int STATIC_READONLY = 2;
    int plainField = 3;
    static int staticField = 4;
    public int AccessorProp {
        get { int accessorLocal = 60; return accessorLocal; }
    }
    public int this[int idx] {
        get { int indexerLocal = 61; return indexerLocal; }
    }
    public event EventHandler Ev {
        add { int evAddLocal = 62; }
        remove { }
    }
    public static A operator +(A a, A b) { int opLocal = 63; return a; }
    public static implicit operator int(A a) { int convLocal = 64; return 0; }
    Action fieldLambda = () => { int lambdaFieldLocal = 8; };
    Action fieldAnonMethod = delegate () { int anonMethodLocal = 9; };

    static A() { int staticCtorLocal = 10; }
    A() { int ctorLocal = 11; }
    ~A() { int dtorLocal = 12; }

    void M() {
        int methodLocal = 20;
        for (int i = 0; i < 3; i++) { int loopBody = 21; }
        try { int tryLocal = 22; } catch (Exception e) { int catchLocal = 23; }
        int LocalFunc() {
            int localFuncLocal = 24;
            return localFuncLocal;
        }
        Action lam = () => { int lambdaLocal = 25; };
    }
}
"""


class TestCSharpLocalVariableContraction:
    """Issue #628 — C# method/ctor/dtor/local-fn/lambda/accessor/operator
    locals must NOT reach ast_symbol_rows; class/interface/record fields
    (const, static readonly, plain) stay kind="variable". Unlike Java (#630),
    ``block`` is NOT in the scope set: C# top-level statements put blocks at
    compilation-unit level (live-parse: ``block < if_statement <
    global_statement``), so a block-keyed set would drop if/try-wrapped
    top-level declarators and break the #612 module-scope guarantee. Fields
    are safe regardless: they route ``declaration_list > field_declaration``
    and never through any function-like node (live-parse verified)."""

    def _variables(self, src: str, lang: str) -> list[str]:
        return sorted(
            s["name"] for s in _symbols_for(src, lang) if s["kind"] == "variable"
        )

    def test_csharp_exactly_fields_constants_and_top_level_survive(self):
        assert self._variables(_CSHARP_628_SRC, "csharp") == [
            "CONST_FIELD",
            "IFACE_CONST",
            "REC_CONST",
            "STATIC_READONLY",
            "fieldAnonMethod",
            "fieldLambda",
            "plainField",
            "staticField",
            "topCatchLocal",
            "topLevelIfLocal",
            "topLevelVar",
            "topLevelVar2",
            "topTryLocal",
        ]

    def test_csharp_method_ctor_dtor_and_local_fn_locals_dropped(self):
        names = self._variables(_CSHARP_628_SRC, "csharp")
        for local in (
            "methodLocal",
            "i",
            "loopBody",
            "tryLocal",
            "catchLocal",
            "localFuncLocal",
            "lam",
            "lambdaLocal",
            "ctorLocal",
            "staticCtorLocal",
            "dtorLocal",
        ):
            assert local not in names

    def test_csharp_lambda_accessor_and_operator_locals_dropped(self):
        # lambdaFieldLocal/anonMethodLocal sit in lambdas hanging off FIELD
        # initializers — the only shapes where lambda_expression /
        # anonymous_method_expression (not a method) is the gating scope
        # node; the field holders themselves stay captured. accessor bodies
        # (property/indexer/event) gate via accessor_declaration; operator
        # bodies via (conversion_)operator_declaration.
        names = self._variables(_CSHARP_628_SRC, "csharp")
        for local in (
            "lambdaFieldLocal",
            "anonMethodLocal",
            "accessorLocal",
            "indexerLocal",
            "evAddLocal",
            "opLocal",
            "convLocal",
        ):
            assert local not in names

    def test_csharp_top_level_statement_vars_kept(self):
        # C# 9 top-level statements ARE the program's module scope —
        # plain, if-wrapped, and try-wrapped declarators all stay captured
        # (mirrors the #612 if/try-wrapped module-level guarantee).
        names = self._variables(_CSHARP_628_SRC, "csharp")
        for kept in (
            "topLevelVar",
            "topLevelVar2",
            "topLevelIfLocal",
            "topTryLocal",
            "topCatchLocal",
        ):
            assert kept in names


class TestCSharpErrorRegionHardening:
    """#629 ERROR-hardening precedent applied to C#: declarations inside
    error-recovered regions have undecidable scope — they must not be emitted
    (better unindexed than a lambda local masquerading as a field)."""

    def test_declaration_inside_error_node_not_emitted(self):
        # Unterminated lambda-in-field shatters the class into an ERROR node;
        # 'leaked' currently surfaces as ERROR > local_declaration_statement
        # (live-parse verified) — it must produce no row.
        src = "class A {\n  Action r = () => {\n    int leaked = 1;\n"
        syms = _symbols_for(src, "csharp")
        assert [s["name"] for s in syms if s["kind"] == "variable"] == []
