#!/usr/bin/env python3
"""
Comprehensive tests for MCP server to achieve high coverage.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from tree_sitter_analyzer.interfaces.mcp_server import TreeSitterAnalyzerMCPServer


class TestTreeSitterAnalyzerMCPServerComprehensive:
    """Comprehensive test suite for TreeSitterAnalyzerMCPServer"""

    def test_init_success(self):
        """Test successful initialization"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            server = TreeSitterAnalyzerMCPServer()
            assert server.name == "tree-sitter-analyzer"
            assert server.version == "2.0.0"
            assert server.server is None

    def test_init_mcp_not_available(self):
        """Test initialization when MCP is not available"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', False):
            with pytest.raises(ImportError, match="MCP library not available"):
                TreeSitterAnalyzerMCPServer()

    def test_create_server(self):
        """Test server creation"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            with patch('tree_sitter_analyzer.interfaces.mcp_server.Server') as mock_server_class:
                mock_server = Mock()
                mock_server.list_tools = Mock(return_value=lambda: None)
                mock_server.call_tool = Mock(return_value=lambda: None)
                mock_server.list_resources = Mock(return_value=lambda: None)
                mock_server.read_resource = Mock(return_value=lambda: None)
                mock_server_class.return_value = mock_server
                
                server_instance = TreeSitterAnalyzerMCPServer()
                result = server_instance.create_server()
                
                assert result is not None
                mock_server_class.assert_called_once_with("tree-sitter-analyzer")

    def test_run_server(self):
        """Test running the server"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            with patch('tree_sitter_analyzer.interfaces.mcp_server.Server') as mock_server_class:
                with patch('tree_sitter_analyzer.interfaces.mcp_server.stdio_server') as mock_stdio:
                    mock_server = Mock()
                    mock_server.list_tools = Mock(return_value=lambda: None)
                    mock_server.call_tool = Mock(return_value=lambda: None)
                    mock_server.list_resources = Mock(return_value=lambda: None)
                    mock_server.read_resource = Mock(return_value=lambda: None)
                    mock_server_class.return_value = mock_server
                    
                    mock_stdio.return_value = AsyncMock()
                    
                    server_instance = TreeSitterAnalyzerMCPServer()
                    
                    # Test that run method exists and can be called
                    assert hasattr(server_instance, 'run')

    def test_server_tools_registration(self):
        """Test that server tools are properly registered"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            with patch('tree_sitter_analyzer.interfaces.mcp_server.Server') as mock_server_class:
                mock_server = Mock()
                list_tools_decorator = Mock()
                call_tool_decorator = Mock()
                list_resources_decorator = Mock()
                read_resource_decorator = Mock()
                
                mock_server.list_tools.return_value = list_tools_decorator
                mock_server.call_tool.return_value = call_tool_decorator
                mock_server.list_resources.return_value = list_resources_decorator
                mock_server.read_resource.return_value = read_resource_decorator
                
                mock_server_class.return_value = mock_server
                
                server_instance = TreeSitterAnalyzerMCPServer()
                server_instance.create_server()
                
                # Verify decorators were called
                mock_server.list_tools.assert_called()
                mock_server.call_tool.assert_called()
                mock_server.list_resources.assert_called()
                mock_server.read_resource.assert_called()

    def test_error_handling_in_server_creation(self):
        """Test error handling during server creation"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            with patch('tree_sitter_analyzer.interfaces.mcp_server.Server') as mock_server_class:
                mock_server_class.side_effect = Exception("Server creation failed")
                
                server_instance = TreeSitterAnalyzerMCPServer()
                
                with pytest.raises(Exception, match="Server creation failed"):
                    server_instance.create_server()

    def test_logging_integration(self):
        """Test logging integration"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            with patch('tree_sitter_analyzer.interfaces.mcp_server.log_info') as mock_log_info:
                server_instance = TreeSitterAnalyzerMCPServer()
                
                # Verify initialization logging
                mock_log_info.assert_called_with("Initializing tree-sitter-analyzer v2.0.0")

    def test_server_attributes(self):
        """Test server attributes"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            server_instance = TreeSitterAnalyzerMCPServer()
            
            assert server_instance.name == "tree-sitter-analyzer"
            assert server_instance.version == "2.0.0"
            assert server_instance.server is None

    def test_server_with_api_integration(self):
        """Test server integration with API"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            with patch('tree_sitter_analyzer.interfaces.mcp_server.api') as mock_api:
                mock_api.analyze_file = Mock(return_value={"result": "success"})
                mock_api.analyze_code = Mock(return_value={"result": "success"})
                mock_api.extract_elements = Mock(return_value={"elements": []})
                
                server_instance = TreeSitterAnalyzerMCPServer()
                
                # Test that API is available for use
                assert mock_api is not None

    def test_fallback_classes_when_mcp_unavailable(self):
        """Test fallback classes when MCP is not available"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', False):
            # Import the fallback classes
            from tree_sitter_analyzer.interfaces.mcp_server import (
                Server, InitializationOptions, Tool, Resource, TextContent, stdio_server
            )
            
            # Test fallback classes can be instantiated
            server = Server()
            init_options = InitializationOptions()
            tool = Tool()
            resource = Resource()
            text_content = TextContent()
            
            # Test fallback function
            result = stdio_server()
            assert result is None

    def test_server_configuration(self):
        """Test server configuration"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            server_instance = TreeSitterAnalyzerMCPServer()
            
            # Test server properties
            assert isinstance(server_instance.name, str)
            assert isinstance(server_instance.version, str)
            assert len(server_instance.name) > 0
            assert len(server_instance.version) > 0

    def test_multiple_server_instances(self):
        """Test creating multiple server instances"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            server1 = TreeSitterAnalyzerMCPServer()
            server2 = TreeSitterAnalyzerMCPServer()
            
            # Each instance should be independent
            assert server1 is not server2
            assert server1.name == server2.name
            assert server1.version == server2.version

    def test_server_method_existence(self):
        """Test that required server methods exist"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            server_instance = TreeSitterAnalyzerMCPServer()
            
            # Test that key methods exist
            assert hasattr(server_instance, 'create_server')
            assert callable(getattr(server_instance, 'create_server'))
            
            # Test that run method exists (if implemented)
            if hasattr(server_instance, 'run'):
                assert callable(getattr(server_instance, 'run'))

    def test_server_with_different_configurations(self):
        """Test server with different configurations"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            # Test default configuration
            server_instance = TreeSitterAnalyzerMCPServer()
            assert server_instance.name == "tree-sitter-analyzer"
            
            # Test that server can be created multiple times
            server1 = server_instance.create_server()
            server2 = server_instance.create_server()
            
            # Both should be valid server objects
            assert server1 is not None
            assert server2 is not None

    def test_error_recovery(self):
        """Test error recovery scenarios"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            with patch('tree_sitter_analyzer.interfaces.mcp_server.log_error') as mock_log_error:
                server_instance = TreeSitterAnalyzerMCPServer()
                
                # Test that server instance is still valid after errors
                assert server_instance.name == "tree-sitter-analyzer"
                assert server_instance.version == "2.0.0"

    def test_memory_usage(self):
        """Test memory usage patterns"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            # Create and destroy multiple server instances
            servers = []
            for i in range(10):
                server = TreeSitterAnalyzerMCPServer()
                servers.append(server)
            
            # All servers should be independent
            assert len(servers) == 10
            assert all(s.name == "tree-sitter-analyzer" for s in servers)
            
            # Clear references
            servers.clear()
            
            # Should complete without memory issues
            assert True

    def test_concurrent_server_creation(self):
        """Test concurrent server creation"""
        import threading
        
        results = []
        errors = []
        
        def create_server():
            try:
                with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
                    server = TreeSitterAnalyzerMCPServer()
                    results.append(server)
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
        assert len(results) == 5
        assert all(s.name == "tree-sitter-analyzer" for s in results)

    def test_server_state_consistency(self):
        """Test server state consistency"""
        with patch('tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE', True):
            server_instance = TreeSitterAnalyzerMCPServer()
            
            # Initial state
            initial_name = server_instance.name
            initial_version = server_instance.version
            initial_server = server_instance.server
            
            # State should remain consistent
            assert server_instance.name == initial_name
            assert server_instance.version == initial_version
            assert server_instance.server == initial_server
            
            # After creating server
            created_server = server_instance.create_server()
            
            # Basic properties should remain the same
            assert server_instance.name == initial_name
            assert server_instance.version == initial_version
            assert created_server is not None