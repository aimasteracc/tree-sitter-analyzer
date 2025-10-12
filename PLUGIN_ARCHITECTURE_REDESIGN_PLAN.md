# 言語プラグインアーキテクチャ再設計計画書

## 📋 現状分析サマリー

### 🔍 発見された問題点
1. **54件の言語固有条件分岐**が散在（特に`query_service.py`に9件集中）
2. **プラグインマネージャーは実装済み**だが、コアロジックで十分活用されていない
3. **各言語プラグインは独立実装**で一貫性に欠ける
4. **フォーマッターに言語固有ロジック**が混在

### ✅ 既存の優秀な設計
- **`plugins/base.py`**: 529行、複雑度86の充実したプラグインベースクラス
- **`plugins/manager.py`**: 379行、複雑度69の高機能プラグインマネージャー
- **言語プラグイン**: 6言語（Java, Python, JavaScript, TypeScript, HTML, Markdown）が実装済み

## 🎯 段階的移行戦略

### Phase 1: プラグインインターフェース拡張（1-2週間）
**目標**: 既存プラグインシステムを拡張し、条件分岐削除の基盤を構築

#### 1.1 拡張プラグインインターフェース設計
```python
class EnhancedLanguagePlugin(LanguagePlugin):
    """拡張言語プラグインインターフェース"""
    
    @abstractmethod
    def get_query_definitions(self) -> Dict[str, str]:
        """言語固有のクエリ定義を返す"""
        pass
    
    @abstractmethod
    def create_formatter(self, format_type: str) -> BaseFormatter:
        """言語固有のフォーマッターを作成"""
        pass
    
    @abstractmethod
    def get_language_config(self) -> LanguageConfig:
        """言語設定を返す"""
        pass
    
    def supports_query(self, query_key: str) -> bool:
        """特定のクエリをサポートするかチェック"""
        return query_key in self.get_query_definitions()
```

#### 1.2 統一設定システム
```python
@dataclass
class LanguageConfig:
    """言語設定の統一データクラス"""
    name: str
    extensions: List[str]
    tree_sitter_language: str
    supported_queries: List[str]
    default_formatters: List[str]
    special_handling: Dict[str, Any] = field(default_factory=dict)
```

### Phase 2: 条件分岐削除（2-3週間）
**目標**: `query_service.py`の9件の条件分岐を段階的に削除

#### 2.1 優先順位付け
1. **高優先度**: `query_service.py`の条件分岐（9件）
2. **中優先度**: `analysis_engine.py`の条件分岐（1件）
3. **低優先度**: その他ファイルの条件分岐（44件）

#### 2.2 統一クエリエンジン設計
```python
class UnifiedQueryEngine:
    """言語非依存の統一クエリエンジン"""
    
    def __init__(self, plugin_manager: PluginManager):
        self.plugin_manager = plugin_manager
        self.query_cache: Dict[str, str] = {}
    
    def execute_query(self, language: str, query_key: str, node: Node) -> List[QueryResult]:
        """プラグインベースのクエリ実行"""
        plugin = self.plugin_manager.get_plugin(language)
        if not plugin:
            raise UnsupportedLanguageError(f"No plugin for language: {language}")
        
        query_def = plugin.get_query_definitions().get(query_key)
        if not query_def:
            raise UnsupportedQueryError(f"Query '{query_key}' not supported for {language}")
        
        return self._execute_tree_sitter_query(query_def, node)
```

### Phase 3: フォーマッター統合（2-3週間）
**目標**: 言語固有フォーマッターをプラグインシステムに統合

#### 3.1 統一フォーマッターファクトリー
```python
class PluginBasedFormatterFactory:
    """プラグインベースのフォーマッターファクトリー"""
    
    def create_formatter(self, language: str, format_type: str) -> BaseFormatter:
        plugin = self.plugin_manager.get_plugin(language)
        if plugin and hasattr(plugin, 'create_formatter'):
            return plugin.create_formatter(format_type)
        
        # フォールバック: 汎用フォーマッター
        return GenericFormatter(format_type)
```

#### 3.2 既存フォーマッターの段階的移行
- `java_formatter.py` → `JavaPlugin.create_formatter()`
- `python_formatter.py` → `PythonPlugin.create_formatter()`
- `javascript_formatter.py` → `JavaScriptPlugin.create_formatter()`

### Phase 4: 言語プラグイン標準化（3-4週間）
**目標**: 既存言語プラグインを新インターフェースに準拠

#### 4.1 プラグイン移行順序
1. **Java**: 最も複雑（1,364行）→ 新アーキテクチャの実証
2. **Python**: 中程度の複雑さ → 汎用パターンの確立
3. **JavaScript/TypeScript**: 類似言語 → 効率的な移行
4. **HTML/Markdown**: 特殊言語 → エッジケース対応

#### 4.2 標準プラグイン構造
```
plugins/
├── core/
│   ├── enhanced_base.py          # 拡張ベースクラス
│   ├── unified_query_engine.py   # 統一クエリエンジン
│   └── plugin_formatter_factory.py # プラグインフォーマッターファクトリー
├── languages/
│   ├── java/
│   │   ├── plugin.py             # JavaEnhancedPlugin
│   │   ├── queries.py            # Java固有クエリ
│   │   ├── formatters.py         # Java固有フォーマッター
│   │   └── config.py             # Java言語設定
│   └── python/
│       ├── plugin.py
│       ├── queries.py
│       ├── formatters.py
│       └── config.py
└── config/
    └── language_registry.yaml    # 言語登録設定
```

## 🔄 移行戦略の詳細

### 後方互換性保証
1. **既存API維持**: 現在のAPIエンドポイントは変更しない
2. **段階的廃止**: 旧実装は`@deprecated`マークし、段階的に削除
3. **フォールバック機能**: 新プラグインが利用できない場合の旧実装フォールバック

### リスク軽減策
1. **並行開発**: 新システムを既存システムと並行して開発
2. **機能フラグ**: 新機能の段階的有効化
3. **包括的テスト**: 各段階でのスナップショットテスト実行

### 検証基準
- **機能性**: 既存機能の100%互換性
- **パフォーマンス**: 既存実装と同等以上
- **拡張性**: 新言語追加が1日以内で完了
- **保守性**: 条件分岐の完全排除

## 📊 実装スケジュール

| Phase | 期間 | 主要成果物 | 検証方法 |
|-------|------|-----------|----------|
| Phase 1 | 1-2週間 | 拡張プラグインインターフェース | 単体テスト |
| Phase 2 | 2-3週間 | 統一クエリエンジン | スナップショットテスト |
| Phase 3 | 2-3週間 | 統一フォーマッターシステム | 統合テスト |
| Phase 4 | 3-4週間 | 標準化された言語プラグイン | E2Eテスト |

## 🎯 成功指標

### 定量的指標
- **条件分岐削除**: 54件 → 0件
- **新言語追加時間**: 現在数日 → 1日以内
- **テストカバレッジ**: 90%以上維持
- **パフォーマンス**: 既存実装の95%以上

### 定性的指標
- **コード可読性**: 言語固有ロジックの明確な分離
- **拡張性**: プラグインベースの統一アーキテクチャ
- **保守性**: 新言語追加時の影響範囲最小化

## 🔧 次のステップ

1. **Phase 1開始**: 拡張プラグインインターフェースの実装
2. **プロトタイプ開発**: Java言語での新アーキテクチャ実証
3. **テスト戦略策定**: 段階的移行のためのテスト計画
4. **チーム調整**: 開発リソースの配分と役割分担

---

この計画により、tree-sitter-analyzerは真に拡張可能で保守容易なプラグインアーキテクチャを実現し、新言語サポートの追加が劇的に簡素化されます。