# 互換性比較レポート: v{VERSION_A} vs v{VERSION_B}

- **テスト実施日**: {TEST_DATE}
- **担当者**: {TESTER_NAME}
- **テスト環境**: {TEST_ENVIRONMENT}

## 1. 総評

{SUMMARY}

## 2. テスト実行結果

### 2.1. テスト実行統計

| 項目 | 値 |
| :--- | :--- |
| 実行テストケース数 | {TOTAL_TEST_CASES} |
| 成功したテストケース | {SUCCESSFUL_CASES} |
| 失敗したテストケース | {FAILED_CASES} |
| 差分が検出されたケース | {DIFF_DETECTED_CASES} |

### 2.2. バージョン別実行状況

#### v{VERSION_A}
- **サーバー起動**: {VERSION_A_SERVER_STATUS}
- **テスト実行時間**: {VERSION_A_EXECUTION_TIME}
- **生成ファイル数**: {VERSION_A_OUTPUT_FILES}

#### v{VERSION_B}
- **サーバー起動**: {VERSION_B_SERVER_STATUS}
- **テスト実行時間**: {VERSION_B_EXECUTION_TIME}
- **生成ファイル数**: {VERSION_B_OUTPUT_FILES}

{CACHE_REPORT}

## 3. 差分詳細分析

### 3.1. 破壊的変更 (Breaking Changes)

{BREAKING_CHANGES_TABLE}

### 3.2. 非破壊的変更 (Non-Breaking Changes)

{NON_BREAKING_CHANGES_TABLE}

### 3.3. バグ/意図しない変更 (Bugs/Unintended Changes)

{BUGS_TABLE}

### 3.4. 一致した項目 (Identical Output)

{IDENTICAL_ITEMS_LIST}

## 4. 詳細な差分情報

### 4.1. ツール別差分サマリー

| ツール名 | テストケース数 | 一致 | 差分あり | 主な変更内容 |
| :--- | :--- | :--- | :--- | :--- |
{TOOL_SUMMARY_TABLE}

### 4.2. 個別テストケース結果

{INDIVIDUAL_TEST_RESULTS}

## 5. 互換性評価

### 5.1. 後方互換性

- **評価**: {BACKWARD_COMPATIBILITY_RATING}
- **理由**: {BACKWARD_COMPATIBILITY_REASON}

### 5.2. 推奨される対応

#### 即座の対応が必要な項目
{IMMEDIATE_ACTIONS}

#### 長期的な対応が推奨される項目
{LONG_TERM_ACTIONS}

### 5.3. マイグレーション要否

- **マイグレーションガイドが必要**: {MIGRATION_REQUIRED}
- **対象となる変更**: {MIGRATION_TARGETS}

## 6. 技術的詳細

### 6.1. 検出された差分の詳細

{DETAILED_DIFFS}

### 6.2. パフォーマンス比較

{PERFORMANCE_COMPARISON}

## 7. 結論と推奨事項

### 7.1. 結論

{CONCLUSION}

### 7.2. 推奨事項

{RECOMMENDATIONS}

---

## 付録

### A. テスト環境詳細

- **OS**: {OS_INFO}
- **Python バージョン**: {PYTHON_VERSION}
- **uv バージョン**: {UV_VERSION}
- **プロジェクトルート**: {PROJECT_ROOT}

### B. 実行コマンド

```bash
{EXECUTION_COMMANDS}
```

### C. 生成ファイル一覧

#### v{VERSION_A} 出力ファイル
{VERSION_A_FILES_LIST}

#### v{VERSION_B} 出力ファイル
{VERSION_B_FILES_LIST}

### D. エラーログ (該当する場合)

{ERROR_LOGS}
