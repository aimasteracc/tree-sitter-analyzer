#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Structure Command

Handles structure analysis functionality with appropriate Japanese output.
"""
from typing import TYPE_CHECKING

from ...output_manager import output_data, output_json, output_section
from .base_command import BaseCommand

if TYPE_CHECKING:
    from ...models import AnalysisResult


class StructureCommand(BaseCommand):
    """Command for structure analysis with Japanese output."""

    async def execute_async(self, language: str) -> int:
        analysis_result = await self.analyze_file(language)
        if not analysis_result:
            return 1

        self._output_structure_analysis(analysis_result)
        return 0

    def _output_structure_analysis(self, analysis_result: "AnalysisResult") -> None:
        """Output structure analysis results with appropriate Japanese header."""
        output_section("構造解析結果")
        
        # Convert to legacy structure format expected by tests
        structure_dict = self._convert_to_legacy_format(analysis_result)
        
        if self.args.output_format == "json":
            output_json(structure_dict)
        else:
            self._output_text_format(structure_dict)
    
    def _convert_to_legacy_format(self, analysis_result: "AnalysisResult") -> dict:
        """Convert AnalysisResult to legacy structure format expected by tests."""
        import time
        
        # Extract elements by type
        classes = [e for e in analysis_result.elements if e.__class__.__name__ == 'Class']
        methods = [e for e in analysis_result.elements if e.__class__.__name__ == 'Function']
        fields = [e for e in analysis_result.elements if e.__class__.__name__ == 'Variable']
        imports = [e for e in analysis_result.elements if e.__class__.__name__ == 'Import']
        packages = [e for e in analysis_result.elements if e.__class__.__name__ == 'Package']
        
        return {
            'file_path': analysis_result.file_path,
            'language': analysis_result.language,
            'package': {
                'name': packages[0].name,
                'line_range': {
                    'start': packages[0].start_line,
                    'end': packages[0].end_line
                }
            } if packages else None,
            'classes': [{'name': getattr(c, 'name', 'unknown')} for c in classes],
            'methods': [{'name': getattr(m, 'name', 'unknown')} for m in methods],
            'fields': [{'name': getattr(f, 'name', 'unknown')} for f in fields],
            'imports': [{
                'name': getattr(i, 'name', 'unknown'),
                'is_static': getattr(i, 'is_static', False),
                'is_wildcard': getattr(i, 'is_wildcard', False),
                'statement': getattr(i, 'import_statement', ''),
                'line_range': {
                    'start': getattr(i, 'start_line', 0),
                    'end': getattr(i, 'end_line', 0)
                }
            } for i in imports],
            'annotations': [],
            'statistics': {
                'class_count': len(classes),
                'method_count': len(methods),
                'field_count': len(fields),
                'import_count': len(imports),
                'total_lines': analysis_result.line_count,
                'annotation_count': 0
            },
            'analysis_metadata': {
                'analysis_time': getattr(analysis_result, 'analysis_time', 0.0),
                'language': analysis_result.language,
                'file_path': analysis_result.file_path,
                'analyzer_version': '2.0.0',
                'timestamp': time.time()
                         }
         }
    
    def _output_text_format(self, structure_dict: dict) -> None:
        """Output structure analysis in human-readable text format."""
        output_data(f"ファイル: {structure_dict['file_path']}")
        output_data(f"言語: {structure_dict['language']}")
        
        if structure_dict['package']:
            output_data(f"パッケージ: {structure_dict['package']['name']}")
        
        stats = structure_dict['statistics']
        output_data(f"統計:")
        output_data(f"  クラス数: {stats['class_count']}")
        output_data(f"  メソッド数: {stats['method_count']}")
        output_data(f"  フィールド数: {stats['field_count']}")
        output_data(f"  インポート数: {stats['import_count']}")
        output_data(f"  総行数: {stats['total_lines']}")
        
        if structure_dict['classes']:
            output_data("クラス:")
            for cls in structure_dict['classes']:
                output_data(f"  - {cls['name']}")
        
        if structure_dict['methods']:
            output_data("メソッド:")
            for method in structure_dict['methods']:
                output_data(f"  - {method['name']}")
        
        if structure_dict['fields']:
            output_data("フィールド:")
            for field in structure_dict['fields']:
                output_data(f"  - {field['name']}") 