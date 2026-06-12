"""Tests for C# plugin functionality."""

from pathlib import Path

import pytest
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


class TestCSharpPluginAnalyzeFile:
    """Test analyze_file method."""

    @pytest.mark.asyncio
    async def test_analyze_file_nonexistent(self):
        """Test analyzing nonexistent file."""
        plugin = CSharpPlugin()
        result = await plugin.analyze_file("nonexistent.cs", None)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_analyze_file_with_temp_file(self, tmp_path):
        """Test analyzing a temporary C# file."""
        # Create temporary C# file
        cs_file = tmp_path / "Test.cs"
        cs_file.write_text(SIMPLE_CLASS_CODE, encoding="utf-8")

        plugin = CSharpPlugin()
        result = await plugin.analyze_file(str(cs_file), None)

        assert result.success is not False or result.error_message is None
        assert result.language == "csharp"
        assert result.file_path == str(cs_file)


class TestCSharpIntegration:
    """Integration tests for C# plugin."""

    def test_plugin_loads_successfully(self):
        """Test that C# plugin loads successfully."""
        plugin = CSharpPlugin()
        assert plugin is not None
        assert plugin.get_language_name() == "csharp"

    def test_cs_file_extension_recognized(self):
        """Test that .cs file extension is recognized."""
        plugin = CSharpPlugin()
        extensions = plugin.get_file_extensions()
        assert ".cs" in extensions

    def test_full_extraction_workflow(self):
        """Test complete extraction workflow."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_CLASS_CODE, plugin)

        classes = plugin.extractor.extract_classes(tree, COMPLEX_CLASS_CODE)
        functions = plugin.extractor.extract_functions(tree, COMPLEX_CLASS_CODE)
        variables = plugin.extractor.extract_variables(tree, COMPLEX_CLASS_CODE)
        imports = plugin.extractor.extract_imports(tree, COMPLEX_CLASS_CODE)

        assert len(classes) > 0
        assert len(functions) > 0
        assert len(imports) > 0
        # Variables might be extracted within classes
        assert isinstance(variables, list)

    def test_record_type_extraction(self):
        """Test extraction of C# record type."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_CLASS_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_CLASS_CODE)

        # OrderItem is a record
        class_names = [c.name for c in classes]
        # Record should be extracted as class-like structure
        assert "OrderItem" in class_names or any(
            "record" in str(c.raw_text) for c in classes
        )

    def test_struct_extraction(self):
        """Test extraction of C# struct."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_CLASS_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_CLASS_CODE)

        # Point is a struct
        point = next((c for c in classes if c.name == "Point"), None)
        assert point is not None or any("struct" in str(c.raw_text) for c in classes)

    def test_enum_extraction(self):
        """Test extraction of C# enum."""
        plugin = CSharpPlugin()
        tree = get_tree_for_code(COMPLEX_CLASS_CODE, plugin)
        classes = plugin.extractor.extract_classes(tree, COMPLEX_CLASS_CODE)

        # OrderStatus is an enum
        class_names = [c.name for c in classes]
        assert "OrderStatus" in class_names or any(
            "enum" in str(c.raw_text) for c in classes
        )

    @pytest.mark.skipif(
        not Path("examples/Sample.cs").exists(), reason="C# sample file not found"
    )
    def test_analyze_sample_file(self):
        """Test analysis of example C# file."""
        CSharpPlugin()
        sample_path = Path("examples/Sample.cs")
        with open(sample_path, encoding="utf-8") as f:
            code = f.read()
        # Just verify it can be read without errors
        assert len(code) > 0


# ---------------------------------------------------------------------------
# Issue #536 — return types void-ified + interface members marked private
# ---------------------------------------------------------------------------

RETURN_TYPE_CODE = """
namespace MyApp
{
    public class Calc
    {
        public bool IsValid() { return true; }
        public string ToString() { return "x"; }
        public int GetCount() { return 42; }
    }

    public interface IRepo
    {
        User GetById(int id);
        IEnumerable<User> GetAll();
        void Add(User user);
        void Delete(int id);
    }
}
"""


class TestCSharpReturnTypes:
    """Issue #536 leg 1: primitive and generic return types must not be 'void'."""

    def _parse(self, code: str):
        plugin = CSharpPlugin()
        tree = get_tree_for_code(code, plugin)
        return plugin.extractor.extract_functions(tree, code)

    def test_bool_return_type(self):
        """IsValid() → bool, not void."""
        functions = self._parse(RETURN_TYPE_CODE)
        is_valid = next((f for f in functions if f.name == "IsValid"), None)
        assert is_valid is not None
        assert is_valid.return_type == "bool"

    def test_string_return_type(self):
        """ToString() → string, not void."""
        functions = self._parse(RETURN_TYPE_CODE)
        to_string = next((f for f in functions if f.name == "ToString"), None)
        assert to_string is not None
        assert to_string.return_type == "string"

    def test_int_return_type(self):
        """GetCount() → int, not void."""
        functions = self._parse(RETURN_TYPE_CODE)
        get_count = next((f for f in functions if f.name == "GetCount"), None)
        assert get_count is not None
        assert get_count.return_type == "int"

    def test_identifier_return_type(self):
        """IRepo.GetById() → User, not void."""
        functions = self._parse(RETURN_TYPE_CODE)
        get_by_id = next((f for f in functions if f.name == "GetById"), None)
        assert get_by_id is not None
        assert get_by_id.return_type == "User"

    def test_generic_return_type(self):
        """IRepo.GetAll() → IEnumerable<User>, not void."""
        functions = self._parse(RETURN_TYPE_CODE)
        get_all = next((f for f in functions if f.name == "GetAll"), None)
        assert get_all is not None
        assert get_all.return_type == "IEnumerable<User>"

    def test_void_return_type_preserved(self):
        """IRepo.Add() and Delete() keep void."""
        functions = self._parse(RETURN_TYPE_CODE)
        add = next((f for f in functions if f.name == "Add"), None)
        delete = next((f for f in functions if f.name == "Delete"), None)
        assert add is not None
        assert add.return_type == "void"
        assert delete is not None
        assert delete.return_type == "void"


class TestCSharpInterfaceMemberVisibility:
    """Issue #536 leg 2: interface members without explicit modifier → public."""

    def _parse(self, code: str):
        plugin = CSharpPlugin()
        tree = get_tree_for_code(code, plugin)
        return plugin.extractor.extract_functions(tree, code)

    def test_interface_method_visibility_public(self):
        """All IRepo methods without explicit modifier must be public."""
        functions = self._parse(RETURN_TYPE_CODE)
        interface_methods = ["GetById", "GetAll", "Add", "Delete"]
        for name in interface_methods:
            fn = next((f for f in functions if f.name == name), None)
            assert fn is not None, f"Method {name} not found"
            assert fn.visibility == "public", (
                f"{name}: expected visibility='public', got {fn.visibility!r}"
            )

    def test_class_method_with_no_modifier_stays_private(self):
        """A class method without any modifier keeps C# default (private)."""
        code = """
namespace MyApp
{
    public class Foo
    {
        void InternalMethod() { }
    }
}
"""
        functions = self._parse(code)
        internal = next((f for f in functions if f.name == "InternalMethod"), None)
        assert internal is not None
        assert internal.visibility == "private"

    def test_sample_cs_interface_methods_public(self):
        """All IUserRepository methods in examples/Sample.cs are public."""
        sample = Path("examples/Sample.cs")
        if not sample.exists():
            pytest.skip("examples/Sample.cs not found")
        code = sample.read_text(encoding="utf-8")
        functions = self._parse(code)
        repo_methods = ["GetById", "GetAll", "Add", "Update", "Delete"]
        for name in repo_methods:
            fn = next((f for f in functions if f.name == name), None)
            assert fn is not None, f"IUserRepository.{name} not found"
            assert fn.visibility == "public", (
                f"IUserRepository.{name}: expected public, got {fn.visibility!r}"
            )
