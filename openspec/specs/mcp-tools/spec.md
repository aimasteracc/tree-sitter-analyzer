# mcp-tools Specification

## Purpose
TBD - created by archiving change fix-search-content-parameters. Update Purpose after archive.
## Requirements
### Requirement: 出力形式パラメータ排他制御

search_contentツールは出力形式に関連するパラメータの同時指定を検証し、競合を防止しなければならない（MUST）。

#### Scenario: 単一出力形式パラメータの許可

**Given** search_contentツールにアクセスする場合
**When** `total_only=True`のみを指定する
**Then** 処理が正常に実行される
**And** 期待される形式の結果が返される

#### Scenario: 複数出力形式パラメータの拒否

**Given** search_contentツールにアクセスする場合
**When** `total_only=True`と`count_only_matches=True`を同時に指定する
**Then** バリデーションエラーが発生する
**And** 明確なエラーメッセージが返される
**And** "出力形式パラメータは排他的です"という内容のメッセージが含まれる

#### Scenario: 全出力形式パラメータの排他制御

**Given** search_contentツールにアクセスする場合
**When** `total_only`、`count_only_matches`、`summary_only`、`group_by_file`、`optimize_paths`のうち複数を同時指定する
**Then** バリデーションエラーが発生する
**And** 競合するパラメータ名が明示される

### Requirement: max_count機能の正常動作

search_contentツールはmax_countパラメータが指定された場合、ripgrepコマンドに正しく`-m`オプションを適用しなければならない（MUST）。

#### Scenario: max_countパラメータの適用

**Given** search_contentツールにmax_countパラメータを指定する場合
**When** `max_count=5`を設定してクエリを実行する
**Then** ripgrepコマンドに`-m 5`オプションが含まれる
**And** 結果の件数が5件以下に制限される

#### Scenario: max_countのデフォルト値適用

**Given** search_contentツールでmax_countを指定しない場合
**When** 検索クエリを実行する
**Then** デフォルトの制限値が適用される
**And** ripgrepコマンドに適切な`-m`オプションが含まれる

#### Scenario: max_countの上限制御

**Given** search_contentツールに過大なmax_countを指定する場合
**When** `max_count=50000`を設定する
**Then** 安全な上限値（10000）に調整される
**And** ripgrepコマンドに`-m 10000`が適用される

### Requirement: キャッシュキー生成改善

search_contentツールのキャッシュシステムは出力形式パラメータを考慮した適切なキャッシュキー生成を行わなければならない（MUST）。

#### Scenario: 出力形式別キャッシュキー生成

**Given** 同一の検索クエリで異なる出力形式を指定する場合
**When** 最初に`total_only=True`で実行し、次に`count_only_matches=True`で実行する
**Then** 異なるキャッシュキーが生成される
**And** それぞれの形式に対応した結果が返される

#### Scenario: キャッシュヒット時の形式一致

**Given** キャッシュに保存された検索結果が存在する場合
**When** 同じクエリと出力形式で再度検索する
**Then** キャッシュから適切な形式の結果が返される
**And** `cache_hit=True`が設定される

#### Scenario: 形式変更時のキャッシュミス

**Given** `total_only=True`でキャッシュされた結果が存在する場合
**When** 同じクエリで`summary_only=True`を指定する
**Then** キャッシュミスが発生する
**And** 新しい検索が実行される
**And** 適切な形式の結果が返される

### Requirement: エラーハンドリング強化

search_contentツールは明確で有用なエラーメッセージを提供し、デバッグを支援しなければならない（MUST）。

#### Scenario: パラメータ競合エラーの詳細

**Given** 競合する出力形式パラメータを指定する場合
**When** バリデーションエラーが発生する
**Then** エラーメッセージに競合するパラメータ名が含まれる
**And** 正しい使用方法の例が提示される

#### Scenario: max_count範囲外エラー

**Given** 不正なmax_count値を指定する場合
**When** 負の値や文字列を指定する
**Then** 適切なエラーメッセージが返される
**And** 許可される値の範囲が明示される

### Requirement: 後方互換性維持

search_contentツールの修正は既存のAPIや動作を変更せず、完全な後方互換性を維持しなければならない（MUST）。

#### Scenario: 既存パラメータの動作保持

**Given** 修正前のsearch_contentツール使用コードが存在する場合
**When** 修正後のツールで同じパラメータを使用する
**Then** 同一の結果が返される
**And** エラーが発生しない

#### Scenario: レガシー出力形式の保持

**Given** 出力形式パラメータを指定しない場合
**When** 検索を実行する
**Then** デフォルトの標準形式で結果が返される
**And** 従来と同じフィールド構成が維持される

### Requirement: 型安全性とコード品質

search_contentツール関連のコードはmypyとruffの品質チェックに完全に準拠しなければならない（MUST）。

#### Scenario: 型注釈の完全性

**Given** search_contentツール関連のPythonコードを検査する場合
**When** `mypy --strict`を実行する
**Then** 型エラーが発生しない
**And** 全ての関数と変数に適切な型注釈が付与されている

#### Scenario: コード品質基準準拠

**Given** search_contentツール関連のコードを検査する場合
**When** `ruff check`を実行する
**Then** lintエラーが発生しない
**And** PEP 8準拠のコード記述になっている

### Requirement: テストカバレッジと品質保証

search_contentツールの修正は包括的なテストスイートでカバーされ、90%以上のテストカバレッジを維持しなければならない（MUST）。

#### Scenario: 新機能のテストカバレッジ

**Given** 新たに追加された機能を検証する場合
**When** テストスイートを実行する
**Then** 全ての新機能がテストされている
**And** エッジケースとエラーケースがカバーされている

#### Scenario: 既存機能の非破壊テスト

**Given** 既存のsearch_content関連テストを実行する場合
**When** 修正後のコードでテストする
**Then** 全ての既存テストが通過する
**And** 予期しないテスト失敗が発生しない

