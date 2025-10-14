# 仕様書: 004 - フォーマッターの拡張と動的管理

**Feature**: Formatter Extension and Dynamic Management
**Date**: 2025-10-13
**Status**: Draft

## 1. 概要

本仕様書は、`tree-sitter-analyzer`の出力フォーマット機能を拡張し、新しいフォーマッターを動的に追加・管理するためのアーキテクチャを定義する。`FormatterRegistry`を導入し、`analyze_code_structure`ツールなどの出力形式を柔軟に拡張可能にすることを目的とする。

## 2. 背景

現在のフォーマット機能は、`full`, `compact`, `csv`, `json`などの固定形式に限定されている。新しい出力形式（例: `markdown`, `xml`）を追加するには、コアロジックの変更が必要となり、拡張性に欠ける。この問題を解決するため、フォーマッターをプラグインとして動的に登録・管理する仕組みを導入する。

## 3. アーキテクチャ設計

### 3.1. 設計パターン

- **Strategy Pattern**: `IFormatter`インターフェースを定義し、各フォーマット形式の変換ロジックを具体的な戦略として実装する。
- **Registry Pattern**: `FormatterRegistry`が、利用可能なすべての`IFormatter`実装を管理し、要求されたフォーマット形式に対応するインスタンスを提供する。

### 3.2. コンポーネント図

```mermaid
graph TD
    subgraph Core System
        A[TableFormatTool] --> B{FormatterRegistry};
        B --> C{IFormatter};
    end

    subgraph Formatters
        D[JsonFormatter] --|> C;
        E[CsvFormatter] --|> C;
        F[MarkdownFormatter] --|> C;
        G[XmlFormatter] --|> C;
    end

    A -- uses --> C;

    style D fill:#dff,stroke:#333,stroke-width:2px
    style E fill:#dff,stroke:#333,stroke-width:2px
    style F fill:#dff,stroke:#333,stroke-width:2px
    style G fill:#dff,stroke:#333,stroke-width:2px,stroke-dasharray: 5 5
```

## 4. インターフェース定義

### 4.1. `IFormatter`

`CodeElement`のリストを特定の文字列形式に変換する処理をカプセル化するインターフェース。

```python
from abc import ABC, abstractmethod
from typing import List
from tree_sitter_analyzer.models import CodeElement

class IFormatter(ABC):
    """
    CodeElementのリストを特定の文字列形式に変換するインターフェース。
    """
    @staticmethod
    @abstractmethod
    def get_format_name() -> str:
        """フォーマット名を返す (例: 'json', 'csv', 'markdown')"""
        pass

    @abstractmethod
    def format(self, elements: List[CodeElement]) -> str:
        """
        CodeElementのリストを受け取り、フォーマットされた文字列を返す。
        """
        pass
```

### 4.2. `FormatterRegistry`

利用可能なフォーマッターを管理し、要求に応じて提供するレジストリ。

```python
class FormatterRegistry:
    _formatters = {}

    @classmethod
    def register_formatter(cls, formatter: IFormatter):
        """フォーマッターを動的に登録する"""
        format_name = formatter.get_format_name()
        if format_name not in cls._formatters:
            cls._formatters[format_name] = formatter

    @classmethod
    def get_formatter(cls, format_name: str) -> IFormatter:
        """フォーマット名に対応するフォーマッターを取得する"""
        if format_name not in cls._formatters:
            raise ValueError(f"Unsupported format: {format_name}")
        return cls._formatters[format_name]()

    @classmethod
    def get_available_formats(cls) -> List[str]:
        """利用可能なすべてのフォーマット名をリストで返す"""
        return list(cls._formatters.keys())
```

## 5. `TableFormatTool` の更新

`analyze_code_structure`ツール（`TableFormatTool`）をリファクタリングし、`FormatterRegistry`を利用して出力を生成するように変更する。

- `format_type`パラメータのバリデーションは、`FormatterRegistry.get_available_formats()`を呼び出して動的に行う。
- `format_type`で指定されたフォーマッターを`FormatterRegistry.get_formatter()`で取得し、`format()`メソッドを実行して最終的な出力を得る。

```python
# TableFormatTool.execute の一部 (イメージ)
format_type = arguments.get("format_type", "full")
available_formats = FormatterRegistry.get_available_formats()

if format_type not in available_formats:
    raise ValueError(f"Invalid format_type. Available formats: {available_formats}")

# ... (CodeElementのリストを生成) ...
elements = self.analyze_structure(file_path)

formatter = FormatterRegistry.get_formatter(format_type)
formatted_output = formatter.format(elements)

return {"table_output": formatted_output}
```

## 6. 実装ガイドライン

1.  **インターフェースとレジストリの実装**: `IFormatter`と`FormatterRegistry`を`tree_sitter_analyzer/formatters/`（仮）ディレクトリに実装する。
2.  **既存フォーマッターの移行**: 既存の`json`, `csv`などのフォーマットロジックを、`IFormatter`を継承した`JsonFormatter`, `CsvFormatter`クラスに移行する。
3.  **レジストリへの登録**: `FormatterRegistry`に、実装したフォーマッターを登録する処理を追加する。
4.  **`TableFormatTool`のリファクタリング**: `TableFormatTool`が`FormatterRegistry`を利用するように修正する。

## 7. テスト要件

- `FormatterRegistry`が正しくフォーマッターを登録・取得できることの単体テスト。
- 各`IFormatter`実装が、仕様通りに`CodeElement`リストを文字列に変換できることの単体テスト。
- `TableFormatTool`が、動的に取得したフォーマッターを利用して正しい出力を行えることの結合テスト。
- サポートされていないフォーマット形式が指定された場合のエラーハンドリングテスト。