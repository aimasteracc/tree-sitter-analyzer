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
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPECTED_SUBJECT_COMMIT = "7e0e8f6e03270fcbf4025d717415ef69c9354145"
EXPECTED_SUBJECT_TREE = "fe340eff33002b67ae88b34f1174bbcca4efc370"
EXPECTED_SUBJECT_LOCK_SHA256 = "516430f61ddff1d9a4436409822d7b12aa6d6c9cc0a7b6fc3fa7085639dc0909"
ROOT_NAME = "tree-sitter-analyzer"
TOOL_GROUP = "no1-006b-collector-tool"
HATCHLING_VERSION = "1.31.0"
EXPECTED_UV_VERSION = "uv 0.12.3 (507230998 2026-08-07 aarch64-apple-darwin)"
EXPECTED_UV_SHA256 = "2b4ccdac26598ca8c300e5c36d24297fa1471c350c46d2f34c835bf06be303ab"
SCHEMA = Path(__file__).parents[1] / "schemas/no1-006b-baseline.schema.json"
EXPECTED_MCP_TOOLS = sorted(["edit", "health", "index", "nav", "project", "search", "set_project_path", "structure", "viz"])
MAX_CAPTURE_BYTES = 8 * 1024 * 1024
MAX_FRAME_BYTES = 2 * 1024 * 1024
MAX_DISTRIBUTIONS = 256
MAX_FILES = 100_000
MAX_SOURCE_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_REQUIREMENTS_BYTES = 8 * 1024 * 1024
MAX_ROOT_WHEEL_BYTES = 128 * 1024 * 1024
CLI_STARTUP_DEFINITION = "clock before Popen through exact successful JSON analysis of fixture.py"
MCP_STARTUP_DEFINITION = "clock before Popen through successful initialize, initialized notification, and exact tools/list readiness"
SAMPLE_ORDER = "all CLI samples, then all MCP samples"


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_file_budget(path: Path, maximum: int, label: str) -> None:
    size=path.stat().st_size
    if size>maximum: raise RuntimeError(f"{label} exceeded {maximum} byte disk budget: {size}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    # Fail closed against user/project uv configuration. UV_CACHE_DIR is the only
    # inherited UV_* input: it selects already-downloaded offline artifacts, not
    # resolution or index policy.
    keep = {key: os.environ[key] for key in ("HOME", "PATH", "TMPDIR", "UV_CACHE_DIR") if key in os.environ}
    clean = {**keep, "UV_NO_CONFIG": "1", "UV_OFFLINE": "1", "PYTHONDONTWRITEBYTECODE": "1", "LC_ALL": "C", "LANG": "C",
             "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    for key,value in (overrides or {}).items():
        if key.startswith("UV_"): raise ValueError(f"uv environment override is not allowed: {key}")
        clean[key]=value
    return clean


def run(command: list[str], *, cwd: Path, timeout: int = 180, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    process=subprocess.Popen(command,cwd=cwd,env=clean_env(env_overrides),stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    assert process.stdout is not None and process.stderr is not None
    selector=selectors.DefaultSelector(); selector.register(process.stdout,selectors.EVENT_READ,"stdout"); selector.register(process.stderr,selectors.EVENT_READ,"stderr")
    buffers={"stdout":bytearray(),"stderr":bytearray()}; deadline=time.monotonic()+timeout
    try:
        while selector.get_map() and time.monotonic()<deadline:
            for key,_ in selector.select(max(0,deadline-time.monotonic())):
                block=os.read(key.fileobj.fileno(),65536)
                if not block: selector.unregister(key.fileobj); continue
                buffers[key.data].extend(block)
                if sum(map(len,buffers.values()))>MAX_CAPTURE_BYTES: raise RuntimeError(f"subprocess output exceeded {MAX_CAPTURE_BYTES} bytes")
        if selector.get_map(): raise TimeoutError(f"command exceeded {timeout} seconds")
        returncode=process.wait(timeout=3)
    except BaseException:
        try: os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        process.wait(timeout=3); raise
    finally: selector.close()
    result=subprocess.CompletedProcess(command,returncode,bytes(buffers["stdout"]),bytes(buffers["stderr"]))
    if result.returncode:
        detail=result.stderr[-4096:].decode(errors="replace")
        raise RuntimeError(f"command failed ({result.returncode}): {command!r}: {detail}")
    return result


def git(repo: Path, *args: str) -> bytes:
    return run(["git", *args], cwd=repo, timeout=60).stdout


def bounded_git(repo: Path, *args: str, timeout: int = 60) -> bytes:
    # Git provenance reads must work on Windows, whose default selector cannot
    # monitor anonymous subprocess pipes. Regular temporary files also let us
    # enforce the byte ceiling while git is still running.
    with tempfile.TemporaryDirectory(prefix="no1-006b-git-") as raw:
        stdout_path=Path(raw)/"stdout"; stderr_path=Path(raw)/"stderr"
        with stdout_path.open("w+b") as stdout, stderr_path.open("w+b") as stderr:
            process=subprocess.Popen(["git",*args],cwd=repo,env=clean_env(),stdout=stdout,stderr=stderr,start_new_session=True)
            deadline=time.monotonic()+timeout
            while process.poll() is None:
                if time.monotonic() >= deadline or stdout_path.stat().st_size+stderr_path.stat().st_size > MAX_CAPTURE_BYTES:
                    process.kill(); process.wait(timeout=3)
                    if time.monotonic() >= deadline: raise TimeoutError(f"git command exceeded {timeout} seconds")
                    raise RuntimeError(f"git output exceeded {MAX_CAPTURE_BYTES} bytes")
                time.sleep(0.01)
            stdout.flush(); stderr.flush()
            if stdout_path.stat().st_size+stderr_path.stat().st_size > MAX_CAPTURE_BYTES:
                raise RuntimeError(f"git output exceeded {MAX_CAPTURE_BYTES} bytes")
            stdout.seek(0); stderr.seek(0); output=stdout.read(); detail=stderr.read()
        if process.returncode:
            raise RuntimeError(f"git command failed ({process.returncode}): {args!r}: {detail[-4096:].decode(errors='replace')}")
        return output


def bound_blob(repo: Path, commit: str, relative: str) -> bytes:
    tracked=bounded_git(repo,"ls-files","--error-unmatch","--",relative).decode().strip()
    if tracked != relative: raise RuntimeError(f"collector provenance path is not tracked: {relative}")
    return bounded_git(repo,"show",f"{commit}:{relative}")


def verified_uv() -> tuple[Path,str,str]:
    configured=os.environ.get("NO1_006B_UV")
    discovered=configured or shutil.which("uv")
    if not discovered: raise RuntimeError("trusted uv binary was not found; set NO1_006B_UV")
    candidate=Path(discovered)
    try: resolved=candidate.expanduser().resolve(strict=True)
    except (OSError,RuntimeError) as error: raise RuntimeError("trusted uv binary cannot be resolved") from error
    if not resolved.is_absolute() or not stat.S_ISREG(resolved.stat().st_mode):
        raise RuntimeError("trusted uv binary must resolve to a regular file")
    digest=sha256(resolved)
    version=run([str(resolved),"--no-config","--version"],cwd=Path(__file__).resolve().parents[1]).stdout.decode().strip()
    if version != EXPECTED_UV_VERSION or digest != EXPECTED_UV_SHA256:
        raise RuntimeError(f"trusted uv identity mismatch: version={version!r}, sha256={digest}")
    return resolved,version,digest


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
    tree = git(repo, "rev-parse", "HEAD^{tree}").decode().strip()
    if tree != EXPECTED_SUBJECT_TREE:
        raise RuntimeError(f"expected subject tree {EXPECTED_SUBJECT_TREE}, found {tree}")
    lock_sha256=digest_bytes(bound_blob(repo,commit,"uv.lock"))
    if lock_sha256 != EXPECTED_SUBJECT_LOCK_SHA256:
        raise RuntimeError(f"expected subject lock {EXPECTED_SUBJECT_LOCK_SHA256}, found {lock_sha256}")
    return {"commit":commit,"git_tree":tree,"lock_sha256":lock_sha256}


def collector_identity(tool_export_sha256: str) -> dict[str, str]:
    script = Path(__file__).resolve()
    root = script.parents[1]
    relative = script.relative_to(root).as_posix()
    status = git(root, "status", "--porcelain=v1", "--untracked-files=all", "--ignored").decode()
    if status:
        raise RuntimeError("collector worktree must be clean; commit protocol changes before collection")
    commit = git(root, "rev-parse", "HEAD").decode().strip()
    schema_rel = SCHEMA.resolve().relative_to(root).as_posix()
    lock_rel = (root/"uv.lock").relative_to(root).as_posix()
    # Hash committed blob bytes, not checkout bytes transformed by core.autocrlf.
    # The clean tracked-worktree gate above binds these blobs to the executing checkout.
    blobs={name:bound_blob(root,commit,path) for name,path in
           (("script_sha256",relative),("schema_sha256",schema_rel),("tool_lock_sha256",lock_rel))}
    return {"commit":commit,**{name:digest_bytes(blob) for name,blob in blobs.items()},
            "tool_export_sha256":tool_export_sha256}


def canonical_inventory_rows(rows: list[dict[str,str]]) -> str:
    return digest_bytes(json.dumps(rows,sort_keys=True,separators=(",",":")).encode())


def validate_collector_environment(export: bytes) -> tuple[list[dict[str,str]],str]:
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    logical=export.decode("utf-8").replace("\\\r\n"," ").replace("\\\n"," ")
    expected: dict[str,str]={}
    marker_env=default_environment(); marker_env["extra"]=""
    for line in logical.splitlines():
        stripped=line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("--hash="): continue
        if "--hash=sha256:" not in stripped: raise RuntimeError(f"collector export requirement is unhashed: {stripped}")
        requirement_text=re.sub(r"\s+--hash=sha256:[0-9a-f]+", "", stripped)
        requirement=Requirement(requirement_text)
        if requirement.url or len(requirement.specifier)!=1:
            raise RuntimeError(f"collector export contains non-exact requirement: {requirement_text}")
        spec=next(iter(requirement.specifier))
        if spec.operator != "==": raise RuntimeError(f"collector export contains non-exact requirement: {requirement_text}")
        if requirement.marker is not None and not requirement.marker.evaluate(marker_env): continue
        name=canonicalize_name(requirement.name)
        if name in expected: raise RuntimeError(f"duplicate collector export requirement: {name}")
        expected[name]=spec.version
    if not expected: raise RuntimeError("collector export selected no requirements for active environment")
    code="""import importlib.metadata as m,json,platform,sys
rows=[]
for dist in m.distributions():
 name=dist.metadata.get('Name') or ''
 rows.append({'name':name,'version':dist.version})
print(json.dumps({'executable':sys.executable,'python':platform.python_version(),'rows':rows}))"""
    active=json.loads(run([sys.executable,"-c",code],cwd=Path(__file__).parents[1]).stdout)
    installed: dict[str,str]={}
    for row in active["rows"]:
        name=canonicalize_name(row["name"])
        if not name or name in installed: raise RuntimeError(f"missing or duplicate active collector distribution: {name!r}")
        installed[name]=row["version"]
    if ROOT_NAME in installed: raise RuntimeError("project root must be absent from active collector environment")
    if installed != expected:
        missing=sorted(set(expected)-set(installed)); extra=sorted(set(installed)-set(expected))
        wrong=sorted(name for name in expected.keys() & installed.keys() if expected[name]!=installed[name])
        raise RuntimeError(f"active collector environment does not exactly match export: missing={missing}, extra={extra}, wrong_version={wrong}")
    rows=[{"name":name,"version":installed[name]} for name in sorted(installed)]
    return rows,canonical_inventory_rows(rows)


def collector_tool_export(root: Path, destination: Path, uv: Path) -> tuple[str,list[dict[str,str]],str]:
    result=run([str(uv),"export","--no-config","--frozen","--offline","--only-group",TOOL_GROUP,
                "--no-emit-project","--format","requirements-txt"],cwd=root)
    text=result.stdout
    if b"--hash=sha256:" not in text or any(name not in text for name in (b"hatchling==",b"jsonschema==",b"packaging==")):
        raise RuntimeError("collector tool export did not produce the required hashed exact closure")
    rows,inventory_sha=validate_collector_environment(text)
    destination.write_bytes(text); require_file_budget(destination,MAX_REQUIREMENTS_BYTES,"collector tool export")
    return digest_bytes(text),rows,inventory_sha


PYTHON_IDENTITY_CODE = """import json,platform,struct,sys,sysconfig
print(json.dumps({
 'version':platform.python_version(),
 'implementation':platform.python_implementation(),
 'machine':platform.machine(),
 'system':platform.system(),
 'architecture':platform.architecture()[0],
 'sysconfig_platform':sysconfig.get_platform(),
 'pointer_bits':struct.calcsize('P')*8,
 'executable':str(__import__('pathlib').Path(sys.executable).resolve()),
}))"""
NATIVE_IDENTITY_FIELDS = ("machine","system","sysconfig_platform","pointer_bits")


def python_identity(python: Path, cwd: Path, executable_provenance: str) -> dict[str, Any]:
    identity=json.loads(run([str(python),"-c",PYTHON_IDENTITY_CODE],cwd=cwd).stdout)
    resolved=python.resolve(strict=True)
    if Path(identity["executable"]).resolve(strict=True) != resolved:
        raise RuntimeError("Python identity probe executable does not match requested interpreter")
    identity["executable"]=executable_provenance
    return identity


def require_native_python_identity(collector_python: dict[str, Any], target_python: dict[str, Any]) -> None:
    mismatches={field:(collector_python[field],target_python[field]) for field in NATIVE_IDENTITY_FIELDS
                if collector_python[field] != target_python[field]}
    if mismatches:
        raise RuntimeError(f"NO1_006B_PYTHON target is not native to collector host: {mismatches}")


def build_environment() -> dict[str, Any]:
    identity=python_identity(Path(sys.executable),Path(__file__).parents[1],"<collector-sys-executable>")
    code="import importlib.metadata as m;print(m.version('hatchling'))"
    version=run([sys.executable,"-c",code],cwd=Path(__file__).parents[1]).stdout.decode().strip()
    return {"python":identity,"hatchling_version":version}


def source_archive_sha(repo: Path, destination: Path) -> str:
    run(["git", "-c", "tar.umask=000", "archive", "--format=tar", "HEAD", "-o", str(destination)], cwd=repo)
    require_file_budget(destination,MAX_SOURCE_ARCHIVE_BYTES,"source archive")
    return sha256(destination)


def assert_subject_unchanged(repo: Path, expected_commit: str, initial: dict[str,str], phase: str) -> None:
    current=require_clean_subject(repo,expected_commit)
    expected={key:initial[key] for key in ("commit","git_tree","lock_sha256")}
    if current != expected: raise RuntimeError(f"subject identity mutated during {phase}: expected={expected}, found={current}")
    with tempfile.TemporaryDirectory(prefix="no1-006b-recheck-") as raw:
        archive_sha=source_archive_sha(repo,Path(raw)/"source.tar")
    if archive_sha != initial["source_archive_sha256"]:
        raise RuntimeError(f"subject archive mutated during {phase}: expected={initial['source_archive_sha256']}, found={archive_sha}")


def export_closure(repo: Path, destination: Path, uv: Path) -> str:
    result = run([str(uv), "export", "--no-config", "--frozen", "--offline", "--no-dev", "--no-emit-project",
                  "--format", "requirements-txt"], cwd=repo)
    text = result.stdout
    if b"--hash=sha256:" not in text or b"==" not in text:
        raise RuntimeError("uv frozen export did not produce hashed exact requirements")
    destination.write_bytes(text); require_file_budget(destination,MAX_REQUIREMENTS_BYTES,"frozen requirements export")
    return digest_bytes(text)


def python_path(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def executable(venv: Path, name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return venv / ("Scripts" if os.name == "nt" else "bin") / f"{name}{suffix}"


def install_environment(repo: Path, venv: Path, requirements: Path, wheel: Path, uv: Path) -> Path:
    python_spec = os.environ.get("NO1_006B_PYTHON", "3.14")
    run([str(uv), "venv", "--no-config", str(venv), "--python", python_spec, "--offline"], cwd=repo)
    python = python_path(venv)
    run([str(uv), "pip", "install", "--no-config", "--python", str(python), "--offline", "--no-deps",
         "--require-hashes", "-r", str(requirements)], cwd=repo)
    run([str(uv), "pip", "install", "--no-config", "--python", str(python), "--offline", "--no-deps", str(wheel)], cwd=repo)
    return python


INVENTORY_CODE = r"""import importlib.metadata as m, json, os, stat, sys
from pathlib import Path
root_name="tree-sitter-analyzer"; root=m.distribution(root_name); dists={}
for dist in m.distributions():
 name=dist.metadata.get("Name") or ""
 if not name or name in dists: raise RuntimeError(f"missing or duplicate distribution: {name!r}")
 dists[name] = dist.version
if len(dists)>256: raise RuntimeError("distribution limit exceeded")
venv=Path(sys.prefix).resolve(); seen_paths=set(); seen_inodes=set(); total=0; files=0
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
TARGET_MARKER_CODE = "from packaging.markers import default_environment; import json; print(json.dumps(default_environment()))"


def inventory(python: Path, cwd: Path) -> dict[str, Any]:
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    raw=json.loads(run([str(python), "-c", INVENTORY_CODE], cwd=cwd).stdout)
    import packaging
    packaging_root=Path(packaging.__file__).resolve().parent.parent
    env=json.loads(run([str(python),"-c",TARGET_MARKER_CODE],cwd=cwd,env_overrides={"PYTHONPATH":str(packaging_root)}).stdout)
    env["extra"]=""; direct=set()
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
    payload = json.loads(result.stdout)
    methods = payload.get("summary", {}).get("methods", [])
    if payload.get("success") is not True or payload.get("language") != "python" or [m.get("name") for m in methods] != ["add"]:
        raise RuntimeError("CLI probe did not return the exact deterministic analysis result")
    return round((time.perf_counter_ns() - started) / 1_000_000, 3)


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


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA.read_text())

RFC3339_PATTERN = re.compile(
    r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})\Z"
)


def parse_rfc3339(value: str) -> datetime:
    if RFC3339_PATTERN.fullmatch(value) is None:
        raise ValueError(f"timestamp is not strict RFC 3339: {value!r}")
    parsed=datetime.fromisoformat(value[:-1]+"+00:00" if value.endswith("Z") else value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timestamp is not timezone-aware: {value!r}")
    if datetime.fromisoformat(parsed.isoformat()) != parsed:
        raise ValueError(f"timestamp does not round-trip: {value!r}")
    return parsed


def render_receipt_summary(report: dict[str, Any]) -> str:
    m=report["measurements"]; source=report["source"]
    cli=m["cli_startup"]; mcp=m["mcp_startup"]
    cli_samples=", ".join(str(value) for value in cli["warm_ms"])
    mcp_samples=", ".join(str(value) for value in mcp["warm_ms"])
    return "\n".join([
        f"Its canonical payload SHA-256 is `{report['canonical_payload_sha256']}`.",
        "",
        "| Axis | Measured value |",
        "|---|---:|",
        f"| root wheel artifact SHA-256 / bytes | `{source['root_wheel_sha256']}` / {source['root_wheel_artifact_size_bytes']:,} |",
        "| network transfer | unknown (offline measurement) |",
        f"| installed distribution files | {m['installed_size_bytes']:,} bytes across {m['installed_regular_file_count']:,} unique regular files |",
        f"| dependencies excluding root (direct + transitive) | {m['dependency_distribution_count_excluding_root']} ({m['direct_dependency_count']} + {m['transitive_dependency_count']}) |",
        f"| installed distributions including root | {m['installed_distribution_count_including_root']} |",
        f"| CLI bytecode-cold; warm samples (ms) | {cli['cold_ms']}; {cli_samples} |",
        f"| MCP protocol-ready cold; warm samples (ms) | {mcp['cold_ms']}; {mcp_samples} |",
    ])


def validate_receipt(report: dict[str, Any], schema: dict[str, Any]) -> None:
    from jsonschema import Draft202012Validator, FormatChecker
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(report)
    m=report["measurements"]; closure=report["dependency_closure"]; distributions=closure["distributions"]
    roles=[row["role"] for row in distributions]; names=[row["name"] for row in distributions]
    started=parse_rfc3339(report["collection_started_at_utc"])
    finished=parse_rfc3339(report["collection_finished_at_utc"])
    system=report["environment"]["system"]; os_label=report["environment"]["os"]
    os_consistent={"macos":os_label.startswith("macOS-"),"linux":os_label.startswith("Linux-"),"windows":os_label.startswith("Windows-")}[system]
    checks=[len(m["cli_startup"]["warm_ms"])==report["repeats"], len(m["mcp_startup"]["warm_ms"])==report["repeats"],
            m["direct_dependency_count"]==roles.count("direct"), m["transitive_dependency_count"]==roles.count("transitive"),
            m["installed_distribution_count_including_root"]==len(distributions), roles.count("root")==1,
            next((row["name"] for row in distributions if row["role"]=="root"),None)==ROOT_NAME,
            m["dependency_distribution_count_excluding_root"]==roles.count("direct")+roles.count("transitive"),
            report["source"]["root_wheel_artifact_size_bytes"]==m["root_wheel_artifact_size_bytes"],
            closure["lock_sha256"]==report["source"]["lock_sha256"], report["source"]["lock_sha256"]==EXPECTED_SUBJECT_LOCK_SHA256,
            report["source"]["git_tree"]==EXPECTED_SUBJECT_TREE,
            len(names)==len(set(names)), names==sorted(names),
            report["environment"]["system"]==report["measured_axis"], os_consistent,
            report["environment"]["uv"]=={"version":EXPECTED_UV_VERSION,"sha256":EXPECTED_UV_SHA256},
            all(report["environment"]["build_python"][field]==report["environment"]["python"][field]
                for field in ("version","implementation",*NATIVE_IDENTITY_FIELDS)),
            report["environment"]["machine"]==report["environment"]["python"]["machine"],
            report["environment"]["python"]["system"]=={"macos":"Darwin","linux":"Linux","windows":"Windows"}[system],
            report["environment"]["build_backend"]=={"name":"hatchling","version":HATCHLING_VERSION},
            report["collector"]["tool_export_sha256"]!=closure["export_sha256"],
            report["collector"]["tool_lock_sha256"]!=report["source"]["lock_sha256"],
            report["collector"]["tool_inventory_sha256"]==canonical_inventory_rows(report["collector"]["tool_inventory"]),
            [row["name"] for row in report["collector"]["tool_inventory"]]==sorted(row["name"] for row in report["collector"]["tool_inventory"]),
            ROOT_NAME not in {row["name"] for row in report["collector"]["tool_inventory"]},
            report["canonical_payload_sha256"]==canonical_hash(report), started.tzinfo is not None, finished.tzinfo is not None,
            started <= finished]
    if not all(checks): raise ValueError("receipt cross-field consistency check failed")


def finalize_receipt(report: dict[str, Any], output: Path, subject: Path) -> None:
    schema=load_schema()
    validate_receipt(report,schema)
    safe_write(output,(json.dumps(report,indent=2,sort_keys=True)+"\n").encode(),subject)


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
    if output.is_symlink(): raise ValueError("output must not be a symlink")
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
    uv,uv_version,uv_sha256=verified_uv()
    repo=repo.resolve(); started=datetime.now(timezone.utc).isoformat(); subject=require_clean_subject(repo,expected_commit)
    with tempfile.TemporaryDirectory(prefix="no1-006b-") as raw:
        temp=Path(raw); dist=temp/"dist"; dist.mkdir(); requirements=temp/"locked-requirements.txt"
        subject["source_archive_sha256"]=source_archive_sha(repo,temp/"source.tar")
        assert_subject_unchanged(repo,expected_commit,subject,"initial archive")
        collector_root=Path(__file__).resolve().parents[1]
        tool_export_sha,tool_rows,tool_inventory_sha=collector_tool_export(collector_root,temp/"collector-tool-requirements.txt",uv)
        collector=collector_identity(tool_export_sha)
        collector["tool_inventory"]=tool_rows; collector["tool_inventory_sha256"]=tool_inventory_sha
        build_env=build_environment()
        export_sha=export_closure(repo,requirements,uv)
        assert_subject_unchanged(repo,expected_commit,subject,"before build")
        run([str(uv),"build","--no-config","--wheel","--offline","--no-build-isolation","--python",sys.executable,"--out-dir",str(dist)],cwd=repo)
        assert_subject_unchanged(repo,expected_commit,subject,"after build")
        wheels=list(dist.glob("*.whl"))
        if len(wheels)!=1: raise RuntimeError(f"expected exactly one root wheel, found {len(wheels)}")
        wheel=wheels[0]; require_file_budget(wheel,MAX_ROOT_WHEEL_BYTES,"root wheel artifact")
        fixture=temp/"fixture"; fixture.mkdir(); (fixture/"fixture.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n")
        samples={}; inventories=[]; tool_names=None; py_info=None
        for kind in ("cli","mcp"):
            assert_subject_unchanged(repo,expected_commit,subject,f"before {kind} install")
            python=install_environment(repo,temp/f"{kind}-venv",requirements,wheel,uv)
            assert_subject_unchanged(repo,expected_commit,subject,f"after {kind} install")
            target_python=python_identity(python,repo,"<target-venv-python>")
            require_native_python_identity(build_env["python"],target_python)
            if py_info is None: py_info=target_python
            elif target_python != py_info: raise RuntimeError("fresh CLI/MCP environments have different Python identities")
            inventories.append(inventory(python,repo))
            if kind=="cli": samples[kind]=[cli_sample(executable(python.parent.parent,"tree-sitter-analyzer"),fixture) for _ in range(repeats+1)]
            else:
                results=[mcp_sample(executable(python.parent.parent,"tree-sitter-analyzer-mcp"),fixture) for _ in range(repeats+1)]
                samples[kind]=[r[0] for r in results]; tool_names=results[0][1]
        if inventories[0] != inventories[1]: raise RuntimeError("fresh CLI/MCP environments have different installed closures")
        inv=inventories[0]; rows=inv["distributions"]; roles=[r["role"] for r in rows]; finished=datetime.now(timezone.utc).isoformat()
        report={"schema_version":3,"roadmap_id":"NO1-006B","evidence_level":"E0",
          "collection_started_at_utc":started,"collection_finished_at_utc":finished,"collector":collector,
          "source":{**subject,"root_wheel_filename":wheel.name,"root_wheel_sha256":sha256(wheel),"root_wheel_artifact_size_bytes":wheel.stat().st_size},
          "dependency_closure":{"derivation":"uv.lock frozen export; hashed exact requirements; project wheel installed separately with --no-deps","export_sha256":export_sha,"lock_sha256":subject["lock_sha256"],"distributions":rows},
          "environment":{"os":platform.platform(),"system":"macos","machine":platform.machine(),"python":py_info,"build_python":build_env["python"],"build_backend":{"name":"hatchling","version":build_env["hatchling_version"]},"uv":{"version":uv_version,"sha256":uv_sha256},"network_policy":"UV_OFFLINE=1; uv --offline; no network transfer measurement","bytecode_policy":"PYTHONDONTWRITEBYTECODE=1","cache_protocol":"two independent fresh identical venvs; first sample bytecode-cold but OS cache uncontrolled; subsequent samples fresh-process warm","sample_order":SAMPLE_ORDER,"host_fingerprint":{"cpu":platform.processor() or platform.machine() or "unknown","logical_cpu_count":os.cpu_count() or 1,"ram_bytes":os.sysconf("SC_PAGE_SIZE")*os.sysconf("SC_PHYS_PAGES"),"filesystem":"unknown; not controlled","virtualization":"unknown; not detected","power":"unknown; not controlled"}},
          "measurements":{"root_wheel_artifact_size_bytes":wheel.stat().st_size,"network_transfer_bytes":{"status":"unknown","reason":"offline cache artifacts do not measure network transfer"},"installed_size_bytes":inv["installed_size_bytes"],"installed_regular_file_count":inv["regular_file_count"],"installed_size_scope":"unique resolved in-venv regular files; pyc/direct_url excluded; symlinks rejected; hardlinks inode-deduplicated; interpreter excluded","direct_dependency_count":roles.count("direct"),"transitive_dependency_count":roles.count("transitive"),"dependency_distribution_count_excluding_root":len(rows)-1,"installed_distribution_count_including_root":len(rows),"cli_startup":{"definition":CLI_STARTUP_DEFINITION,"cold_ms":samples["cli"][0],"warm_ms":samples["cli"][1:]},"mcp_startup":{"definition":MCP_STARTUP_DEFINITION,"cold_ms":samples["mcp"][0],"warm_ms":samples["mcp"][1:],"tool_names":tool_names}},
          "commands":{"collector_tool_export":["uv","export","--no-config","--frozen","--offline","--only-group",TOOL_GROUP,"--no-emit-project","--format","requirements-txt"],"export":["uv","export","--no-config","--frozen","--offline","--no-dev","--no-emit-project","--format","requirements-txt"],"build":["uv","build","--no-config","--wheel","--offline","--no-build-isolation","--python","<collector-sys-executable>","--out-dir","<temp>/dist"],"closure_install":["uv","pip","install","--no-config","--offline","--no-deps","--require-hashes","-r","<locked-requirements>"],"root_install":["uv","pip","install","--no-config","--offline","--no-deps","<root-wheel>"],"cli_probe":["tree-sitter-analyzer","fixture.py","--summary","--format","json"],"mcp_probe":["tree-sitter-analyzer-mcp","--project-root","<fixture>","initialize","notifications/initialized","tools/list"]},
          "repeats":repeats,"measured_axis":"macos","platform_axes":{"macos":"measured_e0","linux":"unknown","windows":"unknown"}}
        report["canonical_payload_sha256"]=canonical_hash(report)
        assert_subject_unchanged(repo,expected_commit,subject,"final publication")
        finalize_receipt(report,output,repo); return report


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--repo",type=Path,required=True); parser.add_argument("--output",type=Path,required=True); parser.add_argument("--repeats",type=int,default=5); parser.add_argument("--expected-commit",default=EXPECTED_SUBJECT_COMMIT)
    args=parser.parse_args(); collect(args.repo,args.output,args.repeats,args.expected_commit); return 0

if __name__ == "__main__": raise SystemExit(main())
# fmt: on
