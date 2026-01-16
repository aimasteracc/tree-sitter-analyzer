# 設計ドキュメント: TOON Format 統合

## 概要

本設計ドキュメントは、Tree-sitter Analyzer に TOON（Token-Oriented Object Notation）フォーマットを統合するための技術方案を記述します。設計はプロジェクト既存のフォーマッターアーキテクチャに従い、既存基盤とのシームレスな統合を確保します。

## アーキテクチャ

### システム構成図

```
┌─────────────────────────────────────────────────────────────┐
│                    tree-sitter-analyzer                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐         ┌──────────────┐                 │
│  │ CLI Commands │────────▶│ Output Mgr   │                 │
│  └──────────────┘         └──────┬───────┘                 │
│                                   │                          │
│  ┌──────────────┐                │                          │
│  │  MCP Tools   │────────────────┤                          │
│  └──────────────┘                │                          │
│                                   ▼                          │
│                          ┌─────────────────┐                │
│                          │ Format Registry │                │
│                          └────────┬────────┘                │
│                                   │                          │
│         ┌─────────────────────────┼─────────────────┐       │
│         │                         │                 │       │
│         ▼                         ▼                 ▼       │
│  ┌─────────────┐         ┌──────────────┐   ┌──────────┐  │
│  │JSON Formatter│         │TOON Formatter│   │CSV/Table │  │
│  └─────────────┘         └──────────────┘   └──────────┘  │
│                                   │                          │
│                                   ▼                          │
│                          ┌─────────────────┐                │
│                          │  TOON Encoder   │                │
│                          └─────────────────┘                │
│                                   │                          │
│                          ┌────────┴────────┐                │
│                          │                 │                │
│                          ▼                 ▼                │
│                   ┌─────────────┐  ┌─────────────┐         │
│                   │Simple Values│  │Array Tables │         │
│                   └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

### ファイル構成

```
tree_sitter_analyzer/
├── formatters/
│   ├── base_formatter.py      # BaseFormatter 抽象基底クラス
│   ├── toon_encoder.py        # 低レベルエンコーダー
│   └── toon_formatter.py      # 高レベルフォーマッター
├── output_manager.py          # Formatter Registry 管理
└── mcp/
    ├── tools/                 # MCP ツール（TOON統合予定）
    └── utils/
        └── file_output_manager.py  # ファイル出力管理

tests/
├── test_toon_formatter_integration.py  # 統合テスト（37 tests）
└── (予定) benchmarks/
    └── test_toon_performance.py        # パフォーマンステスト
```

## コンポーネントとインターフェース

### 1. BaseFormatter 抽象基底クラス

すべてのフォーマッターが継承する抽象基底クラスです。

```python
from abc import ABC, abstractmethod
from typing import Any

class BaseFormatter(ABC):
    """
    フォーマッターの抽象基底クラス。
    
    すべてのフォーマッターはこのクラスを継承し、
    必須メソッドを実装します。
    """
    
    @abstractmethod
    def __init__(self) -> None:
        pass
    
    def format(self, data: Any) -> str:
        """
        統一フォーマットメソッド（OutputManager互換）。
        
        Args:
            data: フォーマット対象のデータ
            
        Returns:
            フォーマットされた文字列
        """
        if isinstance(data, dict):
            return self.format_structure(data)
        else:
            import json
            return json.dumps(data, indent=2, ensure_ascii=False)
    
    @abstractmethod
    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """サマリー出力をフォーマット"""
        pass
    
    @abstractmethod
    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """構造分析出力をフォーマット"""
        pass
    
    @abstractmethod
    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """高度な分析出力をフォーマット"""
        pass
    
    @abstractmethod
    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """テーブル出力をフォーマット"""
        pass
```

### 2. ToonEncoder コンポーネント

低レベルのTOONエンコーディングを担当します。

```python
class ToonEncoder:
    """
    低レベルTOONエンコーディングユーティリティ。
    TOON構文の生成を担当。
    """
    
    def __init__(self, use_tabs: bool = False):
        """
        Initialize TOON encoder.
        
        Args:
            use_tabs: Use tab delimiters instead of commas for further compression
        """
        self.use_tabs = use_tabs
        self.delimiter = "\t" if use_tabs else ","
    
    def encode(self, data: Any, indent: int = 0) -> str:
        """任意のPythonオブジェクトをTOON文字列にエンコード"""
        pass
    
    def encode_dict(self, data: dict, indent: int = 0) -> str:
        """辞書をTOONオブジェクト形式にエンコード"""
        pass
    
    def encode_list(self, items: list, indent: int = 0) -> str:
        """リストをTOON配列形式にエンコード"""
        pass
    
    def encode_value(self, value: Any) -> str:
        """単一の値をエンコード（文字列エスケープを含む）"""
        pass
    
    def encode_array_table(
        self, 
        items: list[dict], 
        schema: list[str] | None = None,
        indent: int = 0
    ) -> str:
        """同型配列をコンパクトなテーブル形式にエンコード"""
        pass
    
    def encode_array_header(self, count: int, schema: list[str] | None = None) -> str:
        """配列ヘッダーを生成 (例: [3]{name,visibility,lines}:)"""
        pass
    
    def _encode_string(self, s: str) -> str:
        """文字列を適切にエスケープしてエンコード"""
        pass
    
    def _infer_schema(self, items: list[dict[str, Any]]) -> list[str]:
        """配列アイテムから共通スキーマを推論"""
        pass
```

### 3. ToonFormatter コンポーネント

高レベルのフォーマッティングを担当し、BaseFormatterを継承します。

```python
class ToonFormatter(BaseFormatter):
    """
    高レベルTOONフォーマッター。
    統一インターフェースを提供し、データ型に応じた
    フォーマッティングを実行。
    """
    
    def __init__(
        self, 
        use_tabs: bool = False, 
        compact_arrays: bool = True,
        include_metadata: bool = True
    ):
        """
        Initialize TOON formatter.
        
        Args:
            use_tabs: Use tab delimiters instead of commas
            compact_arrays: Use CSV-style compact arrays for homogeneous data
            include_metadata: Include file metadata in output
        """
        self.use_tabs = use_tabs
        self.compact_arrays = compact_arrays
        self.include_metadata = include_metadata
        self.encoder = ToonEncoder(use_tabs=use_tabs)
    
    def format(self, data: Any) -> str:
        """
        統一フォーマットメソッド（BaseFormatter実装）。
        データ型に応じて適切な内部メソッドにルーティング。
        """
        if isinstance(data, AnalysisResult):
            return self.format_analysis_result(data)
        elif self._is_mcp_response(data):
            return self.format_mcp_response(data)
        elif isinstance(data, dict):
            return self.format_structure(data)
        else:
            return self.encoder.encode(data)
    
    def format_analysis_result(self, result: AnalysisResult, table_type: str = "full") -> str:
        """AnalysisResultをTOON形式に変換"""
        pass
    
    def format_mcp_response(self, data: dict) -> str:
        """MCPレスポンスをTOON形式に変換"""
        pass
    
    def _is_mcp_response(self, data: dict[str, Any]) -> bool:
        """データがMCPレスポンス構造かどうかを検出"""
        pass
```

### 4. OutputManager 拡張

Formatter Registryを管理し、統一的なフォーマット呼び出しを提供します。

```python
class OutputManager:
    """CLIの出力管理"""
    
    SUPPORTED_FORMATS = ["json", "yaml", "csv", "table", "toon"]
    
    def __init__(
        self, 
        quiet: bool = False, 
        json_output: bool = False,
        output_format: str = "json"
    ):
        self.quiet = quiet
        self.json_output = json_output
        self.output_format = output_format if not json_output else "json"
        self._formatter_registry = self._init_formatters()
    
    def _init_formatters(self) -> dict[str, Any]:
        """フォーマッターレジストリを初期化"""
        formatters = {}
        
        # JSON formatter (built-in)
        formatters["json"] = JsonFormatter()
        
        # TOON formatter
        try:
            from .formatters.toon_formatter import ToonFormatter
            formatters["toon"] = ToonFormatter()
        except ImportError:
            pass
        
        # YAML formatter (optional)
        try:
            import yaml
            formatters["yaml"] = YamlFormatter()
        except ImportError:
            pass
        
        return formatters
    
    def data(self, data: Any, format_type: str | None = None) -> None:
        """指定されたフォーマットでデータを出力"""
        fmt = format_type or self.output_format
        formatter = self._formatter_registry.get(fmt)
        if formatter:
            output = formatter.format(data)
            print(output)
```

## データモデル

### TOON 出力形式

#### 入力例（JSON）

```json
{
  "file_path": "BigService.java",
  "language": "java",
  "line_count": 1419,
  "methods": [
    {"name": "updateCustomer", "visibility": "public", "return_type": "void", "lines": "93-106"},
    {"name": "getCustomer", "visibility": "public", "return_type": "Customer", "lines": "108-120"}
  ]
}
```

#### 出力例（TOON）

```toon
file_path: BigService.java
language: java
line_count: 1419

methods:
[2]{name,visibility,return_type,lines}:
  updateCustomer,public,void,93-106
  getCustomer,public,Customer,108-120
```

### 文字列エスケープ規則

| 入力 | 出力 |
|------|------|
| `\` | `\\` |
| `"` | `\"` |
| 改行 | `\n` |
| キャリッジリターン | `\r` |
| タブ | `\t` |

特殊文字を含む文字列はダブルクォートで囲まれます。

### クォートが必要な文字

以下の文字を含む文字列は自動的にダブルクォートで囲まれます：

- デリミタ（`,` または `\t`）
- 改行（`\n`）、キャリッジリターン（`\r`）、タブ（`\t`）
- バックスラッシュ（`\`）
- コロン（`:`）
- ブレース（`{`, `}`）
- ブラケット（`[`, `]`）
- ダブルクォート（`"`）

## 正確性プロパティ

### プロパティ1: スカラー値のエンコード正確性

任意の有効なPythonスカラー値（string, int, float, bool, None）に対して、ToonEncoderは正しくエンコードし、特殊文字を適切にエスケープすること。

**検証対象**: 要件1.1, 1.4

### プロパティ2: 配列テーブルの一貫性

任意の同型辞書配列に対して、encode_array_tableは正しいスキーマヘッダーと対応するデータ行を生成すること。

**検証対象**: 要件1.3

### プロパティ3: BaseFormatter準拠

ToonFormatterはBaseFormatterを継承し、すべての抽象メソッドを実装すること。format()メソッドは任意の入力データに対して常に文字列を返すこと。

**検証対象**: 要件2.1, 2.5

### プロパティ4: トークン削減率

任意のAnalysisResultに対して、TOON出力のトークン数はJSON出力のトークン数の50%以下であること。

**検証対象**: 要件6.5

### プロパティ5: 後方互換性

OutputManagerのデフォルト動作（format_type未指定）はJSON形式を出力し、既存の動作と同一であること。

**検証対象**: 要件3.4

### プロパティ6: 区切り文字の一貫性

use_tabs=True の場合、スキーマヘッダーと値行の両方でタブ区切りが使用されること。

**検証対象**: 要件1.5, 1.6

## エラーハンドリング

### 現在の実装状態

堅牢なエラーハンドリングが実装されています。

| 機能 | 状態 |
|------|------|
| 基本的な型変換 | ✅ 実装済み |
| 空データ処理 | ✅ 実装済み |
| ToonEncodeError例外 | ✅ 実装済み |
| JSONフォールバック | ✅ 実装済み |
| 循環参照検出 | ✅ 実装済み |
| 最大ネスト深度制限 | ✅ 実装済み (default: 100) |
| イテレーティブ実装 | ✅ 実装済み（再帰を排除） |

### エラーハンドリング実装

#### ToonEncodeError 例外

```python
class ToonEncodeError(Exception):
    """TOON encoding error with detailed context"""
    def __init__(self, message: str, path: list[str] | None = None, value: Any = None):
        self.path = path or []
        self.value = value
        super().__init__(message)

# 使用例
try:
    output = encoder.encode(data)
except ToonEncodeError as e:
    logger.warning(f"TOON encode failed: {e}, falling back to JSON")
    output = json.dumps(data)
```

#### 未サポートのデータ型

- カスタムクラス: `str()` 変換を試行
- バイナリデータ: Base64エンコード
- 循環参照: `ToonEncodeError` を送出

#### フォールバック動作

1. TOON エンコード失敗 → JSON フォールバック（自動）
2. 不正な形式指定 → `ValueError` を送出
3. 空データ → 空文字列を返す

## テスト戦略

### ユニットテスト

| テスト対象 | テストケース |
|-----------|-------------|
| ToonEncoder | スカラーエンコード、辞書エンコード、配列エンコード、エスケープ処理 |
| ToonFormatter | format()分岐、AnalysisResult処理、MCPレスポンス処理 |
| OutputManager | レジストリ初期化、フォーマット選択、エラーハンドリング |

### 統合テスト

| テスト対象 | テストケース |
|-----------|-------------|
| CLI統合 | `--format toon` オプション、ファイル出力、バッチ処理 |
| MCP統合 | output_formatパラメータ、レスポンス形式検証 |

### ベンチマークテスト

| 指標 | テスト方法 |
|------|-----------|
| トークン削減率 | 同一データのJSON/TOON出力を比較 |
| エンコード速度 | 大規模データセットでの処理時間計測 |
| メモリ使用量 | 処理中のメモリ使用量プロファイリング |

### 現在のテストファイル構成

```
tests/
├── test_toon_formatter_integration.py  # 統合テスト（37 tests）
│   ├── TestToonEncoder                 # エンコーダーテスト
│   ├── TestToonFormatter               # フォーマッターテスト
│   ├── TestOutputManagerIntegration    # OutputManager統合テスト
│   └── TestFormatterProtocolCompliance # Protocol準拠テスト
└── (予定)
    └── benchmarks/
        └── test_toon_performance.py    # パフォーマンステスト
```

## 依存関係

### 内部依存

| コンポーネント | 依存先 |
|---------------|--------|
| ToonFormatter | ToonEncoder, BaseFormatter |
| OutputManager | ToonFormatter, JsonFormatter |
| MCP Tools | ToonFormatter, OutputManager, FileOutputManager |

### 外部依存

**なし** - 完全なカスタム実装のため、外部ライブラリへの依存はありません。

### Python バージョン

- **最小**: Python 3.10+
- **機能**: `list[str]` 型ヒント構文を使用

## パフォーマンス考慮事項

### 現在の実装状態

| 最適化戦略 | 状態 | 説明 |
|-----------|------|------|
| イテレーティブ実装 | ✅ 実装済み | 明示的スタックで再帰を排除 |
| スキーマ推論 | ✅ 実装済み | 最初のアイテムからスキーマを推論 |
| メモリ効率 | ✅ 実装済み | 明示的スタックで使用量を予測可能に |
| スキーマキャッシング | ❌ 未実装（オプション） | 同型配列のスキーマ推論結果をキャッシュ |
| ストリーミング | ❌ 未実装（オプション） | 大規模データセット用の `encode_lines()` ジェネレータ |
| 遅延評価 | ❌ 未実装（オプション） | 必要になるまでフォーマット変換を遅延 |

### ベンチマーク目標

| 指標 | 目標 |
|------|------|
| エンコードオーバーヘッド | JSON比 < 5% |
| メモリオーバーヘッド | JSON比 < 10% |
| トークン削減 | 50-70% |

## 実装状況サマリー

### 完了項目 ✅

| コンポーネント | ファイル | 状態 |
|---------------|---------|------|
| ToonEncoder | `formatters/toon_encoder.py` | ✅ 実装済み（イテレーティブ実装） |
| ToonFormatter | `formatters/toon_formatter.py` | ✅ 実装済み |
| BaseFormatter拡張 | `formatters/base_formatter.py` | ✅ 更新済み |
| OutputManager統合 | `output_manager.py` | ✅ 更新済み |
| ToonEncodeError例外 | `formatters/toon_encoder.py` | ✅ 実装済み |
| JSONフォールバック | `formatters/toon_formatter.py` | ✅ 実装済み |
| 循環参照検出 | `formatters/toon_encoder.py` | ✅ 実装済み |
| 最大ネスト深度制限 | `formatters/toon_encoder.py` | ✅ 実装済み |
| MCP Tools統合 | `mcp/tools/*.py` (8ツール) | ✅ 実装済み |
| CLI統合 | `cli_main.py`, `cli/commands/*.py` | ✅ 実装済み |
| 統合テスト (基礎) | `test_toon_formatter_integration.py` | ✅ 37 tests |
| エラーハンドリングテスト | `test_toon_error_handling.py` | ✅ 23 tests |
| MCP統合テスト | `mcp/test_toon_mcp_integration.py` | ✅ 24 tests |
| CLI統合テスト | `cli/test_toon_cli_integration.py` | ✅ 14 tests |
| ゴールデンマスタテスト | `golden_masters/toon/` | ✅ 18言語対応 |
| ドキュメント（英語） | `docs/toon-format-guide.md` | ✅ 作成済み |
| ドキュメント（日本語） | `docs/ja/toon-format-guide.md` | ✅ 作成済み |
| デモスクリプト | `examples/toon_demo.py` | ✅ 作成済み |
| ベンチマーク | `examples/toon_token_benchmark.py` | ✅ 50.6%削減達成 |

### 未完了項目 ❌ （オプション）

| コンポーネント | 状態 |
|---------------|------|
| スキーマキャッシング | ❌ 未実装（オプション） |
| ストリーミングエンコード | ❌ 未実装（オプション） |
| 遅延評価 | ❌ 未実装（オプション） |
