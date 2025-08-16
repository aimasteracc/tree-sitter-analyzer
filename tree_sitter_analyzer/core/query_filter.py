#!/usr/bin/env python3
"""
Query Filter Service

Provides post-processing filtering for query results, supporting filtering by name, parameters, and other conditions.
"""

import re
from typing import Any


class QueryFilter:
    """Query result filter"""

    def __init__(self) -> None:
        pass

    def filter_results(
        self, results: list[dict[str, Any]], filter_expression: str
    ) -> list[dict[str, Any]]:
        """
        Filter query results based on filter expression

        Args:
            results: Original query results
            filter_expression: Filter expression supporting multiple formats:
                - "name=main" - Exact name match
                - "name~auth*" - Pattern name match
                - "params=0" - Filter by parameter count
                - "static=true" - Filter by modifier

        Returns:
            Filtered results list
        """
        if not filter_expression:
            return results

        # Parse filter expression
        filters = self._parse_filter_expression(filter_expression)

        filtered_results = []
        for result in results:
            if self._matches_filters(result, filters):
                filtered_results.append(result)

        return filtered_results

    def _parse_filter_expression(self, expression: str) -> dict[str, Any]:
        """Parse filter expression"""
        filters = {}

        # Support multiple conditions separated by commas
        conditions = expression.split(",")

        for condition in conditions:
            condition = condition.strip()

            if "=" in condition:
                key, value = condition.split("=", 1)
                key = key.strip()
                value = value.strip()

                # Handle pattern matching
                if value.startswith("~"):
                    filters[key] = {"type": "pattern", "value": value[1:]}
                else:
                    filters[key] = {"type": "exact", "value": value}

        return filters

    def _matches_filters(self, result: dict[str, Any], filters: dict[str, Any]) -> bool:
        """Check if result matches all filter conditions"""
        for filter_key, filter_config in filters.items():
            if not self._matches_single_filter(result, filter_key, filter_config):
                return False
        return True

    def _matches_single_filter(
        self, result: dict[str, Any], filter_key: str, filter_config: dict[str, Any]
    ) -> bool:
        """Check single filter condition"""
        filter_type = filter_config["type"]
        filter_value = filter_config["value"]

        if filter_key == "name":
            return self._match_name(result, filter_type, filter_value)
        elif filter_key == "params":
            return self._match_params(result, filter_type, filter_value)
        elif filter_key == "static":
            return self._match_modifier(result, "static", filter_value)
        elif filter_key == "public":
            return self._match_modifier(result, "public", filter_value)
        elif filter_key == "private":
            return self._match_modifier(result, "private", filter_value)
        elif filter_key == "protected":
            return self._match_modifier(result, "protected", filter_value)

        return True

    def _match_name(self, result: dict[str, Any], match_type: str, value: str) -> bool:
        """Match method name"""
        content = result.get("content", "")

        # Extract method name
        method_name = self._extract_method_name(content)

        if match_type == "exact":
            return method_name == value
        elif match_type == "pattern":
            # Support wildcard patterns
            pattern = value.replace("*", ".*")
            return re.match(pattern, method_name, re.IGNORECASE) is not None

        return False

    def _match_params(
        self, result: dict[str, Any], match_type: str, value: str
    ) -> bool:
        """Match parameter count"""
        content = result.get("content", "")
        param_count = self._count_parameters(content)

        try:
            target_count = int(value)
            return param_count == target_count
        except ValueError:
            return False

    def _match_modifier(
        self, result: dict[str, Any], modifier: str, value: str
    ) -> bool:
        """Match modifier"""
        content = result.get("content", "")
        has_modifier = modifier in content

        return (value.lower() == "true") == has_modifier

    def _extract_method_name(self, content: str) -> str:
        """Extract method name from content"""
        # Match method declaration patterns
        patterns = [
            r"(?:public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\(",  # Java method
            r"def\s+(\w+)\s*\(",  # Python method
            r"function\s+(\w+)\s*\(",  # JavaScript function
        ]

        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                return match.group(1)

        return "unknown"

    def _count_parameters(self, content: str) -> int:
        """Count method parameters"""
        # Find parameter list
        match = re.search(r"\(([^)]*)\)", content)
        if not match:
            return 0

        params_str = match.group(1).strip()
        if not params_str:
            return 0

        # Simple parameter counting (by comma separation)
        # Note: This is a simple implementation, doesn't handle generics etc.
        params = [p.strip() for p in params_str.split(",") if p.strip()]
        return len(params)

    def get_filter_help(self) -> str:
        """Get filter help information"""
        return """
Filter Syntax Help:

Basic Syntax:
  --filter "key=value"               # Exact match
  --filter "key=~pattern"            # Pattern match (supports wildcard *)
  --filter "key1=value1,key2=value2" # Multiple conditions (AND logic)

Supported filter keys:
  name       - Method/function name
             e.g.: name=main, name=~auth*, name=~get*

  params     - Number of parameters
             e.g.: params=0, params=2

  static     - Whether it is a static method
             e.g.: static=true, static=false

  public     - Whether it is a public method
             e.g.: public=true, public=false

  private    - Whether it is a private method
             e.g.: private=true, private=false

Examples:
  --query-key methods --filter "name=main"
  --query-key methods --filter "name=~get*,public=true"
  --query-key methods --filter "params=0,static=true"
"""
