"""Tests for C# plugin functionality."""

import tree_sitter

from tree_sitter_analyzer.languages.csharp_plugin import (
    CSharpElementExtractor,
    CSharpPlugin,
)

# Sample C# code snippets for testing
SIMPLE_CLASS_CODE = """
using System;
using System.Collections.Generic;

namespace MyApp.Models
{
    public class Person
    {
        private string _name;
        public int Age { get; set; }

        public Person(string name, int age)
        {
            _name = name;
            Age = age;
        }

        public string GetName()
        {
            return _name;
        }
    }
}
"""

INTERFACE_CODE = """
using System;

namespace MyApp.Interfaces
{
    public interface IRepository<T>
    {
        T GetById(int id);
        void Save(T entity);
        void Delete(int id);
    }
}
"""

def get_tree_for_code(code: str, plugin: CSharpPlugin):
    """Helper to parse C# code and return tree."""
    language = plugin.get_tree_sitter_language()
    parser = tree_sitter.Parser()
    if hasattr(parser, "set_language"):
        parser.set_language(language)
    elif hasattr(parser, "language"):
        parser.language = language
    else:
        parser = tree_sitter.Parser(language)
    return parser.parse(code.encode("utf-8"))


# ---------------------------------------------------------------------------
# Issue #767 — C# namespace extracted as Package element
# ---------------------------------------------------------------------------


class TestCSharpNamespacePackageExtraction:
    """Issue #767 — namespace_declaration must be surfaced as a Package element
    so that package.name is populated (was always 'unknown' before the fix)."""

    def test_qualified_namespace_produces_package_element(self):
        """Qualified namespace (MyApp.Models) is extracted as Package."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        packages = plugin.extractor.extract_packages(tree, SIMPLE_CLASS_CODE)

        assert len(packages) == 1
        assert packages[0].name == "MyApp.Models"

    def test_package_element_language_is_csharp(self):
        """Extracted Package element carries language='csharp'."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        packages = plugin.extractor.extract_packages(tree, SIMPLE_CLASS_CODE)

        assert packages[0].language == "csharp"

    def test_simple_namespace_produces_package_element(self):
        """Single-segment namespace (MyApp) is also extracted."""
        src = "namespace MyApp\n{\n    public class Foo {}\n}\n"
        plugin = CSharpPlugin()
        tree = get_tree_for_code(src, plugin)
        packages = plugin.extractor.extract_packages(tree, src)

        assert len(packages) == 1
        assert packages[0].name == "MyApp"

    def test_file_scoped_namespace_produces_package_element(self):
        """C# 10 file-scoped namespace declarations use a distinct node type."""
        src = "namespace MyApp.Services;\npublic class Foo {}\n"
        plugin = CSharpPlugin()
        tree = get_tree_for_code(src, plugin)
        packages = plugin.extractor.extract_packages(tree, src)

        assert len(packages) == 1
        assert packages[0].name == "MyApp.Services"

    def test_multiple_block_namespaces_are_all_extracted(self):
        src = (
            "namespace First { public class A {} }\n"
            "namespace Second { public class B {} }\n"
        )
        plugin = CSharpPlugin()
        tree = get_tree_for_code(src, plugin)
        packages = plugin.extractor.extract_packages(tree, src)

        assert [pkg.name for pkg in packages] == ["First", "Second"]

    def test_grouped_extract_elements_includes_packages(self):
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        grouped = plugin.extract_elements(tree, SIMPLE_CLASS_CODE)

        assert "packages" in grouped
        assert grouped["packages"][0].name == "MyApp.Models"

    def test_no_namespace_returns_empty(self):
        """A C# file without a namespace declaration returns no Package."""
        src = "public class Bare {}\n"
        plugin = CSharpPlugin()
        tree = get_tree_for_code(src, plugin)
        packages = plugin.extractor.extract_packages(tree, src)

        assert packages == []

    def test_none_tree_returns_empty(self):
        """extract_packages with a None tree returns an empty list."""
        extractor = CSharpElementExtractor()
        assert extractor.extract_packages(None, "") == []

    def test_interface_namespace_extracted(self):
        """Interface file namespace is correctly captured."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(INTERFACE_CODE, plugin)
        packages = plugin.extractor.extract_packages(tree, INTERFACE_CODE)

        assert len(packages) == 1
        assert packages[0].name == "MyApp.Interfaces"


class TestCSharpPerClassNamespaceFqn:
    """Bug #977 — each class's FQN must reflect its OWN enclosing namespace."""

    def test_multiple_block_namespaces(self):
        """Classes in the 2nd+ namespace get that namespace, not the first."""
        src = "namespace A { class X {} } namespace B { class Y {} }\n"
        plugin = CSharpPlugin()
        tree = get_tree_for_code(src, plugin)
        classes = plugin.extractor.extract_classes(tree, src)

        by_name = {c.name: c for c in classes}
        assert by_name["X"].full_qualified_name == "A.X"
        assert by_name["Y"].full_qualified_name == "B.Y"

    def test_nested_block_namespaces(self):
        """Nested block namespaces concatenate with '.'."""
        src = "namespace Outer { namespace Inner { class C {} } }\n"
        plugin = CSharpPlugin()
        tree = get_tree_for_code(src, plugin)
        classes = plugin.extractor.extract_classes(tree, src)

        by_name = {c.name: c for c in classes}
        assert by_name["C"].full_qualified_name == "Outer.Inner.C"

    def test_single_block_namespace_regression(self):
        """A single block namespace still produces the correct FQN."""
        src = "namespace App.Models { public class Person {} }\n"
        plugin = CSharpPlugin()
        tree = get_tree_for_code(src, plugin)
        classes = plugin.extractor.extract_classes(tree, src)

        by_name = {c.name: c for c in classes}
        assert by_name["Person"].full_qualified_name == "App.Models.Person"

    def test_file_scoped_namespace_regression(self):
        """A file-scoped namespace still produces the correct FQN."""
        src = "namespace App.Models;\npublic class Person {}\n"
        plugin = CSharpPlugin()
        tree = get_tree_for_code(src, plugin)
        classes = plugin.extractor.extract_classes(tree, src)

        by_name = {c.name: c for c in classes}
        assert by_name["Person"].full_qualified_name == "App.Models.Person"

    def test_no_namespace_regression(self):
        """A class with no enclosing namespace keeps its bare name."""
        src = "public class Bare {}\n"
        plugin = CSharpPlugin()
        tree = get_tree_for_code(src, plugin)
        classes = plugin.extractor.extract_classes(tree, src)

        by_name = {c.name: c for c in classes}
        assert by_name["Bare"].full_qualified_name == "Bare"

    def test_nested_class_under_file_scoped_namespace(self):
        """A class nested inside another class under a file-scoped namespace.

        The inner class node is two levels below the compilation unit, so the
        walk-to-compilation-unit loop iterates before resolving the file-scoped
        namespace. Outer/Inner are both attributed to the file-scoped namespace
        (nested-class containment is not part of the FQN here, matching prior
        behaviour).
        """
        src = "namespace App.Models;\npublic class Outer { class Inner {} }\n"
        plugin = CSharpPlugin()
        tree = get_tree_for_code(src, plugin)
        classes = plugin.extractor.extract_classes(tree, src)

        by_name = {c.name: c for c in classes}
        assert by_name["Outer"].full_qualified_name == "App.Models.Outer"
        assert by_name["Inner"].full_qualified_name == "App.Models.Inner"
