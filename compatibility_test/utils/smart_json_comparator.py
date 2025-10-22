import copy
import json
from pathlib import Path

import deepdiff


class SmartJsonComparator:
    def __init__(self, config_path):
        """設定ファイルを読み込んで初期化"""
        with open(config_path) as f:
            self.config = json.load(f)

    def _sort_arrays(self, data):
        """設定に基づいて配列をソートする再帰的な関数"""
        if isinstance(data, dict):
            for key, value in data.items():
                if key in self.config.get("sort_arrays_by", {}) and isinstance(
                    value, list
                ):
                    sort_key = self.config["sort_arrays_by"][key]
                    # sort_keyが存在する要素のみをソート対象とする
                    items_to_sort = [
                        item
                        for item in value
                        if isinstance(item, dict) and sort_key in item
                    ]
                    # sort_keyが存在しない要素はそのまま
                    other_items = [
                        item
                        for item in value
                        if not (isinstance(item, dict) and sort_key in item)
                    ]

                    try:
                        sorted_items = sorted(items_to_sort, key=lambda x: x[sort_key])
                        data[key] = sorted_items + other_items
                    except (TypeError, KeyError):
                        # ソートキーでソートできない場合は何もしない
                        pass

                self._sort_arrays(value)
        elif isinstance(data, list):
            for item in data:
                self._sort_arrays(item)
        return data

    def normalize_json(self, data):
        """JSONを正規化（無視フィールド除去、ソート等）"""

        # deepcopyして元のデータを変更しないようにする
        data_copy = copy.deepcopy(data)

        # 配列のソート
        sorted_data = self._sort_arrays(data_copy)

        def recursive_normalize(d):
            if isinstance(d, dict):
                new_dict = {}
                # キーの正規化が有効な場合はキーでソート
                items = (
                    sorted(d.items())
                    if self.config.get("normalize_keys")
                    else d.items()
                )
                for k, v in items:
                    if k not in self.config.get("ignore_fields", []):
                        new_dict[k] = recursive_normalize(v)
                return new_dict
            elif isinstance(d, list):
                return [recursive_normalize(item) for item in d]
            else:
                return d

        return recursive_normalize(sorted_data)

    def compare_with_report(self, file1_path, file2_path):
        """詳細な比較レポートを生成"""
        with open(file1_path, encoding="utf-8") as f1:
            data1 = json.load(f1)
        with open(file2_path, encoding="utf-8") as f2:
            data2 = json.load(f2)

        normalized1 = self.normalize_json(data1)
        normalized2 = self.normalize_json(data2)

        raw_diff = deepdiff.DeepDiff(
            data1, data2, ignore_order=self.config.get("ignore_field_order", True)
        )
        normalized_diff = deepdiff.DeepDiff(
            normalized1,
            normalized2,
            ignore_order=self.config.get("ignore_field_order", True),
        )

        report = {
            "file1": str(file1_path),
            "file2": str(file2_path),
            "raw_diff": raw_diff,
            "normalized_diff": normalized_diff,
            "is_identical_raw": not raw_diff,
            "is_identical_normalized": not normalized_diff,
        }

        return report

    def generate_normalized_files(self, input_dir, output_dir):
        """正規化されたファイルを出力ディレクトリに生成"""
        input_path = Path(input_dir)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        for file_path in input_path.glob("*.json"):
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)

            normalized_data = self.normalize_json(data)

            output_file_path = output_path / file_path.name
            with open(output_file_path, "w", encoding="utf-8") as f:
                json.dump(normalized_data, f, indent=2, ensure_ascii=False)
