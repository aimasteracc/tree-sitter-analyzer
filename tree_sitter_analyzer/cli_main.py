#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI Main Module - Entry point for command-line interface."""

import argparse
import logging
import sys
from typing import Optional

# Import command classes
from .cli.commands import (
    AdvancedCommand,
    DefaultCommand,
    PartialReadCommand,
    QueryCommand,
    StructureCommand,
    SummaryCommand,
    TableCommand,
)
from .cli.info_commands import (
    DescribeQueryCommand,
    ListQueriesCommand,
    ShowExtensionsCommand,
    ShowLanguagesCommand,
)
from .output_manager import output_error, output_info, output_list
from .query_loader import query_loader


class CLICommandFactory:
    """Factory for creating CLI commands based on arguments."""

    @staticmethod
    def create_command(args: argparse.Namespace):
        """Create appropriate command based on arguments."""

        # Information commands (no file analysis required)
        if args.list_queries:
            return ListQueriesCommand(args)

        if args.describe_query:
            return DescribeQueryCommand(args)

        if args.show_supported_languages:
            return ShowLanguagesCommand(args)

        if args.show_supported_extensions:
            return ShowExtensionsCommand(args)

        # File analysis commands (require file path)
        if not args.file_path:
            return None

        # Partial read command - highest priority for file operations
        if hasattr(args, "partial_read") and args.partial_read:
            return PartialReadCommand(args)

        if hasattr(args, "table") and args.table:
            return TableCommand(args)

        if hasattr(args, "structure") and args.structure:
            return StructureCommand(args)

        if hasattr(args, "summary") and args.summary is not None:
            return SummaryCommand(args)

        if hasattr(args, "advanced") and args.advanced:
            return AdvancedCommand(args)

        if hasattr(args, "query_key") and args.query_key:
            return QueryCommand(args)

        if hasattr(args, "query_string") and args.query_string:
            return QueryCommand(args)

        # Default command - if file_path is provided but no specific command, use default analysis
        return DefaultCommand(args)


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="Tree-sitterを使用してコードを解析し、構造化された情報を抽出します。",
        epilog="例: tree-sitter-analyzer example.java --table=full",
    )

    # File path
    parser.add_argument("file_path", nargs="?", help="解析対象のファイルのパス")

    # Query options
    query_group = parser.add_mutually_exclusive_group(required=False)
    query_group.add_argument(
        "--query-key", help="利用可能なクエリのキー (例: class, method)"
    )
    query_group.add_argument(
        "--query-string", help="実行するTree-sitterクエリを直接指定"
    )

    # Information options
    parser.add_argument(
        "--list-queries", action="store_true", help="利用可能なクエリキーの一覧を表示"
    )
    parser.add_argument("--describe-query", help="指定されたクエリキーの説明を表示")
    parser.add_argument(
        "--show-supported-languages",
        action="store_true",
        help="サポートされている言語一覧を表示",
    )
    parser.add_argument(
        "--show-supported-extensions",
        action="store_true",
        help="サポートされている拡張子一覧を表示",
    )
    parser.add_argument(
        "--show-common-queries",
        action="store_true",
        help="複数言語共通のクエリ一覧を表示",
    )
    parser.add_argument(
        "--show-query-languages",
        action="store_true",
        help="クエリサポートされている言語一覧を表示",
    )

    # Output format options
    parser.add_argument(
        "--output-format",
        choices=["json", "text"],
        default="json",
        help="出力形式を指定",
    )
    parser.add_argument(
        "--table", choices=["full", "compact", "csv"], help="テーブル形式での出力"
    )
    parser.add_argument(
        "--include-javadoc",
        action="store_true",
        help="JavaDoc/ドキュメントコメントを出力に含める",
    )

    # Analysis options
    parser.add_argument("--advanced", action="store_true", help="高度な解析機能を使用")
    parser.add_argument(
        "--summary",
        nargs="?",
        const="classes,methods",
        help="指定された要素タイプの要約を表示",
    )
    parser.add_argument(
        "--structure", action="store_true", help="詳細な構造情報をJSON形式で出力"
    )
    parser.add_argument("--statistics", action="store_true", help="統計情報のみを表示")

    # Language options
    parser.add_argument(
        "--language", help="言語を明示的に指定（省略時は拡張子から自動判定）"
    )

    # Partial reading options
    parser.add_argument(
        "--partial-read",
        action="store_true",
        help="ファイルの部分読み込みモードを有効にする",
    )
    parser.add_argument("--start-line", type=int, help="読み込み開始行番号（1ベース）")
    parser.add_argument("--end-line", type=int, help="読み込み終了行番号（1ベース）")
    parser.add_argument(
        "--start-column", type=int, help="読み込み開始列番号（0ベース）"
    )
    parser.add_argument("--end-column", type=int, help="読み込み終了列番号（0ベース）")

    return parser


def handle_special_commands(args: argparse.Namespace) -> Optional[int]:
    """Handle special commands that don't fit the normal pattern."""

    # Validate partial read options
    if hasattr(args, 'partial_read') and args.partial_read:
        if args.start_line is None:
            output_error("ERROR: --start-lineが必須です")
            return 1
        
        if args.start_line < 1:
            output_error("ERROR: --start-lineは1以上である必要があります")
            return 1
        
        if args.end_line and args.end_line < args.start_line:
            output_error("ERROR: --end-lineは--start-line以上である必要があります")
            return 1
        
        if args.start_column is not None and args.start_column < 0:
            output_error("ERROR: --start-columnは0以上である必要があります")
            return 1
        
        if args.end_column is not None and args.end_column < 0:
            output_error("ERROR: --end-columnは0以上である必要があります")
            return 1

    # Query language commands
    if args.show_query_languages:
        output_list(["クエリサポートされている言語:"])
        for lang in query_loader.list_supported_languages():
            query_count = len(query_loader.list_queries_for_language(lang))
            output_list([f"  {lang:<15} ({query_count} クエリ)"])
        return 0

    if args.show_common_queries:
        common_queries = query_loader.get_common_queries()
        if common_queries:
            output_list("複数言語共通のクエリ:")
            for query in common_queries:
                output_list(f"  {query}")
        else:
            output_info("共通クエリが見つかりませんでした。")
        return 0

    return None


def main() -> None:
    """Main entry point for the CLI."""
    parser = create_argument_parser()
    args = parser.parse_args()

    # Configure logging for table output
    if hasattr(args, "table") and args.table:
        logging.getLogger().setLevel(logging.ERROR)
        logging.getLogger("tree_sitter_analyzer").setLevel(logging.ERROR)
        logging.getLogger("tree_sitter_analyzer.performance").setLevel(logging.ERROR)

    # Handle special commands first
    special_result = handle_special_commands(args)
    if special_result is not None:
        sys.exit(special_result)

    # Create and execute command
    command = CLICommandFactory.create_command(args)

    if command:
        exit_code = command.execute()
        sys.exit(exit_code)
    else:
        if not args.file_path:
            output_error("ERROR: ファイルパスが指定されていません。")
        else:
            output_error("ERROR: 実行可能なコマンドが指定されていません。")
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        output_info("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        output_error(f"Unexpected error: {e}")
        sys.exit(1)
