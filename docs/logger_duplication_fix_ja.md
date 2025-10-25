# ログ重複問題の修正：統一ログ管理システムの実装

## 概要

tree-sitter-analyzerプロジェクトにおいて、複数のモジュールが同時にログ設定を行うことで、ログメッセージが重複して出力される問題が発生していました。この文書では、問題の根本原因、実装した解決策、およびベストプラクティスについて詳しく説明します。

## 問題の分析

### 根本原因

従来のシステムでは、以下のモジュールがそれぞれ独立してログ設定を行っていました：

1. **start_mcp_server.py** - MCPサーバー起動時
2. **tree_sitter_analyzer/mcp/server.py** - MCPサーバー初期化時  
3. **各MCPツール** - ツール初期化時
4. **その他のモジュール** - 必要に応じて

この結果、同一のロガー名に対して複数のハンドラーが追加され、ログメッセージが重複して出力される問題が発生していました。

### 影響範囲

- **ユーザビリティ**: 重複ログによる可読性の低下
- **パフォーマンス**: 不要なログ処理によるオーバーヘッド
- **デバッグ効率**: ログの重複による問題特定の困難
- **ディスク使用量**: ファイルログ有効時の容量増加

## 実装した解決策

### 1. LoggerManagerシングルトンクラス

中央集権的なログ管理を実現するため、`LoggerManager`シングルトンクラスを実装しました。

```python
# tree_sitter_analyzer/logging_manager.py
class LoggerManager:
    """統一ログ管理システム"""
    
    _instance = None
    _lock = threading.Lock()
    _loggers = {}
    _handler_registry = {}
    _initialized = False
```

#### 主要機能

- **重複防止**: 同一ロガー名に対するハンドラーの重複登録を防止
- **スレッドセーフ**: マルチスレッド環境での安全な操作
- **設定統一**: プロジェクト全体での一貫したログ設定
- **メモリ効率**: ロガーインスタンスの再利用

### 2. 後方互換性の保持

既存の`setup_logger`関数を保持し、内部的に`LoggerManager`を使用するよう修正しました。

```python
def setup_logger(
    name: str = "tree_sitter_analyzer",
    level: str | int = "INFO"
) -> logging.Logger:
    """統一ログマネージャーを使用したロガー設定"""
    manager = get_logger_manager()
    return manager.get_logger(name, level)
```

### 3. SafeStreamHandlerの実装

MCP stdio通信との互換性を確保するため、安全なストリームハンドラーを実装しました。

```python
class SafeStreamHandler(logging.StreamHandler):
    """MCPサーバーのstdio通信に対応した安全なストリームハンドラー"""
    
    def emit(self, record):
        try:
            if hasattr(self.stream, 'closed') and self.stream.closed:
                return
            super().emit(record)
        except (AttributeError, ValueError, OSError):
            pass  # MCP stdio通信エラーを無視
```

## アーキテクチャ設計

### システム構成図

```
┌─────────────────────────────────────────┐
│              アプリケーション層           │
├─────────────────────────────────────────┤
│  start_mcp_server.py │ mcp/server.py    │
│  各MCPツール         │ その他モジュール │
├─────────────────────────────────────────┤
│              統一インターフェース         │
│           setup_logger()               │
├─────────────────────────────────────────┤
│              LoggerManager             │
│          (シングルトンパターン)          │
├─────────────────────────────────────────┤
│              Python logging           │
│    Logger │ Handler │ Formatter        │
└─────────────────────────────────────────┘
```

### データフロー

1. **初期化**: アプリケーション起動時にLoggerManagerが初期化
2. **ロガー要求**: 各モジュールがsetup_logger()を呼び出し
3. **重複チェック**: LoggerManagerが既存ロガーの存在確認
4. **設定適用**: 新規作成または既存インスタンス返却
5. **ログ出力**: 統一された設定でログメッセージを出力

## 技術的詳細

### スレッドセーフ実装

```python
def __new__(cls):
    if cls._instance is None:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
    return cls._instance
```

ダブルチェッキングロッキングパターンを使用し、マルチスレッド環境での安全性を確保しています。

### ハンドラー重複防止

```python
def _add_handler_if_not_exists(self, logger, handler_type, **kwargs):
    """重複しないハンドラーの追加"""
    handler_key = self._create_handler_key(logger.name, handler_type, **kwargs)
    
    if handler_key not in self._handler_registry:
        handler = self._create_handler(handler_type, **kwargs)
        logger.addHandler(handler)
        self._handler_registry[handler_key] = handler
```

ハンドラーレジストリを使用して、同一設定のハンドラー重複を防止しています。

### 環境変数サポート

- `LOG_LEVEL`: デフォルトログレベルの設定
- `TREE_SITTER_ANALYZER_ENABLE_FILE_LOG`: ファイルログの有効化
- `TREE_SITTER_ANALYZER_LOG_DIR`: ログファイル保存ディレクトリ

## 性能への影響

### ベンチマーク結果

- **ロガー作成時間**: 100ロガー作成が1秒以内
- **ロガー取得時間**: 1000回取得が0.1秒以内
- **メモリ使用量**: ロガーインスタンス再利用により削減
- **ログ重複**: 完全に排除

### 最適化ポイント

1. **インスタンス再利用**: 同名ロガーの再利用によるメモリ効率化
2. **レイジー初期化**: 必要時のみハンドラー作成
3. **キャッシュ戦略**: ハンドラーレジストリによる高速検索

## テスト戦略

### テストカバレッジ

実装した包括的なテストスイート：

- **シングルトンパターンテスト**: インスタンス一意性の確認
- **スレッドセーフテスト**: 並行アクセス時の安全性検証  
- **重複防止テスト**: ハンドラー重複の完全防止確認
- **後方互換性テスト**: 既存APIの動作継続確認
- **パフォーマンステスト**: 応答時間とメモリ使用量測定

### テスト実行

```bash
# ログ重複修正の専用テスト実行
python -m pytest tests/test_logger_duplication_fix.py -v

# 全テストスイート実行
python -m pytest tests/ -v
```

## 使用方法とベストプラクティス

### 基本的な使用方法

```python
from tree_sitter_analyzer.utils import setup_logger

# 標準的なロガー作成
logger = setup_logger("my_module")

# ログレベル指定
debug_logger = setup_logger("debug_module", "DEBUG")

# パフォーマンスロガー
from tree_sitter_analyzer.utils import create_performance_logger
perf_logger = create_performance_logger("performance_test")
```

### 推奨パターン

#### 1. モジュールレベルロガー

```python
# 各モジュールの先頭で
import logging
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)
```

#### 2. 条件付きロガー設定

```python
# 開発環境でのデバッグログ有効化
import os
level = "DEBUG" if os.getenv("DEBUG") else "INFO"
logger = setup_logger("my_app", level)
```

#### 3. パフォーマンス監視

```python
from tree_sitter_analyzer.utils import create_performance_logger

perf_logger = create_performance_logger("query_performance")
start_time = time.time()
# 処理実行
elapsed = time.time() - start_time
perf_logger.info(f"Query completed in {elapsed:.3f}s")
```

### アンチパターン（避けるべき実装）

```python
# ❌ 直接ロガー作成（重複の原因）
logger = logging.getLogger("my_logger")
handler = logging.StreamHandler()
logger.addHandler(handler)

# ❌ 複数回のsetup_logger呼び出し（同一モジュール内）
logger1 = setup_logger("test")
logger2 = setup_logger("test")  # 不要

# ✅ 正しいパターン
logger = setup_logger("test")  # 一度だけ呼び出し
```

## トラブルシューティング

### よくある問題と解決策

#### 1. ログが表示されない

**原因**: ログレベルの設定ミス

**解決策**:
```python
# 環境変数でレベル確認
import os
print(f"LOG_LEVEL: {os.getenv('LOG_LEVEL', 'INFO')}")

# 明示的レベル指定
logger = setup_logger("debug_test", "DEBUG")
```

#### 2. ファイルログが作成されない

**原因**: 環境変数が未設定またはディレクトリ権限不足

**解決策**:
```bash
# 環境変数設定
export TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true
export TREE_SITTER_ANALYZER_LOG_DIR=/writable/path

# ディレクトリ作成
mkdir -p /writable/path
chmod 755 /writable/path
```

#### 3. MCPサーバーでログエラー

**原因**: stdio通信との競合

**解決策**: SafeStreamHandlerが自動的に処理するため、追加設定不要

### デバッグ手法

#### LoggerManagerの状態確認

```python
from tree_sitter_analyzer.logging_manager import get_logger_manager

manager = get_logger_manager()
print(f"登録済みロガー数: {len(manager._loggers)}")
print(f"ハンドラー数: {len(manager._handler_registry)}")

# 登録済みロガー一覧
for name in manager._loggers.keys():
    print(f"ロガー: {name}")
```

#### ログレベル確認

```python
logger = setup_logger("test")
print(f"ロガーレベル: {logging.getLevelName(logger.level)}")
print(f"ハンドラー数: {len(logger.handlers)}")

for i, handler in enumerate(logger.handlers):
    print(f"ハンドラー{i}: {type(handler).__name__}")
```

## 今後の拡張計画

### 1. 構造化ログ対応

JSON形式でのログ出力サポート：

```python
# 将来の実装例
logger = setup_logger("api", format_type="json")
logger.info("Request processed", extra={
    "user_id": 123,
    "response_time": 0.45,
    "status_code": 200
})
```

### 2. ログローテーション

ファイルサイズベースのローテーション：

```python
# 設定例
logger = setup_logger("app", 
    enable_rotation=True,
    max_bytes=10*1024*1024,  # 10MB
    backup_count=5
)
```

### 3. 外部ログシステム連携

syslog、ELKスタック等との統合：

```python
# 構想
logger = setup_logger("app", 
    external_handler="syslog",
    syslog_address=("localhost", 514)
)
```

## まとめ

このログ重複問題の修正により、以下の改善を実現しました：

### 技術的改善

- ✅ **ログ重複の完全排除**: 統一ログ管理システムの導入
- ✅ **スレッドセーフ**: マルチスレッド環境での安全性確保
- ✅ **後方互換性**: 既存コードの無修正継続使用
- ✅ **性能向上**: ロガーインスタンス再利用によるメモリ効率化

### 運用面改善

- ✅ **保守性向上**: 中央集権的なログ設定管理
- ✅ **デバッグ効率**: クリアなログ出力による問題特定高速化
- ✅ **設定統一**: プロジェクト全体での一貫したログ動作
- ✅ **拡張性**: 将来的な機能追加への対応基盤

### 開発プロセス改善

- ✅ **テスト駆動開発**: 包括的なテストカバレッジ
- ✅ **文書駆動開発**: 詳細な技術文書による知識共有
- ✅ **最小修正原則**: 既存システムへの影響最小化
- ✅ **ベストプラクティス準拠**: 業界標準に従った実装

この実装により、tree-sitter-analyzerプロジェクトのログシステムは、拡張性と保守性を兼ね備えた堅牢なアーキテクチャとなりました。今後の機能追加や保守作業において、一貫性のあるログ管理が可能になります。