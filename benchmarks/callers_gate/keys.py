"""Cache keys. Every key is a pure function of the inputs that can change the cached value.

Index key (``index/<repo>/<key>``): the index is built by the *head* code and
then read by both base and head. It must change whenever anything that can
change index contents changes:

* the gate format and the index build arguments;
* the repo name and its pinned commit;
* the interpreter version and every installed distribution (name + version),
  except the analyzer itself, whose code is hashed directly;
* the gate's server environment template;
* ``pyproject.toml`` (entry points, plugin wiring);
* the blob hash of **every file** under ``tree_sitter_analyzer/`` (code, queries,
  data) except the query-only modules matched by :data:`QUERY_ONLY`.

TSA's own ``source_fingerprint`` (used by ``.ast-cache/graph-memo``) hashes
path + size + mtime, so two checkouts of one commit never agree; it is safe for
an in-place cache but useless across worktrees. The gate hashes git blobs
instead, which are content-addressed and line-ending normalized.

``QUERY_ONLY`` is a claim: "building the index never imports these modules".
The index builder (:mod:`._index_worker`) audits ``sys.modules`` after the
build and the gate refuses an index whose build loaded one of them. A change
that makes the indexer import such a module must edit a non-excluded file (the
importer), which changes the key, so the audit always runs on the new code.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from .layout import GATE_FORMAT, INDEX_ARGS, QUERY_ARGS

#: Package-relative globs that only the ``nav action=callers`` query path uses.
QUERY_ONLY: tuple[str, ...] = ("mcp/tools/callers_*.py",)


def is_query_only(rel: str) -> bool:
    return any(fnmatch.fnmatchcase(rel, pattern) for pattern in QUERY_ONLY)


def query_only_modules(blobs: Iterable[str]) -> list[str]:
    """Dotted module names of the excluded files (for the import audit)."""
    out = []
    for rel in blobs:
        if is_query_only(rel) and rel.endswith(".py"):
            out.append("tree_sitter_analyzer." + rel[:-3].replace("/", "."))
    return sorted(out)


def _digest(parts: Mapping[str, Any]) -> str:
    data = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.blake2b(data, digest_size=12).hexdigest()


def index_key(
    *,
    repo: str,
    repo_sha: str,
    package_blobs: Mapping[str, str],
    pyproject_blob: str | None,
    env_fingerprint: str,
) -> str:
    """Key of the index the head code builds for ``repo``."""
    if not package_blobs:
        raise ValueError("empty package tree: refusing to key an index on nothing")
    indexed = {rel: sha for rel, sha in package_blobs.items() if not is_query_only(rel)}
    return _digest(
        {
            "kind": "index",
            "format": GATE_FORMAT,
            "args": INDEX_ARGS,
            "repo": repo,
            "repo_sha": repo_sha,
            "env": env_fingerprint,
            "pyproject": pyproject_blob,
            "package": sorted(indexed.items()),
        }
    )


def query_key(*, targets_sha256: str, scip: str | None = None) -> str:
    """Key of one answer set beyond (tree, index key): the targets and the query form.

    ``scip`` is the digest of the SCIP index + manifest a ``--scip`` head side
    reads; without it the key is exactly the key of a run without SCIP.
    """
    parts: dict[str, Any] = {
        "kind": "query",
        "format": GATE_FORMAT,
        "args": QUERY_ARGS,
        "forms": ["full", "compact"],
        "targets": targets_sha256,
    }
    if scip is not None:
        parts["scip"] = scip
    return _digest(parts)


def env_fingerprint(
    python_version: str, distributions: Iterable[str], server_env: Mapping[str, str]
) -> str:
    dists = sorted(
        d
        for d in distributions
        if not d.lower().replace("_", "-").startswith("tree-sitter-analyzer==")
    )
    return _digest(
        {
            "kind": "env",
            "python": python_version,
            "dists": dists,
            "server_env": dict(sorted(server_env.items())),
        }
    )
