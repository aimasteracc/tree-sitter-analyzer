# run_test.py
import sys

from tree_sitter_analyzer.api import analyze_file, execute_query, validate_file
from tree_sitter_analyzer.utils import (
    log_debug,
    log_error,
    log_info,
    log_warning,
    setup_logger,
)

# ロガーを再セットアップして、環境変数の変更を確実に反映させる
log_level = "DEBUG"  # テスト中は全てのログを拾えるようにする
logger = setup_logger(level=log_level)


def run_mcp_tools():
    """MCPツールを実行してログを生成する"""
    # Javaファイルをテスト対象として使用
    java_files = [
        "examples/BigService.java",
        "examples/MultiClass.java",
        "examples/Sample.java",
    ]

    for file_path in java_files:
        log_info(f"--- Starting MCP tool tests for {file_path} ---")

        try:
            log_debug(f"Calling analyze_file for {file_path}")
            result = analyze_file(file_path)
            log_info(f"analyze_file finished successfully for {file_path}.")
            log_debug(f"Result type: {type(result)}")

            log_debug(f"Calling execute_query for {file_path}")
            query_result = execute_query(file_path, "method")
            log_info(f"execute_query finished successfully for {file_path}.")
            log_debug(f"Query result type: {type(query_result)}")

            log_debug(f"Calling validate_file for {file_path}")
            scale_result = validate_file(file_path)
            log_info(f"validate_file finished successfully for {file_path}.")
            log_debug(f"Scale result type: {type(scale_result)}")

        except Exception as e:
            log_error(
                f"An error occurred during MCP tool execution for {file_path}: {e}"
            )

        log_warning(f"This is a test warning message for {file_path}.")
        log_error(f"This is a test error message for {file_path}.")
        log_info(f"--- MCP tool tests finished for {file_path} ---")


def run_single_file_test(file_path="examples/BigService.java"):
    """単一ファイルでのテスト（デフォルトはBigService.java）"""
    log_info(f"--- Starting single file test for {file_path} ---")

    try:
        log_debug(f"Calling analyze_file for {file_path}")
        result = analyze_file(file_path)
        log_info(f"analyze_file finished successfully for {file_path}.")

        log_debug(f"Calling execute_query with 'class' query for {file_path}")
        query_result = execute_query(file_path, "class")
        log_info(f"execute_query (class) finished successfully for {file_path}.")

        log_debug(f"Calling execute_query with 'method' query for {file_path}")
        query_result = execute_query(file_path, "method")
        log_info(f"execute_query (method) finished successfully for {file_path}.")

        log_debug(f"Calling validate_file for {file_path}")
        scale_result = validate_file(file_path)
        log_info(f"validate_file finished successfully for {file_path}.")

    except Exception as e:
        log_error(f"An error occurred during single file test for {file_path}: {e}")

    log_warning("This is a test warning message for single file test.")
    log_error("This is a test error message for single file test.")
    log_info(f"--- Single file test finished for {file_path} ---")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "single":
            # 単一ファイルテスト
            file_path = sys.argv[2] if len(sys.argv) > 2 else "examples/BigService.java"
            run_single_file_test(file_path)
        elif sys.argv[1] == "all":
            # 全ファイルテスト
            run_mcp_tools()
        else:
            # 指定されたファイルでの単一テスト
            run_single_file_test(sys.argv[1])
    else:
        # デフォルトは単一ファイルテスト（BigService.java）
        run_single_file_test()
