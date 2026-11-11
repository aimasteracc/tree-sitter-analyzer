"""``setup``: the persistent corpus (pinned repos + targets + ground truth) and its checks.

The targets, the hand labels and the manifest are versioned in
``benchmarks/callers_gate/corpus_data/`` byte for byte; ``setup`` installs them
into ``<root>/corpus/``. GT2 is not versioned (~39 MB): the versioned manifest
pins its digests and ``setup`` accepts only a gate-root copy that matches.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from . import gitutil
from .layout import REPOS, VERSIONED_CORPUS, Layout, RepoPin


class CorpusError(RuntimeError):
    """The corpus is missing or does not match its manifest (fail closed)."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def clone_repo(layout: Layout, pin: RepoPin, log: Any = print) -> None:
    dest = layout.repo(pin.name)
    if dest.is_dir():
        have = gitutil.git(dest, "cat-file", "-t", pin.sha).strip()
        if have != "commit":
            raise CorpusError(f"{dest} lacks pinned commit {pin.sha}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = str(pin.seed_clone) if pin.seed_clone.is_dir() else pin.url
    log(f"[setup] clone {pin.name} from {source}")
    subprocess.run(["git", "clone", "--bare", "--quiet", source, str(dest)], check=True)
    gitutil.git(dest, "remote", "set-url", "origin", pin.url)
    try:
        gitutil.git(dest, "cat-file", "-t", pin.sha)
    except gitutil.GitError:
        gitutil.git(dest, "fetch", "--quiet", "origin", pin.sha)
    gitutil.git(dest, "update-ref", "refs/callers-gate/pin", pin.sha)


def versioned_manifest(source: Path | None = None) -> dict[str, str]:
    """The versioned manifest, after checking every versioned file against it.

    GT2 entries name files that are not versioned (too large); only their
    digests are pinned here, and :func:`install_corpus` enforces them.
    """
    source = source or VERSIONED_CORPUS
    path = source / "manifest.json"
    try:
        manifest = json.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise CorpusError(
            f"versioned corpus manifest unreadable ({path}): this checkout lacks "
            "benchmarks/callers_gate/corpus_data/"
        ) from exc
    if not isinstance(manifest, dict) or not manifest:
        raise CorpusError(f"versioned corpus manifest empty: {path}")
    for rel, digest in manifest.items():
        file = source / rel
        if file.is_file() and sha256_file(file) != digest:
            raise CorpusError(f"versioned corpus file changed: {file}")
        if not file.is_file() and not rel.startswith("gt2/"):
            raise CorpusError(f"versioned corpus file missing: {file}")
    return manifest


def _gt2_missing(rel: str, dst: Path, digest: str, state: str) -> CorpusError:
    return CorpusError(
        f"{rel}: the gate-root copy {dst} {state}, and GT2 is not reproducible "
        f"from this repo (its generator was a dogfood harness, see "
        f"docs/dev/callers-gate.md#ground-truth). Restore the file with sha256 "
        f"{digest} from a backup of a gate root."
    )


def install_corpus(
    layout: Layout, log: Any = print, source: Path | None = None
) -> dict[str, str]:
    """Bring ``<root>/corpus/`` to exactly the versioned corpus; return its manifest.

    A gate-root file whose digest matches is kept untouched; a missing or
    edited targets / labels file is copied from the versioned corpus. GT2 must
    already be in the gate root with the pinned digest. Every file is checked
    before anything is written, so a failure leaves the gate root as it was.
    """
    source = source or VERSIONED_CORPUS
    manifest = versioned_manifest(source)
    copies: list[tuple[Path, Path]] = []
    for rel, digest in sorted(manifest.items()):
        dst = layout.corpus / rel
        if dst.is_file() and sha256_file(dst) == digest:
            continue
        src = source / rel
        if src.is_file():
            copies.append((src, dst))
            continue
        state = "differs from the pinned digest" if dst.is_file() else "is missing"
        raise _gt2_missing(rel, dst, digest, state)
    for src, dst in copies:
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(f"{dst.name}.{os.getpid()}.tmp")
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
        log(f"[setup] copied {dst.relative_to(layout.corpus).as_posix()}")
    target = layout.corpus / "manifest.json"
    wanted = (source / "manifest.json").read_bytes()
    if not target.is_file() or target.read_bytes() != wanted:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(wanted)
    return manifest


def verify_corpus(
    layout: Layout, expected: dict[str, str] | None = None
) -> dict[str, str]:
    """Manifest entries after checking every file against it; raises on any drift.

    With ``expected`` (the versioned manifest), the gate-root manifest must
    also be exactly that one.
    """
    path = layout.corpus / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CorpusError(f"corpus manifest unreadable ({path}): run setup") from exc
    if not isinstance(manifest, dict) or not manifest:
        raise CorpusError("corpus manifest empty: run setup")
    if expected is not None and manifest != expected:
        differ = sorted(
            rel
            for rel in set(manifest) | set(expected)
            if manifest.get(rel) != expected.get(rel)
        )
        raise CorpusError(
            f"gate-root corpus {path} differs from the versioned corpus "
            f"(benchmarks/callers_gate/corpus_data) in {differ}: run setup"
        )
    for rel, digest in manifest.items():
        file = layout.corpus / rel
        if not file.is_file():
            raise CorpusError(f"corpus file missing: {file}")
        if sha256_file(file) != digest:
            raise CorpusError(f"corpus file changed since setup: {file}")
    return manifest


def verify_gate_corpus(layout: Layout) -> dict[str, str]:
    """:func:`verify_corpus` against the corpus versioned in this checkout."""
    return verify_corpus(layout, expected=versioned_manifest())


def load_targets(
    layout: Layout, repo: str, manifest: dict[str, str]
) -> tuple[list[dict[str, Any]], str]:
    rel = f"targets/{repo}.json"
    if rel not in manifest:
        raise CorpusError(f"no targets for {repo} in the corpus manifest")
    rows = json.loads(layout.targets(repo).read_text(encoding="utf-8"))
    return rows, manifest[rel]


def load_json_truth(path: Path, manifest: dict[str, str], layout: Layout) -> Any:
    """GT2 / labels, verified against the manifest; a missing file is an error."""
    rel = path.relative_to(layout.corpus).as_posix()
    if rel not in manifest or not path.is_file():
        raise CorpusError(f"ground truth missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def setup(layout: Layout, python: Path, log: Any = print) -> None:
    layout.root.mkdir(parents=True, exist_ok=True)
    if not python.is_file():
        raise CorpusError(f"gate interpreter not found: {python}")
    manifest = install_corpus(layout, log)
    for pin in REPOS.values():
        clone_repo(layout, pin, log)
    config = {
        "python": str(python),
        "corpus_files": len(manifest),
        "repos": {p.name: p.sha for p in REPOS.values()},
    }
    layout.config.write_text(json.dumps(config, indent=1), encoding="utf-8")
    log(
        f"[setup] corpus ok: {len(manifest)} files, {len(REPOS)} repos under {layout.root}"
    )


def load_config(layout: Layout) -> dict[str, Any]:
    try:
        data = json.loads(layout.config.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CorpusError(f"{layout.config} unreadable: run setup first") from exc
    if not isinstance(data, dict) or "python" not in data:
        raise CorpusError(f"{layout.config} malformed: run setup again")
    return data
