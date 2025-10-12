# 条件分岐削除計画書

## 🎯 目標
**54件の言語固有条件分岐を段階的に削除し、プラグインベースの統一アーキテクチャに移行**

## 📊 現状分析

### 条件分岐の分布
| ファイル | 条件分岐数 | 影響度 | 複雑度 |
|---------|-----------|--------|--------|
| `query_service.py` | 9件 | **極高** | **極高** |
| `analysis_engine.py` | 1件 | 高 | 中 |
| その他44ファイル | 44件 | 中-低 | 低-中 |

### 詳細分析結果

#### 🔥 最優先：`query_service.py`（9件）
```python
# 現在の問題のある実装例
if language == "java":
    # Java固有処理
elif language == "python":
    # Python固有処理
elif language in ["javascript", "typescript"]:
    # JavaScript/TypeScript固有処理
elif language == "markdown":
    # Markdown固有処理
```

**問題点:**
- 新言語追加時に必ずコア修正が必要
- テストケースが言語数に比例して増加
- 保守性が著しく低下

## 🚀 段階的削除戦略

### Phase 1: 最優先削除（1-2週間）
**対象**: `query_service.py`の9件の条件分岐

#### 1.1 現在の条件分岐詳細
```python
# tree_sitter_analyzer/core/query_service.py

# 条件分岐 #1-4: クエリ実行ロジック（214-235行）
if language == "java":
    return self._execute_java_query(query_key, node, source_code)
elif language == "python":
    return self._execute_python_query(query_key, node, source_code)
elif language in ["javascript", "typescript"]:
    return self._execute_js_ts_query(query_key, node, source_code)
elif language == "markdown":
    return self._execute_markdown_query(query_key, node, source_code)

# 条件分岐 #5-9: 結果処理ロジック（279-307行）
elif language == "python":
    return self._process_python_result(node, query_key)
elif language in ["javascript", "typescript"]:
    return self._process_js_ts_result(node, query_key)
elif query_key in ["interface", "interfaces"] and language == "typescript":
    return self._process_typescript_interface(node)
elif query_key in ["type", "types"] and language == "typescript":
    return self._process_typescript_type(node)
elif language == "java":
    return self._process_java_result(node, query_key)
```

#### 1.2 削除戦略
**新しい統一実装:**
```python
class UnifiedQueryService:
    """プラグインベースの統一クエリサービス"""
    
    def __init__(self, plugin_manager: PluginManager):
        self.plugin_manager = plugin_manager
        self.query_engine = UnifiedQueryEngine(plugin_manager)
    
    def execute_query(self, language: str, query_key: str, node: Node, source_code: str):
        """条件分岐なしのクエリ実行"""
        return self.query_engine.execute_query(language, query_key, node, source_code)
    
    def process_result(self, language: str, query_key: str, raw_result: Any):
        """条件分岐なしの結果処理"""
        plugin = self.plugin_manager.get_plugin(language)
        if not plugin:
            raise UnsupportedLanguageError(f"No plugin for language: {language}")
        
        return plugin.process_query_result(query_key, raw_result)
```

### Phase 2: 中優先削除（2-3週間）
**対象**: `analysis_engine.py`の1件 + フォーマッター関連

#### 2.1 `analysis_engine.py`の条件分岐
```python
# 現在の実装（323行）
if result.language == "unknown" or not result.language:
    # 言語検出失敗時の処理
```

**削除戦略:**
```python
# 新しい実装
def handle_unknown_language(self, result: AnalysisResult) -> AnalysisResult:
    """言語不明時の統一処理"""
    # デフォルトプラグインまたはフォールバック処理
    default_plugin = self.plugin_manager.get_plugin("generic")
    return default_plugin.analyze_result(result)
```

#### 2.2 フォーマッター関連の条件分岐
**対象ファイル:**
- `formatter_factory.py`
- `language_formatter_factory.py`
- 各言語固有フォーマッター

**削除戦略:**
```python
class PluginBasedFormatterFactory:
    """プラグインベースのフォーマッターファクトリー"""
    
    def create_formatter(self, language: str, format_type: str):
        """条件分岐なしのフォーマッター作成"""
        plugin = self.plugin_manager.get_plugin(language)
        if plugin and hasattr(plugin, 'create_formatter'):
            return plugin.create_formatter(format_type)
        
        # フォールバック
        return self.create_generic_formatter(format_type)
```

### Phase 3: 低優先削除（3-4週間）
**対象**: その他44件の散在する条件分岐

#### 3.1 分類と優先順位
1. **API層の条件分岐** (高優先度)
   - `api.py`内の言語判定ロジック
   - CLI関連の言語固有処理

2. **ユーティリティ層の条件分岐** (中優先度)
   - `language_detector.py`の拡張子判定
   - `file_handler.py`の言語固有処理

3. **テスト関連の条件分岐** (低優先度)
   - テストケース内の言語固有分岐
   - モック作成時の言語判定

## 🔧 実装詳細

### 1. 統一クエリエンジンの実装

```python
# tree_sitter_analyzer/core/unified_query_engine.py

class UnifiedQueryEngine:
    """条件分岐を排除した統一クエリエンジン"""
    
    def execute_query(self, language: str, query_type: str, tree: Tree, source_code: str):
        """プラグインベースのクエリ実行"""
        
        # 1. プラグイン取得（条件分岐なし）
        plugin = self._get_validated_plugin(language)
        
        # 2. クエリサポート確認
        if not plugin.supports_query(query_type):
            raise UnsupportedQueryError(f"Query '{query_type}' not supported for {language}")
        
        # 3. クエリ定義取得
        query_def = plugin.get_query_definitions()[query_type]
        
        # 4. Tree-sitterクエリ実行
        raw_results = self._execute_tree_sitter_query(language, query_def, tree, source_code)
        
        # 5. プラグインによる後処理
        return plugin.process_query_result(query_type, raw_results)
    
    def _get_validated_plugin(self, language: str) -> EnhancedLanguagePlugin:
        """プラグイン取得と検証"""
        plugin = self.plugin_manager.get_plugin(language)
        
        if not plugin:
            raise UnsupportedLanguageError(f"No plugin found for language: {language}")
        
        if not isinstance(plugin, EnhancedLanguagePlugin):
            # 後方互換性: 旧プラグインのラッパー作成
            plugin = LegacyPluginWrapper(plugin)
        
        return plugin
```

### 2. レガシープラグインラッパー

```python
class LegacyPluginWrapper(EnhancedLanguagePlugin):
    """旧プラグインインターフェースのラッパー"""
    
    def __init__(self, legacy_plugin: LanguagePlugin):
        super().__init__()
        self.legacy_plugin = legacy_plugin
        self._config = self._create_config_from_legacy()
    
    def get_language_config(self) -> LanguageConfig:
        """レガシープラグインから設定を生成"""
        return LanguageConfig(
            name=self.legacy_plugin.get_language_name(),
            display_name=self.legacy_plugin.get_language_name().title(),
            extensions=self.legacy_plugin.get_file_extensions(),
            tree_sitter_language=self.legacy_plugin.get_language_name(),
            supported_queries=self._infer_supported_queries(),
            default_formatters=["json", "csv", "summary"]
        )
    
    def get_query_definitions(self) -> Dict[str, QueryDefinition]:
        """レガシープラグインからクエリ定義を推測"""
        # 既存のクエリファイルから定義を読み込み
        return self._load_legacy_queries()
    
    def create_formatter(self, format_type: str) -> BaseFormatter:
        """レガシーフォーマッターの作成"""
        # 既存のフォーマッターファクトリーを使用
        return self._create_legacy_formatter(format_type)
```

### 3. 段階的移行のためのフィーチャーフラグ

```python
# tree_sitter_analyzer/config/feature_flags.py

class FeatureFlags:
    """段階的移行のためのフィーチャーフラグ"""
    
    # Phase 1: クエリエンジン
    USE_UNIFIED_QUERY_ENGINE = True
    
    # Phase 2: フォーマッター
    USE_PLUGIN_BASED_FORMATTERS = False
    
    # Phase 3: 完全移行
    DISABLE_LEGACY_PLUGINS = False
    
    @classmethod
    def is_enabled(cls, flag_name: str) -> bool:
        """フラグの状態を確認"""
        return getattr(cls, flag_name, False)
```

## 📋 削除スケジュール

### Week 1-2: Phase 1実装
- [ ] `UnifiedQueryEngine`の実装
- [ ] `query_service.py`の9件の条件分岐削除
- [ ] 単体テストの作成
- [ ] 統合テストの実行

### Week 3-4: Phase 2実装
- [ ] `UnifiedFormatterFactory`の実装
- [ ] `analysis_engine.py`の条件分岐削除
- [ ] フォーマッター関連の条件分岐削除
- [ ] 回帰テストの実行

### Week 5-6: Phase 3実装
- [ ] API層の条件分岐削除
- [ ] ユーティリティ層の条件分岐削除
- [ ] レガシーコードの段階的削除

### Week 7-8: 最終検証
- [ ] 全機能の動作確認
- [ ] パフォーマンステスト
- [ ] ドキュメント更新
- [ ] リリース準備

## 🧪 テスト戦略

### 1. 段階的テスト
```python
class ConditionalBranchEliminationTest:
    """条件分岐削除のテスト"""
    
    def test_query_service_no_conditionals(self):
        """query_serviceに条件分岐がないことを確認"""
        source_code = self._read_file("tree_sitter_analyzer/core/query_service.py")
        
        # 言語固有の条件分岐パターンを検索
        patterns = [
            r'if\s+language\s*==',
            r'elif\s+language\s*==',
            r'language\s+in\s*\[',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, source_code)
            self.assertEqual(len(matches), 0, f"Found conditional branches: {matches}")
    
    def test_plugin_based_query_execution(self):
        """プラグインベースのクエリ実行をテスト"""
        for language in ["java", "python", "javascript"]:
            with self.subTest(language=language):
                result = self.unified_query_engine.execute_query(
                    language, "function", self.sample_tree, self.sample_code
                )
                self.assertIsNotNone(result)
```

### 2. 後方互換性テスト
```python
def test_backward_compatibility(self):
    """既存APIとの互換性を確認"""
    # 既存のAPIが引き続き動作することを確認
    old_result = self.legacy_query_service.execute_query(...)
    new_result = self.unified_query_service.execute_query(...)
    
    self.assertEqual(old_result, new_result)
```

## 📊 成功指標

### 定量的指標
- **条件分岐数**: 54件 → 0件
- **コード行数削減**: 推定500行削減
- **テスト実行時間**: 現状維持または改善
- **メモリ使用量**: 現状維持または改善

### 定性的指標
- **新言語追加時間**: 数日 → 数時間
- **コードの可読性**: 大幅改善
- **保守性**: 大幅改善
- **テスト容易性**: 大幅改善

## 🚨 リスク管理

### 高リスク
1. **既存機能の破綻**: 段階的移行とテストで軽減
2. **パフォーマンス劣化**: ベンチマークテストで監視
3. **後方互換性の破綻**: ラッパークラスで対応

### 中リスク
1. **移行期間の長期化**: 明確なマイルストーンで管理
2. **チーム学習コスト**: ドキュメント整備で軽減

### 低リスク
1. **新バグの混入**: 包括的テストで検出
2. **設計の不備**: プロトタイプで事前検証

この計画により、54件の条件分岐を段階的かつ安全に削除し、真に拡張可能なアーキテクチャを実現します。