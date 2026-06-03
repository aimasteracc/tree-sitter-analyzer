# 包括的フォーマットテスト戦略 - クイックスタートガイド

## 🚀 即座に始める

### 1. **全テストの実行**
```bash
# フォーマットテストディレクトリに移動
cd tests/integration/formatters

# 全テストを実行
python -m pytest -v
```

### 2. **特定のテストカテゴリを実行**
```bash
# ゴールデンマスターテストのみ
python -m pytest test_comprehensive_format_validation.py::TestComprehensiveFormatValidation::test_golden_master_functionality -v

# スキーマ検証テストのみ
python -m pytest test_comprehensive_format_validation.py::TestComprehensiveFormatValidation::test_schema_validation -v

# 実際の統合テストのみ
python -m pytest test_real_integration.py -v
```

### 3. **回帰レポートの生成**
```bash
# テスト失敗時の詳細レポート生成
python generate_regression_report.py
```

## 📋 テストフレームワークの構成

```
tests/integration/formatters/
├── comprehensive_test_suite.py      # メインテストスイート
├── golden_master.py                 # ゴールデンマスターテスト
├── schema_validation.py             # スキーマ検証
├── format_assertions.py             # フォーマット固有アサーション
├── enhanced_assertions.py           # 拡張アサーション
├── test_data_manager.py            # テストデータ管理
├── test_comprehensive_format_validation.py  # 包括的検証テスト
├── test_framework_validation.py     # フレームワーク検証テスト
├── test_real_integration.py         # 実際の統合テスト
├── generate_regression_report.py    # 回帰レポート生成
└── README.md                        # このファイル
```

## 🎯 自動デグレ検知の仕組み

### **CI/CDでの自動実行**
- **プッシュ時**: 全フォーマットテストが自動実行
- **プルリクエスト時**: 変更による影響を事前検証
- **リリース時**: 前バージョンとの互換性チェック

### **検知される問題例**
1. **Markdownテーブル形式の変更**
2. **CSV出力フォーマットの破損**
3. **JSON構造の不整合**
4. **パフォーマンス劣化**
5. **メモリリーク**

## 🔧 実際の使用例

### **例1: 新機能開発時のテスト**
```python
# 新しいフォーマッターをテスト
from comprehensive_test_suite import ComprehensiveFormatTestSuite

suite = ComprehensiveFormatTestSuite()
result = suite.validate_format_output(
    analyzer_function=your_new_formatter,
    test_cases=["simple_class", "complex_inheritance"],
    format_types=["full", "compact", "csv"]
)
```

### **例2: バグ修正後の検証**
```python
# 修正がフォーマットに影響しないことを確認
from golden_master import GoldenMasterTester

tester = GoldenMasterTester("full")
tester.assert_matches_golden_master(
    actual_output=fixed_output,
    test_name="bug_fix_validation"
)
```

### **例3: リリース前の完全検証**
```python
# 全フォーマットの包括的検証
from comprehensive_test_suite import run_full_validation_suite

results = run_full_validation_suite(
    test_data_dir=Path("test_data"),
    formats=["full", "compact", "csv"],
    include_performance=True
)
```

## 📊 テスト結果の解釈

### **成功例**
```
======================== test session starts ========================
collected 25 items

test_comprehensive_format_validation.py::TestComprehensiveFormatValidation::test_golden_master_functionality PASSED
test_comprehensive_format_validation.py::TestComprehensiveFormatValidation::test_schema_validation PASSED
test_comprehensive_format_validation.py::TestComprehensiveFormatValidation::test_format_assertions PASSED
...
======================== 25 passed in 2.34s ========================
```

### **失敗例と対応**
```
FAILED test_comprehensive_format_validation.py::TestComprehensiveFormatValidation::test_golden_master_functionality

# 対応手順:
1. 詳細確認: pytest -v --tb=long
2. 差分確認: 回帰レポートを確認
3. 意図的変更の場合: ゴールデンマスター更新
4. バグの場合: 修正後再テスト
```

## 🛠️ トラブルシューティング

### **よくある問題**

#### **問題1: ImportError**
```bash
# 解決方法
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
# または
pip install -e .
```

#### **問題2: ゴールデンマスター不一致**
```bash
# 差分確認
python -c "
from tests.integration.formatters.golden_master import GoldenMasterTester
tester = GoldenMasterTester('full')
content = tester.get_golden_master_content('test_name')
print(content)
"

# 更新（意図的変更の場合のみ）
python tests/integration/formatters/update_baselines.py --test-name test_name
```

#### **問題3: スキーマ検証失敗**
```bash
# 詳細エラー確認
python -c "
from tests.integration.formatters.schema_validation import MarkdownTableValidator
validator = MarkdownTableValidator()
result = validator.validate(your_content)
print(f'Valid: {result.is_valid}')
print(f'Errors: {result.errors}')
print(f'Warnings: {result.warnings}')
"
```

## 📈 継続的改善

### **メトリクス監視**
- テスト実行時間
- 検知された問題数
- 修正にかかった時間
- 再発率

### **定期的なレビュー**
- 月次: テスト戦略の効果確認
- 四半期: 新しい問題パターンの分析
- 年次: フレームワーク全体の見直し

## 🎉 成功指標

### **品質指標**
- ✅ フォーマット回帰ゼロ
- ✅ テストカバレッジ 95%以上
- ✅ 自動検知率 99%以上
- ✅ 修正時間 < 1時間

### **効率指標**
- ✅ テスト実行時間 < 5分
- ✅ 手動テスト工数 80%削減
- ✅ 問題発見時間 < 10分
- ✅ 開発者満足度向上

## 📚 詳細ドキュメント

詳細な情報については以下を参照してください：
- [包括的活用ガイド](../../../docs/format-testing-guide.md)
- [フォーマット仕様書](../../../docs/format_specifications.md)
- [CI/CD設定](../../.github/workflows/format-regression-testing.yml)

---

**このフレームワークにより、tree-sitter-analyzerプロジェクトのフォーマット品質が自動的に保証され、バージョンアップ時のデグレが即座に検知されます。**
