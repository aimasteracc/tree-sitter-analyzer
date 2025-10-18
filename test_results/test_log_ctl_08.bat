@echo off
echo Setting environment variables for LOG-CTL-08 test...
set TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true
set TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=INVALID_LEVEL

echo Environment variables set:
echo TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=%TREE_SITTER_ANALYZER_ENABLE_FILE_LOG%
echo TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=%TREE_SITTER_ANALYZER_FILE_LOG_LEVEL%

echo Starting LOG-CTL-08 test (Invalid log level handling)...
uv run python run_test.py

echo Test completed.