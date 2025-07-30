#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base formatter for language-specific table formatting.
"""

import csv
import io
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseTableFormatter(ABC):
    """Base class for language-specific table formatters"""

    def __init__(self, format_type: str = "full"):
        self.format_type = format_type

    def _get_platform_newline(self) -> str:
        """プラットフォーム固有の改行コードを取得"""
        return os.linesep

    def _convert_to_platform_newlines(self, text: str) -> str:
        """通常の\nをプラットフォーム固有の改行コードに変換"""
        if os.linesep != "\n":
            return text.replace("\n", os.linesep)
        return text

    def format_structure(self, structure_data: Dict[str, Any]) -> str:
        """構造データをテーブル形式でフォーマット"""
        if self.format_type == "full":
            result = self._format_full_table(structure_data)
        elif self.format_type == "compact":
            result = self._format_compact_table(structure_data)
        elif self.format_type == "csv":
            result = self._format_csv(structure_data)
        else:
            raise ValueError(f"Unsupported format type: {self.format_type}")

        # 最終的にプラットフォーム固有の改行コードに変換
        if self.format_type == "csv":
            return result

        return self._convert_to_platform_newlines(result)

    @abstractmethod
    def _format_full_table(self, data: Dict[str, Any]) -> str:
        """完全版テーブル形式（言語固有実装）"""
        pass

    @abstractmethod
    def _format_compact_table(self, data: Dict[str, Any]) -> str:
        """コンパクト版テーブル形式（言語固有実装）"""
        pass

    def _format_csv(self, data: Dict[str, Any]) -> str:
        """CSV形式（共通実装）"""
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")

        # ヘッダー
        writer.writerow(
            ["Type", "Name", "Signature", "Visibility", "Lines", "Complexity", "Doc"]
        )

        # フィールド
        for field in data.get("fields", []):
            writer.writerow(
                [
                    "Field",
                    str(field.get("name", "")),
                    f"{str(field.get('name', ''))}:{str(field.get('type', ''))}",
                    str(field.get("visibility", "")),
                    f"{field.get('line_range', {}).get('start', 0)}-{field.get('line_range', {}).get('end', 0)}",
                    "",
                    self._clean_csv_text(
                        self._extract_doc_summary(str(field.get("javadoc", "")))
                    ),
                ]
            )

        # メソッド
        for method in data.get("methods", []):
            writer.writerow(
                [
                    "Constructor" if method.get("is_constructor", False) else "Method",
                    str(method.get("name", "")),
                    self._clean_csv_text(self._create_full_signature(method)),
                    str(method.get("visibility", "")),
                    f"{method.get('line_range', {}).get('start', 0)}-{method.get('line_range', {}).get('end', 0)}",
                    method.get("complexity_score", 0),
                    self._clean_csv_text(
                        self._extract_doc_summary(str(method.get("javadoc", "")))
                    ),
                ]
            )

        csv_content = output.getvalue()
        csv_content = csv_content.replace("\r\n", "\n").replace("\r", "\n")
        csv_content = csv_content.rstrip("\n")
        output.close()

        return csv_content

    # 共通ヘルパーメソッド
    def _create_full_signature(self, method: Dict[str, Any]) -> str:
        """完全なメソッドシグネチャを作成"""
        params = method.get("parameters", [])
        param_strs = []
        for param in params:
            if isinstance(param, dict):
                param_type = str(param.get("type", "Object"))
                param_name = str(param.get("name", "param"))
                param_strs.append(f"{param_name}:{param_type}")
            else:
                param_strs.append(str(param))

        params_str = ", ".join(param_strs)
        return_type = str(method.get("return_type", "void"))

        modifiers = []
        if method.get("is_static", False):
            modifiers.append("[static]")

        modifier_str = " ".join(modifiers)
        signature = f"({params_str}):{return_type}"

        if modifier_str:
            signature += f" {modifier_str}"

        return signature

    def _convert_visibility(self, visibility: str) -> str:
        """可視性を記号に変換"""
        mapping = {"public": "+", "private": "-", "protected": "#", "package": "~"}
        return mapping.get(visibility, visibility)

    def _extract_doc_summary(self, javadoc: str) -> str:
        """ドキュメントから要約を抽出"""
        if not javadoc:
            return "-"

        # コメント記号を除去
        clean_doc = (
            javadoc.replace("/**", "").replace("*/", "").replace("*", "").strip()
        )

        # 最初の行を取得
        lines = clean_doc.split("\n")
        first_line = lines[0].strip()

        # 長すぎる場合は切り詰め
        if len(first_line) > 50:
            first_line = first_line[:47] + "..."

        return first_line.replace("|", "\\|").replace("\n", " ")

    def _clean_csv_text(self, text: str) -> str:
        """CSV形式用のテキストクリーニング"""
        if not text:
            return ""

        cleaned = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
        cleaned = " ".join(cleaned.split())
        cleaned = cleaned.replace('"', '""')

        return cleaned