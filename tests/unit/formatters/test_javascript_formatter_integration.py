#!/usr/bin/env python3
"""Integration tests for JavaScriptTableFormatter — realistic JS/TS data formatting."""

from tree_sitter_analyzer.formatters.javascript_formatter import (
    JavaScriptTableFormatter,
)


class TestJavaScriptFormatterIntegration:
    """Integration tests for JavaScript formatter"""

    def test_format_real_javascript_data(self):
        """Test formatting with realistic JavaScript analysis data"""
        formatter = JavaScriptTableFormatter()

        # Realistic JavaScript analysis data
        real_data = {
            "file_path": "src/components/UserProfile.js",
            "imports": [
                {"name": "React", "source": "react"},
                {"name": "useState", "source": "react"},
                {"name": "useEffect", "source": "react"},
                {"name": "PropTypes", "source": "prop-types"},
                {"name": "UserService", "source": "../services/UserService"},
            ],
            "exports": [
                {"name": "UserProfile", "is_default": True},
                {"name": "validateUser", "is_named": True},
            ],
            "classes": [
                {
                    "name": "UserProfile",
                    "methods": [
                        {"name": "constructor", "parameters": ["props"]},
                        {"name": "componentDidMount", "parameters": []},
                        {"name": "handleUserUpdate", "parameters": ["userData"]},
                        {"name": "render", "parameters": []},
                    ],
                }
            ],
            "variables": [
                {"name": "defaultProps", "type": "object", "is_constant": True},
                {
                    "name": "userState",
                    "type": "object",
                    "raw_text": "const userState = useState({})",
                },
                {
                    "name": "isLoading",
                    "type": "boolean",
                    "raw_text": "let isLoading = false",
                },
            ],
            "functions": [
                {
                    "name": "validateUser",
                    "parameters": [
                        {"name": "user", "type": "object"},
                        {"name": "options", "type": "object", "default": "{}"},
                    ],
                    "is_async": False,
                    "return_type": "boolean",
                },
                {
                    "name": "fetchUserData",
                    "parameters": [{"name": "userId", "type": "string"}],
                    "is_async": True,
                    "return_type": "Promise<User>",
                },
            ],
            "statistics": {
                "function_count": 2,
                "variable_count": 3,
                "class_count": 1,
                "import_count": 5,
                "export_count": 2,
            },
        }

        # Test all format types
        full_result = formatter.format(real_data, "full")
        compact_result = formatter.format(real_data, "compact")
        csv_result = formatter.format(real_data, "csv")
        json_result = formatter.format(real_data, "json")

        # Verify all formats work
        assert isinstance(full_result, str)
        # Normalize CRLF→LF so byte pins hold on Windows (5b-B; Codex P1)
        assert len(full_result.replace("\r\n", "\n")) == 217
        assert isinstance(compact_result, str)
        assert len(compact_result.replace("\r\n", "\n")) == 110
        assert isinstance(csv_result, str)
        assert len(csv_result.replace("\r\n", "\n")) == 51
        assert isinstance(json_result, str)
        assert len(json_result.replace("\r\n", "\n")) == 2058

        # Verify content is present in full format (new format uses class name as header)
        assert "UserProfile" in full_result

    def test_format_with_complex_typescript_features(self):
        """Test formatting with complex TypeScript/JavaScript features"""
        formatter = JavaScriptTableFormatter()

        complex_data = {
            "file_path": "src/utils/ApiClient.ts",
            "imports": [
                {"name": "axios", "source": "axios"},
                {"name": "AxiosResponse", "source": "axios"},
                {"name": "Observable", "source": "rxjs"},
                {"name": "map", "source": "rxjs/operators"},
            ],
            "exports": [
                {"name": "ApiClient", "is_default": True},
                {"name": "HttpMethod", "is_named": True},
                {"name": "ApiResponse", "is_named": True},
            ],
            "classes": [
                {
                    "name": "ApiClient",
                    "methods": [
                        {"name": "constructor", "parameters": ["baseUrl", "config"]},
                        {
                            "name": "get",
                            "parameters": ["url", "config"],
                            "generics": ["T"],
                        },
                        {
                            "name": "post",
                            "parameters": ["url", "data", "config"],
                            "generics": ["T", "U"],
                        },
                        {"name": "put", "parameters": ["url", "data", "config"]},
                        {"name": "delete", "parameters": ["url", "config"]},
                    ],
                }
            ],
            "variables": [
                {
                    "name": "DEFAULT_TIMEOUT",
                    "type": "number",
                    "is_constant": True,
                    "value": "5000",
                },
                {
                    "name": "httpClient",
                    "type": "AxiosInstance",
                    "raw_text": "const httpClient = axios.create()",
                },
                {
                    "name": "interceptors",
                    "type": "object",
                    "raw_text": "let interceptors = {}",
                },
            ],
            "functions": [
                {
                    "name": "createApiClient",
                    "parameters": [
                        {"name": "config", "type": "ApiConfig"},
                        {
                            "name": "interceptors",
                            "type": "Interceptor[]",
                            "default": "[]",
                        },
                    ],
                    "is_async": False,
                    "return_type": "ApiClient",
                    "generics": ["T extends BaseConfig"],
                },
                {
                    "name": "handleApiError",
                    "parameters": [
                        {"name": "error", "type": "AxiosError"},
                        {"name": "context", "type": "string", "default": "'unknown'"},
                    ],
                    "is_async": True,
                    "return_type": "Promise<never>",
                },
            ],
            "statistics": {
                "function_count": 2,
                "variable_count": 3,
                "class_count": 1,
                "import_count": 4,
                "export_count": 3,
            },
        }

        # Test formatting
        result = formatter.format(complex_data, "full")

        # Verify complex features are handled (new format uses class name as header)
        assert isinstance(result, str)
        assert len(result.replace("\r\n", "\n")) == 211
        assert "ApiClient" in result
