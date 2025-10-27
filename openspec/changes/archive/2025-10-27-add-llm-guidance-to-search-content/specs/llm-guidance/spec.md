## ADDED Requirements

### Requirement: ツール説明へのトークン効率性ガイダンス埋め込み

MCPツールは、LLMが自律的にトークン効率的な使用判断を行えるよう、トークン効率性に関するガイダンスをツール定義のdescriptionフィールドに明示的に埋め込まなければならない（MUST）。

#### Scenario: トークン効率性比較表の提供

**GIVEN** search_contentツールのようなトークン消費に大きな差異がある複数の出力形式を持つツールの場合
**WHEN** LLMがツール定義を参照する
**THEN** description内に各出力形式のトークンコスト比較表が含まれる
**AND** 最も効率的な形式が明示される
**AND** 具体的なトークン数の目安が提示される

#### Scenario: 効率性順位の明示

**GIVEN** 複数のパラメータが存在し、効率性に優先順位がある場合
**WHEN** LLMがパラメータを選択する
**THEN** 各パラメータのdescriptionに効率性順位（例：「最も効率的」「中程度」「最も詳細」）が含まれる
**AND** 効率性順位の判断基準（トークン数、処理速度など）が説明される

### Requirement: 段階的使用戦略の明示

複数の出力形式を持つツールは、LLMが段階的に情報を取得できるよう、推奨される使用フローをツール定義に含めなければならない（MUST）。

#### Scenario: 推奨ワークフローの提供

**GIVEN** search_contentツールのような段階的な情報取得が可能なツールの場合
**WHEN** LLMがツール定義を参照する
**THEN** description内に推奨ワークフローのフローチャートまたはステップが含まれる
**AND** 各ステップでの判断基準が明示される
**AND** 次のステップへの移行条件が説明される

**Example workflow:**
```
Step 1: total_only (件数確認) → 0件なら終了
Step 2: count_only_matches (ファイル別件数) → 少数ファイルならStep 3
Step 3: summary_only (サマリー確認) → 詳細が必要ならStep 4
Step 4: group_by_file (グループ化) → 全詳細が必要ならStep 5
Step 5: Normal (全詳細取得)
```

#### Scenario: 状況別推奨パラメータの提示

**GIVEN** 異なるユースケースで最適なパラメータが異なる場合
**WHEN** LLMがユースケースに応じたパラメータを選択する
**THEN** 各パラメータのdescriptionに推奨シナリオが含まれる
**AND** 「このパラメータを使用すべき状況」が具体例とともに示される

**Example:**
- `total_only`: 「マッチ件数のみ必要で、内容確認が不要な場合（例：検索可能性の確認、大量検索のフィルタリング）」
- `summary_only`: 「概要を把握してから詳細を取得するか判断したい場合（例：初回調査、スコープ確認）」

### Requirement: パラメータ排他性の明示的警告

相互に排他的なパラメータを持つツールは、各パラメータのdescriptionに排他性の警告を含めなければならない（MUST）。

#### Scenario: 排他性警告の表示

**GIVEN** 出力形式パラメータのような排他的パラメータ群が存在する場合
**WHEN** LLMがパラメータのdescriptionを読む
**THEN** 各排他的パラメータのdescriptionに「⚠️ EXCLUSIVE」マーカーが含まれる
**AND** 同時使用できない他のパラメータ名がリストされる
**AND** 同時指定時のエラーが明示される

**Example:**
```
"total_only": {
  "description": "Return only the total match count as a number. 
  Most token-efficient option (~10 tokens). 
  ⚠️ EXCLUSIVE: Cannot be used with count_only_matches, summary_only, 
  group_by_file, or optimize_paths."
}
```

#### Scenario: 排他性違反エラーの詳細化

**GIVEN** 排他的パラメータが同時指定された場合
**WHEN** バリデーションエラーが発生する
**THEN** エラーメッセージに競合するパラメータ名が含まれる
**AND** 正しい使用方法の例が提示される
**AND** 多言語対応（少なくとも英語と日本語）でメッセージが提供される

### Requirement: 重要情報の視覚的強調

ツール定義内で重要な情報は、LLMが容易に識別できるよう視覚的マーカーで強調しなければならない（MUST）。

#### Scenario: マーカーを用いた情報分類

**GIVEN** ツールのdescriptionフィールドに複数の重要情報が含まれる場合
**WHEN** LLMがdescriptionを解析する
**THEN** 以下のマーカーが使用される：
- `⚠️ IMPORTANT` - 重要な注意事項や制約
- `🎯 RECOMMENDED` - 推奨される使用方法
- `💡 TIP` - 効率化のヒント
- `⚠️ EXCLUSIVE` - 排他的パラメータの警告
- `📊 COMPARISON` - 比較表やメトリクス

**AND** 各マーカーの後に明確な見出しまたは説明が続く

#### Scenario: 構造化されたdescription

**GIVEN** ツールのdescriptionが長文になる場合
**WHEN** LLMがdescriptionを読む
**THEN** descriptionがセクションに分割される
**AND** 各セクションに明確な見出しがある
**AND** 重要度順に情報が配置される（最重要情報を先頭に）

**Example structure:**
```
⚠️ IMPORTANT: Token Efficiency Guide
[重要な効率性情報]

🎯 RECOMMENDED WORKFLOW:
[段階的使用フロー]

💡 TOKEN EFFICIENCY COMPARISON:
[トークンコスト比較表]

📝 General Description:
[一般的なツール説明]
```

### Requirement: 具体的なメトリクスをMUST提供

ツール定義は、LLMが定量的な判断を行えるよう、具体的なメトリクス（トークン数、処理時間など）を含めなければならない（MUST）。

#### Scenario: トークンコストの具体的数値提示

**GIVEN** 異なる出力形式でトークン消費量が大きく異なる場合
**WHEN** LLMが出力形式を選択する
**THEN** 各形式のdescriptionに具体的なトークン数の目安が含まれる
**AND** 数値は実測値または推定値として明示される

**Example:**
- `total_only`: ~10 tokens
- `count_only_matches`: ~50-200 tokens (ファイル数依存)
- `summary_only`: ~500-2000 tokens
- `group_by_file`: ~2000-10000 tokens
- Normal: ~10000-50000 tokens (マッチ数依存)

#### Scenario: パフォーマンス特性の明示

**GIVEN** パラメータによって処理時間が異なる場合
**WHEN** LLMがパフォーマンスを考慮してパラメータを選択する
**THEN** 各パラメータのdescriptionに処理時間の目安が含まれる
**AND** 相対的な速度比較（例：「最速」「標準」「低速」）が示される

### Requirement: エラーメッセージは教育的価値をMUST提供

ツールのエラーメッセージは、LLMが同じエラーを繰り返さないよう、教育的な情報を含めなければならない（MUST）。

#### Scenario: エラー原因の明確な説明

**GIVEN** パラメータ検証エラーが発生する場合
**WHEN** エラーメッセージが生成される
**THEN** エラーメッセージに以下が含まれる：
- 何が問題だったか（例：「複数の出力形式パラメータが指定されました」）
- どのパラメータが競合したか（例：「total_only と count_only_matches」）
- 正しい使用方法（例：「これらのパラメータは排他的です。1つのみ指定してください」）

#### Scenario: 具体的な修正例の提示

**GIVEN** パラメータの使用方法が誤っている場合
**WHEN** エラーメッセージが生成される
**THEN** エラーメッセージに正しい使用例が含まれる
**AND** 修正後のパラメータセットの例が示される

**Example error message:**
```
出力形式パラメータは排他的です。複数指定できません: total_only, count_only_matches.
次のうち1つのみ指定してください: total_only, count_only_matches, summary_only, group_by_file, optimize_paths

正しい使用例:
- 件数のみ取得: {"total_only": true}
- ファイル別件数: {"count_only_matches": true}
- サマリー取得: {"summary_only": true}
```

### Requirement: マルチ言語サポートをSHALL提供

グローバルに使用されるツールは、エラーメッセージとガイダンスを複数言語で提供しなければならない（SHALL）。

#### Scenario: 英語と日本語での説明提供

**GIVEN** ツールが英語圏と日本語圏で使用される場合
**WHEN** ツール定義とエラーメッセージが生成される
**THEN** 英語の説明が提供される
**AND** 日本語の説明も提供される
**AND** 言語切り替えが可能、または両言語が併記される

#### Scenario: エラーメッセージの多言語化

**GIVEN** バリデーションエラーが発生する場合
**WHEN** エラーメッセージが生成される
**THEN** エラーメッセージが英語と日本語の両方で提供される
**OR** ユーザーのロケール設定に基づいて適切な言語が選択される