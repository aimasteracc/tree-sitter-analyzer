"""Repository file and query helpers for formatter test data."""

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from typing import Any


def store_test_data_set(repository: Any, test_data_set: Any) -> str:
    """Persist a test data set and return its id."""
    data_dir = repository.data_path / test_data_set.metadata.id
    data_dir.mkdir(exist_ok=True)

    _write_source_file(data_dir, test_data_set, repository._get_file_extension)
    _write_expected_outputs(data_dir, test_data_set.expected_outputs)
    _write_metadata(data_dir, test_data_set)
    _upsert_test_data_record(repository.db_path, data_dir, test_data_set)

    return test_data_set.metadata.id


def search_test_data_sets(
    db_path: Path,
    metadata_type: type,
    language: str | None = None,
    complexity: str | None = None,
    tags: list[str] | None = None,
    limit: int = 100,
) -> list[Any]:
    """Search repository metadata records with optional filters."""
    query, params = _build_search_query(language, complexity, tags, limit)

    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

    return [_metadata_from_row(row, metadata_type) for row in rows]


def _write_source_file(
    data_dir: Path, test_data_set: Any, extension_for_language: Callable[[str], str]
) -> None:
    source_file = (
        data_dir / f"source.{extension_for_language(test_data_set.metadata.language)}"
    )
    with open(source_file, "w", encoding="utf-8") as f:
        f.write(test_data_set.source_code)


def _write_expected_outputs(data_dir: Path, expected_outputs: dict[str, str]) -> None:
    outputs_dir = data_dir / "expected_outputs"
    outputs_dir.mkdir(exist_ok=True)

    for format_type, output in expected_outputs.items():
        output_file = outputs_dir / f"{format_type}.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output)


def _write_metadata(data_dir: Path, test_data_set: Any) -> None:
    metadata_file = data_dir / "metadata.json"
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "metadata": asdict(test_data_set.metadata),
                "test_scenarios": test_data_set.test_scenarios,
            },
            f,
            indent=2,
        )


def _upsert_test_data_record(db_path: Path, data_dir: Path, test_data_set: Any) -> None:
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO test_data_sets
            (id, name, description, language, complexity_level, file_size_bytes,
             element_counts, created_timestamp, version, tags, source_hash,
             validation_status, file_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                test_data_set.metadata.id,
                test_data_set.metadata.name,
                test_data_set.metadata.description,
                test_data_set.metadata.language,
                test_data_set.metadata.complexity_level,
                test_data_set.metadata.file_size_bytes,
                json.dumps(test_data_set.metadata.element_counts),
                test_data_set.metadata.created_timestamp,
                test_data_set.metadata.version,
                json.dumps(test_data_set.metadata.tags),
                test_data_set.metadata.source_hash,
                test_data_set.metadata.validation_status,
                str(data_dir),
            ),
        )
        conn.commit()


def _build_search_query(
    language: str | None,
    complexity: str | None,
    tags: list[str] | None,
    limit: int,
) -> tuple[str, list[str]]:
    query = "SELECT * FROM test_data_sets WHERE 1=1"
    params = []

    if language:
        query += " AND language = ?"
        params.append(language)

    if complexity:
        query += " AND complexity_level = ?"
        params.append(complexity)

    if tags:
        for tag in tags:
            query += " AND tags LIKE ?"
            params.append(f"%{tag}%")

    query += f" ORDER BY created_timestamp DESC LIMIT {limit}"
    return query, params


def _metadata_from_row(row: tuple[Any, ...], metadata_type: type) -> Any:
    return metadata_type(
        id=row[0],
        name=row[1],
        description=row[2],
        language=row[3],
        format_types=["full", "compact", "csv"],
        complexity_level=row[4],
        file_size_bytes=row[5],
        element_counts=json.loads(row[6]),
        created_timestamp=row[7],
        version=row[8],
        tags=json.loads(row[9]),
        source_hash=row[10],
        validation_status=row[11],
    )
