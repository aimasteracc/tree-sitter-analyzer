
# 新言語プラグイン追加ガイド

## 📋 概要

このガイドでは、tree-sitter-analyzerに新しい言語のサポートを追加する詳細な手順を説明します。プラグインベースアーキテクチャを活用して、既存コードに影響を与えることなく新言語を追加できます。

### 対象読者
- 新言語サポートを追加したい開発者
- プラグイン開発者
- コントリビューター

### 前提条件
- Tree-sitterの基本知識
- 対象言語の構文知識
- Python 3.8+の開発経験

---

## 🚀 クイックスタート

### 新言語追加の基本手順

1. **Tree-sitter言語パーサーの確認**
2. **プラグインクラスの実装**
3. **クエリ定義の作成**
4. **フォーマッターの実装**
5. **テストケースの作成**
6. **ドキュメントの更新**

### 所要時間
- **簡単な言語**: 1-2日
- **複雑な言語**: 3-5日
- **高度なカスタマイズ**: 1週間

---

## 📋 Step 1: 事前準備

### 1.1 Tree-sitter言語パーサーの確認

```bash
# 利用可能なTree-sitter言語パーサーを確認
pip search tree-sitter-

# 例: Rust言語の場合
pip install tree-sitter-rust

# または、tree-sitter-languagesパッケージを使用
pip install tree-sitter-languages
```

### 1.2 対応言語の調査

```python
# 対象言語のTree-sitterサポート確認
import tree_sitter_rust as ts_rust

# 言語オブジェクトの取得
language = ts_rust.language()
print(f"Language: {language}")

# 利用可能なノードタイプの確認
node_types = language.node_types
print(f"Available node types: {len(node_types)}")
```

### 1.3 サンプルコードの準備

```rust
// examples/sample.rs - テスト用Rustコード
fn main() {
    println!("Hello, world!");
}

struct Person {
    name: String,
    age: u32,
}

impl Person {
    fn new(name: String, age: u32) -> Self {
        Person { name, age }
    }
    
    fn greet(&self) {
        println!("Hello, my name is {}", self.name);
    }
}

enum Color {
    Red,
    Green,
    Blue,
}

trait Drawable {
    fn draw(&self);
}
```

---

## 🔧 Step 2: プラグインクラスの実装

### 2.1 基本プラグインクラスの作成

```python
# tree_sitter_analyzer/languages/rust.py
from typing import Dict, List, Any, Optional
import tree_sitter
import tree_sitter_rust as ts_rust
from tree_sitter_analyzer.plugins.base import EnhancedLanguagePlugin
from tree_sitter_analyzer.formatters.base import BaseFormatter
from tree_sitter_analyzer.models import AnalysisRequest, AnalysisResult
from tree_sitter_analyzer.exceptions import ParseError, UnsupportedQueryError

class RustPlugin(EnhancedLanguagePlugin):
    """Rust言語プラグイン"""
    
    def __init__(self):
        """プラグインの初期化"""
        self.language = ts_rust.language()
        self.parser = tree_sitter.Parser()
        self.parser.set_language(self.language)
        self._query_cache: Dict[str, tree_sitter.Query] = {}
        self._performance_metrics = {
            "parse_count": 0,
            "total_parse_time": 0.0,
            "error_count": 0
        }
    
    def get_language_name(self) -> str:
        """言語名を返す"""
        return "rust"
    
    def get_file_extensions(self) -> List[str]:
        """対応ファイル拡張子のリストを返す"""
        return [".rs"]
    
    def is_applicable(self, file_path: str) -> bool:
        """ファイルがこのプラグインで処理可能かを判定"""
        return any(file_path.endswith(ext) for ext in self.get_file_extensions())
    
    def get_supported_features(self) -> List[str]:
        """サポートする機能のリストを返す"""
        return [
            "functions",
            "structs", 
            "enums",
            "traits",
            "implementations",
            "modules",
            "constants",
            "variables"
        ]
    
    def get_plugin_info(self) -> Dict[str, Any]:
        """プラグイン情報を返す"""
        return {
            "name": "Rust Language Plugin",
            "version": "1.0.0",
            "language": self.get_language_name(),
            "extensions": self.get_file_extensions(),
            "features": self.get_supported_features(),
            "author": "tree-sitter-analyzer team",
            "description": "Comprehensive Rust language analysis plugin",
            "tree_sitter_version": ts_rust.__version__ if hasattr(ts_rust, '__version__') else "unknown"
        }
```

### 2.2 クエリ定義の実装

```python
    def get_query_definitions(self) -> Dict[str, str]:
        """Tree-sitterクエリ定義を返す"""
        return {
            "functions": """
                (function_item
                    name: (identifier) @function.name
                    parameters: (parameters) @function.params
                    body: (block) @function.body
                ) @function.definition
            """,
            
            "structs": """
                (struct_item
                    name: (type_identifier) @struct.name
                    body: (field_declaration_list) @struct.body
                ) @struct.definition
            """,
            
            "enums": """
                (enum_item
                    name: (type_identifier) @enum.name
                    body: (enum_variant_list) @enum.body
                ) @enum.definition
            """,
            
            "traits": """
                (trait_item
                    name: (type_identifier) @trait.name
                    body: (declaration_list) @trait.body
                ) @trait.definition
            """,
            
            "implementations": """
                (impl_item
                    trait: (type_identifier)? @impl.trait
                    type: (type_identifier) @impl.type
                    body: (declaration_list) @impl.body
                ) @impl.definition
            """,
            
            "modules": """
                (mod_item
                    name: (identifier) @module.name
                    body: (declaration_list)? @module.body
                ) @module.definition
            """,
            
            "constants": """
                (const_item
                    name: (identifier) @const.name
                    type: (_) @const.type
                    value: (_) @const.value
                ) @const.definition
            """,
            
            "variables": """
                (let_declaration
                    pattern: (identifier) @var.name
                    type: (_)? @var.type
                    value: (_)? @var.value
                ) @var.definition
            """
        }
```

### 2.3 解析メソッドの実装

```python
    def analyze_file(self, file_path: str, request: AnalysisRequest) -> AnalysisResult:
        """ファイルを解析して結果を返す"""
        import time
        from pathlib import Path
        
        start_time = time.time()
        
        try:
            # ファイル読み込み
            source_code = Path(file_path).read_text(encoding='utf-8')
            
            # パース実行
            tree = self.parser.parse(source_code.encode('utf-8'))
            
            if tree.root_node.has_error:
                raise ParseError(f"Parse error in {file_path}")
            
            # 結果オブジェクトの初期化
            result = AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                functions=[],
                classes=[],
                variables=[],
                imports=[],
                metadata={}
            )
            
            # 要求された解析タイプに応じて処理
            for query_type in request.query_types:
                if query_type == "functions":
                    result.functions = self._extract_functions(tree, source_code)
                elif query_type == "structs":
                    result.classes = self._extract_structs(tree, source_code)
                elif query_type == "enums":
                    result.metadata["enums"] = self._extract_enums(tree, source_code)
                elif query_type == "traits":
                    result.metadata["traits"] = self._extract_traits(tree, source_code)
                elif query_type == "implementations":
                    result.metadata["implementations"] = self._extract_implementations(tree, source_code)
                elif query_type == "modules":
                    result.metadata["modules"] = self._extract_modules(tree, source_code)
                elif query_type == "constants":
                    result.metadata["constants"] = self._extract_constants(tree, source_code)
                elif query_type == "variables":
                    result.variables = self._extract_variables(tree, source_code)
            
            # パフォーマンス記録
            parse_time = time.time() - start_time
            self._performance_metrics["parse_count"] += 1
            self._performance_metrics["total_parse_time"] += parse_time
            
            result.metadata["parse_time"] = parse_time
            result.metadata["node_count"] = self._count_nodes(tree.root_node)
            
            return result
            
        except Exception as e:
            self._performance_metrics["error_count"] += 1
            raise ParseError(f"Failed to analyze {file_path}: {str(e)}")
```

### 2.4 要素抽出メソッドの実装

```python
    def _extract_functions(self, tree: tree_sitter.Tree, source_code: str) -> List[ModelFunction]:
        """関数定義を抽出"""
        from tree_sitter_analyzer.models import ModelFunction
        
        functions = []
        query = self._get_compiled_query("functions")
        captures = query.captures(tree.root_node)
        
        for node, capture_name in captures:
            if capture_name == "function.definition":
                func_name = self._extract_function_name(node, source_code)
                if func_name:
                    function = ModelFunction(
                        name=func_name,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        start_column=node.start_point[1],
                        end_column=node.end_point[1],
                        docstring=self._extract_function_docstring(node, source_code),
                        parameters=self._extract_function_parameters(node, source_code),
                        return_type=self._extract_function_return_type(node, source_code),
                        is_async=False,  # Rustは非同期関数の概念が異なる
                        is_method=self._is_method(node),
                        visibility=self._extract_visibility(node, source_code),
                        metadata={
                            "is_unsafe": self._is_unsafe_function(node),
                            "is_extern": self._is_extern_function(node),
                            "generics": self._extract_generics(node, source_code)
                        }
                    )
                    functions.append(function)
        
        return functions
    
    def _extract_structs(self, tree: tree_sitter.Tree, source_code: str) -> List[ModelClass]:
        """構造体定義を抽出（クラスとして扱う）"""
        from tree_sitter_analyzer.models import ModelClass
        
        structs = []
        query = self._get_compiled_query("structs")
        captures = query.captures(tree.root_node)
        
        for node, capture_name in captures:
            if capture_name == "struct.definition":
                struct_name = self._extract_struct_name(node, source_code)
                if struct_name:
                    struct = ModelClass(
                        name=struct_name,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        start_column=node.start_point[1],
                        end_column=node.end_point[1],
                        docstring=self._extract_struct_docstring(node, source_code),
                        methods=[],  # implブロックから別途抽出
                        fields=self._extract_struct_fields(node, source_code),
                        base_classes=[],  # Rustには継承がない
                        is_abstract=False,
                        visibility=self._extract_visibility(node, source_code),
                        metadata={
                            "is_tuple_struct": self._is_tuple_struct(node),
                            "generics": self._extract_generics(node, source_code),
                            "derives": self._extract_derives(node, source_code)
                        }
                    )
                    structs.append(struct)
        
        return structs
```

### 2.5 ヘルパーメソッドの実装

```python
    def _get_compiled_query(self, query_key: str) -> tree_sitter.Query:
        """コンパイル済みクエリを取得（キャッシュ利用）"""
        if query_key not in self._query_cache:
            query_definitions = self.get_query_definitions()
            if query_key not in query_definitions:
                raise UnsupportedQueryError(f"Query '{query_key}' not supported for Rust")
            
            query_string = query_definitions[query_key]
            self._query_cache[query_key] = self.language.query(query_string)
        
        return self._query_cache[query_key]
    
    def _extract_function_name(self, node: tree_sitter.Node, source_code: str) -> Optional[str]:
        """関数名を抽出"""
        for child in node.children:
            if child.type == "identifier":
                return source_code[child.start_byte:child.end_byte]
        return None
    
    def _extract_function_parameters(self, node: tree_sitter.Node, source_code: str) -> List[str]:
        """関数パラメータを抽出"""
        parameters = []
        for child in node.children:
            if child.type == "parameters":
                for param_child in child.children:
                    if param_child.type == "parameter":
                        param_text = source_code[param_child.start_byte:param_child.end_byte]
                        parameters.append(param_text)
        return parameters
    
    def _extract_visibility(self, node: tree_sitter.Node, source_code: str) -> str:
        """可視性を抽出"""
        # Rustの可視性修飾子をチェック
        for child in node.children:
            if child.type == "visibility_modifier":
                return source_code[child.start_byte:child.end_byte]
        return "private"  # デフォルトはprivate
    
    def _is_unsafe_function(self, node: tree_sitter.Node) -> bool:
        """unsafe関数かどうかを判定"""
        for child in node.children:
            if child.type == "unsafe" and child.text.decode() == "unsafe":
                return True
        return False
    
    def _extract_generics(self, node: tree_sitter.Node, source_code: str) -> List[str]:
        """ジェネリクスパラメータを抽出"""
        generics = []
        for child in node.children:
            if child.type == "type_parameters":
                for param in child.children:
                    if param.type == "type_identifier":
                        generics.append(source_code[param.start_byte:param.end_byte])
        return generics
    
    def _count_nodes(self, node: tree_sitter.Node) -> int:
        """ノード数をカウント"""
        count = 1
        for child in node.children:
            count += self._count_nodes(child)
        return count
```

---

## 🎨 Step 3: フォーマッターの実装

### 3.1 基本フォーマッタークラス

```python
# tree_sitter_analyzer/formatters/rust.py
from typing import Dict, List, Any
from tree_sitter_analyzer.formatters.base import BaseFormatter
from tree_sitter_analyzer.models import AnalysisResult, ModelFunction, ModelClass

class RustFormatter(BaseFormatter):
    """Rust言語用フォーマッター"""
    
    def __init__(self, format_type: str = "table"):
        super().__init__(format_type)
        self.language = "rust"
    
    def format_functions(self, functions: List[ModelFunction]) -> str:
        """関数リストをフォーマット"""
        if self.format_type == "table":
            return self._format_functions_table(functions)
        elif self.format_type == "json":
            return self._format_functions_json(functions)
        elif self.format_type == "csv":
            return self._format_functions_csv(functions)
        else:
            return self._format_functions_simple(functions)
    
    def _format_functions_table(self, functions: List[ModelFunction]) -> str:
        """テーブル形式で関数をフォーマット"""
        if not functions:
            return "No functions found."
        
        # ヘッダー
        output = ["# Rust Functions\n"]
        output.append("| Name | Visibility | Parameters | Return Type | Line | Unsafe | Extern |")
        output.append("|------|------------|------------|-------------|------|--------|--------|")
        
        # 関数データ
        for func in functions:
            visibility = func.metadata.get("visibility", "private")
            params = ", ".join(func.parameters) if func.parameters else "-"
            return_type = func.return_type or "-"
            is_unsafe = "✓" if func.metadata.get("is_unsafe", False) else "-"
            is_extern = "✓" if func.metadata.get("is_extern", False) else "-"
            
            output.append(
                f"| `{func.name}` | {visibility} | `{params}` | `{return_type}` | "
                f"{func.start_line} | {is_unsafe} | {is_extern} |"
            )
        
        return "\n".join(output)
    
    def _format_structs_table(self, structs: List[ModelClass]) -> str:
        """テーブル形式で構造体をフォーマット"""
        if not structs:
            return "No structs found."
        
        output = ["# Rust Structs\n"]
        output.append("| Name | Visibility | Fields | Generics | Line | Derives |")
        output.append("|------|------------|--------|----------|------|---------|")
        
        for struct in structs:
            visibility = struct.metadata.get("visibility", "private")
            fields_count = len(struct.fields)
            generics = ", ".join(struct.metadata.get("generics", []))
            derives = ", ".join(struct.metadata.get("derives", []))
            
            output.append(
                f"| `{struct.name}` | {visibility} | {fields_count} | "
                f"`{generics or '-'}` | {struct.start_line} | `{derives or '-'}` |"
            )
        
        return "\n".join(output)
```

### 3.2 プラグインでのフォーマッター作成

```python
# RustPluginクラスに追加
    def create_formatter(self, format_type: str) -> BaseFormatter:
        """指定されたフォーマット種別のフォーマッターを作成"""
        from tree_sitter_analyzer.formatters.rust import RustFormatter
        return RustFormatter(format_type)
```

---

## 🧪 Step 4: テストケースの作成

### 4.1 基本テストクラス

```python
# tests/test_languages/test_rust_plugin.py
import pytest
from pathlib import Path
from tree_sitter_analyzer.languages.rust import RustPlugin
from tree_sitter_analyzer.models import AnalysisRequest

class TestRustPlugin:
    """Rustプラグインのテストクラス"""
    
    @pytest.fixture
    def plugin(self):
        return RustPlugin()
    
    @pytest.fixture
    def sample_rust_file(self, tmp_path):
        content = '''
fn main() {
    println!("Hello, world!");
}

pub fn add(a: i32, b: i32) -> i32 {
    a + b
}

unsafe fn dangerous_function() {
    // unsafe code here
}

struct Person {
    name: String,
    age: u32,
}

impl Person {
    pub fn new(name: String, age: u32) -> Self {
        Person { name, age }
    }
    
    fn greet(&self) {
        println!("Hello, {}", self.name);
    }
}

enum Color {
    Red,
    Green,
    Blue,
}

trait Drawable {
    fn draw(&self);
}
        '''
        file_path = tmp_path / "sample.rs"
        file_path.write_text(content)
        return str(file_path)
    
    def test_language_name(self, plugin):
        assert plugin.get_language_name() == "rust"
    
    def test_file_extensions(self, plugin):
        extensions = plugin.get_file_extensions()
        assert ".rs" in extensions
    
    def test_is_applicable(self, plugin):
        assert plugin.is_applicable("test.rs") is True
        assert plugin.is_applicable("test.py") is False
    
    def test_supported_features(self, plugin):
        features = plugin.get_supported_features()
        expected_features = [
            "functions", "structs", "enums", "traits", 
            "implementations", "modules", "constants", "variables"
        ]
        for feature in expected_features:
            assert feature in features
    
    def test_query_definitions(self, plugin):
        queries = plugin.get_query_definitions()
        assert "functions" in queries
        assert "structs" in queries
        assert "enums" in queries
        assert "traits" in queries
    
    def test_analyze_functions(self, plugin, sample_rust_file):
        request = AnalysisRequest(query_types=["functions"])
        result = plugin.analyze_file(sample_rust_file, request)
        
        functions = result.functions
        assert len(functions) >= 4  # main, add, dangerous_function, new, greet
        
        # main関数のテスト
        main_func = next((f for f in functions if f.name == "main"), None)
        assert main_func is not None
        assert main_func.start_line > 0
        
        # add関数のテスト
        add_func = next((f for f in functions if f.name == "add"), None)
        assert add_func is not None
        assert add_func.return_type == "i32"
        assert len(add_func.parameters) == 2
        
        # unsafe関数のテスト
        unsafe_func = next((f for f in functions if f.name == "dangerous_function"), None)
        assert unsafe_func is not None
        assert unsafe_func.metadata.get("is_unsafe") is True
    
    def test_analyze_structs(self, plugin, sample_rust_file):
        request = AnalysisRequest(query_types=["structs"])
        result = plugin.analyze_file(sample_rust_file, request)
        
        structs = result.classes  # 構造体はclassesとして扱う
        assert len(structs) >= 1
        
        person_struct = next((s for s in structs if s.name == "Person"), None)
        assert person_struct is not None
        assert len(person_struct.fields) == 2  # name, age
    
    def test_plugin_info(self, plugin):
        info = plugin.get_plugin_info()
        assert info["name"] == "Rust Language Plugin"
        assert info["language"] == "rust"
        assert ".rs" in info["extensions"]
        assert "functions" in info["features"]
    
    def test_performance_metrics(self, plugin, sample_rust_file):
        # 複数回解析してパフォーマンスメトリクスをテスト
        request = AnalysisRequest(query_types=["functions"])
        
        for _ in range(3):
            plugin.analyze_file(sample_rust_file, request)
        
        metrics = plugin.get_performance_metrics()
        assert metrics["parse_count"] == 3
        assert metrics["total_parse_time"] > 0
        assert metrics["error_count"] == 0
```

### 4.2 スナップショットテスト

```python
# tests/snapshots/test_rust_snapshots.py
import pytest
from tree_sitter_analyzer.testing.snapshot import SnapshotTester

class TestRustSnapshots:
    """Rustプラグインのスナップショットテスト"""
    
    @pytest.fixture
    def snapshot_tester(self):
        return SnapshotTester("rust")
    
    def test_function_extraction_snapshot(self, snapshot_tester):
        sample_code = '''
fn simple_function() {
    println!("Hello");
}

pub fn public_function(param: &str) -> String {
    format!("Hello, {}", param)
}

unsafe fn unsafe_function() -> *const u8 {
    std::ptr::null()
}

fn generic_function<T>(value: T) -> T {
    value
}
        '''
        
        result = snapshot_tester.analyze_code(sample_code, ["functions"])
        snapshot_tester.assert_matches_snapshot("rust_functions", result)
    
    def test_struct_extraction_snapshot(self, snapshot_tester):
        sample_code = '''
struct SimpleStruct {
    field1: String,
    field2: i32,
}

pub struct PublicStruct<T> {
    data: T,
}

#[derive(Debug, Clone)]
struct DerivedStruct {
    value: u64,
}

struct TupleStruct(String, i32);
        '''
        
        result = snapshot_tester.analyze_code(sample_code, ["structs"])
        snapshot_tester.assert_matches_snapshot("rust_structs", result)
```

---

## 📝 Step 5: ドキュメントの更新

### 5.1 README.mdの更新

```markdown
## 対応言語

| 言語 | 拡張子 | 機能 | 状態 |
|------|--------|------|------|
| Python | .py, .pyi | 関数、クラス、変数、インポート | ✅ 完全対応 |
| JavaScript | .js, .mjs | 関数、クラス、変数、インポート | ✅ 完全対応 |
| TypeScript | .ts, .tsx | 関数、クラス、インターフェース、型 | ✅ 完全対応 |
| Java | .java | クラス、メソッド、フィールド、インポート | ✅ 完全対応 |
| Markdown | .md | ヘッダー、リンク、コードブロック | ✅ 完全対応 |
| HTML | .html, .htm | 要素、属性、構造 | 🚧 開発中 |
| **Rust** | **.rs** | **関数、構造体、列挙型、トレイト** | **✅ 新規追加** |
```

### 5.2 使用例の追加

```markdown
### Rust解析の例

```bash
# Rust関数の解析
tree-sitter-analyzer query examples/sample.rs --query functions

# Rust構造体の解析
tree-sitter-analyzer query examples/sample.rs --query structs

# 複数要素の解析
tree-sitter-analyzer query examples/sample.rs --query functions,structs,enums
```
```

### 5.3 設定ファイルの更新

```python
# tree_sitter_analyzer/__init__.py
# バージョン更新
__version__ = "1.3.0"  # Rust対応追加

# setup.py または pyproject.toml
# 依存関係の追加
dependencies = [
    "tree-sitter>=0.20.0",
    "tree-sitter-languages>=1.5.0",
    "tree-sitter-rust>=0.20.0",  # 新規追加
    # ... 他の依存関係
]
```

---

## 🔧 Step 6: 高度なカスタマイズ

### 6.1 カスタムクエリの追加

```python
# より複雑なクエリの例
def get_advanced_query_definitions(self) -> Dict[str, str]:
    """高度なクエリ定義"""
    return {
        "async_functions": """
            (function_item
                (function_modifiers
                    "async" @async.modifier
                )
                name: (identifier) @async.function.name
            ) @async.function.definition
        """,
        
        "generic_structs": """
            (struct_item
                name: (type_identifier) @generic.struct.name
                type_parameters: (type_parameters) @generic.params
            ) @generic.struct.definition
        """,
        
        "macro_definitions": """
            (macro_definition
                name: (identifier) @macro.name
                parameters: (macro_rule)* @macro.rules
            ) @macro.definition
        """,
        
        "use_statements": """
            (use_declaration
                argument: (use_clause) @use.clause
            ) @use.statement
        """
    }
```

### 6.2 エラーハンドリングの強化

```python
def analyze_file_with_recovery(self, file_path: str, request: AnalysisRequest) -> AnalysisResult:
    """エラー回復機能付きファイル解析"""
    try:
        return self.analyze_file(file_path, request)
    