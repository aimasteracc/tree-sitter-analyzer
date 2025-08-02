#!/usr/bin/env python3
"""
Tree-sitter Analyzer パッケージのメインエントリーポイント

このファイルにより、`python -m tree_sitter_analyzer` でパッケージを実行できます。
"""

from .cli_main import main

if __name__ == "__main__":
    main()
