import json

try:
    with open("coverage.json") as f:
        data = json.load(f)

    # Calculate from files
    total_covered = 0
    total_statements = 0
    low_coverage_files = []
    high_coverage_files = []

    for file_path, file_data in data.get("files", {}).items():
        summary = file_data.get("summary", {})
        covered = summary.get("covered_lines", 0)
        statements = summary.get("num_statements", 0)
        percent = summary.get("percent_covered", 0)
        total_covered += covered
        total_statements += statements

        if percent < 50 and statements > 20:
            low_coverage_files.append((file_path, percent, statements))
        elif percent >= 80:
            high_coverage_files.append((file_path, percent, statements))

    overall = (total_covered / total_statements * 100) if total_statements > 0 else 0
    print(f"Total Coverage: {overall:.2f}%")
    print(f"Covered Lines: {total_covered}")
    print(f"Total Lines: {total_statements}")
    print("\nHigh Coverage Files (>= 80%):")
    for f, p, s in sorted(high_coverage_files, key=lambda x: -x[1])[:10]:
        print(f"  {p:.1f}% - {f} ({s} lines)")
    print("\nLow Coverage Files (< 50%, > 20 lines):")
    for f, p, s in sorted(low_coverage_files, key=lambda x: x[1])[:25]:
        print(f"  {p:.1f}% - {f} ({s} lines)")

except Exception as e:
    print(f"Error: {e}")
