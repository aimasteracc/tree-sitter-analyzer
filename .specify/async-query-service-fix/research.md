# Research: Async Query Service Fix

**Feature**: Async Query Service Fix  
**Date**: 2025-10-14  
**Status**: Complete  

## Overview

tree-sitter-analyzer v1.8.0における非同期処理不整合の修正に関する技術調査と意思決定の記録です。QueryService.execute_query()メソッドの非同期化アプローチ、代替案の評価、および実装戦略の選択根拠を文書化します。

## Problem Analysis

### Root Cause Investigation

**発見された問題**:
```python
# QueryCommand.execute_async() - Line 31, 39
results = await self.query_service.execute_query(...)  # ❌ TypeError

# QueryService.execute_query() - Line 33
def execute_query(self, ...):  # ❌ Missing 'async' keyword
```

**影響範囲**:
- **CLI Commands**: QueryCommandの全機能が使用不可
- **MCP Tools**: query_toolでの同様のエラー
- **User Impact**: アプリケーションクラッシュによる完全な機能停止

**技術的詳細**:
- Python asyncio: 同期関数を`await`で呼び出すとTypeError
- 既存コード: QueryCommandは正しく非同期実装済み
- 不整合: QueryServiceのみが同期実装

## Research Questions & Decisions

### 1. 非同期化アプローチの選択

**Question**: QueryService.execute_query()をどのように非同期化するか？

**Options Evaluated**:

#### Option A: 完全非同期化 (SELECTED)
```python
async def execute_query(self, ...):
    content, encoding = await self._read_file_async(file_path)
    # ... rest of the method
```

**Pros**:
- 真の非同期処理による性能向上
- 並行処理のサポート
- 将来の拡張性
- アーキテクチャの一貫性

**Cons**:
- わずかな実装複雑性の増加
- 非同期テストの必要性

#### Option B: 同期ラッパー維持
```python
def execute_query(self, ...):
    return asyncio.run(self._execute_query_async(...))

async def _execute_query_async(self, ...):
    # Actual implementation
```

**Pros**:
- 既存呼び出し元の変更不要
- 段階的移行可能

**Cons**:
- 性能オーバーヘッド
- アーキテクチャの不整合継続
- 複雑性の増加

#### Option C: 呼び出し元の修正
```python
# QueryCommandで同期呼び出しに変更
results = self.query_service.execute_query(...)  # Remove await
```

**Pros**:
- QueryServiceの変更不要

**Cons**:
- 非同期アーキテクチャの後退
- 性能劣化
- 将来の拡張性阻害

**Decision**: Option A (完全非同期化)
**Rationale**: 
- Tree-sitter Analyzer憲法のAI-First Architectureに準拠
- 長期的な性能とスケーラビリティの確保
- アーキテクチャの一貫性維持

### 2. ファイル読み込みの非同期化手法

**Question**: `read_file_safe()`をどのように非同期化するか？

**Options Evaluated**:

#### Option A: asyncio.run_in_executor() (SELECTED)
```python
async def _read_file_async(self, file_path: str) -> tuple[str, str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, read_file_safe, file_path)
```

**Pros**:
- 既存の`read_file_safe()`を再利用
- 最小限の変更
- 安定性の確保

**Cons**:
- スレッドプールのオーバーヘッド

#### Option B: aiofiles使用
```python
async def _read_file_async(self, file_path: str) -> tuple[str, str]:
    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
        content = await f.read()
    return content, 'utf-8'
```

**Pros**:
- 真の非同期I/O
- 高性能

**Cons**:
- 新しい依存関係
- エンコーディング検出の再実装必要
- 既存ロジックとの不整合リスク

#### Option C: 同期のまま維持
```python
async def execute_query(self, ...):
    content, encoding = read_file_safe(file_path)  # Blocking call
```

**Pros**:
- 変更最小
- 安定性

**Cons**:
- 非同期の利点なし
- ブロッキングI/O

**Decision**: Option A (asyncio.run_in_executor)
**Rationale**:
- 既存の安定したコードを活用
- 段階的な非同期化
- 依存関係の増加回避

### 3. エラーハンドリング戦略

**Question**: 非同期処理でのエラーハンドリングをどう改善するか？

**Options Evaluated**:

#### Option A: 既存エラーハンドリング維持 (SELECTED)
```python
try:
    content, encoding = await self._read_file_async(file_path)
    # ... existing logic
except Exception as e:
    logger.error(f"Query execution failed: {e}")
    raise
```

**Pros**:
- 既存の安定したエラーハンドリング
- 最小限の変更
- 後方互換性

**Cons**:
- 非同期特有のエラー情報不足

#### Option B: 非同期専用エラーハンドリング
```python
try:
    content, encoding = await self._read_file_async(file_path)
except asyncio.TimeoutError:
    raise AsyncTimeoutError(...)
except Exception as e:
    context = AsyncErrorContext(...)
    logger.error(f"Async query failed: {e}", extra=context)
    raise AsyncQueryError(...) from e
```

**Pros**:
- 詳細な非同期エラー情報
- 専用例外クラス

**Cons**:
- 実装複雑性の増加
- 既存エラーハンドリングとの不整合

**Decision**: Option A (既存維持)
**Rationale**:
- 緊急修正の性質上、最小変更を優先
- Phase 2で詳細なエラーハンドリングを検討

### 4. テスト戦略

**Question**: 非同期処理のテストをどのように実装するか？

**Options Evaluated**:

#### Option A: pytest-asyncio使用 (SELECTED)
```python
@pytest.mark.asyncio
async def test_execute_query_async():
    service = QueryService()
    results = await service.execute_query(...)
    assert results is not None
```

**Pros**:
- 標準的なアプローチ
- 豊富なドキュメント
- 既存テストとの統合容易

**Cons**:
- 新しい依存関係

#### Option B: asyncio.run()使用
```python
def test_execute_query_async():
    service = QueryService()
    results = asyncio.run(service.execute_query(...))
    assert results is not None
```

**Pros**:
- 追加依存関係不要

**Cons**:
- テストの複雑性
- 並行テストの困難

**Decision**: Option A (pytest-asyncio)
**Rationale**:
- 非同期テストのベストプラクティス
- 将来の拡張性

### 5. 性能最適化アプローチ

**Question**: 非同期化による性能への影響をどう最小化するか？

**Research Findings**:

#### 性能測定結果 (予測)
```python
# 同期版 (現在)
- 単一ファイル処理: 100ms
- メモリ使用量: 50MB
- 並行処理: 不可

# 非同期版 (目標)
- 単一ファイル処理: 105ms (5%増加)
- メモリ使用量: 55MB (10%増加)
- 並行処理: 3倍のスループット
```

#### 最適化戦略
1. **ファイルI/O**: run_in_executorによる非ブロッキング化
2. **並行処理**: asyncio.gather()による複数クエリ同時実行
3. **メモリ管理**: 既存のキャッシュ機能維持

**Decision**: 段階的最適化
**Rationale**:
- Phase 1: 基本的な非同期化
- Phase 2: 性能測定と最適化
- Phase 3: 並行処理の活用

## Technology Choices

### Core Technologies

| Technology | Version | Purpose | Justification |
|------------|---------|---------|---------------|
| Python asyncio | 3.10+ | 非同期処理基盤 | 標準ライブラリ、安定性 |
| pytest-asyncio | Latest | 非同期テスト | 業界標準、豊富な機能 |
| mypy | Latest | 型チェック | 非同期コードの型安全性 |

### Rejected Technologies

| Technology | Reason for Rejection |
|------------|---------------------|
| aiofiles | 追加依存関係、既存コードとの不整合 |
| asyncio.Queue | 現在の要件に対してオーバーエンジニアリング |
| concurrent.futures | asyncioで十分、一貫性のため |

## Architecture Decisions

### Decision 1: 最小変更原則

**Context**: 緊急修正の性質上、リスクを最小化する必要がある

**Decision**: QueryService.execute_query()のみを変更し、他のコンポーネントは最小限の修正

**Consequences**:
- ✅ リスク最小化
- ✅ 迅速な修正
- ❌ 包括的な非同期化は後回し

### Decision 2: 後方互換性の維持

**Context**: 既存のAPIユーザーへの影響を最小化

**Decision**: メソッドシグネチャは`async`キーワード追加のみ、その他は変更なし

**Consequences**:
- ✅ 既存コードの動作継続
- ✅ 移行コスト最小
- ❌ 一部の同期呼び出し元は修正必要

### Decision 3: 段階的実装

**Context**: 品質と速度のバランス

**Decision**: 3段階のフェーズに分けて実装

**Consequences**:
- ✅ 各段階での品質確保
- ✅ 早期の問題解決
- ❌ 完全な最適化まで時間要

## Performance Analysis

### Benchmarking Plan

```python
# 性能測定項目
1. 単一ファイル処理時間
2. メモリ使用量
3. 並行処理スループット
4. エラー復旧時間

# 測定環境
- Python 3.10, 3.11, 3.12
- Linux, Windows, macOS
- 小規模ファイル (< 1MB)
- 中規模ファイル (1-10MB)
- 大規模ファイル (10-100MB)
```

### Expected Results

| Metric | Current | Target | Acceptable Range |
|--------|---------|--------|------------------|
| Processing Time | 100ms | 105ms | 100-110ms |
| Memory Usage | 50MB | 55MB | 50-60MB |
| Concurrent Throughput | 1x | 3x | 2-4x |
| Error Recovery | 2s | 1s | < 1.5s |

## Risk Assessment

### Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| 非同期化による予期しない副作用 | Medium | High | 包括的テスト、段階的実装 |
| 性能劣化 | Low | Medium | 性能測定、最適化 |
| 既存機能の回帰 | Low | High | 全テスト実行、回帰テスト |

### Implementation Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| 時間超過 | Low | Medium | 最小変更原則、事前準備 |
| テスト環境問題 | Low | Low | 複数環境での検証 |
| 依存関係競合 | Very Low | Low | 既存依存関係維持 |

## Alternative Approaches Considered

### 1. 同期インターフェース維持

**Approach**: QueryServiceを同期のまま維持し、呼び出し元を修正

**Pros**: QueryServiceの変更不要
**Cons**: 非同期アーキテクチャの後退、性能劣化
**Rejection Reason**: 長期的なアーキテクチャ目標と矛盾

### 2. 完全な非同期リファクタリング

**Approach**: 全コンポーネントを一度に非同期化

**Pros**: 完全な一貫性、最適な性能
**Cons**: 高リスク、長期間の開発
**Rejection Reason**: 緊急修正の性質と矛盾

### 3. デュアルインターフェース

**Approach**: 同期と非同期の両方のメソッドを提供

**Pros**: 完全な後方互換性
**Cons**: コードの複雑性、保守負荷
**Rejection Reason**: オーバーエンジニアリング

## Lessons Learned

### 1. アーキテクチャ一貫性の重要性

**Learning**: 非同期/同期の混在は予期しない問題を引き起こす
**Action**: 今後の開発では一貫した非同期アーキテクチャを維持

### 2. 段階的移行の有効性

**Learning**: 大きな変更は段階的に実装することでリスクを軽減
**Action**: 将来の大規模変更でも段階的アプローチを採用

### 3. テストファーストの価値

**Learning**: 非同期コードでは特にテストが重要
**Action**: 非同期機能の開発では必ずテストファーストで進める

## Future Research Areas

### 1. 高度な非同期最適化

- ストリーミング処理の導入
- 非同期キャッシュの実装
- バックプレッシャー制御

### 2. 観測可能性の向上

- 非同期処理のメトリクス収集
- 分散トレーシングの導入
- リアルタイム監視

### 3. 並行処理の最適化

- ワーカープールの導入
- 負荷分散の実装
- リソース制限の動的調整

## Conclusion

本研究により、QueryService.execute_query()の非同期化が最適なアプローチであることが確認されました。最小変更原則に基づく段階的実装により、リスクを最小化しながら重大な問題を解決できます。

**Key Decisions**:
1. ✅ 完全非同期化アプローチ
2. ✅ asyncio.run_in_executor()によるファイルI/O
3. ✅ 既存エラーハンドリングの維持
4. ✅ pytest-asyncioによるテスト
5. ✅ 段階的実装戦略

**Next Steps**:
1. Phase 1実装の開始
2. 継続的な性能監視
3. Phase 2での最適化検討

---

**Research Completed**: 2025-10-14  
**Confidence Level**: High  
**Implementation Ready**: Yes  
**Risk Level**: Low