#!/usr/bin/env python3
"""Content-bound native outdated-uv actionable-recovery qualification."""

from __future__ import annotations

# ruff: noqa: B904, E401, E701, E702, I001
# fmt: off
import argparse, hashlib, json, os, platform, re, shutil, signal, subprocess, sys, tarfile, tempfile, urllib.request, zipfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "no1-006a-outdated-uv-attestation-v2"
OLD_VERSION, SUPPORTED_VERSION = "0.10.9", "0.11.0"
AXES = ("linux", "macos", "windows")
PROJECT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = PROJECT / "config/no1_uv_fixtures.json"
REQUIRED_COMMANDS = ("awk", "cat", "grep", "mktemp", "python3", "realpath", "rm", "sleep", "uname")

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(value,sort_keys=True,indent=2)+"\n","utf-8"); os.replace(tmp,path)

def identity(job: str) -> tuple[dict[str,Any],dict[str,str]]:
    server=os.environ.get("GITHUB_SERVER_URL","https://github.com"); repo=os.environ.get("GITHUB_REPOSITORY","local/unknown"); run=os.environ.get("GITHUB_RUN_ID","0")
    return ({"repository":repo,"commit":os.environ.get("GITHUB_SHA","0"*40),"ref":os.environ.get("GITHUB_REF","local"),"dirty":False},
      {"event":os.environ.get("GITHUB_EVENT_NAME","local"),"run_id":run,"run_attempt":os.environ.get("GITHUB_RUN_ATTEMPT","0"),"job":job,"workflow_ref":os.environ.get("GITHUB_WORKFLOW_REF","local"),"run_url":f"{server}/{repo}/actions/runs/{run}"})

def allowlist() -> dict[str,Any]:
    value=json.loads(ALLOWLIST_PATH.read_text("utf-8"))
    if value.get("schema_version")!="no1-006a-uv-fixtures-v1" or value.get("supported_version")!=SUPPORTED_VERSION: raise ValueError("fixture allowlist identity mismatch")
    return value

def fixture(axis: str, version: str) -> dict[str,Any]:
    machine=platform.machine().lower()
    architecture="arm64" if machine in ("arm64","aarch64") else "x86_64"
    key=f"macos-{architecture}-{version}" if axis=="macos" else f"{axis}-{version}"
    return allowlist()["fixtures"][key]

def validate_archive(path: Path, expected: dict[str,Any]) -> dict[str,Any]:
    path=path.resolve(strict=True)
    observed={"filename":expected["filename"],"url":expected["url"],"version":expected["version"],"size":path.stat().st_size,"sha256":sha256(path)}
    if observed["size"]!=expected["size"] or observed["sha256"]!=expected["sha256"]: raise ValueError("archive bytes not in official exact allowlist")
    return observed

def fetch(args: argparse.Namespace) -> int:
    expected=fixture(args.axis,args.version); output=Path(args.output)
    request=urllib.request.Request(expected["url"],headers={"User-Agent":"tsa-no1-qualification/1"})
    with urllib.request.urlopen(request,timeout=60) as source, output.open("wb") as target: shutil.copyfileobj(source,target)
    validate_archive(output,expected); return 0

def _safe_member(name: str, destination: Path) -> Path:
    normalized=name.replace("\\","/")
    pure=Path(normalized)
    if not normalized or pure.is_absolute() or ".." in pure.parts or re.match(r"^[A-Za-z]:",normalized): raise ValueError(f"unsafe archive member path: {name}")
    target=(destination/pure).resolve()
    try: target.relative_to(destination.resolve())
    except ValueError: raise ValueError(f"archive member escapes destination: {name}")
    return target

def safe_extract(archive: Path, destination: Path, expected_filename: str | None=None) -> Path:
    destination.mkdir(parents=True); archive=archive.resolve(strict=True)
    filename=expected_filename or archive.name
    expected_format="zip" if filename.endswith(".zip") else "tar.gz" if filename.endswith(".tar.gz") else None
    content_format="zip" if zipfile.is_zipfile(archive) else "tar.gz" if tarfile.is_tarfile(archive) else None
    if expected_format is None or content_format != expected_format: raise ValueError("archive filename/content format differs from allowlist")
    if content_format=="zip":
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                mode=(info.external_attr >> 16) & 0o170000
                if mode not in (0,0o100000,0o040000): raise ValueError(f"unsafe zip member type: {info.filename}")
                target=_safe_member(info.filename,destination)
                if info.is_dir(): target.mkdir(parents=True,exist_ok=True); continue
                target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(info) as source, target.open("xb") as output: shutil.copyfileobj(source,output)
    else:
        with tarfile.open(archive,"r:gz") as t:
            for member in t.getmembers():
                if member.issym() or member.islnk() or member.isdev() or not (member.isfile() or member.isdir()): raise ValueError(f"unsafe tar member type: {member.name}")
                target=_safe_member(member.name,destination)
                if member.isdir(): target.mkdir(parents=True,exist_ok=True); continue
                target.parent.mkdir(parents=True,exist_ok=True); source=t.extractfile(member)
                if source is None: raise ValueError(f"tar member has no content: {member.name}")
                with source, target.open("xb") as output: shutil.copyfileobj(source,output)
    executable="uv.exe" if content_format=="zip" else "uv"
    found=[p for p in destination.rglob(executable) if p.is_file()]
    if len(found)!=1: raise ValueError("archive must contain exactly one uv executable")
    found[0].chmod(found[0].stat().st_mode|0o700); return found[0]

def uv_details(executable: Path, expected: str) -> dict[str,Any]:
    executable=executable.resolve(strict=True); completed=subprocess.run([str(executable),"--version"],capture_output=True,text=True,timeout=10,check=False)
    if completed.returncode or completed.stderr or re.fullmatch(rf"uv {re.escape(expected)}(?: [^\n]+)?\n?",completed.stdout) is None: raise ValueError(f"fixture did not execute as exact uv {expected}")
    return {"version":expected,"path":str(executable),"sha256":sha256(executable),"size":executable.stat().st_size,"version_stdout":completed.stdout}

def tree_snapshot(root: Path) -> list[dict[str,Any]]:
    result=[]
    for p in sorted(root.rglob("*")):
        rel=str(p.relative_to(root)); result.append({"path":rel,"type":"symlink" if p.is_symlink() else "dir" if p.is_dir() else "file","sha256":sha256(p) if p.is_file() and not p.is_symlink() else None})
    return result

def curated_tools(root: Path) -> Path:
    root.mkdir()
    for name in REQUIRED_COMMANDS:
        target=shutil.which(name)
        if not target: raise ValueError(f"required OS command missing: {name}")
        os.symlink(Path(target).resolve(),root/name)
    return root

def clean_env(home: Path, temp: Path, path: str, disable: bool) -> dict[str,str]:
    keep={k:os.environ[k] for k in ("LANG","LC_ALL","SSL_CERT_FILE","SSL_CERT_DIR") if k in os.environ}
    keep.update({"HOME":str(home),"XDG_CONFIG_HOME":str(home/".config"),"XDG_CACHE_HOME":str(home/".cache"),"XDG_DATA_HOME":str(home/".local/share"),"TMPDIR":str(temp),"PATH":path,"PYTHONPATH":"","PYTHONNOUSERSITE":"1","PYTHONHOME":"","UV_NO_CONFIG":"1"})
    if disable: keep["TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP"]="1"
    return keep

def run_tree(argv:list[str],cwd:Path,env:dict[str,str],timeout:float)->subprocess.CompletedProcess[bytes]:
    process=subprocess.Popen(argv,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=os.name!="nt")
    try: out,err=process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name!="nt":
            for sig,grace in ((signal.SIGTERM,.5),(signal.SIGKILL,.5)):
                try: os.killpg(process.pid,sig)
                except ProcessLookupError: pass
                try: process.communicate(timeout=grace)
                except subprocess.TimeoutExpired: pass
        else:
            subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],capture_output=True,timeout=5,check=False)
        try: process.communicate(timeout=.5)
        except subprocess.TimeoutExpired:
            for stream in (process.stdout,process.stderr):
                if stream: stream.close()
            try: process.wait(timeout=.5)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=.5)
        raise TimeoutError("installer process tree timed out and was reaped")
    return subprocess.CompletedProcess(argv,process.returncode,out,err)

def package_binding(args: argparse.Namespace)->dict[str,Any]:
    wheel=Path(args.wheel).resolve(strict=True); aggregate=Path(args.package_aggregate).resolve(strict=True); report=Path(args.package_report).resolve(strict=True); manifest=Path(args.wheel_manifest).resolve(strict=True)
    a=json.loads(aggregate.read_text()); r=json.loads(report.read_text()); m=json.loads(manifest.read_text()); meta=m["wheel"]
    if {"filename":wheel.name,"sha256":sha256(wheel),"size":wheel.stat().st_size} != {k:meta[k] for k in ("filename","sha256","size")}: raise ValueError("candidate wheel differs from build-once manifest")
    expected={"axis":args.axis,"report_sha256":sha256(report),"passed":True}
    if r.get("wheel")!=meta or expected not in a.get("axes",[]) or a.get("wheel")!=meta: raise ValueError("package axis/wheel binding mismatch")
    return {"aggregate_sha256":sha256(aggregate),"axis_report_sha256":sha256(report),"build_manifest_sha256":sha256(manifest),"wheel":meta}

def base_report(axis:str)->dict[str,Any]:
    source,workflow=identity("outdated-uv-axis")
    return {"schema_version":SCHEMA_VERSION,"kind":"outdated_uv_axis","qualification_id":"NO1-006A","evidence_scope":"native_outdated_uv_actionable_recovery","axis":axis,"qualification_performed":axis!="windows","passed":False,"status":"NOT_APPLICABLE_NO_NATIVE_INSTALLER" if axis=="windows" else "PENDING","source":source,"workflow":workflow,"runner":{"declared_axis":axis,"observed_system":platform.system(),"release":platform.release(),"machine":platform.machine(),"image_os":os.environ.get("ImageOS","unknown"),"image_version":os.environ.get("ImageVersion","unknown")},"remediation_mode":"manual_content_bound_remediation","automatic_mutable_bootstrap_qualified":False,"old_uv":None,"supported_uv":None,"installer":None,"config":None,"package_qualification":None,"mcp_causal_report":None,"artifacts":{},"failure":None}

def write_side(side:Path,name:str,data:bytes,report:dict[str,Any])->None:
    path=side/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data); report["artifacts"][name]={"sha256":sha256(path),"size":path.stat().st_size}

def axis(args:argparse.Namespace)->int:
    output=Path(args.output).resolve(); side=output.parent; side.mkdir(parents=True,exist_ok=True); report=base_report(args.axis)
    try:
        expected_system={"linux":"Linux","macos":"Darwin","windows":"Windows"}[args.axis]
        if platform.system()!=expected_system: raise ValueError("declared axis and native runner differ")
        old_archive=Path(args.old_archive); old_meta=validate_archive(old_archive,fixture(args.axis,OLD_VERSION)); shutil.copyfile(old_archive,side/"old.archive"); report["artifacts"]["old.archive"]={"sha256":old_meta["sha256"],"size":old_meta["size"]}
        root=Path(tempfile.mkdtemp(prefix="tsa-outdated-native-"))
        try:
            old=uv_details(safe_extract(old_archive,root/"old",old_meta["filename"]),OLD_VERSION); report["old_uv"]={"archive":old_meta,"executable":old}
            report["package_qualification"]=package_binding(args)
            if args.axis=="windows":
                if Path(args.installer).with_name("install.ps1").exists(): raise ValueError("Windows native installer now exists; implement its qualification")
                report["status"]="NOT_APPLICABLE_NO_NATIVE_INSTALLER"; report["failure"]={"type":"NotApplicable","message":"Windows has no native install.ps1; real old uv.exe execution retained only as a platform fixture"}
                return 0
            supported_archive=Path(args.supported_archive); supported_meta=validate_archive(supported_archive,fixture(args.axis,SUPPORTED_VERSION)); shutil.copyfile(supported_archive,side/"supported.archive"); report["artifacts"]["supported.archive"]={"sha256":supported_meta["sha256"],"size":supported_meta["size"]}
            supported=uv_details(safe_extract(supported_archive,root/"supported",supported_meta["filename"]),SUPPORTED_VERSION); report["supported_uv"]={"archive":supported_meta,"executable":supported}
            installer=Path(args.installer).resolve(strict=True); write_side(side,"installer.source",installer.read_bytes(),report)
            home=root/"home"; temp=root/"tmp"; project=root/"fixture"; tools=curated_tools(root/"tools")
            for p in (home,temp,project): p.mkdir()
            config=home/".claude/.mcp.json"; config.parent.mkdir(parents=True); config.write_text('{}\n',"utf-8")
            before=tree_snapshot(home); old_path=os.pathsep.join((str(Path(old["path"]).parent),str(tools)))
            first=run_tree(["/bin/bash",str(installer)],project,clean_env(home,temp,old_path,True),args.timeout)
            write_side(side,"first.stdout",first.stdout,report); write_side(side,"first.stderr",first.stderr,report); after_first=tree_snapshot(home)
            first_text=first.stdout.decode("utf-8","replace")
            required=("TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP=1",f"Install uv >= {SUPPORTED_VERSION} manually","Then re-run the original Tree-sitter Analyzer install command")
            detected=re.search(rf"uv {re.escape(OLD_VERSION)}(?: [^\n]+)? does not satisfy required uv >= {re.escape(SUPPORTED_VERSION)}",first_text)
            if first.returncode!=1 or detected is None or not all(x in first_text for x in required) or "installation complete" in first_text or before!=after_first: raise ValueError("first install fail-closed/config/curl oracle failed")
            supported_path=os.pathsep.join((str(Path(supported["path"]).parent),str(tools)))
            second=run_tree(["/bin/bash",str(installer)],project,clean_env(home,temp,supported_path,False),args.timeout)
            write_side(side,"second.stdout",second.stdout,report); write_side(side,"second.stderr",second.stderr,report); after_second=tree_snapshot(home)
            expected_entry={"command":"uvx","args":["--from","tree-sitter-analyzer[mcp]","tree-sitter-analyzer-mcp"],"env":{"TREE_SITTER_PROJECT_ROOT":str(project.resolve())}}
            value=json.loads(config.read_text()); backups=list(config.parent.glob(".mcp.json.bak.*"))
            expected_value={"mcpServers":{"tree-sitter-analyzer":expected_entry}}
            if second.returncode!=0 or f"uv {SUPPORTED_VERSION}" not in second.stdout.decode("utf-8","replace") or value!=expected_value or len(backups)!=1 or backups[0].read_bytes()!=b'{}\n': raise ValueError("manual recovery config diff/backup oracle failed")
            expected_after=[item for item in before if item["path"] not in (".claude/.mcp.json",)]
            expected_after.extend([{"path":".claude/.mcp.json","type":"file","sha256":hashlib.sha256((json.dumps(expected_value,indent=2)+"\n").encode()).hexdigest()},{"path":str(backups[0].relative_to(home)),"type":"file","sha256":hashlib.sha256(b'{}\n').hexdigest()}])
            if sorted(after_second,key=lambda item:item["path"])!=sorted(expected_after,key=lambda item:item["path"]): raise ValueError("second install changed HOME beyond exact config replacement and one backup")
            report["installer"]={"path":str(installer),"sha256":sha256(installer),"first_exit":first.returncode,"second_exit":second.returncode,"curl_invocations":0,"first_path":old_path,"second_path":supported_path}
            report["config"]={"before":before,"after_first":after_first,"after_second":after_second,"expected_entry":expected_entry,"backup_sha256":sha256(backups[0])}
            mcp_dir=side/"mcp"; mcp_dir.mkdir(); env=os.environ.copy(); env["TSA_QUALIFICATION_UV"]=supported["path"]
            command=[sys.executable,str(PROJECT/"scripts/qualify_native_install.py"),"axis","--axis",args.axis,"--wheel",str(Path(args.wheel).resolve()),"--wheel-manifest",str(Path(args.wheel_manifest).resolve()),"--output",str(mcp_dir/"report.json")]
            causal=subprocess.run(command,cwd=PROJECT,env=env,capture_output=True,timeout=420,check=False)
            write_side(side,"mcp-driver.stdout",causal.stdout,report); write_side(side,"mcp-driver.stderr",causal.stderr,report)
            if causal.returncode or not (mcp_dir/"report.json").exists(): raise RuntimeError("supported uv exact-wheel MCP qualification failed")
            causal_report=json.loads((mcp_dir/"report.json").read_text()); binding=report["package_qualification"]
            install=causal_report.get("install",{}); tool=install.get("tool",{}); expected_tool={k:supported[k] for k in ("path","sha256","size","version_stdout","version")}
            runtime=causal_report.get("runtime",{}); causal_runner=causal_report.get("runner")
            expected_argv=[supported["path"],"pip","install","--python",runtime.get("executable"),"--no-cache",f"{Path(args.wheel).resolve()}[mcp]"]
            sidecar_hashes={"install_stdout_sha256":sha256(mcp_dir/"install.stdout"),"install_stderr_sha256":sha256(mcp_dir/"install.stderr"),"dependency_manifest_sha256":sha256(mcp_dir/"dependency-manifest.txt")}
            if causal_report.get("passed") is not True or causal_report.get("wheel")!=binding["wheel"] or causal_report.get("build_manifest_sha256")!=binding["build_manifest_sha256"] or causal_runner!=report["runner"] or tool!=expected_tool or install.get("argv")!=expected_argv or install.get("stdout_sha256")!=sidecar_hashes["install_stdout_sha256"] or install.get("stderr_sha256")!=sidecar_hashes["install_stderr_sha256"] or causal_report.get("dependency_manifest_sha256")!=sidecar_hashes["dependency_manifest_sha256"]: raise ValueError("MCP causal report/install-tool/runtime/sidecar identity mismatch")
            report["mcp_causal_report"]={"sha256":sha256(mcp_dir/"report.json"),"wheel":causal_report["wheel"],"runner":causal_runner,"first_call":causal_report["mcp"]["first_call"],"install_tool":tool,"install_argv":install["argv"],**sidecar_hashes}
            for p in sorted(mcp_dir.iterdir()): report["artifacts"][f"mcp/{p.name}"]={"sha256":sha256(p),"size":p.stat().st_size}
            report["passed"]=True; report["status"]="PASSED"
        finally: shutil.rmtree(root,ignore_errors=True)
    except Exception as exc: report["failure"]={"type":type(exc).__name__,"message":str(exc)}; report["status"]="FAILED"
    finally: atomic_write(output,report)
    return 0 if report["passed"] or report["status"]=="NOT_APPLICABLE_NO_NATIVE_INSTALLER" else 1

def aggregate(args:argparse.Namespace)->int:
    output=Path(args.output).resolve(); source,workflow=identity("outdated-uv-aggregate"); failures=[]; axes=[]; package=None
    for expected,raw in zip(AXES,args.reports,strict=True):
        path=Path(raw).resolve()
        try:
            value=json.loads(path.read_text()); ok=(expected in ("linux","macos") and value.get("passed") is True) or (expected=="windows" and value.get("status")=="NOT_APPLICABLE_NO_NATIVE_INSTALLER" and value.get("passed") is False and value.get("qualification_performed") is False)
            if value.get("axis")!=expected or not ok: failures.append(f"{expected}: invalid required outcome")
            expected_source,expected_workflow=identity("outdated-uv-axis")
            if value.get("source")!=expected_source or value.get("workflow")!=expected_workflow: failures.append(f"{expected}: report GITHUB identity mismatch")
            if value.get("automatic_mutable_bootstrap_qualified") is not False: failures.append(f"{expected}: mutable bootstrap claim")
            binding=value.get("package_qualification")
            common={k:binding.get(k) for k in ("aggregate_sha256","build_manifest_sha256","wheel")} if isinstance(binding,dict) else None
            if package is None: package=common
            if common!=package or not isinstance(binding,dict) or binding.get("axis_report_sha256") is None: failures.append(f"{expected}: package identity mismatch")
            axes.append({"axis":expected,"report_sha256":sha256(path),"status":value.get("status"),"passed":value.get("passed")})
        except Exception as exc: failures.append(f"{expected}: {type(exc).__name__}: {exc}")
    trusted=args.trusted and os.environ.get("GITHUB_EVENT_NAME")=="push" and os.environ.get("GITHUB_REF")=="refs/heads/develop"
    if args.trusted and not trusted: failures.append("trusted aggregate restricted to develop push")
    result={"schema_version":SCHEMA_VERSION,"kind":"outdated_uv_aggregate","qualification_id":"NO1-006A","evidence_scope":"native_outdated_uv_actionable_recovery","qualification_performed":len(axes)==3,"qualified":False,"evidence_trust":"EXTERNAL_ATTESTATION_REQUIRED" if trusted and not failures else "UNTRUSTED_CANDIDATE","source_commit":source["commit"],"package_qualification":package,"required_axes":{"package":["linux","macos","windows"],"outdated":["linux","macos"],"not_applicable":{"windows":"NOT_APPLICABLE_NO_NATIVE_INSTALLER"}},"automatic_mutable_bootstrap_qualified":False,"axes":axes,"failures":failures,"workflow":workflow}
    atomic_write(output,result); return 1 if failures else 0

def main()->int:
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="command",required=True)
    f=sub.add_parser("fetch"); f.add_argument("--axis",choices=AXES,required=True); f.add_argument("--version",choices=(OLD_VERSION,SUPPORTED_VERSION),required=True); f.add_argument("--output",required=True); f.set_defaults(func=fetch)
    a=sub.add_parser("axis"); a.add_argument("--axis",choices=AXES,required=True)
    for name in ("old-archive","installer","wheel","wheel-manifest","package-aggregate","package-report","output"): a.add_argument("--"+name,required=True)
    a.add_argument("--supported-archive"); a.add_argument("--timeout",type=float,default=180); a.set_defaults(func=axis)
    g=sub.add_parser("aggregate"); g.add_argument("--reports",nargs=3,required=True); g.add_argument("--output",required=True); g.add_argument("--trusted",action="store_true"); g.set_defaults(func=aggregate)
    args=parser.parse_args(); return int(args.func(args))
if __name__=="__main__": raise SystemExit(main())
