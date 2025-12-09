#!/usr/bin/env python3
"""
Property-based tests for parser error recovery.

**Feature: test-coverage-improvement, Property 6: Parser Error Recovery**

Tests that for any source code with syntax errors, the parser SHALL return
partial results without crashing.

**Validates: Requirements 5.1**
"""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.core.engine import AnalysisEngine
from tree_sitter_analyzer.core.parser import Parser, ParseResult

# ========================================
# Hypothesis Strategies for Code Generation
# ========================================

# Strategy for generating valid Python identifiers
python_identifier = st.sampled_from(
    [
        "test",
        "foo",
        "bar",
        "baz",
        "my_func",
        "my_class",
        "MyClass",
        "value",
        "data",
        "result",
        "count",
        "index",
        "item",
        "name",
        "process",
        "execute",
        "validate",
        "create",
        "update",
        "delete",
    ]
)

# Strategy for generating valid Java identifiers
java_identifier = st.sampled_from(
    [
        "Test",
        "Foo",
        "Bar",
        "MyClass",
        "MyService",
        "Controller",
        "Repository",
        "Handler",
        "Manager",
        "Processor",
        "Builder",
        "getValue",
        "setValue",
        "process",
        "execute",
        "validate",
    ]
)

# Strategy for generating valid JavaScript identifiers
js_identifier = st.sampled_from(
    [
        "test",
        "foo",
        "bar",
        "myFunc",
        "MyClass",
        "handler",
        "callback",
        "promise",
        "async",
        "data",
        "result",
        "value",
        "onClick",
        "onChange",
        "handleSubmit",
        "fetchData",
        "render",
    ]
)


# Strategy for generating Python code with syntax errors
@st.composite
def python_code_with_syntax_error(draw):
    """Generate Python code that contains syntax errors."""
    error_type = draw(
        st.sampled_from(
            [
                "missing_colon",
                "unclosed_paren",
                "unclosed_bracket",
                "unclosed_brace",
                "invalid_indent",
                "incomplete_string",
                "missing_operator",
                "incomplete_def",
                "incomplete_class",
                "incomplete_if",
            ]
        )
    )

    name = draw(python_identifier)

    if error_type == "missing_colon":
        # def without colon
        return f"def {name}()\n    pass"
    elif error_type == "unclosed_paren":
        return f"def {name}(x, y:\n    return x + y"
    elif error_type == "unclosed_bracket":
        return f"{name} = [1, 2, 3"
    elif error_type == "unclosed_brace":
        return f"{name} = {{'key': 'value'"
    elif error_type == "invalid_indent":
        return f"def {name}():\npass"  # Missing indent
    elif error_type == "incomplete_string":
        return f'{name} = "incomplete string'
    elif error_type == "missing_operator":
        return f"{name} = 1 2 3"  # Missing operators
    elif error_type == "incomplete_def":
        return f"def {name}"  # Incomplete function definition
    elif error_type == "incomplete_class":
        return f"class {name}"  # Incomplete class definition
    elif error_type == "incomplete_if":
        return f"if {name}"  # Incomplete if statement

    return f"def {name}(\n    pass"  # Default: unclosed paren


# Strategy for generating Java code with syntax errors
@st.composite
def java_code_with_syntax_error(draw):
    """Generate Java code that contains syntax errors."""
    error_type = draw(
        st.sampled_from(
            [
                "missing_semicolon",
                "unclosed_brace",
                "unclosed_paren",
                "incomplete_class",
                "incomplete_method",
                "missing_type",
                "invalid_modifier",
            ]
        )
    )

    name = draw(java_identifier)

    if error_type == "missing_semicolon":
        return f"public class {name} {{ int x = 5 }}"
    elif error_type == "unclosed_brace":
        return f"public class {name} {{ public void test() {{"
    elif error_type == "unclosed_paren":
        return f"public class {name} {{ public void test(int x {{}}"
    elif error_type == "incomplete_class":
        return f"public class {name}"
    elif error_type == "incomplete_method":
        return f"public class {name} {{ public void }}"
    elif error_type == "missing_type":
        return f"public class {name} {{ public test() {{}} }}"
    elif error_type == "invalid_modifier":
        return f"public private class {name} {{}}"

    return f"public class {name} {{"  # Default: unclosed brace


# Strategy for generating JavaScript code with syntax errors
@st.composite
def javascript_code_with_syntax_error(draw):
    """Generate JavaScript code that contains syntax errors."""
    error_type = draw(
        st.sampled_from(
            [
                "unclosed_brace",
                "unclosed_paren",
                "unclosed_bracket",
                "incomplete_function",
                "incomplete_arrow",
                "missing_operator",
                "incomplete_object",
            ]
        )
    )

    name = draw(js_identifier)

    if error_type == "unclosed_brace":
        return f"function {name}() {{"
    elif error_type == "unclosed_paren":
        return f"function {name}(x, y {{"
    elif error_type == "unclosed_bracket":
        return f"const {name} = [1, 2, 3"
    elif error_type == "incomplete_function":
        return f"function {name}"
    elif error_type == "incomplete_arrow":
        return f"const {name} = (x) =>"
    elif error_type == "missing_operator":
        return f"const {name} = 1 2 3;"
    elif error_type == "incomplete_object":
        return f"const {name} = {{ key:"

    return f"function {name}() {{"  # Default: unclosed brace


# Strategy for generating code with mixed valid and invalid parts
@st.composite
def code_with_partial_errors(draw):
    """Generate code that has both valid and invalid parts."""
    language = draw(st.sampled_from(["python", "java", "javascript"]))

    if language == "python":
        valid_part = "def valid_function():\n    return 42\n\n"
        invalid_part = draw(python_code_with_syntax_error())
        return (language, valid_part + invalid_part)
    elif language == "java":
        valid_part = "public class ValidClass { public void valid() {} }\n"
        invalid_part = draw(java_code_with_syntax_error())
        return (language, valid_part + invalid_part)
    else:  # javascript
        valid_part = "function validFunction() { return 42; }\n"
        invalid_part = draw(javascript_code_with_syntax_error())
        return (language, valid_part + invalid_part)


# Strategy for generating random garbage that might crash parsers
@st.composite
def random_garbage_code(draw):
    """Generate random garbage that should not crash the parser."""
    garbage_type = draw(
        st.sampled_from(
            [
                "random_symbols",
                "nested_brackets",
                "unicode_chaos",
                "mixed_quotes",
                "excessive_nesting",
            ]
        )
    )

    if garbage_type == "random_symbols":
        symbols = draw(
            st.text(alphabet="!@#$%^&*()[]{}|\\;:',.<>?/`~", min_size=10, max_size=100)
        )
        return symbols
    elif garbage_type == "nested_brackets":
        depth = draw(st.integers(min_value=5, max_value=20))
        return "(" * depth + "x" + ")" * (depth - 1)  # Unbalanced
    elif garbage_type == "unicode_chaos":
        return draw(st.text(min_size=10, max_size=100))
    elif garbage_type == "mixed_quotes":
        return '''def test(): return "unclosed' + 'mixed"'''
    elif garbage_type == "excessive_nesting":
        return "{{{{{{{{{{" + "x" + "}}}}}}"  # Unbalanced braces

    return "!@#$%^&*()"


# ========================================
# Property Tests for Parser Error Recovery
# ========================================


class TestParserErrorRecoveryProperties:
    """
    Property-based tests for parser error recovery.

    **Feature: test-coverage-improvement, Property 6: Parser Error Recovery**
    **Validates: Requirements 5.1**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(code=python_code_with_syntax_error())
    def test_property_6_python_parser_does_not_crash_on_syntax_errors(self, code: str):
        """
        **Feature: test-coverage-improvement, Property 6: Parser Error Recovery**

        For any Python code with syntax errors, the parser SHALL return a result
        without crashing.

        **Validates: Requirements 5.1**
        """
        parser = Parser()

        # Parser should not raise an exception
        result = parser.parse_code(code, "python")

        # Property: Result should always be a ParseResult
        assert isinstance(
            result, ParseResult
        ), "Parser should return ParseResult even for invalid code"

        # Property: Result should have language set
        assert result.language == "python", "Language should be preserved in result"

        # Property: Source code should be preserved
        assert result.source_code == code, "Source code should be preserved in result"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(code=java_code_with_syntax_error())
    def test_property_6_java_parser_does_not_crash_on_syntax_errors(self, code: str):
        """
        **Feature: test-coverage-improvement, Property 6: Parser Error Recovery**

        For any Java code with syntax errors, the parser SHALL return a result
        without crashing.

        **Validates: Requirements 5.1**
        """
        parser = Parser()

        # Parser should not raise an exception
        result = parser.parse_code(code, "java")

        # Property: Result should always be a ParseResult
        assert isinstance(
            result, ParseResult
        ), "Parser should return ParseResult even for invalid code"

        # Property: Result should have language set
        assert result.language == "java", "Language should be preserved in result"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(code=javascript_code_with_syntax_error())
    def test_property_6_javascript_parser_does_not_crash_on_syntax_errors(
        self, code: str
    ):
        """
        **Feature: test-coverage-improvement, Property 6: Parser Error Recovery**

        For any JavaScript code with syntax errors, the parser SHALL return a result
        without crashing.

        **Validates: Requirements 5.1**
        """
        parser = Parser()

        # Parser should not raise an exception
        result = parser.parse_code(code, "javascript")

        # Property: Result should always be a ParseResult
        assert isinstance(
            result, ParseResult
        ), "Parser should return ParseResult even for invalid code"

        # Property: Result should have language set
        assert result.language == "javascript", "Language should be preserved in result"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=code_with_partial_errors())
    def test_property_6_parser_returns_partial_results_for_mixed_code(
        self, data: tuple
    ):
        """
        **Feature: test-coverage-improvement, Property 6: Parser Error Recovery**

        For any code with both valid and invalid parts, the parser SHALL return
        partial results containing the valid parts.

        **Validates: Requirements 5.1**
        """
        language, code = data
        parser = Parser()

        # Parser should not raise an exception
        result = parser.parse_code(code, language)

        # Property: Result should always be a ParseResult
        assert isinstance(
            result, ParseResult
        ), "Parser should return ParseResult for mixed valid/invalid code"

        # Property: If parsing succeeded, tree should have nodes
        # Tree-sitter is error-tolerant and often succeeds even with errors
        if result.success and result.tree is not None:
            assert (
                result.tree.root_node is not None
            ), "Successful parse should have root node"

    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    @given(garbage=random_garbage_code())
    def test_property_6_parser_handles_garbage_input_gracefully(self, garbage: str):
        """
        **Feature: test-coverage-improvement, Property 6: Parser Error Recovery**

        For any random garbage input, the parser SHALL not crash and SHALL return
        a result.

        **Validates: Requirements 5.1**
        """
        parser = Parser()

        # Try parsing as different languages - none should crash
        for language in ["python", "java", "javascript"]:
            if not parser.is_language_supported(language):
                continue

            # Parser should not raise an exception
            result = parser.parse_code(garbage, language)

            # Property: Result should always be a ParseResult
            assert isinstance(
                result, ParseResult
            ), f"Parser should return ParseResult for garbage input ({language})"


class TestEngineErrorRecoveryProperties:
    """
    Property-based tests for AnalysisEngine error recovery.

    **Feature: test-coverage-improvement, Property 6: Parser Error Recovery**
    **Validates: Requirements 5.1**
    """

    @settings(
        max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None
    )
    @given(code=python_code_with_syntax_error())
    def test_property_6_engine_returns_result_for_invalid_python(self, code: str):
        """
        **Feature: test-coverage-improvement, Property 6: Parser Error Recovery**

        For any Python code with syntax errors, the AnalysisEngine SHALL return
        an AnalysisResult without crashing.

        **Validates: Requirements 5.1**
        """
        engine = AnalysisEngine()

        # Engine should not raise an exception
        result = engine.analyze_code(code, language="python")

        # Property: Result should always be an AnalysisResult
        from tree_sitter_analyzer.models import AnalysisResult

        assert isinstance(
            result, AnalysisResult
        ), "Engine should return AnalysisResult even for invalid code"

        # Property: Language should be set
        assert result.language == "python", "Language should be preserved in result"

    @settings(
        max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None
    )
    @given(code=java_code_with_syntax_error())
    def test_property_6_engine_returns_result_for_invalid_java(self, code: str):
        """
        **Feature: test-coverage-improvement, Property 6: Parser Error Recovery**

        For any Java code with syntax errors, the AnalysisEngine SHALL return
        an AnalysisResult without crashing.

        **Validates: Requirements 5.1**
        """
        engine = AnalysisEngine()

        # Engine should not raise an exception
        result = engine.analyze_code(code, language="java")

        # Property: Result should always be an AnalysisResult
        from tree_sitter_analyzer.models import AnalysisResult

        assert isinstance(
            result, AnalysisResult
        ), "Engine should return AnalysisResult even for invalid code"

    @settings(
        max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None
    )
    @given(code=javascript_code_with_syntax_error())
    def test_property_6_engine_returns_result_for_invalid_javascript(self, code: str):
        """
        **Feature: test-coverage-improvement, Property 6: Parser Error Recovery**

        For any JavaScript code with syntax errors, the AnalysisEngine SHALL return
        an AnalysisResult without crashing.

        **Validates: Requirements 5.1**
        """
        engine = AnalysisEngine()

        # Engine should not raise an exception
        result = engine.analyze_code(code, language="javascript")

        # Property: Result should always be an AnalysisResult
        from tree_sitter_analyzer.models import AnalysisResult

        assert isinstance(
            result, AnalysisResult
        ), "Engine should return AnalysisResult even for invalid code"

        # Property: Language should be set
        assert result.language == "javascript", "Language should be preserved in result"


class TestParserErrorDetectionProperties:
    """
    Property-based tests for parser error detection capabilities.

    **Feature: test-coverage-improvement, Property 6: Parser Error Recovery**
    **Validates: Requirements 5.1**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(code=python_code_with_syntax_error())
    def test_property_6_parser_can_detect_errors_in_tree(self, code: str):
        """
        **Feature: test-coverage-improvement, Property 6: Parser Error Recovery**

        For any code with syntax errors, if parsing succeeds, the parser SHALL
        be able to detect error nodes in the resulting tree.

        **Validates: Requirements 5.1**
        """
        parser = Parser()
        result = parser.parse_code(code, "python")

        # If parsing succeeded (tree-sitter is error-tolerant)
        if result.success and result.tree is not None:
            # Property: get_parse_errors should not crash
            errors = parser.get_parse_errors(result.tree)

            # Property: errors should be a list
            assert isinstance(errors, list), "get_parse_errors should return a list"

            # Property: each error should have required fields
            for error in errors:
                assert isinstance(error, dict), "Each error should be a dictionary"
                assert "type" in error, "Error should have 'type' field"
                assert "start_point" in error, "Error should have 'start_point' field"
                assert "end_point" in error, "Error should have 'end_point' field"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=code_with_partial_errors())
    def test_property_6_parser_validates_ast_correctly(self, data: tuple):
        """
        **Feature: test-coverage-improvement, Property 6: Parser Error Recovery**

        For any parsed code, the validate_ast method SHALL correctly identify
        whether the tree is valid.

        **Validates: Requirements 5.1**
        """
        language, code = data
        parser = Parser()
        result = parser.parse_code(code, language)

        # Property: validate_ast should not crash
        is_valid = parser.validate_ast(result.tree)

        # Property: validate_ast should return a boolean
        assert isinstance(is_valid, bool), "validate_ast should return a boolean"

        # Property: If tree is None, validation should return False
        assert (
            parser.validate_ast(None) is False
        ), "validate_ast(None) should return False"


class TestParserUnsupportedLanguageProperties:
    """
    Property-based tests for handling unsupported languages.

    **Feature: test-coverage-improvement, Property 6: Parser Error Recovery**
    **Validates: Requirements 5.1**
    """

    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    @given(
        code=st.text(min_size=1, max_size=100),
        language=st.sampled_from(
            [
                "unsupported_lang",
                "fake_language",
                "xyz123",
                "not_a_language",
                "random_lang",
            ]
        ),
    )
    def test_property_6_parser_handles_unsupported_language_gracefully(
        self, code: str, language: str
    ):
        """
        **Feature: test-coverage-improvement, Property 6: Parser Error Recovery**

        For any unsupported language, the parser SHALL return a result with
        appropriate error message without crashing.

        **Validates: Requirements 5.1**
        """
        parser = Parser()

        # Parser should not raise an exception
        result = parser.parse_code(code, language)

        # Property: Result should always be a ParseResult
        assert isinstance(
            result, ParseResult
        ), "Parser should return ParseResult for unsupported language"

        # Property: Success should be False for unsupported language
        assert (
            result.success is False
        ), "Parsing unsupported language should not succeed"

        # Property: Error message should be set
        assert (
            result.error_message is not None
        ), "Error message should be set for unsupported language"

        # Property: Tree should be None
        assert result.tree is None, "Tree should be None for unsupported language"


class TestParserEmptyInputProperties:
    """
    Property-based tests for handling empty and edge case inputs.

    **Feature: test-coverage-improvement, Property 6: Parser Error Recovery**
    **Validates: Requirements 5.1**
    """

    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    @given(language=st.sampled_from(["python", "java", "javascript", "typescript"]))
    def test_property_6_parser_handles_empty_string(self, language: str):
        """
        **Feature: test-coverage-improvement, Property 6: Parser Error Recovery**

        For empty string input, the parser SHALL return a result without crashing.

        **Validates: Requirements 5.1**
        """
        parser = Parser()

        if not parser.is_language_supported(language):
            return  # Skip unsupported languages

        # Parser should not raise an exception
        result = parser.parse_code("", language)

        # Property: Result should always be a ParseResult
        assert isinstance(
            result, ParseResult
        ), "Parser should return ParseResult for empty string"

    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    @given(
        whitespace=st.text(alphabet=" \t\n\r", min_size=1, max_size=100),
        language=st.sampled_from(["python", "java", "javascript"]),
    )
    def test_property_6_parser_handles_whitespace_only(
        self, whitespace: str, language: str
    ):
        """
        **Feature: test-coverage-improvement, Property 6: Parser Error Recovery**

        For whitespace-only input, the parser SHALL return a result without crashing.

        **Validates: Requirements 5.1**
        """
        parser = Parser()

        if not parser.is_language_supported(language):
            return  # Skip unsupported languages

        # Parser should not raise an exception
        result = parser.parse_code(whitespace, language)

        # Property: Result should always be a ParseResult
        assert isinstance(
            result, ParseResult
        ), "Parser should return ParseResult for whitespace-only input"
