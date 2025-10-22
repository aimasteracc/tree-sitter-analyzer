# Tree-sitter Analyzer プロジェクト固有ベストプラクティス

このファイルは、tree-sitter-analyzerプロジェクトの特性に基づいた具体的なベストプラクティスを定義します。

## アーキテクチャ原則

### MCP (Model Context Protocol) 設計
- **非同期処理**: 全てのMCPツールは`async/await`パターンを使用
- **エラーハンドリング**: MCPエラーレスポンスの標準化
- **リソース管理**: ファイルハンドルやプロセスの適切なクリーンアップ
- **セキュリティ**: パス検証とサンドボックス化の徹底

### Tree-sitter統合
- **パーサー管理**: 言語パーサーの遅延ロードとキャッシュ
- **クエリ最適化**: 複雑なクエリの分割と並列処理
- **エラー処理**: パース失敗時の適切なフォールバック
- **メモリ管理**: 大きなファイル処理時のメモリ効率

## コーディング規約

### ファイル構造
```
tree_sitter_analyzer/
├── core/           # コアエンジン
├── mcp/            # MCPサーバー実装
├── plugins/        # 言語プラグイン
├── formatters/     # 出力フォーマッター
├── utils/          # ユーティリティ
└── queries/        # Tree-sitterクエリ
```

### 命名規則
- **モジュール**: `snake_case`（例: `query_service.py`）
- **クラス**: `PascalCase`（例: `AnalysisEngine`）
- **関数**: `snake_case`（例: `analyze_code_structure`）
- **定数**: `UPPER_SNAKE_CASE`（例: `DEFAULT_TIMEOUT`）
- **プライベート**: `_leading_underscore`

### 型ヒント規約
```python
from typing import Dict, List, Optional, Union, Any
from pathlib import Path

# 関数の型ヒント
async def analyze_file(
    file_path: Path,
    language: Optional[str] = None,
    include_details: bool = True
) -> Dict[str, Any]:
    """ファイル分析を実行する。"""
    pass

# クラスの型ヒント
class AnalysisResult:
    def __init__(
        self,
        file_path: Path,
        elements: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        self.file_path = file_path
        self.elements = elements
        self.metadata = metadata or {}
```

## エラーハンドリング

### 例外階層
```python
class TreeSitterAnalyzerError(Exception):
    """基底例外クラス"""
    pass

class ParseError(TreeSitterAnalyzerError):
    """パース関連エラー"""
    pass

class LanguageNotSupportedError(TreeSitterAnalyzerError):
    """サポートされていない言語"""
    pass

class SecurityError(TreeSitterAnalyzerError):
    """セキュリティ関連エラー"""
    pass
```

### エラーハンドリングパターン
```python
async def safe_file_operation(file_path: Path) -> Optional[str]:
    """安全なファイル操作の例"""
    try:
        # ファイル操作
        return await read_file_content(file_path)
    except FileNotFoundError:
        logger.warning(f"File not found: {file_path}")
        return None
    except PermissionError:
        logger.error(f"Permission denied: {file_path}")
        raise SecurityError(f"Access denied to {file_path}")
    except Exception as e:
        logger.error(f"Unexpected error reading {file_path}: {e}")
        raise TreeSitterAnalyzerError(f"Failed to read {file_path}") from e
```

## 非同期プログラミング

### asyncio パターン
```python
import asyncio
from typing import List, Coroutine

async def process_files_concurrently(
    file_paths: List[Path],
    max_concurrent: int = 10
) -> List[AnalysisResult]:
    """ファイルを並行処理する"""
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_single_file(file_path: Path) -> AnalysisResult:
        async with semaphore:
            return await analyze_file(file_path)
    
    tasks = [process_single_file(path) for path in file_paths]
    return await asyncio.gather(*tasks, return_exceptions=True)
```

### リソース管理
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def managed_parser(language: str):
    """パーサーのライフサイクル管理"""
    parser = None
    try:
        parser = await load_parser(language)
        yield parser
    finally:
        if parser:
            await cleanup_parser(parser)
```

## テスト戦略

### テスト構造
```
tests/
├── unit/           # 単体テスト
├── integration/    # 統合テスト
├── mcp/           # MCPサーバーテスト
├── fixtures/      # テストデータ
└── conftest.py    # pytest設定
```

### テストパターン
```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_analyze_file_success():
    """正常ケースのテスト"""
    # Arrange
    file_path = Path("test_file.py")
    expected_result = {"elements": [], "metadata": {}}
    
    # Act
    result = await analyze_file(file_path)
    
    # Assert
    assert result is not None
    assert "elements" in result

@pytest.mark.asyncio
async def test_analyze_file_not_found():
    """ファイルが見つからない場合のテスト"""
    file_path = Path("nonexistent.py")
    
    with pytest.raises(FileNotFoundError):
        await analyze_file(file_path)
```

## パフォーマンス最適化

### キャッシュ戦略
```python
from functools import lru_cache
import hashlib

class AnalysisCache:
    """分析結果のキャッシュ管理"""
    
    def __init__(self, max_size: int = 1000):
        self._cache: Dict[str, Any] = {}
        self._max_size = max_size
    
    def get_cache_key(self, file_path: Path, options: Dict[str, Any]) -> str:
        """キャッシュキーの生成"""
        content = f"{file_path}:{hash(frozenset(options.items()))}"
        return hashlib.md5(content.encode()).hexdigest()
    
    async def get_or_compute(
        self,
        file_path: Path,
        options: Dict[str, Any],
        compute_func: Callable
    ) -> Any:
        """キャッシュから取得または計算"""
        cache_key = self.get_cache_key(file_path, options)
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        result = await compute_func(file_path, options)
        
        if len(self._cache) >= self._max_size:
            # LRU eviction
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        
        self._cache[cache_key] = result
        return result
```

### メモリ効率
```python
async def process_large_file(file_path: Path) -> AsyncIterator[Dict[str, Any]]:
    """大きなファイルのストリーミング処理"""
    async with aiofiles.open(file_path, 'r') as file:
        async for line_num, line in enumerate(file, 1):
            if line_num % 1000 == 0:
                # 定期的にメモリ使用量をチェック
                await asyncio.sleep(0)  # 他のタスクに制御を譲る
            
            yield {"line": line_num, "content": line.strip()}
```

## セキュリティ

### パス検証
```python
from pathlib import Path
import os

def validate_file_path(file_path: Path, project_root: Path) -> Path:
    """ファイルパスの安全性を検証"""
    try:
        # 絶対パスに変換
        abs_path = file_path.resolve()
        abs_root = project_root.resolve()
        
        # プロジェクトルート内かチェック
        abs_path.relative_to(abs_root)
        
        # 存在チェック
        if not abs_path.exists():
            raise FileNotFoundError(f"File not found: {abs_path}")
        
        # ファイルかチェック
        if not abs_path.is_file():
            raise ValueError(f"Not a file: {abs_path}")
        
        return abs_path
        
    except ValueError as e:
        raise SecurityError(f"Invalid file path: {file_path}") from e
```

### 入力サニタイゼーション
```python
import re
from typing import Pattern

class InputValidator:
    """入力値の検証"""
    
    SAFE_FILENAME_PATTERN: Pattern = re.compile(r'^[a-zA-Z0-9._-]+$')
    MAX_FILENAME_LENGTH: int = 255
    
    @classmethod
    def validate_filename(cls, filename: str) -> str:
        """ファイル名の検証"""
        if not filename:
            raise ValueError("Filename cannot be empty")
        
        if len(filename) > cls.MAX_FILENAME_LENGTH:
            raise ValueError(f"Filename too long: {len(filename)} > {cls.MAX_FILENAME_LENGTH}")
        
        if not cls.SAFE_FILENAME_PATTERN.match(filename):
            raise ValueError(f"Invalid filename: {filename}")
        
        return filename
```

## ログ設定

### 構造化ログ
```python
import logging
import json
from datetime import datetime

class StructuredLogger:
    """構造化ログの実装"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def log_analysis_start(self, file_path: Path, options: Dict[str, Any]) -> None:
        """分析開始ログ"""
        self.logger.info(json.dumps({
            "event": "analysis_start",
            "timestamp": datetime.utcnow().isoformat(),
            "file_path": str(file_path),
            "options": options
        }))
    
    def log_analysis_complete(
        self,
        file_path: Path,
        duration: float,
        element_count: int
    ) -> None:
        """分析完了ログ"""
        self.logger.info(json.dumps({
            "event": "analysis_complete",
            "timestamp": datetime.utcnow().isoformat(),
            "file_path": str(file_path),
            "duration_seconds": duration,
            "element_count": element_count
        }))
```

## 継続的改善

### メトリクス収集
- パフォーマンス指標の監視
- エラー率の追跡
- メモリ使用量の監視
- キャッシュヒット率の測定

### コードレビューチェックリスト
- [ ] 型ヒントが適切に設定されているか
- [ ] エラーハンドリングが適切か
- [ ] 非同期処理が正しく実装されているか
- [ ] セキュリティ要件が満たされているか
- [ ] テストが十分にカバーされているか
- [ ] ドキュメントが更新されているか
- [ ] パフォーマンスへの影響が考慮されているか