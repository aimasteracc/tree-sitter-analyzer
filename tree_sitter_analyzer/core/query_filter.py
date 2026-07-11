#!/usr/bin/env python3
"""
Query Filter Service

Provides post-processing filtering for query results, supporting filtering by name, parameters, and other conditions.
"""

import re
import sys
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

        # Warn once when complexity filter is present but none of the input items have
        # complexity_score — this typically means the query key (e.g. classes, imports)
        # does not produce complexity data.
        if (
            "complexity" in filters
            and results
            and all("complexity_score" not in r for r in results)
        ):
            sys.stderr.write(
                "Warning: '--filter complexity' was applied but none of the results "
                "have 'complexity_score'. "
                "Try --query-key methods or functions instead.\n"
            )

        return filtered_results

    def _parse_filter_expression(self, expression: str) -> dict[str, Any]:
        """Parse filter expression"""
        filters = {}

        # Support multiple conditions separated by commas
        conditions = expression.split(",")

        for condition in conditions:
            condition = condition.strip()

            # Check comparison operators first (>=/<= before >/<, to avoid mis-parsing)
            if ">=" in condition:
                key, raw_value = condition.split(">=", 1)
                parsed = self._parse_numeric_value(key.strip(), raw_value.strip(), ">=")
                if parsed is not None:
                    filters[key.strip()] = {"type": "gte", "value": parsed}
            elif "<=" in condition:
                key, raw_value = condition.split("<=", 1)
                parsed = self._parse_numeric_value(key.strip(), raw_value.strip(), "<=")
                if parsed is not None:
                    filters[key.strip()] = {"type": "lte", "value": parsed}
            elif ">" in condition:
                key, raw_value = condition.split(">", 1)
                parsed = self._parse_numeric_value(key.strip(), raw_value.strip(), ">")
                if parsed is not None:
                    filters[key.strip()] = {"type": "gt", "value": parsed}
            elif "<" in condition:
                key, raw_value = condition.split("<", 1)
                parsed = self._parse_numeric_value(key.strip(), raw_value.strip(), "<")
                if parsed is not None:
                    filters[key.strip()] = {"type": "lt", "value": parsed}
            elif "=" in condition:
                key, value = condition.split("=", 1)
                key = key.strip()
                value = value.strip()

                # Handle pattern matching
                if value.startswith("~"):
                    filters[key] = {"type": "pattern", "value": value[1:]}
                else:
                    filters[key] = {"type": "exact", "value": value}

        return filters

    def _parse_numeric_value(
        self, key: str, raw_value: str, operator: str
    ) -> float | None:
        """Parse a numeric RHS value for comparison operators.

        Returns the float value on success, or None on failure (with a warning to stderr).
        """
        try:
            return float(raw_value)
        except ValueError:
            sys.stderr.write(
                f"Warning: filter '{key}{operator}{raw_value}' — "
                f"'{raw_value}' is not a valid number; condition ignored.\n"
            )
            return None

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
        elif filter_key == "visibility":
            return self._match_visibility(result, filter_value)
        elif filter_key == "static":
            return self._match_modifier(result, "static", filter_value)
        elif filter_key == "public":
            return self._match_modifier(result, "public", filter_value)
        elif filter_key == "private":
            return self._match_modifier(result, "private", filter_value)
        elif filter_key == "protected":
            return self._match_modifier(result, "protected", filter_value)
        elif filter_key == "async":
            return self._match_modifier(result, "async", filter_value)
        elif filter_key == "final":
            return self._match_modifier(result, "final", filter_value)
        elif filter_key == "abstract":
            return self._match_modifier(result, "abstract", filter_value)
        elif filter_key == "complexity":
            return self._match_numeric_comparison(result, "complexity_score", filter_config)
        elif filter_key == "line_span":
            return self._match_numeric_comparison(result, "line_span", filter_config)

        return True

    def _match_numeric_comparison(
        self, result: dict[str, Any], field_name: str, filter_config: dict[str, Any]
    ) -> bool:
        """Compare a numeric field in result against a filter config with type/value.

        Returns False if the field is absent (excludes the result).
        """
        field_value = result.get(field_name)
        if field_value is None:
            return False

        threshold = filter_config["value"]
        comparison_type = filter_config["type"]

        if comparison_type == "gt":
            return bool(float(field_value) > threshold)
        elif comparison_type == "lt":
            return bool(float(field_value) < threshold)
        elif comparison_type == "gte":
            return bool(float(field_value) >= threshold)
        elif comparison_type == "lte":
            return bool(float(field_value) <= threshold)

        return False

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
        """Match modifier as a keyword in the declaration prefix"""
        content = result.get("content", "")
        # Only check first line of the declaration to avoid matching
        # identifiers like "abstractMethod" or "staticValue"
        first_line = content.split("\n")[0]
        # Match modifier as a standalone keyword before the return type/name
        pattern = r"(?:^|\s)" + re.escape(modifier) + r"(?:\s|<)"
        has_modifier = bool(re.search(pattern, first_line))

        return (value.lower() == "true") == has_modifier

    def _match_visibility(self, result: dict[str, Any], value: str) -> bool:
        """Match visibility modifier in content"""
        content = result.get("content", "")
        vis = value.lower()
        if vis in ("public", "private", "protected"):
            return vis in content
        return True

    def _extract_method_name(self, content: str) -> str:
        """Extract method name from content"""
        patterns = [
            r"(?:public|private|protected)\s+(?:static\s+)?(?:final\s+)?(?:abstract\s+)?(?:synchronized\s+)?(?:[\w<>,\s\[\]]+)\s+(\w+)\s*\(",  # Java/C# method
            r"(?:static\s+)?(?:final\s+)?(?:abstract\s+)?(?:[\w<>,\s\[\]]+)\s+(\w+)\s*\(",  # Java/C# method (no visibility)
            r"def\s+(\w+)\s*\(",  # Python method
            r"function\s+(\w+)\s*\(",  # JavaScript function
        ]

        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                return match.group(1)

        return "unknown"

    def _count_parameters(self, content: str) -> int:
        """Count method parameters, handling nested generics/parens."""
        match = re.search(r"\(([^)]*)\)", content)
        if not match:
            return 0

        params_str = match.group(1).strip()
        if not params_str:
            return 0

        count = 0
        depth = 0
        for ch in params_str:
            if ch in "(<":
                depth += 1
            elif ch in ")>":
                depth -= 1
            elif ch == "," and depth == 0:
                count += 1

        if params_str:
            count += 1

        return count

    def get_filter_help(self) -> str:
        """Get filter help information"""
        return """
Filter Syntax Help:

Basic Syntax:
  --filter "key=value"               # Exact match
  --filter "key=~pattern"            # Pattern match (supports wildcard *)
  --filter "key1=value1,key2=value2" # Multiple conditions (AND logic)

Comparison Operators:
  --filter "key>N"                   # Greater than
  --filter "key<N"                   # Less than
  --filter "key>=N"                  # Greater than or equal
  --filter "key<=N"                  # Less than or equal

Supported filter keys:
  name       - Method/function name
             e.g.: name=main, name=~auth*, name=~get*

  params     - Number of parameters
             e.g.: params=0, params=2

  static     - Whether it is a static method
             e.g.: static=true, static=false

  visibility - Visibility modifier (checks content for the keyword)
             e.g.: visibility=private, visibility=public, visibility=protected

  public     - Whether it is a public method
             e.g.: public=true, public=false

  private    - Whether it is a private method
             e.g.: private=true, private=false

  async      - Whether it is async
             e.g.: async=true, async=false

  final      - Whether it is final
             e.g.: final=true, final=false

  abstract   - Whether it is abstract
             e.g.: abstract=true, abstract=false

  complexity - Complexity score (比較演算子 >, <, >=, <= が有効)
             e.g.: complexity>10, complexity<5, complexity>=3
             Note: complexity_score を持たないアイテムは除外される

  line_span  - 行数 (end_line - start_line + 1) (比較演算子 >, <, >=, <= が有効)
             e.g.: line_span>50, line_span<20, line_span>=10

Examples:
  --query-key methods --filter "name=main"
  --query-key methods --filter "name=~get*,public=true"
  --query-key methods --filter "params=0,static=true"
  --query-key methods --filter "complexity>10"
  --query-key methods --filter "line_span>50"
  --query-key methods --filter "complexity>5,public=true"
"""
