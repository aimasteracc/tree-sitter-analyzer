"""Issue #588 — Go interface method signatures owned by their interface.

Before this fix: ``type Reader interface { Read(p []byte) (n int, err error) }``
reported methods=[] because ``method_elem`` children of ``interface_type`` were
never extracted — an agent asking "what methods does Reader require" got an
empty interface.

After this fix: each ``method_elem`` is emitted as a Function with
``receiver_type`` = the interface name (the innermost-span ownership convention
from #532/#474), ``is_method=True``, and real parameters/return type.
"""

from __future__ import annotations

import pytest

pytest.importorskip("tree_sitter_go", reason="tree-sitter-go not installed")


def _extract(src: str):
    """Run the Go plugin's function + class extraction over ``src``."""
    import tree_sitter
    import tree_sitter_go

    from tree_sitter_analyzer.languages.go_plugin import GoElementExtractor

    lang = tree_sitter.Language(tree_sitter_go.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(src.encode())
    extractor = GoElementExtractor()
    return (
        extractor.extract_functions(tree, src),
        extractor.extract_classes(tree, src),
    )


class TestReaderInterfaceMethod:
    """Single-method interface: signature fully extracted and owned."""

    SRC = (
        "package main\n"
        "\n"
        "// Reader is an interface for reading data.\n"
        "type Reader interface {\n"
        "\t// Read reads data into the provided buffer.\n"
        "\tRead(p []byte) (n int, err error)\n"
        "}\n"
    )

    def test_read_signature_extracted_and_owned(self) -> None:
        functions, classes = self._parsed()
        assert len(functions) == 1, f"got {[f.name for f in functions]}"
        read = functions[0]
        assert read.name == "Read"
        assert read.parameters == ["p []byte"]
        assert read.return_type == "(n int, err error)"
        assert read.receiver_type == "Reader"
        assert read.is_method is True
        assert read.receiver is None  # interface signatures have no receiver var
        assert read.visibility == "public"
        # span lands inside the interface so find_class_name containment works
        assert read.start_line == 6
        assert read.end_line == 6

    def test_interface_class_still_extracted(self) -> None:
        _, classes = self._parsed()
        assert len(classes) == 1
        assert classes[0].name == "Reader"
        assert classes[0].class_type == "interface"

    def _parsed(self):
        return _extract(self.SRC)


class TestReadWriterEmbeddingNoPhantoms:
    """Embedding-only interface: embeds preserved, zero phantom methods."""

    SRC = "package main\ntype ReadWriter interface {\n\tReader\n\tWriter\n}\n"

    def test_no_phantom_methods(self) -> None:
        functions, _ = _extract(self.SRC)
        assert len(functions) == 0, f"got {[f.name for f in functions]}"

    def test_embedding_still_reflected(self) -> None:
        _, classes = _extract(self.SRC)
        assert len(classes) == 1
        assert classes[0].interfaces == ["Reader", "Writer"]


class TestEmptyInterface:
    """``type Empty interface {}`` emits no functions."""

    def test_no_methods(self) -> None:
        functions, classes = _extract("package main\ntype Empty interface {}\n")
        assert len(functions) == 0
        assert len(classes) == 1
        assert classes[0].name == "Empty"


class TestAnonymousInterfaceParamIgnored:
    """An anonymous ``interface{ ... }`` in a parameter is NOT a named owner."""

    SRC = (
        "package main\n"
        "func Use(r interface{ Close() error }) error {\n"
        "\treturn r.Close()\n"
        "}\n"
    )

    def test_only_the_real_function_extracted(self) -> None:
        functions, _ = _extract(self.SRC)
        assert [f.name for f in functions] == ["Use"]


class TestGuardBranches:
    """Defensive guards in extract_go_interface_methods (direct unit calls)."""

    @staticmethod
    def _node(node_type: str, fields: dict | None = None, children: list | None = None):
        from unittest.mock import MagicMock

        node = MagicMock()
        node.parent = None  # MagicMock parent chains are an OOM hazard
        node.type = node_type
        node.children = children or []
        node.child_by_field_name.side_effect = (fields or {}).get
        return node

    def _extract(self, spec_node):
        from tree_sitter_analyzer.languages._go_function_helpers import (
            extract_go_interface_methods,
        )

        return extract_go_interface_methods(spec_node, lambda n: "", [])

    def test_missing_name_or_type_field_returns_empty(self) -> None:
        spec = self._node("type_spec", fields={"type": self._node("interface_type")})
        assert self._extract(spec) == []

    def test_non_interface_type_spec_returns_empty(self) -> None:
        spec = self._node(
            "type_spec",
            fields={
                "name": self._node("type_identifier"),
                "type": self._node("struct_type"),
            },
        )
        assert self._extract(spec) == []

    def test_empty_interface_name_text_returns_empty(self) -> None:
        spec = self._node(
            "type_spec",
            fields={
                "name": self._node("type_identifier"),
                "type": self._node("interface_type"),
            },
        )
        # get_node_text returns "" for every node → name guard fires
        assert self._extract(spec) == []

    def test_nameless_method_elem_skipped(self) -> None:
        from tree_sitter_analyzer.languages._go_function_helpers import (
            extract_go_interface_methods,
        )

        bad_elem = self._node("method_elem")  # no "name" field
        iface = self._node("interface_type", children=[bad_elem])
        spec = self._node(
            "type_spec",
            fields={"name": self._node("type_identifier"), "type": iface},
        )
        result = extract_go_interface_methods(spec, lambda n: "R", [])
        assert result == []

    def test_exception_returns_empty(self) -> None:
        from unittest.mock import MagicMock

        from tree_sitter_analyzer.languages._go_function_helpers import (
            extract_go_interface_methods,
        )

        spec = MagicMock()
        spec.parent = None
        spec.child_by_field_name.side_effect = RuntimeError("boom")
        assert extract_go_interface_methods(spec, lambda n: "", []) == []


class TestAliasToInterface:
    """``type R = interface{ M() }`` (type_alias) also owns its signatures."""

    SRC = "package main\ntype R = interface{ M() }\n"

    def test_alias_interface_method_owned(self) -> None:
        functions, _ = _extract(self.SRC)
        assert len(functions) == 1
        assert functions[0].name == "M"
        assert functions[0].receiver_type == "R"
        assert functions[0].is_method is True
