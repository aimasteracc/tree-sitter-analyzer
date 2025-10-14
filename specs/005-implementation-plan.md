# 仕様書: 005 - 実装計画とマイグレーション手順

**Feature**: Implementation Plan and Migration Strategy
**Date**: 2025-10-13
**Status**: Draft

## 1. 概要

本仕様書は、`tree-sitter-analyzer`のアーキテクチャ刷新に関する実装計画を定義する。以下の仕様書で定義された変更を、4つのフェーズに分けて段階的に実装・移行する戦略をとる。

- `002-language-abstraction-spec.md`
- `003-html-css-support-spec.md`
- `004-formatter-extension-spec.md`

## 2. 実装フェーズ

### フェーズ 1: 基盤アーキテクチャの構築

**目的**: 言語処理の抽象化基盤を構築し、既存の言語サポートを新しいアーキテクチャに移行する。

**期間**: 2週間

**タスク**:
1.  **インターフェース定義**:
    - `ILanguagePlugin` インターフェースを作成する。
    - `LanguagePluginFactory` クラスを作成する。
2.  **既存言語のプラグイン化**:
    - `PythonPlugin`, `JavaPlugin`, `TypeScriptPlugin` を作成し、既存の解析ロジックを移行する。
3.  **ファクトリへの登録**:
    - 作成した3つのプラグインを `LanguagePluginFactory` に静的に登録する。
4.  **`AnalysisEngine` のリファクタリング**:
    - `AnalysisEngine` が `LanguagePluginFactory` を介して言語処理を行うように修正する。
5.  **テストの更新**:
    - 既存の単体テストおよび結合テストを、新しいアーキテクチャに合わせて更新する。

**完了条件**:
- 既存の全テストがパスすること。
- Python, Java, TypeScript の解析機能が、リファクタリング前と同等に動作すること。

### フェーズ 2: フォーマッター拡張機能の実装

**目的**: 出力フォーマット機能を拡張可能なアーキテクチャに刷新する。

**期間**: 1週間

**タスク**:
1.  **インターフェース定義**:
    - `IFormatter` インターフェースを作成する。
    - `FormatterRegistry` クラスを作成する。
2.  **既存フォーマッターの移行**:
    - `JsonFormatter`, `CsvFormatter`, `FullFormatter`, `CompactFormatter` を作成し、既存のロジックを移行する。
3.  **レジストリへの登録**:
    - 作成したフォーマッターを `FormatterRegistry` に登録する。
4.  **`TableFormatTool` のリファクタリング**:
    - `TableFormatTool` (`analyze_code_structure`) が `FormatterRegistry` を利用して出力を生成するように修正する。
5.  **テストの追加**:
    - フォーマッター関連の新しい単体テストおよび結合テストを作成する。

**完了条件**:
- `analyze_code_structure` ツールが、既存のフォーマット形式 (`json`, `csv`等) で正しく出力できること。
- 新しいフォーマッターを簡単に追加できる基盤が整うこと。

### フェーズ 3: HTML/CSS サポートの追加

**目的**: HTMLとCSSの特殊な構造に対応するための新しいデータモデルとプラグインを実装する。

**期間**: 2週間

**タスク**:
1.  **データモデルの追加**:
    - `CodeElement` を継承した `MarkupElement` (HTML用) と `StyleElement` (CSS用) を作成する。
2.  **プラグインの実装**:
    - `HtmlPlugin` を作成し、HTMLを解析して `MarkupElement` のツリーを構築するロジックを実装する。
    - `CssPlugin` を作成し、CSSを解析して `StyleElement` のリストを生成するロジックを実装する。
3.  **要素分類システムの実装**:
    - 各プラグイン内に、仕様書で定義された要素分類ロジックを実装する。
4.  **ファクトリへの登録**:
    - `HtmlPlugin` と `CssPlugin` を `LanguagePluginFactory` に登録する。
5.  **テストの追加**:
    - HTMLとCSSの解析、および要素分類に関する新しいテストケースを追加する。

**完了条件**:
- HTMLファイルとCSSファイルを解析し、それぞれ `MarkupElement` と `StyleElement` の構造化データを取得できること。
- 要素分類システムが正しく機能すること。

### フェーズ 4: 統合とドキュメント更新

**目的**: すべての変更を統合し、関連ドキュメントを更新してプロジェクトを完了する。

**期間**: 1週間

**タスク**:
1.  **最終統合テスト**:
    - すべての言語 (Python, Java, TS, HTML, CSS) とフォーマッターが協調して動作することを確認するエンドツーエンドテストを実施する。
2.  **パフォーマンス測定**:
    - 新しいアーキテクチャにおけるパフォーマンスを測定し、リファクタリング前と比較して大きな劣化がないことを確認する。
3.  **仕様書の更新**:
    - `spec.md` と `data-model.md` を更新し、新しい仕様書 (`002`, `003`, `004`) への参照を追加する。
    - すべての仕様書のステータスを `Draft` から `Final` に更新する。
4.  **READMEの更新**:
    - `README.md` を更新し、新しくサポートされた言語 (HTML, CSS) とフォーマット形式について追記する。

**完了条件**:
- すべての機能が安定して動作し、ドキュメントが最新の状態に更新されていること。

## 3. タイムライン

```mermaid
gantt
    title アーキテクチャ刷新プロジェクト タイムライン
    dateFormat  YYYY-MM-DD
    section フェーズ 1
    基盤アーキテクチャ構築 : 2025-10-14, 14d
    section フェーズ 2
    フォーマッター拡張 : 2025-10-28, 7d
    section フェーズ 3
    HTML/CSSサポート追加 : 2025-11-04, 14d
    section フェーズ 4
    統合とドキュメント更新 : 2025-11-18, 7d