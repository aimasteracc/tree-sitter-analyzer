#!/usr/bin/env python3
"""
Query Command

Handles query execution functionality.
"""

from ...output_manager import output_data, output_error, output_info, output_json
from ...query_loader import query_loader
from .base_command import BaseCommand


class QueryCommand(BaseCommand):
    """Command for executing queries."""

    async def execute_async(self, language: str) -> int:
        # Get the query to execute
        query_to_execute = None

        if hasattr(self.args, "query_key") and self.args.query_key:
            try:
                query_to_execute = query_loader.get_query(language, self.args.query_key)
                if query_to_execute is None:
                    output_error(
                        f"ERROR: クエリ '{self.args.query_key}' が言語 '{language}' で見つかりません"
                    )
                    return 1
            except ValueError as e:
                output_error(f"ERROR: {e}")
                return 1
        elif hasattr(self.args, "query_string") and self.args.query_string:
            query_to_execute = self.args.query_string

        if not query_to_execute:
            output_error("ERROR: クエリが指定されていません。")
            return 1

        # Perform analysis
        analysis_result = await self.analyze_file(language)
        if not analysis_result:
            return 1

        # Process query results
        results = []
        if hasattr(analysis_result, "query_results") and analysis_result.query_results:
            results = analysis_result.query_results.get("captures", [])
        else:
            # Create basic results from elements
            if hasattr(analysis_result, "elements") and analysis_result.elements:
                for element in analysis_result.elements:
                    results.append(
                        {
                            "capture_name": getattr(
                                element, "__class__", type(element)
                            ).__name__.lower(),
                            "node_type": getattr(
                                element, "__class__", type(element)
                            ).__name__,
                            "start_line": getattr(element, "start_line", 0),
                            "end_line": getattr(element, "end_line", 0),
                            "content": getattr(element, "name", str(element)),
                        }
                    )

        # Output results
        if results:
            if self.args.output_format == "json":
                output_json(results)
            else:
                for i, query_result in enumerate(results, 1):
                    output_data(
                        f"\n{i}. {query_result['capture_name']} ({query_result['node_type']})"
                    )
                    output_data(
                        f"   位置: 行 {query_result['start_line']}-{query_result['end_line']}"
                    )
                    output_data(f"   内容:\n{query_result['content']}")
        else:
            output_info("\nINFO: クエリにマッチする結果は見つかりませんでした。")

        return 0
