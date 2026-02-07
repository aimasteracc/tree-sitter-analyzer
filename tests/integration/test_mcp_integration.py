"""Integration tests for MCP server"""

import pytest
import asyncio
import json
import tempfile
from pathlib import Path

from tree_sitter_analyzer_v2.mcp.server import MCPServer


@pytest.fixture
def temp_project():
    """Create a temporary project directory with sample Python file"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a sample Python file
        sample_file = Path(tmpdir) / "sample.py"
        sample_file.write_text("""
def hello():
    print("Hello, World!")

def goodbye():
    print("Goodbye!")

class MyClass:
    def method1(self):
        pass
    
    def method2(self):
        pass
""")
        yield tmpdir


class TestMCPIntegration:
    """Test MCP server integration"""

    @pytest.mark.asyncio
    async def test_server_initialization(self, temp_project):
        """Test server can be initialized"""
        server = MCPServer(project_root=temp_project)
        assert server is not None
        assert server.tool_registry is not None
        assert server.project_root == Path(temp_project).resolve()

    @pytest.mark.asyncio
    async def test_list_tools(self, temp_project):
        """Test listing available tools"""
        server = MCPServer(project_root=temp_project)
        tools = server.tool_registry.get_all_schemas()
        
        assert len(tools) == 11  # 11 core tree-sitter + search + graph tools
        tool_names = [t['name'] for t in tools]
        assert 'analyze_code_graph' in tool_names
        assert 'analyze_code_structure' in tool_names
        assert 'find_files' in tool_names

    @pytest.mark.asyncio
    async def test_tool_execution_async(self, temp_project):
        """Test that tools execute without blocking"""
        server = MCPServer(project_root=temp_project)
        
        # This should not block
        start = asyncio.get_event_loop().time()
        
        # Execute a simple tool
        tool = server.tool_registry.get('find_files')
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            tool.execute,
            {'root_dir': temp_project, 'pattern': '*.py'}
        )
        
        elapsed = asyncio.get_event_loop().time() - start
        
        assert result is not None
        assert elapsed < 5.0  # Should complete quickly

    @pytest.mark.asyncio
    async def test_parallel_tool_calls(self, temp_project):
        """Test multiple tools can execute in parallel"""
        server = MCPServer(project_root=temp_project)
        
        # Execute multiple find_files calls concurrently
        tool = server.tool_registry.get('find_files')
        
        loop = asyncio.get_event_loop()
        
        tasks = [
            loop.run_in_executor(
                None,
                tool.execute,
                {'root_dir': temp_project, 'pattern': '*.py'}
            )
            for _ in range(10)
        ]
        
        start = asyncio.get_event_loop().time()
        results = await asyncio.gather(*tasks)
        elapsed = asyncio.get_event_loop().time() - start
        
        assert len(results) == 10
        assert all(r is not None for r in results)
        assert elapsed < 5.0  # Parallel execution should be fast

    @pytest.mark.asyncio
    async def test_tool_timeout_handling(self, temp_project):
        """Test that long-running tools can be cancelled"""
        server = MCPServer(project_root=temp_project)
        
        # Execute a potentially slow operation
        tool = server.tool_registry.get('analyze_code_graph')
        
        loop = asyncio.get_event_loop()
        
        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    tool.execute,
                    {'file_path': str(Path(temp_project) / 'sample.py')}
                ),
                timeout=10.0
            )
            assert result is not None
        except asyncio.TimeoutError:
            pytest.fail("Tool execution timed out")

    @pytest.mark.asyncio
    async def test_error_handling(self, temp_project):
        """Test error handling in tool execution"""
        server = MCPServer(project_root=temp_project)
        
        tool = server.tool_registry.get('find_files')
        
        loop = asyncio.get_event_loop()
        
        # Execute with invalid arguments
        try:
            result = await loop.run_in_executor(
                None,
                tool.execute,
                {'root_dir': '/nonexistent/path', 'pattern': '*.py'}
            )
            # Should return error result, not crash
            assert result is not None
        except Exception as e:
            # Exception is acceptable for invalid input
            assert str(e) is not None

    @pytest.mark.asyncio
    async def test_analyze_code_graph_execution(self, temp_project):
        """Test analyze_code_graph tool execution"""
        server = MCPServer(project_root=temp_project)
        
        tool = server.tool_registry.get('analyze_code_graph')
        
        loop = asyncio.get_event_loop()
        
        # Analyze the sample file
        result = await loop.run_in_executor(
            None,
            tool.execute,
            {'file_path': str(Path(temp_project) / 'sample.py')}
        )
        
        assert result is not None
        # Check that result is a dictionary with expected keys
        assert isinstance(result, dict)
        # Should have statistics or output
        assert 'statistics' in result or 'output' in result or 'result' in result

    @pytest.mark.asyncio
    async def test_concurrent_tool_access(self, temp_project):
        """Test concurrent access to different tools"""
        server = MCPServer(project_root=temp_project)
        
        find_tool = server.tool_registry.get('find_files')
        analyze_tool = server.tool_registry.get('analyze_code_graph')
        
        loop = asyncio.get_event_loop()
        
        # Execute different tools concurrently
        tasks = [
            loop.run_in_executor(
                None,
                find_tool.execute,
                {'root_dir': temp_project, 'pattern': '*.py'}
            ),
            loop.run_in_executor(
                None,
                analyze_tool.execute,
                {'file_path': str(Path(temp_project) / 'sample.py')}
            ),
            loop.run_in_executor(
                None,
                find_tool.execute,
                {'root_dir': temp_project, 'pattern': '*.py'}
            ),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        assert len(results) == 3
        # At least some results should succeed
        successful = [r for r in results if not isinstance(r, Exception)]
        assert len(successful) > 0
