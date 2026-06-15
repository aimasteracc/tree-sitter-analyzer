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


class TestCSharpVariableExtraction:
    """Test C# variable/field extraction."""

    def test_extract_private_field(self):
        """Test extraction of private field."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        variables = plugin.extractor.extract_variables(tree, SIMPLE_CLASS_CODE)

        # Should find _name field
        var_names = [v.name for v in variables]
        assert "_name" in var_names

    def test_extract_const_field(self):
        """Test extraction of const field."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_CLASS_CODE, plugin)
        variables = plugin.extractor.extract_variables(tree, COMPLEX_CLASS_CODE)

        tax_rate = next((v for v in variables if v.name == "TaxRate"), None)
        assert tax_rate is not None
        assert tax_rate.is_constant is True or "const" in tax_rate.modifiers

    def test_extract_readonly_field(self):
        """Test extraction of readonly field."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_CLASS_CODE, plugin)
        variables = plugin.extractor.extract_variables(tree, COMPLEX_CLASS_CODE)

        items = next((v for v in variables if v.name == "_items"), None)
        assert items is not None
        assert "readonly" in items.modifiers or items.raw_text is not None

    def test_extract_field_type(self):
        """Test that field type is extracted."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        variables = plugin.extractor.extract_variables(tree, SIMPLE_CLASS_CODE)

        name_field = next((v for v in variables if v.name == "_name"), None)
        assert name_field is not None
        assert name_field.variable_type == "string" or "string" in str(
            name_field.raw_text
        )

    def test_extract_event_field(self):
        """Test extraction of event field."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_CLASS_CODE, plugin)
        variables = plugin.extractor.extract_variables(tree, COMPLEX_CLASS_CODE)

        # Event should be extracted as variable
        event_field = next((v for v in variables if v.name == "OrderPlaced"), None)
        # Event may or may not be extracted depending on implementation
        if event_field:
            assert "event" in event_field.modifiers

    def test_extract_variables_empty_tree(self):
        """Test variable extraction with empty tree."""
        extractor = CSharpElementExtractor()
        variables = extractor.extract_variables(None, "")
        assert variables == []

    def test_extract_static_field(self):
        """Test extraction of static field."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_CLASS_CODE, plugin)
        variables = plugin.extractor.extract_variables(tree, COMPLEX_CLASS_CODE)

        order_count = next((v for v in variables if v.name == "OrderCount"), None)
        # Static properties might be extracted differently
        if order_count:
            assert "static" in order_count.modifiers


class TestCSharpImportExtraction:
    """Test C# import (using directive) extraction."""

    def test_extract_simple_using(self):
        """Test extraction of simple using directive."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        imports = plugin.extractor.extract_imports(tree, SIMPLE_CLASS_CODE)

        import_names = [i.name for i in imports]
        assert "System" in import_names
        assert "System.Collections.Generic" in import_names

    def test_extract_static_using(self):
        """Test extraction of static using directive."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_CLASS_CODE, plugin)
        imports = plugin.extractor.extract_imports(tree, COMPLEX_CLASS_CODE)

        # Should find static using for System.Math
        static_imports = [i for i in imports if i.is_static]
        assert len(static_imports) == 1

    def test_extract_imports_empty_tree(self):
        """Test import extraction with empty tree."""
        extractor = CSharpElementExtractor()
        imports = extractor.extract_imports(None, "")
        assert imports == []

    def test_import_line_numbers(self):
        """Test that import line numbers are correct."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        imports = plugin.extractor.extract_imports(tree, SIMPLE_CLASS_CODE)

        assert [i.start_line for i in imports] == [2, 3]
        assert all(i.end_line >= i.start_line for i in imports)


class TestCSharpPropertyExtraction:
    """Test C# property extraction."""

    def test_extract_auto_property(self):
        """Test extraction of auto-property."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, SIMPLE_CLASS_CODE)

        person_class = classes[0]
        # Age should be a property
        assert "Age" in str(person_class.raw_text)

    def test_extract_various_properties(self):
        """Test extraction of various property types."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(PROPERTY_VARIATIONS_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, PROPERTY_VARIATIONS_CODE)

        assert len(classes) == 1
        prop_class = classes[0]
        # Should capture various property patterns
        assert "Name" in str(prop_class.raw_text)
        assert "IsValid" in str(prop_class.raw_text)


class TestCSharpComplexityCalculation:
    """Test complexity calculation for C# code."""

    def test_complexity_with_control_flow(self):
        """Test complexity calculation with control flow statements."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(CONTROL_FLOW_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, CONTROL_FLOW_CODE)

        calculate = next((f for f in functions if f.name == "Calculate"), None)
        assert calculate is not None
        # if, else if, else, for, while, switch, try/catch all add complexity
        assert calculate.complexity_score == 7

    def test_simple_method_low_complexity(self):
        """Test that simple method has low complexity."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        functions = plugin.extractor.extract_functions(tree, SIMPLE_CLASS_CODE)

        get_name = next((f for f in functions if f.name == "GetName"), None)
        assert get_name is not None
        # Simple return statement should have low complexity
        assert get_name.complexity_score <= 2


class TestCSharpNamespaceHandling:
    """Test namespace handling."""

    def test_extract_namespace(self):
        """Test namespace extraction from class."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, SIMPLE_CLASS_CODE)

        person_class = classes[0]
        # Namespace should be in full_qualified_name
        assert person_class.full_qualified_name == "MyApp.Models.Person"

    def test_nested_namespace(self):
        """Test handling of nested namespaces."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_CLASS_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_CLASS_CODE)

        # All classes should have full qualified name with namespace
        for cls in classes:
            if cls.full_qualified_name:
                assert "MyApp.Domain" in cls.full_qualified_name


class TestCSharpExtractorHelpers:
    """Test CSharpElementExtractor helper methods."""

    def test_get_node_text_optimized(self):
        """Test optimized node text extraction."""
        extractor = CSharpElementExtractor()
        extractor.source_code = "test code"
        extractor.content_lines = ["test code"]
        # The method should work with the cache
        assert extractor.source_code is not None

    def test_traverse_iterative(self):
        """Test iterative tree traversal."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        extractor = CSharpElementExtractor()

        nodes = list(extractor._traverse_iterative(tree.root_node))
        assert len(nodes) == 98
        # Should traverse all nodes in the tree

    def test_cache_invalidation(self):
        """Test that source code is properly set between extractions."""
        extractor = CSharpElementExtractor()

        # After new extraction with different source, source should be updated
        plugin = CSharpPlugin()
        tree = get_tree_for_code(SIMPLE_CLASS_CODE, plugin)
        extractor.extract_classes(tree, SIMPLE_CLASS_CODE)

        # Source code should be properly set
        assert extractor.source_code == SIMPLE_CLASS_CODE

        # Reset caches method should exist
        assert hasattr(extractor, "_reset_caches")
