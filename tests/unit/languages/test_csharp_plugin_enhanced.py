"""Enhanced tests for C# plugin functionality with focus on advanced features."""

import tree_sitter

from tree_sitter_analyzer.languages.csharp_plugin import (
    CSharpPlugin,
)

# Enhanced C# code samples for testing
NAMESPACE_CODE = """
using System;
using System.Collections.Generic;

namespace MyApp.Core
{
    namespace Models
    {
        public class User
        {
            public string Name { get; set; }
        }
    }

    namespace Services
    {
        public class UserService
        {
            public void CreateUser() { }
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

    public interface ILogger
    {
        void Log(string message);
        void LogError(string error);
    }
}
"""

ENUM_CODE = """
namespace MyApp.Enums
{
    public enum OrderStatus
    {
        Pending = 0,
        Processing = 1,
        Shipped = 2,
        Delivered = 3,
        Cancelled = 4
    }

    public enum Priority
    {
        Low,
        Medium,
        High,
        Critical
    }
}
"""

COMPLEX_STRUCTURE_CODE = """
using System;
using System.Collections.Generic;
using System.Linq;

namespace MyApp.Domain
{
    [Serializable]
    public abstract class BaseEntity
    {
        public int Id { get; protected set; }
        public DateTime CreatedAt { get; private set; }
    }

    public class Order : BaseEntity, IComparable<Order>
    {
        private List<OrderItem> _items = new List<OrderItem>();
        public const decimal TaxRate = 0.15m;
        public static int TotalOrders { get; private set; }

        public event EventHandler<OrderEventArgs> OrderPlaced;

        public Order()
        {
            CreatedAt = DateTime.UtcNow;
        }

        public decimal CalculateTotal()
        {
            return _items.Sum(i => i.Price * i.Quantity) * (1 + TaxRate);
        }

        public int CompareTo(Order other)
        {
            return this.Id.CompareTo(other.Id);
        }
    }

    public class OrderItem
    {
        public string Name { get; set; }
        public decimal Price { get; set; }
        public int Quantity { get; set; }
    }

    public class OrderEventArgs : EventArgs
    {
        public Order Order { get; set; }
    }
}
"""

GENERIC_CODE = """
using System;
using System.Collections.Generic;

namespace MyApp.Generic
{
    public class Repository<T> where T : class
    {
        public T GetById(int id) => default;
        public void Save(T entity) { }
    }

    public class Service<T, TKey> where T : class where TKey : struct
    {
        public TKey GetKey(T entity) => default;
    }

    public interface IProcessor<in TInput, out TOutput>
    {
        TOutput Process(TInput input);
    }
}
"""

ASYNC_CODE = """
using System;
using System.Threading.Tasks;

namespace MyApp.Async
{
    public class AsyncService
    {
        public async Task<string> GetDataAsync()
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

        public async IAsyncEnumerable<int> GetNumbersAsync()
        {
            for (int i = 0; i < 10; i++)
            {
                await Task.Delay(10);
                yield return i;
            }
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


class TestCSharpClassRecognition:
    """Test C# class recognition and extraction."""

    def test_extract_simple_class(self):
        """Test extraction of a simple class."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        assert len(classes) >= 1
        entity_class = next((c for c in classes if c.name == "BaseEntity"), None)
        assert entity_class is not None
        assert "abstract" in entity_class.modifiers
        assert "public" in entity_class.modifiers

    def test_extract_class_with_inheritance(self):
        """Test extraction of class with inheritance."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        order_class = next((c for c in classes if c.name == "Order"), None)
        assert order_class is not None
        # Should have BaseEntity as base class
        assert "BaseEntity" in str(order_class.raw_text)

    def test_extract_class_with_interfaces(self):
        """Test extraction of class implementing interfaces."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        order_class = next((c for c in classes if c.name == "Order"), None)
        assert order_class is not None
        # Should implement IComparable<Order>
        assert "IComparable" in str(order_class.raw_text)

    def test_extract_generic_class(self):
        """Test extraction of generic class."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(GENERIC_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, GENERIC_CODE)

        repository_class = next((c for c in classes if "Repository" in c.name), None)
        assert repository_class is not None
        # Should capture generic type parameter
        assert "T" in str(repository_class.raw_text)

    def test_extract_class_with_attributes(self):
        """Test extraction of class with attributes."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        entity_class = next((c for c in classes if c.name == "BaseEntity"), None)
        assert entity_class is not None
        # Should have Serializable attribute
        assert "Serializable" in str(entity_class.raw_text)

    def test_extract_multiple_classes(self):
        """Test extraction of multiple classes."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        class_names = [c.name for c in classes]
        assert "BaseEntity" in class_names
        assert "Order" in class_names
        assert "OrderItem" in class_names
        assert "OrderEventArgs" in class_names

    def test_class_visibility_modifiers(self):
        """Test extraction of class visibility modifiers."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        for cls in classes:
            if cls.name in ["BaseEntity", "Order", "OrderItem", "OrderEventArgs"]:
                assert "public" in cls.modifiers

    def test_class_namespace_inclusion(self):
        """Test that namespace is included in class information."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        order_class = next((c for c in classes if c.name == "Order"), None)
        assert order_class is not None
        # Should have full qualified name with namespace
        assert "MyApp.Domain" in order_class.full_qualified_name


class TestCSharpMethodRecognition:
    """Test C# method/function recognition and extraction."""

    def test_extract_simple_method(self):
        """Test extraction of a simple method."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, COMPLEX_STRUCTURE_CODE)

        calculate_total = next(
            (f for f in functions if f.name == "CalculateTotal"), None
        )
        assert calculate_total is not None
        assert "public" in calculate_total.modifiers

    def test_extract_async_method(self):
        """Test extraction of async method."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(ASYNC_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, ASYNC_CODE)

        async_methods = [f for f in functions if "Async" in f.name]
        assert len(async_methods) >= 2
        assert "GetDataAsync" in [f.name for f in async_methods]

    def test_extract_generic_method(self):
        """Test extraction of generic method."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(GENERIC_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, GENERIC_CODE)

        # Should find methods with generic type parameters
        assert len(functions) >= 3

    def test_method_return_type(self):
        """Test that method return type is extracted."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, COMPLEX_STRUCTURE_CODE)

        calculate_total = next(
            (f for f in functions if f.name == "CalculateTotal"), None
        )
        assert calculate_total is not None
        # Should have decimal return type
        assert "decimal" in str(calculate_total.raw_text)

    def test_method_parameters(self):
        """Test that method parameters are extracted."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, COMPLEX_STRUCTURE_CODE)

        compare_to = next((f for f in functions if f.name == "CompareTo"), None)
        assert compare_to is not None
        # Should have Order parameter
        assert "Order" in str(compare_to.raw_text)

    def test_method_modifiers(self):
        """Test extraction of method modifiers."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, COMPLEX_STRUCTURE_CODE)

        for func in functions:
            if func.name in ["CalculateTotal", "CompareTo"]:
                assert "public" in func.modifiers

    def test_method_complexity(self):
        """Test that method complexity is calculated."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, COMPLEX_STRUCTURE_CODE)

        calculate_total = next(
            (f for f in functions if f.name == "CalculateTotal"), None
        )
        assert calculate_total is not None
        # Method with LINQ should have some complexity
        assert calculate_total.complexity_score >= 1

    def test_extract_interface_method(self):
        """Test extraction of interface methods."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(INTERFACE_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, INTERFACE_CODE)

        # Should find methods in interfaces
        assert len(functions) >= 5


class TestCSharpPropertyRecognition:
    """Test C# property recognition and extraction."""

    def test_extract_auto_property(self):
        """Test extraction of auto-property."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        order_class = next((c for c in classes if c.name == "Order"), None)
        assert order_class is not None
        # Should have properties
        assert "Id" in str(order_class.raw_text)

    def test_extract_readonly_property(self):
        """Test extraction of readonly property."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        entity_class = next((c for c in classes if c.name == "BaseEntity"), None)
        assert entity_class is not None
        # Should have readonly properties
        assert "CreatedAt" in str(entity_class.raw_text)

    def test_extract_static_property(self):
        """Test extraction of static property."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        order_class = next((c for c in classes if c.name == "Order"), None)
        assert order_class is not None
        # Should have static property
        assert "TotalOrders" in str(order_class.raw_text)

    def test_extract_const_property(self):
        """Test extraction of const property."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        order_class = next((c for c in classes if c.name == "Order"), None)
        assert order_class is not None
        # Should have const property
        assert "TaxRate" in str(order_class.raw_text)

    def test_property_visibility(self):
        """Test extraction of property visibility modifiers."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        order_class = next((c for c in classes if c.name == "Order"), None)
        assert order_class is not None
        # Should have public properties
        assert "public" in str(order_class.raw_text)


class TestCSharpNamespaceRecognition:
    """Test C# namespace recognition and extraction."""

    def test_extract_single_namespace(self):
        """Test extraction of single namespace."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        for cls in classes:
            if cls.full_qualified_name:
                assert "MyApp.Domain" in cls.full_qualified_name

    def test_extract_nested_namespace(self):
        """Test extraction of nested namespaces."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(NAMESPACE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, NAMESPACE_CODE)

        # Should find classes in nested namespaces
        class_names = [c.name for c in classes]
        assert "User" in class_names
        assert "UserService" in class_names

    def test_namespace_full_qualified_name(self):
        """Test that full qualified name includes namespace."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(NAMESPACE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, NAMESPACE_CODE)

        user_class = next((c for c in classes if c.name == "User"), None)
        assert user_class is not None
        # The full qualified name should contain the class name
        assert "User" in user_class.full_qualified_name
        # And should contain at least part of the namespace
        assert "MyApp.Core" in user_class.full_qualified_name

    def test_multiple_namespaces(self):
        """Test extraction from multiple namespaces."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(NAMESPACE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, NAMESPACE_CODE)

        # Should find classes from different namespaces
        namespaces = set()
        for cls in classes:
            if cls.full_qualified_name:
                parts = cls.full_qualified_name.split(".")
                if len(parts) > 1:
                    namespaces.add(parts[0])

        assert "MyApp" in namespaces


class TestCSharpInterfaceRecognition:
    """Test C# interface recognition and extraction."""

    def test_extract_simple_interface(self):
        """Test extraction of simple interface."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(INTERFACE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, INTERFACE_CODE)

        repo_interface = next((c for c in classes if c.name == "IRepository"), None)
        assert repo_interface is not None

    def test_extract_generic_interface(self):
        """Test extraction of generic interface."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(INTERFACE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, INTERFACE_CODE)

        repo_interface = next((c for c in classes if c.name == "IRepository"), None)
        assert repo_interface is not None
        # Should capture generic type parameter
        assert "T" in str(repo_interface.raw_text)

    def test_extract_multiple_interfaces(self):
        """Test extraction of multiple interfaces."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(INTERFACE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, INTERFACE_CODE)

        interface_names = [c.name for c in classes]
        assert "IRepository" in interface_names
        assert "ILogger" in interface_names

    def test_interface_methods(self):
        """Test that interface methods are extracted."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(INTERFACE_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, INTERFACE_CODE)

        # Should find methods in interfaces
        assert len(functions) >= 5

    def test_interface_visibility(self):
        """Test that interfaces have public visibility."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(INTERFACE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, INTERFACE_CODE)

        for cls in classes:
            if cls.name in ["IRepository", "ILogger"]:
                assert "public" in cls.modifiers


class TestCSharpEnumRecognition:
    """Test C# enum recognition and extraction."""

    def test_extract_simple_enum(self):
        """Test extraction of simple enum."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(ENUM_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, ENUM_CODE)

        order_status = next((c for c in classes if c.name == "OrderStatus"), None)
        assert order_status is not None

    def test_extract_enum_with_values(self):
        """Test extraction of enum with explicit values."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(ENUM_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, ENUM_CODE)

        order_status = next((c for c in classes if c.name == "OrderStatus"), None)
        assert order_status is not None
        # Should capture enum values
        assert "Pending" in str(order_status.raw_text)
        assert "Processing" in str(order_status.raw_text)

    def test_extract_multiple_enums(self):
        """Test extraction of multiple enums."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(ENUM_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, ENUM_CODE)

        enum_names = [c.name for c in classes]
        assert "OrderStatus" in enum_names
        assert "Priority" in enum_names

    def test_enum_visibility(self):
        """Test that enums have public visibility."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(ENUM_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, ENUM_CODE)

        for cls in classes:
            if cls.name in ["OrderStatus", "Priority"]:
                assert "public" in cls.modifiers


class TestCSharpComplexStructures:
    """Test extraction of complex C# code structures."""

    def test_extract_class_with_events(self):
        """Test extraction of class with events."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        order_class = next((c for c in classes if c.name == "Order"), None)
        assert order_class is not None
        # Should have event
        assert "OrderPlaced" in str(order_class.raw_text)

    def test_extract_class_with_indexers(self):
        """Test extraction of class with indexers (if present)."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        # Just verify extraction works
        assert len(classes) >= 1

    def test_extract_class_with_operators(self):
        """Test extraction of class with operators (if present)."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        # Just verify extraction works
        assert len(classes) >= 1

    def test_extract_generic_constraints(self):
        """Test extraction of generic type constraints."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(GENERIC_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, GENERIC_CODE)

        repository_class = next((c for c in classes if "Repository" in c.name), None)
        assert repository_class is not None
        # Should capture type constraints
        assert "where T" in str(repository_class.raw_text)

    def test_extract_async_enumerable(self):
        """Test extraction of IAsyncEnumerable."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(ASYNC_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, ASYNC_CODE)

        get_numbers = next((f for f in functions if f.name == "GetNumbersAsync"), None)
        assert get_numbers is not None
        # Should have IAsyncEnumerable return type
        assert "IAsyncEnumerable" in str(get_numbers.raw_text)


class TestCSharpQueryAccuracy:
    """Test accuracy of C# queries."""

    def test_class_query_accuracy(self):
        """Test that class query accurately identifies classes."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        # Should not extract non-class elements
        for cls in classes:
            assert cls.name is not None
            assert len(cls.name) > 0

    def test_method_query_accuracy(self):
        """Test that method query accurately identifies methods."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, COMPLEX_STRUCTURE_CODE)

        # Should not extract non-method elements
        for func in functions:
            assert func.name is not None
            assert len(func.name) > 0

    def test_property_query_accuracy(self):
        """Test that property query accurately identifies properties."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        # Properties should be within classes
        for cls in classes:
            if cls.name == "Order":
                assert "Id" in str(cls.raw_text)
                assert "CreatedAt" in str(cls.raw_text)

    def test_namespace_query_accuracy(self):
        """Test that namespace is accurately captured."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(NAMESPACE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, NAMESPACE_CODE)

        # All classes should have correct namespace
        for cls in classes:
            if cls.full_qualified_name:
                assert "MyApp" in cls.full_qualified_name

    def test_interface_query_accuracy(self):
        """Test that interface query accurately identifies interfaces."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(INTERFACE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, INTERFACE_CODE)

        # Should find interfaces
        interface_names = [c.name for c in classes]
        assert "IRepository" in interface_names
        assert "ILogger" in interface_names

    def test_enum_query_accuracy(self):
        """Test that enum query accurately identifies enums."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(ENUM_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, ENUM_CODE)

        # Should find enums
        enum_names = [c.name for c in classes]
        assert "OrderStatus" in enum_names
        assert "Priority" in enum_names

    def test_no_false_positives(self):
        """Test that queries don't produce false positives."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        # Should not extract random text as classes
        for cls in classes:
            assert cls.name is not None
            assert cls.name.strip() != ""

    def test_no_false_negatives(self):
        """Test that queries don't miss elements."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        # Should find all expected classes
        class_names = [c.name for c in classes]
        assert "BaseEntity" in class_names
        assert "Order" in class_names
        assert "OrderItem" in class_names
        assert "OrderEventArgs" in class_names

    def test_line_number_accuracy(self):
        """Test that line numbers are accurate."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_STRUCTURE_CODE)

        for cls in classes:
            assert cls.start_line > 0
            assert cls.end_line >= cls.start_line

    def test_complexity_calculation_accuracy(self):
        """Test that complexity calculation is accurate."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, COMPLEX_STRUCTURE_CODE)

        calculate_total = next(
            (f for f in functions if f.name == "CalculateTotal"), None
        )
        assert calculate_total is not None
        # LINQ query should have reasonable complexity
        assert calculate_total.complexity_score >= 1
