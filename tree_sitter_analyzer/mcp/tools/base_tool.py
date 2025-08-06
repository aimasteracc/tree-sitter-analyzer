#!/usr/bin/env python3
"""
Base Tool Protocol for MCP Tools

This module defines the protocol that all MCP tools must implement
to ensure type safety and consistency.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Protocol


class MCPTool(Protocol):
    """
    Protocol for MCP tools.

    All MCP tools must implement this protocol to ensure they have
    the required methods for integration with the MCP server.
    """

    def get_tool_definition(self) -> Any:
        """
        Get the MCP tool definition.

        Returns:
            Tool definition object compatible with MCP server
        """
        ...

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the tool with the given arguments.

        Args:
            arguments: Tool arguments

        Returns:
            Dictionary containing execution results
        """
        ...

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        Validate tool arguments.

        Args:
            arguments: Arguments to validate

        Returns:
            True if arguments are valid

        Raises:
            ValueError: If arguments are invalid
        """
        ...


class BaseTool(ABC):
    """
    魔法ツールの基底クラス

    すべての魔法ツールが継承すべき抽象基底クラス。
    MCPToolプロトコルを実装し、共通機能を提供します。
    """

    def __init__(self, name: str, description: str):
        """
        基底ツールの初期化

        Args:
            name: ツール名
            description: ツールの説明
        """
        self.name = name
        self.description = description

    def get_tool_definition(self) -> Dict[str, Any]:
        """
        MCP ツール定義の取得

        Returns:
            Dict: MCP互換のツール定義
        """
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self._get_input_schema_properties(),
                "required": self._get_required_parameters(),
                "additionalProperties": False
            }
        }

    @abstractmethod
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        ツールの実行（サブクラスで実装）

        Args:
            arguments: 実行引数

        Returns:
            Dict: 実行結果
        """
        pass

    def validate_arguments(self, arguments: Dict[str, Any]) -> bool:
        """
        引数の検証

        Args:
            arguments: 検証する引数

        Returns:
            bool: 引数が有効な場合True

        Raises:
            ValueError: 引数が無効な場合
        """
        required_params = self._get_required_parameters()

        # 必須パラメータのチェック
        for param in required_params:
            if param not in arguments:
                raise ValueError(f"Required parameter '{param}' is missing")

        return True

    def _get_input_schema_properties(self) -> Dict[str, Any]:
        """
        入力スキーマのプロパティ定義（サブクラスでオーバーライド可能）

        Returns:
            Dict: スキーマプロパティ
        """
        return {
            "project_path": {
                "type": "string",
                "description": "Path to the project directory"
            }
        }

    def _get_required_parameters(self) -> list[str]:
        """
        必須パラメータのリスト（サブクラスでオーバーライド可能）

        Returns:
            list: 必須パラメータ名のリスト
        """
        return ["project_path"]
