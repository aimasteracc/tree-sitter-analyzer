@echo off
echo Setting environment variables for LOG-CTL-06 test...
set TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true
set TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=WARNING

echo Environment variables set:
echo TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=%TREE_SITTER_ANALYZER_ENABLE_FILE_LOG%
echo TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=%TREE_SITTER_ANALYZER_FILE_LOG_LEVEL%

echo Starting LOG-CTL-06 test...
uv run python run_test.py

echo Test completed.