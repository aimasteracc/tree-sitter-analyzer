#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tree-sitter Analyzer Custom Exceptions

Unified exception handling system for consistent error management
across the entire framework.
"""

from typing import Any, Dict, Optional, Union
from pathlib import Path


class TreeSitterAnalyzerError(Exception):
    """Base exception for all tree-sitter analyzer errors."""
    
    def __init__(
        self, 
        message: str, 
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.context = context or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary format."""
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "context": self.context
        }


class AnalysisError(TreeSitterAnalyzerError):
    """Raised when file analysis fails."""
    
    def __init__(
        self, 
        message: str, 
        file_path: Optional[Union[str, Path]] = None,
        language: Optional[str] = None,
        **kwargs
    ) -> None:
        context = kwargs.get('context', {})
        if file_path:
            context['file_path'] = str(file_path)
        if language:
            context['language'] = language
        super().__init__(message, context=context, **kwargs)


class ParseError(TreeSitterAnalyzerError):
    """Raised when parsing fails."""
    
    def __init__(
        self, 
        message: str, 
        language: Optional[str] = None,
        source_info: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        context = kwargs.get('context', {})
        if language:
            context['language'] = language
        if source_info:
            context.update(source_info)
        super().__init__(message, context=context, **kwargs)


class LanguageNotSupportedError(TreeSitterAnalyzerError):
    """Raised when a language is not supported."""
    
    def __init__(
        self, 
        language: str, 
        supported_languages: Optional[list] = None,
        **kwargs
    ) -> None:
        message = f"Language '{language}' is not supported"
        context = kwargs.get('context', {})
        context['language'] = language
        if supported_languages:
            context['supported_languages'] = supported_languages
            message += f". Supported languages: {', '.join(supported_languages)}"
        super().__init__(message, context=context, **kwargs)


class PluginError(TreeSitterAnalyzerError):
    """Raised when plugin operations fail."""
    
    def __init__(
        self, 
        message: str, 
        plugin_name: Optional[str] = None,
        operation: Optional[str] = None,
        **kwargs
    ) -> None:
        context = kwargs.get('context', {})
        if plugin_name:
            context['plugin_name'] = plugin_name
        if operation:
            context['operation'] = operation
        super().__init__(message, context=context, **kwargs)


class QueryError(TreeSitterAnalyzerError):
    """Raised when query execution fails."""
    
    def __init__(
        self, 
        message: str, 
        query_name: Optional[str] = None,
        query_string: Optional[str] = None,
        language: Optional[str] = None,
        **kwargs
    ) -> None:
        context = kwargs.get('context', {})
        if query_name:
            context['query_name'] = query_name
        if query_string:
            context['query_string'] = query_string
        if language:
            context['language'] = language
        super().__init__(message, context=context, **kwargs)


class FileHandlingError(TreeSitterAnalyzerError):
    """Raised when file operations fail."""
    
    def __init__(
        self, 
        message: str, 
        file_path: Optional[Union[str, Path]] = None,
        operation: Optional[str] = None,
        **kwargs
    ) -> None:
        context = kwargs.get('context', {})
        if file_path:
            context['file_path'] = str(file_path)
        if operation:
            context['operation'] = operation
        super().__init__(message, context=context, **kwargs)


class ConfigurationError(TreeSitterAnalyzerError):
    """Raised when configuration is invalid."""
    
    def __init__(
        self, 
        message: str, 
        config_key: Optional[str] = None,
        config_value: Optional[Any] = None,
        **kwargs
    ) -> None:
        context = kwargs.get('context', {})
        if config_key:
            context['config_key'] = config_key
        if config_value is not None:
            context['config_value'] = config_value
        super().__init__(message, context=context, **kwargs)


class ValidationError(TreeSitterAnalyzerError):
    """Raised when validation fails."""
    
    def __init__(
        self, 
        message: str, 
        validation_type: Optional[str] = None,
        invalid_value: Optional[Any] = None,
        **kwargs
    ) -> None:
        context = kwargs.get('context', {})
        if validation_type:
            context['validation_type'] = validation_type
        if invalid_value is not None:
            context['invalid_value'] = invalid_value
        super().__init__(message, context=context, **kwargs)


class MCPError(TreeSitterAnalyzerError):
    """Raised when MCP operations fail."""
    
    def __init__(
        self, 
        message: str, 
        tool_name: Optional[str] = None,
        resource_uri: Optional[str] = None,
        **kwargs
    ) -> None:
        context = kwargs.get('context', {})
        if tool_name:
            context['tool_name'] = tool_name
        if resource_uri:
            context['resource_uri'] = resource_uri
        super().__init__(message, context=context, **kwargs)


# Exception handling utilities
def handle_exception(
    exception: Exception,
    context: Optional[Dict[str, Any]] = None,
    reraise_as: Optional[type] = None
) -> None:
    """
    Handle exceptions with optional context and re-raising.
    
    Args:
        exception: The original exception
        context: Additional context information
        reraise_as: Exception class to re-raise as
    """
    from .utils import log_error
    
    # Log the original exception
    error_context = context or {}
    if hasattr(exception, 'context'):
        error_context.update(exception.context)
    
    log_error(f"Exception handled: {exception}", extra=error_context)
    
    # Re-raise as different exception type if requested
    if reraise_as and not isinstance(exception, reraise_as):
        if issubclass(reraise_as, TreeSitterAnalyzerError):
            raise reraise_as(str(exception), context=error_context)
        else:
            raise reraise_as(str(exception))
    
    # Re-raise original exception
    raise exception


def safe_execute(
    func,
    *args,
    default_return=None,
    exception_types: tuple = (Exception,),
    log_errors: bool = True,
    **kwargs
):
    """
    Safely execute a function with exception handling.
    
    Args:
        func: Function to execute
        *args: Function arguments
        default_return: Value to return on exception
        exception_types: Exception types to catch
        log_errors: Whether to log errors
        **kwargs: Function keyword arguments
    
    Returns:
        Function result or default_return on exception
    """
    try:
        return func(*args, **kwargs)
    except exception_types as e:
        if log_errors:
            from .utils import log_error
            log_error(f"Safe execution failed for {func.__name__}: {e}")
        return default_return


def create_error_response(
    exception: Exception,
    include_traceback: bool = False
) -> Dict[str, Any]:
    """
    Create standardized error response dictionary.
    
    Args:
        exception: The exception to convert
        include_traceback: Whether to include traceback
    
    Returns:
        Error response dictionary
    """
    import traceback
    
    response = {
        "success": False,
        "error": {
            "type": exception.__class__.__name__,
            "message": str(exception)
        }
    }
    
    # Add context if available
    if hasattr(exception, 'context'):
        response["error"]["context"] = exception.context
    
    # Add error code if available
    if hasattr(exception, 'error_code'):
        response["error"]["code"] = exception.error_code
    
    # Add traceback if requested
    if include_traceback:
        response["error"]["traceback"] = traceback.format_exc()
    
    return response


# Decorator for exception handling
def handle_exceptions(
    default_return=None,
    exception_types: tuple = (Exception,),
    reraise_as: Optional[type] = None,
    log_errors: bool = True
):
    """
    Decorator for automatic exception handling.
    
    Args:
        default_return: Value to return on exception
        exception_types: Exception types to catch
        reraise_as: Exception class to re-raise as
        log_errors: Whether to log errors
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exception_types as e:
                if log_errors:
                    from .utils import log_error
                    log_error(f"Exception in {func.__name__}: {e}")
                
                if reraise_as:
                    if issubclass(reraise_as, TreeSitterAnalyzerError):
                        raise reraise_as(str(e))
                    else:
                        raise reraise_as(str(e))
                
                return default_return
        return wrapper
    return decorator