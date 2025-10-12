
"""
サンプルフォーマッター実装例

このファイルは、新しいフォーマッターを実装する際の参考として使用できる
完全なサンプル実装です。複数の出力形式をサポートしています。
"""

from typing import Dict, List, Any, Optional
import json
import csv
import io
from abc import ABC, abstractmethod

from tree_sitter_analyzer.formatters.base import BaseFormatter
from tree_sitter_analyzer.models import (
    AnalysisResult, ModelFunction, ModelClass, ModelVariable, ModelImport
)


class EnhancedFormatter(BaseFormatter):
    """
    拡張フォーマッターのサンプル実装
    
    複数の出力形式と詳細なカスタマイズオプションをサポートします。
    """
    
    def __init__(self, format_type: str, **kwargs):
        """
        フォーマッターの初期化
        
        Args:
            format_type: 出力形式 ("table", "json", "csv", "markdown", "html")
            **kwargs: 追加オプション
        """
        super().__init__(format_type, **kwargs)
        
        # カスタマイズオプション
        self.options = {
            "include_metadata": kwargs.get("include_metadata", True),
            "include_docstrings": kwargs.get("include_docstrings", True),
            "include_line_numbers": kwargs.get("include_line_numbers", True),
            "include_visibility": kwargs.get("include_visibility", True),
            "max_line_length": kwargs.get("max_line_length", 100),
            "indent_size": kwargs.get("indent_size", 2),
            "sort_by": kwargs.get("sort_by", "name"),  # name, line, type
            "group_by": kwargs.get("group_by", None),  # type, visibility, module
            "filter_by": kwargs.get("filter_by", {}),  # 条件フィルタ
            "custom_fields": kwargs.get("custom_fields", []),  # 追加フィールド
        }
        
        # 統計情報
        self.stats = {
            "formatted_items": 0,
            "total_size": 0,
            "format_time": 0.0
        }
    
    def format_analysis_result(self, result: AnalysisResult) -> str:
        """
        解析結果全体をフォーマット
        
        Args:
            result: 解析結果
            
        Returns:
            str: フォーマット済み文字列
        """
        import time
        start_time = time.time()
        
        try:
            if self.format_type == "table":
                output = self._format_table(result)
            elif self.format_type == "json":
                output = self._format_json(result)
            elif self.format_type == "csv":
                output = self._format_csv(result)
            elif self.format_type == "markdown":
                output = self._format_markdown(result)
            elif self.format_type == "html":
                output = self._format_html(result)
            elif self.format_type == "xml":
                output = self._format_xml(result)
            else:
                raise ValueError(f"Unsupported format type: {self.format_type}")
            
            # 統計更新
            self.stats["formatted_items"] += 1
            self.stats["total_size"] += len(output)
            self.stats["format_time"] += time.time() - start_time
            
            return output
            
        except Exception as e:
            raise Exception(f"Formatting failed: {str(e)}")
    
    def _format_table(self, result: AnalysisResult) -> str:
        """テーブル形式でのフォーマット"""
        lines = []
        
        # ヘッダー情報
        lines.append(f"📁 ファイル: {result.file_path}")
        lines.append(f"🔤 言語: {result.language}")
        lines.append("=" * 80)
        
        # 関数セクション
        if result.functions:
            lines.append("\n🔧 関数一覧")
            lines.append("-" * 40)
            
            # ソート
            functions = self._sort_items(result.functions)
            
            # テーブルヘッダー
            headers = ["名前", "可視性", "パラメータ", "戻り値", "行番号"]
            if self.options["include_docstrings"]:
                headers.append("説明")
            
            # カラム幅の計算
            col_widths = self._calculate_column_widths(functions, headers)
            
            # ヘッダー行
            header_line = " | ".join(h.ljust(w) for h, w in zip(headers, col_widths))
            lines.append(header_line)
            lines.append("-" * len(header_line))
            
            # データ行
            for func in functions:
                if self._should_include_item(func):
                    row = self._format_function_row(func, col_widths)
                    lines.append(row)
        
        # クラスセクション
        if result.classes:
            lines.append("\n📦 クラス一覧")
            lines.append("-" * 40)
            
            classes = self._sort_items(result.classes)
            
            for cls in classes:
                if self._should_include_item(cls):
                    lines.append(self._format_class_summary(cls))
        
        # 変数セクション
        if result.variables:
            lines.append("\n📊 変数一覧")
            lines.append("-" * 40)
            
            variables = self._sort_items(result.variables)
            
            for var in variables:
                if self._should_include_item(var):
                    lines.append(self._format_variable_summary(var))
        
        # インポートセクション
        if result.imports:
            lines.append("\n📥 インポート一覧")
            lines.append("-" * 40)
            
            for imp in result.imports:
                lines.append(self._format_import_summary(imp))
        
        # 統計情報
        if self.options["include_metadata"]:
            lines.append("\n📈 統計情報")
            lines.append("-" * 40)
            lines.append(f"関数数: {len(result.functions)}")
            lines.append(f"クラス数: {len(result.classes)}")
            lines.append(f"変数数: {len(result.variables)}")
            lines.append(f"インポート数: {len(result.imports)}")
            
            if result.metadata:
                for key, value in result.metadata.items():
                    lines.append(f"{key}: {value}")
        
        return "\n".join(lines)
    
    def _format_json(self, result: AnalysisResult) -> str:
        """JSON形式でのフォーマット"""
        data = {
            "file_path": result.file_path,
            "language": result.language,
            "summary": {
                "functions": len(result.functions),
                "classes": len(result.classes),
                "variables": len(result.variables),
                "imports": len(result.imports)
            }
        }
        
        # 詳細データ
        if result.functions:
            data["functions"] = [self._function_to_dict(f) for f in result.functions 
                               if self._should_include_item(f)]
        
        if result.classes:
            data["classes"] = [self._class_to_dict(c) for c in result.classes 
                             if self._should_include_item(c)]
        
        if result.variables:
            data["variables"] = [self._variable_to_dict(v) for v in result.variables 
                               if self._should_include_item(v)]
        
        if result.imports:
            data["imports"] = [self._import_to_dict(i) for i in result.imports]
        
        # メタデータ
        if self.options["include_metadata"] and result.metadata:
            data["metadata"] = result.metadata
        
        return json.dumps(data, indent=self.options["indent_size"], ensure_ascii=False)
    
    def _format_csv(self, result: AnalysisResult) -> str:
        """CSV形式でのフォーマット"""
        output = io.StringIO()
        
        # 関数のCSV
        if result.functions:
            writer = csv.writer(output)
            
            # ヘッダー
            headers = ["type", "name", "visibility", "parameters", "return_type", 
                      "start_line", "end_line", "is_method"]
            if self.options["include_docstrings"]:
                headers.append("docstring")
            
            writer.writerow(headers)
            
            # データ
            for func in result.functions:
                if self._should_include_item(func):
                    row = [
                        "function",
                        func.name,
                        func.visibility or "",
                        "; ".join(func.parameters) if func.parameters else "",
                        func.return_type or "",
                        func.start_line,
                        func.end_line,
                        func.is_method
                    ]
                    
                    if self.options["include_docstrings"]:
                        row.append(func.docstring or "")
                    
                    writer.writerow(row)
        
        # クラスのCSV
        if result.classes:
            for cls in result.classes:
                if self._should_include_item(cls):
                    row = [
                        "class",
                        cls.name,
                        cls.visibility or "",
                        "; ".join(cls.base_classes) if cls.base_classes else "",
                        "",  # return_type (N/A for classes)
                        cls.start_line,
                        cls.end_line,
                        False  # is_method (N/A for classes)
                    ]
                    
                    if self.options["include_docstrings"]:
                        row.append(cls.docstring or "")
                    
                    writer.writerow(row)
        
        return output.getvalue()
    
    def _format_markdown(self, result: AnalysisResult) -> str:
        """Markdown形式でのフォーマット"""
        lines = []
        
        # タイトル
        lines.append(f"# 解析結果: {result.file_path}")
        lines.append(f"**言語**: {result.language}")
        lines.append("")
        
        # 目次
        lines.append("## 目次")
        if result.functions:
            lines.append("- [関数一覧](#関数一覧)")
        if result.classes:
            lines.append("- [クラス一覧](#クラス一覧)")
        if result.variables:
            lines.append("- [変数一覧](#変数一覧)")
        if result.imports:
            lines.append("- [インポート一覧](#インポート一覧)")
        lines.append("")
        
        # 関数セクション
        if result.functions:
            lines.append("## 関数一覧")
            lines.append("")
            
            functions = self._sort_items(result.functions)
            
            for func in functions:
                if self._should_include_item(func):
                    lines.extend(self._format_function_markdown(func))
                    lines.append("")
        
        # クラスセクション
        if result.classes:
            lines.append("## クラス一覧")
            lines.append("")
            
            classes = self._sort_items(result.classes)
            
            for cls in classes:
                if self._should_include_item(cls):
                    lines.extend(self._format_class_markdown(cls))
                    lines.append("")
        
        # 変数セクション
        if result.variables:
            lines.append("## 変数一覧")
            lines.append("")
            
            variables = self._sort_items(result.variables)
            
            lines.append("| 名前 | 型 | 可視性 | 行番号 |")
            lines.append("|------|----|---------|---------| ")
            
            for var in variables:
                if self._should_include_item(var):
                    lines.append(self._format_variable_markdown_row(var))
            
            lines.append("")
        
        # インポートセクション
        if result.imports:
            lines.append("## インポート一覧")
            lines.append("")
            
            for imp in result.imports:
                lines.append(f"- `{imp.module}`: {', '.join(imp.names) if imp.names else '*'}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_html(self, result: AnalysisResult) -> str:
        """HTML形式でのフォーマット"""
        html_parts = []
        
        # HTMLヘッダー
        html_parts.append("""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>解析結果</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background-color: #f5f5f5; padding: 10px; border-radius: 5px; }
        .section { margin: 20px 0; }
        .function, .class { border: 1px solid #ddd; margin: 10px 0; padding: 10px; border-radius: 5px; }
        .function-name, .class-name { font-weight: bold; color: #0066cc; }
        .visibility { color: #666; font-size: 0.9em; }
        .line-number { color: #999; font-size: 0.8em; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        .docstring { font-style: italic; color: #666; margin-top: 5px; }
    </style>
</head>
<body>
        """)
        
        # ヘッダー情報
        html_parts.append(f"""
    <div class="header">
        <h1>解析結果: {result.file_path}</h1>
        <p><strong>言語:</strong> {result.language}</p>
        <p><strong>統計:</strong> 関数 {len(result.functions)}, クラス {len(result.classes)}, 変数 {len(result.variables)}</p>
    </div>
        """)
        
        # 関数セクション
        if result.functions:
            html_parts.append('<div class="section">')
            html_parts.append('<h2>関数一覧</h2>')
            
            functions = self._sort_items(result.functions)
            
            for func in functions:
                if self._should_include_item(func):
                    html_parts.append(self._format_function_html(func))
            
            html_parts.append('</div>')
        
        # クラスセクション
        if result.classes:
            html_parts.append('<div class="section">')
            html_parts.append('<h2>クラス一覧</h2>')
            
            classes = self._sort_items(result.classes)
            
            for cls in classes:
                if self._should_include_item(cls):
                    html_parts.append(self._format_class_html(cls))
            
            html_parts.append('</div>')
        
        # HTMLフッター
        html_parts.append("""
</body>
</html>
        """)
        
        return "".join(html_parts)
    
    def _format_xml(self, result: AnalysisResult) -> str:
        """XML形式でのフォーマット"""
        from xml.etree.ElementTree import Element, SubElement, tostring
        from xml.dom import minidom
        
        # ルート要素
        root = Element("analysis_result")
        root.set("file_path", result.file_path)
        root.set("language", result.language)
        
        # 関数
        if result.functions:
            functions_elem = SubElement(root, "functions")
            
            for func in result.functions:
                if self._should_include_item(func):
                    func_elem = SubElement(functions_elem, "function")
                    func_elem.set("name", func.name)
                    func_elem.set("visibility", func.visibility or "")
                    func_elem.set("start_line", str(func.start_line))
                    func_elem.set("end_line", str(func.end_line))
                    func_elem.set("is_method", str(func.is_method))
                    
                    if func.parameters:
                        params_elem = SubElement(func_elem, "parameters")
                        for param in func.parameters:
                            param_elem = SubElement(params_elem, "parameter")
                            param_elem.text = param
                    
                    if func.docstring:
                        doc_elem = SubElement(func_elem, "docstring")
                        doc_elem.text = func.docstring
        
        # クラス
        if result.classes:
            classes_elem = SubElement(root, "classes")
            
            for cls in result.classes:
                if self._should_include_item(cls):
                    cls_elem = SubElement(classes_elem, "class")
                    cls_elem.set("name", cls.name)
                    cls_elem.set("visibility", cls.visibility or "")
                    cls_elem.set("start_line", str(cls.start_line))
                    cls_elem.set("end_line", str(cls.end_line))
                    
                    if cls.base_classes:
                        bases_elem = SubElement(cls_elem, "base_classes")
                        for base in cls.base_classes:
                            base_elem = SubElement(bases_elem, "base_class")
                            base_elem.text = base
        
        # XMLを整形
        rough_string = tostring(root, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")
    
    def _sort_items(self, items: List[Any]) -> List[Any]:
        """アイテムをソート"""
        sort_by = self.options["sort_by"]
        
        if sort_by == "name":
            return sorted(items, key=lambda x: x.name.lower())
        elif sort_by == "line":
            return sorted(items, key=lambda x: x.start_line)
        elif sort_by == "type":
            return sorted(items, key=lambda x: type(x).__name__)
        else:
            return items
    
    def _should_include_item(self, item: Any) -> bool:
        """アイテムを含めるかどうかを判定"""
        filters = self.options["filter_by"]
        
        if not filters:
            return True
        
        # 可視性フィルタ
        if "visibility" in filters:
            if hasattr(item, 'visibility') and item.visibility not in filters["visibility"]:
                return False
        
        # 名前フィルタ
        if "name_pattern" in filters:
            import re
            pattern = filters["name_pattern"]
            if not re.search(pattern, item.name):
                return False
        
        # 行番号フィルタ
        if "line_range" in filters:
            start, end = filters["line_range"]
            if not (start <= item.start_line <= end):
                return False
        
        return True
    
    def _calculate_column_widths(self, items: List[Any], headers: List[str]) -> List[int]:
        """テーブルのカラム幅を計算"""
        widths = [len(h) for h in headers]
        
        for item in items:
            if hasattr(item, 'name'):
                widths[0] = max(widths[0], len(item.name))
            if hasattr(item, 'visibility'):
                widths[1] = max(widths[1], len(item.visibility or ""))
        
        return widths
    
    def _format_function_row(self, func: ModelFunction, col_widths: List[int]) -> str:
        """関数のテーブル行をフォーマット"""
        name = func.name.ljust(col_widths[0])
        visibility = (func.visibility or "").ljust(col_widths[1])
        params = (", ".join(func.parameters[:2]) + ("..." if len(func.parameters) > 2 else "")).ljust(col_widths[2])
        return_type = (func.return_type or "").ljust(col_widths[3])
        line_info = f"{func.start_line}-{func.end_line}".ljust(col_widths[4])
        
        row = f"{name} | {visibility} | {params} | {return_type} | {line_info}"
        
        if self.options["include_docstrings"] and len(col_widths) > 5:
            docstring = (func.docstring or "")[:50] + ("..." if len(func.docstring or "") > 50 else "")
            row += f" | {docstring.ljust(col_widths[5])}"
        
        return row
    
    def _format_class_summary(self, cls: ModelClass) -> str:
        """クラスの要約をフォーマット"""
        base_info = f" extends {', '.join(cls.base_classes)}" if cls.base_classes else ""
        return f"📦 {cls.name}{base_info} ({cls.start_line}-{cls.end_line}) [{cls.visibility or 'default'}]"
    
    def _format_variable_summary(self, var: ModelVariable) -> str:
        """変数の要約をフォーマット"""
        type_info = f": {var.type_annotation}" if var.type_annotation else ""
        return f"📊 {var.name}{type_info} ({var.start_line}) [{var.visibility or 'default'}]"
    
    def _format_import_summary(self, imp: ModelImport) -> str:
        """インポートの要約をフォーマット"""
        names = ", ".join(imp.names) if imp.names else "*"
        alias = f" as {imp.alias}" if imp.alias else ""
        return f"📥 from {imp.module} import {names}{alias}"
    
    def _function_to_dict(self, func: ModelFunction) -> Dict[str, Any]:
        """関数を辞書に変換"""
        data = {
            "name": func.name,
            "start_line": func.start_line,
            "end_line": func.end_line,
            "is_method": func.is_method,
            "is_async": func.is_async
        }
        
        if self.options["include_visibility"]:
            data["visibility"] = func.visibility
        
        if func.parameters:
            data["parameters"] = func.parameters
        
        if func.return_type:
            data["return_type"] = func.return_type
        
        if self.options["include_docstrings"] and func.docstring:
            data["docstring"] = func.docstring
        
        if self.options["include_metadata"] and func.metadata:
            data["metadata"] = func.metadata
        
        return data
    
    def _class_to_dict(self, cls: ModelClass) -> Dict[str, Any]:
        """クラスを辞書に変換"""
        data = {
            "name": cls.name,
            "start_line": cls.start_line,
            "end_line": cls.end_line,
            "is_abstract": cls.is_abstract
        }
        
        if self.options["include_visibility"]:
            data["visibility"] = cls.visibility
        
        if cls.base_classes:
            data["base_classes"] = cls.base_classes
        
        if cls.methods:
            data["methods"] = [self._function_to_dict(m) for m in cls.methods]
        
        if cls.fields:
            data["fields"] = cls.fields
        
        if self.options["include_docstrings"] and cls.docstring:
            data["docstring"] = cls.docstring
        
        if self.options["include_metadata"] and cls.metadata:
            data["metadata"] = cls.metadata
        
        return data
    
    def _variable_to_dict(self, var: ModelVariable) -> Dict[str, Any]:
        """変数を辞書に変換"""
        data = {
            "name": var.name,
            "start_line": var.start_line,
            "end_line": var.end_line,
            "is_constant": var.is_constant
        }
        
        if self.options["include_visibility"]:
            data["visibility"] = var.visibility
        
        if var.type_annotation:
            data["type_annotation"] = var.type_annotation
        
        if var.default_value:
            data["default_value"] = var.default_value
        
        if self.options["include_metadata"] and var.metadata:
            data["metadata"] = var.metadata
        
        return data
    
    def _import_to_dict(self, imp: ModelImport) -> Dict[str, Any]:
        """インポートを辞書に変換"""
        data = {
            "module": imp.module,
            "start_line": imp.start_line,
            "end_line": imp.end_line,
            "is_wildcard": imp.is_wildcard
        }
        
        if imp.names:
            data["names"] = imp.names
        
        if imp.alias:
            data["alias"] = imp.alias
        
        if self.options["include_metadata"] and imp.metadata:
            data["metadata"] = imp.metadata
        
        return data
    
    def _format_function_markdown(self, func: ModelFunction) -> List[str]:
        """関数のMarkdown形式"""
        lines = []
        
        # 関数シグネチャ
        visibility = f"`{func.visibility}` " if func.visibility else ""
        async_marker = "`async` " if func.is_async else ""
        method_marker = " *(method)*" if func.is_method else ""
        
        lines.append(f"### {visibility}{async_marker}`{func.name}`{method_marker}")
        
        # 位置情報
        if self.options["include_line_numbers"]:
            lines.append(f"**位置**: {func.start_line}-{func.end_line}行")
        
        # パラメータ
        if func.parameters:
            lines.append(f"**パラメータ**: `{', '.join(func.parameters)}`")
        
        # 戻り値
        if func.return_type:
            lines.append(f"**戻り値**: `{func.return_type}`")
        
        # ドキュメント
        if self.options["include_docstrings"] and func.docstring:
            lines.append(f"**説明**: {func.docstring}")
        
        return lines
    
    def _format_class_markdown(self, cls: ModelClass) -> List[str]:
        """クラスのMarkdown形式"""
        lines = []
        
        # クラス名
        visibility = f"`{cls.visibility}` " if cls.visibility else ""
        abstract_marker = "`abstract` " if cls.is_abstract else ""
        
        lines.append(f"### {visibility}{abstract_marker}`{cls.name}`")
        
        # 位置情報
        if self.options["include_line_numbers"]:
            lines.append(f"**位置**: {cls.start_line}-{cls.end_line}行")
        
        # 継承
        if cls.base_classes:
            lines.append(f"**継承**: `{', '.join(cls.base_classes)}`")
        
        # メソッド数
        if cls.methods:
            lines.append(f"**メソッド数**: {len(cls.methods)}")
        
        # フィールド数
        if cls.fields:
            lines.append(f"**フィールド数**: {len(cls.fields)}")
        
        # ドキュメント
        if self.options["include_docstrings"] and cls.docstring:
            lines.append(f"**説明**: {cls.docstring}")
        
        return lines
    
    def _format_variable_markdown_row(self, var: ModelVariable) -> str:
        """変数のMarkdownテーブル行"""
        name = f"`{var.name}`"
        type_info = f"`{var.type_annotation}`" if var.type_annotation else "不明"
        visibility = var.visibility or "default"
        line_info = f"{var.start_line}"
        
        return f"| {name} | {type_info} | {visibility} | {line_info} |"
    
    def _format_function_html(self, func: ModelFunction) -> str:
        """関数のHTML形式"""
        visibility_class = f"visibility-{func.visibility}" if func.visibility else ""
        
        html = f'''
    <div class="function {visibility_class}">
        <div class="function-name">{func.name}</div>
        <div class="visibility">{func.visibility or 'default'}</div>
        <div class="line-number">行 {func.start_line}-{func.end_line}</div>
        '''
        
        if func.parameters:
            html += f'<div class="parameters"><strong>パラメータ:</strong> {", ".join(func.parameters)}</div>'
        
        if func.return_type:
            html += f'<div class="return-type"><strong>戻り値:</strong> {func.return_type}</div>'
        
        if self.options["include_docstrings"] and func.docstring:
            html += f'<div class="docstring">{func.docstring}</div>'
        
        html += '</div>'
        
        return html
    
    def _format_class_html(self, cls: ModelClass) -> str:
        """クラスのHTML形式"""
        visibility_class = f"visibility-{cls.visibility}" if cls.visibility else ""
        
        html = f'''
    <div class="class {visibility_class}">
        <div class="class-name">{cls.name}</div>
        <div class="visibility">{cls.visibility or 'default'}</div>
        <div class="line-number">行 {cls.start_line}-{cls.end_line}</div>
        '''
        
        if cls.base_classes:
            html += f'<div class="inheritance"><strong>継承:</strong> {", ".join(cls.base_classes)}</div>'
        
        if cls.methods:
            html += f'<div class="methods"><strong>メソッド数:</strong> {len(cls.methods)}</div>'
        
        if self.options["include_docstrings"] and cls.docstring:
            html += f'<div class="docstring">{cls.docstring}</div>'
        
        html += '</div>'
        
        return html
    
    def get_statistics(self) -> Dict[str, Any]:
        """フォーマッター統計を取得"""
        return self.stats.copy()
    
    def reset_statistics(self):
        """統計をリセット"""
        self.stats = {
            "formatted_items": 0,
            "total_size": 0,
            "format_time": 0.0
        }


# 使用例とテスト
if __name__ == "__main__":
    # サンプルデータの作成
    from tree_sitter_analyzer.models import AnalysisResult, ModelFunction, ModelClass
    
    # サンプル関数
    sample_function = ModelFunction(
        name="calculate_sum",
        start_line=10,
        end_line=15,
        start_column=0,
        end_column=20,
        docstring="数値のリストの合計を計算します",
        parameters=["numbers: List[int]"],
        return_type="int",
        is_async=False,
        is_method=False,
        visibility="public",
        metadata={}
    )
    
    # サンプルクラス
    sample_class = ModelClass(
        name="Calculator",
        start_line=20,
        end_line=40,
        start_column=0,
        end_column=10,
        docstring="計算機クラス",
        methods=[sample_function],
        fields=["value: int"],
        base_classes=[],
        is_abstract=False,
        visibility="public",
        metadata={}
    )
    
    # サンプル解析結果
    sample_result = AnalysisResult(
        file_path="sample.py",
        language="python",
        functions=[sample_function],
        classes=[sample_class],
        variables=[],
        imports=[],
        metadata={"parse_time": 0.1, "file_size": 1024}
    )
    
    # 各フォーマットのテスト
    formats = ["table", "json", "csv", "markdown", "html"]
    
    for format_type in formats:
        print(f"\n{'='*50}")
        print(f"フォーマット: {format_type}")
        print(f"{'='*50}")
        
        formatter = EnhancedFormatter(
            format_type,
            include_metadata=True,
            include_docstrings=True,
            include_line_numbers=True
        )
        
        try:
            output = formatter.format_analysis_result(sample_result)
            
            if format_type in ["json", "html", "xml"]:
                # 長い出力は最初の500文字のみ表示
                if len(output) > 500:
                    print(output[:500] + "\n... (truncated)")
                else:
                    print(output)
            else:
                print(output)
            
            # 統計情報
            stats = formatter.get_statistics()
            print(f"\n統計: {stats}")
            
        except Exception as e:
            print(f"エラー: {str(e)}")
    
    print(f"\n{'='*50}")
    print("フォーマッターテスト完了")
    print(f"{'='*50}")