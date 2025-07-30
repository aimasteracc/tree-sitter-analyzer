#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python Language Plugin

Provides Python-specific parsing and element extraction functionality.
Integrates with the existing Python queries for comprehensive analysis.
"""

import re
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    import tree_sitter

from ..language_loader import loader
from ..models import Class, Function, Import, Variable
from ..queries.python import ALL_QUERIES, get_query
from ..utils import log_debug, log_error, log_warning
from . import ElementExtractor, LanguagePlugin


class PythonElementExtractor(ElementExtractor):
    """Python-specific element extractor with comprehensive analysis"""

    def __init__(self) -> None:
        # 分析コンテキスト
        self.current_module: str = ""
        self.current_file: str = ""
        self.source_code: str = ""
        self.imports: List[str] = []

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> List[Function]:
        """Extract Python function definitions with comprehensive analysis"""
        self.source_code = source_code
        functions: List[Function] = []

        try:
            language = tree.language if hasattr(tree, "language") else None
            if language:
                # 関数定義クエリを使用
                query_string = get_query("functions")
                query = language.query(query_string)
                captures = query.captures(tree.root_node)

                if captures is not None and isinstance(captures, dict):
                    # 関数定義を処理
                    function_nodes = captures.get("function.definition", [])
                    for node in function_nodes:
                        function = self._extract_detailed_function_info(
                            node, source_code
                        )
                        if function:
                            functions.append(function)

                    # async関数も処理
                    async_nodes = captures.get("function.async", [])
                    for node in async_nodes:
                        function = self._extract_detailed_function_info(
                            node, source_code, is_async=True
                        )
                        if function:
                            functions.append(function)

        except Exception as e:
            log_warning(f"Could not extract Python functions: {e}")

        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> List[Class]:
        """Extract Python class definitions with comprehensive analysis"""
        self.source_code = source_code
        classes: List[Class] = []

        try:
            language = tree.language if hasattr(tree, "language") else None
            if language:
                # クラス定義クエリを使用
                query_string = get_query("classes")
                query = language.query(query_string)
                captures = query.captures(tree.root_node)

                if captures is not None and isinstance(captures, dict):
                    class_nodes = captures.get("class.definition", [])
                    for node in class_nodes:
                        cls = self._extract_detailed_class_info(node, source_code)
                        if cls:
                            classes.append(cls)

        except Exception as e:
            log_warning(f"Could not extract Python classes: {e}")

        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> List[Variable]:
        """Extract Python variable definitions"""
        variables: List[Variable] = []

        try:
            language = tree.language if hasattr(tree, "language") else None
            if language:
                # 変数代入クエリを使用
                query_string = get_query("variables")
                query = language.query(query_string)
                captures = query.captures(tree.root_node)

                if captures is not None and isinstance(captures, dict):
                    # 通常の代入
                    assignment_nodes = captures.get("variable.assignment", [])
                    for node in assignment_nodes:
                        variable = self._extract_variable_info(node, source_code)
                        if variable:
                            variables.append(variable)

                    # 複数代入
                    multiple_nodes = captures.get("variable.multiple", [])
                    for node in multiple_nodes:
                        variable = self._extract_variable_info(
                            node, source_code, is_multiple=True
                        )
                        if variable:
                            variables.append(variable)

                    # 拡張代入
                    augmented_nodes = captures.get("variable.augmented", [])
                    for node in augmented_nodes:
                        variable = self._extract_variable_info(
                            node, source_code, is_augmented=True
                        )
                        if variable:
                            variables.append(variable)

        except Exception as e:
            log_warning(f"Could not extract Python variables: {e}")

        return variables

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> List[Import]:
        """Extract Python import statements"""
        imports: List[Import] = []

        try:
            language = tree.language if hasattr(tree, "language") else None
            if language:
                # インポート文クエリを使用
                query_string = get_query("imports")
                query = language.query(query_string)
                captures = query.captures(tree.root_node)

                if captures is not None and isinstance(captures, dict):
                    # 通常のimport
                    import_nodes = captures.get("import.statement", [])
                    for node in import_nodes:
                        imp = self._extract_import_info(node, source_code)
                        if imp:
                            imports.append(imp)

                    # from import
                    from_nodes = captures.get("import.from", [])
                    for node in from_nodes:
                        imp = self._extract_import_info(node, source_code, is_from=True)
                        if imp:
                            imports.append(imp)

                    # from import list
                    from_list_nodes = captures.get("import.from_list", [])
                    for node in from_list_nodes:
                        imp = self._extract_import_info(
                            node, source_code, is_from_list=True
                        )
                        if imp:
                            imports.append(imp)

                    # aliased import
                    aliased_nodes = captures.get("import.aliased", [])
                    for node in aliased_nodes:
                        imp = self._extract_import_info(
                            node, source_code, is_aliased=True
                        )
                        if imp:
                            imports.append(imp)

        except Exception as e:
            log_warning(f"Could not extract Python imports: {e}")

        return imports

    def _extract_detailed_function_info(
        self, node: "tree_sitter.Node", source_code: str, is_async: bool = False
    ) -> Optional[Function]:
        """Extract comprehensive function information from AST node"""
        try:
            # 基本情報の抽出
            name = self._extract_name_from_node(node, source_code)
            if not name:
                return None

            # パラメータの抽出
            parameters = self._extract_parameters_from_node(node, source_code)

            # デコレータの抽出
            decorators = self._extract_decorators_from_node(node, source_code)

            # 戻り値の型ヒントの抽出
            return_type = self._extract_return_type_from_node(node, source_code)

            # docstringの抽出
            docstring = self._extract_docstring_from_node(node, source_code)

            # 関数ボディの抽出
            body = self._extract_function_body(node, source_code)

            # 複雑度の簡易計算
            complexity_score = self._calculate_complexity(body)

            # 可視性の判定（Pythonの慣例に基づく）
            visibility = "public"
            if name.startswith("__") and name.endswith("__"):
                visibility = "magic"  # マジックメソッド
            elif name.startswith("_"):
                visibility = "private"

            start_byte = min(node.start_byte, len(source_code))
            end_byte = min(node.end_byte, len(source_code))
            raw_text = source_code[start_byte:end_byte] if start_byte < end_byte else source_code

            return Function(
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=raw_text,
                language="python",
                parameters=parameters,
                return_type=return_type or "Any",
                modifiers=decorators,
                is_static="staticmethod" in decorators,
                is_private=visibility == "private",
                is_public=visibility == "public",
                is_async=is_async,
                docstring=docstring,
                complexity_score=complexity_score,
            )

        except Exception as e:
            log_warning(f"Could not extract detailed function info: {e}")
            return None

    def _extract_detailed_class_info(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Optional[Class]:
        """Extract comprehensive class information from AST node"""
        try:
            # 基本情報の抽出
            name = self._extract_name_from_node(node, source_code)
            if not name:
                return None

            # スーパークラスの抽出
            superclasses = self._extract_superclasses_from_node(node, source_code)

            # デコレータの抽出
            decorators = self._extract_decorators_from_node(node, source_code)

            # docstringの抽出
            docstring = self._extract_docstring_from_node(node, source_code)

            # 完全修飾名の生成
            full_qualified_name = (
                f"{self.current_module}.{name}" if self.current_module else name
            )

            # 可視性の判定
            visibility = "public"
            if name.startswith("_"):
                visibility = "private"

            return Class(
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=source_code[node.start_byte : node.end_byte],
                language="python",
                class_type="class",
                full_qualified_name=full_qualified_name,
                package_name=self.current_module,
                superclass=superclasses[0] if superclasses else None,
                interfaces=superclasses[1:] if len(superclasses) > 1 else [],
                modifiers=decorators,
                docstring=docstring,
            )

        except Exception as e:
            log_warning(f"Could not extract detailed class info: {e}")
            return None

    def _extract_name_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Optional[str]:
        """Extract name from AST node"""
        for child in node.children:
            if child.type == "identifier":
                return source_code[child.start_byte : child.end_byte]
        return None

    def _extract_parameters_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> List[str]:
        """Extract parameters from function node"""
        parameters: List[str] = []
        for child in node.children:
            if child.type == "parameters":
                for param_child in child.children:
                    if param_child.type in [
                        "identifier",
                        "typed_parameter",
                        "default_parameter",
                    ]:
                        param_text = source_code[
                            param_child.start_byte : param_child.end_byte
                        ]
                        parameters.append(param_text)
        return parameters

    def _extract_decorators_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> List[str]:
        """Extract decorators from node"""
        decorators: List[str] = []

        # デコレータは関数/クラス定義の前にある
        if hasattr(node, "parent") and node.parent:
            for sibling in node.parent.children:
                if (
                    sibling.type == "decorator"
                    and sibling.end_point[0] < node.start_point[0]
                ):
                    decorator_text = source_code[sibling.start_byte : sibling.end_byte]
                    # @を除去
                    if decorator_text.startswith("@"):
                        decorator_text = decorator_text[1:].strip()
                    decorators.append(decorator_text)

        return decorators

    def _extract_return_type_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Optional[str]:
        """Extract return type annotation from function node"""
        for child in node.children:
            if child.type == "type":
                return source_code[child.start_byte : child.end_byte]
        return None

    def _extract_docstring_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Optional[str]:
        """Extract docstring from function/class node"""
        for child in node.children:
            if child.type == "block":
                # ブロックの最初の文がdocstringかチェック
                for stmt in child.children:
                    if stmt.type == "expression_statement":
                        for expr in stmt.children:
                            if expr.type == "string":
                                # start_byteとend_byteが整数であることを確認
                                if (hasattr(expr, 'start_byte') and hasattr(expr, 'end_byte') and
                                    isinstance(expr.start_byte, int) and isinstance(expr.end_byte, int)):
                                    docstring = source_code[expr.start_byte : expr.end_byte]
                                else:
                                    return None
                                # クォートを除去
                                if docstring.startswith('"""') or docstring.startswith(
                                    "'''"
                                ):
                                    return docstring[3:-3].strip()
                                elif docstring.startswith('"') or docstring.startswith(
                                    "'"
                                ):
                                    return docstring[1:-1].strip()
                                return docstring
                        break
                break
        return None

    def _extract_function_body(self, node: "tree_sitter.Node", source_code: str) -> str:
        """Extract function body"""
        for child in node.children:
            if child.type == "block":
                return source_code[child.start_byte : child.end_byte]
        return ""

    def _extract_superclasses_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> List[str]:
        """Extract superclasses from class node"""
        superclasses: List[str] = []
        for child in node.children:
            if child.type == "argument_list":
                for arg in child.children:
                    if arg.type == "identifier":
                        superclasses.append(source_code[arg.start_byte : arg.end_byte])
        return superclasses

    def _calculate_complexity(self, body: str) -> int:
        """Calculate cyclomatic complexity (simplified)"""
        complexity = 1  # 基本複雑度
        keywords = ["if", "elif", "for", "while", "try", "except", "with", "and", "or"]
        for keyword in keywords:
            complexity += body.count(f" {keyword} ") + body.count(f"\n{keyword} ")
        return complexity

    def _extract_variable_info(
        self,
        node: "tree_sitter.Node",
        source_code: str,
        is_multiple: bool = False,
        is_augmented: bool = False,
    ) -> Optional[Variable]:
        """Extract detailed variable information from AST node"""
        try:
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

            # 変数名の抽出（簡略化）
            variable_text = source_code[node.start_byte : node.end_byte]

            # 変数名を抽出（=の左側）
            if "=" in variable_text:
                name_part = variable_text.split("=")[0].strip()
                if is_multiple and "," in name_part:
                    name = name_part.split(",")[0].strip()
                else:
                    name = name_part
            else:
                name = "variable"

            return Variable(
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=variable_text,
                language="python",
                variable_type=(
                    "multiple"
                    if is_multiple
                    else "augmented" if is_augmented else "assignment"
                ),
            )

        except Exception as e:
            log_warning(f"Could not extract variable info: {e}")
            return None

    def _extract_import_info(
        self,
        node: "tree_sitter.Node",
        source_code: str,
        is_from: bool = False,
        is_from_list: bool = False,
        is_aliased: bool = False,
    ) -> Optional[Import]:
        """Extract detailed import information from AST node"""
        try:
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

            # テスト環境での安全な境界処理
            source_len = len(source_code)
            if node.start_byte >= source_len or node.end_byte > source_len:
                # ノードの範囲がソースコードを超える場合（テスト環境など）、全体を使用
                import_text = source_code
            else:
                start_byte = node.start_byte
                end_byte = node.end_byte
                import_text = source_code[start_byte:end_byte] if start_byte < end_byte else source_code

            # インポート名とモジュール名を抽出（完全なインポート文を保持）
            if is_from:
                import_type = "from_import"
                if "from" in import_text and "import" in import_text:
                    parts = import_text.split("import")
                    module_name = parts[0].replace("from", "").strip()
                    # from importの場合は完全な文を保持
                    import_name = import_text
                else:
                    module_name = ""
                    import_name = import_text
            elif is_aliased:
                import_type = "aliased_import"
                module_name = ""
                # エイリアスインポートも完全な文を保持
                import_name = import_text
            else:
                import_type = "import"
                module_name = ""
                # 通常のインポートも完全な文を保持
                import_name = import_text

            return Import(
                name=import_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=import_text,
                language="python",
                module_name=module_name,
                import_statement=import_text,
                line_number=node.start_point[0] + 1,
            )

        except Exception as e:
            log_warning(f"Could not extract import info: {e}")
            return None


class PythonPlugin(LanguagePlugin):
    """Python language plugin"""

    def __init__(self) -> None:
        self._extractor = PythonElementExtractor()
        self._language: Optional["tree_sitter.Language"] = None

    @property
    def language_name(self) -> str:
        return "python"

    @property
    def file_extensions(self) -> List[str]:
        return [".py", ".pyw", ".pyi"]

    def get_language_name(self) -> str:
        """Return the name of the programming language this plugin supports"""
        return "python"

    def get_file_extensions(self) -> List[str]:
        """Return list of file extensions this plugin supports"""
        return [".py", ".pyw", ".pyi"]

    def create_extractor(self) -> ElementExtractor:
        """Create and return an element extractor for this language"""
        return PythonElementExtractor()

    def get_extractor(self) -> ElementExtractor:
        return self._extractor

    def get_tree_sitter_language(self) -> Optional["tree_sitter.Language"]:
        """Load and return Python tree-sitter language"""
        if self._language is None:
            self._language = loader.load_language("python")
        return self._language

    def get_supported_queries(self) -> List[str]:
        """Get list of supported query types for Python"""
        return list(ALL_QUERIES.keys())

    def execute_query(self, tree: "tree_sitter.Tree", query_name: str) -> dict:
        """Execute a specific query on the tree"""
        try:
            query_string = get_query(query_name)
            language = self.get_tree_sitter_language()
            if language:
                query = language.query(query_string)
                captures = query.captures(tree.root_node)
                return captures if isinstance(captures, dict) else {}
        except Exception as e:
            log_warning(f"Could not execute query '{query_name}': {e}")
        return {}
