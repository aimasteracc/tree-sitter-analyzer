#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Java Language Plugin

Provides Java-specific parsing and element extraction functionality.
"""

import re
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    import tree_sitter
    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

from ..language_loader import loader
from ..models import (
    Class,
    Function,
    Import,
    JavaAnnotation,
    JavaClass,
    JavaField,
    JavaImport,
    JavaMethod,
    Variable,
)
from ..utils import log_debug, log_error, log_warning
from . import ElementExtractor, LanguagePlugin


class JavaElementExtractor(ElementExtractor):
    """Advanced Java-specific element extractor with comprehensive analysis"""

    def __init__(self) -> None:
        # 分析コンテキスト
        self.current_package: str = ""
        self.current_file: str = ""
        self.source_code: str = ""
        self.imports: List[str] = []

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> List[Function]:
        """Extract Java method definitions with comprehensive analysis"""
        self.source_code = source_code
        functions: List[Function] = []

        # 複数のメソッドパターンを検索
        method_queries = [
            # 通常のメソッド宣言
            """
            (method_declaration
                (modifiers)? @method.modifiers
                type: (_)? @method.return_type
                name: (identifier) @method.name
                parameters: (formal_parameters) @method.params
                (throws)? @method.throws
                body: (block)? @method.body) @method.declaration
            """,
            # コンストラクタ
            """
            (constructor_declaration
                (modifiers)? @constructor.modifiers
                name: (identifier) @constructor.name
                parameters: (formal_parameters) @constructor.params
                (throws)? @constructor.throws
                body: (constructor_body) @constructor.body) @constructor.declaration
            """,
        ]

        try:
            language = tree.language if hasattr(tree, "language") else None
            if language:
                for query_string in method_queries:
                    query = language.query(query_string)
                    captures = query.captures(tree.root_node)

                    if isinstance(captures, dict):
                        # メソッド宣言を処理
                        method_nodes = captures.get("method.declaration", [])
                        for node in method_nodes:
                            function = self._extract_detailed_method_info(
                                node, source_code, False
                            )
                            if function:
                                functions.append(function)

                        # コンストラクタを処理
                        constructor_nodes = captures.get("constructor.declaration", [])
                        for node in constructor_nodes:
                            function = self._extract_detailed_method_info(
                                node, source_code, True
                            )
                            if function:
                                functions.append(function)

        except Exception as e:
            log_warning(f"Could not extract Java methods: {e}")

        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> List[Class]:
        """Extract Java class definitions with comprehensive analysis"""
        self.source_code = source_code
        classes: List[Class] = []

        # 複数のクラスタイプを検索
        class_queries = [
            # 通常のクラス
            """
            (class_declaration
                (modifiers)? @class.modifiers
                name: (identifier) @class.name
                (superclass)? @class.superclass
                (super_interfaces)? @class.interfaces
                body: (class_body) @class.body) @class.declaration
            """,
            # インターフェース
            """
            (interface_declaration
                (modifiers)? @interface.modifiers
                name: (identifier) @interface.name
                (extends_interfaces)? @interface.extends
                body: (interface_body) @interface.body) @interface.declaration
            """,
            # 列挙型
            """
            (enum_declaration
                (modifiers)? @enum.modifiers
                name: (identifier) @enum.name
                (super_interfaces)? @enum.interfaces
                body: (enum_body) @enum.body) @enum.declaration
            """,
            # アノテーション型
            """
            (annotation_type_declaration
                (modifiers)? @annotation.modifiers
                name: (identifier) @annotation.name
                body: (annotation_type_body) @annotation.body) @annotation.declaration
            """,
        ]

        try:
            language = tree.language if hasattr(tree, "language") else None
            if language:
                for query_string in class_queries:
                    query = language.query(query_string)
                    captures = query.captures(tree.root_node)

                    if isinstance(captures, dict):
                        # 各タイプのクラスを処理
                        for key, nodes in captures.items():
                            if key.endswith(".declaration"):
                                class_type = key.split(".")[0]
                                for node in nodes:
                                    cls = self._extract_detailed_class_info(
                                        node, source_code, class_type
                                    )
                                    if cls:
                                        classes.append(cls)

        except Exception as e:
            log_warning(f"Could not extract Java classes: {e}")

        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> List[Variable]:
        """Extract Java field and variable definitions"""
        variables: List[Variable] = []

        # Field declarations
        query_string = """
        (field_declaration
            type: (_) @field.type
            declarator: (variable_declarator
                name: (identifier) @field.name)) @field.declaration
        """

        try:
            language = tree.language if hasattr(tree, "language") else None
            if language:
                query = language.query(query_string)
                captures = query.captures(tree.root_node)

                if isinstance(captures, dict):
                    field_nodes = captures.get("field.declaration", [])
                    for node in field_nodes:
                        variable = self._extract_field_info(node, source_code)
                        if variable:
                            variables.append(variable)

        except Exception as e:
            log_warning(f"Could not extract Java fields: {e}")

        return variables

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> List[Import]:
        """Extract Java import statements"""
        imports: List[Import] = []

        query_string = """
        (import_declaration
            (scoped_identifier) @import.name) @import.declaration
        """

        try:
            language = tree.language if hasattr(tree, "language") else None
            if language:
                query = language.query(query_string)
                captures = query.captures(tree.root_node)

                if isinstance(captures, dict):
                    import_nodes = captures.get("import.declaration", [])
                    for node in import_nodes:
                        imp = self._extract_import_info(node, source_code)
                        if imp:
                            imports.append(imp)

        except Exception as e:
            log_warning(f"Could not extract Java imports: {e}")

        return imports

    def _extract_detailed_method_info(
        self, node: "tree_sitter.Node", source_code: str, is_constructor: bool = False
    ) -> Optional[Function]:
        """Extract comprehensive method information from AST node"""
        try:
            # 基本情報の抽出
            name = self._extract_name_from_node(node, source_code)
            if not name:
                return None

            # 詳細情報の抽出
            return_type = (
                self._extract_return_type_from_node(node, source_code)
                if not is_constructor
                else "void"
            )
            parameters = self._extract_parameters_from_node(node, source_code)
            modifiers = self._extract_modifiers_from_node(node, source_code)
            annotations = self._extract_annotations_from_node(node, source_code)
            throws = self._extract_throws_from_node(node, source_code)

            # 可視性の判定
            visibility = "public"
            if "private" in modifiers:
                visibility = "private"
            elif "protected" in modifiers:
                visibility = "protected"
            elif "public" not in modifiers and len(modifiers) > 0:
                visibility = "package"

            # メソッドボディの抽出
            body = self._extract_method_body(node, source_code)
            signature = self._generate_method_signature(
                name, return_type, parameters, modifiers
            )

            # 複雑度の簡易計算
            complexity_score = self._calculate_complexity(body)

            # Function型として返すため、基本的なFunction型を作成
            return Function(
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=source_code[node.start_byte : node.end_byte],
                language="java",
                parameters=parameters,
                return_type=return_type,
                modifiers=modifiers,
                is_static="static" in modifiers,
                is_private="private" in modifiers,
                is_public="public" in modifiers,
            )

        except Exception as e:
            log_warning(f"Could not extract detailed method info: {e}")
            return None

    def _extract_name_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Optional[str]:
        """Extract name from AST node"""
        for child in node.children:
            if child.type == "identifier":
                return source_code[child.start_byte : child.end_byte]
        return None

    def _extract_return_type_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> str:
        """Extract return type from method node"""
        for child in node.children:
            if child.type in [
                "type_identifier",
                "generic_type",
                "array_type",
                "primitive_type",
            ]:
                return source_code[child.start_byte : child.end_byte]
        return "void"

    def _extract_parameters_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> List[str]:
        """Extract parameters from method node"""
        parameters: List[str] = []
        for child in node.children:
            if child.type == "formal_parameters":
                for param_child in child.children:
                    if param_child.type == "formal_parameter":
                        param_text = source_code[
                            param_child.start_byte : param_child.end_byte
                        ]
                        parameters.append(param_text)
        return parameters

    def _extract_modifiers_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> List[str]:
        """Extract modifiers from node"""
        modifiers: List[str] = []
        for child in node.children:
            if child.type == "modifiers":
                modifier_text = source_code[child.start_byte : child.end_byte]
                # 簡単な分割で各修飾子を抽出
                for modifier in modifier_text.split():
                    if modifier in [
                        "public",
                        "private",
                        "protected",
                        "static",
                        "final",
                        "abstract",
                        "synchronized",
                    ]:
                        modifiers.append(modifier)
        return modifiers

    def _extract_annotations_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> List[JavaAnnotation]:
        """Extract annotations from node (simplified)"""
        annotations: List[JavaAnnotation] = []
        # より詳細な実装が必要だが、今回は簡略化
        return annotations

    def _extract_throws_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> List[str]:
        """Extract throws clause from method node"""
        throws: List[str] = []
        for child in node.children:
            if child.type == "throws":
                throws_text = source_code[child.start_byte : child.end_byte]
                # "throws" キーワードを除去して例外タイプを抽出
                if throws_text.startswith("throws"):
                    exceptions = throws_text[6:].strip()
                    throws.extend([ex.strip() for ex in exceptions.split(",")])
        return throws

    def _extract_method_body(self, node: "tree_sitter.Node", source_code: str) -> str:
        """Extract method body"""
        for child in node.children:
            if child.type in ["block", "constructor_body"]:
                return source_code[child.start_byte : child.end_byte]
        return ""

    def _generate_method_signature(
        self, name: str, return_type: str, parameters: List[str], modifiers: List[str]
    ) -> str:
        """Generate method signature"""
        modifier_str = " ".join(modifiers) + " " if modifiers else ""
        param_str = ", ".join(parameters) if parameters else ""
        return f"{modifier_str}{return_type} {name}({param_str})"

    def _calculate_complexity(self, body: str) -> int:
        """Calculate cyclomatic complexity (simplified)"""
        complexity = 1  # Base complexity
        keywords = ["if", "else", "for", "while", "switch", "case", "catch", "&&", "||"]
        for keyword in keywords:
            complexity += body.count(keyword)
        return complexity

    def _extract_detailed_class_info(
        self, node: "tree_sitter.Node", source_code: str, class_type: str = "class"
    ) -> Optional[Class]:
        """Extract comprehensive class information from AST node"""
        try:
            # 基本情報の抽出
            name = self._extract_name_from_node(node, source_code)
            if not name:
                return None

            # 詳細情報の抽出
            modifiers = self._extract_modifiers_from_node(node, source_code)
            annotations = self._extract_annotations_from_node(node, source_code)
            superclass = self._extract_superclass_from_node(node, source_code)
            interfaces = self._extract_interfaces_from_node(node, source_code)

            # 完全修飾名の生成
            full_qualified_name = (
                f"{self.current_package}.{name}" if self.current_package else name
            )

            # 可視性の判定
            visibility = "public"
            if "private" in modifiers:
                visibility = "private"
            elif "protected" in modifiers:
                visibility = "protected"
            elif "public" not in modifiers and len(modifiers) > 0:
                visibility = "package"

            # ネストクラスかどうかの判定（簡略化）
            is_nested = "." in self.current_package if self.current_package else False

            # Class型として返すため、基本的なClass型を作成
            return Class(
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=source_code[node.start_byte : node.end_byte],
                language="java",
                class_type=class_type,
                full_qualified_name=full_qualified_name,
                package_name=self.current_package,
                superclass=superclass,
                interfaces=interfaces,
                modifiers=modifiers,
            )

        except Exception as e:
            log_warning(f"Could not extract detailed class info: {e}")
            return None

    def _extract_superclass_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Optional[str]:
        """Extract superclass from class node"""
        for child in node.children:
            if child.type == "superclass":
                for subchild in child.children:
                    if subchild.type == "type_identifier":
                        return source_code[subchild.start_byte : subchild.end_byte]
        return None

    def _extract_interfaces_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> List[str]:
        """Extract implemented interfaces from class node"""
        interfaces: List[str] = []
        for child in node.children:
            if child.type in ["super_interfaces", "extends_interfaces"]:
                for subchild in child.children:
                    if subchild.type == "type_identifier":
                        interfaces.append(
                            source_code[subchild.start_byte : subchild.end_byte]
                        )
        return interfaces

    def _extract_field_info(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Optional[Variable]:
        """Extract detailed field information from AST node"""
        try:
            # Check if node has required attributes
            if (
                not hasattr(node, "start_byte")
                or not hasattr(node, "end_byte")
                or not hasattr(node, "start_point")
                or not hasattr(node, "end_point")
            ):
                return None
            if (
                node.start_byte is None
                or node.end_byte is None
                or node.start_point is None
                or node.end_point is None
            ):
                return None

            # Simple field extraction
            field_text = source_code[node.start_byte : node.end_byte]

            # Variable型として返すため、基本的なVariable型を作成
            return Variable(
                name="field",  # Would need more sophisticated parsing
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=field_text,
                language="java",
            )

        except Exception as e:
            log_warning(f"Could not extract field info: {e}")
            return None

    def _extract_import_info(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Optional[Import]:
        """Extract detailed import information from AST node"""
        try:
            # Check if node has required attributes
            if (
                not hasattr(node, "start_byte")
                or not hasattr(node, "end_byte")
                or not hasattr(node, "start_point")
                or not hasattr(node, "end_point")
            ):
                return None
            if (
                node.start_byte is None
                or node.end_byte is None
                or node.start_point is None
                or node.end_point is None
            ):
                return None

            import_text = source_code[node.start_byte : node.end_byte]

            # Import型として返すため、基本的なImport型を作成
            return Import(
                name="import",  # Would need more sophisticated parsing
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=import_text,
                language="java",
                module_name=import_text,
            )

        except Exception as e:
            log_warning(f"Could not extract import info: {e}")
            return None


class JavaPlugin(LanguagePlugin):
    """Java language plugin"""

    def __init__(self) -> None:
        self._extractor = JavaElementExtractor()
        self._language: Optional["tree_sitter.Language"] = None

    @property
    def language_name(self) -> str:
        return "java"

    @property
    def file_extensions(self) -> List[str]:
        return [".java", ".jsp", ".jspx"]

    def get_language_name(self) -> str:
        """Return the name of the programming language this plugin supports"""
        return "java"

    def get_file_extensions(self) -> List[str]:
        """Return list of file extensions this plugin supports"""
        return [".java", ".jsp", ".jspx"]

    def create_extractor(self) -> ElementExtractor:
        """Create and return an element extractor for this language"""
        return JavaElementExtractor()

    def get_extractor(self) -> ElementExtractor:
        return self._extractor

    def get_tree_sitter_language(self) -> Optional["tree_sitter.Language"]:
        """Load and return Java tree-sitter language"""
        if self._language is None:
            self._language = loader.load_language("java")
        return self._language
    
    async def analyze_file(self, file_path: str, request: 'AnalysisRequest') -> 'AnalysisResult':
        """
        Javaファイルを解析してAnalysisResultを返す
        
        Args:
            file_path: 解析対象ファイルのパス
            request: 解析リクエスト
            
        Returns:
            解析結果
        """
        from ..models import AnalysisResult
        from ..core.analysis_engine import get_analysis_engine, AnalysisRequest
        
        try:
            # Use UnifiedAnalysisEngine for file analysis
            analyzer = get_analysis_engine()
            
            # Create analysis request and analyze file
            request = AnalysisRequest(
                file_path=file_path,
                language="java",
                include_complexity=True,
                include_details=True
            )
            result = await analyzer.analyze(request)
            
            if not result or not result.success:
                return AnalysisResult(
                    file_path=file_path,
                    success=False,
                    error_message=f"Failed to analyze Java file: {file_path}"
                )
            
            return result
            
        except Exception as e:
            log_error(f"Error analyzing Java file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                success=False,
                error_message=str(e)
            )
