"""Gate constants and the on-disk layout under the gate root.

Root: ``--root`` or ``TSA_GATE_ROOT`` (default ``C:\\git-private\\tsa-gate``)::

    config.json                         interpreter + corpus provenance (written by setup)
    repos/<repo>/                       bare clone, pinned commit; never deleted per PR
    corpus/targets/<repo>.json          the r15 callers corpus, one row per target
    corpus/gt2/<repo>.json              GT2 (Python repos)
    corpus/labels/<repo>.json           hand labels (hono, zod)
    corpus/manifest.json                sha256 of every corpus file (verified on load)
    v<format>/                          every cache of one gate format:
      src/<tree>/tree_sitter_analyzer/    base snapshots extracted with ``git archive``
      index/<repo>/<index-key>/tree/      detached worktree = project root + .ast-cache
      index/<repo>/<index-key>/manifest.json
      baseline/<tree>/<index-key>/<repo>.json   answers of <tree> on that index (cache)
      results/<tree>/<index-key>/<repo>.json    head answers (promote -> baseline)
      runs/<stamp>/report.{md,json}       one directory per run, with server logs
      locks/<repo>.lock                   one index writer per repo
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOT = Path(r"C:\git-private\tsa-gate")
DEFAULT_PYTHON = Path(r"C:\git-private\tree-sitter-analyzer\.venv\Scripts\python.exe")
DOGFOOD = Path(r"C:\git-private\tsa-dogfood")

#: Bumped whenever the meaning of a cached file changes; every key includes it.
#: Format 2: query-time memos disabled in gate servers, snapshot mtimes derived
#: from the tree hash, single-process index builds, base-index comparison.
GATE_FORMAT = 2
#: Caches of this format live under ``<root>/v<format>/`` so that a gate of an
#: older format can keep running on the same root (format 1 used the root itself).
CACHE_DIR = f"v{GATE_FORMAT}"


@dataclass(frozen=True)
class RepoPin:
    name: str
    url: str
    sha: str
    lang: str  # "python" | "java" | "ts" | "js"
    seed_clone: Path  # local clone the corpus was built from (object source)

    @property
    def is_python(self) -> bool:
        return self.lang == "python"


REPOS: dict[str, RepoPin] = {
    pin.name: pin
    for pin in (
        RepoPin(
            "rich",
            "https://github.com/Textualize/rich",
            "9d8f9a372cc5916fd4781fec207ced7ddac2f08f",
            "python",
            DOGFOOD / "r10" / "repos" / "rich",
        ),
        RepoPin(
            "pydantic",
            "https://github.com/pydantic/pydantic",
            "e3b6f55a8c778a143f3ae3ddb0f7bc4d67795dc3",
            "python",
            DOGFOOD / "r10" / "repos" / "pydantic",
        ),
        RepoPin(
            "fastapi",
            "https://github.com/fastapi/fastapi",
            "b2ce629ace6bdd152d577e5f5e256a079ac1e4fd",
            "python",
            DOGFOOD / "r10" / "repos" / "fastapi",
        ),
        RepoPin(
            "axios",
            "https://github.com/axios/axios",
            "fceeb10997ea71778ad8bc9671ad53e9195a707c",
            "js",
            DOGFOOD / "r10" / "repos" / "axios",
        ),
        RepoPin(
            "gson",
            "https://github.com/google/gson",
            "e2292f9c9f2e07a4791827e8eea34aa7d80545d6",
            "java",
            DOGFOOD / "r10" / "repos" / "gson",
        ),
        RepoPin(
            "hono",
            "https://github.com/honojs/hono",
            "5ca49b0720755c585c9a9835f0a479ceea36fb52",
            "ts",
            DOGFOOD / "ts1" / "repos" / "hono",
        ),
        RepoPin(
            "zod",
            "https://github.com/colinhacks/zod",
            "afdac65e0f80c0ccf9e8909da97c411567908b57",
            "ts",
            DOGFOOD / "ts1" / "repos" / "zod",
        ),
    )
}

#: Source files per language for the grep oracle (``git grep`` pathspecs).
LANG_EXTS: dict[str, tuple[str, ...]] = {
    "python": (".py", ".pyi"),
    "java": (".java",),
    "js": (".js", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".jsx"),
    "ts": (".ts", ".tsx", ".mts", ".cts", ".js", ".mjs", ".cjs", ".jsx"),
}

#: Corpus sources copied by ``setup`` (read-only inputs, never modified).
R15_ANSWERS = DOGFOOD / "r15" / "analysis-complete-rate" / "answers.json"
GT2_SOURCE = {
    name: DOGFOOD / "r10" / name / "gt-gt2.json"
    for name in ("rich", "pydantic", "fastapi")
}
LABEL_SOURCE = {
    name: DOGFOOD / "r15" / name / "gt-labels.json" for name in ("hono", "zod")
}

#: Query form, identical to the PR-1/2/4 manual gates.
QUERY_ARGS = {"action": "callers", "include_bodies": False, "limit": 5000}
#: ``workers=1``: the build runs in the audited process (no spawn pool, see ``_boot``).
INDEX_ARGS = {"action": "full", "mode": "full", "workers": 1}


@dataclass(frozen=True)
class Layout:
    root: Path

    @classmethod
    def from_env(cls, root: str | os.PathLike[str] | None = None) -> Layout:
        value = root or os.environ.get("TSA_GATE_ROOT") or DEFAULT_ROOT
        return cls(Path(value).resolve())

    @property
    def config(self) -> Path:
        return self.root / "config.json"

    def repo(self, name: str) -> Path:
        return self.root / "repos" / name

    @property
    def corpus(self) -> Path:
        return self.root / "corpus"

    def targets(self, name: str) -> Path:
        return self.corpus / "targets" / f"{name}.json"

    def gt2(self, name: str) -> Path:
        return self.corpus / "gt2" / f"{name}.json"

    def labels(self, name: str) -> Path:
        return self.corpus / "labels" / f"{name}.json"

    @property
    def cache(self) -> Path:
        """Root of every cache of the current format (``<root>/v<format>``)."""
        return self.root / CACHE_DIR

    def src(self, tree: str) -> Path:
        return self.cache / "src" / tree

    def index_root(self, name: str) -> Path:
        return self.cache / "index" / name

    def index_dir(self, name: str, key: str) -> Path:
        return self.index_root(name) / key

    def baseline(self, tree: str, key: str, name: str) -> Path:
        return self.cache / "baseline" / tree / key / f"{name}.json"

    def results_dir(self, tree: str) -> Path:
        return self.cache / "results" / tree

    def result(self, tree: str, key: str, name: str) -> Path:
        return self.results_dir(tree) / key / f"{name}.json"

    @property
    def runs(self) -> Path:
        return self.cache / "runs"

    def lock(self, name: str) -> Path:
        return self.cache / "locks" / f"{name}.lock"
