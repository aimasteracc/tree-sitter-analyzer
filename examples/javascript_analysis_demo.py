#!/usr/bin/env python3
"""
JavaScript Analysis Demo

Demonstrates the enhanced JavaScript plugin capabilities by analyzing
a comprehensive modern JavaScript file and showcasing the extracted information.
"""

import sys
from pathlib import Path

from tree_sitter_analyzer.api import analyze_file
from tree_sitter_analyzer.formatters.formatter_factory import TableFormatterFactory

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


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
        # Analyze the JavaScript file
        result = analyze_file(str(js_file))

        if not result.get("success", True):
            print(f"❌ Analysis failed: {result.get('error_message', 'Unknown error')}")
            return

        # Display basic statistics
        print("📊 Analysis Results:")
        language_info = result.get("language_info", {})
        ast_info = result.get("ast_info", {})
        print(f"   • Language: {language_info.get('language', 'unknown')}")
        print(f"   • Lines of code: {ast_info.get('line_count', 0)}")
        print(f"   • AST nodes: {ast_info.get('node_count', 0)}")
        elements = result.get("elements", [])
        print(f"   • Elements found: {len(elements)}")
        print()

        # Categorize elements
        functions = [
            e
            for e in elements
            if e.get("type") == "function"
            or e.get("element_type") == "function"
            or e.__class__.__name__ == "Function"
        ]
        classes = [
            e
            for e in elements
            if e.get("type") == "class"
            or e.get("element_type") == "class"
            or e.__class__.__name__ == "Class"
        ]
        variables = [
            e
            for e in elements
            if e.get("type") == "variable"
            or e.get("element_type") == "variable"
            or e.__class__.__name__ == "Variable"
        ]
        imports = [
            e
            for e in elements
            if e.get("type") == "import"
            or e.get("element_type") == "import"
            or e.__class__.__name__ == "Import"
        ]

        print("📈 Element Breakdown:")
        print(f"   • Functions: {len(functions)}")
        print(f"   • Classes: {len(classes)}")
        print(f"   • Variables: {len(variables)}")
        print(f"   • Imports: {len(imports)}")
        print()

        # Show detailed function analysis
        if functions:
            print("🔧 Function Analysis:")
            print("-" * 30)

            # Group functions by type
            regular_functions = []
            arrow_functions = []
            async_functions = []
            methods = []

            for func in functions:
                if getattr(func, "is_method", False) or func.get("is_method", False):
                    methods.append(func)
                elif getattr(func, "is_arrow", False) or func.get("is_arrow", False):
                    arrow_functions.append(func)
                elif getattr(func, "is_async", False) or func.get("is_async", False):
                    async_functions.append(func)
                else:
                    regular_functions.append(func)

            if regular_functions:
                print(f"📝 Regular Functions ({len(regular_functions)}):")
                for func in regular_functions[:5]:  # Show first 5
                    name = func.get("name") if isinstance(func, dict) else func.name
                    parameters = (
                        func.get("parameters")
                        if isinstance(func, dict)
                        else func.parameters
                    )
                    params_count = len(parameters) if parameters else 0
                    complexity = (
                        func.get("complexity_score", "N/A")
                        if isinstance(func, dict)
                        else getattr(func, "complexity_score", "N/A")
                    )
                    print(
                        f"   • {name}({params_count} params) - Complexity: {complexity}"
                    )
                if len(regular_functions) > 5:
                    print(f"   ... and {len(regular_functions) - 5} more")
                print()

            if arrow_functions:
                print(f"🏹 Arrow Functions ({len(arrow_functions)}):")
                for func in arrow_functions[:3]:
                    name = func.get("name") if isinstance(func, dict) else func.name
                    parameters = (
                        func.get("parameters")
                        if isinstance(func, dict)
                        else func.parameters
                    )
                    params_count = len(parameters) if parameters else 0
                    print(f"   • {name}({params_count} params)")
                if len(arrow_functions) > 3:
                    print(f"   ... and {len(arrow_functions) - 3} more")
                print()

            if async_functions:
                print(f"⚡ Async Functions ({len(async_functions)}):")
                for func in async_functions[:3]:
                    name = func.get("name") if isinstance(func, dict) else func.name
                    parameters = (
                        func.get("parameters")
                        if isinstance(func, dict)
                        else func.parameters
                    )
                    params_count = len(parameters) if parameters else 0
                    print(f"   • {name}({params_count} params)")
                if len(async_functions) > 3:
                    print(f"   ... and {len(async_functions) - 3} more")
                print()

            if methods:
                print(f"🏛️  Methods ({len(methods)}):")
                for method in methods[:5]:
                    name = (
                        method.get("name") if isinstance(method, dict) else method.name
                    )
                    class_name = (
                        method.get("class_name", "Unknown")
                        if isinstance(method, dict)
                        else getattr(method, "class_name", "Unknown")
                    )
                    is_constructor = (
                        method.get("is_constructor", False)
                        if isinstance(method, dict)
                        else getattr(method, "is_constructor", False)
                    )
                    method_type = "constructor" if is_constructor else "method"
                    visibility = "private" if name.startswith("#") else "public"
                    print(f"   • {class_name}.{name} ({method_type}, {visibility})")
                if len(methods) > 5:
                    print(f"   ... and {len(methods) - 5} more")
                print()

        # Show class analysis
        if classes:
            print("🏗️  Class Analysis:")
            print("-" * 30)
            for cls in classes:
                name = cls.get("name") if isinstance(cls, dict) else cls.name
                start_line = (
                    cls.get("start_line") if isinstance(cls, dict) else cls.start_line
                )
                end_line = (
                    cls.get("end_line") if isinstance(cls, dict) else cls.end_line
                )
                extends = (
                    cls.get("superclass")
                    if isinstance(cls, dict)
                    else getattr(cls, "superclass", None)
                )
                extends_info = f" extends {extends}" if extends else ""
                is_react = (
                    cls.get("is_react_component", False)
                    if isinstance(cls, dict)
                    else getattr(cls, "is_react_component", False)
                )
                react_info = " (React Component)" if is_react else ""

                print(f"📦 {name}{extends_info}{react_info}")
                print(f"   Lines: {start_line}-{end_line}")

                # Show class methods
                class_methods = [
                    m
                    for m in methods
                    if (
                        m.get("class_name")
                        if isinstance(m, dict)
                        else getattr(m, "class_name", None)
                    )
                    == name
                ]
                if class_methods:
                    print(f"   Methods: {len(class_methods)}")
                    for method in class_methods[:3]:
                        method_name = (
                            method.get("name")
                            if isinstance(method, dict)
                            else method.name
                        )
                        method_type = []
                        if (
                            method.get("is_constructor", False)
                            if isinstance(method, dict)
                            else getattr(method, "is_constructor", False)
                        ):
                            method_type.append("constructor")
                        if (
                            method.get("is_static", False)
                            if isinstance(method, dict)
                            else getattr(method, "is_static", False)
                        ):
                            method_type.append("static")
                        if (
                            method.get("is_async", False)
                            if isinstance(method, dict)
                            else getattr(method, "is_async", False)
                        ):
                            method_type.append("async")
                        if (
                            method.get("is_getter", False)
                            if isinstance(method, dict)
                            else getattr(method, "is_getter", False)
                        ):
                            method_type.append("getter")
                        if (
                            method.get("is_setter", False)
                            if isinstance(method, dict)
                            else getattr(method, "is_setter", False)
                        ):
                            method_type.append("setter")

                        type_info = (
                            f" ({', '.join(method_type)})" if method_type else ""
                        )
                        print(f"     • {method_name}{type_info}")

                    if len(class_methods) > 3:
                        print(f"     ... and {len(class_methods) - 3} more")
                print()

        # Show import analysis
        if imports:
            print("📥 Import Analysis:")
            print("-" * 30)

            # Group imports by type
            es6_imports = []
            commonjs_imports = []
            dynamic_imports = []

            for imp in imports:
                import_type = getattr(imp, "import_type", "unknown")
                if import_type == "commonjs":
                    commonjs_imports.append(imp)
                elif import_type == "dynamic":
                    dynamic_imports.append(imp)
                else:
                    es6_imports.append(imp)

            if es6_imports:
                print(f"📦 ES6 Imports ({len(es6_imports)}):")
                for imp in es6_imports[:5]:
                    if isinstance(imp, dict):
                        import_type = imp.get("import_type", "default")
                        names = imp.get("imported_names", [imp.get("name", "unknown")])
                        module_path = imp.get("module_path", "unknown")
                    else:
                        import_type = getattr(imp, "import_type", "default")
                        names = getattr(imp, "imported_names", [imp.name])
                        module_path = imp.module_path
                    names_str = (
                        ", ".join(names)
                        if len(names) <= 3
                        else f"{names[0]}, ... (+{len(names) - 1})"
                    )
                    print(f"   • {names_str} from '{module_path}' ({import_type})")
                if len(es6_imports) > 5:
                    print(f"   ... and {len(es6_imports) - 5} more")
                print()

            if commonjs_imports:
                print(f"🔧 CommonJS Imports ({len(commonjs_imports)}):")
                for imp in commonjs_imports:
                    name = (
                        imp.name if hasattr(imp, "name") else imp.get("name", "unknown")
                    )
                    module_path = (
                        imp.module_path
                        if hasattr(imp, "module_path")
                        else imp.get("module_path", "unknown")
                    )
                    print(f"   • {name} = require('{module_path}')")
                print()

            if dynamic_imports:
                print(f"⚡ Dynamic Imports ({len(dynamic_imports)}):")
                for imp in dynamic_imports:
                    module_path = (
                        imp.module_path
                        if hasattr(imp, "module_path")
                        else imp.get("module_path", "unknown")
                    )
                    print(f"   • import('{module_path}')")
                print()

        # Show variable analysis
        if variables:
            print("📊 Variable Analysis:")
            print("-" * 30)

            # Group variables by type
            const_vars = []
            let_vars = []
            var_vars = []
            class_props = []

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
                    var_type = getattr(var, "variable_type", "unknown")
                    print(f"   • {var.name}: {var_type}")
                if len(const_vars) > 3:
                    print(f"   ... and {len(const_vars) - 3} more")
                print()

            if let_vars:
                print(f"🔄 Let Variables ({len(let_vars)}):")
                for var in let_vars[:3]:
                    var_type = getattr(var, "variable_type", "unknown")
                    print(f"   • {var.name}: {var_type}")
                if len(let_vars) > 3:
                    print(f"   ... and {len(let_vars) - 3} more")
                print()

            if class_props:
                print(f"🏛️  Class Properties ({len(class_props)}):")
                for prop in class_props:
                    class_name = getattr(prop, "class_name", "Unknown")
                    is_static = getattr(prop, "is_static", False)
                    static_info = " (static)" if is_static else ""
                    print(f"   • {class_name}.{prop.name}{static_info}")
                print()

        # Generate formatted table
        print("📋 Formatted Analysis Table:")
        print("-" * 50)

        # Create JavaScript formatter
        formatter = TableFormatterFactory.create_formatter("javascript", "full")

        # Prepare data for formatter
        formatter_data = {
            "file_path": str(js_file),
            "functions": [
                {
                    "name": f.get("name") if isinstance(f, dict) else f.name,
                    "parameters": (
                        f.get("parameters", [])
                        if isinstance(f, dict)
                        else (f.parameters or [])
                    ),
                    "line_range": {
                        "start": (
                            f.get("start_line", 0)
                            if isinstance(f, dict)
                            else f.start_line
                        ),
                        "end": (
                            f.get("end_line", 0) if isinstance(f, dict) else f.end_line
                        ),
                    },
                    "is_async": (
                        f.get("is_async", False)
                        if isinstance(f, dict)
                        else getattr(f, "is_async", False)
                    ),
                    "is_arrow": (
                        f.get("is_arrow", False)
                        if isinstance(f, dict)
                        else getattr(f, "is_arrow", False)
                    ),
                    "is_method": (
                        f.get("is_method", False)
                        if isinstance(f, dict)
                        else getattr(f, "is_method", False)
                    ),
                    "class_name": (
                        f.get("class_name")
                        if isinstance(f, dict)
                        else getattr(f, "class_name", None)
                    ),
                    "complexity_score": (
                        f.get("complexity_score", 1)
                        if isinstance(f, dict)
                        else getattr(f, "complexity_score", 1)
                    ),
                    "jsdoc": (
                        f.get("docstring")
                        if isinstance(f, dict)
                        else getattr(f, "docstring", None)
                    ),
                }
                for f in functions
            ],
            "classes": [
                {
                    "name": c.get("name") if isinstance(c, dict) else c.name,
                    "superclass": (
                        c.get("superclass")
                        if isinstance(c, dict)
                        else getattr(c, "superclass", None)
                    ),
                    "line_range": {
                        "start": (
                            c.get("start_line", 0)
                            if isinstance(c, dict)
                            else c.start_line
                        ),
                        "end": (
                            c.get("end_line", 0) if isinstance(c, dict) else c.end_line
                        ),
                    },
                }
                for c in classes
            ],
            "variables": [
                {
                    "name": v.get("name") if isinstance(v, dict) else v.name,
                    "variable_type": (
                        v.get("variable_type", "unknown")
                        if isinstance(v, dict)
                        else getattr(v, "variable_type", "unknown")
                    ),
                    "declaration_kind": (
                        v.get("declaration_kind", "unknown")
                        if isinstance(v, dict)
                        else getattr(v, "declaration_kind", "unknown")
                    ),
                    "initializer": (
                        v.get("initializer")
                        if isinstance(v, dict)
                        else getattr(v, "initializer", None)
                    ),
                    "is_constant": (
                        v.get("is_constant", False)
                        if isinstance(v, dict)
                        else getattr(v, "is_constant", False)
                    ),
                    "line_range": {
                        "start": (
                            v.get("start_line", 0)
                            if isinstance(v, dict)
                            else v.start_line
                        ),
                        "end": (
                            v.get("end_line", 0) if isinstance(v, dict) else v.end_line
                        ),
                    },
                }
                for v in variables
            ],
            "imports": [
                {
                    "name": i.get("name") if isinstance(i, dict) else i.name,
                    "source": (
                        i.get("module_path") if isinstance(i, dict) else i.module_path
                    ),
                    "import_type": (
                        i.get("import_type", "default")
                        if isinstance(i, dict)
                        else getattr(i, "import_type", "default")
                    ),
                    "statement": (
                        i.get("raw_text") if isinstance(i, dict) else i.raw_text
                    ),
                }
                for i in imports
            ],
            "exports": [],  # Would be populated if we had export extraction
            "statistics": {
                "function_count": len(functions),
                "class_count": len(classes),
                "variable_count": len(variables),
                "import_count": len(imports),
            },
        }

        # Generate and display formatted table
        try:
            formatted_table = formatter.format(formatter_data)
            print(formatted_table)
        except Exception as e:
            print(f"⚠️  Could not generate formatted table: {e}")
            print("Raw statistics instead:")
            for key, value in formatter_data["statistics"].items():
                print(f"   • {key}: {value}")

        print("\n✅ Analysis Complete!")
        print(f"📄 Successfully analyzed {len(elements)} code elements")

        # Show framework detection if available
        metadata = getattr(result, "metadata", {})
        if metadata:
            print("\n🔍 Detected Features:")
            if metadata.get("is_module"):
                print("   • ES6 Module")
            if metadata.get("is_jsx"):
                print("   • JSX Support")
            framework = metadata.get("framework_type")
            if framework:
                print(f"   • Framework: {framework.title()}")

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

    # Group queries by category
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
                keyword in q
                for keyword in [
                    "async",
                    "arrow",
                    "template",
                    "spread",
                    "await",
                    "yield",
                ]
            )
        ],
        "JSX/React": [q for q in queries if "jsx" in q or "react" in q],
        "Control Flow": [
            q
            for q in queries
            if any(
                keyword in q
                for keyword in ["if", "for", "while", "switch", "try", "catch"]
            )
        ],
        "Advanced": [
            q
            for q in queries
            if any(keyword in q for keyword in ["closure", "iife", "promise", "event"])
        ],
    }

    for category, category_queries in categories.items():
        if category_queries:
            print(f"\n📂 {category} ({len(category_queries)} queries):")
            for query in sorted(category_queries)[:5]:  # Show first 5
                print(f"   • {query}")
            if len(category_queries) > 5:
                print(f"   ... and {len(category_queries) - 5} more")

    print(f"\n📊 Total Available Queries: {len(queries)}")


if __name__ == "__main__":
    print("🚀 JavaScript Analysis Demo")
    print("=" * 60)

    # Run the main analysis
    analyze_modern_javascript()

    # Show query capabilities
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
