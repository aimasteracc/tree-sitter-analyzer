import json

try:
    with open("coverage.json") as f:
        data = json.load(f)

    # Calculate from files
    total_covered = 0
    total_statements = 0
    all_files = []

    for file_path, file_data in data.get("files", {}).items():
        summary = file_data.get("summary", {})
        covered = summary.get("covered_lines", 0)
        statements = summary.get("num_statements", 0)
        percent = summary.get("percent_covered", 0)
        missing = summary.get("missing_lines", 0)
        total_covered += covered
        total_statements += statements

        if percent < 100 and statements > 0:
            all_files.append((file_path, percent, statements, missing))

    overall = (total_covered / total_statements * 100) if total_statements > 0 else 0
    print(f"Total Coverage: {overall:.2f}%")
    print(f"Covered Lines: {total_covered}")
    print(f"Total Lines: {total_statements}")
    print(f"Missing Lines: {total_statements - total_covered}")
    print("\nAll Files with < 100% Coverage (sorted by coverage %):")
    print(f"Total files needing improvement: {len(all_files)}")
    print()

    for f, p, s, m in sorted(all_files, key=lambda x: x[1]):
        print(f"  {p:5.1f}% - {f:80s} ({m:4d}/{s:4d} lines missing)")

except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
