"""Import/export helpers for formatter integration test data."""

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def export_test_data_suite_data(
    repository: Any, output_path: str, filters: dict[str, Any] | None = None
) -> str:
    """Export repository test data to a portable directory."""
    output_dir = Path(output_path)
    output_dir.mkdir(exist_ok=True)

    test_data_list = _select_export_metadata(repository, filters)
    exported_count = _export_test_data_sets(repository, output_dir, test_data_list)
    _write_export_manifest(output_dir, exported_count, filters, test_data_list)

    return str(output_dir)


def import_test_data_suite_data(
    repository: Any,
    import_path: str,
    metadata_type: Any,
    data_set_type: Any,
) -> dict[str, Any]:
    """Import repository test data from a portable export directory."""
    import_dir = Path(import_path)
    manifest = _load_export_manifest(import_dir)

    imported_count = 0
    skipped_count = 0
    errors: list[str] = []

    for test_data_id in manifest["test_data_ids"]:
        result = _import_one_test_data_set(
            repository, import_dir, test_data_id, metadata_type, data_set_type
        )
        imported_count += result["imported"]
        skipped_count += result["skipped"]
        errors.extend(result["errors"])

    return {
        "imported_count": imported_count,
        "skipped_count": skipped_count,
        "errors": errors,
        "total_in_manifest": len(manifest["test_data_ids"]),
    }


def _select_export_metadata(
    repository: Any, filters: dict[str, Any] | None
) -> list[Any]:
    if not filters:
        return repository.search_test_data(limit=1000)

    return repository.search_test_data(
        language=filters.get("language"),
        complexity=filters.get("complexity"),
        tags=filters.get("tags"),
        limit=filters.get("limit", 1000),
    )


def _export_test_data_sets(
    repository: Any, output_path: Path, test_data_list: list[Any]
) -> int:
    exported_count = 0
    for metadata in test_data_list:
        test_data = repository.get_test_data(metadata.id)
        if not test_data:
            continue

        export_dir = output_path / metadata.id
        export_dir.mkdir(exist_ok=True)

        _write_source_file(
            repository, export_dir, metadata.language, test_data.source_code
        )
        _write_expected_outputs(export_dir, test_data.expected_outputs)
        _write_metadata(export_dir, test_data)
        exported_count += 1

    return exported_count


def _write_source_file(
    repository: Any, export_dir: Path, language: str, source_code: str
) -> None:
    source_file = export_dir / f"source.{repository._get_file_extension(language)}"
    with open(source_file, "w", encoding="utf-8") as f:
        f.write(source_code)


def _write_expected_outputs(export_dir: Path, expected_outputs: dict[str, str]) -> None:
    outputs_dir = export_dir / "expected_outputs"
    outputs_dir.mkdir(exist_ok=True)

    for format_type, output in expected_outputs.items():
        output_file = outputs_dir / f"{format_type}.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output)


def _write_metadata(export_dir: Path, test_data: Any) -> None:
    metadata_file = export_dir / "metadata.json"
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "metadata": asdict(test_data.metadata),
                "test_scenarios": test_data.test_scenarios,
            },
            f,
            indent=2,
        )


def _write_export_manifest(
    output_path: Path,
    exported_count: int,
    filters: dict[str, Any] | None,
    test_data_list: list[Any],
) -> None:
    manifest_file = output_path / "export_manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "export_timestamp": datetime.now(UTC).isoformat(),
                "exported_count": exported_count,
                "filters_applied": filters or {},
                "test_data_ids": [m.id for m in test_data_list],
            },
            f,
            indent=2,
        )


def _load_export_manifest(import_path: Path) -> dict[str, Any]:
    if not import_path.exists():
        raise ValueError(f"Import path does not exist: {import_path}")

    manifest_file = import_path / "export_manifest.json"
    if not manifest_file.exists():
        raise ValueError("Export manifest not found")

    with open(manifest_file, encoding="utf-8") as f:
        return json.load(f)


def _import_one_test_data_set(
    repository: Any,
    import_path: Path,
    test_data_id: str,
    metadata_type: Any,
    data_set_type: Any,
) -> dict[str, Any]:
    test_dir = import_path / test_data_id
    if not test_dir.exists():
        return {
            "imported": 0,
            "skipped": 0,
            "errors": [f"Test data directory not found: {test_data_id}"],
        }

    try:
        if repository.get_test_data(test_data_id):
            return {"imported": 0, "skipped": 1, "errors": []}

        test_data_set = _load_exported_test_data(
            repository, test_dir, metadata_type, data_set_type
        )
        repository.store_test_data(test_data_set)
        return {"imported": 1, "skipped": 0, "errors": []}
    except Exception as e:
        return {
            "imported": 0,
            "skipped": 0,
            "errors": [f"Error importing {test_data_id}: {e}"],
        }


def _load_exported_test_data(
    repository: Any,
    test_dir: Path,
    metadata_type: Any,
    data_set_type: Any,
) -> Any:
    metadata_file = test_dir / "metadata.json"
    with open(metadata_file, encoding="utf-8") as f:
        data = json.load(f)

    metadata = metadata_type(**data["metadata"])
    source_code = _read_exported_source(repository, test_dir, metadata.language)
    expected_outputs = _read_exported_outputs(test_dir)

    return data_set_type(
        metadata=metadata,
        source_code=source_code,
        expected_outputs=expected_outputs,
        test_scenarios=data["test_scenarios"],
    )


def _read_exported_source(repository: Any, test_dir: Path, language: str) -> str:
    source_file = test_dir / f"source.{repository._get_file_extension(language)}"
    with open(source_file, encoding="utf-8") as f:
        return f.read()


def _read_exported_outputs(test_dir: Path) -> dict[str, str]:
    expected_outputs: dict[str, str] = {}
    outputs_dir = test_dir / "expected_outputs"
    if not outputs_dir.exists():
        return expected_outputs

    for output_file in outputs_dir.glob("*.txt"):
        with open(output_file, encoding="utf-8") as f:
            expected_outputs[output_file.stem] = f.read()

    return expected_outputs
