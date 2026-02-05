"""
Test Java language parser implementation.

Following TDD: Write tests FIRST to define the contract.
This is T1.5: First Three Languages - Java
"""


class TestJavaParserBasics:
    """Test basic Java parser functionality."""

    def test_parser_can_be_imported(self):
        """Test that JavaParser can be imported."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        assert JavaParser is not None

    def test_parser_initialization(self):
        """Test creating a parser instance."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        assert parser is not None

    def test_parse_simple_code(self):
        """Test parsing simple Java code."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        code = "public class Test {}"

        result = parser.parse(code)

        assert result is not None
        assert "ast" in result
        assert "metadata" in result


class TestJavaClassExtraction:
    """Test extracting classes from Java code."""

    def test_extract_simple_class(self):
        """Test extracting a simple class."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        code = """
public class Calculator {
}
"""

        result = parser.parse(code)

        assert "classes" in result
        assert len(result["classes"]) == 1

        cls = result["classes"][0]
        assert cls["name"] == "Calculator"
        assert cls["modifiers"] == ["public"]

    def test_extract_class_with_package(self):
        """Test extracting class with package declaration."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        code = """
package com.example.utils;

public class StringUtils {
}
"""

        result = parser.parse(code)

        assert "package" in result
        assert result["package"] == "com.example.utils"

        assert len(result["classes"]) == 1
        assert result["classes"][0]["name"] == "StringUtils"

    def test_extract_class_with_modifiers(self):
        """Test extracting class with multiple modifiers."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        code = """
public abstract class BaseService {
}
"""

        result = parser.parse(code)

        cls = result["classes"][0]
        assert "public" in cls["modifiers"]
        assert "abstract" in cls["modifiers"]


class TestJavaMethodExtraction:
    """Test extracting methods from Java code."""

    def test_extract_simple_method(self):
        """Test extracting a simple method."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        code = """
public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }
}
"""

        result = parser.parse(code)

        cls = result["classes"][0]
        assert "methods" in cls
        assert len(cls["methods"]) == 1

        method = cls["methods"][0]
        assert method["name"] == "add"
        assert method["return_type"] == "int"
        assert len(method["parameters"]) == 2

    def test_extract_method_with_modifiers(self):
        """Test extracting method with modifiers."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        code = """
public class Service {
    private static void initialize() {
    }
}
"""

        result = parser.parse(code)

        method = result["classes"][0]["methods"][0]
        assert "private" in method["modifiers"]
        assert "static" in method["modifiers"]
        assert method["return_type"] == "void"

    def test_extract_method_parameters(self):
        """Test extracting method parameters with types."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        code = """
public class UserService {
    public User findUser(String username, int id) {
        return null;
    }
}
"""

        result = parser.parse(code)

        method = result["classes"][0]["methods"][0]
        assert method["name"] == "findUser"
        assert len(method["parameters"]) == 2

        params = method["parameters"]
        assert params[0]["name"] == "username"
        assert params[0]["type"] == "String"
        assert params[1]["name"] == "id"
        assert params[1]["type"] == "int"


class TestJavaImportExtraction:
    """Test extracting imports from Java code."""

    def test_extract_simple_import(self):
        """Test extracting simple import."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        code = """
import java.util.List;

public class Example {
}
"""

        result = parser.parse(code)

        assert "imports" in result
        assert len(result["imports"]) == 1
        assert result["imports"][0] == "java.util.List"

    def test_extract_wildcard_import(self):
        """Test extracting wildcard import."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        code = """
import java.util.*;

public class Example {
}
"""

        result = parser.parse(code)

        assert "java.util.*" in result["imports"]

    def test_extract_multiple_imports(self):
        """Test extracting multiple imports."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        code = """
import java.util.List;
import java.util.ArrayList;
import java.io.File;

public class Example {
}
"""

        result = parser.parse(code)

        assert len(result["imports"]) == 3
        assert "java.util.List" in result["imports"]
        assert "java.util.ArrayList" in result["imports"]
        assert "java.io.File" in result["imports"]


class TestJavaInterfaceExtraction:
    """Test extracting interfaces from Java code."""

    def test_extract_simple_interface(self):
        """Test extracting a simple interface."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        code = """
public interface Runnable {
    void run();
}
"""

        result = parser.parse(code)

        assert "interfaces" in result
        assert len(result["interfaces"]) == 1

        iface = result["interfaces"][0]
        assert iface["name"] == "Runnable"
        assert iface["modifiers"] == ["public"]

    def test_extract_interface_with_methods(self):
        """Test extracting interface with method signatures."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        code = """
public interface Calculator {
    int add(int a, int b);
    int subtract(int a, int b);
}
"""

        result = parser.parse(code)

        iface = result["interfaces"][0]
        assert "methods" in iface
        assert len(iface["methods"]) == 2

        method_names = [m["name"] for m in iface["methods"]]
        assert "add" in method_names
        assert "subtract" in method_names


class TestJavaAnnotationExtraction:
    """Test extracting annotations from Java code."""

    def test_extract_method_annotation(self):
        """Test extracting method-level annotation."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        code = """
public class Service {
    @Override
    public String toString() {
        return "";
    }
}
"""

        result = parser.parse(code)

        method = result["classes"][0]["methods"][0]
        assert "annotations" in method
        # Check for annotation dict format (new format)
        assert len(method["annotations"]) > 0
        assert any(ann["name"] == "Override" for ann in method["annotations"])

    def test_extract_class_annotation(self):
        """Test extracting class-level annotation."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        code = """
@Deprecated
public class OldService {
}
"""

        result = parser.parse(code)

        cls = result["classes"][0]
        assert "annotations" in cls
        # Check for annotation dict format (new format)
        assert len(cls["annotations"]) > 0
        assert any(ann["name"] == "Deprecated" for ann in cls["annotations"])


class TestJavaMetadata:
    """Test metadata extraction."""

    def test_metadata_includes_counts(self):
        """Test that metadata includes counts."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        code = """
package com.example;

import java.util.List;

public class App {
    public void run() {}
}

public interface Service {
    void execute();
}
"""

        result = parser.parse(code)

        assert "metadata" in result
        assert "total_classes" in result["metadata"]
        assert "total_interfaces" in result["metadata"]
        assert "total_imports" in result["metadata"]

        assert result["metadata"]["total_classes"] == 1
        assert result["metadata"]["total_interfaces"] == 1
        assert result["metadata"]["total_imports"] == 1

    def test_metadata_includes_line_numbers(self):
        """Test that extracted items include line numbers."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        code = """
public class Example {
    public void test() {
    }
}
"""

        result = parser.parse(code)

        # Classes should have line numbers
        cls = result["classes"][0]
        assert "line_start" in cls
        assert "line_end" in cls

        # Methods should have line numbers
        method = cls["methods"][0]
        assert "line_start" in method
        assert "line_end" in method


class TestJavaEdgeCases:
    """Test edge cases and error handling."""

    def test_parse_empty_file(self):
        """Test parsing empty Java file."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        result = parser.parse("")

        assert result is not None
        assert result["classes"] == []
        assert result["interfaces"] == []
        assert result["imports"] == []

    def test_parse_syntax_error(self):
        """Test parsing code with syntax errors."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        code = "public class Broken {"

        result = parser.parse(code)

        # Should still return result, but mark errors
        assert result is not None
        assert "errors" in result
        assert result["errors"] is True

    def test_parse_nested_classes(self):
        """Test parsing nested inner classes."""
        from tree_sitter_analyzer_v2.languages.java_parser import JavaParser

        parser = JavaParser()
        code = """
public class Outer {
    public class Inner {
        public void innerMethod() {}
    }
}
"""

        result = parser.parse(code)

        # Should extract outer class
        assert len(result["classes"]) >= 1
        assert result["classes"][0]["name"] == "Outer"
