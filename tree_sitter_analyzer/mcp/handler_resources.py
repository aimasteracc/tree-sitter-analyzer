from typing import Any

try:
    from mcp.types import Resource
except ImportError:

    class Resource:  # type: ignore
        def __init__(
            self, uri: str, name: str, description: str, mimeType: str
        ) -> None:
            self.uri = uri
            self.name = name
            self.description = description
            self.mimeType = mimeType


from ..utils import setup_logger

logger = setup_logger(__name__)


class ResourceHandler:
    """Handles MCP resource requests."""

    def __init__(self, server: Any) -> None:
        """
        Initialize ResourceHandler.

        Args:
            server: The TreeSitterAnalyzerMCPServer instance containing resources
        """
        self.server = server

    async def list_resources(self) -> list[Resource]:
        """
        List available resources.

        Returns:
            List of Resource objects
        """
        return [
            Resource(
                uri=self.server.code_file_resource.get_resource_info()["uri_template"],
                name=self.server.code_file_resource.get_resource_info()["name"],
                description=self.server.code_file_resource.get_resource_info()[
                    "description"
                ],
                mimeType=self.server.code_file_resource.get_resource_info()[
                    "mime_type"
                ],
            ),
            Resource(
                uri=self.server.project_stats_resource.get_resource_info()[
                    "uri_template"
                ],
                name=self.server.project_stats_resource.get_resource_info()["name"],
                description=self.server.project_stats_resource.get_resource_info()[
                    "description"
                ],
                mimeType=self.server.project_stats_resource.get_resource_info()[
                    "mime_type"
                ],
            ),
        ]

    async def read_resource(self, uri: str) -> str:
        """
        Read resource content.

        Args:
            uri: The URI of the resource to read

        Returns:
            The content of the resource

        Raises:
            ValueError: If resource not found
        """
        try:
            # Check which resource matches the URI
            if self.server.code_file_resource.matches_uri(uri):
                result = await self.server.code_file_resource.read_resource(uri)
                return str(result)
            elif self.server.project_stats_resource.matches_uri(uri):
                result = await self.server.project_stats_resource.read_resource(uri)
                return str(result)
            else:
                raise ValueError(f"Resource not found: {uri}")

        except Exception as e:
            try:
                logger.error(f"Resource read error for {uri}: {e}")
            except (ValueError, OSError):
                pass
            raise
