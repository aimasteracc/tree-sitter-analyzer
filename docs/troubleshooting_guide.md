# Tree-sitter Analyzer トラブルシューティングガイド

## 概要

このガイドでは、Tree-sitter Analyzerの使用中に発生する可能性のある一般的な問題と、その解決方法について説明します。特に、新しく実装されたログ設定改善機能に関連する問題に焦点を当てています。

## 🚨 一般的な問題と解決方法

### 1. MCPサーバー関連の問題

#### 問題: MCPサーバーが起動しない

**症状**:
- Claude DesktopでMCPサーバーが認識されない
- "Server not available" エラーが表示される

**解決手順**:

1. **ログを有効化して詳細を確認**:
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
           "TREE_SITTER_ANALYZER_ENABLE_FILE_LOG": "true",
           "TREE_SITTER_ANALYZER_FILE_LOG_LEVEL": "DEBUG",
           "LOG_LEVEL": "DEBUG"
         }
       }
     }
   }
   ```

2. **ログファイルを確認**:
   ```bash
   # Windows
   type %TEMP%\tree_sitter_analyzer.log
   
   # macOS/Linux
   cat /tmp/tree_sitter_analyzer.log
   ```

3. **依存関係を確認**:
   ```bash
   uv run python -c "import tree_sitter_analyzer; print('OK')"
   ```

#### 問題: MCPサーバーが頻繁にクラッシュする

**症状**:
- サーバーが予期せず終了する
- 接続が不安定

**解決手順**:

1. **メモリ使用量を確認**:
   ```bash
   # ログでメモリ使用量を監視
   export TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true
   export TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=DEBUG
   ```

2. **プロジェクトルートを明示的に設定**:
   ```json
   {
     "env": {
       "TREE_SITTER_PROJECT_ROOT": "/absolute/path/to/project"
     }
   }
   ```

### 2. ファイル解析の問題

#### 問題: 特定のファイルの解析が失敗する

**症状**:
- "Failed to analyze file" エラー
- 解析結果が空

**解決手順**:

1. **ファイルエンコーディングを確認**:
   ```bash
   file -i problematic_file.java
   ```

2. **デバッグモードで詳細を確認**:
   ```bash
   export LOG_LEVEL=DEBUG
   export TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true
   
   uv run python -m tree_sitter_analyzer problematic_file.java --advanced
   ```

3. **ファイルサイズを確認**:
   ```bash
   # 大きすぎるファイルは処理に時間がかかる場合があります
   wc -l problematic_file.java
   ```

#### 問題: 解析結果が期待と異なる

**症状**:
- 要素数が正しくない
- 構造が正しく認識されない

**解決手順**:

1. **言語を明示的に指定**:
   ```bash
   uv run python -m tree_sitter_analyzer file.ext --language java
   ```

2. **サポートされている言語を確認**:
   ```bash
   uv run python -m tree_sitter_analyzer --show-supported-languages
   ```

### 3. ログ設定の問題

#### 問題: ログファイルが作成されない

**症状**:
- `TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true`を設定してもログファイルが作成されない

**解決手順**:

1. **環境変数の設定を確認**:
   ```bash
   echo $TREE_SITTER_ANALYZER_ENABLE_FILE_LOG
   # "true" が表示されることを確認
   ```

2. **ディレクトリの権限を確認**:
   ```bash
   # カスタムログディレクトリを使用している場合
   ls -la /path/to/log/directory
   ```

3. **システム一時ディレクトリを確認**:
   ```bash
   # デフォルトの場所
   ls -la /tmp/tree_sitter_analyzer.log  # Linux/macOS
   dir %TEMP%\tree_sitter_analyzer.log   # Windows
   ```

#### 問題: ログファイルが大きくなりすぎる

**症状**:
- ログファイルがディスク容量を圧迫する

**解決手順**:

1. **ログレベルを調整**:
   ```bash
   # DEBUGからINFOに変更
   export TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=INFO
   ```

2. **定期的なクリーンアップ**:
   ```bash
   # 古いログファイルを削除
   find /tmp -name "tree_sitter_analyzer.log*" -mtime +7 -delete
   ```

### 4. パフォーマンスの問題

#### 問題: 解析が非常に遅い

**症状**:
- 大きなファイルの処理に異常に時間がかかる

**解決手順**:

1. **パフォーマンスログを有効化**:
   ```bash
   export TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true
   export TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=DEBUG
   ```

2. **処理時間を測定**:
   ```bash
   time uv run python -m tree_sitter_analyzer large_file.java --advanced
   ```

3. **メモリ使用量を監視**:
   ```bash
   # Linuxの場合
   /usr/bin/time -v uv run python -m tree_sitter_analyzer large_file.java --advanced
   ```

#### 問題: メモリ不足エラー

**症状**:
- "MemoryError" または "Out of memory" エラー

**解決手順**:

1. **ファイルを分割して処理**:
   ```bash
   # 大きなファイルを小さな部分に分けて解析
   split -l 1000 large_file.java part_
   ```

2. **部分読み取り機能を使用**:
   ```bash
   uv run python -m tree_sitter_analyzer large_file.java --partial-read --start-line 1 --end-line 500
   ```

### 5. 環境固有の問題

#### 問題: Windows環境でのパス問題

**症状**:
- パスの区切り文字に関するエラー
- ファイルが見つからないエラー

**解決手順**:

1. **絶対パスを使用**:
   ```bash
   uv run python -m tree_sitter_analyzer C:\full\path\to\file.java
   ```

2. **パスをエスケープ**:
   ```json
   {
     "env": {
       "TREE_SITTER_PROJECT_ROOT": "C:\\\\path\\\\to\\\\project"
     }
   }
   ```

#### 問題: macOS/Linux環境での権限問題

**症状**:
- "Permission denied" エラー
- ログファイルの作成に失敗

**解決手順**:

1. **ディレクトリの権限を確認**:
   ```bash
   ls -la /path/to/log/directory
   ```

2. **適切な権限を設定**:
   ```bash
   chmod 755 /path/to/log/directory
   ```

## 🔍 診断ツール

### 1. 環境診断スクリプト

以下のスクリプトで環境の状態を確認できます：

```bash
#!/bin/bash
echo "=== Tree-sitter Analyzer 環境診断 ==="
echo "Python version: $(python --version)"
echo "uv version: $(uv --version)"
echo ""
echo "=== 環境変数 ==="
echo "LOG_LEVEL: $LOG_LEVEL"
echo "TREE_SITTER_ANALYZER_ENABLE_FILE_LOG: $TREE_SITTER_ANALYZER_ENABLE_FILE_LOG"
echo "TREE_SITTER_ANALYZER_LOG_DIR: $TREE_SITTER_ANALYZER_LOG_DIR"
echo "TREE_SITTER_ANALYZER_FILE_LOG_LEVEL: $TREE_SITTER_ANALYZER_FILE_LOG_LEVEL"
echo ""
echo "=== パッケージ確認 ==="
uv run python -c "import tree_sitter_analyzer; print(f'tree-sitter-analyzer: OK')" 2>/dev/null || echo "tree-sitter-analyzer: ERROR"
echo ""
echo "=== ログファイル確認 ==="
if [ -f "/tmp/tree_sitter_analyzer.log" ]; then
    echo "ログファイル: 存在 ($(wc -l < /tmp/tree_sitter_analyzer.log) lines)"
else
    echo "ログファイル: 存在しない"
fi
```

### 2. ログ分析ツール

```bash
#!/bin/bash
LOG_FILE="${1:-/tmp/tree_sitter_analyzer.log}"

if [ ! -f "$LOG_FILE" ]; then
    echo "ログファイルが見つかりません: $LOG_FILE"
    exit 1
fi

echo "=== ログファイル分析: $LOG_FILE ==="
echo "総行数: $(wc -l < "$LOG_FILE")"
echo "エラー数: $(grep -c "ERROR" "$LOG_FILE")"
echo "警告数: $(grep -c "WARNING" "$LOG_FILE")"
echo ""
echo "=== 最新のエラー ==="
grep "ERROR" "$LOG_FILE" | tail -5
echo ""
echo "=== パフォーマンス情報 ==="
grep "performance" "$LOG_FILE" | tail -5
```

## 📞 サポートとヘルプ

### 問題報告時に含める情報

Issue を作成する際は、以下の情報を含めてください：

1. **環境情報**:
   ```bash
   python --version
   uv --version
   uname -a  # Linux/macOS
   ver       # Windows
   ```

2. **設定情報**:
   - 使用した環境変数
   - MCP設定ファイル（機密情報は除く）

3. **エラー情報**:
   - 完全なエラーメッセージ
   - ログファイルの関連部分

4. **再現手順**:
   - 実行したコマンド
   - 使用したファイル（可能であれば）

### よくある質問 (FAQ)

**Q: ログファイルはどこに保存されますか？**
A: デフォルトではシステムの一時ディレクトリに `tree_sitter_analyzer.log` として保存されます。`TREE_SITTER_ANALYZER_LOG_DIR` 環境変数でカスタマイズできます。

**Q: ログレベルを変更するにはどうすればよいですか？**
A: `LOG_LEVEL` 環境変数（メインロガー）と `TREE_SITTER_ANALYZER_FILE_LOG_LEVEL` 環境変数（ファイルログ）で制御できます。

**Q: MCPサーバーのデバッグはどのように行いますか？**
A: Claude Desktop の設定で環境変数を設定し、ログファイルを確認してください。

**Q: 大きなファイルの処理を高速化するにはどうすればよいですか？**
A: 部分読み取り機能を使用するか、ファイルを分割して処理することを検討してください。

## 🔗 関連リソース

- [デバッグガイド](debugging_guide.md) - 詳細なデバッグ手順
- [README.md](../README.md) - 基本的な使用方法
- [CONTRIBUTING.md](CONTRIBUTING.md) - 開発者向けガイド
- [GitHub Issues](https://github.com/aimasteracc/tree-sitter-analyzer/issues) - 問題報告とサポート