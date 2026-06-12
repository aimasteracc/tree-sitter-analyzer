"""C++ qualified-name ownership (#590).

``int math::max(...)`` defined OUTSIDE the ``namespace math { }`` block and
``T max(...)`` defined INSIDE it are the same logical symbol — both must
extract to the SAME representation: bare ``name`` + the owner in
``receiver_type`` (house convention, same as Go/Rust receivers #429/#474 and
field owners #535).
"""

import pytest
import tree_sitter
import tree_sitter_cpp

from tree_sitter_analyzer.formatters.cpp_formatter import CppTableFormatter
from tree_sitter_analyzer.languages.cpp_plugin import CppElementExtractor


@pytest.fixture
def extractor() -> CppElementExtractor:
    return CppElementExtractor()


def _parse(code: str):
    lang = tree_sitter.Language(tree_sitter_cpp.language())
    parser = tree_sitter.Parser(lang)
    return parser.parse(code.encode("utf-8"))


def _functions(extractor, code):
    return extractor.extract_functions(_parse(code), code)


def _one(funcs, name):
    matches = [f for f in funcs if f.name == name]
    assert len(matches) == 1, f"expected exactly one {name!r}, got {matches}"
    return matches[0]


# --- (a) function defined INSIDE the namespace block -----------------------


def test_in_namespace_function_gets_namespace_receiver(extractor):
    code = "namespace math {\nint min(int a, int b) { return a < b ? a : b; }\n}\n"
    func = _one(_functions(extractor, code), "min")
    assert func.receiver_type == "math"


def test_in_namespace_template_function_gets_namespace_receiver(extractor):
    # The literal sweep-N3 case (examples/sample.cpp): template fn in namespace.
    code = (
        "namespace math {\n"
        "template<typename T>\n"
        "T max(T a, T b) { return (a > b) ? a : b; }\n"
        "}\n"
    )
    func = _one(_functions(extractor, code), "max")
    assert func.receiver_type == "math"


# --- (b) qualified function defined OUTSIDE the namespace block ------------


def test_out_of_namespace_qualified_function_splits_qualifier(extractor):
    code = (
        "namespace math { int max(int a, int b); }\n"
        "int math::max(int a, int b) { return a > b ? a : b; }\n"
    )
    funcs = [f for f in _functions(extractor, code) if f.start_line == 2]
    assert len(funcs) == 1
    assert funcs[0].name == "max"
    assert funcs[0].receiver_type == "math"


def test_definition_styles_converge_to_same_representation(extractor):
    inside = _one(
        _functions(
            extractor, "namespace math {\nint max(int a, int b) { return a; }\n}\n"
        ),
        "max",
    )
    outside_funcs = _functions(extractor, "int math::max(int a, int b) { return a; }\n")
    assert len(outside_funcs) == 1
    outside = outside_funcs[0]
    assert (inside.name, inside.receiver_type) == ("max", "math")
    assert (outside.name, outside.receiver_type) == ("max", "math")


# --- (c) qualified out-of-class method definitions --------------------------


def test_out_of_class_qualified_method_splits_qualifier(extractor):
    code = "void math::Foo::bar() { }\n"
    funcs = _functions(extractor, code)
    assert len(funcs) == 1
    assert funcs[0].name == "bar"
    assert funcs[0].receiver_type == "math::Foo"


def test_out_of_class_constructor_is_flagged(extractor):
    code = "math::Foo::Foo() { }\n"
    funcs = _functions(extractor, code)
    assert len(funcs) == 1
    assert funcs[0].name == "Foo"
    assert funcs[0].receiver_type == "math::Foo"
    assert funcs[0].is_constructor is True


def test_out_of_class_destructor_is_not_constructor(extractor):
    code = "math::Foo::~Foo() { }\n"
    funcs = _functions(extractor, code)
    assert len(funcs) == 1
    assert funcs[0].name == "~Foo"
    assert funcs[0].receiver_type == "math::Foo"
    assert funcs[0].is_constructor is False


def test_out_of_class_method_inside_enclosing_namespace_composes(extractor):
    code = "namespace outer {\nvoid Foo::bar() { }\n}\n"
    func = _one(_functions(extractor, code), "bar")
    assert func.receiver_type == "outer::Foo"


# --- guards: representations that must NOT change ---------------------------


def test_in_class_method_keeps_bare_name_and_no_receiver(extractor):
    code = "namespace math {\nclass Foo {\npublic:\n    void bar() {}\n};\n}\n"
    func = _one(_functions(extractor, code), "bar")
    assert func.receiver_type is None


def test_global_function_has_no_receiver(extractor):
    func = _one(
        _functions(extractor, "int square(int x) { return x * x; }\n"), "square"
    )
    assert func.receiver_type is None


def test_conversion_operator_name_is_not_split(extractor):
    code = (
        'class Money {\npublic:\n    operator std::string() const { return ""; }\n};\n'
    )
    func = _one(_functions(extractor, code), "operator std::string")
    assert func.receiver_type is None


def test_anonymous_namespace_contributes_no_receiver(extractor):
    func = _one(_functions(extractor, "namespace {\nvoid hidden() { }\n}\n"), "hidden")
    assert func.receiver_type is None


def test_nested_namespaces_join_outer_to_inner(extractor):
    code = "namespace a {\nnamespace b {\nvoid f() { }\n}\n}\n"
    func = _one(_functions(extractor, code), "f")
    assert func.receiver_type == "a::b"


def test_cpp17_nested_namespace_specifier(extractor):
    code = "namespace a::b {\nvoid g() { }\n}\n"
    func = _one(_functions(extractor, code), "g")
    assert func.receiver_type == "a::b"


def test_namespace_name_accepts_str_text_nodes():
    # Defensive branch parity with _cpp_containing_class_name: node.text may
    # already be str on mocked/alternative node implementations.
    from tree_sitter_analyzer.languages._cpp_element_helpers import _cpp_namespace_name

    class _NameNode:
        type = "namespace_identifier"
        text = "math"
        parent = None

    class _NsNode:
        children = (_NameNode(),)
        parent = None

    assert _cpp_namespace_name(_NsNode()) == "math"


# --- table surface: Global Functions rows show the qualified owner ----------


def test_full_table_global_functions_show_qualified_name(extractor):
    code = (
        "namespace math {\n"
        "int min(int a, int b) { return a < b ? a : b; }\n"
        "}\n"
        "void math::Foo::bar() { }\n"
    )

    class _Result:
        def __init__(self, elements, file_path):
            self.elements = elements
            self.file_path = file_path
            self.language = "cpp"
            self.line_count = 4

    elements = list(_functions(extractor, code))
    formatter = CppTableFormatter()
    table = formatter.format_analysis_result(_Result(elements, "qualified.cpp"), "full")
    rows = [line for line in table.splitlines() if line.startswith("| math::")]
    assert len(rows) == 2
    assert rows[0].startswith("| math::min |")
    assert rows[1].startswith("| math::Foo::bar |")
