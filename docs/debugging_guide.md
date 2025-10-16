# Tree-sitter Analyzer デバッグガイド

## 概要

Tree-sitter Analyzerのログ設定改善機能により、開発者とユーザーは詳細なデバッグ情報を取得できるようになりました。このガイドでは、効果的なデバッグ手順と環境変数の使用方法について説明します。

## 🔧 環境変数による制御

### 基本的なログ制御

| 環境変数 | 説明 | デフォルト値 | 使用例 |
|---------|------|------------|--------|
| `LOG_LEVEL` | メインロガーのログレベル | `WARNING` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `TREE_SITTER_ANALYZER_ENABLE_FILE_LOG` | ファイルログの有効化 | `false` | `true` |
| `TREE_SITTER_ANALYZER_LOG_DIR` | ログファイルの出力ディレクトリ | システム一時ディレクトリ | `/var/log/tree-sitter` |
| `TREE_SITTER_ANALYZER_FILE_LOG_LEVEL` | ファイルログのレベル | メインロガーと同じ | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### 設定例

#### 1. 基本的なデバッグ設定

```bash
export LOG_LEVEL=DEBUG
export TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true
```

#### 2. カスタムログディレクトリ設定

```bash
export TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true
export TREE_SITTER_ANALYZER_LOG_DIR=/home/user/logs/tree-sitter
export TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=DEBUG
```

#### 3. 本番環境での最小ログ設定

```bash
export LOG_LEVEL=ERROR
export TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true
export TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=WARNING
```

## 🐛 デバッグ手順

### 1. MCPサーバーのデバッグ

#### Claude Desktopでのデバッグ設定

`claude_desktop_config.json`に以下を追加：

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
        "TREE_SITTER_PROJECT_ROOT": "/path/to/your/project",
        "TREE_SITTER_ANALYZER_ENABLE_FILE_LOG": "true",
        "TREE_SITTER_ANALYZER_FILE_LOG_LEVEL": "DEBUG",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

#### ログファイルの確認

1. **ログファイルの場所を確認**：
   ```bash
   # デフォルトの場所（システム一時ディレクトリ）
   ls /tmp/tree_sitter_analyzer.log  # Linux/macOS
   dir %TEMP%\tree_sitter_analyzer.log  # Windows
   ```

2. **リアルタイムでログを監視**：
   ```bash
   tail -f /tmp/tree_sitter_analyzer.log
   ```

### 2. CLIツールのデバッグ

#### デバッグモードでの実行

```bash
# 環境変数を設定してCLIを実行
export LOG_LEVEL=DEBUG
export TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true

uv run python -m tree_sitter_analyzer examples/BigService.java --advanced
```

#### 詳細なパフォーマンス分析

```bash
# パフォーマンスログも有効化
export LOG_LEVEL=DEBUG
export TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true
export TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=DEBUG

uv run python -m tree_sitter_analyzer examples/BigService.java --table=full
```

### 3. 一般的な問題のトラブルシューティング

#### 問題1: MCPサーバーが起動しない

**症状**: Claude DesktopでMCPサーバーが認識されない

**デバッグ手順**:
1. ログファイルを有効化
2. Claude Desktopを再起動
3. ログファイルでエラーメッセージを確認

```bash
export TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true
export TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=DEBUG
```

#### 問題2: ファイル解析が失敗する

**症状**: 特定のファイルの解析でエラーが発生

**デバッグ手順**:
1. DEBUGレベルでログを有効化
2. 問題のファイルを単独で解析
3. エラーの詳細を確認

```bash
export LOG_LEVEL=DEBUG
export TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true

uv run python -m tree_sitter_analyzer problematic_file.java --advanced
```

#### 問題3: パフォーマンスが遅い

**症状**: 大きなファイルの解析に時間がかかる

**デバッグ手順**:
1. パフォーマンスログを有効化
2. 処理時間を測定
3. ボトルネックを特定

```bash
export TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true
export TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=DEBUG

time uv run python -m tree_sitter_analyzer large_file.java --advanced
```

## 📊 ログ出力の理解

### ログレベルの説明

- **DEBUG**: 詳細な実行情報、変数の値、内部状態
- **INFO**: 一般的な実行情報、処理の開始/終了
- **WARNING**: 警告メッセージ、非致命的な問題
- **ERROR**: エラーメッセージ、処理の失敗

### ログメッセージの例

```
2025-10-16 12:00:00,123 - tree_sitter_analyzer - INFO - MCP server starting with project root: /path/to/project
2025-10-16 12:00:00,124 - tree_sitter_analyzer - DEBUG - File logging enabled: /tmp/tree_sitter_analyzer.log
2025-10-16 12:00:01,456 - tree_sitter_analyzer.performance - DEBUG - File analysis: 0.1234s - lines: 1419, elements: 85
```

## 🔍 高度なデバッグテクニック

### 1. 条件付きログ出力

特定の条件でのみ詳細ログを出力：

```bash
# 大きなファイルのみDEBUGログを出力
if [ $(wc -l < "$FILE") -gt 1000 ]; then
    export LOG_LEVEL=DEBUG
else
    export LOG_LEVEL=INFO
fi
```

### 2. ログローテーション

長時間実行時のログファイル管理：

```bash
# ログファイルのサイズ制限
export TREE_SITTER_ANALYZER_LOG_DIR=/var/log/tree-sitter
# logrotateを使用してローテーション設定
```

### 3. 構造化ログ分析

ログファイルからの情報抽出：

```bash
# エラーメッセージのみ抽出
grep "ERROR" /tmp/tree_sitter_analyzer.log

# パフォーマンス情報の抽出
grep "performance" /tmp/tree_sitter_analyzer.log | grep -o "[0-9]\+\.[0-9]\+s"

# 特定のファイルの処理時間
grep "File analysis" /tmp/tree_sitter_analyzer.log | grep "BigService.java"
```

## 🚨 注意事項

### セキュリティ

- ログファイルには機密情報が含まれる可能性があります
- 本番環境では適切なログレベルを設定してください
- ログファイルのアクセス権限を適切に設定してください

### パフォーマンス

- DEBUGレベルのログは大量の出力を生成します
- ファイルログは若干のパフォーマンス影響があります
- 必要に応じてログレベルを調整してください

### ストレージ

- ログファイルは時間とともに大きくなります
- 定期的なクリーンアップを検討してください
- ディスク容量を監視してください

## 📞 サポート

問題が解決しない場合は、以下の情報を含めてIssueを作成してください：

1. 使用した環境変数の設定
2. 実行したコマンド
3. エラーメッセージ
4. ログファイルの関連部分
5. 環境情報（OS、Pythonバージョンなど）

## 🔗 関連ドキュメント

- [README.md](../README.md) - 基本的な使用方法
- [CONTRIBUTING.md](CONTRIBUTING.md) - 開発者向けガイド
- [トラブルシューティングガイド](troubleshooting_guide.md) - 一般的な問題の解決方法