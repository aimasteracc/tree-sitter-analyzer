## 背景

`tree_sitter_analyzer/file_handler.py`の現在の`read_file_partial`関数は、小さな行範囲を抽出するためにファイル全体をメモリに読み込みます。このアプローチは大きなファイルに対して許容できないほど遅く、メモリを大量に消費し、`extract_code_section` MCPツールの性能に直接的な影響を与えています。

## 目標 / 非目標

- **目標**:
  - メモリ効率的なストリーミングベースの行リーダーを実装する。
  - 大きなファイル読み込みの遅延を劇的に削減する（約30秒から200ms未満へ）。
  - 既存の`read_file_safe`ユーティリティと統合することで、様々なエンコーディングを正しく処理する。
  - 既存の関数シグネチャとの100%後方互換性を維持する。

- **非目標**:
  - `extract_code_section`ツールのパブリックAPIを変更すること。
  - 新しい外部依存関係を導入すること。ソリューションは標準のPythonライブラリを使用します。

## 決定事項

- **決定: `itertools.islice`を使用したストリーミングアプローチを採用**。
  - ファイルを開いて行ごとに反復処理することで、メモリ効率を実現します。
  - `itertools.islice(f, start_idx, end_idx)`を使用して、ファイル全体を読み込むことなく、開始行まで効率的にシークし、終了行の後で停止するイテレータを作成します。
  - これにより、ファイル全体をリストに読み込むことを避け、性能問題の根本原因に直接対処します。

- **検討した代替案**:
  - **手動行カウント**: `for`ループとカウンターを使用した反復処理。`islice`はより慣用的で簡潔であり、C言語で実装されているため高速である可能性があります。
  - **`mmap`**: メモリマップファイルの使用も選択肢でしたが、特にクロスプラットフォーム互換性とリソース管理において複雑さが増します。シンプルな行ごとの反復処理で十分であり、より安全です。

## 実装スケッチ

```python
# tree_sitter_analyzer/file_handler.py内

import itertools
from .encoding_utils import read_file_safe_streaming # ストリーミング版が存在するか作成される想定

def read_file_partial(
    file_path: str,
    start_line: int,
    end_line: int | None = None,
    # ... その他のパラメータ
) -> str | None:
    """
    ストリーミングアプローチを使用して行範囲でファイルの一部を読み込む。
    """
    # パラメータ検証（従来通り）
    if start_line < 1:
        return None
    if end_line is not None and end_line < start_line:
        return None

    start_idx = start_line - 1
    # isliceの場合、end_lineがNoneでなければend_idxは排他的
    end_idx = end_line if end_line is not None else None

    try:
        # 行を生成するストリーミングリーダーを使用
        with read_file_safe_streaming(file_path) as f:
            # イテレータを効率的にスライス
            selected_lines_iterator = itertools.islice(f, start_idx, end_idx)
            selected_lines = list(selected_lines_iterator)

            # カラム操作が必要な場合、小さな`selected_lines`リストに適用可能
            # ... （カラム処理ロジックは類似しているが、はるかに小さなリストで動作）

            return "".join(selected_lines)

    except Exception as e:
        log_error(f"Failed to read partial file {file_path}: {e}")
        return None

# 注意: これには`encoding_utils.py`に正しいエンコーディングでファイルを開き、
# 行を生成する`read_file_safe_streaming`コンテキストマネージャーの作成が必要になる可能性があります。
```

## リスク / トレードオフ

- **リスク**: 現在の`read_file_safe`関数は完全なコンテンツを返します。この設計をサポートするために、適応させるか、新しいストリーミング対応版（`read_file_safe_streaming`）を作成する必要があります。
  - **軽減策**: エンコーディング検出を実行してからファイルハンドルを生成する新しいコンテキスト管理関数`read_file_safe_streaming`を作成し、リソースが適切に管理されることを保証します。これにより変更が分離され、元の関数の有用性が維持されます。

## 移行計画

- これはドロップイン置換です。データ移行は不要です。
- 変更は次回の定期リリースの一部として展開されます。
- **ロールバック**: 予期しない問題が発生した場合、gitを介して`file_handler.py`への変更を元に戻すことで、以前の動作を復元できます。