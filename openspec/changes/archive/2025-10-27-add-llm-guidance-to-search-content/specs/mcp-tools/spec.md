## ADDED Requirements

### Requirement: search_contentツールのLLMガイダンス強化

search_contentツールは、LLMが自律的に最適なパラメータを選択できるよう、トークン効率性とベストプラクティスに関する包括的なガイダンスをツール定義に埋め込まなければならない（MUST）。

#### Scenario: ツール説明への効率性ガイドセクション追加

**GIVEN** search_contentツールの定義を参照する場合
**WHEN** LLMがツールのdescriptionフィールドを読む
**THEN** description冒頭に以下のセクションが含まれる：
- `⚠️ IMPORTANT: Token Efficiency Guide` - トークン効率性の重要性説明
- `🎯 RECOMMENDED WORKFLOW` - 段階的使用戦略のフローチャート
- `💡 TOKEN EFFICIENCY COMPARISON` - 各出力形式のトークンコスト比較表

**AND** 各セクションが明確に区切られている
**AND** 最重要情報が先頭に配置されている

#### Scenario: トークン効率性比較表の提供

**GIVEN** search_contentツールの出力形式を選択する場合
**WHEN** LLMがツール定義を参照する
**THEN** description内に以下の形式でトークンコスト比較表が含まれる：

```
💡 TOKEN EFFICIENCY COMPARISON:
  total_only:          ~10 tokens      (最も効率的)
  count_only_matches:  ~50-200 tokens  (ファイル数依存)
  summary_only:        ~500-2000 tokens
  group_by_file:       ~2000-10000 tokens
  Normal (full):       ~10000-50000 tokens (マッチ数依存)
```

**AND** 各形式の適用シナリオが併記される

#### Scenario: 段階的使用フローの明示

**GIVEN** search_contentツールで段階的に情報を取得する場合
**WHEN** LLMがツール定義を参照する
**THEN** description内に以下の推奨ワークフローが含まれる：

```
🎯 RECOMMENDED WORKFLOW:
  Step 1: Use total_only=true to check if matches exist (0件なら終了)
  Step 2: Use count_only_matches=true for file distribution (少数ファイルならStep 3)
  Step 3: Use summary_only=true for overview (詳細が必要ならStep 4)
  Step 4: Use group_by_file=true for organized results (全詳細が必要ならStep 5)
  Step 5: Use normal mode for complete details
```

**AND** 各ステップでの判断基準が明示される

### Requirement: 出力形式パラメータ説明の強化

search_contentツールの各出力形式パラメータは、効率性順位、推奨シナリオ、排他性警告を含む詳細な説明を持たなければならない（MUST）。

#### Scenario: total_onlyパラメータの完全な説明

**GIVEN** total_onlyパラメータを選択する場合
**WHEN** LLMがパラメータのdescriptionを読む
**THEN** 以下の情報が含まれる：
- 「Return only the total match count as a number」（基本説明）
- 「Most token-efficient option (~10 tokens)」（効率性順位）
- 「Best for: checking if matches exist, quick filtering, large-scale searches」（推奨シナリオ）
- 「⚠️ EXCLUSIVE: Cannot be used with count_only_matches, summary_only, group_by_file, or optimize_paths」（排他性警告）
- 「Takes priority over all other output formats」（優先順位）

#### Scenario: count_only_matchesパラメータの完全な説明

**GIVEN** count_only_matchesパラメータを選択する場合
**WHEN** LLMがパラメータのdescriptionを読む
**THEN** 以下の情報が含まれる：
- 「Return only match counts per file instead of full match details」（基本説明）
- 「Token-efficient (~50-200 tokens depending on file count)」（効率性順位）
- 「Best for: understanding distribution across files, identifying hotspots」（推奨シナリオ）
- 「⚠️ EXCLUSIVE: Cannot be used with total_only, summary_only, group_by_file, or optimize_paths」（排他性警告）

#### Scenario: summary_onlyパラメータの完全な説明

**GIVEN** summary_onlyパラメータを選択する場合
**WHEN** LLMがパラメータのdescriptionを読む
**THEN** 以下の情報が含まれる：
- 「Return a condensed summary of results to reduce context size」（基本説明）
- 「Moderate efficiency (~500-2000 tokens)」（効率性順位）
- 「Best for: initial investigation, understanding scope before diving deep」（推奨シナリオ）
- 「Shows top files and sample matches」（動作説明）
- 「⚠️ EXCLUSIVE: Cannot be used with total_only, count_only_matches, group_by_file, or optimize_paths」（排他性警告）

#### Scenario: group_by_fileパラメータの完全な説明

**GIVEN** group_by_fileパラメータを選択する場合
**WHEN** LLMがパラメータのdescriptionを読む
**THEN** 以下の情報が含まれる：
- 「Group results by file to eliminate file path duplication」（基本説明）
- 「More efficient than normal (~2000-10000 tokens)」（効率性順位）
- 「Best for: reviewing matches in context, reducing path duplication」（推奨シナリオ）
- 「Significantly reduces tokens when multiple matches exist in same files」（効果説明）
- 「⚠️ EXCLUSIVE: Cannot be used with total_only, count_only_matches, summary_only, or optimize_paths」（排他性警告）

#### Scenario: optimize_pathsパラメータの完全な説明

**GIVEN** optimize_pathsパラメータを選択する場合
**WHEN** LLMがパラメータのdescriptionを読む
**THEN** 以下の情報が含まれる：
- 「Optimize file paths in results by removing common prefixes」（基本説明）
- 「Token savings: ~10-30% depending on path depth」（効率性順位）
- 「Best for: deep directory structures, token budget constraints」（推奨シナリオ）
- 「⚠️ EXCLUSIVE: Cannot be used with total_only, count_only_matches, summary_only, or group_by_file」（排他性警告）

### Requirement: 排他性エラーメッセージの多言語化

search_contentツールの出力形式パラメータ競合エラーは、英語と日本語の両方で明確なメッセージを提供しなければならない（MUST）。

#### Scenario: 英語エラーメッセージの詳細化

**GIVEN** 複数の出力形式パラメータが同時指定された場合
**WHEN** 英語ロケールでエラーが発生する
**THEN** 以下の形式のエラーメッセージが返される：

```
Output format parameters are mutually exclusive. 
Multiple formats specified: total_only, count_only_matches.
Please specify only one of: total_only, count_only_matches, summary_only, group_by_file, optimize_paths.

Examples of correct usage:
  - For count only: {"total_only": true}
  - For per-file counts: {"count_only_matches": true}
  - For summary: {"summary_only": true}
```

#### Scenario: 日本語エラーメッセージの詳細化

**GIVEN** 複数の出力形式パラメータが同時指定された場合
**WHEN** 日本語ロケールまたはデフォルトでエラーが発生する
**THEN** 以下の形式のエラーメッセージが返される：

```
出力形式パラメータは排他的です。複数指定できません: total_only, count_only_matches.
次のうち1つのみ指定してください: total_only, count_only_matches, summary_only, group_by_file, optimize_paths.

正しい使用例:
  - 件数のみ取得: {"total_only": true}
  - ファイル別件数: {"count_only_matches": true}
  - サマリー取得: {"summary_only": true}
```

### Requirement: ドキュメントとツール定義はMUST同期

search_contentツールの説明改善は、関連するドキュメント（Rooルール、READMEなど）にも反映され、一貫性が維持されなければならない（MUST）。

#### Scenario: Rooルールへのベストプラクティス追加

**GIVEN** search_contentツールのベストプラクティスが定義された場合
**WHEN** Rooルールファイルを更新する
**THEN** `.roo/rules/`に以下の内容が追加される：
- トークン効率的な検索戦略
- 段階的情報取得のフロー
- 出力形式パラメータの排他性ルール

#### Scenario: README文書の更新

**GIVEN** search_contentツールの使用方法が改善された場合
**WHEN** プロジェクトREADMEを更新する
**THEN** 以下のセクションが追加または更新される：
- 「Token-Efficient Search Strategies」
- 「Output Format Selection Guide」
- 「Common Pitfalls and Solutions」

### Requirement: 実装の後方互換性

search_contentツールの説明改善は、既存のAPI、パラメータ、動作を一切変更せず、完全な後方互換性を維持しなければならない（MUST）。

#### Scenario: 既存パラメータの動作保持

**GIVEN** 説明改善前のsearch_contentツール使用コードが存在する場合
**WHEN** 説明改善後のツールで同じパラメータを使用する
**THEN** 同一の結果が返される
**AND** エラーが発生しない
**AND** レスポンス形式が変更されない

#### Scenario: 新規ユーザーへの明確なガイダンス

**GIVEN** search_contentツールを初めて使用するLLMの場合
**WHEN** ツール定義を読んで最適なパラメータを選択する
**THEN** 明確なガイダンスに基づいて適切な出力形式を選択できる
**AND** 不要なトークン消費を回避できる
**AND** エラーを起こさずに実行できる