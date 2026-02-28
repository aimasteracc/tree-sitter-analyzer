---
name: tsa-self-improve
description: TDD + Spec駆動でtree-sitter-analyzerを自立的に改善するスキル。カバレッジ分析から機能拡張まで、Spec-First TDDサイクルを実行。
license: MIT
compatibility: Python 3.10+, uv, pytest, tree-sitter-analyzer MCP
metadata:
  author: tree-sitter-analyzer
  version: "2.0"
  approach: "Spec-First TDD"
---

# TSA Self-Improve Skill

tree-sitter-analyzerプロジェクトを自立的に分析・改善するスキル。

## 前提条件

- 作業ディレクトリ: tree-sitter-analyzerプロジェクトルート
- 必要ツール: uv, pytest, fd, ripgrep
- MCP設定: tree-sitter-analyzer MCPサーバー推奨

---

## ワークフロー

```
┌─────────────────────────────────────────────────────────────┐
│                    TDD + Spec駆動サイクル                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. ANALYZE                                                 │
│     カバレッジ分析 → 改善候補特定                            │
│              ▼                                              │
│  2. SPEC                                                    │
│     機能仕様定義 → インターフェース設計 → 受け入れ基準        │
│              ▼                                              │
│  3. RED                                                     │
│     失敗するテスト作成 → テスト実行確認                      │
│              ▼                                              │
│  4. GREEN                                                   │
│     最小実装 → テスト成功確認                                │
│              ▼                                              │
│  5. REFACTOR                                                │
│     コード整理 → 品質チェック                                │
│              ▼                                              │
│  次の改善候補へ                                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: ANALYZE - 現状分析

### 1.1 カバレッジレポート生成

```bash
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=json --cov-report=term-missing -q
```

### 1.2 低カバレッジモジュール特定

カバレッジ < 80% のモジュールをリストアップ:

```bash
uv run python -c "
import json
with open('coverage.json') as f:
    data = json.load(f)
for file, metrics in data['files'].items():
    pct = metrics['summary']['percent_covered']
    if pct < 80:
        print(f'{pct:.1f}% {file}')
" | sort -n
```

### 1.3 品質チェック

```bash
uv run python check_quality.py --new-code-only
uv run python llm_code_checker.py --check-all
```

### 1.4 改善候補リスト生成

```
改善候補:
├── カバレッジ不足
│   ├── P0 (<30%): [ファイルリスト]
│   ├── P1 (30-50%): [ファイルリスト]
│   └── P2 (50-80%): [ファイルリスト]
├── 品質問題
│   ├── リントエラー: N件
│   └── 型エラー: N件
└── 機能拡張候補
    ├── 新言語プラグイン
    └── MCPツール拡張
```

---

## Phase 2: SPEC - 仕様定義

### 2.1 Specファイル作成

**場所:** `openspec/specs/{feature}/spec.md`

```markdown
# {機能名} Specification

## 概要
{機能の簡潔な説明}

## インターフェース

### シグネチャ
```python
def {function_name}(self, param1: Type1, param2: Type2) -> ReturnType
```

### パラメータ
| 名前 | 型 | 必須 | 説明 |
|------|-----|------|------|
| param1 | Type1 | Yes | 説明 |
| param2 | Type2 | No | 説明 |

### 戻り値
- 型: ReturnType
- 説明: 何を返すか

## 振る舞い

### 正常系 (Happy Path)
1. 条件Aの場合 → 結果Xを返す
2. 条件Bの場合 → 結果Yを返す

### 異常系 (Error Cases)
1. 無効な入力 → {Exception}を送出
2. 条件不満 → {Exception}を送出

## 事前条件 (Preconditions)
- param1はNoneでない
- param2が指定される場合、正の整数である

## 事後条件 (Postconditions)
- 戻り値は常に非None
- エラー時は例外を送出

## 受け入れ基準
- [ ] 正常系テストがパスする
- [ ] 異常系テストがパスする
- [ ] カバレッジ >= 80%

## テストケース一覧
| ID | シナリオ | 入力 | 期待結果 |
|----|----------|------|----------|
| T1 | 正常系 | ... | ... |
| T2 | 境界値 | ... | ... |
| T3 | 異常系 | ... | Exception |
```

### 2.2 Specテンプレート (Python関数用)

```markdown
# {module}.{function_name} Specification

## 契約

```python
def {function_name}(param1: Type1, param2: Type2 = None) -> ReturnType:
    """
    {機能の説明}
    
    Args:
        param1: {説明}
        param2: {説明} (optional)
    
    Returns:
        {戻り値の説明}
    
    Raises:
        {Exception1}: {発生条件}
        {Exception2}: {発生条件}
    
    Examples:
        >>> {function_name}({input})
        {expected_output}
    """
```

## Property-Based Tests

| プロパティ | 説明 |
|-----------|------|
| {property1} | 任意の有効な入力に対して... |
| {property2} | ... |

## Table-Driven Tests

| Input | Expected | Type |
|-------|----------|------|
| ...   | ...      | normal |
| ...   | ...      | edge |
| ...   | Exception | error |
```

---

## Phase 3: RED - テスト先行作成

### 3.1 テスト作成ルール

1. **実装前にテストを作成**
2. **テストは失敗することを確認 (RED)**
3. **Specのテストケースを網羅**

### 3.2 テストファイルテンプレート

```python
# tests/unit/{module}/test_{target}.py
"""
Spec: openspec/specs/{module}/spec.md

TDD Cycle:
1. RED: This test should fail initially
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality
"""

import pytest
from tree_sitter_analyzer.{module} import {Target}


class Test{Target}NormalCases:
    """正常系テスト - Spec Section: 正常系"""
    
    def test_{scenario}_returns_expected_result(self):
        """Spec: T1 - {説明}"""
        # Arrange
        target = {Target}()
        
        # Act
        result = target.{method}({input})
        
        # Assert
        assert result == {expected}
    
    def test_{scenario}_with_valid_input(self):
        """Spec: T2 - {説明}"""
        # Arrange
        target = {Target}()
        
        # Act & Assert
        assert target.{method}({input}) is not None


class Test{Target}EdgeCases:
    """境界値テスト - Spec Section: 境界値"""
    
    def test_{scenario}_empty_input(self):
        """Spec: T3 - 空の入力"""
        # Arrange
        target = {Target}()
        
        # Act & Assert
        result = target.{method}("")
        assert result == {expected_for_empty}
    
    def test_{scenario}_maximum_input(self):
        """Spec: T4 - 最大値入力"""
        pass


class Test{Target}ErrorCases:
    """異常系テスト - Spec Section: 異常系"""
    
    def test_{scenario}_invalid_input_raises_exception(self):
        """Spec: T5 - 無効な入力で例外"""
        # Arrange
        target = {Target}()
        
        # Act & Assert
        with pytest.raises({ExpectedException}):
            target.{method}({invalid_input})
    
    def test_{scenario}_null_input_raises_exception(self):
        """Spec: T6 - None入力で例外"""
        target = {Target}()
        with pytest.raises((TypeError, ValueError)):
            target.{method}(None)
```

### 3.3 RED確認

```bash
uv run pytest tests/unit/{module}/test_{target}.py -v
# 期待: FAILED (まだ実装していないため)
```

**確認ポイント:**
- テストが実行されること
- 適切な理由で失敗すること (ImportError, AssertionError等)
- テスト名がSpecと対応していること

---

## Phase 4: GREEN - 最小実装

### 4.1 実装ルール

- **YAGNI (You Aren't Gonna Need It)**: 必要最小限の実装のみ
- **テストを通すことのみ**を目的
- 過剰な抽象化・最適化はREFACTORで

### 4.2 実装テンプレート

```python
# tree_sitter_analyzer/{module}/{target}.py

from typing import Optional


class {Target}:
    """
    {機能の説明}
    
    Spec: openspec/specs/{module}/spec.md
    """
    
    def {method}(self, param1: Type1, param2: Optional[Type2] = None) -> ReturnType:
        """
        {メソッドの説明}
        
        Args:
            param1: {説明}
            param2: {説明}
        
        Returns:
            {戻り値の説明}
        
        Raises:
            {Exception}: {発生条件}
        """
        # 最小実装: テストを通すためのコードのみ
        if param1 is None:
            raise ValueError("param1 must not be None")
        
        # 基本ロジック
        result = self._process(param1, param2)
        return result
    
    def _process(self, param1: Type1, param2: Optional[Type2]) -> ReturnType:
        """内部処理 (REFACTORで分割・整理)"""
        # 実装
        pass
```

### 4.3 GREEN確認

```bash
uv run pytest tests/unit/{module}/test_{target}.py -v
# 期待: PASSED (全テスト成功)
```

---

## Phase 5: REFACTOR - 品質向上

### 5.1 リファクタリングチェックリスト

- [ ] **重複排除**: 同じロジックが複数箇所にないか
- [ ] **命名改善**: 変数・関数名が意図を表しているか
- [ ] **単一責任**: 関数が1つのことだけしているか
- [ ] **型アノテーション**: 全引数・戻り値に型があるか
- [ ] **ドキュメント**: docstringが十分か

### 5.2 品質ゲート

```bash
# 1. 全テストパス
uv run pytest tests/ -v

# 2. 型チェック
uv run mypy tree_sitter_analyzer/

# 3. リント
uv run ruff check tree_sitter_analyzer/

# 4. 品質チェック
uv run python check_quality.py

# 5. AIコードチェック
uv run python llm_code_checker.py --check-all

# 6. カバレッジ確認
uv run pytest tests/ --cov=tree_sitter_analyzer.{module} --cov-report=term-missing
```

### 5.3 変更サマリー

```
## 改善完了レポート

### Spec
- 作成: openspec/specs/{module}/spec.md

### テスト
- 作成: tests/unit/{module}/test_{target}.py
- テスト数: N個

### 実装
- 変更: tree_sitter_analyzer/{module}/{target}.py

### カバレッジ
- Before: XX%
- After: YY%
- Improvement: +ZZ%

### 品質メトリクス
- テスト: PASS
- 型チェック: PASS
- リント: PASS
- 品質チェック: PASS
```

---

## 実行サイクル

```
while 改善候補が存在:
    1. ANALYZE: カバレッジ分析
    2. 次の改善候補を選択
    3. SPEC: 仕様定義 (openspec/specs/{feature}/spec.md)
    4. RED: テスト作成 → 失敗確認
    5. GREEN: 最小実装 → テスト成功
    6. REFACTOR: 品質向上
    7. 品質ゲート通過確認
    8. 繰り返し
```

---

## ディレクトリ構造

```
tree-sitter-analyzer/
├── openspec/
│   └── specs/
│       └── {module}/
│           └── spec.md              # 機能仕様書
├── tests/
│   ├── unit/
│   │   └── {module}/
│   │       └── test_{target}.py     # Spec由来のテスト
│   ├── integration/
│   └── regression/
└── tree_sitter_analyzer/
    └── {module}/
        └── {target}.py              # 実装
```

---

## Token効率化

### 大規模ファイル分析

```python
# MCPツール使用時
check_code_scale(file_path)  # 事前評価

# 大規模の場合
analyze_code_structure(
    file_path,
    suppress_output=True,
    output_file="analysis.json"
)
```

### 検索結果制限

```python
search_content(
    query="pattern",
    total_only=True,      # 件数のみ
    max_count=20          # 上限
)
```

---

## 注意事項

### Windows対応

- Unixコマンド (`grep`, `find`, `cat`) 禁止
- PowerShell/Git Bashコマンド使用
- パス区切りは `/` または `os.path.join`

### セーフガード

- `main` ブランチへの直接コミット禁止
- 破壊的変更はユーザー確認必須
- 秘密情報のコミット禁止
- 未テストのコードをマージ禁止

### TDD原則

1. **RED first**: テストなしで実装しない
2. **Minimal GREEN**: 過剰実装しない
3. **Continuous REFACTOR**: 常に品質向上
