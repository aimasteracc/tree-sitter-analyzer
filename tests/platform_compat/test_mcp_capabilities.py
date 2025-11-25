from unittest.mock import patch

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.platform_compat.detector import PlatformInfo


class TestMCPCapabilities:
    def test_platform_info_in_metadata(self):
        """
        Property 14: MCP capability consistency
        Validates: Requirements 7.5
        """
        with patch("tree_sitter_analyzer.mcp.server.PlatformDetector") as mock_detector:
            mock_detector.detect.return_value = PlatformInfo(
                os_name="test_os",
                os_version="1.0",
                python_version="3.10",
                platform_key="test_os-3.10",
            )

            # Mock other dependencies to avoid side effects
            with (
                patch("tree_sitter_analyzer.mcp.server.get_analysis_engine"),
                patch("tree_sitter_analyzer.mcp.server.SecurityValidator"),
                patch("tree_sitter_analyzer.mcp.server.QueryTool"),
                patch("tree_sitter_analyzer.mcp.server.ReadPartialTool"),
                patch("tree_sitter_analyzer.mcp.server.TableFormatTool"),
                patch("tree_sitter_analyzer.mcp.server.AnalyzeScaleTool"),
                patch("tree_sitter_analyzer.mcp.server.ListFilesTool"),
                patch("tree_sitter_analyzer.mcp.server.SearchContentTool"),
                patch("tree_sitter_analyzer.mcp.server.FindAndGrepTool"),
            ):
                server = TreeSitterAnalyzerMCPServer()

                assert "test_os-3.10" in server.version
