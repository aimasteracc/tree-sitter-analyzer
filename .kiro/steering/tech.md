---
inclusion: always
---

# 技術スタック

## ビルドシステム

- **hatchling** - モダンなPythonビルドバックエンド
- **Python 3.10+** - source/target compatibility (3.10, 3.11, 3.12, 3.13対応)
- **uv** - 高速Pythonパッケージマネージャー（推奨）

## 主要フレームワーク

- **tree-sitter >=0.25.0** - 高精度構文解析エンジン
- **mcp >=1.12.3** - Model Context Protocol（AI統合）
- **asyncio** - 非同期処理フレームワーク
- **pathlib** - モダンパス操作
- **chardet >=5.0.0** - 文字エンコーディング検出
- **cachetools >=5.0.0** - インメモリキャッシュシステム
- **psutil >=5.9.8** - システムプロセス監視
- **deepdiff >=6.7.1** - 深い差分比較

## 言語パーサー（Tree-sitter）

### コア言語サポート
- **tree-sitter-java >=0.23.5,<0.25.0** - Java言語パーサー
- **tree-sitter-python >=0.23.6,<0.25.0** - Python言語パーサー
- **tree-sitter-javascript >=0.23.1,<0.25.0** - JavaScript言語パーサー
- **tree-sitter-typescript >=0.23.2** - TypeScript言語パーサー
- **tree-sitter-c-sharp >=0.23.1** - C#言語パーサー

### Web技術サポート
- **tree-sitter-html >=0.23.0,<0.25.0** - HTML DOM解析（MarkupElement データモデル）
- **tree-sitter-css >=0.23.0,<0.25.0** - CSS解析（StyleElement データモデル）

### その他言語サポート
- **tree-sitter-cpp >=0.23.4,<0.25.0** - C++言語パーサー
- **tree-sitter-markdown >=0.3.1** - Markdown文書解析
- **tree-sitter-sql >=0.3.11,<0.4.0** - SQLデータベーススキーマ解析
- **tree-sitter-php >=0.23.0,<0.25.0** - PHP Webアプリケーション解析
- **tree-sitter-ruby >=0.23.0,<0.25.0** - Ruby Rails/スクリプト解析

## MCPサーバーサポート

- **mcp >=1.12.2** - Model Context Protocol コア
- **anyio >=4.0.0** - 非同期I/O抽象化
- **httpx >=0.27.0,<1.0.0** - 非同期HTTPクライアント
- **pydantic >=2.5.0** - データ検証とシリアライゼーション
- **pydantic-settings >=2.2.1** - 設定管理

## 開発・テスト

### コード品質ツール
- **black >=24.0.0** - コードフォーマッター（88文字制限）
- **ruff >=0.5.0** - 高速リンター・フォーマッター（統合ツール）
- **mypy >=1.17.0** - 静的型チェック
- **isort >=5.13.0** - インポート整理（Black互換）
- **bandit** - セキュリティ脆弱性検出
- **pydocstyle** - docstring品質チェック（Google規約）
- **pyupgrade** - Python構文近代化

### テストフレームワーク
- **pytest >=8.4.1** - テストフレームワーク
- **pytest-cov >=4.0.0** - カバレッジ測定
- **pytest-asyncio >=1.1.0** - 非同期テストサポート
- **pytest-mock >=3.14.1** - モックテスト
- **pytest-benchmark >=4.0.0** - パフォーマンステスト
- **memory-profiler >=0.61.0** - メモリプロファイリング

### 型チェック補助
- **types-psutil >=5.9.0** - psutil型定義
- **types-toml >=0.10.8.20240310** - TOML型定義
- **types-requests >=2.32.4.20250913** - requests型定義

## 外部ツール統合

### 高性能検索ツール
- **fd** - 高速ファイル検索（Rust製）
- **ripgrep (rg)** - 高速テキスト検索（Rust製）

### CI/CD
- **pre-commit >=3.0.0** - Git pre-commitフック
- **GitHub Actions** - 継続的インテグレーション
- **codecov** - コードカバレッジ監視

## よく使うコマンド

### 開発環境セットアップ
```bash
# 基本インストール
uv add tree-sitter-analyzer

# 人気言語パッケージ（推奨）
uv add "tree-sitter-analyzer[popular]"

# 完全インストール（MCP対応）
uv add "tree-sitter-analyzer[all,mcp]"

# 開発環境セットアップ
uv sync --extra all --extra mcp
```

### コード解析実行
```bash
# 基本解析
uv run tree-sitter-analyzer examples/BigService.java --advanced --output-format text

# 構造テーブル生成
uv run tree-sitter-analyzer examples/BigService.java --table full

# 精密コード抽出
uv run tree-sitter-analyzer examples/BigService.java --partial-read --start-line 93 --end-line 106

# HTML/CSS解析
uv run tree-sitter-analyzer examples/comprehensive_sample.html --table full
uv run tree-sitter-analyzer examples/comprehensive_sample.css --advanced

# SQL解析
uv run tree-sitter-analyzer examples/sample_database.sql --table full
```

### 検索・発見コマンド
```bash
# ファイル一覧
uv run list-files . --extensions java

# コンテンツ検索
uv run search-content --roots . --query "class.*extends" --include-globs "*.java"

# 二段階検索
uv run find-and-grep --roots . --query "@SpringBootApplication" --extensions java
```

### 品質チェック
```bash
# 包括的品質チェック
uv run pre-commit run --all-files

# 個別チェック
uv run black --check --line-length=88 .
uv run ruff check .
uv run mypy tree_sitter_analyzer/
uv run pytest tests/

# テスト実行
uv run pytest tests/ -v
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html
```

### MCPサーバー実行
```bash
# MCPサーバー起動
uv run python -m tree_sitter_analyzer.mcp.server

# MCPサーバー（同期版）
uv run tree-sitter-analyzer-mcp
```

## 設定に関する注意事項

### 環境変数設定
- **TREE_SITTER_PROJECT_ROOT**: プロジェクトルートパス（MCP設定）
- **TREE_SITTER_OUTPUT_PATH**: 出力ディレクトリパス（MCP設定）
- **TREE_SITTER_ANALYZER_ENABLE_FILE_LOG**: ファイルログ有効化
- **TREE_SITTER_ANALYZER_LOG_DIR**: カスタムログディレクトリ
- **TREE_SITTER_ANALYZER_FILE_LOG_LEVEL**: ファイルログレベル

### MCP設定（Claude Desktop）
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": [
        "run", "--with", "tree-sitter-analyzer[mcp]",
        "python", "-m", "tree_sitter_analyzer.mcp.server"
      ],
      "env": {
        "TREE_SITTER_PROJECT_ROOT": "/absolute/path/to/your/project",
        "TREE_SITTER_OUTPUT_PATH": "/absolute/path/to/output/directory"
      }
    }
  }
}
```

### 品質基準
- **テストカバレッジ**: 80%以上を目標
- **型チェック**: MyPyエラーゼロ
- **リンティング**: Ruff/Flake8エラーゼロ
- **セキュリティ**: Bandit警告ゼロ
- **ドキュメント**: パブリックAPI 100%カバー
- **行長制限**: 88文字以内（Black/Ruff統一）

### パフォーマンス要件
- **大きなファイル**: 1MB+でも適切な応答時間
- **並行処理**: 最大4倍の検索速度向上
- **メモリ効率**: ストリーミング処理による最適化
- **キャッシュ**: 99.8%高速化（200-400倍改善）

---

## Level 2-3 最適化プロセス (Session 14 追加)

### 品質目標
- **スコア基準**: >= 90/100 (PASS), 70-89 (PARTIAL), 0-69 (FAIL)
- **自動チェッカー**: `.kiro/optimization_work/check_optimization_quality.py`

### ドキュメント要件

**パブリックメソッド** (必須100%):
- `Args`: 引数説明（なしの場合は `None` と明記）
- `Returns`: 戻り値の型と説明
- `Note`: 重要な動作/制限事項

**推奨セクション**:
- `Raises`: 発生する例外
- `Performance`: パフォーマンス特性
- `Thread Safety`: スレッドセーフティ保証
- `Example`: 使用例

**プライベートメソッド** (簡易版):
- `Args`, `Returns`, `Note` のみ

### 例外クラスパターン

各モジュールに3つのカスタム例外:
``python
class ModuleBaseException(Exception):
    """Base exception for this module."""
    pass

class SpecificError1(ModuleBaseException):
    """Specific error condition 1."""
    pass

class SpecificError2(ModuleBaseException):
    """Specific error condition 2."""
    pass
``

### パフォーマンス監視

各ファイルに5-8個の監視ポイント:
``python
from time import perf_counter

start = perf_counter()
# ... operation ...
elapsed = perf_counter() - start
self._stats['operation_time'] = elapsed
``

### 統計トラッキング

``python
def __init__(self):
    self._stats = {
        'total_calls': 0,
        'cache_hits': 0,
        'errors': 0,
        'avg_time': 0.0
    }

def get_statistics(self) -> dict[str, Any]:
    """Get performance and usage statistics.
    
    Args:
        None (instance method with no parameters)
        
    Returns:
        dict[str, Any]: Statistics with derived metrics
    """
    return {
        **self._stats,
        'hit_rate': self._stats['cache_hits'] / max(1, self._stats['total_calls'])
    }
``

### エクスポート要件

``python
__all__ = [
    # Public classes
    'MainClass',
    'HelperClass',
    # Public functions
    'main_function',
    # Exceptions (always exported)
    'ModuleBaseException',
    'SpecificError1',
    'SpecificError2'
]
``

### 8フェーズ最適化ワークフロー

1. **Baseline**: `python check_optimization_quality.py <file>`
2. **Module Header**: 11必須セクション追加
3. **Exceptions**: 3クラス定義
4. **Public Methods**: Args/Returns/Note 追加
5. **Private Methods**: 簡易ドキュメント追加
6. **Performance**: perf_counter 監視ポイント追加
7. **Statistics**: _stats + get_statistics() 実装
8. **Validate**: スコア >= 90 確認

### ツール

- **check_optimization_quality.py**: 品質自動チェック（スコア計算、詳細レポート）
- **README.md**: 完全ワークフロー、コードテンプレート、トラブルシューティング

### 現在のステータス

| ファイル | スコア | ステータス |
|---------|-------|----------|
| python_formatter.py | 100/100 | ✅ PASS |
| python_plugin.py | 97/100 | ✅ PASS |
| 残り | - | ⏳ Phase 2-3 対象 (180 files) |

**詳細**: `.kiro/optimization_work/README.md` 参照

---

**最終更新**: 2026-01-31 (Session 14)
