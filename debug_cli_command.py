#!/usr/bin/env python3
"""
CLI Command Selection Debug Script
"""

import sys
sys.path.insert(0, '.')

from tree_sitter_analyzer.cli_main import create_argument_parser
from tree_sitter_analyzer.cli.commands.query_command import QueryCommand
from tree_sitter_analyzer.cli.commands.default_command import DefaultCommand

def debug_command_selection():
    """Debug which command is selected for query-key"""
    
    # Parse arguments
    parser = create_argument_parser()
    args = parser.parse_args(['test_form_simple.html', '--query-key', 'form_element', '--table', 'compact'])
    
    print("=== CLI Command Selection Debug ===")
    print(f"args.query_key: {getattr(args, 'query_key', 'NOT_FOUND')}")
    print(f"hasattr(args, 'query_key'): {hasattr(args, 'query_key')}")
    print(f"args.query_key is not None: {getattr(args, 'query_key', None) is not None}")
    print(f"bool(args.query_key): {bool(getattr(args, 'query_key', None))}")
    
    # Manual command selection logic
    print("\n=== Command Selection Logic ===")
    
    if hasattr(args, "query_key") and args.query_key:
        print("✅ QueryCommand should be selected")
        command = QueryCommand(args)
    else:
        print("❌ DefaultCommand will be selected")
        command = DefaultCommand(args)
    
    print(f"Selected command: {type(command).__name__}")
    
    # Test the actual condition
    condition_result = hasattr(args, "query_key") and args.query_key
    print(f"Condition result: {condition_result}")

if __name__ == "__main__":
    debug_command_selection()