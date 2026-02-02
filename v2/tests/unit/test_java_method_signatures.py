"""
Unit tests for Java method signature enhancement.

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

Phase 2: Method Signature Enhancement (7 tests)
- Generic types (List<T>, Map<K,V>)
- Array types (int[], String[][])
- Throws clauses
- Complex parameter types
"""


class TestGenericTypes:
    """Tests for generic type extraction."""

    def test_simple_generic_list(self):
        """Test extracting List<String> return type."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class UserService {
    public List<String> getNames() {
        return null;
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "UserService.java")

        assert result["errors"] is False
        assert len(result["classes"]) == 1

        method = result["classes"][0]["methods"][0]
        assert method["name"] == "getNames"
        assert method["return_type"] == "List<String>"

    def test_generic_map_return_type(self):
        """Test extracting Map<String, Integer> return type."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class CacheService {
    public Map<String, Integer> getCache() {
        return null;
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "CacheService.java")

        method = result["classes"][0]["methods"][0]
        assert method["name"] == "getCache"
        assert method["return_type"] == "Map<String, Integer>"

    def test_nested_generics(self):
        """Test extracting List<Map<String, Object>> return type."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class ComplexService {
    public List<Map<String, Object>> getData() {
        return null;
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "ComplexService.java")

        method = result["classes"][0]["methods"][0]
        assert method["name"] == "getData"
        assert method["return_type"] == "List<Map<String, Object>>"

    def test_generic_parameter_type(self):
        """Test extracting generic parameter types."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class DataService {
    public void process(List<String> items, Map<Integer, User> userMap) {
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "DataService.java")

        method = result["classes"][0]["methods"][0]
        assert method["name"] == "process"
        assert len(method["parameters"]) == 2

        # Check first parameter
        param1 = method["parameters"][0]
        assert param1["name"] == "items"
        assert param1["type"] == "List<String>"

        # Check second parameter
        param2 = method["parameters"][1]
        assert param2["name"] == "userMap"
        assert param2["type"] == "Map<Integer, User>"


class TestArrayTypes:
    """Tests for array type extraction."""

    def test_single_dimension_array(self):
        """Test extracting int[] return type."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class ArrayService {
    public int[] getNumbers() {
        return null;
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "ArrayService.java")

        method = result["classes"][0]["methods"][0]
        assert method["name"] == "getNumbers"
        assert method["return_type"] == "int[]"

    def test_multi_dimension_array(self):
        """Test extracting String[][] return type."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class MatrixService {
    public String[][] getMatrix() {
        return null;
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "MatrixService.java")

        method = result["classes"][0]["methods"][0]
        assert method["name"] == "getMatrix"
        assert method["return_type"] == "String[][]"

    def test_generic_array_combination(self):
        """Test extracting List<String>[] return type."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class HybridService {
    public List<String>[] getListArray() {
        return null;
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "HybridService.java")

        method = result["classes"][0]["methods"][0]
        assert method["name"] == "getListArray"
        assert method["return_type"] == "List<String>[]"


class TestThrowsClause:
    """Tests for throws clause extraction."""

    def test_single_exception(self):
        """Test extracting single throws clause."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class FileService {
    public void readFile() throws IOException {
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "FileService.java")

        method = result["classes"][0]["methods"][0]
        assert method["name"] == "readFile"
        assert "throws" in method
        assert method["throws"] == ["IOException"]

    def test_multiple_exceptions(self):
        """Test extracting multiple throws clauses."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class DatabaseService {
    public void connect() throws SQLException, IOException, TimeoutException {
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "DatabaseService.java")

        method = result["classes"][0]["methods"][0]
        assert method["name"] == "connect"
        assert "throws" in method
        assert len(method["throws"]) == 3
        assert "SQLException" in method["throws"]
        assert "IOException" in method["throws"]
        assert "TimeoutException" in method["throws"]

    def test_no_throws_clause(self):
        """Test method without throws clause."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class SimpleService {
    public void doSomething() {
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "SimpleService.java")

        method = result["classes"][0]["methods"][0]
        assert method["name"] == "doSomething"
        # throws should either not exist or be empty list
        throws = method.get("throws", [])
        assert throws == []


class TestComplexMethodSignatures:
    """Tests for complex method signatures combining all features."""

    def test_complex_signature_all_features(self):
        """Test method with generics, arrays, and throws combined."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class ComplexService {
    public Map<String, List<Object>>[] processData(
        List<String> items,
        int[] numbers
    ) throws IOException, SQLException {
        return null;
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "ComplexService.java")

        method = result["classes"][0]["methods"][0]
        assert method["name"] == "processData"

        # Check return type (generic array)
        assert method["return_type"] == "Map<String, List<Object>>[]"

        # Check parameters
        assert len(method["parameters"]) == 2
        assert method["parameters"][0]["type"] == "List<String>"
        assert method["parameters"][1]["type"] == "int[]"

        # Check throws
        assert len(method["throws"]) == 2
        assert "IOException" in method["throws"]
        assert "SQLException" in method["throws"]
