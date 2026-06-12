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


class TestRustAbstractSignatureReturnType:
    """Cover the -> return-type branch of function_signature_item (codecov)."""

    CODE = """
trait Displayable {
    fn display(&self) -> String;
    fn plain(&self);
}
"""

    def test_signature_with_return_type(self):
        import tree_sitter
        import tree_sitter_rust

        from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

        lang = tree_sitter.Language(tree_sitter_rust.language())
        tree = tree_sitter.Parser(lang).parse(self.CODE.encode())
        fns = RustElementExtractor().extract_functions(tree, self.CODE)
        disp = [f for f in fns if f.name == "display"]
        plain = [f for f in fns if f.name == "plain"]
        assert len(disp) == 1
        assert disp[0].return_type == "String"
        assert len(plain) == 1
        assert plain[0].return_type == "()"


class TestGoAliasNonContainerType:
    """Cover the neither-struct-nor-interface fallback (codecov)."""

    CODE = "package p\n\ntype StringSlice = []string\n"

    def test_alias_to_slice_extracts(self):
        import tree_sitter
        import tree_sitter_go

        from tree_sitter_analyzer.languages.go_plugin import GoElementExtractor

        lang = tree_sitter.Language(tree_sitter_go.language())
        tree = tree_sitter.Parser(lang).parse(self.CODE.encode())
        classes = GoElementExtractor().extract_classes(tree, self.CODE)
        alias = [c for c in classes if c.name == "StringSlice"]
        assert len(alias) == 1
        assert alias[0].interfaces == []


class TestRustExternSignatureNotAbstract:
    """Codex P2 on #583: extern-block foreign fns also emit
    function_signature_item — they are FFI declarations, not trait methods."""

    CODE = """
extern "C" {
    fn puts(s: *const u8) -> i32;
}

trait Greet {
    fn hello(&self) -> String;
}
"""

    def test_extern_fn_excluded_trait_fn_kept(self):
        import tree_sitter
        import tree_sitter_rust

        from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

        lang = tree_sitter.Language(tree_sitter_rust.language())
        tree = tree_sitter.Parser(lang).parse(self.CODE.encode())
        funcs = RustElementExtractor().extract_functions(tree, self.CODE)
        names = [f.name for f in funcs]
        assert "puts" not in names
        trait_fns = [f for f in funcs if f.name == "hello"]
        assert len(trait_fns) == 1
        assert trait_fns[0].is_abstract is True


class TestPythonQualifiedAbcBase:
    """Codex P2 on #583: ``class Animal(abc.ABC)`` must classify as
    abstract_class even without an @abstractmethod in the body."""

    CODE = """import abc


class Animal(abc.ABC):
    pass


class Dog(Animal, abc.ABC):
    pass
"""

    @pytest.fixture
    def classes(self, tmp_path):
        import asyncio

        from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine

        p = tmp_path / "abc_sample.py"
        p.write_text(self.CODE, newline="\n")
        result = asyncio.run(get_analysis_engine().analyze_file(str(p)))
        return [e for e in result.elements if type(e).__name__ == "Class"]

    def test_qualified_abc_is_abstract(self, classes):
        animal = next(c for c in classes if c.name == "Animal")
        assert animal.class_type == "abstract_class"
        assert animal.superclass == "abc.ABC"

    def test_qualified_abc_in_interfaces(self, classes):
        dog = next(c for c in classes if c.name == "Dog")
        assert dog.class_type == "abstract_class"
        assert dog.superclass == "Animal"
        assert dog.interfaces == ["abc.ABC"]


class TestRustTraitSignatureSelfForms:
    """Cover _find_self_parameter branches for trait signatures (codecov)."""

    CODE = """
trait Consume {
    fn take(self: Box<Self>) -> String;
    fn peek(&self) -> i32;
}
"""

    def test_typed_self_parameter_binds_receiver(self):
        import tree_sitter
        import tree_sitter_rust

        from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

        lang = tree_sitter.Language(tree_sitter_rust.language())
        tree = tree_sitter.Parser(lang).parse(self.CODE.encode())
        funcs = RustElementExtractor().extract_functions(tree, self.CODE)
        take = next(f for f in funcs if f.name == "take")
        assert take.is_abstract is True
        peek = next(f for f in funcs if f.name == "peek")
        assert peek.is_abstract is True


class _RustStubNode:
    """Minimal tree-sitter node stand-in (explicit parent, no auto-chains)."""

    def __init__(
        self, type_: str = "function_signature_item", parent=None, fields=None
    ):
        self.type = type_
        self.parent = parent
        self._fields = fields or {}

    def child_by_field_name(self, name):
        return self._fields.get(name)


class TestRustSignatureStubFallbacks:
    """Cover guard branches unreachable from valid Rust source (codecov)."""

    @staticmethod
    def _extractor():
        from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

        return RustElementExtractor()

    def test_no_params_node_returns_none(self):
        node = _RustStubNode(parent=None)
        assert self._extractor()._find_self_parameter(node) is None

    def test_nameless_signature_in_trait_returns_none(self):
        trait = _RustStubNode(type_="trait_item", parent=None)
        body = _RustStubNode(type_="declaration_list", parent=trait)
        node = _RustStubNode(parent=body)
        assert self._extractor()._extract_function_signature(node) is None

    def test_orphan_node_not_inside_trait(self):
        node = _RustStubNode(parent=None)
        assert self._extractor()._inside_trait(node) is False


class TestRustFindSelfParameterDirect:
    """Cover the typed-self ``parameter`` branch of _find_self_parameter,
    unreachable through trait signatures (no impl owner there) — codecov."""

    def _signature_node(self, code: str):
        import tree_sitter
        import tree_sitter_rust

        lang = tree_sitter.Language(tree_sitter_rust.language())
        tree = tree_sitter.Parser(lang).parse(code.encode())
        stack = [tree.root_node]
        while stack:
            n = stack.pop()
            if n.type == "function_signature_item":
                return n
            stack.extend(n.children)
        raise AssertionError("no function_signature_item parsed")

    def _extractor(self, code: str):
        from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

        ex = RustElementExtractor()
        ex.source_code = code
        ex._content_bytes = code.encode()
        return ex

    def test_boxed_self_parameter_found(self):
        code = "trait T { fn take(self: Box<Self>); }"
        node = self._signature_node(code)
        ex = self._extractor(code)
        assert ex._find_self_parameter(node) == "self: Box<Self>"

    def test_plain_typed_parameter_is_not_self(self):
        code = "trait T { fn take(x: i32); }"
        node = self._signature_node(code)
        ex = self._extractor(code)
        assert ex._find_self_parameter(node) is None


class TestRustSignatureArrowPrefixStrip:
    """Cover the defensive '->' strip (mirrors function_item handler) — codecov."""

    def test_arrow_prefixed_return_type_stripped(self):
        from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

        content = b"x-> i32"

        class _SpanStub(_RustStubNode):
            def __init__(self, type_, parent=None, fields=None, span=(0, 0)):
                super().__init__(type_, parent=parent, fields=fields)
                self.start_byte, self.end_byte = span
                self.start_point = (0, self.start_byte)
                self.end_point = (0, self.end_byte)
                self.children = []

        trait = _SpanStub("trait_item")
        body = _SpanStub("declaration_list", parent=trait)
        name = _SpanStub("identifier", span=(0, 1))
        ret = _SpanStub("type", span=(1, 7))
        node = _SpanStub(
            "function_signature_item",
            parent=body,
            fields={"name": name, "return_type": ret, "parameters": None},
            span=(0, 7),
        )

        ex = RustElementExtractor()
        ex.source_code = content.decode()
        ex._content_bytes = content
        func = ex._extract_function_signature(node)
        assert func is not None
        assert func.return_type == "i32"


class TestRustSignatureGuardEdges:
    """Cover depth-cap exhaustion and the extractor except branch (codecov)."""

    def test_self_referencing_parent_chain_hits_depth_cap(self):
        from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

        node = _RustStubNode(parent=None)
        node.parent = node  # cycle: never None, never a terminator type
        assert RustElementExtractor()._inside_trait(node) is False

    def test_node_error_inside_trait_returns_none(self):
        from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

        class _ExplodingName(_RustStubNode):
            def child_by_field_name(self, name):
                raise RuntimeError("boom")

        trait = _RustStubNode(type_="trait_item", parent=None)
        body = _RustStubNode(type_="declaration_list", parent=trait)
        node = _ExplodingName(parent=body)
        assert RustElementExtractor()._extract_function_signature(node) is None


class TestGoStructInterfacesNoneNode:
    """Cover the type_node=None early return (codecov branch)."""

    def test_none_type_node_returns_empty(self):
        from tree_sitter_analyzer.languages._go_type_helpers import (
            _go_struct_interfaces,
        )

        assert _go_struct_interfaces(None, lambda n: "") == []


class TestPythonNodeHelpersQualifiedBase:
    """Cover the attribute branch in the _node_helpers superclass path
    (the fallback extractor path, not exercised by the engine tests)."""

    def test_attribute_base_extracted(self):
        import tree_sitter
        import tree_sitter_python

        from tree_sitter_analyzer.languages.python_plugin._node_helpers import (
            extract_superclasses_from_node,
        )

        code = "class A(abc.ABC, Base):\n    pass\n"
        lang = tree_sitter.Language(tree_sitter_python.language())
        tree = tree_sitter.Parser(lang).parse(code.encode())
        class_node = tree.root_node.children[0]
        assert extract_superclasses_from_node(class_node, code) == [
            "abc.ABC",
            "Base",
        ]
