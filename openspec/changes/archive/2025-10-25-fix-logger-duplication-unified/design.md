# Design: ログ出力重複問題の修正

## アーキテクチャ概要

### 現在のアーキテクチャの問題

```
現在の状況：
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ start_mcp_server│    │   mcp/server    │    │  mcp/tools/*    │
│                 │    │                 │    │                 │
│ setup_logger()  │    │ setup_logger()  │    │ setup_logger()  │
│ ↓               │    │ ↓               │    │ ↓               │
│ Logger A        │    │ Logger B        │    │ Logger C, D, E  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
          │                       │                       │
          ↓                       ↓                       ↓
    [重複ハンドラー]        [重複ハンドラー]        [重複ハンドラー]
          │                       │                       │
          └───────────┬───────────┘───────────────────────┘
                      ↓
              [同じログメッセージを複数回出力]
```

### 提案するアーキテクチャ

```
改善後：
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ start_mcp_server│    │   mcp/server    │    │  mcp/tools/*    │
│                 │    │                 │    │                 │
│ setup_logger()  │    │ setup_logger()  │    │ setup_logger()  │
│ ↓               │    │ ↓               │    │ ↓               │
│ LoggerManager   │    │ LoggerManager   │    │ LoggerManager   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
          │                       │                       │
          └───────────┬───────────┘───────────────────────┘
                      ↓
              ┌───────────────────┐
              │  LoggerManager    │
              │  (Singleton)      │
              │                   │
              │ ┌───────────────┐ │
              │ │ Logger Cache  │ │
              │ │ - main        │ │
              │ │ - performance │ │
              │ │ - mcp.server  │ │
              │ └───────────────┘ │
              └───────────────────┘
                      │
                      ↓
              [統一されたログ出力]
```

## 設計決定とトレードオフ

### 決定1: シングルトンパターンの採用

**判断根拠**:
- ロガーインスタンスの一意性保証
- グローバルアクセスの簡素化
- 既存コードへの影響最小化

**トレードオフ**:
- **利点**: 
  - 重複ハンドラーの完全防止
  - メモリ使用量削減
  - 設定管理の集約化
- **欠点**:
  - テスタビリティの若干の低下
  - 並行処理時の考慮事項増加
- **選択理由**: 利点が欠点を大きく上回り、テスト用の初期化メソッドで緩和可能

### 決定2: 既存APIの完全保持

**判断根拠**:
- 後方互換性の維持
- 移行リスクの最小化
- 段階的改善の実現

**トレードオフ**:
- **利点**:
  - 既存コードの修正不要
  - リグレッションリスク最小
  - 学習コストゼロ
- **欠点**:
  - 内部実装の複雑化
  - 完全な設計刷新の機会損失
- **選択理由**: 安定性とリスク管理を優先

### 決定3: 段階的移行戦略

**判断根拠**:
- リスク分散
- 早期問題発見
- 継続的価値提供

**段階設計**:
```
Phase 1: 基盤実装
├── LoggerManager実装
├── 重複検出機能
└── setup_logger改善

Phase 2: パフォーマンス統一
├── 重複ロガー削除
└── 設定標準化

Phase 3: モジュール統一
├── MCPサーバー修正
├── 起動スクリプト修正
└── ツール群修正

Phase 4: 品質保証
├── テスト実装
├── ドキュメント更新
└── 性能検証
```

## 詳細設計

### LoggerManagerクラス設計

```python
class LoggerManager:
    """
    統一されたロガー管理クラス
    
    シングルトンパターンでロガーインスタンスを管理し、
    重複ハンドラーを防止する。
    """
    
    _instance: Optional['LoggerManager'] = None
    _lock: threading.Lock = threading.Lock()
    _loggers: Dict[str, logging.Logger] = {}
    _handler_registry: Dict[str, List[str]] = {}
    
    def __new__(cls) -> 'LoggerManager':
        """スレッドセーフなシングルトン実装"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_logger(self, name: str, **kwargs) -> logging.Logger:
        """重複を防ぐロガー取得"""
        if name not in self._loggers:
            self._loggers[name] = self._create_logger(name, **kwargs)
        return self._loggers[name]
    
    def _create_logger(self, name: str, **kwargs) -> logging.Logger:
        """ロガー作成とハンドラー設定"""
        logger = logging.getLogger(name)
        
        # 重複ハンドラーチェック
        if not self._has_handlers(logger, name):
            self._setup_handlers(logger, name, **kwargs)
            
        return logger
    
    def _has_handlers(self, logger: logging.Logger, name: str) -> bool:
        """ハンドラー重複チェック"""
        handler_types = [type(h).__name__ for h in logger.handlers]
        
        if name in self._handler_registry:
            existing_types = self._handler_registry[name]
            return any(ht in existing_types for ht in handler_types)
        
        self._handler_registry[name] = handler_types
        return len(handler_types) > 0
    
    def reset_for_testing(self) -> None:
        """テスト用リセット機能"""
        self._loggers.clear()
        self._handler_registry.clear()
```

### ハンドラー管理戦略

```python
class HandlerManager:
    """ハンドラー重複管理クラス"""
    
    @staticmethod
    def get_handler_fingerprint(handler: logging.Handler) -> str:
        """ハンドラーのフィンガープリント生成"""
        return f"{type(handler).__name__}:{getattr(handler, 'baseFilename', 'console')}"
    
    @staticmethod
    def is_duplicate_handler(logger: logging.Logger, new_handler: logging.Handler) -> bool:
        """重複ハンドラーチェック"""
        new_fingerprint = HandlerManager.get_handler_fingerprint(new_handler)
        existing_fingerprints = [
            HandlerManager.get_handler_fingerprint(h) for h in logger.handlers
        ]
        return new_fingerprint in existing_fingerprints
```

## 性能影響分析

### メモリ使用量

```
修正前:
- N個のロガーインスタンス × M個のハンドラー = N×M個のオブジェクト
- 重複設定による無駄なメモリ使用

修正後:
- 1個のLoggerManager + 最適化されたロガー数
- 約30-50%のメモリ使用量削減見込み
```

### 処理性能

```
修正前:
- 各ロガー作成時の重複処理
- ハンドラー重複による処理オーバーヘッド

修正後:
- 初回作成時のわずかなオーバーヘッド
- 以降は最適化されたアクセス
- 全体で10-20%の性能向上見込み
```

## セキュリティ考慮事項

### スレッドセーフティ

```python
# 並行アクセス対策
_lock = threading.Lock()

def get_logger(self, name: str) -> logging.Logger:
    with self._lock:
        # クリティカルセクション
        return self._get_or_create_logger(name)
```

### リソース管理

```python
def cleanup(self) -> None:
    """リソースクリーンアップ"""
    for logger in self._loggers.values():
        for handler in logger.handlers:
            handler.close()
            logger.removeHandler(handler)
    self._loggers.clear()
```

## 品質保証戦略

### 単体テスト設計

1. **LoggerManager動作テスト**
   - シングルトン保証テスト
   - ロガー重複防止テスト
   - ハンドラー重複防止テスト

2. **パフォーマンステスト**
   - メモリ使用量測定
   - 処理時間測定
   - 並行アクセステスト

3. **統合テスト**
   - MCPサーバー起動テスト
   - ログ出力一貫性テスト
   - エラーシナリオテスト

### 回帰テスト戦略

```python
class LoggerRegressionTest:
    """回帰テスト実装例"""
    
    def test_no_duplicate_logs(self):
        """ログ重複がないことを確認"""
        with capture_logs() as logs:
            # 複数モジュールでロガー使用
            start_server_logger()
            mcp_server_logger()
            tools_logger()
            
        # 重複メッセージチェック
        assert_no_duplicate_messages(logs)
    
    def test_api_compatibility(self):
        """既存API互換性確認"""
        # 既存のsetup_logger呼び出しが動作することを確認
        logger1 = setup_logger("test1")
        logger2 = setup_logger("test2") 
        
        assert logger1 != logger2
        assert isinstance(logger1, logging.Logger)
```

## 移行計画

### フェーズごとの検証ポイント

**Phase 1完了時**:
- LoggerManagerのシングルトン動作確認
- 基本的なログ出力動作確認
- 既存テストの通過確認

**Phase 2完了時**:
- パフォーマンスロガーの統一確認
- 性能回帰がないことの確認
- パフォーマンステストの通過

**Phase 3完了時**:
- MCPサーバー正常起動確認
- ログ重複完全除去の確認
- 全モジュール統合テストの通過

**Phase 4完了時**:
- 全テストスイートの通過
- ドキュメント整合性確認
- 本番環境での動作確認

## まとめ

この設計により、以下を実現できます：

1. **技術的目標**
   - ログ重複の完全除去
   - システム性能の向上
   - コードの保守性向上

2. **品質目標**
   - 既存機能の完全保持
   - 高い信頼性の維持
   - 十分なテストカバレッジ

3. **運用目標**
   - 透明な移行プロセス
   - 最小限のダウンタイム
   - 容易なロールバック可能性

設計の核心は「最小侵襲的改善」と「段階的品質向上」にあり、リスクを最小化しながら確実な改善を実現します。