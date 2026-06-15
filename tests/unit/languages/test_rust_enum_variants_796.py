"""Bug #796 — Rust enum variants must be extracted as Variable entries.

RED-first: these tests fail until extract_variables() walks enum_variant_list
and yields one Variable per enum_variant child.

Contract:
- Each enum variant becomes a Variable with variable_type == "enum_variant"
- The variant's name is the identifier text
- parent_class (or receiver_type) carries the enum name
- Unit-style variants (no fields) are extracted; tuple/struct variants too
"""

from __future__ import annotations

import pytest

_TS_RUST_AVAILABLE = False
try:
    import tree_sitter_rust  # noqa: F401

    _TS_RUST_AVAILABLE = True
except ImportError:
    pass


def _parse_rust(code: str):
    """Parse Rust code with tree-sitter-rust. Returns (tree, language) or None."""
    if not _TS_RUST_AVAILABLE:
        return None, None
    import tree_sitter
    import tree_sitter_rust

    caps = tree_sitter_rust.language()
    lang = tree_sitter.Language(caps)
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(code.encode("utf-8"))
    return tree, lang


@pytest.mark.skipif(
    not _TS_RUST_AVAILABLE,
    reason="#960: tree-sitter-rust not installed",
)
class TestRustEnumVariantExtraction:
    """extract_variables() must yield one Variable per enum variant."""

    def test_simple_enum_variants_are_extracted(self):
        """Direction enum: four unit variants must each become a Variable."""
        from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

        code = "enum Direction { North, South, East, West }"
        tree, _ = _parse_rust(code)
        extractor = RustElementExtractor()
        variables = extractor.extract_variables(tree, code)

        variant_names = {
            v.name
            for v in variables
            if getattr(v, "variable_type", None) == "enum_variant"
        }
        assert variant_names == {"North", "South", "East", "West"}, (
            f"Expected all four Direction variants, got: {variant_names}"
        )

    def test_option_like_enum_variants(self):
        """Option<T>-style enum: None and Some variants extracted."""
        from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

        code = "enum Option<T> { None, Some(T) }"
        tree, _ = _parse_rust(code)
        extractor = RustElementExtractor()
        variables = extractor.extract_variables(tree, code)

        variant_names = {
            v.name
            for v in variables
            if getattr(v, "variable_type", None) == "enum_variant"
        }
        assert variant_names == {"None", "Some"}, (
            f"Expected None and Some, got: {variant_names}"
        )

    def test_enum_variant_has_correct_variable_type(self):
        """Each variant must carry variable_type == 'enum_variant'."""
        from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

        code = "enum Color { Red, Green, Blue }"
        tree, _ = _parse_rust(code)
        extractor = RustElementExtractor()
        variables = extractor.extract_variables(tree, code)

        enum_variants = [
            v for v in variables if getattr(v, "variable_type", None) == "enum_variant"
        ]
        assert len(enum_variants) == 3, (
            f"Expected 3 enum_variant variables, got {len(enum_variants)}"
        )
        for v in enum_variants:
            assert v.variable_type == "enum_variant", (
                f"Variant {v.name} has wrong variable_type: {v.variable_type!r}"
            )

    def test_enum_variant_receiver_type_is_enum_name(self):
        """Each variant's receiver_type must be the containing enum name."""
        from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

        code = "enum Status { Active, Inactive }"
        tree, _ = _parse_rust(code)
        extractor = RustElementExtractor()
        variables = extractor.extract_variables(tree, code)

        variants = [
            v for v in variables if getattr(v, "variable_type", None) == "enum_variant"
        ]
        assert len(variants) == 2
        for v in variants:
            assert v.receiver_type == "Status", (
                f"Variant {v.name} receiver_type expected 'Status', "
                f"got {v.receiver_type!r}"
            )

    def test_struct_fields_and_enum_variants_coexist(self):
        """Struct fields (field_declaration) must not be crowded out by enum variant extraction."""
        from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

        code = "struct Point { x: f64, y: f64 }\nenum Dir { North, South }\n"
        tree, _ = _parse_rust(code)
        extractor = RustElementExtractor()
        variables = extractor.extract_variables(tree, code)

        field_names = {
            v.name
            for v in variables
            if getattr(v, "variable_type", None) != "enum_variant"
        }
        variant_names = {
            v.name
            for v in variables
            if getattr(v, "variable_type", None) == "enum_variant"
        }

        assert "x" in field_names and "y" in field_names, (
            f"Struct fields x/y missing from: {field_names}"
        )
        assert variant_names == {"North", "South"}, (
            f"Enum variants wrong: {variant_names}"
        )

    def test_struct_like_enum_variant_fields_do_not_leak(self):
        """Struct-like enum body fields are not ordinary struct fields (#960)."""
        from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

        code = (
            "struct Point { px: f64, py: f64 }\n"
            "enum Event { Move { x: i32, y: i32 }, Quit }\n"
        )
        tree, _ = _parse_rust(code)
        extractor = RustElementExtractor()
        variables = extractor.extract_variables(tree, code)

        field_names = [
            v.name
            for v in variables
            if getattr(v, "variable_type", None) != "enum_variant"
        ]
        variant_names = [
            v.name
            for v in variables
            if getattr(v, "variable_type", None) == "enum_variant"
        ]

        assert field_names == ["px", "py"]
        assert variant_names == ["Move", "Quit"]

    def test_enum_variant_visibility_inherits_enum_visibility(self):
        """Variants inherit the enclosing enum visibility for API consumers (#960)."""
        from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

        code = "pub enum Direction { North, South }"
        tree, _ = _parse_rust(code)
        extractor = RustElementExtractor()
        variables = extractor.extract_variables(tree, code)

        variants = [
            v for v in variables if getattr(v, "variable_type", None) == "enum_variant"
        ]

        assert [(v.name, v.visibility) for v in variants] == [
            ("North", "pub"),
            ("South", "pub"),
        ]

    def test_enum_variant_line_range_within_enum_span(self):
        """Variant start_line must be within the enclosing enum's line span."""
        from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

        code = "enum Suit {\n    Clubs,\n    Diamonds,\n    Hearts,\n    Spades,\n}\n"
        tree, _ = _parse_rust(code)
        extractor = RustElementExtractor()
        variables = extractor.extract_variables(tree, code)

        variants = [
            v for v in variables if getattr(v, "variable_type", None) == "enum_variant"
        ]
        assert len(variants) == 4, f"Expected 4 variants, got {len(variants)}"
        # All variants must be inside lines 1-6 (1-based)
        for v in variants:
            assert 1 <= v.start_line <= 6, (
                f"Variant {v.name} start_line={v.start_line} out of enum span"
            )

    def test_multiple_enums_variants_separate(self):
        """Two enums in one file: each set of variants has the correct receiver_type."""
        from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor

        code = "enum A { Foo, Bar }\nenum B { Baz, Qux }\n"
        tree, _ = _parse_rust(code)
        extractor = RustElementExtractor()
        variables = extractor.extract_variables(tree, code)

        variants = [
            v for v in variables if getattr(v, "variable_type", None) == "enum_variant"
        ]
        assert len(variants) == 4

        a_variants = {v.name for v in variants if v.receiver_type == "A"}
        b_variants = {v.name for v in variants if v.receiver_type == "B"}
        assert a_variants == {"Foo", "Bar"}, f"A variants wrong: {a_variants}"
        assert b_variants == {"Baz", "Qux"}, f"B variants wrong: {b_variants}"
