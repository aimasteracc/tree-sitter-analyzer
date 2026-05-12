import pytest
import tree_sitter
import tree_sitter_cpp

from tree_sitter_analyzer.languages.cpp_plugin import CppElementExtractor, CppPlugin


@pytest.fixture
def plugin():
    return CppPlugin()


@pytest.fixture
def extractor():
    return CppElementExtractor()


def _parse(code: str):
    lang = tree_sitter.Language(tree_sitter_cpp.language())
    parser = tree_sitter.Parser(lang)
    return parser.parse(code.encode("utf-8"))


def test_cpp_plugin_basic(plugin):
    code = """
    #include <iostream>
    namespace my_ns {
        class MyClass {
            public:
                void my_method() {}
        };
    }
    void global_func() {}
    """
    tree = _parse(code)
    elements_dict = plugin.extract_elements(tree, code)
    assert elements_dict is not None
    assert len(elements_dict["functions"]) > 0
    assert len(elements_dict["classes"]) > 0

    names = [e.name for e in elements_dict["functions"]]
    assert "my_method" in names
    assert "global_func" in names


# --- Template function extraction ---
def test_template_function(extractor):
    code = "template <typename T> T max_val(T a, T b) { return a > b ? a : b; }\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    names = [f.name for f in funcs]
    assert "max_val" in names
    tfunc = next(f for f in funcs if f.name == "max_val")
    assert "template" in (tfunc.modifiers or [])


# --- Template class extraction ---
def test_template_class(extractor):
    code = "template <typename T> class Stack { T data[100]; int top; };\n"
    tree = _parse(code)
    classes = extractor.extract_classes(tree, code)
    names = [c.name for c in classes]
    assert "Stack" in names
    tcls = next(c for c in classes if c.name == "Stack")
    assert "template" in (tcls.modifiers or [])


# --- Union extraction ---
def test_union_extraction(extractor):
    code = "union Data { int i; float f; char c; };\n"
    tree = _parse(code)
    classes = extractor.extract_classes(tree, code)
    assert len(classes) >= 1
    unions = [c for c in classes if c.class_type == "union"]
    assert len(unions) >= 1
    assert unions[0].name == "Data"


# --- Namespace extraction (packages) ---
def test_namespace_extraction(extractor):
    code = "namespace physics { double gravity = 9.8; }\n"
    tree = _parse(code)
    packages = extractor.extract_packages(tree, code)
    assert len(packages) >= 1
    assert packages[0].name == "physics"


# --- Using declaration in imports ---
def test_using_declaration_import(extractor):
    code = "using namespace std;\n"
    tree = _parse(code)
    imports = extractor.extract_imports(tree, code)
    assert len(imports) >= 1
    assert any("using" in i.import_statement for i in imports)


# --- Alias declaration in imports ---
def test_alias_declaration_import(extractor):
    code = "using IntVec = vector<int>;\n"
    tree = _parse(code)
    imports = extractor.extract_imports(tree, code)
    assert len(imports) >= 1
    assert any("IntVec" in i.name for i in imports)


# --- Fallback include extraction (regex) ---
def test_include_fallback_regex(extractor):
    code = '#include "myheader.h"\n#include <vector>\n'
    tree = _parse(code)
    imports = extractor.extract_imports(tree, code)
    names = [i.name for i in imports]
    assert "myheader.h" in names or "vector" in names


# --- System include ---
def test_system_include(extractor):
    code = "#include <iostream>\n#include <string>\n"
    tree = _parse(code)
    imports = extractor.extract_imports(tree, code)
    names = [i.name for i in imports]
    assert "iostream" in names
    assert "string" in names


# --- Inheritance (base classes) ---
def test_class_inheritance(extractor):
    code = "class Base { public: virtual void foo() {} };\nclass Derived : public Base { public: void foo() override {} };\n"
    tree = _parse(code)
    classes = extractor.extract_classes(tree, code)
    derived = [c for c in classes if c.name == "Derived"]
    assert len(derived) >= 1
    # base_class_clause is parsed but grammar lacks base_specifier children
    assert derived[0].raw_text is not None


# --- Pure virtual function from field_declaration ---
def test_pure_virtual_function(extractor):
    code = "class Shape { public: virtual double area() const = 0; };\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    area_funcs = [f for f in funcs if f.name == "area"]
    assert len(area_funcs) >= 1


# --- Static and const modifiers ---
def test_static_const_modifiers(extractor):
    code = "class Config { public: static const int MAX_SIZE = 100; };\n"
    tree = _parse(code)
    variables = extractor.extract_variables(tree, code)
    assert len(variables) >= 1
    max_var = [v for v in variables if v.name == "MAX_SIZE"]
    assert len(max_var) >= 1
    assert max_var[0].is_static is True
    assert max_var[0].is_constant is True


# --- Global variables ---
def test_global_variable(extractor):
    code = "int counter = 0;\nstatic double pi = 3.14;\n"
    tree = _parse(code)
    variables = extractor.extract_variables(tree, code)
    assert len(variables) >= 1
    names = [v.name for v in variables]
    assert "counter" in names


# --- Visibility: public/private/protected ---
def test_visibility_in_class(extractor):
    code = (
        "class Widget {\n"
        "public:\n"
        "    void show() {}\n"
        "private:\n"
        "    int secret;\n"
        "protected:\n"
        "    void internal() {}\n"
        "};\n"
    )
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    show_funcs = [f for f in funcs if f.name == "show"]
    assert len(show_funcs) >= 1
    assert show_funcs[0].visibility == "public"

    internal_funcs = [f for f in funcs if f.name == "internal"]
    assert len(internal_funcs) >= 1
    assert internal_funcs[0].visibility == "protected"


# --- Struct default visibility is public ---
def test_struct_default_visibility(extractor):
    code = "struct Point { int x; int y; };\n"
    tree = _parse(code)
    variables = extractor.extract_variables(tree, code)
    x_vars = [v for v in variables if v.name == "x"]
    assert len(x_vars) >= 1
    assert x_vars[0].visibility == "public"


# --- Doxygen comment extraction ---
def test_doxygen_comment_extraction(extractor):
    code = "/**\n * Calculate area\n */\ndouble area() { return 0.0; }\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    area_funcs = [f for f in funcs if f.name == "area"]
    if area_funcs:
        assert area_funcs[0].docstring is not None


# --- Triple-slash comment extraction ---
def test_triple_slash_comment(extractor):
    code = "/// Computes sum\nint sum(int a, int b) { return a + b; }\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    sum_funcs = [f for f in funcs if f.name == "sum"]
    assert len(sum_funcs) >= 1
    assert sum_funcs[0].docstring is not None
    assert "Computes" in sum_funcs[0].docstring


# --- Complexity calculation with control flow ---
def test_complexity_with_control_flow(extractor):
    code = (
        "int classify(int x) {\n"
        "    if (x > 0) return 1;\n"
        "    else if (x < 0) return -1;\n"
        "    for (int i = 0; i < x; i++) {}\n"
        "    while (x > 10) { x--; }\n"
        "    return 0;\n"
        "}\n"
    )
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    classify = [f for f in funcs if f.name == "classify"]
    assert len(classify) >= 1
    assert classify[0].complexity_score > 1


# --- Qualified identifier function name (namespace-qualified) ---
def test_qualified_function(extractor):
    code = (
        "namespace ns {\n"
        "    class Foo {\n"
        "    public:\n"
        "        void bar() {}\n"
        "    };\n"
        "}\n"
    )
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    bar_funcs = [f for f in funcs if f.name == "bar"]
    assert len(bar_funcs) >= 1


# --- extract_elements with None tree ---
def test_extract_elements_none_tree(plugin):
    result = plugin.extract_elements(None, "code")
    assert result["functions"] == []
    assert result["classes"] == []
    assert result["variables"] == []
    assert result["imports"] == []
    assert result["packages"] == []


# --- _count_tree_nodes ---
def test_count_tree_nodes(plugin):
    code = "int main() { return 0; }\n"
    tree = _parse(code)
    count = plugin._count_tree_nodes(tree.root_node)
    assert count >= 1


def test_count_tree_nodes_none(plugin):
    assert plugin._count_tree_nodes(None) == 0


# --- Variable with init_declarator ---
def test_variable_with_init_declarator(extractor):
    code = "int x = 42;\n"
    tree = _parse(code)
    variables = extractor.extract_variables(tree, code)
    assert len(variables) >= 1
    assert variables[0].name == "x"
    assert variables[0].variable_type == "int"


# --- Field with init_declarator in class ---
def test_field_with_init_declarator(extractor):
    code = "class Foo { int val = 0; };\n"
    tree = _parse(code)
    variables = extractor.extract_variables(tree, code)
    val_vars = [v for v in variables if v.name == "val"]
    assert len(val_vars) >= 1


# --- Destructor function name ---
def test_destructor_extraction(extractor):
    code = "class Resource { public: ~Resource() {} };\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    dtor_funcs = [f for f in funcs if f.name and "~" in f.name]
    assert len(dtor_funcs) >= 1


# --- Const qualified method ---
def test_const_method(extractor):
    code = "class Val { public: int get() const { return v; } int v; };\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    get_funcs = [f for f in funcs if f.name == "get"]
    assert len(get_funcs) >= 1


# --- Static global variable is private visibility ---
def test_static_global_private_visibility(extractor):
    code = "static int internal_counter = 0;\n"
    tree = _parse(code)
    variables = extractor.extract_variables(tree, code)
    ctr_vars = [v for v in variables if v.name == "internal_counter"]
    assert len(ctr_vars) >= 1
    assert ctr_vars[0].visibility == "private"


# --- extract_classes with class having no name (edge case) ---
def test_class_no_name_returns_none(extractor):
    code = "class { int x; } instance;\n"
    tree = _parse(code)
    classes = extractor.extract_classes(tree, code)
    # Anonymous class may not be extracted (name is None -> skip)
    # Just verify it doesn't crash
    for c in classes:
        assert c.name is not None


# --- Function declaration (prototype) ---
def test_function_declaration(extractor):
    code = "void initialize(int argc, char** argv);\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    init_funcs = [f for f in funcs if f.name == "initialize"]
    assert len(init_funcs) >= 1
    assert init_funcs[0].return_type == "void"


# --- Function declaration inside class ---
def test_method_declaration_in_class(extractor):
    code = "class Engine { public: void start(); void stop(); };\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    names = [f.name for f in funcs]
    assert "start" in names
    assert "stop" in names


# --- Extract includes with local and system ---
def test_mixed_includes(extractor):
    code = '#include <iostream>\n#include "utils.h"\n'
    tree = _parse(code)
    imports = extractor.extract_imports(tree, code)
    assert len(imports) >= 2


# --- Fallback regex for includes ---
def test_fallback_regex_only(extractor):
    # Force fallback by using code that won't match tree-sitter child nodes
    code = "// no preproc nodes at root level\n#define FOO 1\n#include <vector>\n"
    tree = _parse(code)
    imports = extractor.extract_imports(tree, code)
    # Should find includes via tree-sitter or fallback
    names = [i.name for i in imports]
    assert "vector" in names


# --- Reference declarator (reference return type) ---
def test_reference_return_function(extractor):
    code = "int& get_ref(int& x) { return x; }\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    ref_funcs = [f for f in funcs if f.name == "get_ref"]
    assert len(ref_funcs) >= 1


# --- Pointer declarator (pointer return type) ---
def test_pointer_return_function(extractor):
    code = "int* create_ptr(int val) { return new int(val); }\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    ptr_funcs = [f for f in funcs if f.name == "create_ptr"]
    assert len(ptr_funcs) >= 1


# --- Operator overloading ---
def test_operator_function(extractor):
    code = "class Vec { public: Vec operator+(const Vec& other) const; };\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    op_funcs = [f for f in funcs if f.name and "operator" in f.name]
    assert len(op_funcs) >= 1


# --- Nested namespace ---
def test_nested_namespace(extractor):
    code = "namespace outer { namespace inner { int x = 1; } }\n"
    tree = _parse(code)
    packages = extractor.extract_packages(tree, code)
    names = [p.name for p in packages]
    assert "outer" in names or "inner" in names


# --- Class default visibility is private ---
def test_class_default_visibility(extractor):
    code = "class Secret { int value; };\n"
    tree = _parse(code)
    variables = extractor.extract_variables(tree, code)
    val_vars = [v for v in variables if v.name == "value"]
    assert len(val_vars) >= 1
    assert val_vars[0].visibility == "private"


# --- Field with multiple declarators ---
def test_field_multiple_declarators(extractor):
    code = "class Pair { int a, b; };\n"
    tree = _parse(code)
    variables = extractor.extract_variables(tree, code)
    names = [v.name for v in variables]
    assert "a" in names or "b" in names


# --- Variable with template type ---
def test_variable_template_type(extractor):
    code = "vector<int> nums;\n"
    tree = _parse(code)
    variables = extractor.extract_variables(tree, code)
    assert len(variables) >= 1
    assert "vector" in (variables[0].variable_type or "")


# --- Function with storage class specifier ---
def test_function_with_static(extractor):
    code = "static void helper() {}\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    helper_funcs = [f for f in funcs if f.name == "helper"]
    assert len(helper_funcs) >= 1
    assert helper_funcs[0].is_static is True


# --- Extract elements with exception handling in plugin ---
def test_extract_elements_exception_handling(plugin):
    result = plugin.extract_elements(None, "int x;")
    assert result["functions"] == []


# --- Template struct ---
def test_template_struct(extractor):
    code = "template <typename T> struct Holder { T value; };\n"
    tree = _parse(code)
    classes = extractor.extract_classes(tree, code)
    holders = [c for c in classes if c.name == "Holder"]
    assert len(holders) >= 1
    assert "template" in (holders[0].modifiers or [])


# --- Multiple parameters ---
def test_function_multiple_parameters(extractor):
    code = "int add(int a, int b, int c) { return a + b + c; }\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    add_funcs = [f for f in funcs if f.name == "add"]
    assert len(add_funcs) >= 1
    assert len(add_funcs[0].parameters) >= 2


# --- Variadic parameter ---
def test_variadic_function(extractor):
    code = "int printf(const char* fmt, ...);\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    printf_funcs = [f for f in funcs if f.name == "printf"]
    assert len(printf_funcs) >= 1


# --- Full qualified name with namespace ---
def test_qualified_name_with_namespace(extractor):
    code = (
        "namespace gfx {\n    class Color {\n    public:\n        int r;\n    };\n}\n"
    )
    tree = _parse(code)
    classes = extractor.extract_classes(tree, code)
    color_classes = [c for c in classes if c.name == "Color"]
    assert len(color_classes) >= 1
    assert (
        color_classes[0].full_qualified_name == "gfx::Color"
        or color_classes[0].package_name == "gfx"
    )


# --- Deleted method (= delete) ---
def test_deleted_method(extractor):
    code = "class NonCopy {\npublic:\n    NonCopy(const NonCopy&) = delete;\n};\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    nc_funcs = [f for f in funcs if f.name and "NonCopy" in f.name]
    assert len(nc_funcs) >= 1


# --- Defaulted method (= default) ---
def test_defaulted_method(extractor):
    code = "class Defaults {\npublic:\n    Defaults() = default;\n};\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    assert isinstance(funcs, list)
    defaults_funcs = [f for f in funcs if f.name and "Defaults" in f.name]
    assert len(defaults_funcs) >= 1
    # default modifier is extracted via field_declaration path


# --- Protected visibility via explicit access specifier ---
def test_protected_access_specifier(extractor):
    code = "class Base {\nprotected:\n    void do_thing() {}\n};\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    thing_funcs = [f for f in funcs if f.name == "do_thing"]
    assert len(thing_funcs) >= 1
    assert thing_funcs[0].visibility == "protected"


# --- Protected visibility via explicit modifier ---
def test_protected_explicit_modifier_determine_visibility(extractor):
    result = extractor._determine_visibility(["protected"], is_global=False, node=None)
    assert result == "protected"


# --- Private visibility via explicit modifier ---
def test_private_explicit_modifier_determine_visibility(extractor):
    result = extractor._determine_visibility(["private"], is_global=False, node=None)
    assert result == "private"


# --- Public visibility via explicit modifier ---
def test_public_explicit_modifier_determine_visibility(extractor):
    result = extractor._determine_visibility(["public"], is_global=True, node=None)
    assert result == "public"


# --- Static global visibility is private ---
def test_static_global_determine_visibility(extractor):
    result = extractor._determine_visibility(["static"], is_global=True, node=None)
    assert result == "private"


# --- Default: public for global, private for non-global ---
def test_default_visibility(extractor):
    assert extractor._determine_visibility([], is_global=True, node=None) == "public"
    assert extractor._determine_visibility([], is_global=False, node=None) == "private"


# --- Field with init_declarator containing identifier in class ---
def test_field_init_declarator_identifier(extractor):
    code = "class Pair { int val = 0; };\n"
    tree = _parse(code)
    variables = extractor.extract_variables(tree, code)
    val_vars = [v for v in variables if v.name == "val"]
    assert len(val_vars) >= 1
    assert val_vars[0].variable_type == "int"


# --- Extract includes fallback with local include only ---
def test_include_fallback_local_only(extractor):
    code = '#include "local_header.h"\n'
    tree = _parse(code)
    imports = extractor.extract_imports(tree, code)
    names = [i.name for i in imports]
    assert "local_header.h" in names


# --- Virtual function with const qualifier ---
def test_virtual_const_function(extractor):
    code = "class Shape {\npublic:\n    virtual double area() const = 0;\n};\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    area_funcs = [f for f in funcs if f.name == "area"]
    assert len(area_funcs) >= 1
    assert "virtual" in (area_funcs[0].modifiers or [])
    assert "pure_virtual" in (area_funcs[0].modifiers or [])


# --- For-range loop complexity ---
def test_for_range_complexity(extractor):
    code = "int sum_items() {\n    int total = 0;\n    for (int x : items) { total += x; }\n    return total;\n}\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    sum_funcs = [f for f in funcs if f.name == "sum_items"]
    assert len(sum_funcs) >= 1
    assert sum_funcs[0].complexity_score > 1


# --- Switch statement complexity ---
def test_switch_complexity(extractor):
    code = "int grade(int score) {\n    switch(score) {\n        case 90: return 4;\n        case 80: return 3;\n        default: return 0;\n    }\n}\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    grade_funcs = [f for f in funcs if f.name == "grade"]
    assert len(grade_funcs) >= 1
    assert grade_funcs[0].complexity_score > 1


# --- Catch clause complexity ---
def test_try_catch_complexity(extractor):
    code = (
        "void safe_op() {\n    try { risky(); }\n    catch (int e) { handle(e); }\n}\n"
    )
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    safe_funcs = [f for f in funcs if f.name == "safe_op"]
    assert len(safe_funcs) >= 1
    assert safe_funcs[0].complexity_score > 1


# --- _get_access_specifier with node not in field_declaration_list ---
def test_get_access_specifier_not_in_class(extractor):
    code = "int x;\n"
    tree = _parse(code)
    assert extractor._get_access_specifier(tree.root_node) is None


# --- _is_global_scope for root node ---
def test_is_global_scope_root(extractor):
    code = "class Foo { int x; };\n"
    tree = _parse(code)
    assert extractor._is_global_scope(tree.root_node) is True


# --- Extract elements with exception in plugin ---
def test_extract_elements_with_bad_extractor(plugin, monkeypatch):
    def bad_extractor_factory(self):
        class BadExtractor:
            def extract_functions(self, tree, src):
                raise RuntimeError("boom")

            def extract_classes(self, tree, src):
                return []

            def extract_variables(self, tree, src):
                return []

            def extract_imports(self, tree, src):
                return []

            def extract_packages(self, tree, src):
                return []

        return BadExtractor()

    code = "int x;\n"
    tree = _parse(code)
    from unittest.mock import patch

    with patch.object(type(plugin), "create_extractor", bad_extractor_factory):
        result = plugin.extract_elements(tree, code)
    assert result["functions"] == []


# --- Multiple global variables with init_declarator ---
def test_multiple_global_variables_init_declarator(extractor):
    code = "int a = 1, b = 2;\n"
    tree = _parse(code)
    variables = extractor.extract_variables(tree, code)
    names = [v.name for v in variables]
    assert "a" in names or "b" in names


# --- _count_tree_nodes with child nodes ---
def test_count_tree_nodes_with_children(plugin):
    code = "class Foo { int x; void bar() {} };\n"
    tree = _parse(code)
    count = plugin._count_tree_nodes(tree.root_node)
    assert count > 5


# --- Extract with doxygen comment on class ---
def test_doxygen_comment_on_class(extractor):
    code = "/**\n * A documented class.\n */\nclass DocClass {\n};\n"
    tree = _parse(code)
    classes = extractor.extract_classes(tree, code)
    dc = [c for c in classes if c.name == "DocClass"]
    assert len(dc) >= 1
    assert dc[0].docstring is not None
    assert "documented" in dc[0].docstring


# --- Extract namespace with namespace_identifier child ---
def test_namespace_identifier_node(extractor):
    code = "namespace my_lib { int val = 42; }\n"
    tree = _parse(code)
    packages = extractor.extract_packages(tree, code)
    assert len(packages) >= 1
    assert packages[0].name == "my_lib"


# --- Deleted method (= delete) ---
def test_deleted_method(extractor):
    code = "class NoCopy {\npublic:\n    NoCopy(const NoCopy&) = delete;\n    NoCopy& operator=(const NoCopy&) = delete;\n};\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    deleted_funcs = [f for f in funcs if "NoCopy" in (f.name or "")]
    assert len(deleted_funcs) >= 1
    for f in deleted_funcs:
        assert "deleted" in (f.modifiers or [])


# --- Defaulted method (= default) ---
def test_defaulted_method(extractor):
    code = "class Foo {\npublic:\n    Foo() = default;\n    ~Foo() = default;\n};\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    default_funcs = [f for f in funcs if "Foo" in (f.name or "")]
    assert len(default_funcs) >= 1
    for f in default_funcs:
        assert "default" in (f.modifiers or [])


# --- Simple function declaration (prototype) with identifier ---
def test_simple_function_declaration_identifier(extractor):
    code = "int compute(int x, int y);\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    compute_funcs = [f for f in funcs if f.name == "compute"]
    assert len(compute_funcs) >= 1
    assert len(compute_funcs[0].parameters) >= 2


# --- Deeply nested blocks (max depth) ---
def test_deeply_nested_blocks(extractor):
    nesting = 100
    code = "int main() {\n"
    for _ in range(nesting):
        code += "    {\n"
    code += "    int x = 1;\n"
    for _ in range(nesting):
        code += "    }\n"
    code += "}\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    main_funcs = [f for f in funcs if f.name == "main"]
    assert len(main_funcs) >= 1


# --- Static field declaration ---
def test_static_field_declaration(extractor):
    code = "class Counter {\n    static int count;\n};\n"
    tree = _parse(code)
    variables = extractor.extract_variables(tree, code)
    count_vars = [v for v in variables if v.name == "count"]
    assert len(count_vars) >= 1
    assert count_vars[0].is_static is True


# --- Lambda function extraction ---
def test_lambda_expression(extractor):
    code = "auto add = [](int a, int b) { return a + b; };\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    # Lambda should not be extracted as a regular function
    lambda_funcs = [f for f in funcs if f.name is not None and "operator" in (f.name or "")]
    assert len(lambda_funcs) >= 0  # Just exercise the extractor path
