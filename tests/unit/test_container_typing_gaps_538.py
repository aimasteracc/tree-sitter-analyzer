"""Issue #538 — per-language container/typing gap fixes (RED→GREEN).

Covers the six items from the sweep digest:
1. Go: ``type X = []string`` alias present as class_type="type_alias"
2. Go: interface embedding reflected in Class.interfaces
3. Rust: trait abstract method (function_signature_item) extracted with is_abstract=True
4. Python: ``class Animal(ABC)`` → class_type="abstract_class"
5. TS: ``abstract validate()`` → is_abstract=True on the Function
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers: language availability guards
# ---------------------------------------------------------------------------
def _go_lang():
    try:
        import tree_sitter
        import tree_sitter_go

        return tree_sitter.Language(tree_sitter_go.language())
    except Exception:
        return None


def _rust_lang():
    try:
        import tree_sitter
        import tree_sitter_rust

        return tree_sitter.Language(tree_sitter_rust.language())
    except Exception:
        return None


def _ts_lang():
    try:
        import tree_sitter
        import tree_sitter_typescript

        return tree_sitter.Language(tree_sitter_typescript.language_typescript())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Go — type alias
# ---------------------------------------------------------------------------
@pytest.mark.skipif(_go_lang() is None, reason="tree-sitter-go not available")
def test_go_type_alias_extracted() -> None:
    """``type StringSlice = []string`` must be extracted as class_type='type_alias'.

    Before fix: _iter_type_specs only iterated 'type_spec' children, so
    'type_alias' siblings were silently dropped (issue #538 N1).
    """
    from tree_sitter import Parser

    from tree_sitter_analyzer.languages._go_type_helpers import extract_type_declaration

    lang = _go_lang()
    parser = Parser(lang)
    src = "package main\ntype StringSlice = []string\n"
    tree = parser.parse(src.encode())

    def get_text(n):
        return n.text.decode("utf-8", errors="replace") if n.text else ""

    def find(node, t, out):
        if node.type == t:
            out.append(node)
        for c in node.children:
            find(c, t, out)

    decls: list = []
    find(tree.root_node, "type_declaration", decls)
    assert len(decls) == 1, "expected exactly 1 type_declaration"

    results = extract_type_declaration(decls[0], get_text, src.split("\n"))
    assert len(results) == 1, f"expected 1 Class, got {len(results)}"
    cls = results[0]
    assert cls.name == "StringSlice"
    assert cls.class_type == "type_alias"


# ---------------------------------------------------------------------------
# Go — interface embedding
# ---------------------------------------------------------------------------
@pytest.mark.skipif(_go_lang() is None, reason="tree-sitter-go not available")
def test_go_interface_embedding_reflected() -> None:
    """Embedded interfaces in a composite interface must appear in Class.interfaces.

    Before fix: _go_struct_interfaces only handled struct_type; interface
    type_elem children were never visited (issue #538 N5).
    """
    from tree_sitter import Parser

    from tree_sitter_analyzer.languages._go_type_helpers import extract_type_declaration

    lang = _go_lang()
    parser = Parser(lang)
    src = "package main\ntype ReadWriter interface {\n    Reader\n    Writer\n}\n"
    tree = parser.parse(src.encode())

    def get_text(n):
        return n.text.decode("utf-8", errors="replace") if n.text else ""

    def find(node, t, out):
        if node.type == t:
            out.append(node)
        for c in node.children:
            find(c, t, out)

    decls: list = []
    find(tree.root_node, "type_declaration", decls)
    assert len(decls) == 1

    results = extract_type_declaration(decls[0], get_text, src.split("\n"))
    assert len(results) == 1
    cls = results[0]
    assert cls.class_type == "interface"
    assert "Reader" in cls.interfaces
    assert "Writer" in cls.interfaces
    assert len(cls.interfaces) == 2


# ---------------------------------------------------------------------------
# Rust — trait abstract method
# ---------------------------------------------------------------------------
@pytest.mark.skipif(_rust_lang() is None, reason="tree-sitter-rust not available")
def test_rust_trait_abstract_method_extracted() -> None:
    """A trait required-method (no body) must be extracted with is_abstract=True.

    Before fix: extract_functions only traversed 'function_item' (has body);
    'function_signature_item' (no body, ends with ';') was silently skipped
    (issue #538, Rust N2).
    """
    from tree_sitter import Parser

    from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

    lang = _rust_lang()
    parser = Parser(lang)
    src = (
        "trait Displayable {\n"
        "    fn display(&self);\n"
        "\n"
        "    fn summary(&self) -> String {\n"
        '        String::from("default")\n'
        "    }\n"
        "}\n"
    )
    tree = parser.parse(src.encode())
    extractor = RustElementExtractor()
    fns = extractor.extract_functions(tree, src)

    names = {f.name for f in fns}
    assert "display" in names, f"abstract method 'display' not extracted; got {names}"
    assert "summary" in names, (
        f"default-impl method 'summary' not extracted; got {names}"
    )

    by_name = {f.name: f for f in fns}
    assert by_name["display"].is_abstract is True
    assert by_name["summary"].is_abstract is False
    assert len(fns) == 2


# ---------------------------------------------------------------------------
# Python — ABC → abstract_class
# ---------------------------------------------------------------------------
def test_python_abc_class_type_is_abstract_class() -> None:
    """``class Animal(ABC)`` must produce class_type='abstract_class'.

    Before fix: build_class_element hard-coded class_type='class' for all
    classes; is_abstract was set but class_type stayed 'class' (issue #538).
    """
    from tree_sitter_analyzer.languages.python_plugin._element_builders import (
        ClassBuildInput,
        build_class_element,
    )

    data = ClassBuildInput(
        name="Animal",
        start_line=1,
        end_line=5,
        raw_text="class Animal(ABC):\n    pass",
        superclasses=["ABC"],
        decorators=[],
        docstring=None,
        current_module="",
        framework_type="",
    )
    cls = build_class_element(data)
    assert cls.class_type == "abstract_class"
    assert cls.is_abstract is True


def test_python_non_abc_class_type_unchanged() -> None:
    """A plain class without ABC must remain class_type='class'."""
    from tree_sitter_analyzer.languages.python_plugin._element_builders import (
        ClassBuildInput,
        build_class_element,
    )

    data = ClassBuildInput(
        name="Dog",
        start_line=1,
        end_line=3,
        raw_text="class Dog(Animal):\n    pass",
        superclasses=["Animal"],
        decorators=[],
        docstring=None,
        current_module="",
        framework_type="",
    )
    cls = build_class_element(data)
    assert cls.class_type == "class"
    assert cls.is_abstract is False


# ---------------------------------------------------------------------------
# TypeScript — abstract method is_abstract flag
# ---------------------------------------------------------------------------
@pytest.mark.skipif(_ts_lang() is None, reason="tree-sitter-typescript not available")
def test_ts_abstract_method_has_is_abstract_true() -> None:
    """``abstract validate(): boolean`` inside an abstract class must carry
    is_abstract=True on the extracted Function.

    Before fix: extract_abstract_method_signature returned a Function without
    setting is_abstract=True (issue #538, TS N5).
    """
    from tree_sitter import Parser

    from tree_sitter_analyzer.languages.typescript_plugin.extractor import (
        TypeScriptElementExtractor,
    )

    lang = _ts_lang()
    parser = Parser(lang)
    src = (
        "abstract class Shape {\n"
        "    abstract validate(): boolean;\n"
        "    describe(): string {\n"
        "        return 'shape';\n"
        "    }\n"
        "}\n"
    )
    tree = parser.parse(src.encode())
    extractor = TypeScriptElementExtractor()
    fns = extractor.extract_functions(tree, src)

    by_name = {f.name: f for f in fns}
    assert "validate" in by_name, (
        f"abstract method 'validate' missing; got {list(by_name)}"
    )
    assert by_name["validate"].is_abstract is True
    assert by_name["describe"].is_abstract is False
    assert len(fns) == 2
