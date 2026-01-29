# テスト不具合修正計画

## テスト実行結果サマリー

- **合計テスト数**: 7,456
- **成功**: 1,629 (21.8%)
- **失敗**: 34
- **エラー**: 1
- **スキップ**: 13
- **警告**: 50

## 失敗の分類

### P0 (Critical) - Import/API エラー (1件)

#### E1: ImportError - CheckCodeScaleTool
**ファイル**: `tests/integration/test_end_to_end.py:19`
**エラー**: `ImportError: cannot import name 'CheckCodeScaleTool' from 'tree_sitter_analyzer.mcp.tools.analyze_scale_tool'`
**影響**: 1エラー
**原因**: クラス名の変更または削除
**修正方針**: import文を正しいクラス名に修正

### P1 (High) - API変更による失敗 (26件)

#### F1: FdCommandBuilder/RgCommandBuilder - コンストラクタ引数エラー (14件)
**エラー**: `TypeError: FdCommandBuilder() takes no arguments` / `TypeError: RgCommandBuilder() takes no arguments`
**影響テスト**:
- `test_fd_builder_basic_search`
- `test_fd_builder_with_extensions`
- `test_fd_builder_with_type_filter`
- `test_fd_builder_with_depth_limit`
- `test_fd_builder_with_exclude_patterns`
- `test_fd_builder_fluent_interface`
- `test_rg_builder_with_json_output`
- `test_rg_builder_case_sensitive`
- `test_rg_builder_with_file_pattern`
- `test_rg_builder_count_only`
- `test_rg_builder_with_context`
- `test_fd_result_parser_with_real_output`
- `test_rg_result_parser_with_real_output`
- `test_rg_result_parser_count_mode`

**原因**: Builder Patternリファクタリングでコンストラクタが引数を取らなくなった
**修正方針**: コンストラクタに引数を受け入れるようにする（後方互換性）

#### F2: UnifiedAnalysisEngine - analyze()メソッド引数エラー (9件)
**エラー**: `TypeError: UnifiedAnalysisEngine.analyze() got an unexpected keyword argument 'file_path'`
**影響テスト**:
- `test_analyze_python_file`
- `test_analyze_java_file`
- `test_analyze_typescript_file`
- `test_auto_language_detection`
- `test_file_loader_integration`
- `test_encoding_detection`
- `test_japanese_encoding_support`
- `test_cache_integration`

**原因**: `analyze()`メソッドのシグネチャ変更
**修正方針**: `analyze()`メソッドに`file_path`パラメータを追加（後方互換性）

#### F3: UnifiedAnalysisEngine - analyze_code_sync/analyze_file_async メソッド不在 (4件)
**エラー**: `AttributeError: 'UnifiedAnalysisEngine' object has no attribute 'analyze_code_sync'` / `'analyze_file_async'`
**影響テスト**:
- `test_unified_engine_analyze_code`
- `test_analyze_code_java_success`
- `test_analyze_code_python_success`
- `test_integrated_workflow_scenario_2`

**原因**: リファクタリングでメソッドが削除または名前変更された
**修正方針**: 後方互換性メソッドを追加

#### F4: FileLoader - コンストラクタ引数エラー (1件)
**エラー**: `TypeError: FileLoader.__init__() got an unexpected keyword argument 'project_root'`
**影響テスト**:
- `test_dependency_injection_with_custom_file_loader`

**原因**: `FileLoader`のコンストラクタシグネチャ変更
**修正方針**: `project_root`パラメータを受け入れるようにする

### P2 (Medium) - ロジックエラー (7件)

#### F5: API結果構造の変更 (3件)
**エラー**: `KeyError: 'elements'` / `KeyError: 'partial_content_result'`
**影響テスト**:
- `test_api_consistency_across_methods`
- `test_workflow_file_discovery_and_analysis`
- `test_workflow_configuration_analysis`

**原因**: APIレスポンス構造の変更
**修正方針**: テストを新しいレスポンス構造に更新

#### F6: FileLoader - BOM処理とファイルサイズ (2件)
**エラー**: 
- `AssertionError: assert 15 == 14` (ファイルサイズ)
- `AssertionError: assert '\ufeffHello, World!\n' == 'Hello, World!\n'` (BOM)

**影響テスト**:
- `test_get_file_size`
- `test_load_utf8_with_bom`

**原因**: BOM処理の実装変更
**修正方針**: BOMを除去する処理を追加

#### F7: エラーハンドリングの変更 (1件)
**エラー**: `AssertionError: Expected AnalysisError for nonexistent file`
**影響テスト**:
- `test_error_handling_invalid_paths`

**原因**: エラーハンドリングロジックの変更
**修正方針**: 新しいエラーハンドリング動作に合わせてテストを更新

#### F8: 複雑度解析の失敗 (1件)
**エラー**: `assert 0 > 0` (total_files_analyzed)
**影響テスト**:
- `test_integrated_workflow_scenario_2`

**原因**: `analyze_file_async`メソッド不在による解析失敗
**修正方針**: F3の修正で解決される見込み

### P3 (Low) - パフォーマンステスト (1件)

#### F9: Hypothesis テスト - 入力生成が遅い
**エラー**: `hypothesis.errors.FailedHealthCheck: Input generation is slow`
**影響テスト**:
- `test_format_idempotency`

**原因**: テストデータ生成戦略の非効率性
**修正方針**: `@settings(suppress_health_check=[HealthCheck.too_slow])`を追加

## 修正優先順位

### Phase 1: P0 - Import/API エラー (1件)
1. ✅ E1: CheckCodeScaleTool import修正

### Phase 2: P1 - API変更 (26件)
1. ⏳ F3: 後方互換性メソッド追加（analyze_code_sync, analyze_file_async）
2. ⏳ F2: analyze()メソッドのfile_path対応
3. ⏳ F1: FdCommandBuilder/RgCommandBuilder コンストラクタ対応
4. ⏳ F4: FileLoader コンストラクタ対応

### Phase 3: P2 - ロジックエラー (7件)
1. ⏳ F6: FileLoader BOM処理
2. ⏳ F5: API結果構造の更新
3. ⏳ F7: エラーハンドリング更新
4. ⏳ F8: 複雑度解析（F3で解決見込み）

### Phase 4: P3 - パフォーマンステスト (1件)
1. ⏳ F9: Hypothesis設定追加

## 修正方針: 後方互換性メソッドの追加

**理由**:
1. 既存のテストを最小限の変更で動作させる
2. 既存のユーザーコードへの影響を最小化
3. 段階的な移行を可能にする
4. 新しいAPIと旧APIの両方をサポート

## 検収基準

- [ ] P0エラーがすべて解決されている
- [ ] P1失敗がすべて解決されている
- [ ] P2失敗がすべて解決されている
- [ ] P3失敗がすべて解決されている
- [ ] テスト成功率が95%以上になっている
- [ ] 新しい失敗が発生していない
- [ ] 後方互換性が維持されている
