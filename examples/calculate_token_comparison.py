#!/usr/bin/env python3
"""
Token consumption comparison analysis script
Calculates and compares token consumption differences with and without structured data (detailed/summary).
"""

import json
import re


def count_tokens_estimate(text):
    """
    Estimate token count by character count instead of strict tokenizer.
    Generally calculated as Japanese: 1 character = 1 token, alphanumeric: 4 characters = 1 token.
    """
    # Count Japanese characters (hiragana, katakana, kanji)
    japanese_chars = len(re.findall(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]", text))

    # Count other characters (alphanumeric, symbols, spaces, etc.)
    other_chars = len(text) - japanese_chars

    # Token count estimation: Japanese 1 char = 1 token, others 4 chars = 1 token
    estimated_tokens = japanese_chars + (other_chars // 4)

    return estimated_tokens


def read_file_content(file_path):
    """Read file content"""
    try:
        with open(file_path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"File reading error: {e}")
        return ""


def extract_method_lines(java_content, start_line, end_line):
    """Extract code from specified line range"""
    lines = java_content.split("\n")
    # 1-based indexing to 0-based indexing
    start_idx = max(0, start_line - 1)
    end_idx = min(len(lines), end_line)

    extracted_lines = lines[start_idx:end_idx]
    return "\n".join(extracted_lines)


def find_update_customer_name_method_detailed(json_content):
    """Get updateCustomerName method information from BigService.json (detailed version)"""
    try:
        # Extract actual JSON part from JSON content
        json_start = json_content.find("{")
        if json_start == -1:
            return None

        json_data = json.loads(json_content[json_start:])

        # Search for updateCustomerName in methods section
        for method in json_data.get("methods", []):
            if method.get("name") == "updateCustomerName":
                lines_str = method.get("lines", "")
                if "-" in lines_str:
                    start_line, end_line = map(int, lines_str.split("-"))
                    return {
                        "name": method.get("name"),
                        "start_line": start_line,
                        "end_line": end_line,
                        "lines": lines_str,
                        "visibility": method.get("visibility"),
                        "parameters": method.get("parameters"),
                        "complexity": method.get("complexity"),
                    }
        return None
    except Exception as e:
        print(f"Detailed JSON parsing error: {e}")
        return None


def find_update_customer_name_method_summary(summary_content):
    """Get updateCustomerName method information from BigService.summary.json (summary version)"""
    try:
        # Extract actual JSON part from JSON content
        json_start = summary_content.find("{")
        if json_start == -1:
            return None

        json_data = json.loads(summary_content[json_start:])

        # Search for updateCustomerName in summary_elements section
        for element in json_data.get("summary_elements", []):
            if (
                element.get("name") == "updateCustomerName"
                and element.get("type") == "method"
            ):
                lines_info = element.get("lines", {})
                start_line = lines_info.get("start")
                end_line = lines_info.get("end")

                if start_line and end_line:
                    return {
                        "name": element.get("name"),
                        "start_line": start_line,
                        "end_line": end_line,
                        "lines": f"{start_line}-{end_line}",
                        "type": element.get("type"),
                    }
        return None
    except Exception as e:
        print(f"Summary JSON parsing error: {e}")
        return None


def main():
    print("=" * 80)
    print("Final Token Consumption Comparison Analysis")
    print("=" * 80)

    # File reading
    java_content = read_file_content("BigService.java")
    json_content = read_file_content("BigService.json")
    summary_content = read_file_content("BigService.summary.json")

    if not java_content or not json_content or not summary_content:
        print("Failed to read files.")
        return

    # Basic information of BigService.java
    java_lines = java_content.split("\n")
    total_java_lines = len(java_lines)

    print(f"BigService.java: {total_java_lines:,} lines")

    # Get updateCustomerName method information (detailed and summary versions)
    method_info_detailed = find_update_customer_name_method_detailed(json_content)
    method_info_summary = find_update_customer_name_method_summary(summary_content)

    if not method_info_detailed or not method_info_summary:
        print("updateCustomerName method information not found.")
        return

    print(f"updateCustomerName method: {method_info_detailed['lines']} lines")

    # Scenario 1: Token count for entire BigService.java
    scenario1_tokens = count_tokens_estimate(java_content)

    # Scenario 2: BigService.json + updateCustomerName method part token count
    json_tokens = count_tokens_estimate(json_content)

    # Extract updateCustomerName method part
    method_code = extract_method_lines(
        java_content,
        method_info_detailed["start_line"],
        method_info_detailed["end_line"],
    )
    method_tokens = count_tokens_estimate(method_code)
    method_lines_count = (
        method_info_detailed["end_line"] - method_info_detailed["start_line"] + 1
    )

    scenario2_tokens = json_tokens + method_tokens

    # Scenario 3: BigService.summary.json + updateCustomerName method part token count
    summary_tokens = count_tokens_estimate(summary_content)
    scenario3_tokens = summary_tokens + method_tokens

    # Calculate reduction amount and reduction rate
    scenario2_reduction = scenario1_tokens - scenario2_tokens
    scenario2_reduction_percentage = (
        (scenario2_reduction / scenario1_tokens) * 100 if scenario1_tokens > 0 else 0
    )

    scenario3_reduction_vs_scenario1 = scenario1_tokens - scenario3_tokens
    scenario3_reduction_percentage_vs_scenario1 = (
        (scenario3_reduction_vs_scenario1 / scenario1_tokens) * 100
        if scenario1_tokens > 0
        else 0
    )

    scenario3_reduction_vs_scenario2 = scenario2_tokens - scenario3_tokens
    scenario3_reduction_percentage_vs_scenario2 = (
        (scenario3_reduction_vs_scenario2 / scenario2_tokens) * 100
        if scenario2_tokens > 0
        else 0
    )

    # Display results
    print("\n" + "=" * 80)
    print("【Final Token Consumption Comparison】")
    print("=" * 80)

    print("\n■ Scenario 1: Traditional (Entire File)")
    print(f"   - Target: BigService.java ({total_java_lines:,} lines)")
    print(f"   - Token count: Approx. {scenario1_tokens:,} tokens")

    print("\n■ Scenario 2: Detailed Data Utilization")
    print(f"   - Target: BigService.json + Code part ({method_lines_count} lines)")
    print(
        f"   - Token count: Approx. {scenario2_tokens:,} tokens (JSON: {json_tokens:,} + Code: {method_tokens:,})"
    )
    print(
        f"   - Reduction rate (vs Scenario 1): Approx. {scenario2_reduction_percentage:.1f}%"
    )

    print("\n■ Scenario 3: Summary Data Utilization")
    print(
        f"   - Target: BigService.summary.json + Code part ({method_lines_count} lines)"
    )
    print(
        f"   - Token count: Approx. {scenario3_tokens:,} tokens (JSON: {summary_tokens:,} + Code: {method_tokens:,})"
    )
    print(
        f"   - Reduction rate (vs Scenario 1): Approx. {scenario3_reduction_percentage_vs_scenario1:.1f}%"
    )
    print(
        f"   - Reduction rate (vs Scenario 2): Approx. {scenario3_reduction_percentage_vs_scenario2:.1f}%"
    )

    # Detailed information
    print("\n" + "=" * 80)
    print("【Detailed Information】")
    print("=" * 80)
    print("updateCustomerName method details:")
    print(f"  - Line range: {method_info_detailed['lines']}")
    print(f"  - Extracted lines: {method_lines_count} lines")
    print(f"  - Visibility: {method_info_detailed.get('visibility', 'N/A')}")
    print(f"  - Parameter count: {method_info_detailed.get('parameters', 'N/A')}")
    print(f"  - Complexity: {method_info_detailed.get('complexity', 'N/A')}")

    print("\nFile size comparison:")
    print(f"  - BigService.java: {len(java_content):,} characters")
    print(f"  - BigService.json: {len(json_content):,} characters")
    print(f"  - BigService.summary.json: {len(summary_content):,} characters")
    print(f"  - Extracted code part: {len(method_code):,} characters")

    print("\nNote: Token counts are estimated values based on character count.")
    print(
        "      Calculated as Japanese characters = 1 token, others 4 characters = 1 token."
    )

    # Conclusion
    print("\n" + "=" * 80)
    print("【Conclusion】")
    print("=" * 80)
    print("With the introduction of the --summary feature, compared to Scenario 2,")
    print(
        f"an additional approx. {scenario3_reduction_percentage_vs_scenario2:.1f}% token reduction was achieved."
    )
    print("\nThis improvement significantly enhances the practicality and")
    print("economic efficiency of LLM-powered development support tools,")
    print("enabling more efficient code analysis and AI-assisted development.")


if __name__ == "__main__":
    main()
