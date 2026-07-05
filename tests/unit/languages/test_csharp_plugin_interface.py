"""Tests for C# plugin functionality."""

import tree_sitter

from tree_sitter_analyzer.languages.csharp_plugin import (
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


class TestCSharpPluginInterface:
    """Test CSharp plugin interface implementation."""

    def test_plugin_instantiation(self):
        """Test that plugin instantiates successfully."""
        plugin = CSharpPlugin()
        assert isinstance(plugin, CSharpPlugin)

    def test_get_tree_sitter_language(self):
        """Test tree-sitter language retrieval."""
        import tree_sitter

        plugin = CSharpPlugin()
        language = plugin.get_tree_sitter_language()
        assert isinstance(language, tree_sitter.Language)

    def test_language_caching(self):
        """Test that language is cached after first load."""
        plugin = CSharpPlugin()
        lang1 = plugin.get_tree_sitter_language()
        lang2 = plugin.get_tree_sitter_language()
        assert lang1 is lang2

    def test_get_queries(self):
        """Test query retrieval."""
        plugin = CSharpPlugin()
        queries = plugin.get_queries()
        assert isinstance(queries, dict)

    def test_get_element_categories(self):
        """Test element categories."""
        plugin = CSharpPlugin()
        categories = plugin.get_element_categories()
        assert "classes" in categories
        assert "methods" in categories
        assert "properties" in categories
        assert "fields" in categories
        assert "imports" in categories

    def test_execute_query_strategy_wrong_language(self):
        """Test query strategy with wrong language."""
        plugin = CSharpPlugin()
        result = plugin.execute_query_strategy("classes", "python")
        assert result is None

    def test_execute_query_strategy_csharp(self):
        """Test query strategy for C#."""
        plugin = CSharpPlugin()
        result = plugin.execute_query_strategy("classes", "csharp")
        # May return None if key doesn't exist, but shouldn't crash
        assert result is None or isinstance(result, str)

    def test_execute_query_strategy_none_key(self):
        """Test query strategy with None key."""
        plugin = CSharpPlugin()
        result = plugin.execute_query_strategy(None, "csharp")
        assert result is None

    def test_execute_query_strategy_csharp_classes(self):
        """Query strategy returns string or None for valid C# keys."""
        plugin = CSharpPlugin()
        for key in ("classes", "methods", "variables", "imports"):
            result = plugin.execute_query_strategy(key, "csharp")
            assert result is None or isinstance(result, str)
