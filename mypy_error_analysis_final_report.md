# tree-sitter-analyzer フェーズ4: 残存mypyエラー詳細分析レポート（最終版）

## 分析概要

- **分析日時**: 2025-10-21T18:36:14.147505
- **総エラー数**: 168個
- **対象ファイル数**: 17個

## エラー優先度別分布

- **CRITICAL**: 82個
- **UNKNOWN**: 48個
- **LOW**: 25個
- **MEDIUM**: 9個
- **HIGH**: 4個


## 最も問題のあるファイル（上位10）

| ファイル名 | エラー数 | 優先度スコア | CRITICAL | HIGH | MEDIUM | LOW |
|-----------|---------|-------------|----------|------|--------|-----|
| unknown | 75 | 678 | 65 | 0 | 0 | 1 |
| markdown_plugin.py | 28 | 59 | 0 | 0 | 1 | 12 |
| html_plugin.py | 6 | 53 | 5 | 0 | 0 | 0 |
| css_plugin.py | 6 | 46 | 4 | 0 | 0 | 0 |
| server.py | 10 | 43 | 3 | 0 | 2 | 3 |


## フェーズ別修正計画

### PHASE_5: CRITICAL エラーの修正

- **対象エラー数**: 82個
- **重点エラーコード**: attr-defined, name-defined, no-redef
- **推定作業量**: HIGH
- **リスクレベル**: LOW

### PHASE_6: HIGH 優先度エラーの修正

- **対象エラー数**: 4個
- **重点エラーコード**: override, return-value, assignment, arg-type
- **推定作業量**: HIGH
- **リスクレベル**: MEDIUM

### PHASE_7: MEDIUM 優先度エラーの修正

- **対象エラー数**: 9個
- **重点エラーコード**: no-untyped-def, var-annotated, no-any-return
- **推定作業量**: MEDIUM
- **リスクレベル**: LOW

### PHASE_8: LOW 優先度エラーの修正

- **対象エラー数**: 25個
- **重点エラーコード**: unreachable, unused-ignore
- **推定作業量**: LOW
- **リスクレベル**: VERY_LOW

### PHASE_9: UNKNOWN エラーの調査と修正

- **対象エラー数**: 48個
- **重点エラーコード**: unknown
- **推定作業量**: MEDIUM
- **リスクレベル**: MEDIUM

## 修正推奨事項

1. 最優先修正ファイル: unknown, markdown_plugin.py, html_plugin.py
2. CRITICAL エラー 82個を最優先で修正
3. HIGH 優先度エラー 4個を次に修正
4. 継承関係の修正が必要: css_plugin.py
5. 型注釈の追加が必要: 8箇所


## 詳細エラー分析

### エラーコード別分析

#### CRITICAL 優先度 (82個)

**影響ファイル**: unknown, html_plugin.py, api.py, server.py, list_files_tool.py, table_format_tool.py, css_plugin.py

**根本原因分布**:
- other: 6個
- missing_attributes: 67個
- import_issues: 8個
- inheritance_mismatch: 1個

#### UNKNOWN 優先度 (48個)

**影響ファイル**: unknown, java_plugin.py, html_plugin.py, server.py, list_files_tool.py, table_command.py, search_content_tool.py, typescript_plugin.py, validator.py, javascript_plugin.py, css_plugin.py, python_plugin.py, markdown_plugin.py

**根本原因分布**:
- missing_attributes: 1個
- other: 25個
- type_incompatibility: 21個
- type_annotation_missing: 1個

#### LOW 優先度 (25個)

**影響ファイル**: advanced_command.py, java_plugin.py, unknown, server.py, typescript_plugin.py, javascript_plugin.py, python_plugin.py, markdown_plugin.py

**根本原因分布**:
- unreachable_code: 24個
- other: 1個

#### MEDIUM 優先度 (9個)

**影響ファイル**: query_command.py, java_plugin.py, server.py, table_command.py, javascript_plugin.py, python_plugin.py, markdown_plugin.py

**根本原因分布**:
- type_annotation_missing: 7個
- other: 2個

#### HIGH 優先度 (4個)

**影響ファイル**: javascript_plugin.py

**根本原因分布**:
- other: 4個

### ファイル別エラー詳細

#### unknown (75個のエラー)

**優先度分布**:
- CRITICAL: 65個
- UNKNOWN: 9個
- LOW: 1個

**根本原因分布**:
- missing_attributes: 65個
- other: 10個

#### markdown_plugin.py (28個のエラー)

**優先度分布**:
- UNKNOWN: 15個
- LOW: 12個
- MEDIUM: 1個

**根本原因分布**:
- other: 5個
- type_incompatibility: 10個
- unreachable_code: 12個
- type_annotation_missing: 1個

#### python_plugin.py (11個のエラー)

**優先度分布**:
- LOW: 3個
- UNKNOWN: 6個
- MEDIUM: 2個

**根本原因分布**:
- unreachable_code: 3個
- type_incompatibility: 5個
- other: 1個
- type_annotation_missing: 2個

#### server.py (10個のエラー)

**優先度分布**:
- CRITICAL: 3個
- UNKNOWN: 2個
- LOW: 3個
- MEDIUM: 2個

**根本原因分布**:
- other: 7個
- unreachable_code: 3個

#### javascript_plugin.py (9個のエラー)

**優先度分布**:
- LOW: 1個
- HIGH: 4個
- UNKNOWN: 3個
- MEDIUM: 1個

**根本原因分布**:
- unreachable_code: 1個
- other: 4個
- type_incompatibility: 3個
- type_annotation_missing: 1個

#### html_plugin.py (6個のエラー)

**優先度分布**:
- CRITICAL: 5個
- UNKNOWN: 1個

**根本原因分布**:
- import_issues: 5個
- other: 1個

#### css_plugin.py (6個のエラー)

**優先度分布**:
- UNKNOWN: 2個
- CRITICAL: 4個

**根本原因分布**:
- type_annotation_missing: 1個
- import_issues: 3個
- other: 1個
- inheritance_mismatch: 1個

#### java_plugin.py (6個のエラー)

**優先度分布**:
- LOW: 2個
- UNKNOWN: 3個
- MEDIUM: 1個

**根本原因分布**:
- unreachable_code: 2個
- type_incompatibility: 3個
- type_annotation_missing: 1個

#### list_files_tool.py (3個のエラー)

**優先度分布**:
- CRITICAL: 1個
- UNKNOWN: 2個

**根本原因分布**:
- other: 3個

#### typescript_plugin.py (2個のエラー)

**優先度分布**:
- LOW: 1個
- UNKNOWN: 1個

**根本原因分布**:
- unreachable_code: 1個
- other: 1個

