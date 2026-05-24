"""Database schema definitions for formatter integration test data."""

TEST_DATA_TABLE_SCHEMAS = (
    """
    CREATE TABLE IF NOT EXISTS test_data_sets (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        language TEXT NOT NULL,
        complexity_level TEXT NOT NULL,
        file_size_bytes INTEGER,
        element_counts TEXT,
        created_timestamp TEXT NOT NULL,
        version TEXT NOT NULL,
        tags TEXT,
        source_hash TEXT NOT NULL,
        validation_status TEXT DEFAULT 'unknown',
        file_path TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS test_data_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        test_data_id TEXT NOT NULL,
        usage_timestamp TEXT NOT NULL,
        test_type TEXT NOT NULL,
        result TEXT,
        FOREIGN KEY (test_data_id) REFERENCES test_data_sets (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS test_data_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        test_data_id TEXT NOT NULL,
        version TEXT NOT NULL,
        changes TEXT,
        created_timestamp TEXT NOT NULL,
        FOREIGN KEY (test_data_id) REFERENCES test_data_sets (id)
    )
    """,
)
