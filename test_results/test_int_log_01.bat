@echo off
echo Setting environment variables for INT-LOG-01 test...
set TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true
set TREE_SITTER_ANALYZER_LOG_DIR=./test_logs_int
set TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=DEBUG

echo Environment variables set:
echo TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=%TREE_SITTER_ANALYZER_ENABLE_FILE_LOG%
echo TREE_SITTER_ANALYZER_LOG_DIR=%TREE_SITTER_ANALYZER_LOG_DIR%
echo TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=%TREE_SITTER_ANALYZER_FILE_LOG_LEVEL%

echo Starting INT-LOG-01 test (Combined environment variables)...
uv run python run_test.py

echo Test completed.
