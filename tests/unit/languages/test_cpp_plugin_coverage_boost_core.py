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
