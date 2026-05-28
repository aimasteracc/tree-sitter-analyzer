#!/usr/bin/env python3
"""
JavaScript Analysis Demo

Demonstrates the enhanced JavaScript plugin capabilities by analyzing
a comprehensive modern JavaScript file and showcasing the extracted information.
"""

import sys
from pathlib import Path

from tree_sitter_analyzer.api import analyze_file
from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ── Attribute access helper ────────────────────────────────────────────────────


def _get_field(obj, attr, default=None):
    """Uniform attribute access for dict or object."""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


# ── Element categorization ─────────────────────────────────────────────────────


def _categorize_elements(elements):
    """Split a flat elements list into typed groups."""
    fns = [e for e in elements if _is_function(e)]
    classes = [e for e in elements if _is_class(e)]
    variables = [e for e in elements if _is_variable(e)]
    imports = [e for e in elements if _is_import(e)]
    return fns, classes, variables, imports


def _is_function(e):
    return (
        _get_field(e, "type") == "function"
        or _get_field(e, "element_type") == "function"
        or type(e).__name__ == "Function"
    )


def _is_class(e):
    return (
        _get_field(e, "type") == "class"
        or _get_field(e, "element_type") == "class"
        or type(e).__name__ == "Class"
    )


def _is_variable(e):
    return (
        _get_field(e, "type") == "variable"
        or _get_field(e, "element_type") == "variable"
        or type(e).__name__ == "Variable"
    )


def _is_import(e):
    return (
        _get_field(e, "type") == "import"
        or _get_field(e, "element_type") == "import"
        or type(e).__name__ == "Import"
    )


def _categorize_functions(functions):
    """Split functions into regular / arrow / async / methods."""
    regular, arrow, async_, methods = [], [], [], []
    for func in functions:
        if _get_field(func, "is_method"):
            methods.append(func)
        elif _get_field(func, "is_arrow"):
            arrow.append(func)
        elif _get_field(func, "is_async"):
            async_.append(func)
        else:
            regular.append(func)
    return regular, arrow, async_, methods


# ── Print helpers ──────────────────────────────────────────────────────────────


def _print_stats(result, elements):
    language_info = result.get("language_info", {})
    ast_info = result.get("ast_info", {})
    print("📊 Analysis Results:")
    print(f"   • Language: {language_info.get('language', 'unknown')}")
    print(f"   • Lines of code: {ast_info.get('line_count', 0)}")
    print(f"   • AST nodes: {ast_info.get('node_count', 0)}")
    print(f"   • Elements found: {len(elements)}")
    print()


def _print_element_breakdown(functions, classes, variables, imports):
    print("📈 Element Breakdown:")
    print(f"   • Functions: {len(functions)}")
    print(f"   • Classes: {len(classes)}")
    print(f"   • Variables: {len(variables)}")
    print(f"   • Imports: {len(imports)}")
    print()


def _print_function_group(label, funcs, limit=5):
    if not funcs:
        return
    print(f"{label} ({len(funcs)}):")
    for func in funcs[:limit]:
        name = _get_field(func, "name")
        params = _get_field(func, "parameters") or []
        complexity = _get_field(func, "complexity_score", "N/A")
        print(f"   • {name}({len(params)} params) - Complexity: {complexity}")
    if len(funcs) > limit:
        print(f"   ... and {len(funcs) - limit} more")
    print()


def _print_methods_group(methods, limit=5):
    if not methods:
        return
    print(f"🏛️  Methods ({len(methods)}):")
    for method in methods[:limit]:
        name = _get_field(method, "name")
        class_name = _get_field(method, "class_name", "Unknown")
        is_constructor = _get_field(method, "is_constructor", False)
        method_type = "constructor" if is_constructor else "method"
        visibility = "private" if name and name.startswith("#") else "public"
        print(f"   • {class_name}.{name} ({method_type}, {visibility})")
    if len(methods) > limit:
        print(f"   ... and {len(methods) - limit} more")
    print()


def _print_function_section(functions):
    if not functions:
        return
    print("🔧 Function Analysis:")
    print("-" * 30)
    regular, arrow, async_, methods = _categorize_functions(functions)
    _print_function_group("📝 Regular Functions", regular)
    _print_function_group("🏹 Arrow Functions", arrow, limit=3)
    _print_function_group("⚡ Async Functions", async_, limit=3)
    _print_methods_group(methods)


def _print_method_type_tags(method):
    tags = []
    if _get_field(method, "is_constructor"):
        tags.append("constructor")
    if _get_field(method, "is_static"):
        tags.append("static")
    if _get_field(method, "is_async"):
        tags.append("async")
    if _get_field(method, "is_getter"):
        tags.append("getter")
    if _get_field(method, "is_setter"):
        tags.append("setter")
    return tags


def _print_class_section(classes, methods):
    if not classes:
        return
    print("🏗️  Class Analysis:")
    print("-" * 30)
    for cls in classes:
        name = _get_field(cls, "name")
        start_line = _get_field(cls, "start_line")
        end_line = _get_field(cls, "end_line")
        extends = _get_field(cls, "superclass")
        is_react = _get_field(cls, "is_react_component", False)
        extends_info = f" extends {extends}" if extends else ""
        react_info = " (React Component)" if is_react else ""
        print(f"📦 {name}{extends_info}{react_info}")
        print(f"   Lines: {start_line}-{end_line}")

        class_methods = [m for m in methods if _get_field(m, "class_name") == name]
        if class_methods:
            print(f"   Methods: {len(class_methods)}")
            for method in class_methods[:3]:
                method_name = _get_field(method, "name")
                tags = _print_method_type_tags(method)
                tag_info = f" ({', '.join(tags)})" if tags else ""
                print(f"     • {method_name}{tag_info}")
            if len(class_methods) > 3:
                print(f"     ... and {len(class_methods) - 3} more")
        print()


def _print_import_section(imports):
    if not imports:
        return
    print("📥 Import Analysis:")
    print("-" * 30)

    es6, commonjs, dynamic = [], [], []
    for imp in imports:
        import_type = getattr(imp, "import_type", "unknown")
        if import_type == "commonjs":
            commonjs.append(imp)
        elif import_type == "dynamic":
            dynamic.append(imp)
        else:
            es6.append(imp)

    if es6:
        print(f"📦 ES6 Imports ({len(es6)}):")
        for imp in es6[:5]:
            import_type = _get_field(imp, "import_type", "default")
            names = _get_field(imp, "imported_names") or [
                _get_field(imp, "name", "unknown")
            ]
            module_path = _get_field(imp, "module_path", "unknown")
            names_str = (
                ", ".join(names)
                if len(names) <= 3
                else f"{names[0]}, ... (+{len(names) - 1})"
            )
            print(f"   • {names_str} from '{module_path}' ({import_type})")
        if len(es6) > 5:
            print(f"   ... and {len(es6) - 5} more")
        print()

    if commonjs:
        print(f"🔧 CommonJS Imports ({len(commonjs)}):")
        for imp in commonjs:
            name = _get_field(imp, "name", "unknown")
            module_path = _get_field(imp, "module_path", "unknown")
            print(f"   • {name} = require('{module_path}')")
        print()

    if dynamic:
        print(f"⚡ Dynamic Imports ({len(dynamic)}):")
        for imp in dynamic:
            module_path = _get_field(imp, "module_path", "unknown")
            print(f"   • import('{module_path}')")
        print()


def _print_variable_section(variables):
    if not variables:
        return
    print("📊 Variable Analysis:")
    print("-" * 30)

    const_vars, let_vars, var_vars, class_props = [], [], [], []
    for var in variables:
        kind = getattr(var, "declaration_kind", "unknown")
        if kind == "const":
            const_vars.append(var)
        elif kind == "let":
            let_vars.append(var)
        elif kind == "var":
            var_vars.append(var)
        elif kind == "property":
            class_props.append(var)

    if const_vars:
        print(f"🔒 Constants ({len(const_vars)}):")
        for var in const_vars[:3]:
            print(f"   • {var.name}: {getattr(var, 'variable_type', 'unknown')}")
        if len(const_vars) > 3:
            print(f"   ... and {len(const_vars) - 3} more")
        print()

    if let_vars:
        print(f"🔄 Let Variables ({len(let_vars)}):")
        for var in let_vars[:3]:
            print(f"   • {var.name}: {getattr(var, 'variable_type', 'unknown')}")
        if len(let_vars) > 3:
            print(f"   ... and {len(let_vars) - 3} more")
        print()

    if class_props:
        print(f"🏛️  Class Properties ({len(class_props)}):")
        for prop in class_props:
            class_name = getattr(prop, "class_name", "Unknown")
            static_info = " (static)" if getattr(prop, "is_static", False) else ""
            print(f"   • {class_name}.{prop.name}{static_info}")
        print()


def _build_formatter_data(js_file, functions, classes, variables, imports):
    return {
        "file_path": str(js_file),
        "functions": [
            {
                "name": _get_field(f, "name"),
                "parameters": _get_field(f, "parameters") or [],
                "line_range": {
                    "start": _get_field(f, "start_line", 0),
                    "end": _get_field(f, "end_line", 0),
                },
                "is_async": _get_field(f, "is_async", False),
                "is_arrow": _get_field(f, "is_arrow", False),
                "is_method": _get_field(f, "is_method", False),
                "class_name": _get_field(f, "class_name"),
                "complexity_score": _get_field(f, "complexity_score", 1),
                "jsdoc": _get_field(f, "docstring"),
            }
            for f in functions
        ],
        "classes": [
            {
                "name": _get_field(c, "name"),
                "superclass": _get_field(c, "superclass"),
                "line_range": {
                    "start": _get_field(c, "start_line", 0),
                    "end": _get_field(c, "end_line", 0),
                },
            }
            for c in classes
        ],
        "variables": [
            {
                "name": _get_field(v, "name"),
                "variable_type": _get_field(v, "variable_type", "unknown"),
                "declaration_kind": _get_field(v, "declaration_kind", "unknown"),
                "initializer": _get_field(v, "initializer"),
                "is_constant": _get_field(v, "is_constant", False),
                "line_range": {
                    "start": _get_field(v, "start_line", 0),
                    "end": _get_field(v, "end_line", 0),
                },
            }
            for v in variables
        ],
        "imports": [
            {
                "name": _get_field(i, "name"),
                "source": _get_field(i, "module_path"),
                "import_type": _get_field(i, "import_type", "default"),
                "statement": _get_field(i, "raw_text"),
            }
            for i in imports
        ],
        "exports": [],
        "statistics": {
            "function_count": len(functions),
            "class_count": len(classes),
            "variable_count": len(variables),
            "import_count": len(imports),
        },
    }


def _print_formatted_table(js_file, functions, classes, variables, imports):
    print("📋 Formatted Analysis Table:")
    print("-" * 50)
    formatter = FormatterRegistry.get_formatter_for_language("javascript", "full")
    data = _build_formatter_data(js_file, functions, classes, variables, imports)
    try:
        print(formatter.format(data))
    except Exception as e:
        print(f"⚠️  Could not generate formatted table: {e}")
        print("Raw statistics instead:")
        for key, value in data["statistics"].items():
            print(f"   • {key}: {value}")


def _print_framework_info(result):
    metadata = getattr(result, "metadata", {})
    if not metadata:
        return
    print("\n🔍 Detected Features:")
    if metadata.get("is_module"):
        print("   • ES6 Module")
    if metadata.get("is_jsx"):
        print("   • JSX Support")
    framework = metadata.get("framework_type")
    if framework:
        print(f"   • Framework: {framework.title()}")


# ── Main analysis ──────────────────────────────────────────────────────────────


def analyze_modern_javascript():
    """Analyze the ModernJavaScript.js example file"""
    js_file = project_root / "examples" / "ModernJavaScript.js"

    if not js_file.exists():
        print(f"❌ JavaScript example file not found: {js_file}")
        return

    print("🔍 Analyzing Modern JavaScript File...")
    print("=" * 50)
    print(f"📁 File: {js_file.name}")
    print()

    try:
        result = analyze_file(str(js_file))

        if not result.get("success", True):
            print(f"❌ Analysis failed: {result.get('error_message', 'Unknown error')}")
            return

        elements = result.get("elements", [])
        _print_stats(result, elements)

        functions, classes, variables, imports = _categorize_elements(elements)
        _print_element_breakdown(functions, classes, variables, imports)

        _, _, _, methods = _categorize_functions(functions)

        _print_function_section(functions)
        _print_class_section(classes, methods)
        _print_import_section(imports)
        _print_variable_section(variables)
        _print_formatted_table(js_file, functions, classes, variables, imports)

        print("\n✅ Analysis Complete!")
        print(f"📄 Successfully analyzed {len(elements)} code elements")
        _print_framework_info(result)

    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        import traceback

        traceback.print_exc()


def demonstrate_query_capabilities():
    """Demonstrate the enhanced query capabilities"""
    print("\n🔎 JavaScript Query Capabilities:")
    print("=" * 50)

    from tree_sitter_analyzer.queries.javascript import get_available_javascript_queries

    queries = get_available_javascript_queries()

    categories = {
        "Functions": [q for q in queries if "function" in q],
        "Classes": [
            q for q in queries if "class" in q or "method" in q or "constructor" in q
        ],
        "Variables": [
            q for q in queries if "variable" in q or "const" in q or "let" in q
        ],
        "Imports/Exports": [q for q in queries if "import" in q or "export" in q],
        "Modern JS": [
            q
            for q in queries
            if any(
                k in q
                for k in ["async", "arrow", "template", "spread", "await", "yield"]
            )
        ],
        "JSX/React": [q for q in queries if "jsx" in q or "react" in q],
        "Control Flow": [
            q
            for q in queries
            if any(k in q for k in ["if", "for", "while", "switch", "try", "catch"])
        ],
        "Advanced": [
            q
            for q in queries
            if any(k in q for k in ["closure", "iife", "promise", "event"])
        ],
    }

    for category, category_queries in categories.items():
        if category_queries:
            print(f"\n📂 {category} ({len(category_queries)} queries):")
            for query in sorted(category_queries)[:5]:
                print(f"   • {query}")
            if len(category_queries) > 5:
                print(f"   ... and {len(category_queries) - 5} more")

    print(f"\n📊 Total Available Queries: {len(queries)}")


if __name__ == "__main__":
    print("🚀 JavaScript Analysis Demo")
    print("=" * 60)

    analyze_modern_javascript()
    demonstrate_query_capabilities()

    print("\n" + "=" * 60)
    print("🎉 Demo completed successfully!")
    print("\nThis demo showcases the enhanced JavaScript plugin capabilities:")
    print("• Comprehensive element extraction (functions, classes, variables, imports)")
    print("• Modern JavaScript feature support (ES6+, async/await, arrow functions)")
    print("• JSX and React component detection")
    print("• Detailed metadata and complexity analysis")
    print("• Professional table formatting")
    print("• 80+ specialized queries for different JavaScript patterns")
