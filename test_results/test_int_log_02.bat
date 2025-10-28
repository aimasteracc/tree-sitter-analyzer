@echo off
echo === INT-LOG-02: Actual Log Output Content Test ===
echo.

REM Clear environment variables
set TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=
set TREE_SITTER_ANALYZER_LOG_DIR=
set TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=
set LOG_LEVEL=

REM Set environment variables for INT-LOG-02
set TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true
set TREE_SITTER_ANALYZER_LOG_DIR=./test_logs_content
set TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=INFO

echo Environment variables:
echo TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=%TREE_SITTER_ANALYZER_ENABLE_FILE_LOG%
echo TREE_SITTER_ANALYZER_LOG_DIR=%TREE_SITTER_ANALYZER_LOG_DIR%
echo TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=%TREE_SITTER_ANALYZER_FILE_LOG_LEVEL%
echo LOG_LEVEL=%LOG_LEVEL%
echo.

echo Executing MCP tool (analyze_code_structure)...
echo.

REM Execute run_test.py
uv run python run_test.py

echo.
echo Test completed. Check log file content:
echo - Directory: %TREE_SITTER_ANALYZER_LOG_DIR%
echo - File: tree_sitter_analyzer.log
echo.
