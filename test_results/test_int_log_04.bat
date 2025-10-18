@echo off
echo === INT-LOG-04: Standard Logger and File Logger Level Separation Test ===
echo.

REM Clear environment variables
set TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=
set TREE_SITTER_ANALYZER_LOG_DIR=
set TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=
set LOG_LEVEL=

REM Set environment variables for INT-LOG-04
set LOG_LEVEL=WARNING
set TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true
set TREE_SITTER_ANALYZER_LOG_DIR=./test_logs_separation
set TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=DEBUG

echo Environment variables:
echo LOG_LEVEL=%LOG_LEVEL%
echo TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=%TREE_SITTER_ANALYZER_ENABLE_FILE_LOG%
echo TREE_SITTER_ANALYZER_LOG_DIR=%TREE_SITTER_ANALYZER_LOG_DIR%
echo TREE_SITTER_ANALYZER_FILE_LOG_LEVEL=%TREE_SITTER_ANALYZER_FILE_LOG_LEVEL%
echo.

echo Expected behavior:
echo - Standard error output: WARNING and ERROR logs only
echo - Log file: DEBUG, INFO, WARNING, ERROR all levels
echo.
echo NOTE: Current implementation limitation discovered:
echo LOG_LEVEL affects file logger too, so only WARNING/ERROR will be recorded.
echo.

echo Executing run_test.py...
echo.

REM Execute run_test.py
uv run python run_test.py

echo.
echo Test completed. Check results:
echo - Standard error output: Should show WARNING and ERROR only
echo - Log file: %TREE_SITTER_ANALYZER_LOG_DIR%\tree_sitter_analyzer.log
echo   (Current implementation: WARNING and ERROR only due to LOG_LEVEL limitation)
echo.