"""Tests for C/C++ extraction bugs #751, #752, #753.

#751: C++ nested struct/class inside class body not extracted.
#752: C typedef struct should not produce duplicate entries (regression guard).
#753: C anonymous nested union/struct inside struct should be skipped (not extracted
      with empty or line-number-based synthetic name).
"""

import tree_sitter
import tree_sitter_c
import tree_sitter_cpp

from tree_sitter_analyzer.languages.c_plugin import CElementExtractor
from tree_sitter_analyzer.languages.cpp_plugin import CppElementExtractor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_c(code: str) -> tree_sitter.Tree:
    lang = tree_sitter.Language(tree_sitter_c.language())
    parser = tree_sitter.Parser(lang)
    return parser.parse(code.encode("utf-8"))


def _parse_cpp(code: str) -> tree_sitter.Tree:
    lang = tree_sitter.Language(tree_sitter_cpp.language())
    parser = tree_sitter.Parser(lang)
    return parser.parse(code.encode("utf-8"))


# ---------------------------------------------------------------------------
# Bug #751 — C++ nested struct/class not extracted
# ---------------------------------------------------------------------------


class TestBug751CppNestedClass:
    """C++ inner class/struct inside a class body must be extracted."""

    def test_nested_struct_inside_class(self) -> None:
        """Simple struct nested inside a class body."""
        code = """\
class Outer {
public:
    struct Inner { int x; };
    int y;
};
"""
        tree = _parse_cpp(code)
        ext = CppElementExtractor()
        classes = ext.extract_classes(tree, code)
        names = [c.name for c in classes]

        assert "Outer" in names
        assert "Inner" in names
        assert len(names) == 2

    def test_nested_class_inside_class(self) -> None:
        """class nested inside a class body."""
        code = """\
class Outer {
public:
    class Inner {
    public:
        int value;
        void doSomething() {}
    };
    int z;
};
"""
        tree = _parse_cpp(code)
        ext = CppElementExtractor()
        classes = ext.extract_classes(tree, code)
        names = [c.name for c in classes]

        assert "Outer" in names
        assert "Inner" in names
        assert len(names) == 2

    def test_nested_struct_has_parent_class(self) -> None:
        """Nested struct should have parent_class set to enclosing class name."""
        code = """\
class Outer {
public:
    struct Inner { int x; };
};
"""
        tree = _parse_cpp(code)
        ext = CppElementExtractor()
        classes = ext.extract_classes(tree, code)

        inner = next(c for c in classes if c.name == "Inner")
        assert inner.parent_class == "Outer"

    def test_multiple_nested_types(self) -> None:
        """Multiple nested types all extracted."""
        code = """\
class Container {
public:
    struct Point { double x; double y; };
    struct Size { double w; double h; };
    int count;
};
"""
        tree = _parse_cpp(code)
        ext = CppElementExtractor()
        classes = ext.extract_classes(tree, code)
        names = sorted(c.name for c in classes)

        assert names == ["Container", "Point", "Size"]

    def test_outer_class_type_preserved(self) -> None:
        """Outer class class_type stays 'class'."""
        code = """\
class Outer {
    struct Inner { int x; };
};
"""
        tree = _parse_cpp(code)
        ext = CppElementExtractor()
        classes = ext.extract_classes(tree, code)

        outer = next(c for c in classes if c.name == "Outer")
        inner = next(c for c in classes if c.name == "Inner")

        assert outer.class_type == "class"
        assert inner.class_type == "struct"

    def test_field_type_reference_is_not_nested_class(self) -> None:
        """struct Point field references inside Rect must not emit bogus nested Point."""
        code = """\
struct Point { int x; int y; };
struct Rect { struct Point br; };
"""
        tree = _parse_cpp(code)
        ext = CppElementExtractor()
        classes = ext.extract_classes(tree, code)
        names = [c.name for c in classes]

        assert names.count("Point") == 1
        assert not any(c.name == "Point" and c.parent_class == "Rect" for c in classes)

    def test_template_nested_struct_has_parent_class(self) -> None:
        code = """\
class Outer {
public:
    template <typename T> struct Inner {};
};
"""
        tree = _parse_cpp(code)
        ext = CppElementExtractor()
        inner = next(c for c in ext.extract_classes(tree, code) if c.name == "Inner")

        assert inner.parent_class == "Outer"
        assert "template" in inner.modifiers

    def test_union_nested_struct_has_parent_class(self) -> None:
        code = """\
union Outer {
    struct Inner { int x; };
};
"""
        tree = _parse_cpp(code)
        ext = CppElementExtractor()
        inner = next(c for c in ext.extract_classes(tree, code) if c.name == "Inner")

        assert inner.parent_class == "Outer"


# ---------------------------------------------------------------------------
# Bug #752 — C typedef struct regression guard (no duplicate entries)
# ---------------------------------------------------------------------------


class TestBug752CTypedefStructNoDuplicate:
    """typedef struct { ... } Name must produce exactly one entry."""

    def test_anonymous_typedef_struct_single_entry(self) -> None:
        """Simplest case: typedef struct { ... } MyType produces exactly one entry."""
        code = "typedef struct { int x; } MyType;\n"
        tree = _parse_c(code)
        ext = CElementExtractor()
        classes = ext.extract_classes(tree, code)

        assert len(classes) == 1
        assert classes[0].name == "MyType"
        assert classes[0].class_type == "struct"

    def test_anonymous_typedef_struct_name_not_synthetic(self) -> None:
        """typedef struct { ... } MyType must not also emit an anonymous_struct_ entry."""
        code = "typedef struct { int x; } MyType;\n"
        tree = _parse_c(code)
        ext = CElementExtractor()
        classes = ext.extract_classes(tree, code)

        names = [c.name for c in classes]
        # No synthetic anonymous name should appear alongside MyType
        assert not any(n.startswith("anonymous_struct_") for n in names)

    def test_named_typedef_struct_single_entry(self) -> None:
        """typedef struct Foo { ... } Foo produces exactly one entry (no double Foo)."""
        code = "typedef struct Foo { int x; int y; } Foo;\n"
        tree = _parse_c(code)
        ext = CElementExtractor()
        classes = ext.extract_classes(tree, code)

        names = [c.name for c in classes]
        assert names.count("Foo") == 1
        assert len(classes) == 1

    def test_multiple_independent_typedefs(self) -> None:
        """Multiple typedef structs each produce exactly one entry."""
        code = "typedef struct { int x; } TypeA;\ntypedef struct { float y; } TypeB;\n"
        tree = _parse_c(code)
        ext = CElementExtractor()
        classes = ext.extract_classes(tree, code)

        names = [c.name for c in classes]
        assert len(classes) == 2
        assert "TypeA" in names
        assert "TypeB" in names


# ---------------------------------------------------------------------------
# Bug #753 — C anonymous nested union/struct should be skipped
# ---------------------------------------------------------------------------


class TestBug753CAnonymousNestedContainerSkipped:
    """Anonymous nested unions/structs inside a typedef struct must NOT be extracted
    with empty or synthetic line-based names — they should be silently skipped."""

    def test_anonymous_nested_union_skipped(self) -> None:
        """typedef struct { union { int a; float b; } data; } Container — only
        Container is extracted; the anonymous inner union is not."""
        code = "typedef struct {\n    union { int a; float b; } data;\n} Container;\n"
        tree = _parse_c(code)
        ext = CElementExtractor()
        classes = ext.extract_classes(tree, code)

        names = [c.name for c in classes]
        assert len(classes) == 1
        assert names == ["Container"]

    def test_anonymous_nested_struct_skipped(self) -> None:
        """Nested anonymous struct with a field name is skipped."""
        code = "struct Outer {\n    struct { int x; int y; } coords;\n};\n"
        tree = _parse_c(code)
        ext = CElementExtractor()
        classes = ext.extract_classes(tree, code)

        names = [c.name for c in classes]
        assert len(classes) == 1
        assert names == ["Outer"]

    def test_no_anonymous_synthetic_name_emitted(self) -> None:
        """No anonymous_union_N or anonymous_struct_N name should appear for
        nested containers that have a field identifier (e.g., data, coords)."""
        code = (
            "typedef struct {\n"
            "    union { int a; float b; } data;\n"
            "    struct { int x; int y; } pos;\n"
            "} Container;\n"
        )
        tree = _parse_c(code)
        ext = CElementExtractor()
        classes = ext.extract_classes(tree, code)

        names = [c.name for c in classes]
        assert not any(n.startswith("anonymous_union_") for n in names)
        assert not any(n.startswith("anonymous_struct_") for n in names)

    def test_named_nested_struct_is_extracted(self) -> None:
        """A NAMED nested struct (with type_identifier) inside a struct body IS extracted.
        Contrast with the anonymous case above — named types have identity."""
        code = "struct Outer {\n    struct Inner { int x; };\n    int y;\n};\n"
        tree = _parse_c(code)
        ext = CElementExtractor()
        classes = ext.extract_classes(tree, code)

        names = sorted(c.name for c in classes)
        assert names == ["Inner", "Outer"]


class TestBitfields:
    """Unnamed C/C++ bitfields are padding, not addressable field symbols."""

    def test_c_unnamed_bitfield_is_skipped(self) -> None:
        code = "struct Flags { unsigned : 1; unsigned enabled : 1; };\n"
        tree = _parse_c(code)
        ext = CElementExtractor()
        names = [v.name for v in ext.extract_variables(tree, code)]

        assert names == ["enabled"]

    def test_cpp_unnamed_bitfield_is_skipped(self) -> None:
        code = "struct Flags { unsigned : 1; unsigned enabled : 1; };\n"
        tree = _parse_cpp(code)
        ext = CppElementExtractor()
        names = [v.name for v in ext.extract_variables(tree, code)]

        assert names == ["enabled"]
