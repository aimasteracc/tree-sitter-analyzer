# 仕様書: 002 - 言語処理の抽象化と拡張性向上

**Feature**: Language Abstraction and Extensibility
**Date**: 2025-10-13
**Status**: Draft

## 1. 概要

本仕様書は、`tree-sitter-analyzer`の言語処理機能をリファクタリングし、拡張性と保守性を向上させるための新しいアーキテクチャを定義する。Strategy、Factory、およびPluginパターンを組み合わせ、言語固有の処理をカプセル化し、新しい言語の追加を容易にすることを目的とする。

## 2. アーキテクチャ設計

### 2.1. 設計パターン

- **Strategy Pattern**: `ILanguagePlugin`インターフェースを定義し、各言語の解析ロジックを具体的な戦略として実装する。
- **Factory Pattern**: `LanguagePluginFactory`が、言語名に基づいて適切な`ILanguagePlugin`インスタンスを生成する。
- **Plugin Pattern**: 新しい言語サポートを独立したプラグインとして追加できる構造を提供する。

### 2.2. コンポーネント図

```mermaid
graph TD
    subgraph Core System
        A[AnalysisEngine] --> B{LanguagePluginFactory};
        B --> C{ILanguagePlugin};
    end

    subgraph Language Plugins
        D[PythonPlugin] --|> C;
        E[JavaPlugin] --|> C;
        F[TypeScriptPlugin] --|> C;
        G[FutureLanguagePlugin] --|> C;
    end

    A -- uses --> C;

    style D fill:#f9f,stroke:#333,stroke-width:2px
    style E fill:#f9f,stroke:#333,stroke-width:2px
    style F fill:#f9f,stroke:#333,stroke-width:2px
    style G fill:#f9f,stroke:#333,stroke-width:2px,stroke-dasharray: 5 5
```

## 3. インターフェース定義

### 3.1. `ILanguagePlugin`

言語固有の処理をカプセル化する中心的なインターフェース。

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any

class ILanguagePlugin(ABC):
    """
    言語固有の解析ロジックを定義するインターフェース。
    """
    @staticmethod
    @abstractmethod
    def get_language_name() -> str:
        """言語名を返す (例: 'python', 'java')"""
        pass

    @abstractmethod
    def get_supported_element_types(self) -> List[str]:
        """サポートするCodeElementのタイプを返す"""
        pass

    @abstractmethod
    def parse(self, file_content: str) -> List['CodeElement']:
        """
        ファイル内容を解析し、CodeElementのリストを生成する。
        """
        pass

    @abstractmethod
    def get_queries(self) -> Dict[str, str]:
        """
        言語固有のtree-sitterクエリを返す。
        キー: クエリ名 (例: 'methods', 'classes')
        値: クエリ文字列
        """
        pass
```

### 3.2. `LanguagePluginFactory`

言語名に基づいてプラグインインスタンスを生成するファクトリ。

```python
class LanguagePluginFactory:
    _plugins = {}

    @classmethod
    def register_plugin(cls, plugin: ILanguagePlugin):
        """プラグインを動的に登録する"""
        language = plugin.get_language_name()
        if language not in cls._plugins:
            cls._plugins[language] = plugin

    @classmethod
    def create_plugin(cls, language: str) -> ILanguagePlugin:
        """言語名に対応するプラグインを生成する"""
        if language not in cls._plugins:
            raise ValueError(f"Unsupported language: {language}")
        return cls._plugins[language]()
```

## 4. データモデル

### 4.1. `CodeElement`

既存の`CodeElement`モデルをそのまま利用する。言語プラグインは、この統一データモデルに従って解析結果を返す責任を負う。

```python
class CodeElement:
    element_type: str
    name: str
    start_line: int
    end_line: int
    # ... 他の属性
    metadata: Dict[str, Any] # 言語固有の追加情報
```

## 5. 実装ガイドライン

1.  **プラグインの実装**:
    - 新しい言語サポートを追加する場合、`ILanguagePlugin`を継承した新しいクラスを作成する。
    - `tree_sitter_analyzer/plugins/`ディレクトリ内に言語ごとのファイル（例: `python_plugin.py`）を作成する。
2.  **プラグインの登録**:
    - `LanguagePluginFactory`に、実装したプラグインを登録する処理を追加する。将来的には、エントリーポイントを用いた動的なプラグイン検出メカニズムを検討する。
3.  **`AnalysisEngine`の更新**:
    - 既存の`AnalysisEngine`をリファクタリングし、`LanguagePluginFactory`を使用して言語処理を委譲するように変更する。

## 6. マイグレーション手順

1.  **インターフェース定義**: `ILanguagePlugin`と`LanguagePluginFactory`を定義する。
2.  **既存ロジックの移行**: 既存のPython、Java、TypeScriptの解析ロジックを、それぞれ`PythonPlugin`, `JavaPlugin`, `TypeScriptPlugin`に移行する。
3.  **`AnalysisEngine`のリファクタリング**: `AnalysisEngine`が新しいファクトリとプラグインを利用するように修正する。
4.  **テストの更新**: 既存のテストを更新し、新しいアーキテクチャで正しく動作することを確認する。

## 7. テスト要件

- `LanguagePluginFactory`が正しくプラグインを登録・生成できることの単体テスト。
- 各`ILanguagePlugin`実装が、仕様通りにコードを解析し、`CodeElement`を生成することの単体テスト。
- `AnalysisEngine`が、複数の言語プラグインを正しく利用して解析できることの結合テスト。
- サポートされていない言語が指定された場合のエラーハンドリングテスト。