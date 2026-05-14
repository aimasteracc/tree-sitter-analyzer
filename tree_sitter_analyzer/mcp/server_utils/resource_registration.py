"""Resource handler registration for MCP server — extracted from server.py create_server."""

from typing import Any

from ...utils import setup_logger

logger = setup_logger(__name__)


def register_resources(server: Any, server_instance: Any) -> None:
    """Register resource handlers on the MCP server."""
    code_file_resource = server_instance.code_file_resource
    project_stats_resource = server_instance.project_stats_resource

    @server.list_resources()  # type: ignore
    async def handle_list_resources() -> list[Any]:
        """List available resources."""
        from mcp.types import Resource

        return [
            Resource(
                uri=code_file_resource.get_resource_info()["uri_template"],
                name=code_file_resource.get_resource_info()["name"],
                description=code_file_resource.get_resource_info()["description"],
                mimeType=code_file_resource.get_resource_info()["mime_type"],
            ),
            Resource(
                uri=project_stats_resource.get_resource_info()["uri_template"],
                name=project_stats_resource.get_resource_info()["name"],
                description=project_stats_resource.get_resource_info()["description"],
                mimeType=project_stats_resource.get_resource_info()["mime_type"],
            ),
        ]

    @server.read_resource()  # type: ignore
    async def handle_read_resource(uri: str) -> Any:
        """Read resource content."""
        try:
            if code_file_resource.matches_uri(uri):
                return await code_file_resource.read_resource(uri)
            elif project_stats_resource.matches_uri(uri):
                return await project_stats_resource.read_resource(uri)
            else:
                raise ValueError(f"Resource not found: {uri}")
        except Exception as e:
            try:
                logger.error(f"Resource read error for {uri}: {e}")
            except (ValueError, OSError):
                pass
            raise
