#!/usr/bin/env python3
"""
Intent Aliases System

Intent-based tool名を実装ベースの tool名に変換するシステム。
AI エージェントが「何をしたいか」（意図）でツールを呼び出せるようにする。

例:
- "locate_usage" → "search_content" (使用箇所を探す意図)
- "map_structure" → "list_files" (プロジェクト構造を把握する意図)
- "extract_structure" → "analyze_code_structure" (コード構造を抽出する意図)

Features:
- Intent-based naming (ユーザーの意図を反映した名前)
- Backward compatibility (元の tool名も引き続き使用可能)
- Multiple aliases (複数の alias が同じ tool を指せる)
- Case-sensitive (大文字小文字を区別)
"""

from typing import Dict


# Intent Alias マッピング: 意図ベースの名前 → 実装ベースの tool名
INTENT_ALIASES: Dict[str, str] = {
    # Search & Find 系
    "locate_usage": "search_content",  # 使用箇所を特定する
    "find_usage": "search_content",  # 使用箇所を見つける（locate_usage の代替）
    # File Discovery 系
    "map_structure": "list_files",  # プロジェクト構造をマッピングする
    "discover_files": "list_files",  # ファイルを発見する（map_structure の代替）
    # Impact Analysis 系
    "find_impacted_code": "find_and_grep",  # 影響を受けるコードを見つける
    # Structure Extraction 系
    "extract_structure": "analyze_code_structure",  # コード構造を抽出する
    # Navigation 系
    "navigate_structure": "get_code_outline",  # コード構造をナビゲートする
}


class IntentAliasResolver:
    """
    Intent Alias を tool名に解決するリゾルバー

    Usage:
        resolver = IntentAliasResolver()
        tool_name = resolver.resolve("locate_usage")  # → "search_content"
    """

    def __init__(self, aliases: Dict[str, str] | None = None) -> None:
        """
        Initialize IntentAliasResolver

        Args:
            aliases: カスタム alias マッピング（テスト用）
                    None の場合はデフォルトの INTENT_ALIASES を使用
        """
        self._aliases = aliases if aliases is not None else INTENT_ALIASES

    def resolve(self, name: str) -> str:
        """
        Tool名または alias を正規の tool名に解決

        Args:
            name: Tool名または intent alias

        Returns:
            正規の tool名

        Raises:
            TypeError: name が None の場合
            ValueError: name が空文字列または未知の名前の場合
        """
        if name is None:
            raise TypeError("Tool name cannot be None")

        if not name:
            raise ValueError("Tool name cannot be empty")

        # Alias マッピングに存在する場合は変換
        if name in self._aliases:
            return self._aliases[name]

        # 元々の tool名かチェック（backward compatibility）
        # alias の値（target tool名）のセットを取得
        known_tool_names = set(self._aliases.values())

        if name in known_tool_names:
            # 元々の tool名なのでそのまま返す
            return name

        # どちらでもない場合はエラー
        raise ValueError(
            f"Unknown tool or alias: '{name}'. "
            f"Must be a valid tool name or intent alias."
        )


def get_tool_name_from_alias(name: str) -> str:
    """
    Helper function: alias を tool名に変換

    Args:
        name: Tool名または intent alias

    Returns:
        正規の tool名

    Raises:
        ValueError: 未知の名前の場合
    """
    resolver = IntentAliasResolver()
    return resolver.resolve(name)


def get_all_aliases() -> Dict[str, str]:
    """
    全ての intent alias マッピングを取得

    Returns:
        {alias: tool_name} の辞書
    """
    return INTENT_ALIASES.copy()


def is_valid_alias(name: str) -> bool:
    """
    名前が有効な alias または tool名かチェック

    Args:
        name: チェックする名前

    Returns:
        有効な場合 True
    """
    if not name:
        return False

    try:
        resolver = IntentAliasResolver()
        resolver.resolve(name)
        return True
    except (ValueError, TypeError):
        return False
