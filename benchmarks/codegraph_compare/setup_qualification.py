"""Compatibility facade for the split NO1-008A qualification contracts.

The implementation is separated by responsibility into plan, inventory, schema,
and validation modules.  This module preserves the original import surface.
"""

# ruff: noqa: F401 - intentional compatibility re-exports

from benchmarks.codegraph_compare.setup_qualification_inventory import (
    _git,
    _tracked_stage,
    inventory_sources,
)
from benchmarks.codegraph_compare.setup_qualification_paths import (
    _hash_tree,
    _hash_tree_at,
    _open_beneath,
    _open_root,
    _read_regular_at,
    _read_regular_beneath,
    _snapshot_tree_at,
    _stable_directory_identity,
    _tree_size,
    _tree_size_at,
    canonical_relative_path,
)
from benchmarks.codegraph_compare.setup_qualification_plan import (
    DEFAULT_SOURCE_RULES,
    EXPECTED_CELLS,
    FROZEN_EXECUTION_ENVIRONMENT_DIGEST,
    INDEX_PATH_PLACEHOLDER,
    INDEXED_ARMS,
    REPOSITORIES,
    ZERO_COUNTERS,
    CellPlanV1,
    EligibilityV1,
    ExecutionSpecV1,
    HarnessArtifactV1,
    OracleSpecV1,
    ResourcePlanV1,
    SourceRulesV1,
    _bytes_hash,
    _is_finite_number,
    _sorted_paths,
    _write_exclusive,
    produce_strict_cell,
)
from benchmarks.codegraph_compare.setup_qualification_schema import (
    _canonical_json_bytes,
    _require_exact_keys,
    _strict_json_bytes,
    strict_json_loads,
    validate_receipt_schema_v2,
)
from benchmarks.codegraph_compare.setup_qualification_trust import VerifierConfigV1
from benchmarks.codegraph_compare.setup_qualification_validation import (
    _evidence_core_payload,
    validate_cell_receipt,
)
