# 架構問題分析と根本的修正計画

## 🚨 発見された根本的問題

### 1. 言語間結合問題
**場所**: `tree_sitter_analyzer/formatters/formatter_factory.py` Line 44-45
```python
if formatter_class is None:
    # Use Java formatter as default  ← 問題の根源
    formatter_class = JavaTableFormatter
```

**問題**: 未知の言語に対してJavaFormatterをデフォルト使用することで、言語固有の処理が混在

### 2. シグネチャ生成問題
**場所**: `tree_sitter_analyzer/formatters/java_formatter.py` Line 233-243
```python
def _create_compact_signature(self, method: dict[str, Any]) -> str:
    params = method.get("parameters", [])
    param_types = [
        self._shorten_type(p.get("type", "O") if isinstance(p, dict) else str(p))
        for p in params
    ]
    params_str = ",".join(param_types)
    return_type = self._shorten_type(method.get("return_type", "void"))
    return f"({params_str}):{return_type}"
```

**問題**: パラメータ処理が不適切で、`():void`のような不正確なシグネチャが生成される

## 📋 修正計画

### Phase 1: 架構の根本的修正

#### 1.1 言語間結合の解除
- [ ] `formatter_factory.py`のデフォルトフォールバック機能を修正
- [ ] 言語固有のフォーマッターが存在しない場合の適切な処理を実装
- [ ] 汎用フォーマッターの作成

#### 1.2 シグネチャパーサーの改善
- [ ] JavaFormatterの`_create_compact_signature`メソッドを修正
- [ ] パラメータ処理ロジックの改善
- [ ] 戻り値型処理の改善

### Phase 2: 包括的テストの実装

#### 2.1 期待結果の予測
**Sample.javaの期待結果**:
```
staticParentMethod: ():void [static]
ParentClass(): ():ParentClass [constructor]
abstractMethod: ():void [override]
parentMethod: ():void
```

**comprehensive_html.htmlの期待結果**:
```
form要素: 正しいHTMLタグ認識
input要素: type属性の正確な抽出
semantic要素: article, section, nav等の認識
```

#### 2.2 テストプログラムの作成
- [ ] `test_architecture_fix.py`: 架構修正の検証
- [ ] `test_signature_accuracy.py`: シグネチャ精度の検証
- [ ] `test_language_isolation.py`: 言語間分離の検証

### Phase 3: バグ修正と検証

#### 3.1 修正の実装
- [ ] FormatterFactoryの修正
- [ ] JavaFormatterの修正
- [ ] HTMLFormatterの独立性確保

#### 3.2 回帰テストの実行
- [ ] 既存機能への影響確認
- [ ] 新機能の動作確認
- [ ] エンコーディング対応の確認

## 🎯 成功基準

### A. 架構品質の改善
- [ ] 言語間結合の完全解除
- [ ] 各言語フォーマッターの独立性確保
- [ ] 拡張可能な設計への移行

### B. 機能精度の向上
- [ ] Javaメソッドシグネチャの正確な表示
- [ ] HTMLクエリの完全動作
- [ ] 全言語での一貫した出力品質

### C. 保守性の向上
- [ ] 新言語追加の容易性
- [ ] エラーハンドリングの改善
- [ ] テストカバレッジの向上

## 🔄 実装手順

1. **分析完了** ✅
2. **修正計画策定** ✅ 
3. **Codeモードへ切り替え** ← 次のステップ
4. **架構修正の実装**
5. **テストプログラムの作成**
6. **包括的テストの実行**
7. **最終検証と評価**

## 📊 技術的詳細

### 修正対象ファイル
1. `tree_sitter_analyzer/formatters/formatter_factory.py`
2. `tree_sitter_analyzer/formatters/java_formatter.py`
3. `tree_sitter_analyzer/formatters/base_formatter.py`

### 新規作成ファイル
1. `test_architecture_fix.py`
2. `test_signature_accuracy.py`
3. `test_language_isolation.py`

### 検証対象サンプル
1. `examples/Sample.java`
2. `examples/comprehensive_html.html`
3. `examples/test_markdown.md`

---

**次のアクション**: Codeモードに切り替えて、上記計画に基づく修正を実装する