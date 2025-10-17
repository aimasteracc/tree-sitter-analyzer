#!/usr/bin/env python3
"""
MCP Client for testing tree-sitter-analyzer MCP server

This module provides a client to communicate with the MCP server
using the standard MCP protocol over stdio.
"""

import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# バージョン管理機能をインポート
from version_manager import VersionManager, create_version_manager

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_CLIENT_AVAILABLE = True
except ImportError:
    MCP_CLIENT_AVAILABLE = False

logger = logging.getLogger(__name__)

class MCPClient:
    """MCP Client for testing tree-sitter-analyzer"""
    
    def __init__(self, project_root: Optional[str] = None, version: str = "current"):
        self.project_root = project_root or str(Path(__file__).parent.parent.parent)
        self.version = version
        self.session: Optional[ClientSession] = None
        
        # バージョン管理機能を初期化
        self.version_manager = create_version_manager()
        
    async def connect(self) -> bool:
        """Connect to the MCP server"""
        if not MCP_CLIENT_AVAILABLE:
            logger.error("MCP client library not available")
            return False
            
        try:
            # バージョンに応じたPython実行可能ファイルとモジュールパスを取得
            python_exe = self.version_manager.get_python_executable(self.version)
            module_path = self.version_manager.get_module_path(self.version)
            env = self.version_manager.get_environment_variables(self.version)
            
            # Server parameters for stdio connection
            server_params = StdioServerParameters(
                command=python_exe,
                args=["-m", f"{module_path}.mcp.server", "--project-root", self.project_root],
                env=env
            )
            
            logger.info(f"MCPサーバーを起動中 (バージョン: {self.version}, Python: {python_exe})")
            
            # Create stdio client
            stdio_transport = stdio_client(server_params)
            
            # Initialize session
            self.session = await stdio_transport.__aenter__()
            
            # Initialize the session
            await self.session.initialize()
            
            logger.info("Successfully connected to MCP server")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from the MCP server"""
        if self.session:
            try:
                await self.session.__aexit__(None, None, None)
                self.session = None
                logger.info("Disconnected from MCP server")
            except Exception as e:
                logger.error(f"Error disconnecting from MCP server: {e}")
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on the MCP server"""
        if not self.session:
            return {
                "error": "NotConnected",
                "message": "Not connected to MCP server"
            }
        
        try:
            # Call the tool
            result = await self.session.call_tool(tool_name, arguments)
            
            # Extract content from result
            if hasattr(result, 'content') and result.content:
                # Get the first content item
                content_item = result.content[0]
                if hasattr(content_item, 'text'):
                    # Parse JSON response
                    return json.loads(content_item.text)
                else:
                    return {"content": str(content_item)}
            else:
                return {"result": "success", "content": str(result)}
                
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            return {
                "error": "ToolCallError",
                "message": str(e)
            }
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools"""
        if not self.session:
            return []
        
        try:
            tools_result = await self.session.list_tools()
            tools = []
            
            for tool in tools_result.tools:
                tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema
                })
            
            return tools
            
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            return []

class SimpleMCPClient:
    """Simplified MCP client using direct subprocess communication"""
    
    def __init__(self, project_root: Optional[str] = None, version: str = "current"):
        self.project_root = project_root or str(Path(__file__).parent.parent.parent)
        self.version = version
        self.process: Optional[subprocess.Popen] = None
        
        # バージョン管理機能を初期化
        self.version_manager = create_version_manager()
        
    async def connect(self) -> bool:
        """Start the MCP server process"""
        try:
            # バージョンに応じたPython実行可能ファイルとモジュールパスを取得
            python_exe = self.version_manager.get_python_executable(self.version)
            module_path = self.version_manager.get_module_path(self.version)
            env = self.version_manager.get_environment_variables(self.version)
            
            cmd = [
                python_exe, "-m", f"{module_path}.mcp.server",
                "--project-root", self.project_root
            ]
            
            logger.info(f"MCPサーバープロセスを起動中 (バージョン: {self.version}, コマンド: {' '.join(cmd)})")
            
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0,
                env=env
            )
            
            # Wait a bit for the server to start
            await asyncio.sleep(1)
            
            if self.process.poll() is None:
                logger.info("MCP server process started successfully")
                return True
            else:
                stderr_output = self.process.stderr.read() if self.process.stderr else ""
                logger.error(f"MCP server failed to start: {stderr_output}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to start MCP server: {e}")
            return False
    
    async def disconnect(self):
        """Stop the MCP server process"""
        if self.process:
            try:
                self.process.terminate()
                await asyncio.sleep(1)
                if self.process.poll() is None:
                    self.process.kill()
                self.process = None
                logger.info("MCP server process stopped")
            except Exception as e:
                logger.error(f"Error stopping MCP server: {e}")
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool using JSON-RPC over stdio"""
        if not self.process or self.process.poll() is not None:
            return {
                "error": "ServerNotRunning",
                "message": "MCP server is not running"
            }
        
        try:
            # Create JSON-RPC request
            request = {
                "jsonrpc": "2.0",
                "id": f"test_{int(asyncio.get_event_loop().time() * 1000)}",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            
            # Send request
            request_json = json.dumps(request) + "\n"
            logger.debug(f"Sending request: {request_json.strip()}")
            
            self.process.stdin.write(request_json)
            self.process.stdin.flush()
            
            # Read response with timeout
            response_line = await asyncio.wait_for(
                self._read_line_async(),
                timeout=30.0
            )
            
            if not response_line:
                return {
                    "error": "NoResponse",
                    "message": "No response from MCP server"
                }
            
            logger.debug(f"Received response: {response_line.strip()}")
            
            # Parse JSON-RPC response
            try:
                response = json.loads(response_line)
                
                if "error" in response:
                    return {
                        "error": response["error"].get("code", "UnknownError"),
                        "message": response["error"].get("message", "Unknown error")
                    }
                
                # Extract result from MCP response
                result = response.get("result", {})
                if isinstance(result, list) and len(result) > 0:
                    # Extract text content from MCP TextContent response
                    content_item = result[0]
                    if isinstance(content_item, dict) and "text" in content_item:
                        return json.loads(content_item["text"])
                
                return result
                
            except json.JSONDecodeError as e:
                return {
                    "error": "InvalidJSON",
                    "message": f"Invalid JSON response: {e}"
                }
                
        except asyncio.TimeoutError:
            return {
                "error": "Timeout",
                "message": "Tool call timed out"
            }
        except Exception as e:
            return {
                "error": "Exception",
                "message": str(e)
            }
    
    async def _read_line_async(self) -> str:
        """Read a line from stdout asynchronously"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.process.stdout.readline)

async def create_mcp_client(project_root: Optional[str] = None, version: str = "current") -> SimpleMCPClient:
    """Create and connect an MCP client"""
    client = SimpleMCPClient(project_root, version)
    
    if await client.connect():
        return client
    else:
        raise RuntimeError(f"Failed to connect to MCP server (version: {version})")

# For backward compatibility
MCPTestClient = SimpleMCPClient