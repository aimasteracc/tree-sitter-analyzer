"""
サンプル言語プラグイン実装例

このファイルは、新しい言語プラグインを実装する際の参考として使用できる
完全なサンプル実装です。Rust言語を例として使用しています。
"""

from typing import Dict, List, Optional, Any
import tree_sitter
import tree_sitter_rust
from pathlib import Path

from tree_sitter_analyzer.plugins.base import EnhancedLanguagePlugin
from tree_sitter_analyzer.models import (
    AnalysisRequest, AnalysisResult, ModelFunction, ModelClass, 
    ModelVariable, ModelImport
)
from tree_sitter_analyzer.formatters.base import BaseFormatter


class RustPlugin(EnhancedLanguagePlugin):
    """
    Rust言語プラグインのサンプル実装
    
    このクラスは、新しい言語プラグインを実装する際の
    完全なテンプレートとして使用できます。
    """
    
    def __init__(self):
        """プラグインの初期化"""
        super().__init__()
        
        # Tree-sitter言語オブジェクトの設定
        self.language = tree_sitter_rust.language()
        self.parser = tree_sitter.Parser()
        self.parser.set_language(self.language)
        
        # パフォーマンス統計の初期化
        self.performance_stats = {
            "files_analyzed": 0,
            "total_parse_time": 0.0,
            "total_query_time": 0.0,
            "errors": 0
        }
    
    def get_language_name(self) -> str:
        """言語名を返す"""
        return "rust"
    
    def get_file_extensions(self) -> List[str]:
        """サポートするファイル拡張子を返す"""
        return [".rs"]
    
    def is_applicable(self, file_path: str) -> bool:
        """ファイルがこのプラグインで処理可能かを判定"""
        return any(file_path.endswith(ext) for ext in self.get_file_extensions())
    
    def get_language_object(self) -> tree_sitter.Language:
        """Tree-sitter言語オブジェクトを返す"""
        return self.language
    
    def get_query_definitions(self) -> Dict[str, str]:
        """
        Tree-sitterクエリ定義を返す
        
        各クエリは、特定のコード要素を抽出するためのパターンを定義します。
        """
        return {
            "functions": """
                (function_item
                    visibility: (visibility_modifier)? @function.visibility
                    name: (identifier) @function.name
                    parameters: (parameters) @function.params
                    return_type: (type_annotation)? @function.return_type
                    body: (block) @function.body
                ) @function.definition
            """,
            
            "structs": """
                (struct_item
                    visibility: (visibility_modifier)? @struct.visibility
                    name: (type_identifier) @struct.name
                    body: (field_declaration_list)? @struct.fields
                ) @struct.definition
            """,
            
            "enums": """
                (enum_item
                    visibility: (visibility_modifier)? @enum.visibility
                    name: (type_identifier) @enum.name
                    body: (enum_variant_list) @enum.variants
                ) @enum.definition
            """,
            
            "traits": """
                (trait_item
                    visibility: (visibility_modifier)? @trait.visibility
                    name: (type_identifier) @trait.name
                    body: (declaration_list) @trait.body
                ) @trait.definition
            """,
            
            "impls": """
                (impl_item
                    type: (type_identifier) @impl.type
                    body: (declaration_list) @impl.body
                ) @impl.definition
            """,
            
            "variables": """
                (let_declaration
                    pattern: (identifier) @variable.name
                    type: (type_annotation)? @variable.type
                    value: (_)? @variable.value
                ) @variable.definition
            """,
            
            "constants": """
                (const_item
                    visibility: (visibility_modifier)? @const.visibility
                    name: (identifier) @const.name
                    type: (type_annotation) @const.type
                    value: (_) @const.value
                ) @const.definition
            """,
            
            "modules": """
                (mod_item
                    visibility: (visibility_modifier)? @module.visibility
                    name: (identifier) @module.name
                    body: (declaration_list)? @module.body
                ) @module.definition
            """,
            
            "uses": """
                (use_declaration
                    argument: (use_clause) @use.clause
                ) @use.definition
            """,
            
            "macros": """
                (macro_definition
                    name: (identifier) @macro.name
                    parameters: (macro_rule)? @macro.params
                ) @macro.definition
            """
        }
    
    def create_formatter(self, format_type: str, **kwargs) -> BaseFormatter:
        """フォーマッターを作成"""
        return RustFormatter(format_type, **kwargs)
    
    def analyze_file(self, file_path: str, request: AnalysisRequest) -> AnalysisResult:
        """
        ファイルを解析してAnalysisResultを返す
        
        Args:
            file_path: 解析対象ファイルのパス
            request: 解析リクエスト（クエリタイプ等を指定）
            
        Returns:
            AnalysisResult: 解析結果
        """
        import time
        start_time = time.time()
        
        try:
            # ファイル読み込み
            source_code = Path(file_path).read_text(encoding='utf-8')
            
            # パース実行
            parse_start = time.time()
            tree = self.parser.parse(source_code.encode('utf-8'))
            parse_time = time.time() - parse_start
            
            if tree.root_node.has_error:
                raise Exception(f"Parse error in {file_path}")
            
            # 結果オブジェクトの初期化
            result = AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                functions=[],
                classes=[],  # Rustでは構造体として扱う
                variables=[],
                imports=[],
                metadata={}
            )
            
            # クエリ実行
            query_start = time.time()
            for query_type in request.query_types:
                if query_type == "functions":
                    result.functions = self._extract_functions(tree, source_code)
                elif query_type == "structs":
                    # 構造体をクラスとして扱う
                    result.classes = self._extract_structs(tree, source_code)
                elif query_type == "variables":
                    result.variables = self._extract_variables(tree, source_code)
                elif query_type == "uses":
                    result.imports = self._extract_uses(tree, source_code)
                # 他のクエリタイプも同様に処理
            
            query_time = time.time() - query_start
            
            # メタデータの設定
            result.metadata = {
                "parse_time": parse_time,
                "query_time": query_time,
                "total_time": time.time() - start_time,
                "node_count": self._count_nodes(tree.root_node),
                "file_size": len(source_code),
                "line_count": source_code.count('\n') + 1
            }
            
            # 統計の更新
            self._update_performance_stats(parse_time, query_time)
            
            return result
            
        except Exception as e:
            self.performance_stats["errors"] += 1
            raise Exception(f"Failed to analyze {file_path}: {str(e)}")
    
    def _extract_functions(self, tree: tree_sitter.Tree, source_code: str) -> List[ModelFunction]:
        """関数を抽出"""
        functions = []
        query = self.language.query(self.get_query_definitions()["functions"])
        
        for match in query.matches(tree.root_node):
            function_data = self._extract_captures(match, source_code)
            
            if "function.name" in function_data:
                function = ModelFunction(
                    name=function_data["function.name"],
                    start_line=function_data.get("start_line", 0),
                    end_line=function_data.get("end_line", 0),
                    start_column=function_data.get("start_column", 0),
                    end_column=function_data.get("end_column", 0),
                    docstring=self._extract_docstring(function_data, source_code),
                    parameters=self._extract_function_parameters(function_data, source_code),
                    return_type=function_data.get("function.return_type"),
                    is_async=False,  # Rustでは async fn として判定
                    is_method=self._is_method(function_data),
                    visibility=function_data.get("function.visibility", "private"),
                    metadata={
                        "language_specific": {
                            "is_unsafe": self._is_unsafe_function(function_data),
                            "is_extern": self._is_extern_function(function_data),
                            "generics": self._extract_generics(function_data)
                        }
                    }
                )
                functions.append(function)
        
        return functions
    
    def _extract_structs(self, tree: tree_sitter.Tree, source_code: str) -> List[ModelClass]:
        """構造体を抽出（クラスとして扱う）"""
        structs = []
        query = self.language.query(self.get_query_definitions()["structs"])
        
        for match in query.matches(tree.root_node):
            struct_data = self._extract_captures(match, source_code)
            
            if "struct.name" in struct_data:
                struct = ModelClass(
                    name=struct_data["struct.name"],
                    start_line=struct_data.get("start_line", 0),
                    end_line=struct_data.get("end_line", 0),
                    start_column=struct_data.get("start_column", 0),
                    end_column=struct_data.get("end_column", 0),
                    docstring=self._extract_docstring(struct_data, source_code),
                    methods=[],  # impl ブロックから抽出
                    fields=self._extract_struct_fields(struct_data, source_code),
                    base_classes=[],  # Rustには継承がない
                    is_abstract=False,
                    visibility=struct_data.get("struct.visibility", "private"),
                    metadata={
                        "language_specific": {
                            "is_tuple_struct": self._is_tuple_struct(struct_data),
                            "is_unit_struct": self._is_unit_struct(struct_data),
                            "derives": self._extract_derives(struct_data)
                        }
                    }
                )
                structs.append(struct)
        
        return structs
    
    def _extract_variables(self, tree: tree_sitter.Tree, source_code: str) -> List[ModelVariable]:
        """変数を抽出"""
        variables = []
        query = self.language.query(self.get_query_definitions()["variables"])
        
        for match in query.matches(tree.root_node):
            var_data = self._extract_captures(match, source_code)
            
            if "variable.name" in var_data:
                variable = ModelVariable(
                    name=var_data["variable.name"],
                    start_line=var_data.get("start_line", 0),
                    end_line=var_data.get("end_line", 0),
                    start_column=var_data.get("start_column", 0),
                    end_column=var_data.get("end_column", 0),
                    type_annotation=var_data.get("variable.type"),
                    default_value=var_data.get("variable.value"),
                    is_constant=False,
                    visibility="private",  # Rustのlet変数は常にprivate
                    metadata={
                        "language_specific": {
                            "is_mutable": self._is_mutable_variable(var_data),
                            "is_reference": self._is_reference_variable(var_data)
                        }
                    }
                )
                variables.append(variable)
        
        return variables
    
    def _extract_uses(self, tree: tree_sitter.Tree, source_code: str) -> List[ModelImport]:
        """use文を抽出"""
        imports = []
        query = self.language.query(self.get_query_definitions()["uses"])
        
        for match in query.matches(tree.root_node):
            use_data = self._extract_captures(match, source_code)
            
            if "use.clause" in use_data:
                import_stmt = ModelImport(
                    module=self._extract_module_from_use(use_data["use.clause"]),
                    names=self._extract_names_from_use(use_data["use.clause"]),
                    alias=self._extract_alias_from_use(use_data["use.clause"]),
                    is_wildcard=self._is_wildcard_use(use_data["use.clause"]),
                    start_line=use_data.get("start_line", 0),
                    end_line=use_data.get("end_line", 0),
                    metadata={
                        "language_specific": {
                            "is_external_crate": self._is_external_crate(use_data),
                            "visibility": self._extract_use_visibility(use_data)
                        }
                    }
                )
                imports.append(import_stmt)
        
        return imports
    
    def _extract_captures(self, match, source_code: str) -> Dict[str, Any]:
        """マッチからキャプチャデータを抽出"""
        captures = {}
        
        for capture in match.captures:
            node = capture.node
            capture_name = capture.name
            
            # テキスト内容の取得
            text = node.text.decode('utf-8') if node.text else ""
            captures[capture_name] = text
            
            # 位置情報の取得
            if capture_name.endswith('.definition'):
                captures["start_line"] = node.start_point[0] + 1
                captures["end_line"] = node.end_point[0] + 1
                captures["start_column"] = node.start_point[1]
                captures["end_column"] = node.end_point[1]
        
        return captures
    
    def _extract_docstring(self, data: Dict[str, Any], source_code: str) -> Optional[str]:
        """ドキュメントコメントを抽出"""
        # Rustのドキュメントコメント（/// や /** */）を抽出
        # 実装は簡略化
        return None
    
    def _extract_function_parameters(self, data: Dict[str, Any], source_code: str) -> List[str]:
        """関数パラメータを抽出"""
        params_text = data.get("function.params", "")
        if not params_text or params_text == "()":
            return []
        
        # 簡単なパラメータ解析（実際にはより複雑な処理が必要）
        params = []
        param_parts = params_text.strip("()").split(",")
        for part in param_parts:
            part = part.strip()
            if part and part != "":
                params.append(part)
        
        return params
    
    def _extract_struct_fields(self, data: Dict[str, Any], source_code: str) -> List[str]:
        """構造体フィールドを抽出"""
        fields_text = data.get("struct.fields", "")
        if not fields_text:
            return []
        
        # 簡単なフィールド解析
        fields = []
        # 実際の実装では、より詳細な解析が必要
        return fields
    
    def _is_method(self, data: Dict[str, Any]) -> bool:
        """メソッドかどうかを判定"""
        params = data.get("function.params", "")
        return params.startswith("&self") or params.startswith("self") or params.startswith("&mut self")
    
    def _is_unsafe_function(self, data: Dict[str, Any]) -> bool:
        """unsafe関数かどうかを判定"""
        # 実装は簡略化
        return False
    
    def _is_extern_function(self, data: Dict[str, Any]) -> bool:
        """extern関数かどうかを判定"""
        # 実装は簡略化
        return False
    
    def _extract_generics(self, data: Dict[str, Any]) -> List[str]:
        """ジェネリクスパラメータを抽出"""
        # 実装は簡略化
        return []
    
    def _is_tuple_struct(self, data: Dict[str, Any]) -> bool:
        """タプル構造体かどうかを判定"""
        # 実装は簡略化
        return False
    
    def _is_unit_struct(self, data: Dict[str, Any]) -> bool:
        """ユニット構造体かどうかを判定"""
        # 実装は簡略化
        return False
    
    def _extract_derives(self, data: Dict[str, Any]) -> List[str]:
        """derive属性を抽出"""
        # 実装は簡略化
        return []
    
    def _is_mutable_variable(self, data: Dict[str, Any]) -> bool:
        """可変変数かどうかを判定"""
        # 実装は簡略化
        return False
    
    def _is_reference_variable(self, data: Dict[str, Any]) -> bool:
        """参照変数かどうかを判定"""
        # 実装は簡略化
        return False
    
    def _extract_module_from_use(self, use_clause: str) -> str:
        """use文からモジュール名を抽出"""
        # 実装は簡略化
        return use_clause.split("::")[0] if "::" in use_clause else use_clause
    
    def _extract_names_from_use(self, use_clause: str) -> List[str]:
        """use文からインポート名を抽出"""
        # 実装は簡略化
        return [use_clause.split("::")[-1]]
    
    def _extract_alias_from_use(self, use_clause: str) -> Optional[str]:
        """use文からエイリアスを抽出"""
        # 実装は簡略化
        return None
    
    def _is_wildcard_use(self, use_clause: str) -> bool:
        """ワイルドカードインポートかどうかを判定"""
        return use_clause.endswith("*")
    
    def _is_external_crate(self, data: Dict[str, Any]) -> bool:
        """外部クレートかどうかを判定"""
        # 実装は簡略化
        return False
    
    def _extract_use_visibility(self, data: Dict[str, Any]) -> str:
        """use文の可視性を抽出"""
        # 実装は簡略化
        return "private"
    
    def _count_nodes(self, node: tree_sitter.Node) -> int:
        """ノード数をカウント"""
        count = 1
        for child in node.children:
            count += self._count_nodes(child)
        return count
    
    def _update_performance_stats(self, parse_time: float, query_time: float):
        """パフォーマンス統計を更新"""
        self.performance_stats["files_analyzed"] += 1
        self.performance_stats["total_parse_time"] += parse_time
        self.performance_stats["total_query_time"] += query_time
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """パフォーマンスメトリクスを取得"""
        stats = self.performance_stats.copy()
        
        if stats["files_analyzed"] > 0:
            stats["avg_parse_time"] = stats["total_parse_time"] / stats["files_analyzed"]
            stats["avg_query_time"] = stats["total_query_time"] / stats["files_analyzed"]
        else:
            stats["avg_parse_time"] = 0.0
            stats["avg_query_time"] = 0.0
        
        return stats


class RustFormatter(BaseFormatter):
    """
    Rust言語用フォーマッター
    
    解析結果をRust言語に特化した形式で出力します。
    """
    
    def __init__(self, format_type: str, **kwargs):
        super().__init__(format_type, **kwargs)
        self.language = "rust"
    
    def format_function(self, function: ModelFunction) -> str:
        """関数の書式設定"""
        if self.format_type == "table":
            return self._format_function_table(function)
        elif self.format_type == "json":
            return self._format_function_json(function)
        else:
            return str(function)
    
    def _format_function_table(self, function: ModelFunction) -> str:
        """テーブル形式での関数書式設定"""
        visibility = function.visibility or "private"
        params = ", ".join(function.parameters) if function.parameters else "()"
        return_type = function.return_type or "()"
        
        # Rust特有の情報
        metadata = function.metadata.get("language_specific", {})
        modifiers = []
        
        if metadata.get("is_unsafe"):
            modifiers.append("unsafe")
        if metadata.get("is_extern"):
            modifiers.append("extern")
        if function.is_async:
            modifiers.append("async")
        
        modifier_str = " ".join(modifiers)
        if modifier_str:
            modifier_str = f"[{modifier_str}] "
        
        return f"{modifier_str}{visibility} fn {function.name}({params}) -> {return_type}"
    
    def _format_function_json(self, function: ModelFunction) -> str:
        """JSON形式での関数書式設定"""
        import json
        
        data = {
            "name": function.name,
            "visibility": function.visibility,
            "parameters": function.parameters,
            "return_type": function.return_type,
            "is_method": function.is_method,
            "location": {
                "start_line": function.start_line,
                "end_line": function.end_line
            },
            "rust_specific": function.metadata.get("language_specific", {})
        }
        
        return json.dumps(data, indent=2)
    
    def format_class(self, class_obj: ModelClass) -> str:
        """構造体の書式設定"""
        if self.format_type == "table":
            return self._format_struct_table(class_obj)
        elif self.format_type == "json":
            return self._format_struct_json(class_obj)
        else:
            return str(class_obj)
    
    def _format_struct_table(self, struct: ModelClass) -> str:
        """テーブル形式での構造体書式設定"""
        visibility = struct.visibility or "private"
        
        # Rust特有の情報
        metadata = struct.metadata.get("language_specific", {})
        struct_type = "struct"
        
        if metadata.get("is_tuple_struct"):
            struct_type = "tuple struct"
        elif metadata.get("is_unit_struct"):
            struct_type = "unit struct"
        
        derives = metadata.get("derives", [])
        derive_str = f" #[derive({', '.join(derives)})]" if derives else ""
        
        return f"{derive_str} {visibility} {struct_type} {struct.name}"
    
    def _format_struct_json(self, struct: ModelClass) -> str:
        """JSON形式での構造体書式設定"""
        import json
        
        data = {
            "name": struct.name,
            "type": "struct",
            "visibility": struct.visibility,
            "fields": struct.fields,
            "methods": [method.name for method in struct.methods],
            "location": {
                "start_line": struct.start_line,
                "end_line": struct.end_line
            },
            "rust_specific": struct.metadata.get("language_specific", {})
        }
        
        return json.dumps(data, indent=2)


# プラグインの登録例
def register_rust_plugin():
    """
    Rustプラグインを登録する関数
    
    この関数は、プラグインマネージャーにRustプラグインを
    登録するために使用されます。
    """
    from tree_sitter_analyzer.plugins.manager import PluginManager
    
    manager = PluginManager()
    rust_plugin = RustPlugin()
    manager.register_plugin("rust", rust_plugin)
    
    print("✅ Rustプラグインが正常に登録されました")
    return rust_plugin


# 使用例とテスト
if __name__ == "__main__":
    # プラグインのテスト
    plugin = RustPlugin()
    
    # 基本情報の確認
    print(f"言語名: {plugin.get_language_name()}")
    print(f"拡張子: {plugin.get_file_extensions()}")
    print(f"クエリ数: {len(plugin.get_query_definitions())}")
    
    # サンプルRustコードでのテスト
    sample_rust_code = '''
pub struct Calculator {
    value: i32,
}

impl Calculator {
    pub fn new() -> Self {
        Calculator { value: 0 }
    }
    
    pub fn add(&mut self, x: i32) -> i32 {
        self.value += x;
        self.value
    }
}

pub fn main() {
    let mut calc = Calculator::new();
    let result = calc.add(5);
    println!("Result: {}", result);
}
'''
    
    # 一時ファイルでのテスト
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.rs', delete=False) as f:
        f.write(sample_rust_code)
        temp_file = f.name
    
    try:
        from tree_sitter_analyzer.models import AnalysisRequest
        
        request = AnalysisRequest(query_types=["functions", "structs"])
        result = plugin.analyze_file(temp_file, request)
        
        print(f"\n解析結果:")
        print(f"関数数: {len(result.functions)}")
        print(f"構造体数: {len(result.classes)}")
        
        # フォーマッターのテスト
        formatter = plugin.create_formatter("table")
        
        if result.functions:
            print(f"\n関数例:")
            print(formatter.format_function(result.functions[0]))
        
        if result.classes:
            print(f"\n構造体例:")
            print(formatter.format_class(result.classes[0]))
        
    finally:
        import os
        os.unlink(temp_file)
    
    print(f"\nパフォーマンス統計:")
    stats = plugin.get_performance_metrics()
    for key, value in stats.items():
        print(f"  {key}: {value}")