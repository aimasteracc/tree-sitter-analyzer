## Why

search_contentツールにおいて、LLM（Language Model）が効率的なツール使用を自律的に判断できない重大な問題が存在している：

1. **優先順位と階層性の欠如**: 各パラメータが同列に説明され、LLMが適切な使用順序を判断できない。例えば、`total_only`が最もトークン効率的であるにもかかわらず、その優位性が説明されていない。

2. **ベストプラクティスが埋め込まれていない**: 段階的使用戦略（total_only→count_only_matches→summary_only→group_by_file）がツール定義に含まれておらず、LLMは試行錯誤でしか最適解を見つけられない。

3. **排他制御の不明確性**: パラメータの排他性が各description内で明示されていないため、LLMが誤って複数の出力形式パラメータを同時指定し、実行時エラーが発生する。

4. **具体的な使用例の欠如**: トークンコストの目安や実際のユースケース例がないため、LLMが状況に応じた最適なパラメータ選択を行えない。

これらの問題により、LLMは非効率なツール使用を行い、ユーザーのトークン消費が増大し、応答速度が低下している。

## What Changes

以下の5つの改善を実施する：

1. **段階的使用戦略をツール説明に埋め込む**
   - 各パラメータのdescriptionに効率性順位、トークンコスト目安、推奨シナリオを追加
   - 例: `total_only`の説明に「最もトークン効率的（約10トークン）。件数のみ必要な場合に使用」を追加

2. **ツール説明文の冒頭に使用戦略を追加**
   - `search_content_tool.py`のdescriptionに以下のセクションを追加：
     - `⚠️ IMPORTANT: Token Efficiency Guide` - トークン効率性の重要性
     - `🎯 RECOMMENDED WORKFLOW` - 段階的使用戦略のフローチャート
     - `💡 TOKEN EFFICIENCY COMPARISON` - 各形式のトークンコスト比較表

3. **排他性の明示的な警告**
   - `output_format_validator.py`のエラーメッセージを多言語化（英語・日本語）
   - 各出力形式パラメータのdescriptionに排他性警告を追加
   - 例: `"⚠️ EXCLUSIVE: Cannot be used with other output format parameters (count_only_matches, summary_only, group_by_file, optimize_paths)"`

4. **OpenSpec仕様への新規要件追加**
   - 新規capability「llm-guidance」を作成
   - LLM自律的最適化ガイダンスの要件を定義
   - ツール説明の構造化、トークン効率性情報、ベストプラクティス明示の要件

5. **システムプロンプトの同期メカニズム設計**
   - Rooルールとツール定義の一貫性を確保する仕組み
   - ツール定義の変更時にRooルールへの同期を促す検証機構

## Impact

### 影響を受ける仕様
- **新規**: `llm-guidance` - LLMガイダンス埋め込みの要件を定義
- **修正**: `mcp-tools` - search_contentツールの説明改善要件を追加

### 影響を受けるコード
- `tree_sitter_analyzer/mcp/tools/search_content_tool.py`:
  - `get_tool_definition()`メソッドのdescriptionフィールド拡張（約150行追加）
  - 各パラメータのdescription強化
- `tree_sitter_analyzer/mcp/tools/output_format_validator.py`:
  - エラーメッセージの多言語化
  - バリデーション説明の追加

### 破壊的変更
**なし** - 完全な後方互換性を維持。既存のAPI、パラメータ、動作は一切変更しない。

### 期待される効果
- **トークン消費削減**: LLMが最適な出力形式を選択することで、平均30-50%のトークン削減
- **応答速度向上**: 不要な詳細情報の取得を回避することで、平均20-40%の高速化
- **エラー削減**: パラメータ競合エラーが80%以上削減
- **ユーザビリティ向上**: LLMがより適切なツール使用判断を行い、ユーザー体験が改善