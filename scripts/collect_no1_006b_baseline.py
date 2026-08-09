#!/usr/bin/env python3
# ruff: noqa: E701, E702, UP022
# fmt: off
"""Collect the NO1-006B offline, lock-pinned macOS E0 receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import selectors
import signal
import stat
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPECTED_SUBJECT_COMMIT = "7e0e8f6e03270fcbf4025d717415ef69c9354145"
ROOT_NAME = "tree-sitter-analyzer"
SCHEMA = Path(__file__).parents[1] / "schemas/no1-006b-baseline.schema.json"
EXPECTED_MCP_TOOLS = sorted(["edit", "health", "index", "nav", "project", "search", "set_project_path", "structure", "viz"])
MAX_CAPTURE_BYTES = 8 * 1024 * 1024
MAX_FRAME_BYTES = 2 * 1024 * 1024
MAX_DISTRIBUTIONS = 256
MAX_FILES = 100_000


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_env() -> dict[str, str]:
    keep = {key: os.environ[key] for key in ("HOME", "PATH", "TMPDIR", "UV_CACHE_DIR") if key in os.environ}
    return {**keep, "UV_OFFLINE": "1", "PYTHONDONTWRITEBYTECODE": "1", "LC_ALL": "C", "LANG": "C"}


def run(command: list[str], *, cwd: Path, timeout: int = 180) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(command, cwd=cwd, env=clean_env(), capture_output=True, timeout=timeout, start_new_session=True)
    if len(result.stdout) + len(result.stderr) > MAX_CAPTURE_BYTES:
        raise RuntimeError(f"subprocess output exceeded {MAX_CAPTURE_BYTES} bytes")
    if result.returncode:
        detail = result.stderr[-4096:].decode(errors="replace")
        raise RuntimeError(f"command failed ({result.returncode}): {command!r}: {detail}")
    return result


def git(repo: Path, *args: str) -> bytes:
    return run(["git", *args], cwd=repo, timeout=60).stdout


def require_clean_subject(repo: Path, expected_commit: str) -> dict[str, str]:
    commit = git(repo, "rev-parse", "HEAD").decode().strip()
    if commit != expected_commit:
        raise RuntimeError(f"expected subject commit {expected_commit}, found {commit}")
    status = git(repo, "status", "--porcelain=v1", "--untracked-files=all", "--ignored").decode()
    if status:
        raise RuntimeError(f"subject worktree contains tracked, untracked, or ignored entries: {status[:500]}")
    lock = repo / "uv.lock"
    if not lock.is_file() or lock.is_symlink():
        raise RuntimeError("subject uv.lock must be a regular non-symlink file")
    return {"commit": commit, "git_tree": git(repo, "rev-parse", "HEAD^{tree}").decode().strip(),
            "lock_sha256": sha256(lock)}


def collector_identity() -> dict[str, str]:
    script = Path(__file__).resolve()
    root = script.parents[1]
    relative = script.relative_to(root).as_posix()
    status = git(root, "status", "--porcelain=v1", "--untracked-files=all").decode()
    if status:
        raise RuntimeError("collector worktree must be clean; commit protocol changes before collection")
    commit = git(root, "rev-parse", "HEAD").decode().strip()
    tracked = git(root, "ls-files", "--error-unmatch", relative).decode().strip()
    if tracked != relative or git(root, "show", f"HEAD:{relative}") != script.read_bytes():
        raise RuntimeError("collector script is not the exact version stored at collector HEAD")
    schema_rel = SCHEMA.resolve().relative_to(root).as_posix()
    if git(root, "show", f"HEAD:{schema_rel}") != SCHEMA.read_bytes():
        raise RuntimeError("schema is not the exact version stored at collector HEAD")
    return {"commit": commit, "script_sha256": sha256(script), "schema_sha256": sha256(SCHEMA)}


def source_archive_sha(repo: Path, destination: Path) -> str:
    run(["git", "archive", "--format=tar", "HEAD", "-o", str(destination)], cwd=repo)
    return sha256(destination)


def export_closure(repo: Path, destination: Path) -> str:
    result = run(["uv", "export", "--frozen", "--offline", "--no-dev", "--no-emit-project",
                  "--format", "requirements-txt"], cwd=repo)
    text = result.stdout
    if b"--hash=sha256:" not in text or b"==" not in text:
        raise RuntimeError("uv frozen export did not produce hashed exact requirements")
    destination.write_bytes(text)
    return digest_bytes(text)


def python_path(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def executable(venv: Path, name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return venv / ("Scripts" if os.name == "nt" else "bin") / f"{name}{suffix}"


def install_environment(repo: Path, venv: Path, requirements: Path, wheel: Path) -> Path:
    python_spec = os.environ.get("NO1_006B_PYTHON", "3.14")
    run(["uv", "venv", str(venv), "--python", python_spec, "--offline"], cwd=repo)
    python = python_path(venv)
    run(["uv", "pip", "install", "--python", str(python), "--offline", "--no-deps",
         "--require-hashes", "-r", str(requirements)], cwd=repo)
    run(["uv", "pip", "install", "--python", str(python), "--offline", "--no-deps", str(wheel)], cwd=repo)
    return python


INVENTORY_CODE = r"""import importlib.metadata as m, json, os, stat
from pathlib import Path
root_name="tree-sitter-analyzer"; root=m.distribution(root_name); dists={}
for dist in m.distributions():
 name=dist.metadata.get("Name") or ""
 if not name or name in dists: raise RuntimeError(f"missing or duplicate distribution: {name!r}")
 dists[name] = dist.version
if len(dists)>256: raise RuntimeError("distribution limit exceeded")
venv=Path(os.environ["VIRTUAL_ENV"]).resolve(); seen_paths=set(); seen_inodes=set(); total=0; files=0
for dist in m.distributions():
 for item in dist.files or []:
  if item.name=="direct_url.json" or item.suffix==".pyc": continue
  raw=Path(dist.locate_file(item)); resolved=raw.resolve(strict=True)
  if not resolved.is_relative_to(venv): raise RuntimeError(f"distribution file escapes venv: {raw}")
  if raw.is_symlink(): raise RuntimeError(f"distribution file is symlink: {raw}")
  st=raw.stat(follow_symlinks=False)
  if not stat.S_ISREG(st.st_mode): continue
  files += 1
  if files>100000: raise RuntimeError("distribution file limit exceeded")
  path_key=str(resolved); inode=(st.st_dev,st.st_ino)
  if path_key in seen_paths or inode in seen_inodes: continue
  seen_paths.add(path_key); seen_inodes.add(inode); total += st.st_size
print(json.dumps({"versions":dists,"requires":root.requires or [],"installed_size_bytes":total,"regular_file_count":len(seen_paths)}))"""


def inventory(python: Path, cwd: Path) -> dict[str, Any]:
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    raw=json.loads(run([str(python), "-c", INVENTORY_CODE], cwd=cwd).stdout)
    env=default_environment(); env["extra"]=""; direct=set()
    for value in raw.pop("requires"):
        requirement=Requirement(value)
        if requirement.marker is None or requirement.marker.evaluate(env):
            direct.add(canonicalize_name(requirement.name))
    versions={canonicalize_name(name):version for name,version in raw.pop("versions").items()}
    if len(versions) != len(set(versions)) or ROOT_NAME not in versions or not direct.issubset(versions):
        raise RuntimeError("canonical distribution inventory is inconsistent")
    raw["distributions"]=[{"name":name,"version":versions[name],"role":("root" if name==ROOT_NAME else "direct" if name in direct else "transitive")} for name in sorted(versions)]
    return raw


def cli_sample(program: Path, fixture_dir: Path) -> float:
    started = time.perf_counter_ns()
    result = run([str(program), "fixture.py", "--summary", "--format", "json"], cwd=fixture_dir, timeout=30)
    elapsed = round((time.perf_counter_ns() - started) / 1_000_000, 3)
    payload = json.loads(result.stdout)
    methods = payload.get("summary", {}).get("methods", [])
    if payload.get("success") is not True or payload.get("language") != "python" or [m.get("name") for m in methods] != ["add"]:
        raise RuntimeError("CLI probe did not return the exact deterministic analysis result")
    return elapsed


def terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try: os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError): process.kill()
        process.wait(timeout=3)


def read_json_frame(process: subprocess.Popen[bytes], deadline: float) -> dict[str, Any]:
    assert process.stdout is not None
    selector = selectors.DefaultSelector(); selector.register(process.stdout, selectors.EVENT_READ)
    buffer = bytearray()
    try:
        while time.monotonic() < deadline:
            events = selector.select(max(0, deadline - time.monotonic()))
            if not events: break
            block = os.read(process.stdout.fileno(), min(65536, MAX_FRAME_BYTES + 1 - len(buffer)))
            if not block: raise RuntimeError("MCP stdout closed before a complete frame")
            buffer.extend(block)
            if len(buffer) > MAX_FRAME_BYTES: raise RuntimeError("MCP response frame exceeded byte limit")
            if b"\n" in buffer:
                line, remainder = bytes(buffer).split(b"\n", 1)
                if remainder.strip(): raise RuntimeError("MCP emitted unexpected extra frame bytes")
                return json.loads(line)
    finally:
        selector.close()
    raise TimeoutError("MCP response frame exceeded absolute deadline")


def mcp_sample(program: Path, project_root: Path) -> tuple[float, list[str]]:
    started = time.perf_counter_ns()
    process = subprocess.Popen([str(program), "--project-root", str(project_root)], cwd=project_root,
        env=clean_env(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        start_new_session=True)
    deadline = time.monotonic() + 30
    try:
        assert process.stdin is not None
        initialize={"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"no1-006b","version":"2"}}}
        process.stdin.write(json.dumps(initialize,separators=(",",":")).encode()+b"\n"); process.stdin.flush()
        response=read_json_frame(process,deadline)
        if response.get("id") != 1 or "result" not in response: raise RuntimeError("MCP initialize failed")
        process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        process.stdin.write(b'{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n'); process.stdin.flush()
        response=read_json_frame(process,deadline)
        names=sorted(tool.get("name") for tool in response.get("result",{}).get("tools",[]))
        if response.get("id") != 2 or names != EXPECTED_MCP_TOOLS: raise RuntimeError(f"unexpected MCP tool surface: {names}")
        return round((time.perf_counter_ns()-started)/1_000_000,3), names
    finally:
        terminate(process)


def canonical_hash(report: dict[str, Any]) -> str:
    body=dict(report); body.pop("canonical_payload_sha256",None)
    return digest_bytes(json.dumps(body,sort_keys=True,separators=(",",":")).encode())


def validate_receipt(report: dict[str, Any], schema: dict[str, Any] | None = None) -> None:
    if schema is not None:
        from jsonschema import Draft202012Validator, FormatChecker
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(report)
    m=report["measurements"]; closure=report["dependency_closure"]; distributions=closure["distributions"]
    roles=[row["role"] for row in distributions]; names=[row["name"] for row in distributions]
    started=datetime.fromisoformat(report["collection_started_at_utc"].replace("Z","+00:00"))
    finished=datetime.fromisoformat(report["collection_finished_at_utc"].replace("Z","+00:00"))
    checks=[len(m["cli_startup"]["warm_ms"])==report["repeats"], len(m["mcp_startup"]["warm_ms"])==report["repeats"],
            m["direct_dependency_count"]==roles.count("direct"), m["transitive_dependency_count"]==roles.count("transitive"),
            m["installed_distribution_count_including_root"]==len(distributions), roles.count("root")==1,
            m["dependency_distribution_count_excluding_root"]==roles.count("direct")+roles.count("transitive"),
            report["source"]["root_wheel_artifact_size_bytes"]==m["root_wheel_artifact_size_bytes"],
            closure["lock_sha256"]==report["source"]["lock_sha256"], len(names)==len(set(names)), names==sorted(names),
            report["environment"]["system"]==report["measured_axis"],
            report["canonical_payload_sha256"]==canonical_hash(report), started.tzinfo is not None, finished.tzinfo is not None,
            started <= finished]
    if not all(checks): raise ValueError("receipt cross-field consistency check failed")


def safe_write(output: Path, data: bytes, subject: Path) -> None:
    if subject.resolve() == output.resolve() or subject.resolve() in output.resolve().parents:
        raise ValueError("output must be outside the measured subject repository")
    parent=output.parent
    if not parent.exists(): raise ValueError("output parent must already exist")
    current=parent
    while True:
        if stat.S_ISLNK(current.lstat().st_mode): raise ValueError("output parent chain must not contain symlinks")
        if current == current.parent: break
        current=current.parent
    if output.exists() and output.is_symlink(): raise ValueError("output must not be a symlink")
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0)
    temp=parent/f".{output.name}.{os.getpid()}.tmp"
    fd=os.open(temp,flags,0o600)
    try:
        with os.fdopen(fd,"wb",closefd=True) as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp,output)
        directory=os.open(parent,os.O_RDONLY); os.fsync(directory); os.close(directory)
    finally:
        if temp.exists(): temp.unlink()


def collect(repo: Path, output: Path, repeats: int, expected_commit: str) -> dict[str, Any]:
    if platform.system() != "Darwin": raise RuntimeError("this collector currently emits only macOS measured_e0")
    if repeats not in range(3,21): raise ValueError("repeats must be between 3 and 20")
    repo=repo.resolve(); started=datetime.now(timezone.utc).isoformat(); subject=require_clean_subject(repo,expected_commit)
    collector=collector_identity()
    with tempfile.TemporaryDirectory(prefix="no1-006b-") as raw:
        temp=Path(raw); dist=temp/"dist"; dist.mkdir(); requirements=temp/"locked-requirements.txt"
        subject["source_archive_sha256"]=source_archive_sha(repo,temp/"source.tar")
        export_sha=export_closure(repo,requirements)
        run(["uv","build","--wheel","--offline","--out-dir",str(dist)],cwd=repo)
        wheels=list(dist.glob("*.whl"))
        if len(wheels)!=1: raise RuntimeError(f"expected exactly one root wheel, found {len(wheels)}")
        wheel=wheels[0]
        fixture=temp/"fixture"; fixture.mkdir(); (fixture/"fixture.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n")
        samples={}; inventories=[]; tool_names=None; py_info=None
        for kind in ("cli","mcp"):
            python=install_environment(repo,temp/f"{kind}-venv",requirements,wheel)
            inventories.append(inventory(python,repo))
            if py_info is None:
                py_info=json.loads(run([str(python),"-c","import json,platform;print(json.dumps({'version':platform.python_version(),'implementation':platform.python_implementation()}))"],cwd=repo).stdout)
            if kind=="cli": samples[kind]=[cli_sample(executable(python.parent.parent,"tree-sitter-analyzer"),fixture) for _ in range(repeats+1)]
            else:
                results=[mcp_sample(executable(python.parent.parent,"tree-sitter-analyzer-mcp"),fixture) for _ in range(repeats+1)]
                samples[kind]=[r[0] for r in results]; tool_names=results[0][1]
        if inventories[0] != inventories[1]: raise RuntimeError("fresh CLI/MCP environments have different installed closures")
        inv=inventories[0]; rows=inv["distributions"]; roles=[r["role"] for r in rows]; finished=datetime.now(timezone.utc).isoformat()
        report={"schema_version":2,"roadmap_id":"NO1-006B","evidence_level":"E0",
          "collection_started_at_utc":started,"collection_finished_at_utc":finished,"collector":collector,
          "source":{**subject,"root_wheel_filename":wheel.name,"root_wheel_sha256":sha256(wheel),"root_wheel_artifact_size_bytes":wheel.stat().st_size},
          "dependency_closure":{"derivation":"uv.lock frozen export; hashed exact requirements; project wheel installed separately with --no-deps","export_sha256":export_sha,"lock_sha256":subject["lock_sha256"],"distributions":rows},
          "environment":{"os":platform.platform(),"system":"macos","machine":platform.machine(),"python":py_info,"uv":run(["uv","--version"],cwd=repo).stdout.decode().strip(),"network_policy":"UV_OFFLINE=1; uv --offline; no network transfer measurement","bytecode_policy":"PYTHONDONTWRITEBYTECODE=1","cache_protocol":"two independent fresh identical venvs; first sample bytecode-cold but OS cache uncontrolled; subsequent samples fresh-process warm"},
          "measurements":{"root_wheel_artifact_size_bytes":wheel.stat().st_size,"network_transfer_bytes":{"status":"unknown","reason":"offline cache artifacts do not measure network transfer"},"installed_size_bytes":inv["installed_size_bytes"],"installed_regular_file_count":inv["regular_file_count"],"installed_size_scope":"unique resolved in-venv regular files; pyc/direct_url excluded; symlinks rejected; hardlinks inode-deduplicated; interpreter excluded","direct_dependency_count":roles.count("direct"),"transitive_dependency_count":roles.count("transitive"),"dependency_distribution_count_excluding_root":len(rows)-1,"installed_distribution_count_including_root":len(rows),"cli_startup":{"definition":"clock before Popen through exact successful JSON analysis of fixture.py","cold_ms":samples["cli"][0],"warm_ms":samples["cli"][1:]},"mcp_startup":{"definition":"clock before Popen through successful initialize, initialized notification, and exact tools/list readiness","cold_ms":samples["mcp"][0],"warm_ms":samples["mcp"][1:],"tool_names":tool_names}},
          "commands":{"export":["uv","export","--frozen","--offline","--no-dev","--no-emit-project","--format","requirements-txt"],"build":["uv","build","--wheel","--offline","--out-dir","<temp>/dist"],"closure_install":["uv","pip","install","--offline","--no-deps","--require-hashes","-r","<locked-requirements>"],"root_install":["uv","pip","install","--offline","--no-deps","<root-wheel>"],"cli_probe":["tree-sitter-analyzer","fixture.py","--summary","--format","json"],"mcp_probe":["tree-sitter-analyzer-mcp","--project-root","<fixture>","initialize","notifications/initialized","tools/list"]},
          "repeats":repeats,"measured_axis":"macos","platform_axes":{"macos":"measured_e0","linux":"unknown","windows":"unknown"}}
        report["canonical_payload_sha256"]=canonical_hash(report); validate_receipt(report)
        safe_write(output, (json.dumps(report,indent=2,sort_keys=True)+"\n").encode(), repo); return report


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--repo",type=Path,required=True); parser.add_argument("--output",type=Path,required=True); parser.add_argument("--repeats",type=int,default=5); parser.add_argument("--expected-commit",default=EXPECTED_SUBJECT_COMMIT)
    args=parser.parse_args(); collect(args.repo,args.output,args.repeats,args.expected_commit); return 0

if __name__ == "__main__": raise SystemExit(main())
# fmt: on
