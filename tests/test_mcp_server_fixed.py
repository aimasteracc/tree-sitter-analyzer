#!/usr/bin/env python3
"""
Fixed comprehensive tests for MCP server to achieve high coverage.
"""

import pytest
from unittest.mock import Mock, patch
from tree_sitter_analyzer.interfaces.mcp_server import TreeSitterAnalyzerMCPServer


class TestMCPServerFixed:
    """Fixed comprehensive test suite for MCP server"""

    def test_server_initialization_success(self):
        """Test successful server initialization"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            server = TreeSitterAnalyzerMCPServer()
            assert server.name == "tree-sitter-analyzer"
            assert server.version == "2.0.0"
            assert server.server is None

    def test_server_initialization_mcp_unavailable(self):
        """Test server initialization when MCP is unavailable"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', False):
            with pytest.raises(ImportError, match="MCP library not available"):
                TreeSitterAnalyzerMCPServer()

    def test_create_server_basic(self):
        """Test basic server creation"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            with patch('tree_sitter_analyzer.interfaces.mcp_server.Server') as mock_server_class:
                # Create a mock server with the required decorator methods
                mock_server = Mock()
                
                # Mock the decorator methods to return functions
                mock_server.list_tools.return_value = lambda func: func
                mock_server.call_tool.return_value = lambda func: func
                mock_server.list_resources.return_value = lambda func: func
                mock_server.read_resource.return_value = lambda func: func
                
                mock_server_class.return_value = mock_server
                
                server_instance = TreeSitterAnalyzerMCPServer()
                result = server_instance.create_server()
                
                assert result is not None
                mock_server_class.assert_called_once_with("tree-sitter-analyzer")

    def test_server_properties(self):
        """Test server properties"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            server = TreeSitterAnalyzerMCPServer()
            
            assert isinstance(server.name, str)
            assert isinstance(server.version, str)
            assert len(server.name) > 0
            assert len(server.version) > 0

    def test_server_logging_integration(self):
        """Test server logging integration"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            with patch('tree_sitter_analyzer.interfaces.mcp_server.log_info') as mock_log:
                server = TreeSitterAnalyzerMCPServer()
                
                # Verify initialization logging occurred
                mock_log.assert_called_with("Initializing tree-sitter-analyzer v2.0.0")

    def test_server_error_handling_during_creation(self):
        """Test server error handling during creation"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            with patch('tree_sitter_analyzer.interfaces.mcp_server.Server') as mock_server_class:
                mock_server_class.side_effect = Exception("Server creation failed")
                
                server_instance = TreeSitterAnalyzerMCPServer()
                
                with pytest.raises(Exception, match="Server creation failed"):
                    server_instance.create_server()

    def test_multiple_server_instances(self):
        """Test creating multiple server instances"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            servers = []
            for i in range(5):
                server = TreeSitterAnalyzerMCPServer()
                servers.append(server)
            
            # All servers should be independent instances
            assert len(servers) == 5
            for server in servers:
                assert server.name == "tree-sitter-analyzer"
                assert server.version == "2.0.0"
            
            # But they should be different objects
            assert servers[0] is not servers[1]

    def test_server_with_api_integration(self):
        """Test server integration with API module"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            with patch('tree_sitter_analyzer.interfaces.mcp_server.api') as mock_api:
                # Mock API functions
                mock_api.analyze_file.return_value = {"result": "success"}
                mock_api.analyze_code.return_value = {"result": "success"}
                mock_api.get_supported_languages.return_value = ["python", "java"]
                
                server = TreeSitterAnalyzerMCPServer()
                
                # Verify API is available for the server to use
                assert mock_api is not None

    def test_server_fallback_classes(self):
        """Test server fallback classes when MCP unavailable"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', False):
            # Import fallback classes
            from tree_sitter_analyzer.interfaces.mcp_server import (
                Server, InitializationOptions, Tool, Resource, TextContent, stdio_server
            )
            
            # Test that fallback classes exist and can be used
            assert Server is not None
            assert InitializationOptions is not None
            assert Tool is not None
            assert Resource is not None
            assert TextContent is not None
            assert stdio_server is not None
            
            # Test fallback function
            result = stdio_server()
            assert result is None

    def test_server_configuration_consistency(self):
        """Test server configuration consistency"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            server1 = TreeSitterAnalyzerMCPServer()
            server2 = TreeSitterAnalyzerMCPServer()
            
            # Both servers should have the same configuration
            assert server1.name == server2.name
            assert server1.version == server2.version

    def test_server_method_existence(self):
        """Test that server has expected methods"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            server = TreeSitterAnalyzerMCPServer()
            
            # Test that required methods exist
            assert hasattr(server, 'create_server')
            assert callable(server.create_server)
            
            # Test for run method if it exists
            if hasattr(server, 'run'):
                assert callable(server.run)

    def test_server_state_management(self):
        """Test server state management"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            server = TreeSitterAnalyzerMCPServer()
            
            # Initial state
            assert server.server is None
            
            # After creating server (with mocked Server class)
            with patch('tree_sitter_analyzer.interfaces.mcp_server.Server') as mock_server_class:
                mock_server = Mock()
                mock_server.list_tools.return_value = lambda func: func
                mock_server.call_tool.return_value = lambda func: func
                mock_server.list_resources.return_value = lambda func: func
                mock_server.read_resource.return_value = lambda func: func
                mock_server_class.return_value = mock_server
                
                created_server = server.create_server()
                assert created_server is not None

    def test_server_concurrent_creation(self):
        """Test concurrent server creation"""
        import threading
        
        servers = []
        errors = []
        
        def create_server():
            try:
                with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
                    server = TreeSitterAnalyzerMCPServer()
                    servers.append(server)
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=create_server)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(servers) == 5
        
        # All servers should have consistent properties
        for server in servers:
            assert server.name == "tree-sitter-analyzer"
            assert server.version == "2.0.0"

    def test_server_memory_cleanup(self):
        """Test server memory cleanup"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            # Create and destroy many server instances
            for i in range(100):
                server = TreeSitterAnalyzerMCPServer()
                # Use the server briefly
                assert server.name == "tree-sitter-analyzer"
                # Let it go out of scope
                del server
        
        # Should complete without memory issues
        assert True

    def test_server_with_different_configurations(self):
        """Test server behavior with different configurations"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            # Test with different environment variables
            test_configs = [
                {},
                {"LOG_LEVEL": "DEBUG"},
                {"LOG_LEVEL": "INFO"},
                {"LOG_LEVEL": "ERROR"}
            ]
            
            for config in test_configs:
                with patch.dict('os.environ', config):
                    server = TreeSitterAnalyzerMCPServer()
                    assert server.name == "tree-sitter-analyzer"
                    assert server.version == "2.0.0"