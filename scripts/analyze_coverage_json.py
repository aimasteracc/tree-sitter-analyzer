import json


def analyze_coverage(json_path):
    try:
        with open(json_path) as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: {json_path} not found.")
        return

    files = data.get("files", {})
    results = []

    for filename, file_data in files.items():
        # summaryキーの中に covered_lines, num_statements 等があるはず
        summary = file_data.get("summary", {})
        num_statements = summary.get("num_statements", 0)
        covered_lines = summary.get("covered_lines", 0)

        if num_statements > 0:
            percent = (covered_lines / num_statements) * 100
            # 無視したいファイル（テストファイル自体や設定ファイルなど）を除外する簡易フィルタ
            if (
                "tests/" not in filename
                and "examples/" not in filename
                and "scripts/" not in filename
            ):
                results.append((filename, percent, covered_lines, num_statements))

    # カバレッジ率が低い順にソート
    results.sort(key=lambda x: x[1])

    print(f"{'Filename':<60} | {'Cover%':<8} | {'Covered':<8} | {'Total':<8}")
    print("-" * 90)
    for filename, percent, covered, total in results[:20]:  # ワースト20を表示
        print(f"{filename:<60} | {percent:6.2f}% | {covered:<8} | {total:<8}")


if __name__ == "__main__":
    analyze_coverage("coverage.json")
