#!/usr/bin/env python3
"""
QueryCommand Execution Debug Script
"""

import sys
import asyncio
sys.path.insert(0, '.')

from tree_sitter_analyzer.cli_main import create_argument_parser
from tree_sitter_analyzer.cli.commands.query_command import QueryCommand

async def debug_query_command():
    """Debug QueryCommand execution"""
    
    # Parse arguments
    parser = create_argument_parser()
    args = parser.parse_args(['test_form_simple.html', '--query-key', 'form_element', '--table', 'compact'])
    
    print("=== QueryCommand Execution Debug ===")
    print(f"File: {args.file_path}")
    print(f"Query Key: {args.query_key}")
    print(f"Table Format: {getattr(args, 'table', 'NOT_SET')}")
    
    # Create and execute QueryCommand
    command = QueryCommand(args)
    
    # Detect language
    from tree_sitter_analyzer.language_detector import detect_language_from_file
    language = detect_language_from_file(args.file_path)
    print(f"Detected Language: {language}")
    
    # Execute the command
    print("\n=== Command Execution ===")
    try:
        result = await command.execute_async(language)
        print(f"Command result: {result}")
    except Exception as e:
        print(f"Command execution failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_query_command())