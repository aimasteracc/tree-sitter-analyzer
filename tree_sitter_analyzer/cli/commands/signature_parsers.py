#!/usr/bin/env python3
"""
Signature Parsers

言語別のメソッド/関数シグネチャ解析を行うパーサーモジュール
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import re


class SignatureParser(ABC):
    """シグネチャパーサーの抽象基底クラス"""
    
    @abstractmethod
    def parse_signature(self, content: str, capture_name: str) -> Dict[str, Any]:
        """
        コンテンツからシグネチャ情報を解析
        
        Args:
            content: QueryServiceから取得した要素の生テキスト
            capture_name: キャプチャ名（method, function等）
            
        Returns:
            {
                'name': str,
                'parameters': [{'name': str, 'type': str}],
                'return_type': str,
                'modifiers': [str],
                'visibility': str,
                'is_static': bool,
                'is_async': bool
            }
        """
        pass
    
    @abstractmethod
    def supports_language(self, language: str) -> bool:
        """指定された言語をサポートするかどうか"""
        pass


class JavaSignatureParser(SignatureParser):
    """Java用シグネチャパーサー"""
    
    def supports_language(self, language: str) -> bool:
        return language.lower() == "java"
    
    def parse_signature(self, content: str, capture_name: str) -> Dict[str, Any]:
        """Javaメソッドシグネチャを解析"""
        # デフォルト値
        result = {
            'name': 'unknown',
            'parameters': [],
            'return_type': 'void',
            'modifiers': [],
            'visibility': 'public',
            'is_static': False,
            'is_async': False
        }
        
        try:
            # コンテンツをクリーンアップ
            content = content.strip()
            if not content:
                return result
            
            # 複数行の場合は最初の行のみを使用（メソッド宣言行）
            first_line = content.split('\n')[0].strip()
            
            # Javaメソッドシグネチャの正規表現パターン
            method_pattern = r'''
                (?P<modifiers>(?:public|private|protected|static|final|abstract|synchronized|native|strictfp|\s)+)?\s*
                (?P<return_type>[\w\[\]<>.,\s?]+?)\s+
                (?P<method_name>\w+)\s*
                \(\s*(?P<parameters>[^)]*)\s*\)
            '''
            
            match = re.search(method_pattern, first_line, re.VERBOSE)
            
            if match:
                # メソッド名
                result['name'] = match.group('method_name')
                
                # 戻り値型
                return_type = match.group('return_type')
                if return_type:
                    result['return_type'] = return_type.strip()
                
                # 修飾子
                modifiers_str = match.group('modifiers')
                if modifiers_str:
                    modifiers = [m.strip() for m in modifiers_str.split() if m.strip()]
                    result['modifiers'] = modifiers
                    
                    # 可視性とstatic判定
                    for modifier in modifiers:
                        if modifier in ["public", "private", "protected"]:
                            result['visibility'] = modifier
                        elif modifier == "static":
                            result['is_static'] = True
                
                # パラメータ
                params_str = match.group('parameters')
                if params_str and params_str.strip():
                    result['parameters'] = self._parse_java_parameters(params_str.strip())
            else:
                # フォールバック: 既存のメソッド名抽出ロジックを使用
                result['name'] = self._extract_java_method_name(content)
                
                # 簡単なパラメータ抽出を試行
                param_match = re.search(r'\(([^)]*)\)', first_line)
                if param_match:
                    params_str = param_match.group(1).strip()
                    if params_str:
                        result['parameters'] = self._parse_java_parameters(params_str)
                
                # 簡単な戻り値型抽出を試行
                return_type_match = re.search(r'(\w+(?:<[^>]*>)?(?:\[\])*)\s+\w+\s*\(', first_line)
                if return_type_match:
                    result['return_type'] = return_type_match.group(1)
                    
        except Exception as e:
            # エラーが発生した場合はデフォルト値を返す
            pass
            
        return result
    
    def _parse_java_parameters(self, params_str: str) -> List[Dict[str, str]]:
        """Javaパラメータ文字列を解析"""
        parameters = []
        if not params_str.strip():
            return parameters
            
        try:
            # パラメータを分割（カンマで区切られているが、ジェネリック型内のカンマは除外）
            param_parts = []
            current_param = ""
            bracket_depth = 0
            
            for char in params_str:
                if char == '<':
                    bracket_depth += 1
                elif char == '>':
                    bracket_depth -= 1
                elif char == ',' and bracket_depth == 0:
                    if current_param.strip():
                        param_parts.append(current_param.strip())
                    current_param = ""
                    continue
                current_param += char
            
            # 最後のパラメータを追加
            if current_param.strip():
                param_parts.append(current_param.strip())
            
            # 各パラメータを解析
            for param in param_parts:
                param = param.strip()
                if not param:
                    continue
                    
                # パラメータパターン: [final] 型 変数名
                param_pattern = r'(?:final\s+)?(?P<type>[\w\[\]<>.,\s?]+?)\s+(?P<name>\w+)(?:\s*=\s*[^,]*)?'
                match = re.search(param_pattern, param)
                
                if match:
                    param_type = match.group('type').strip()
                    param_name = match.group('name').strip()
                    parameters.append({'name': param_name, 'type': param_type})
                else:
                    # フォールバック: 最後の単語を変数名、残りを型とする
                    parts = param.split()
                    if len(parts) >= 2:
                        param_name = parts[-1]
                        param_type = ' '.join(parts[:-1])
                        parameters.append({'name': param_name, 'type': param_type})
                    elif len(parts) == 1:
                        # 型のみの場合
                        parameters.append({'name': 'param', 'type': parts[0]})
                        
        except Exception as e:
            # エラーが発生した場合は空のリストを返す
            pass
            
        return parameters
    
    def _extract_java_method_name(self, content: str) -> str:
        """Java メソッド宣言から名前を抽出"""
        # Java メソッド宣言パターン: [修飾子] 戻り値型 メソッド名(引数)
        pattern = r'(?:public|private|protected|static|\s)*\s*\w+\s+(\w+)\s*\('
        match = re.search(pattern, content)
        if match:
            return match.group(1)
        
        # フォールバック: 括弧の前の単語を取得
        pattern = r'(\w+)\s*\('
        match = re.search(pattern, content)
        return match.group(1) if match else content.split()[0] if content.strip() else "unknown"


class JavaScriptSignatureParser(SignatureParser):
    """JavaScript/TypeScript用シグネチャパーサー"""
    
    def supports_language(self, language: str) -> bool:
        return language.lower() in ["javascript", "typescript", "js", "ts"]
    
    def parse_signature(self, content: str, capture_name: str) -> Dict[str, Any]:
        """JavaScript/TypeScriptメソッドシグネチャを解析"""
        result = {
            'name': 'unknown',
            'parameters': [],
            'return_type': 'any',
            'modifiers': [],
            'visibility': 'public',
            'is_static': False,
            'is_async': False
        }
        
        try:
            content = content.strip()
            if not content:
                return result
            
            first_line = content.split('\n')[0].strip()
            
            # async判定
            if 'async' in first_line:
                result['is_async'] = True
            
            # 関数名とパラメータを抽出
            # function 宣言: function functionName(params)
            function_pattern = r'(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)'
            match = re.search(function_pattern, first_line)
            
            if match:
                result['name'] = match.group(1)
                params_str = match.group(2).strip()
                if params_str:
                    result['parameters'] = self._parse_js_parameters(params_str)
            else:
                # アロー関数: const functionName = (params) =>
                arrow_pattern = r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>'
                match = re.search(arrow_pattern, first_line)
                
                if match:
                    result['name'] = match.group(1)
                    params_str = match.group(2).strip()
                    if params_str:
                        result['parameters'] = self._parse_js_parameters(params_str)
                else:
                    # メソッド宣言: methodName(params)
                    method_pattern = r'(?:async\s+)?(\w+)\s*\(([^)]*)\)'
                    match = re.search(method_pattern, first_line)
                    if match:
                        result['name'] = match.group(1)
                        params_str = match.group(2).strip()
                        if params_str:
                            result['parameters'] = self._parse_js_parameters(params_str)
                    
        except Exception as e:
            pass
            
        return result
    
    def _parse_js_parameters(self, params_str: str) -> List[Dict[str, str]]:
        """JavaScript/TypeScriptパラメータ文字列を解析"""
        parameters = []
        if not params_str.strip():
            return parameters
            
        try:
            # 簡単な分割（TypeScriptの型注釈も考慮）
            param_parts = [p.strip() for p in params_str.split(',') if p.strip()]
            
            for param in param_parts:
                # TypeScript型注釈: param: type
                if ':' in param:
                    parts = param.split(':', 1)
                    param_name = parts[0].strip()
                    param_type = parts[1].strip() if len(parts) > 1 else 'any'
                    parameters.append({'name': param_name, 'type': param_type})
                else:
                    # JavaScript: param
                    parameters.append({'name': param, 'type': 'any'})
                    
        except Exception as e:
            pass
            
        return parameters


class PythonSignatureParser(SignatureParser):
    """Python用シグネチャパーサー"""
    
    def supports_language(self, language: str) -> bool:
        return language.lower() == "python"
    
    def parse_signature(self, content: str, capture_name: str) -> Dict[str, Any]:
        """Pythonメソッドシグネチャを解析"""
        result = {
            'name': 'unknown',
            'parameters': [],
            'return_type': 'Any',
            'modifiers': [],
            'visibility': 'public',
            'is_static': False,
            'is_async': False
        }
        
        try:
            content = content.strip()
            if not content:
                return result
            
            first_line = content.split('\n')[0].strip()
            
            # async判定
            if first_line.startswith('async def'):
                result['is_async'] = True
            
            # 関数定義パターン: def function_name(params) -> return_type:
            func_pattern = r'(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)(?:\s*->\s*([^:]+))?:'
            match = re.search(func_pattern, first_line)
            
            if match:
                result['name'] = match.group(1)
                
                # パラメータ
                params_str = match.group(2).strip()
                if params_str:
                    result['parameters'] = self._parse_python_parameters(params_str)
                
                # 戻り値型
                return_type = match.group(3)
                if return_type:
                    result['return_type'] = return_type.strip()
                    
                # 可視性判定（Pythonの慣例）
                if result['name'].startswith('__'):
                    result['visibility'] = 'private'
                elif result['name'].startswith('_'):
                    result['visibility'] = 'protected'
                    
        except Exception as e:
            pass
            
        return result
    
    def _parse_python_parameters(self, params_str: str) -> List[Dict[str, str]]:
        """Pythonパラメータ文字列を解析"""
        parameters = []
        if not params_str.strip():
            return parameters
            
        try:
            # 簡単な分割（型ヒントも考慮）
            param_parts = [p.strip() for p in params_str.split(',') if p.strip()]
            
            for param in param_parts:
                # selfやclsをスキップ
                if param in ['self', 'cls']:
                    continue
                    
                # 型ヒント: param: type
                if ':' in param:
                    parts = param.split(':', 1)
                    param_name = parts[0].strip()
                    param_type = parts[1].strip() if len(parts) > 1 else 'Any'
                    # デフォルト値を除去
                    if '=' in param_type:
                        param_type = param_type.split('=')[0].strip()
                    parameters.append({'name': param_name, 'type': param_type})
                else:
                    # 型ヒントなし: param
                    param_name = param.split('=')[0].strip()  # デフォルト値を除去
                    parameters.append({'name': param_name, 'type': 'Any'})
                    
        except Exception as e:
            pass
            
        return parameters


class DefaultSignatureParser(SignatureParser):
    """デフォルト（汎用）シグネチャパーサー"""
    
    def supports_language(self, language: str) -> bool:
        return True  # 全ての言語をサポート（フォールバック）
    
    def parse_signature(self, content: str, capture_name: str) -> Dict[str, Any]:
        """汎用シグネチャ解析（従来の動作）"""
        return {
            'name': self._extract_generic_name(content),
            'parameters': [],
            'return_type': None,
            'modifiers': [],
            'visibility': 'public',
            'is_static': False,
            'is_async': False
        }
    
    def _extract_generic_name(self, content: str) -> str:
        """汎用的な名前抽出"""
        # 最初の単語を返す
        return content.split()[0] if content.strip() else "unknown"


class SignatureParserFactory:
    """シグネチャパーサーファクトリー"""
    
    def __init__(self):
        self._parsers = [
            JavaSignatureParser(),
            JavaScriptSignatureParser(),
            PythonSignatureParser(),
            DefaultSignatureParser(),  # 最後にフォールバック
        ]
    
    def get_parser(self, language: str) -> SignatureParser:
        """指定された言語に適したパーサーを取得"""
        for parser in self._parsers:
            if parser.supports_language(language):
                return parser
        
        # フォールバック（通常はDefaultSignatureParserが返される）
        return self._parsers[-1]
    
    def register_parser(self, parser: SignatureParser):
        """新しいパーサーを登録"""
        # DefaultSignatureParserの前に挿入
        self._parsers.insert(-1, parser)


# グローバルファクトリーインスタンス
signature_parser_factory = SignatureParserFactory()