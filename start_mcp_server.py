#!/usr/bin/env python3
"""
Improved MCP Server Startup Script

This script provides a more robust way to start the MCP server with proper
initialization handling and error recovery.
"""

import asyncio
import sys
from pathlib import Path

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.project_detector import detect_project_root
from tree_sitter_analyzer.utils import setup_logger

# Configure logging
logger = setup_logger(__name__)


async def start_server_with_initialization_check():
    """Start the MCP server with proper initialization checking."""
    try:
        logger.info("=== Tree-sitter Analyzer MCP Server Startup ===")

        # Detect project root
        project_root = detect_project_root()
        logger.info(f"Detected project root: {project_root}")

        # Create server instance
        logger.info("Creating MCP server instance...")
        server = TreeSitterAnalyzerMCPServer(project_root)

        # Wait for initialization to complete
        max_wait_time = 10  # seconds
        wait_interval = 0.1  # seconds
        elapsed_time = 0

        while not server.is_initialized() and elapsed_time < max_wait_time:
            await asyncio.sleep(wait_interval)
            elapsed_time += wait_interval

        if not server.is_initialized():
            raise RuntimeError(
                f"Server initialization timed out after {max_wait_time} seconds"
            )

        logger.info("✅ Server initialization complete")
        logger.info("🚀 Starting MCP server...")

        # Start the server
        await server.run()

    except KeyboardInterrupt:
        logger.info("🛑 Server stopped by user")
    except Exception as e:
        logger.error(f"❌ Server startup failed: {e}")
        sys.exit(1)
    finally:
        logger.info("🔄 Server shutdown complete")


async def main_with_retry():
    """Main function with retry logic for robustness."""
    max_retries = 3
    retry_delay = 2  # seconds

    for attempt in range(max_retries):
        try:
            await start_server_with_initialization_check()
            break  # Success, exit retry loop
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error(f"All {max_retries} attempts failed. Last error: {e}")
                sys.exit(1)


def check_dependencies():
    """Check if all required dependencies are available."""
    try:
        import importlib.util

        mcp_spec = importlib.util.find_spec("mcp")
        if mcp_spec is None:
            raise ImportError()
        logger.info("✅ MCP library available")
    except ImportError:
        logger.error("❌ MCP library not found. Please install: pip install mcp")
        return False

    try:
        import importlib.util

        tree_sitter_spec = importlib.util.find_spec("tree_sitter")
        if tree_sitter_spec is None:
            raise ImportError()
        logger.info("✅ Tree-sitter library available")
    except ImportError:
        logger.error(
            "❌ Tree-sitter library not found. Please install: pip install tree-sitter"
        )
        return False

    return True


if __name__ == "__main__":
    print("🌳 Tree-sitter Analyzer MCP Server")
    print("=" * 50)

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)

    # Start server
    try:
        asyncio.run(main_with_retry())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
