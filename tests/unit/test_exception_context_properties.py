#!/usr/bin/env python3
"""
Property-based tests for exception context preservation.

**Feature: test-coverage-improvement, Property 5: Exception Context Preservation**
**Validates: Requirements 4.2, 4.3**

Tests that exception chains preserve all original cause information.
"""

from typing import Any

import pytest
from hypothesis import given, settings, strategies as st

from tree_sitter_analyzer.exceptions import (
    AnalysisError,
    ConfigurationError,
    FileHandlingError,
    LanguageNotSupportedError,
    MCPError,
    MCPResourceError,
    MCPTimeoutError,
    MCPToolError,
    MCPValidationError,
    ParseError,
    PluginError,
    QueryError,
    SecurityError,
    TreeSitterAnalyzerError,
    ValidationError,
    create_error_response,
    create_mcp_error_response,
    handle_exceptions,
)


# Strategies for generating test data
safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        blacklist_characters="\x00\n\r",
    ),
    min_size=1,
    max_size=100,
)

safe_key = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), blacklist_characters="_"),
    min_size=1,
    max_size=20,
).filter(lambda x: x.isidentifier() or x.replace("_", "a").isidentifier())

# Strategy for generating context dictionaries
context_value = st.one_of(
    st.integers(min_value=-1000, max_value=1000),
    st.text(min_size=0, max_size=50),
    st.booleans(),
    st.none(),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1000, max_value=1000),
)

context_dict = st.dictionaries(
    keys=st.text(
        alphabet=st.characters(whitelist_categories=("L",)),
        min_size=1,
        max_size=10,
    ).filter(lambda x: x.isidentifier()),
    values=context_value,
    min_size=0,
    max_size=5,
)


class TestExceptionContextPreservationProperty:
    """
    Property-based tests for exception context preservation.

    **Feature: test-coverage-improvement, Property 5: Exception Context Preservation**
    **Validates: Requirements 4.2, 4.3**
    """

    @given(
        message=safe_text,
        error_code=st.one_of(st.none(), safe_text),
        context=context_dict,
    )
    @settings(max_examples=100)
    def test_base_exception_preserves_context(
        self, message: str, error_code: str | None, context: dict[str, Any]
    ) -> None:
        """
        Property: For any TreeSitterAnalyzerError, the context dictionary
        SHALL be preserved exactly as provided.

        **Feature: test-coverage-improvement, Property 5: Exception Context Preservation**
        **Validates: Requirements 4.2, 4.3**
        """
        exc = TreeSitterAnalyzerError(message, error_code=error_code, context=context)

        # Context should be preserved
        assert exc.context == context
        assert exc.message == message

        # Error code should be preserved or default to class name
        if error_code:
            assert exc.error_code == error_code
        else:
            assert exc.error_code == "TreeSitterAnalyzerError"

    @given(
        message=safe_text,
        file_path=st.one_of(st.none(), safe_text),
        language=st.one_of(st.none(), st.sampled_from(["python", "java", "javascript"])),
    )
    @settings(max_examples=100)
    def test_analysis_error_preserves_file_and_language_context(
        self, message: str, file_path: str | None, language: str | None
    ) -> None:
        """
        Property: For any AnalysisError, file_path and language SHALL be
        preserved in the context dictionary.

        **Feature: test-coverage-improvement, Property 5: Exception Context Preservation**
        **Validates: Requirements 4.2, 4.3**
        """
        exc = AnalysisError(message, file_path=file_path, language=language)

        # File path should be in context if provided
        if file_path:
            assert "file_path" in exc.context
            assert exc.context["file_path"] == file_path

        # Language should be in context if provided
        if language:
            assert "language" in exc.context
            assert exc.context["language"] == language

    @given(
        original_message=safe_text,
        wrapper_message=safe_text,
    )
    @settings(max_examples=100)
    def test_exception_chain_preserves_cause(
        self, original_message: str, wrapper_message: str
    ) -> None:
        """
        Property: For any chained exception, the __cause__ attribute SHALL
        preserve the original exception with its message intact.

        **Feature: test-coverage-improvement, Property 5: Exception Context Preservation**
        **Validates: Requirements 4.2, 4.3**
        """
        original = ValueError(original_message)

        try:
            try:
                raise original
            except ValueError as e:
                raise AnalysisError(wrapper_message) from e
        except AnalysisError as wrapped:
            # The cause should be preserved
            assert wrapped.__cause__ is not None
            assert wrapped.__cause__ is original
            assert str(wrapped.__cause__) == original_message
            # The wrapper message should also be preserved
            assert wrapped.message == wrapper_message

    @given(
        message=safe_text,
        context=context_dict,
    )
    @settings(max_examples=100)
    def test_to_dict_preserves_all_information(
        self, message: str, context: dict[str, Any]
    ) -> None:
        """
        Property: For any exception, to_dict() SHALL produce a dictionary
        containing all context information.

        **Feature: test-coverage-improvement, Property 5: Exception Context Preservation**
        **Validates: Requirements 4.2, 4.3**
        """
        exc = TreeSitterAnalyzerError(message, context=context)
        result = exc.to_dict()

        # All required fields should be present
        assert "error_type" in result
        assert "error_code" in result
        assert "message" in result
        assert "context" in result

        # Values should match
        assert result["message"] == message
        assert result["context"] == context
        assert result["error_type"] == "TreeSitterAnalyzerError"

    @given(
        message=safe_text,
        context=context_dict,
    )
    @settings(max_examples=100)
    def test_create_error_response_preserves_context(
        self, message: str, context: dict[str, Any]
    ) -> None:
        """
        Property: For any exception with context, create_error_response()
        SHALL include the context in the response.

        **Feature: test-coverage-improvement, Property 5: Exception Context Preservation**
        **Validates: Requirements 4.2, 4.3**
        """
        exc = TreeSitterAnalyzerError(message, context=context)
        response = create_error_response(exc)

        # Response should indicate failure
        assert response["success"] is False

        # Error information should be preserved
        assert response["error"]["type"] == "TreeSitterAnalyzerError"
        assert response["error"]["message"] == message

        # Context should be preserved if non-empty
        if context:
            assert "context" in response["error"]
            assert response["error"]["context"] == context

    @given(
        message=safe_text,
        tool_name=st.one_of(st.none(), safe_text),
    )
    @settings(max_examples=100)
    def test_mcp_error_response_preserves_tool_context(
        self, message: str, tool_name: str | None
    ) -> None:
        """
        Property: For any MCP error, create_mcp_error_response() SHALL
        preserve the tool name in the response.

        **Feature: test-coverage-improvement, Property 5: Exception Context Preservation**
        **Validates: Requirements 4.2, 4.3**
        """
        exc = MCPError(message, tool_name=tool_name)
        response = create_mcp_error_response(exc, tool_name=tool_name)

        # Response should indicate failure
        assert response["success"] is False

        # Tool name should be preserved if provided
        if tool_name:
            assert response["error"]["tool"] == tool_name

        # Timestamp should always be present
        assert "timestamp" in response["error"]

    @given(
        message=safe_text,
        query_name=st.one_of(st.none(), safe_text),
        query_string=st.one_of(st.none(), safe_text),
        language=st.one_of(st.none(), st.sampled_from(["python", "java", "javascript"])),
    )
    @settings(max_examples=100)
    def test_query_error_preserves_all_query_context(
        self,
        message: str,
        query_name: str | None,
        query_string: str | None,
        language: str | None,
    ) -> None:
        """
        Property: For any QueryError, all query-related context (name, string,
        language) SHALL be preserved in the context dictionary.

        **Feature: test-coverage-improvement, Property 5: Exception Context Preservation**
        **Validates: Requirements 4.2, 4.3**
        """
        exc = QueryError(
            message,
            query_name=query_name,
            query_string=query_string,
            language=language,
        )

        if query_name:
            assert exc.context["query_name"] == query_name
        if query_string:
            assert exc.context["query_string"] == query_string
        if language:
            assert exc.context["language"] == language

    @given(
        message=safe_text,
        timeout_seconds=st.floats(
            min_value=0.1, max_value=3600.0, allow_nan=False, allow_infinity=False
        ),
        operation_type=st.one_of(st.none(), safe_text),
    )
    @settings(max_examples=100)
    def test_mcp_timeout_error_preserves_timeout_context(
        self, message: str, timeout_seconds: float, operation_type: str | None
    ) -> None:
        """
        Property: For any MCPTimeoutError, timeout_seconds and operation_type
        SHALL be preserved both as attributes and in context.

        **Feature: test-coverage-improvement, Property 5: Exception Context Preservation**
        **Validates: Requirements 4.2, 4.3**
        """
        exc = MCPTimeoutError(
            message, timeout_seconds=timeout_seconds, operation_type=operation_type
        )

        # Attributes should be preserved
        assert exc.timeout_seconds == timeout_seconds
        assert exc.operation_type == operation_type

        # Context should also contain these values
        assert exc.context["timeout_seconds"] == timeout_seconds
        if operation_type:
            assert exc.context["operation_type"] == operation_type

    @given(
        message=safe_text,
        resource_uri=st.one_of(st.none(), safe_text),
        resource_type=st.one_of(st.none(), st.sampled_from(["file", "directory", "url"])),
        access_mode=st.one_of(st.none(), st.sampled_from(["read", "write", "execute"])),
    )
    @settings(max_examples=100)
    def test_mcp_resource_error_preserves_resource_context(
        self,
        message: str,
        resource_uri: str | None,
        resource_type: str | None,
        access_mode: str | None,
    ) -> None:
        """
        Property: For any MCPResourceError, all resource-related context
        SHALL be preserved both as attributes and in context.

        **Feature: test-coverage-improvement, Property 5: Exception Context Preservation**
        **Validates: Requirements 4.2, 4.3**
        """
        exc = MCPResourceError(
            message,
            resource_uri=resource_uri,
            resource_type=resource_type,
            access_mode=access_mode,
        )

        # Attributes should be preserved
        assert exc.resource_uri == resource_uri
        assert exc.resource_type == resource_type
        assert exc.access_mode == access_mode

        # Context should contain these values if provided
        if resource_type:
            assert exc.context["resource_type"] == resource_type
        if access_mode:
            assert exc.context["access_mode"] == access_mode

    @given(
        inner_message=safe_text,
        outer_message=safe_text,
        inner_context=context_dict,
    )
    @settings(max_examples=100)
    def test_nested_exception_chain_preserves_all_causes(
        self, inner_message: str, outer_message: str, inner_context: dict[str, Any]
    ) -> None:
        """
        Property: For any nested exception chain (A -> B -> C), all causes
        SHALL be preserved and accessible through __cause__ chain.

        **Feature: test-coverage-improvement, Property 5: Exception Context Preservation**
        **Validates: Requirements 4.2, 4.3**
        """
        inner = TreeSitterAnalyzerError(inner_message, context=inner_context)

        try:
            try:
                raise inner
            except TreeSitterAnalyzerError as e:
                raise AnalysisError(outer_message) from e
        except AnalysisError as outer:
            # Outer exception should have cause
            assert outer.__cause__ is not None
            assert outer.__cause__ is inner

            # Inner exception context should be preserved
            assert outer.__cause__.context == inner_context
            assert str(outer.__cause__) == inner_message

    @given(
        message=safe_text,
        language=safe_text,
        supported=st.lists(safe_text, min_size=0, max_size=5),
    )
    @settings(max_examples=100)
    def test_language_not_supported_error_preserves_language_info(
        self, message: str, language: str, supported: list[str]
    ) -> None:
        """
        Property: For any LanguageNotSupportedError, the unsupported language
        and list of supported languages SHALL be preserved in context.

        **Feature: test-coverage-improvement, Property 5: Exception Context Preservation**
        **Validates: Requirements 4.2, 4.3**
        """
        # Use supported list only if non-empty
        supported_list = supported if supported else None
        exc = LanguageNotSupportedError(language, supported_languages=supported_list)

        # Language should always be in context
        assert exc.context["language"] == language

        # Supported languages should be in context if provided
        if supported_list:
            assert exc.context["supported_languages"] == supported_list
            # Message should mention supported languages
            for lang in supported_list:
                assert lang in exc.message

    @given(
        message=safe_text,
        validation_type=st.one_of(st.none(), safe_text),
        invalid_value=st.one_of(
            st.none(),
            st.integers(),
            st.text(max_size=20),
            st.booleans(),
        ),
    )
    @settings(max_examples=100)
    def test_validation_error_preserves_validation_context(
        self, message: str, validation_type: str | None, invalid_value: Any
    ) -> None:
        """
        Property: For any ValidationError, validation_type and invalid_value
        SHALL be preserved in the context dictionary.

        **Feature: test-coverage-improvement, Property 5: Exception Context Preservation**
        **Validates: Requirements 4.2, 4.3**
        """
        exc = ValidationError(
            message, validation_type=validation_type, invalid_value=invalid_value
        )

        if validation_type:
            assert exc.context["validation_type"] == validation_type
        if invalid_value is not None:
            assert exc.context["invalid_value"] == invalid_value


class TestExceptionChainWithDecorator:
    """Test exception chain preservation with handle_exceptions decorator."""

    @given(original_message=safe_text)
    @settings(max_examples=100)
    def test_handle_exceptions_decorator_preserves_cause_chain(
        self, original_message: str
    ) -> None:
        """
        Property: When handle_exceptions decorator re-raises as a different
        exception type, the original exception SHALL be preserved as __cause__.

        **Feature: test-coverage-improvement, Property 5: Exception Context Preservation**
        **Validates: Requirements 4.2, 4.3**
        """

        @handle_exceptions(reraise_as=AnalysisError, log_errors=False)
        def failing_function() -> None:
            raise ValueError(original_message)

        with pytest.raises(AnalysisError) as exc_info:
            failing_function()

        # The cause should be the original ValueError
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)
        assert str(exc_info.value.__cause__) == original_message

