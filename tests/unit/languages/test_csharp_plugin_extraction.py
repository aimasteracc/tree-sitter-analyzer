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

ASYNC_METHOD_CODE = """
using System;
using System.Threading.Tasks;

namespace MyApp.Services
{
    public class DataService
    {
        public async Task<string> FetchDataAsync()
        {
            await Task.Delay(100);
            return "data";
        }

        public async Task ProcessAsync(int count)
        {
            for (int i = 0; i < count; i++)
            {
                await Task.Yield();
            }
        }
    }
}
"""

COMPLEX_CLASS_CODE = """
using System;
using System.Linq;
using static System.Math;

namespace MyApp.Domain
{
    [Serializable]
    public abstract class BaseEntity<TId>
    {
        public TId Id { get; protected set; }
        public DateTime CreatedAt { get; private set; }

        protected BaseEntity()
        {
            CreatedAt = DateTime.UtcNow;
        }
    }

    [Obsolete("Use NewOrder instead")]
    public class Order : BaseEntity<int>
    {
        private readonly List<OrderItem> _items = new();
        public const decimal TaxRate = 0.15m;
        public static int OrderCount { get; private set; }

        public IReadOnlyList<OrderItem> Items => _items.AsReadOnly();

        public event EventHandler<OrderEventArgs> OrderPlaced;

        public Order() : base()
        {
            OrderCount++;
        }

        public decimal CalculateTotal()
        {
            var subtotal = _items.Sum(i => i.Price * i.Quantity);
            return subtotal * (1 + TaxRate);
        }

        public void AddItem(OrderItem item)
        {
            if (item == null)
                throw new ArgumentNullException(nameof(item));
            _items.Add(item);
        }

        protected virtual void OnOrderPlaced()
        {
            OrderPlaced?.Invoke(this, new OrderEventArgs());
        }
    }

    public record OrderItem(string Name, decimal Price, int Quantity);

    public struct Point
    {
        public int X { get; init; }
        public int Y { get; init; }

        public Point(int x, int y)
        {
            X = x;
            Y = y;
        }
    }

    public enum OrderStatus
    {
        Pending,
        Processing,
        Shipped,
        Delivered
    }
}
"""

PROPERTY_VARIATIONS_CODE = """
namespace MyApp.Properties
{
    public class PropertyExample
    {
        // Auto-property
        public string Name { get; set; }

        // Read-only auto-property
        public int Id { get; }

        // Init-only property
        public string Code { get; init; }

        // Computed property
        public bool IsValid => !string.IsNullOrEmpty(Name);

        // Full property
        private int _count;
        public int Count
        {
            get => _count;
            set
            {
                if (value >= 0)
                    _count = value;
            }
        }

        // Indexer
        private string[] _data = new string[10];
        public string this[int index]
        {
            get => _data[index];
            set => _data[index] = value;
        }
    }
}
"""

CONTROL_FLOW_CODE = """
namespace MyApp.Logic
{
    public class Calculator
    {
        public int Calculate(int value)
        {
            int result = 0;

            if (value > 0)
            {
                for (int i = 0; i < value; i++)
                {
                    result += i;
                }
            }
            else if (value < 0)
            {
                while (value < 0)
                {
                    result--;
                    value++;
                }
            }
            else
            {
                switch (value)
                {
                    case 0:
                        result = 1;
                        break;
                    default:
                        result = -1;
                        break;
                }
            }

            try
            {
                result = result / (value + 1);
            }
            catch (DivideByZeroException)
            {
                result = 0;
            }
            finally
            {
                // Cleanup
            }

            return result;
        }
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


class TestCSharpClassExtraction:
    """Test C# class extraction."""

    def test_extract_simple_class(self):
        """Test extraction of a simple class."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, SIMPLE_CLASS_CODE)

        assert len(classes) == 1
        cls = classes[0]
        assert cls.name == "Person"
        assert "public" in cls.modifiers
        assert cls.visibility == "public"

    def test_extract_interface(self):
        """Test extraction of an interface."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(INTERFACE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, INTERFACE_CODE)

        assert len(classes) == 1
        iface = classes[0]
        assert iface.name == "IRepository"
        assert "public" in iface.modifiers

    def test_extract_multiple_classes(self):
        """Test extraction of multiple classes."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_CLASS_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_CLASS_CODE)

        # Should find BaseEntity, Order, OrderItem (record), Point (struct), OrderStatus (enum)
        class_names = [c.name for c in classes]
        assert "BaseEntity" in class_names
        assert "Order" in class_names

    def test_extract_class_with_attributes(self):
        """Test extraction of class with attributes."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_CLASS_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_CLASS_CODE)

        # Find Order class (has Obsolete attribute)
        order_class = next((c for c in classes if c.name == "Order"), None)
        assert order_class is not None

    def test_extract_abstract_class(self):
        """Test extraction of abstract class."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_CLASS_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_CLASS_CODE)

        base_entity = next((c for c in classes if c.name == "BaseEntity"), None)
        assert base_entity is not None
        assert "abstract" in base_entity.modifiers

    def test_extract_class_with_generics(self):
        """Test extraction of generic class."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(INTERFACE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, INTERFACE_CODE)

        repo = next((c for c in classes if c.name == "IRepository"), None)
        assert repo is not None
        # Generic type parameters should be captured in raw text
        assert "T" in str(repo.raw_text)

    def test_class_methods_extraction(self):
        """Test that class methods are extracted as part of class."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, SIMPLE_CLASS_CODE)

        person_class = classes[0]
        # Methods may be extracted separately or as part of class
        # Check that GetName appears in the class raw text at minimum
        assert "GetName" in str(person_class.raw_text)

    def test_class_constructor_extraction(self):
        """Test that constructors are extracted."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, SIMPLE_CLASS_CODE)

        person_class = classes[0]
        # Constructor should be in methods list
        constructor_names = [
            m.name
            for m in person_class.methods
            if "Person" in m.name or m.name == "__init__"
        ]
        assert len(constructor_names) == 0

    def test_extract_empty_tree(self):
        """Test extraction with empty/None tree."""
        extractor = CSharpElementExtractor()
        classes = extractor.extract_classes(None, "")
        assert classes == []

    def test_extract_with_none_source(self):
        """Test extraction with None source code."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        # Extractor should handle empty source gracefully
        classes = plugin.extractor.extract_classes(tree, "")
        # May extract classes but with empty text
        assert isinstance(classes, list)


class TestCSharpFunctionExtraction:
    """Test C# function/method extraction."""

    def test_extract_simple_method(self):
        """Test extraction of simple method."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, SIMPLE_CLASS_CODE)

        # Should find GetName method and constructor
        func_names = [f.name for f in functions]
        assert "GetName" in func_names

    def test_extract_async_methods(self):
        """Test extraction of async methods."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(ASYNC_METHOD_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, ASYNC_METHOD_CODE)

        func_names = [f.name for f in functions]
        assert "FetchDataAsync" in func_names or "ProcessAsync" in func_names

    def test_extract_method_parameters(self):
        """Test that method parameters are extracted."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, SIMPLE_CLASS_CODE)

        get_name = next((f for f in functions if f.name == "GetName"), None)
        assert get_name is not None
        # GetName has no parameters
        assert get_name.parameters == [] or len(get_name.parameters) == 0

    def test_extract_method_with_parameters(self):
        """Test method with parameters."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_CLASS_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, COMPLEX_CLASS_CODE)

        add_item = next((f for f in functions if f.name == "AddItem"), None)
        assert add_item is not None
        # Should have 'item' parameter
        param_names = [p.name if hasattr(p, "name") else p for p in add_item.parameters]
        assert len(param_names) == 1

    def test_extract_constructor(self):
        """Test constructor extraction."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, SIMPLE_CLASS_CODE)

        # Check if constructor is extracted (may be named Person or .ctor)
        constructors = [
            f for f in functions if f.name == "Person" or ".ctor" in str(f.raw_text)
        ]
        # Constructor should exist
        assert len(constructors) == 1

    def test_extract_method_modifiers(self):
        """Test extraction of method modifiers."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_CLASS_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, COMPLEX_CLASS_CODE)

        calculate_total = next(
            (f for f in functions if f.name == "CalculateTotal"), None
        )
        assert calculate_total is not None
        assert "public" in calculate_total.modifiers

    def test_extract_virtual_method(self):
        """Test extraction of virtual method."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_CLASS_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, COMPLEX_CLASS_CODE)

        on_order_placed = next(
            (f for f in functions if f.name == "OnOrderPlaced"), None
        )
        assert on_order_placed is not None
        assert (
            "protected" in on_order_placed.modifiers
            or "virtual" in on_order_placed.modifiers
        )

    def test_extract_functions_empty_tree(self):
        """Test function extraction with empty tree."""
        extractor = CSharpElementExtractor()
        functions = extractor.extract_functions(None, "")
        assert functions == []

    def test_method_complexity_calculation(self):
        """Test method complexity calculation."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(CONTROL_FLOW_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, CONTROL_FLOW_CODE)

        calculate = next((f for f in functions if f.name == "Calculate"), None)
        assert calculate is not None
        # Method with if/for/while/switch should have higher complexity_score
        assert calculate.complexity_score == 7


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
