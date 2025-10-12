# ROO規則 - Tree-Sitter-Analyzer MCP最適化ガイド

## 🎯 核心原則

### 1. 言語サポート
**対応拡張子**: `.java`, `.js`, `.mjs`, `.jsx`, `.ts`, `.tsx`, `.py`, `.md`
**制限**: 上記以外は構造解析機能が制限されます

### 2. 基本規則
- **禁止**: 標準`read_file`での直接コードファイル読取
- **必須**: tree-sitter-analyzer MCPツール使用
- **推奨**: `check_code_scale`による事前評価

### 3. 効率化ワークフロー
```
search_content → check_code_scale → 推奨戦略に従う
```

## 📋 実践ガイド

### 小規模分析
```markdown
search_content → read_file
```

### 大規模分析  
```markdown
search_content → check_code_scale → analyze_code_structure
suppress_output=true + output_file
```

### 安全検索
```markdown
# Token爆発防止
search_content (total_only=true) → 数量確認 → 詳細検索
```

## ⚡ 最適化テクニック

### Token節約
- 大量結果: `suppress_output=true + output_file`
- 検索: `total_only → summary_only → 詳細`の段階的アプローチ
- 日本語検索: 汎用語（「項目名」「データ」「処理」）回避

### システム対応
- **Windows**: Unixコマンド（`grep`, `find`等）禁止
- **Python実行**: 直接`python -c`禁止、テストファイル作成推奨

## 🚨 重要注意

### Token爆発防止
⚠️ **危険**: 汎用語検索での大量結果
✅ **対策**: 必ず`total_only=true`で事前確認

### 効率化パラメータ
```markdown
# 検索制限
max_count: 20
include_globs: ["*.py", "*.java", "*.js", "*.ts", "*.md"]

# 出力制御  
suppress_output: true
output_file: "analysis_result.json"
```

## 🔧 クイックリファレンス

| 目的 | 手法 | パラメータ |
|------|------|------------|
| ファイル探索 | search_content → read_file | - |
| 大規模分析 | check_code_scale → analyze_code_structure | suppress_output=true |
| 安全検索 | search_content | total_only=true |
| 構造解析 | analyze_code_structure | format_type=full |

