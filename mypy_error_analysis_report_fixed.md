# tree-sitter-analyzer フェーズ4: 残存mypyエラー詳細分析レポート

## 分析概要

- **分析日時**: 2025-10-21T18:34:01.486179
- **総エラー数**: 168個
- **対象ファイル数**: 17個

## エラー優先度別分布

- **UNKNOWN**: 168個


## 最も問題のあるファイル（上位10）

| ファイル名 | エラー数 | 優先度スコア | CRITICAL | HIGH |
|-----------|---------|-------------|----------|------|
| unknown | 75 | 225 | 0 | 0 |
| markdown_plugin.py | 28 | 84 | 0 | 0 |
| python_plugin.py | 11 | 33 | 0 | 0 |
| server.py | 10 | 30 | 0 | 0 |
| javascript_plugin.py | 9 | 27 | 0 | 0 |


## フェーズ別修正計画

### PHASE_5: CRITICAL エラーの修正

- **対象エラー数**: 0個
- **重点エラーコード**: attr-defined, name-defined, no-redef
- **推定作業量**: HIGH
- **リスクレベル**: LOW

### PHASE_6: HIGH 優先度エラーの修正

- **対象エラー数**: 0個
- **重点エラーコード**: override, return-value, assignment, arg-type
- **推定作業量**: HIGH
- **リスクレベル**: MEDIUM

### PHASE_7: MEDIUM 優先度エラーの修正

- **対象エラー数**: 0個
- **重点エラーコード**: no-untyped-def, var-annotated, no-any-return
- **推定作業量**: MEDIUM
- **リスクレベル**: LOW

### PHASE_8: LOW 優先度エラーの修正

- **対象エラー数**: 0個
- **重点エラーコード**: unreachable, unused-ignore
- **推定作業量**: LOW
- **リスクレベル**: VERY_LOW

### PHASE_9: UNKNOWN エラーの調査と修正

- **対象エラー数**: 168個
- **重点エラーコード**: unknown
- **推定作業量**: MEDIUM
- **リスクレベル**: MEDIUM

## 修正推奨事項

1. 最優先修正ファイル: unknown, markdown_plugin.py, python_plugin.py
2. 型注釈の追加が必要: 1箇所


## 詳細エラー分析

### ファイル別エラー詳細

#### unknown (75個のエラー)

**優先度分布**:
- UNKNOWN: 75個

**根本原因分布**:
- other: 75個

#### markdown_plugin.py (28個のエラー)

**優先度分布**:
- UNKNOWN: 28個

**根本原因分布**:
- other: 28個

#### python_plugin.py (11個のエラー)

**優先度分布**:
- UNKNOWN: 11個

**根本原因分布**:
- other: 11個

#### server.py (10個のエラー)

**優先度分布**:
- UNKNOWN: 10個

**根本原因分布**:
- other: 8個
- unreachable_code: 2個

#### javascript_plugin.py (9個のエラー)

**優先度分布**:
- UNKNOWN: 9個

**根本原因分布**:
- other: 9個

#### html_plugin.py (6個のエラー)

**優先度分布**:
- UNKNOWN: 6個

**根本原因分布**:
- other: 6個

#### css_plugin.py (6個のエラー)

**優先度分布**:
- UNKNOWN: 6個

**根本原因分布**:
- type_annotation_missing: 1個
- other: 5個

#### java_plugin.py (6個のエラー)

**優先度分布**:
- UNKNOWN: 6個

**根本原因分布**:
- other: 6個

#### list_files_tool.py (3個のエラー)

**優先度分布**:
- UNKNOWN: 3個

**根本原因分布**:
- other: 3個

#### typescript_plugin.py (2個のエラー)

**優先度分布**:
- UNKNOWN: 2個

**根本原因分布**:
- other: 2個

