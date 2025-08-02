#!/usr/bin/env python3
"""
Factory for creating language-specific table formatters.
"""

from .base_formatter import BaseTableFormatter
from .java_formatter import JavaTableFormatter
from .python_formatter import PythonTableFormatter


class TableFormatterFactory:
    """言語固有のテーブルフォーマッターを作成するファクトリー"""

    _formatters: dict[str, type[BaseTableFormatter]] = {
        "java": JavaTableFormatter,
        "python": PythonTableFormatter,
    }

    @classmethod
    def create_formatter(
        cls, language: str, format_type: str = "full"
    ) -> BaseTableFormatter:
        """
        指定された言語用のテーブルフォーマッターを作成

        Args:
            language: プログラミング言語名
            format_type: フォーマットタイプ（full, compact, csv）

        Returns:
            言語固有のテーブルフォーマッター
        """
        formatter_class = cls._formatters.get(language.lower())

        if formatter_class is None:
            # デフォルトとしてJavaフォーマッターを使用
            formatter_class = JavaTableFormatter

        return formatter_class(format_type)

    @classmethod
    def register_formatter(
        cls, language: str, formatter_class: type[BaseTableFormatter]
    ) -> None:
        """
        新しい言語フォーマッターを登録

        Args:
            language: プログラミング言語名
            formatter_class: フォーマッタークラス
        """
        cls._formatters[language.lower()] = formatter_class

    @classmethod
    def get_supported_languages(cls) -> list[str]:
        """
        サポートされている言語一覧を取得

        Returns:
            サポートされている言語のリスト
        """
        return list(cls._formatters.keys())


def create_table_formatter(
    format_type: str, language: str = "java"
) -> BaseTableFormatter:
    """
    テーブルフォーマッターを作成（互換性のための関数）

    Args:
        format_type: フォーマットタイプ
        language: プログラミング言語名

    Returns:
        テーブルフォーマッター
    """
    return TableFormatterFactory.create_formatter(language, format_type)
