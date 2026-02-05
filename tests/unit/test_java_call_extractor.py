"""
Unit tests for JavaCallExtractor.

Tests the extraction of Java method calls from AST nodes.
"""

import pytest

from tree_sitter_analyzer_v2.core.parser import TreeSitterParser
from tree_sitter_analyzer_v2.graph.extractors import JavaCallExtractor


@pytest.fixture
def java_parser():
    """Create Java parser for test cases."""
    return TreeSitterParser("java")


@pytest.fixture
def java_extractor():
    """Create Java call extractor."""
    return JavaCallExtractor()


def test_get_call_node_types(java_extractor):
    """Test that Java extractor returns correct node types."""
    node_types = java_extractor.get_call_node_types()
    assert "method_invocation" in node_types
    assert "object_creation_expression" in node_types


def test_extract_simple_method_call(java_parser, java_extractor):
    """Test extraction of simple method call: method()"""
    code = """
class Test {
    void main() {
        helper();
    }
}
"""
    parse_result = java_parser.parse(code)
    calls = java_extractor.extract_calls(parse_result.tree)

    assert len(calls) == 1
    assert calls[0]["name"] == "helper"
    assert calls[0]["type"] == "simple"
    assert calls[0]["qualifier"] is None
    assert calls[0]["line"] == 4


def test_extract_method_with_arguments(java_parser, java_extractor):
    """Test extraction of method call with arguments: method(arg1, arg2)"""
    code = """
class Test {
    void main() {
        process(x, y);
    }
}
"""
    parse_result = java_parser.parse(code)
    calls = java_extractor.extract_calls(parse_result.tree)

    assert len(calls) == 1
    assert calls[0]["name"] == "process"
    assert calls[0]["type"] == "simple"


def test_extract_multiple_simple_calls(java_parser, java_extractor):
    """Test extraction of multiple simple method calls."""
    code = """
class Test {
    void main() {
        first();
        second();
        third();
    }
}
"""
    parse_result = java_parser.parse(code)
    calls = java_extractor.extract_calls(parse_result.tree)

    assert len(calls) == 3
    call_names = [call["name"] for call in calls]
    assert "first" in call_names
    assert "second" in call_names
    assert "third" in call_names


def test_extract_no_calls(java_parser, java_extractor):
    """Test extraction when there are no method calls."""
    code = """
class Test {
    void main() {
        int x = 5;
        int y = x + 10;
    }
}
"""
    parse_result = java_parser.parse(code)
    calls = java_extractor.extract_calls(parse_result.tree)

    assert len(calls) == 0


# T2.2: Instance Method Calls


def test_extract_instance_method_call(java_parser, java_extractor):
    """Test extraction of instance method call: obj.method()"""
    code = """
class Test {
    void main() {
        user.getName();
    }
}
"""
    parse_result = java_parser.parse(code)
    calls = java_extractor.extract_calls(parse_result.tree)

    assert len(calls) == 1
    assert calls[0]["name"] == "getName"
    assert calls[0]["type"] == "method"
    assert calls[0]["qualifier"] == "user"
    assert calls[0]["line"] == 4


def test_extract_instance_method_with_arguments(java_parser, java_extractor):
    """Test extraction of instance method call with arguments."""
    code = """
class Test {
    void main() {
        calculator.add(5, 10);
    }
}
"""
    parse_result = java_parser.parse(code)
    calls = java_extractor.extract_calls(parse_result.tree)

    assert len(calls) == 1
    assert calls[0]["name"] == "add"
    assert calls[0]["type"] == "method"
    assert calls[0]["qualifier"] == "calculator"


def test_extract_chained_method_calls(java_parser, java_extractor):
    """Test extraction of chained method calls: obj.method1().method2()"""
    code = """
class Test {
    void main() {
        user.getProfile().getName();
    }
}
"""
    parse_result = java_parser.parse(code)
    calls = java_extractor.extract_calls(parse_result.tree)

    # Should extract both method calls in the chain
    assert len(calls) == 2
    call_names = [call["name"] for call in calls]
    assert "getProfile" in call_names
    assert "getName" in call_names


def test_extract_nested_instance_calls(java_parser, java_extractor):
    """Test extraction when method calls are nested in arguments."""
    code = """
class Test {
    void main() {
        service.process(helper.getData());
    }
}
"""
    parse_result = java_parser.parse(code)
    calls = java_extractor.extract_calls(parse_result.tree)

    # Should extract both process() and getData()
    assert len(calls) == 2
    call_names = [call["name"] for call in calls]
    assert "process" in call_names
    assert "getData" in call_names


# T2.3: Static Method Calls


def test_extract_static_method_call(java_parser, java_extractor):
    """Test extraction of static method call: Class.method()"""
    code = """
class Test {
    void main() {
        Math.max(10, 20);
    }
}
"""
    parse_result = java_parser.parse(code)
    calls = java_extractor.extract_calls(parse_result.tree)

    assert len(calls) == 1
    assert calls[0]["name"] == "max"
    assert calls[0]["type"] == "method"  # Can't distinguish static from instance at AST level
    assert calls[0]["qualifier"] == "Math"


def test_extract_multiple_static_calls(java_parser, java_extractor):
    """Test extraction of multiple static method calls."""
    code = """
class Test {
    void main() {
        String.valueOf(123);
        Integer.parseInt("456");
    }
}
"""
    parse_result = java_parser.parse(code)
    calls = java_extractor.extract_calls(parse_result.tree)

    assert len(calls) == 2
    call_info = {call["name"]: call for call in calls}
    assert "valueOf" in call_info
    assert "parseInt" in call_info
    assert call_info["valueOf"]["qualifier"] == "String"
    assert call_info["parseInt"]["qualifier"] == "Integer"


# T2.4: Constructor Calls


def test_extract_constructor_call(java_parser, java_extractor):
    """Test extraction of constructor call: new ClassName()"""
    code = """
class Test {
    void main() {
        User user = new User();
    }
}
"""
    parse_result = java_parser.parse(code)
    calls = java_extractor.extract_calls(parse_result.tree)

    assert len(calls) == 1
    assert calls[0]["name"] == "User"
    assert calls[0]["type"] == "constructor"
    assert calls[0]["qualifier"] is None


def test_extract_constructor_with_arguments(java_parser, java_extractor):
    """Test extraction of constructor call with arguments."""
    code = """
class Test {
    void main() {
        User user = new User("John", 30);
    }
}
"""
    parse_result = java_parser.parse(code)
    calls = java_extractor.extract_calls(parse_result.tree)

    assert len(calls) == 1
    assert calls[0]["name"] == "User"
    assert calls[0]["type"] == "constructor"


def test_extract_generic_constructor(java_parser, java_extractor):
    """Test extraction of generic constructor: new List<String>()"""
    code = """
class Test {
    void main() {
        List<String> list = new ArrayList<String>();
    }
}
"""
    parse_result = java_parser.parse(code)
    calls = java_extractor.extract_calls(parse_result.tree)

    assert len(calls) == 1
    assert calls[0]["name"] == "ArrayList"
    assert calls[0]["type"] == "constructor"


# T2.5: Special Cases


def test_extract_super_call(java_parser, java_extractor):
    """Test extraction of super method call: super.method()"""
    code = """
class Child extends Parent {
    void doSomething() {
        super.doSomething();
    }
}
"""
    parse_result = java_parser.parse(code)
    calls = java_extractor.extract_calls(parse_result.tree)

    assert len(calls) == 1
    assert calls[0]["name"] == "doSomething"
    assert calls[0]["type"] == "super"
    assert calls[0]["qualifier"] == "super"


def test_extract_this_call(java_parser, java_extractor):
    """Test extraction of this method call: this.method()"""
    code = """
class Test {
    void main() {
        this.helper();
    }

    void helper() {
    }
}
"""
    parse_result = java_parser.parse(code)
    calls = java_extractor.extract_calls(parse_result.tree)

    assert len(calls) == 1
    assert calls[0]["name"] == "helper"
    assert calls[0]["type"] == "this"
    assert calls[0]["qualifier"] == "this"


def test_extract_complex_scenario(java_parser, java_extractor):
    """Test extraction in complex scenario with multiple call types."""
    code = """
class Test {
    void process() {
        User user = new User();
        String name = user.getName();
        int value = Math.max(10, 20);
        super.process();
        this.helper();
        validate();
    }
}
"""
    parse_result = java_parser.parse(code)
    calls = java_extractor.extract_calls(parse_result.tree)

    # Should extract: new User(), getName(), max(), super.process(), this.helper(), validate()
    assert len(calls) == 6

    call_types = {call["name"]: call["type"] for call in calls}
    assert call_types["User"] == "constructor"
    assert call_types["getName"] == "method"
    assert call_types["max"] == "method"
    assert call_types["process"] == "super"
    assert call_types["helper"] == "this"
    assert call_types["validate"] == "simple"
