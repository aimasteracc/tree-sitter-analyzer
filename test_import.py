#!/usr/bin/env python3
import sys
import traceback

try:
    from tree_sitter_analyzer.legacy_table_formatter import LegacyTableFormatter
    print("Import successful!")
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
