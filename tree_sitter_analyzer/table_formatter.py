#!/usr/bin/env python3
"""
Table Formatter for Tree-sitter Analyzer

Provides table-formatted output for Java code analysis results.
"""

import csv
import io
import os
from typing import Any


class TableFormatter:
    """Table formatter for code analysis results"""

    def __init__(
        self,
        format_type: str = "full",
        language: str = "java",
        include_javadoc: bool = False,
    ):
        self.format_type = format_type
        self.language = language
        self.include_javadoc = include_javadoc

    def _get_platform_newline(self) -> str:
        """Get platform-specific newline character"""
        return os.linesep

    def _convert_to_platform_newlines(self, text: str) -> str:
        """Convert standard \\n to platform-specific newline characters"""
        if os.linesep != "\n":
            return text.replace("\n", os.linesep)
        return text

    def format_structure(self, structure_data: dict[str, Any]) -> str:
        """Format structure data as table"""
        if self.format_type == "full":
            result = self._format_full_table(structure_data)
        elif self.format_type == "compact":
            result = self._format_compact_table(structure_data)
        elif self.format_type == "csv":
            result = self._format_csv(structure_data)
        else:
            raise ValueError(f"Unsupported format type: {self.format_type}")

        # Finally convert to platform-specific newline characters
        # Skip newline conversion for CSV format (newline control is handled within _format_csv)
        if self.format_type == "csv":
            return result

        return self._convert_to_platform_newlines(result)

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format"""
        lines = []

        # Header - use filename when multiple classes exist
        classes = data.get("classes", [])
        if classes is None:
            classes = []
        if len(classes) > 1:
            # 複数クラスがある場合はファイル名を使用
            file_name = data.get("file_path", "Unknown").split("/")[-1].split("\\")[-1]
            lines.append(f"# {file_name}")
        else:
            # 単一クラスの場合は従来通り
            class_name = classes[0].get("name", "Unknown") if classes else "Unknown"
            lines.append(
                f"# {(data.get('package') or {}).get('name', 'unknown')}.{class_name}"
            )
        lines.append("")

        # Imports
        imports = data.get("imports", [])
        if imports:
            lines.append("## Imports")
            lines.append(f"```{self.language}")
            for imp in imports:
                lines.append(str(imp.get("statement", "")))
            lines.append("```")
            lines.append("")

        # Class Info - 複数クラスに対応
        classes = data.get("classes", [])
        if classes is None:
            classes = []
        if len(classes) > 1:
            lines.append("## Classes")
            lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
            lines.append("|-------|------|------------|-------|---------|--------|")

            for class_info in classes:
                name = str(class_info.get("name", "Unknown"))
                class_type = str(class_info.get("type", "class"))
                visibility = str(class_info.get("visibility", "public"))
                line_range = class_info.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                # このクラスのメソッド数とフィールド数を計算
                class_methods = [
                    m
                    for m in data.get("methods", [])
                    if line_range.get("start", 0)
                    <= m.get("line_range", {}).get("start", 0)
                    <= line_range.get("end", 0)
                ]
                class_fields = [
                    f
                    for f in data.get("fields", [])
                    if line_range.get("start", 0)
                    <= f.get("line_range", {}).get("start", 0)
                    <= line_range.get("end", 0)
                ]

                lines.append(
                    f"| {name} | {class_type} | {visibility} | {lines_str} | {len(class_methods)} | {len(class_fields)} |"
                )
        else:
            # 単一クラスの場合は従来通り
            lines.append("## Class Info")
            lines.append("| Property | Value |")
            lines.append("|----------|-------|")

            package_name = (data.get("package") or {}).get("name", "unknown")
            class_info = data.get("classes", [{}])[0] if data.get("classes") else {}
            stats = data.get("statistics") or {}

            lines.append(f"| Package | {package_name} |")
            lines.append(f"| Type | {str(class_info.get('type', 'class'))} |")
            lines.append(
                f"| Visibility | {str(class_info.get('visibility', 'public'))} |"
            )
            lines.append(
                f"| Lines | {class_info.get('line_range', {}).get('start', 0)}-{class_info.get('line_range', {}).get('end', 0)} |"
            )
            lines.append(f"| Total Methods | {stats.get('method_count', 0)} |")
            lines.append(f"| Total Fields | {stats.get('field_count', 0)} |")

        lines.append("")

        # Fields
        fields = data.get("fields", [])
        if fields is None:
            fields = []
        if fields:
            lines.append("## Fields")
            lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
            lines.append("|------|------|-----|-----------|------|-----|")

            for field in fields:
                name = str(field.get("name", ""))
                field_type = str(field.get("type", ""))
                visibility = self._convert_visibility(str(field.get("visibility", "")))
                modifiers = ",".join([str(m) for m in field.get("modifiers", [])])
                line = field.get("line_range", {}).get("start", 0)
                if self.include_javadoc:
                    doc = self._extract_doc_summary(str(field.get("javadoc", "")))
                else:
                    doc = "-"

                lines.append(
                    f"| {name} | {field_type} | {visibility} | {modifiers} | {line} | {doc} |"
                )
            lines.append("")

        # Constructor
        constructors = [
            m for m in (data.get("methods") or []) if m.get("is_constructor", False)
        ]
        if constructors:
            lines.append("## Constructor")
            lines.append("| Method | Signature | Vis | Lines | Cols | Cx | Doc |")
            lines.append("|--------|-----------|-----|-------|------|----|----|")

            for method in constructors:
                lines.append(self._format_method_row(method))
            lines.append("")

        # Public Methods
        public_methods = [
            m
            for m in (data.get("methods") or [])
            if not m.get("is_constructor", False)
            and str(m.get("visibility")) == "public"
        ]
        if public_methods:
            lines.append("## Public Methods")
            lines.append("| Method | Signature | Vis | Lines | Cols | Cx | Doc |")
            lines.append("|--------|-----------|-----|-------|------|----|----|")

            for method in public_methods:
                lines.append(self._format_method_row(method))
            lines.append("")

        # Private Methods
        private_methods = [
            m
            for m in (data.get("methods") or [])
            if not m.get("is_constructor", False)
            and str(m.get("visibility")) == "private"
        ]
        if private_methods:
            lines.append("## Private Methods")
            lines.append("| Method | Signature | Vis | Lines | Cols | Cx | Doc |")
            lines.append("|--------|-----------|-----|-------|------|----|----|")

            for method in private_methods:
                lines.append(self._format_method_row(method))
            lines.append("")

        # 末尾の空行を削除
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format"""
        lines = []

        # Header
        package_name = (data.get("package") or {}).get("name", "unknown")
        classes = data.get("classes", [])
        if classes is None:
            classes = []
        class_name = classes[0].get("name", "Unknown") if classes else "Unknown"
        lines.append(f"# {package_name}.{class_name}")
        lines.append("")

        # 基本情報
        stats = data.get("statistics") or {}
        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Package | {package_name} |")
        lines.append(f"| Methods | {stats.get('method_count', 0)} |")
        lines.append(f"| Fields | {stats.get('field_count', 0)} |")
        lines.append("")

        # メソッド（簡略版）
        methods = data.get("methods", [])
        if methods is None:
            methods = []
        if methods:
            lines.append("## Methods")
            lines.append("| Method | Sig | V | L | Cx | Doc |")
            lines.append("|--------|-----|---|---|----|----|")

            for method in methods:
                name = str(method.get("name", ""))
                signature = self._create_compact_signature(method)
                visibility = self._convert_visibility(str(method.get("visibility", "")))
                line_range = method.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                complexity = method.get("complexity_score", 0)
                doc = self._clean_csv_text(
                    self._extract_doc_summary(str(method.get("javadoc", "")))
                )

                lines.append(
                    f"| {name} | {signature} | {visibility} | {lines_str} | {complexity} | {doc} |"
                )
            lines.append("")

        # 末尾の空行を削除
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_csv(self, data: dict[str, Any]) -> str:
        """CSV format"""
        output = io.StringIO()
        writer = csv.writer(
            output, lineterminator="\n"
        )  # Explicitly specify newline character

        # Header
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

        # Completely control CSV output newlines
        csv_content = output.getvalue()
        # Unify all newline patterns and remove trailing newlines
        csv_content = csv_content.replace("\r\n", "\n").replace("\r", "\n")
        csv_content = csv_content.rstrip("\n")
        output.close()

        return csv_content

    def _format_method_row(self, method: dict[str, Any]) -> str:
        """メソッド行のフォーマット"""
        name = str(method.get("name", ""))
        signature = self._create_full_signature(method)
        visibility = self._convert_visibility(str(method.get("visibility", "")))
        line_range = method.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        cols_str = "5-6"  # デフォルト値（実際の実装では正確な値を取得）
        complexity = method.get("complexity_score", 0)
        if self.include_javadoc:
            doc = self._clean_csv_text(
                self._extract_doc_summary(str(method.get("javadoc", "")))
            )
        else:
            doc = "-"

        return f"| {name} | {signature} | {visibility} | {lines_str} | {cols_str} | {complexity} | {doc} |"

    def _create_full_signature(self, method: dict[str, Any]) -> str:
        """完全なメソッドシグネチャを作成"""
        params = method.get("parameters", [])
        param_strs = []
        for param in params:
            param_type = str(param.get("type", "Object"))
            param_name = str(param.get("name", "param"))
            param_strs.append(f"{param_name}:{param_type}")

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

    def _create_compact_signature(self, method: dict[str, Any]) -> str:
        """コンパクトなメソッドシグネチャを作成"""
        params = method.get("parameters", [])
        param_types = [self._shorten_type(p.get("type", "O")) for p in params]
        params_str = ",".join(param_types)
        return_type = self._shorten_type(method.get("return_type", "void"))

        return f"({params_str}):{return_type}"

    def _shorten_type(self, type_name: Any) -> str:
        """型名を短縮"""
        if type_name is None:
            return "O"

        # Convert non-string types to string
        if not isinstance(type_name, str):
            type_name = str(type_name)

        # At this point, type_name is guaranteed to be a string
        assert isinstance(type_name, str)

        type_mapping = {
            "String": "S",
            "int": "i",
            "long": "l",
            "double": "d",
            "boolean": "b",
            "void": "void",
            "Object": "O",
            "Exception": "E",
            "SQLException": "SE",
            "IllegalArgumentException": "IAE",
            "RuntimeException": "RE",
        }

        # Map<String,Object> -> M<S,O>
        if "Map<" in type_name:
            return (
                type_name.replace("Map<", "M<")
                .replace("String", "S")
                .replace("Object", "O")
            )

        # List<String> -> L<S>
        if "List<" in type_name:
            return type_name.replace("List<", "L<").replace("String", "S")

        # String[] -> S[]
        if "[]" in type_name:
            base_type = type_name.replace("[]", "")
            if base_type:
                return type_mapping.get(base_type, base_type[0].upper()) + "[]"
            else:
                return "O[]"

        return type_mapping.get(type_name, type_name)

    def _convert_visibility(self, visibility: str) -> str:
        """可視性を記号に変換"""
        mapping = {"public": "+", "private": "-", "protected": "#", "package": "~"}
        return mapping.get(visibility, visibility)

    def _extract_doc_summary(self, javadoc: str) -> str:
        """JavaDocから要約を抽出"""
        if not javadoc:
            return "-"

        # Remove comment symbols
        clean_doc = (
            javadoc.replace("/**", "").replace("*/", "").replace("*", "").strip()
        )

        # Get first line (use standard \\n only)
        lines = clean_doc.split("\n")
        first_line = lines[0].strip()

        # Truncate if too long
        if len(first_line) > 50:
            first_line = first_line[:47] + "..."

        # Escape characters that cause problems in Markdown tables (use standard \\n only)
        return first_line.replace("|", "\\|").replace("\n", " ")

    def _clean_csv_text(self, text: str) -> str:
        """Text cleaning for CSV format"""
        if not text:
            return ""

        # Replace all newline characters with spaces
        cleaned = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
        # Convert consecutive spaces to single space
        cleaned = " ".join(cleaned.split())
        # Escape characters that cause problems in CSV
        cleaned = cleaned.replace('"', '""')  # Escape double quotes

        return cleaned


def create_table_formatter(
    format_type: str, language: str = "java", include_javadoc: bool = False
) -> "TableFormatter":
    """Create table formatter (using new factory)"""
    # Create TableFormatter directly (for JavaDoc support)
    return TableFormatter(format_type, language, include_javadoc)
