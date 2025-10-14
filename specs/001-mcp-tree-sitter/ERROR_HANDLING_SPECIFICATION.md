# Tree-sitter Analyzer MCP Server - エラーハンドリング統一仕様

**Version**: 1.0.0  
**Date**: 2025-10-12  
**Purpose**: 全MCPツールの統一されたエラーハンドリング仕様

## 🎯 エラーハンドリング原則

### 1. 統一性 (Consistency)
全てのMCPツールで一貫したエラーレスポンス形式を使用する。

### 2. 透明性 (Transparency)
エラーの原因と対処法を明確に提供する。

### 3. セキュリティ (Security)
機密情報の漏洩を防ぎ、適切にサニタイズされたエラーメッセージを提供する。

### 4. 回復可能性 (Recoverability)
可能な限り部分的な成功結果を提供し、ユーザーが次のアクションを取れるようにする。

## 📋 エラーレスポンス形式

### 標準エラーレスポンス

```json
{
  "success": false,
  "error": "詳細なエラーメッセージ",
  "error_type": "エラータイプ",
  "error_code": "ERR_001",
  "context": {
    "tool": "ツール名",
    "operation": "実行された操作",
    "timestamp": "2025-10-12T18:45:00Z"
  },
  "suggestions": [
    "推奨される対処法1",
    "推奨される対処法2"
  ]
}
```

### 部分成功レスポンス

```json
{
  "success": true,
  "partial_errors": [
    {
      "file": "problem_file.java",
      "error": "パースエラーの詳細",
      "error_code": "PARSE_001"
    }
  ],
  "results": {
    "processed_files": 95,
    "failed_files": 5,
    "data": "成功した部分の結果"
  }
}
```

## 🔧 ツール別エラーハンドリング仕様

### check_code_scale

**エラーパターン**:
- ファイル不存在: 構造化レスポンス
- アクセス権限エラー: セキュリティエラー
- パースエラー: 部分成功レスポンス

```python
# 実装例
def handle_check_code_scale_error(file_path: str, error: Exception) -> dict:
    if isinstance(error, FileNotFoundError):
        return {
            "success": False,
            "error": f"File not found: {sanitize_path(file_path)}",
            "error_type": "FileNotFoundError",
            "error_code": "FILE_001",
            "suggestions": [
                "Check if the file path is correct",
                "Verify file permissions"
            ]
        }
    # その他のエラーハンドリング...
```

### analyze_code_structure

**エラーパターン**:
- 大規模ファイルエラー: 警告付き部分処理
- 言語サポートエラー: 代替処理提案
- メモリ不足: リソース最適化提案

```python
def handle_structure_analysis_error(error: Exception) -> dict:
    if isinstance(error, MemoryError):
        return {
            "success": False,
            "error": "Memory limit exceeded during analysis",
            "error_type": "MemoryError",
            "error_code": "MEM_001",
            "suggestions": [
                "Use suppress_output=True to reduce memory usage",
                "Process file in smaller sections",
                "Consider using extract_code_section for specific parts"
            ]
        }
```

### extract_code_section

**エラーパターン**:
- ファイル不存在: `success: false`レスポンス
- 範囲指定エラー: 修正提案付きエラー
- エンコーディングエラー: 代替エンコーディング提案

```python
def handle_extract_section_error(file_path: str, start_line: int, end_line: int, error: Exception) -> dict:
    if isinstance(error, FileNotFoundError):
        return {
            "success": False,
            "error": f"File does not exist: {sanitize_path(file_path)}",
            "error_type": "FileNotFoundError",
            "error_code": "FILE_001"
        }
    elif isinstance(error, ValueError) and "line range" in str(error):
        return {
            "success": False,
            "error": f"Invalid line range: {start_line}-{end_line}",
            "error_type": "ValueError",
            "error_code": "RANGE_001",
            "suggestions": [
                f"Use line range 1-{get_file_line_count(file_path)}",
                "Check if start_line <= end_line"
            ]
        }
```

### list_files

**エラーパターン**:
- ディレクトリ不存在: `AnalysisError`例外
- 権限エラー: セキュリティ境界エラー
- パターンエラー: 正規表現修正提案

```python
def handle_list_files_error(roots: List[str], error: Exception) -> None:
    if isinstance(error, ValueError) and "directory does not exist" in str(error):
        raise AnalysisError(
            f"Directory not found: {sanitize_paths(roots)}",
            error_code="DIR_001",
            suggestions=[
                "Check if the directory path is correct",
                "Verify directory permissions",
                "Use set_project_path to set correct project root"
            ]
        ) from error
```

### search_content

**エラーパターン**:
- ファイル不存在: `AnalysisError`例外
- 正規表現エラー: パターン修正提案
- タイムアウト: 検索範囲縮小提案

```python
def handle_search_content_error(query: str, files: List[str], error: Exception) -> None:
    if isinstance(error, ValueError) and "file does not exist" in str(error):
        raise AnalysisError(
            f"One or more files not found in: {sanitize_paths(files)}",
            error_code="FILE_002",
            suggestions=[
                "Use list_files to verify file existence",
                "Check file paths and permissions"
            ]
        ) from error
    elif isinstance(error, re.error):
        raise AnalysisError(
            f"Invalid regular expression: {sanitize_regex(query)}",
            error_code="REGEX_001",
            suggestions=[
                "Check regex syntax",
                "Use fixed_strings=True for literal search",
                "Escape special characters"
            ]
        ) from error
```

### query_code

**エラーパターン**:
- 不正クエリ: 詳細な構文エラー情報
- 言語サポートエラー: サポート言語一覧提示
- パフォーマンスエラー: クエリ最適化提案

```python
def handle_query_code_error(query_string: str, language: str, error: Exception) -> None:
    if isinstance(error, TreeSitterQueryError):
        raise AnalysisError(
            f"Invalid Tree-sitter query: {error.message}",
            error_code="QUERY_001",
            suggestions=[
                "Check query syntax against Tree-sitter documentation",
                "Use predefined query keys instead of custom queries",
                f"Supported languages: {', '.join(SUPPORTED_LANGUAGES)}"
            ]
        ) from error
```

### find_and_grep

**エラーパターン**:
- 複合エラー: 各段階のエラー詳細
- パフォーマンスエラー: 検索範囲最適化提案
- 結果統合エラー: 代替出力形式提案

### set_project_path

**エラーパターン**:
- パス不存在: プロジェクト検出提案
- セキュリティエラー: 許可されたパス範囲説明
- 権限エラー: アクセス権限確認提案

## 🛡️ セキュリティ考慮事項

### パス情報のサニタイゼーション

```python
def sanitize_path(path: str) -> str:
    """パス情報から機密情報を除去"""
    # 絶対パスを相対パスに変換
    # ユーザー名やシステム情報を除去
    # プロジェクトルート外の情報を隠蔽
    return sanitized_path

def sanitize_paths(paths: List[str]) -> str:
    """複数パスの安全な表示"""
    return ", ".join(sanitize_path(p) for p in paths[:3]) + \
           (f" and {len(paths)-3} more" if len(paths) > 3 else "")
```

### エラーメッセージの情報漏洩防止

```python
def sanitize_error_message(message: str) -> str:
    """エラーメッセージから機密情報を除去"""
    # システムパスの除去
    # 内部実装詳細の隠蔽
    # スタックトレースの適切な処理
    return sanitized_message
```

## 📊 エラー分類とコード体系

### エラーコード体系

| プレフィックス | カテゴリ | 例 |
|----------------|----------|-----|
| FILE_xxx | ファイル関連 | FILE_001: ファイル不存在 |
| DIR_xxx | ディレクトリ関連 | DIR_001: ディレクトリ不存在 |
| PERM_xxx | 権限関連 | PERM_001: アクセス権限なし |
| PARSE_xxx | パース関連 | PARSE_001: 構文エラー |
| QUERY_xxx | クエリ関連 | QUERY_001: 不正なクエリ |
| MEM_xxx | メモリ関連 | MEM_001: メモリ不足 |
| NET_xxx | ネットワーク関連 | NET_001: タイムアウト |
| REGEX_xxx | 正規表現関連 | REGEX_001: 不正な正規表現 |
| RANGE_xxx | 範囲指定関連 | RANGE_001: 不正な範囲 |
| SEC_xxx | セキュリティ関連 | SEC_001: 境界違反 |

### エラー重要度レベル

| レベル | 説明 | 対応 |
|--------|------|------|
| **CRITICAL** | システム停止レベル | 即座の対応が必要 |
| **ERROR** | 機能停止レベル | 迅速な対応が必要 |
| **WARNING** | 部分的な問題 | 監視と改善が必要 |
| **INFO** | 情報提供 | ログ記録のみ |

## 🔍 エラー監視とログ記録

### 構造化ログ形式

```json
{
  "timestamp": "2025-10-12T18:45:00Z",
  "level": "ERROR",
  "tool": "check_code_scale",
  "error_code": "FILE_001",
  "error_type": "FileNotFoundError",
  "message": "File not found: ./src/main.java",
  "user_id": "anonymous",
  "session_id": "sess_123456",
  "context": {
    "file_path": "./src/main.java",
    "operation": "code_scale_analysis"
  }
}
```

### エラー統計とアラート

```python
# エラー率監視
def monitor_error_rates():
    """エラー率の監視とアラート"""
    error_rate = calculate_error_rate(last_hour=True)
    if error_rate > 0.05:  # 5%以上
        send_alert(f"High error rate detected: {error_rate:.2%}")
```

## 🧪 エラーハンドリングテスト

### テストケース例

```python
def test_file_not_found_error():
    """ファイル不存在エラーの適切な処理を確認"""
    result = check_code_scale("nonexistent_file.java")
    
    assert result["success"] == False
    assert result["error_code"] == "FILE_001"
    assert "suggestions" in result
    assert len(result["suggestions"]) > 0

def test_security_boundary_error():
    """セキュリティ境界違反の適切な処理を確認"""
    with pytest.raises(AnalysisError) as exc_info:
        list_files(roots=["../../../etc"])
    
    assert exc_info.value.error_code == "SEC_001"
    assert "boundary" in str(exc_info.value)
```

## 📚 エラー対応ガイド

### よくあるエラーと対処法

#### FILE_001: ファイル不存在
**原因**: 指定されたファイルが存在しない
**対処法**:
1. ファイルパスの確認
2. 相対パス/絶対パスの確認
3. ファイル権限の確認

#### QUERY_001: 不正なTree-sitterクエリ
**原因**: Tree-sitterクエリの構文エラー
**対処法**:
1. クエリ構文の確認
2. 定義済みクエリの使用
3. 言語サポート状況の確認

#### MEM_001: メモリ不足
**原因**: 大規模ファイルの処理でメモリ不足
**対処法**:
1. `suppress_output=True`の使用
2. ファイルの分割処理
3. `extract_code_section`での部分処理

## 🔄 継続的改善

### エラーハンドリング品質指標

- **エラー解決率**: 95%以上
- **平均解決時間**: 24時間以内
- **ユーザー満足度**: 4.5/5以上
- **エラー再発率**: 5%以下

### 改善プロセス

1. **エラー分析**: 週次のエラーログ分析
2. **パターン識別**: 共通エラーパターンの特定
3. **改善実装**: エラーハンドリングの強化
4. **効果測定**: 改善効果の定量評価

---

**最終更新**: 2025-10-12  
**次回レビュー**: 2025-11-12  
**責任者**: Tree-sitter Analyzer開発チーム