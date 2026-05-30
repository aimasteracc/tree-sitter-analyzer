#!/usr/bin/env python3
"""
Markup and configuration language models.

Contains: MarkupElement, StyleElement, YAMLElement
"""

from dataclasses import dataclass, field
from typing import Any

from .base import CodeElement


@dataclass(frozen=False)
class MarkupElement(CodeElement):
    """
    HTML要素を表現するデータモデル。
    CodeElementを継承し、マークアップ固有の属性を追加する。
    """

    tag_name: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    parent: "MarkupElement | None" = None
    children: list["MarkupElement"] = field(default_factory=list)
    element_class: str = ""  # 分類システムのカテゴリ (例: 'structure', 'media', 'form')
    element_type: str = "html_element"

    def to_summary_item(self) -> dict[str, Any]:
        """Return dictionary for summary item"""
        return {
            "name": self.name,
            "tag_name": self.tag_name,
            "type": "html_element",
            "element_class": self.element_class,
            "lines": {"start": self.start_line, "end": self.end_line},
        }


@dataclass(frozen=False)
class StyleElement(CodeElement):
    """
    CSSルールを表現するデータモデル。
    CodeElementを継承する。
    """

    selector: str = ""
    properties: dict[str, str] = field(default_factory=dict)
    element_class: str = (
        ""  # 分類システムのカテゴリ (例: 'layout', 'typography', 'color')
    )
    element_type: str = "css_rule"

    def to_summary_item(self) -> dict[str, Any]:
        """Return dictionary for summary item"""
        return {
            "name": self.name,
            "selector": self.selector,
            "type": "css_rule",
            "element_class": self.element_class,
            "lines": {"start": self.start_line, "end": self.end_line},
        }


@dataclass(frozen=False)
class YAMLElement(CodeElement):
    """
    YAML要素を表現するデータモデル。

    Attributes:
        element_type: 要素タイプ (mapping, sequence, scalar, anchor, alias, comment, document)
        key: マッピングのキー
        value: スカラー値（複合構造の場合はNone）
        value_type: 値の型 (string, number, boolean, null, mapping, sequence)
        anchor_name: アンカー名 (&name)
        alias_target: エイリアスの参照先名（展開しない）
        nesting_level: AST上の論理的な深さ
        document_index: マルチドキュメントYAMLでのドキュメントインデックス
        child_count: 複合構造の子要素数
    """

    language: str = "yaml"
    element_type: str = "yaml"
    key: str | None = None
    value: str | None = None
    value_type: str | None = None
    anchor_name: str | None = None
    alias_target: str | None = None
    nesting_level: int = 0
    document_index: int = 0
    child_count: int | None = None

    def to_summary_item(self) -> dict[str, Any]:
        """Return dictionary for summary item with YAML-specific information."""
        return {
            "name": self.name,
            "type": self.element_type,
            "lines": {"start": self.start_line, "end": self.end_line},
            "key": self.key,
            "value_type": self.value_type,
            "nesting_level": self.nesting_level,
            "document_index": self.document_index,
        }


__all__ = [
    "MarkupElement",
    "StyleElement",
    "YAMLElement",
]
