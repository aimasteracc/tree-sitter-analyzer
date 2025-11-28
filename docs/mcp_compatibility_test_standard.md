# MCP互換性テスト標準化プロセス

## 1. はじめに

このドキュメントは、`tree-sitter-analyzer`の異なるバージョン間におけるMCP（Model Context Protocol）ツールの互換性テストを、一貫性と再現性をもって実施するための標準プロセスを定義します。

## 2. 基本方針

### 2.1. 目的

- **一貫性の確保**: 誰がいつ実行しても、同じ基準で互換性を評価できるプロセスを確立します。
- **再現性の保証**: テスト環境の構築から結果の分析まで、すべてのステップを明確に文書化し、誰でも同じ結果を再現できるようにします。
- **変更の早期発見**: 破壊的変更、非破壊的変更、予期せぬバグをリリース前に特定し、影響を最小限に抑えます。
- **明確な情報提供**: 検出された変更点とその影響について、開発者と利用者に分かりやすいレポートを提供します。

### 2.2. 3段階のテストアプローチ

本プロセスは、自動化と手動レビューを組み合わせた3段階のアプローチを採用します。

1. **ステージ1: 自動実行と出力生成**

   - 自動化スクリプトを用いて、比較対象の各バージョンで定義済みのテストケースを実行し、出力結果（JSON、テキストファイル等）を生成します。
   - この段階では、ツールの基本的な応答性（クラッシュしないか、エラーを返さないか）と、期待される形式で出力が生成されることを確認します。
1. **ステージ2: 機械的な差分検出**

   - ステージ1で生成されたバージョン間の出力ファイルを、専用ツール（例: `diff`, `jq`）を用いて機械的に比較し、すべての差分を検出します。
   - これにより、`capture_name` のようなJSON構造の変更や、テキスト出力のわずかな違いも見逃さずに捉えることができます。
1. **ステージ3: 専門家によるレビューと評価**

   - 検出された差分が「破壊的変更」「意図した仕様変更」「パフォーマンス改善」「バグ」のいずれに該当するかを、開発者がレビューし、分類します。
   - この評価に基づき、最終的な互換性レポートを作成し、必要な対応（ドキュメント更新、マイグレーションガイド作成等）を決定します。

### 2.3. 成果物とバージョン管理

- テストに使用するすべての設定ファイル、スクリプト、テストケース定義、および生成されたレポートは、Gitリポジトリでバージョン管理します。
- テスト結果の出力ファイルは、バージョンごとに明確に分離されたディレクトリ（例: `compatibility_test/results/vA/`, `compatibility_test/results/vB/`）に保存し、追跡可能性を確保します。

### 2.4. 再現性のための環境定義

- `mcp_settings.json` の設定テンプレート、必要な環境変数、依存関係のインストール手順を文書化し、クリーンな環境からでも容易にテスト環境を再現できるようにします。

## 3. テスト環境の標準化

互換性テストの再現性を確保するため、以下の手順でテスト環境を標準化します。

### 3.1. ディレクトリ構造

テスト関連のファイルは、プロジェクトルートの `compatibility_test/` ディレクトリに集約します。

```
tree-sitter-analyzer/
├── compatibility_test/
│   ├── README.md                           # 互換性テストガイド
│   ├── test_cases.json                     # テストケース定義
│   ├── troubleshooting_guide.md            # トラブルシューティングガイド
│   ├── scripts/                            # テスト自動化スクリプト
│   │   ├── run_compatibility_test.py       # メインテストスクリプト
│   │   └── analyze_differences.py          # 差分分析スクリプト
│   ├── templates/                          # 設定ファイルテンプレート
│   │   ├── mcp_settings.json.template      # MCPサーバー設定テンプレート
│   │   └── comparison_report_template.md   # レポートテンプレート
│   ├── results/                            # テスト結果の出力先（自動生成）
│   │   ├── vA/                             # バージョンAの出力
│   │   └── vB/                             # バージョンBの出力
│   └── reports/                            # 分析レポート（自動生成）
└── ...
```

### 3.2. MCPサーバー設定 (`mcp_settings.json`)

`mcp_settings.json` は、テスト対象のバージョンを定義する中心的なファイルです。

#### 3.2.1. 設定の基本構造

比較したい2つのバージョン（以下、vA, vB）に対して、それぞれサーバー設定を定義します。

- **サーバー名**: `tree-sitter-analyzer-vA`, `tree-sitter-analyzer-vB` のように、バージョンを明記します。
- **コマンド**: `uvx --from tree-sitter-analyzer[mcp]=={VERSION} tree-sitter-analyzer-mcp` を使用して、特定のバージョンをインストール・実行します。
- **環境変数 `TREE_SITTER_OUTPUT_PATH`**: 各バージョンの出力が混在しないよう、バージョン固有のパス（例: `.analysis-vA`）を指定します。
- **有効/無効フラグ `disabled`**: テスト実行時に、スクリプトがこのフラグを切り替えます。

#### 3.2.2. 設定テンプレート

`compatibility_test/templates/mcp_settings.json.template` として、以下のテンプレートを用意します。`{VERSION_A}` と `{VERSION_B}` は、テスト実施時に具体的なバージョン番号に置換します。

```json
{
  "mcpServers": {
    "tree-sitter-analyzer-vA": {
      "command": "uv",
      "args": [
        "run", "--with", "tree-sitter-analyzer[mcp]=={VERSION_A}",
        "python", "-m", "tree_sitter_analyzer.mcp.server"
      ],
      "env": {
        "TREE_SITTER_PROJECT_ROOT": "{PROJECT_ROOT}",
        "TREE_SITTER_OUTPUT_PATH": "{PROJECT_ROOT}/.analysis-{VERSION_A}"
      },
      "alwaysAllow": ["..."],
      "timeout": 3600,
      "disabled": true
    },
    "tree-sitter-analyzer-vB": {
      "command": "uv",
      "args": [
        "run", "--with", "tree-sitter-analyzer[mcp]=={VERSION_B}",
        "python", "-m", "tree_sitter_analyzer.mcp.server"
      ],
      "env": {
        "TREE_SITTER_PROJECT_ROOT": "{PROJECT_ROOT}",
        "TREE_SITTER_OUTPUT_PATH": "{PROJECT_ROOT}/.analysis-{VERSION_B}"
      },
      "alwaysAllow": ["..."],
      "timeout": 3600,
      "disabled": true
    }
  }
}
```

*Note: `{PROJECT_ROOT}` は、テスト実行スクリプトが自動的に絶対パスに置換します。*

### 3.3. バージョン切り替え手順

テストスクリプトは、以下の手順でバージョンを切り替えます。

1. `mcp_settings.json` を読み込みます。
2. すべての `tree-sitter-analyzer-*` サーバーの `disabled` フラグを `true` に設定します。
3. テスト対象の単一バージョン（例: `tree-sitter-analyzer-vA`）の `disabled` フラグのみを `false` に設定します。
4. 変更を `mcp_settings.json` に保存します。
5. MCPサーバーが再起動し、指定したバージョンが有効になるのを待ちます（約5秒）。

## 4. テスト対象と実行手順の標準化

### 4.1. テスト対象ツール

原則として、以下の8つの主要MCPツールをテスト対象とします。

1. `analyze_code_structure`
2. `query_code`
3. `check_code_scale`
4. `extract_code_section`
5. `set_project_path`
6. `list_files`
7. `find_and_grep`
8. `search_content`

### 4.2. テストケースの定義

テストの柔軟性と拡張性を確保するため、テストケースは外部のJSONファイル (`compatibility_test/test_cases.json`) で定義します。

#### 4.2.1. `test_cases.json` の構造

```json
{
  "analyze_code_structure": [
    {
      "id": "java_sample",
      "params": { "file_path": "examples/Sample.java", "format_type": "full" },
      "output_file": "analyze_code_structure_java.txt"
    },
    {
      "id": "python_engine",
      "params": { "file_path": "tree_sitter_analyzer/core/engine.py", "format_type": "full" },
      "output_file": "analyze_code_structure_python.txt"
    }
  ],
  "query_code": [
    {
      "id": "java_methods",
      "params": { "file_path": "examples/Sample.java", "query_key": "methods" },
      "output_file": "query_code_java_methods.json"
    }
  ],
  "...": "..."
}
```

- **キー**: ツール名 (`analyze_code_structure`など)。
- **`id`**: テストケースの一意な識別子。
- **`params`**: MCPツールに渡す引数。
- **`output_file`**: 結果を保存するファイル名。出力は `compatibility_test/results/{VERSION}/{output_file}` に保存されます。

### 4.3. テスト実行手順 (ステージ1)

1. **テストの準備**:

   - 比較したいバージョンAとBを決定します (例: `1.9.2`, `1.9.3`)。
   - `mcp_settings.json` に、両バージョンのサーバー定義が存在することを確認します。
1. **自動テストの実行**:

   - 以下のコマンドを実行して、テストを開始します。

   ```bash
   python compatibility_test/scripts/run_compatibility_test.py --version-a {VERSION_A} --version-b {VERSION_B}
   ```
1. **スクリプトの内部動作**:

   - 引数で指定されたバージョン（vA, vB）のテストを実行します。
   - **バージョンAのテスト**:
    1. `mcp_settings.json` でバージョンAを有効化します。
    2. `test_cases.json` に基づき、全テストケースを実行します。
    3. 結果を `compatibility_test/results/vA/` に保存します。

- **バージョンBのテスト**:

  1. `mcp_settings.json` でバージョンBを有効化します。
  2. `test_cases.json` に基づき、全テストケースを実行します。
  3. 結果を `compatibility_test/results/vB/` に保存します。

4. **完了**:

   - `results/vA` と `results/vB` に、比較対象となる一連の出力ファイルが生成されたことを確認します。

### 4.4. キャッシュ管理

テスト結果の信頼性と再現性を保証するため、キャッシュ管理は本プロセスの重要な要素です。

#### 4.4.1. キャッシュのクリア

**原則として、各バージョンのテストスイートを実行する直前に、関連するすべてのキャッシュをクリアしなければなりません。** これにより、バージョン間でキャッシュが共有され、古いバージョンの結果が新しいバージョンのテストに影響を与える「キャッシュ汚染」を防ぎます。

- **自動クリア**: `run_compatibility_test.py` スクリプトは、内部で `compatibility_test/utils/cache_manager.py` を呼び出し、テスト開始前に自動的にキャッシュをクリアします。
- **手動クリア**: 手動でテストを実行する場合や、デバッグ時には、以下のコマンドでキャッシュを明示的にクリアする必要があります。
  ```bash
  python compatibility_test/utils/cache_manager.py clear
  ```

#### 4.4.2. キャッシュ状態のレポート

テストの透明性を高めるため、テスト実行前後のキャッシュ状態を記録し、分析レポートに含めることを推奨します。

- `compatibility_test/utils/cache_reporter.py` は、各キャッシュシステム（`UnifiedAnalysisEngine` および `SearchContentTool`）の統計情報（ヒット率、アイテム数など）を取得し、レポートを生成する機能を提供します。
- テスト結果に予期せぬ一致や不一致が見られた場合、このキャッシュレポートを参照することで、キャッシュが影響しているかどうかを判断する手がかりとなります。

#### 4.4.3. キャッシュ管理の重要性

- **独立性の確保**: 各バージョンのテストは、他のバージョンから完全に独立した状態で実行されるべきです。キャッシュのクリアは、この独立性を保証するための最も重要なステップです。
- **バグの正確な特定**: キャッシュされた古いデータが返されることで、修正されたはずのバグが再現したり、逆に新しいバグが見過ごされたりする事態を防ぎます。
- **パフォーマンス評価の精度向上**: 純粋な実行時間を測定するためには、キャッシュヒットによる速度向上を排除する必要があります。

**キャッシュシステムの詳細な設計分析については、[キャッシュシステム設計分析](CACHE_SYSTEM_ANALYSIS.md)を参照してください。**

## 5. 比較分析と評価基準の標準化

### 5.1. 差分検出の方法 (ステージ2)

ステージ1で生成された出力ファイルを、以下の方法で機械的に比較します。

#### 5.1.1. テキストファイルの比較

標準の `diff` コマンドを使用して差分を確認します。

```bash
diff compatibility_test/results/vA/output.txt compatibility_test/results/vB/output.txt
```

#### 5.1.2. JSONファイルの比較

`jq` と `diff` を組み合わせて、キーの順序が異なる場合でも意味的な差分を検出します。

```bash
diff <(jq -S . compatibility_test/results/vA/output.json) <(jq -S . compatibility_test/results/vB/output.json)
```

*(`-S` オプションでキーをソートしてから比較)*

### 5.2. 互換性評価の基準 (ステージ3)

検出された差分は、以下の基準に基づいて専門家がレビューし、分類します。

| 分類                    | 定義                                                               | 例                                                                                                 | 影響度     |
| :---------------------- | :----------------------------------------------------------------- | :------------------------------------------------------------------------------------------------- | :--------- |
| **破壊的変更**          | 既存のクライアント実装が正しく動作しなくなる可能性のある変更。     | ・JSONキー名の変更 (`methods`→`method`)<br>・必須フィールドの削除<br>・データ型の変更 (string→int) | **高**     |
| **非破壊的変更**        | 機能追加や改善であり、既存のクライアント実装に影響を与えない変更。 | ・新しいフィールドの追加<br>・パフォーマンスメトリクスの変動<br>・ログメッセージの変更             | **中〜低** |
| **バグ/意図しない変更** | どちらかのバージョンで明らかに誤った出力がされている変更。         | ・不正な形式のJSON<br>・空であるべきでないフィールドが空<br>・分析結果の欠落                       | **高〜低** |
| **一致**                | 出力内容が完全に同一である、または意味的に等価である状態。         | ・テキスト/JSONファイルが完全一致                                                                  | **なし**   |

### 5.3. レポート生成

分析結果は、`compatibility_test/reports/` に以下の標準フォーマットで記録します。

**ファイル名**: `comparison_report_{VERSION_A}_vs_{VERSION_B}.md`

```markdown
# 互換性比較レポート: v{VERSION_A} vs v{VERSION_B}

- **テスト実施日**: YYYY-MM-DD
- **担当者**: (担当者名)

## 1. 総評

(例: v{VERSION_B}はv{VERSION_A}に対して後方互換性を維持していますが、1件の破壊的変更が確認されました。)

## 2. 差分詳細

### 2.1. 破壊的変更

| ツール | テストケースID | 変更内容 | 影響と推奨対応 |
| :--- | :--- | :--- | :--- |
| `query_code` | `java_methods` | `capture_name`が`methods`から`method`に変更 | クライアントは両方のキーに対応する必要がある。マイグレーションガイドで通知。 |

### 2.2. 非破壊的変更

| ツール | テストケースID | 変更内容 |
| :--- | :--- | :--- |
| `find_and_grep` | `python_class` | `meta`情報に`execution_time`が追加 |

### 2.3. バグ/意図しない変更

| ツール | テストケースID | 問題の内容 |
| :--- | :--- | :--- |
| `analyze_code_structure` | `java_sample` | v{VERSION_B}で一部のメソッドが欠落 |

### 2.4. 一致した項目

- `check_code_scale` (全テストケース)
- `extract_code_section` (全テストケース)
```

## JSON比較のベストプラクティス

### 設定駆動型比較
`compatibility_test/config/comparison_config.json` を使用することで、JSONの比較方法を柔軟に設定できます。これにより、テストの意図に沿った、より意味のある比較が可能になります。

主な設定項目：
- `ignore_fields`: タイムスタンプや実行時間など、比較から除外したいフィールドを指定します。
- `sort_arrays_by`: 特定のキーに基づいて配列をソートし、順序の変動による差分を無視します。
- `normalize_keys`: キーの順序を正規化し、オブジェクト内のキーの順序が異なっていても差分として検出しません。
- `preserve_array_order`: `matches` のように、順序が重要で維持されるべき配列を指定します。

この設定を活用することで、本質的でない差分を排除し、重要な変更点のみに焦点を当てた効率的な互換性テストが実現できます。
