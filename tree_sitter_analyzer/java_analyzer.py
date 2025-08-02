#!/usr/bin/env python3
"""
Java Code Analyzer with tree-sitter
"""

from typing import Any

try:
    import tree_sitter
    import tree_sitter_java as tsjava
    from tree_sitter import Language, Parser

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    from .utils import log_error

    log_error(
        "tree-sitter libraries not found. Please install tree-sitter and tree-sitter-java."
    )

from .file_handler import read_file_with_fallback
from .output_manager import output_error, output_info, output_warning
from .utils import log_error, log_info


class CodeAnalyzer:
    """
    Tree-sitterを使用してソースコードを解析するコアクラス。

    Attributes:
        language: Tree-sitter言語オブジェクト
        parser: Tree-sitterパーサー
        source_code_bytes: 解析対象のソースコードのバイト列
        tree: 構築されたAST
    """

    def __init__(self, language: str = "java") -> None:
        """
        指定された言語用のパーサーを初期化する。

        Args:
            language: 解析対象のプログラミング言語。現在はJavaのみサポート。

        Raises:
            SystemExit: Tree-sitterライブラリの初期化に失敗した場合
        """
        if not TREE_SITTER_AVAILABLE:
            output_error("ERROR: Tree-sitter libraries not available.")
            raise RuntimeError("Tree-sitter libraries not available")

        try:
            if language != "java":
                output_warning(
                    "WARNING: Currently only Java is supported. Using Java parser."
                )

            self.language = Language(tsjava.language())
            self.parser = Parser(self.language)
            self.source_code_bytes: bytes = b""
            self.tree: tree_sitter.Tree | None = None

        except Exception as e:
            output_error(
                f"ERROR: '{language}' 言語の初期化に失敗しました。ライブラリが正しくインストールされているか確認してください。"
            )
            output_error(f"詳細: {e}")
            raise RuntimeError(
                f"Failed to initialize language '{language}': {e}"
            ) from e

    def parse_file(self, file_path: str) -> bool:
        """
        指定されたファイルを解析し、AST（抽象構文木）を構築する。

        Args:
            file_path: 解析するソースファイルのパス

        Returns:
            解析に成功した場合はTrue、失敗した場合はFalse

        Raises:
            None: エラーは内部でハンドリングし、戻り値で示す
        """
        try:
            source_bytes = read_file_with_fallback(file_path)
            if source_bytes is None:
                output_error(
                    f"ERROR: ファイル '{file_path}' の読み込みに失敗しました。"
                )
                return False

            self.source_code_bytes = source_bytes
            self.tree = self.parser.parse(self.source_code_bytes)

            # Tree parsing should always succeed with valid input
            log_info(f"INFO: '{file_path}' の解析が完了し、ASTを構築しました。")
            return True

        except Exception as e:
            output_error(f"ERROR: ファイル解析中にエラーが発生しました: {e}")
            return False

    def execute_query(self, query_string: str) -> list[dict[str, Any]]:
        """
        ASTに対して指定されたクエリを実行し、マッチしたノードの情報を抽出する。

        Args:
            query_string: 実行するTree-sitterクエリ

        Returns:
            マッチした各ノードの情報（内容、位置、キャプチャ名）のリスト

        Raises:
            None: エラーは内部でハンドリングし、空リストを返す
        """
        if not self.tree:
            output_error(
                "ERROR: ASTが構築されていません。先にparse_fileを実行してください。"
            )
            return []

        try:
            query = self.language.query(query_string)
        except Exception as e:
            output_error(
                f"ERROR: クエリのコンパイルに失敗しました。\nクエリ: {query_string}\nエラー: {e}"
            )
            return []

        try:
            captures = query.captures(self.tree.root_node)
        except Exception as e:
            output_error(f"ERROR: クエリの実行に失敗しました: {e}")
            return []

        results = []

        # Tree-sitter 0.24以降の辞書形式に対応
        try:
            # 辞書形式: {capture_name: [nodes...]}
            for capture_name, nodes in captures.items():
                if isinstance(nodes, list):
                    for node in nodes:
                        try:
                            start_line = node.start_point[0] + 1
                            end_line = node.end_point[0] + 1
                            node_text = self.source_code_bytes[
                                node.start_byte : node.end_byte
                            ].decode("utf-8", errors="ignore")

                            results.append(
                                {
                                    "capture_name": capture_name,
                                    "content": node_text,
                                    "start_line": start_line,
                                    "end_line": end_line,
                                    "node_type": node.type,
                                }
                            )
                        except Exception as e:
                            output_warning(
                                f"WARNING: ノード処理中にエラーが発生しました: {e}"
                            )
                            continue

        except Exception as e:
            output_error(f"ERROR: capture処理中に予期しないエラーが発生しました: {e}")
            return []

        return results


def main() -> None:
    """
    モジュールが直接実行された場合のエントリーポイント。
    通常はcli.pyを使用することを推奨。
    """
    output_warning("注意: 直接的なモジュール実行は非推奨です。")
    output_warning("代わりに以下を使用してください:")
    output_info("  uv run java-analyzer <file> --query-key <key>")
    output_info("  または")
    output_info("  python -m tree_sitter_analyzer.cli <file> --query-key <key>")


if __name__ == "__main__":
    main()
