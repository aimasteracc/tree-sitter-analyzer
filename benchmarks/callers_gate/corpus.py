"""``setup``: the persistent corpus (pinned repos + targets + ground truth) and its checks."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from . import gitutil
from .layout import GT2_SOURCE, LABEL_SOURCE, R15_ANSWERS, REPOS, Layout, RepoPin


class CorpusError(RuntimeError):
    """The corpus is missing or does not match its manifest (fail closed)."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def r15_targets(answers: list[dict[str, Any]], repo: str) -> list[dict[str, Any]]:
    """The per-repo target list exactly as the PR-1/2/4 manual gates built it."""
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for answer in answers:
        if answer["repo"] != repo:
            continue
        target = answer["target"]
        if answer["mode"] == "qualified":
            name = target["qual"]
        else:
            name = target.get("name") or target["qual"].rsplit(".", 1)[-1]
        key = (answer["mode"], target["file"], target["qual"])
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "mode": answer["mode"],
                "file": target["file"],
                "qual": target["qual"],
                "name": name,
                "r15": answer["completeness"],
            }
        )
    return out


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


def copy_corpus(layout: Layout, log: Any = print) -> dict[str, str]:
    """Copy the read-only corpus inputs and return ``relative path -> sha256``."""
    answers = json.loads(R15_ANSWERS.read_text(encoding="utf-8"))
    manifest: dict[str, str] = {}
    for name in REPOS:
        rows = r15_targets(answers, name)
        if not rows:
            raise CorpusError(f"no r15 targets for {name}")
        path = layout.targets(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, indent=0), encoding="utf-8")
        log(f"[setup] targets {name}: {len(rows)}")
    for name, src in GT2_SOURCE.items():
        dst = layout.gt2(name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    for name, src in LABEL_SOURCE.items():
        dst = layout.labels(name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    for path in sorted(layout.corpus.rglob("*.json")):
        if path.name == "manifest.json":
            continue
        manifest[path.relative_to(layout.corpus).as_posix()] = sha256_file(path)
    (layout.corpus / "manifest.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8"
    )
    return manifest


def verify_corpus(layout: Layout) -> dict[str, str]:
    """Manifest entries after checking every file against it; raises on any drift."""
    path = layout.corpus / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CorpusError(f"corpus manifest unreadable ({path}): run setup") from exc
    if not isinstance(manifest, dict) or not manifest:
        raise CorpusError("corpus manifest empty: run setup")
    for rel, digest in manifest.items():
        file = layout.corpus / rel
        if not file.is_file():
            raise CorpusError(f"corpus file missing: {file}")
        if sha256_file(file) != digest:
            raise CorpusError(f"corpus file changed since setup: {file}")
    return manifest


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
    for pin in REPOS.values():
        clone_repo(layout, pin, log)
    manifest = copy_corpus(layout, log)
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
