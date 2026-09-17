#!/usr/bin/env python3
"""将意图别名解析为保留的工具入口。

符号定位使用 search action=symbol；map_structure 与 discover_files 使用已建立的 AST 索引。
结构提取和导航别名保持原有入口。退役的文本搜索包装器不再作为检索建议。
"""

# Intent Alias マッピング: 意図ベースの名前 → 実装ベースの tool名
INTENT_ALIASES: dict[str, str] = {
    # Search & Find 系 (search action=symbol を使用)
    "locate_usage": "search",  # 使用箇所を特定する (search action=symbol)
    "find_usage": "search",  # 使用箇所を見つける（locate_usage の代替）
    # File Discovery 系
    "map_structure": "codegraph_sitemap",  # 查看索引中的项目结构
    "discover_files": "codegraph_sitemap",  # 查找已索引文件（map_structure 的别名）
    # Impact Analysis 系 (query_code で代替)
    "find_impacted_code": "query_code",  # 影響を受けるコードを見つける (query_code)
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
        tool_name = resolver.resolve("locate_usage")  # → "search"
    """

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
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


def get_all_aliases() -> dict[str, str]:
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
