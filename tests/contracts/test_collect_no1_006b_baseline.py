"""Contracts for the NO1-006B pinned offline receipt."""

# ruff: noqa: E701, E702
# fmt: off
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib

import pytest
from jsonschema.exceptions import ValidationError

from scripts import collect_no1_006b_baseline as collector

REPO = Path(__file__).parents[2]
BASELINE = REPO / "docs/baselines/no1-006b-macos-e0.json"
SCHEMA = REPO / "schemas/no1-006b-baseline.schema.json"
RFC = REPO / "rfcs/0024-default-dependency-split.md"
PYPROJECT = REPO / "pyproject.toml"


def baseline() -> dict:
    return json.loads(BASELINE.read_text())


def schema() -> dict:
    return json.loads(SCHEMA.read_text())


def mutated(path: tuple[str, ...], value: object) -> dict:
    report=copy.deepcopy(baseline()); target=report
    for key in path[:-1]: target=target[key]
    target[path[-1]]=value; report["canonical_payload_sha256"]=collector.canonical_hash(report)
    return report


def test_checked_in_receipt_passes_schema_and_cross_field_validator() -> None:
    collector.validate_receipt(baseline(), schema())


def test_receipt_binds_distinct_collector_and_subject_commits() -> None:
    report=baseline()
    assert report["source"]["commit"] == collector.EXPECTED_SUBJECT_COMMIT
    assert report["collector"]["commit"] != report["source"]["commit"]


def test_schema_rejects_subject_tree_mutation() -> None:
    report=mutated(("source","git_tree"),"0"*40)
    with pytest.raises(ValidationError): collector.validate_receipt(report,schema())


def test_validator_rejects_subject_tree_mutation_when_schema_constraint_is_removed() -> None:
    # PR #1250: retain a runtime binding even if receipt validation is called with a weakened schema.
    weakened=copy.deepcopy(schema()); weakened["properties"]["source"]["properties"]["git_tree"]={"type":"string"}
    report=mutated(("source","git_tree"),"0"*40)
    with pytest.raises(ValueError,match="cross-field"): collector.validate_receipt(report,weakened)


def test_receipt_binds_exact_collector_and_schema_bytes() -> None:
    report=baseline()
    commit=report["collector"]["commit"]
    blobs=[subprocess.run(["git","show",f"{commit}:{path}"],cwd=REPO,check=True,capture_output=True).stdout for path in ("scripts/collect_no1_006b_baseline.py","schemas/no1-006b-baseline.schema.json")]
    assert [report["collector"]["script_sha256"],report["collector"]["schema_sha256"]] == [collector.digest_bytes(blob) for blob in blobs]


def test_receipt_binds_exact_collector_tool_lock_and_export(tmp_path: Path) -> None:
    # PR #1250: the historical collector closure must be derived from its bound commit, never reviewed HEAD.
    report=baseline(); commit=report["collector"]["commit"]; command=report["commands"]["collector_tool_export"]
    uv=Path(shutil.which(command[0]) or "missing").resolve(strict=True)
    uv_version=subprocess.run([str(uv),"--version"],check=True,capture_output=True,text=True).stdout.strip()
    assert uv_version.split()[:2] == report["environment"]["uv"]["version"].split()[:2]
    bound_command=[str(uv),*command[1:]]
    worktree=tmp_path/"collector"
    subprocess.run(["git","worktree","add","-q","--detach",str(worktree),commit],cwd=REPO,check=True)
    try:
        assert subprocess.run(["git","status","--porcelain=v1","--untracked-files=all","--ignored"],cwd=worktree,check=True,capture_output=True,text=True).stdout == ""
        exported=subprocess.run(bound_command,cwd=worktree,env=collector.clean_env(),check=True,capture_output=True).stdout
        lock_blob=subprocess.run(["git","show",f"{commit}:uv.lock"],cwd=worktree,env=collector.clean_env(),check=True,capture_output=True).stdout
    finally:
        subprocess.run(["git","worktree","remove","--force",str(worktree)],cwd=REPO,check=True)
    assert [report["collector"]["tool_lock_sha256"],report["collector"]["tool_export_sha256"]] == [collector.digest_bytes(lock_blob),collector.digest_bytes(exported)]
    assert worktree.exists() is False


def test_schema_rejects_invalid_rfc3339_timestamp() -> None:
    report=mutated(("collection_started_at_utc",),"not-a-date")
    with pytest.raises(ValueError, match="strict RFC 3339"): collector.validate_receipt(report,schema())


def test_validator_rejects_space_separated_timestamp() -> None:
    report=mutated(("collection_started_at_utc",),"2026-08-09 23:09:51+00:00")
    with pytest.raises(ValueError, match="strict RFC 3339"): collector.validate_receipt(report,schema())


def test_validator_rejects_lowercase_utc_designator() -> None:
    report=mutated(("collection_started_at_utc",),"2026-08-09T23:09:51z")
    with pytest.raises(ValueError, match="strict RFC 3339"): collector.validate_receipt(report,schema())


def test_validator_rejects_naive_timestamp() -> None:
    report=mutated(("collection_started_at_utc",),"2026-08-09T23:09:51")
    with pytest.raises(ValueError, match="strict RFC 3339"): collector.validate_receipt(report,schema())


def test_rfc3339_parser_round_trips_fractional_offset_timestamp() -> None:
    value="2026-08-09T23:09:51.800365+09:30"
    assert collector.parse_rfc3339(value).isoformat() == value


def test_rfc3339_parser_rejects_out_of_range_timestamp() -> None:
    with pytest.raises(ValueError, match="month must be in"):
        collector.parse_rfc3339("2026-13-09T23:09:51Z")


def test_schema_retains_date_time_format_annotations() -> None:
    properties=schema()["properties"]
    assert [properties[key]["format"] for key in ("collection_started_at_utc","collection_finished_at_utc")] == ["date-time","date-time"]


def test_validator_rejects_reverse_timestamp_order() -> None:
    report=mutated(("collection_started_at_utc",),"2999-01-01T00:00:00+00:00")
    with pytest.raises(ValueError,match="cross-field"): collector.validate_receipt(report,schema())


def test_validator_rejects_repeat_sample_mismatch() -> None:
    report=mutated(("repeats",),4)
    with pytest.raises(ValueError,match="cross-field"): collector.validate_receipt(report,schema())


def test_validator_rejects_direct_count_mismatch() -> None:
    report=mutated(("measurements","direct_dependency_count"),0)
    with pytest.raises(ValueError,match="cross-field"): collector.validate_receipt(report,schema())


def test_validator_rejects_total_count_mismatch() -> None:
    report=mutated(("measurements","installed_distribution_count_including_root"),1)
    with pytest.raises(ValueError,match="cross-field"): collector.validate_receipt(report,schema())


def test_validator_rejects_duplicate_distribution_names() -> None:
    report=copy.deepcopy(baseline()); report["dependency_closure"]["distributions"][1]["name"]=report["dependency_closure"]["distributions"][0]["name"]; report["canonical_payload_sha256"]=collector.canonical_hash(report)
    with pytest.raises(ValueError,match="cross-field"): collector.validate_receipt(report,schema())


def test_validator_rejects_root_role_on_non_project_distribution() -> None:
    # PR #1250: role swapping must not relabel a dependency as the project root.
    report=copy.deepcopy(baseline()); rows=report["dependency_closure"]["distributions"]
    project=next(row for row in rows if row["name"]==collector.ROOT_NAME); dependency=next(row for row in rows if row["name"]=="anthropic")
    project["role"],dependency["role"]="direct","root"; report["canonical_payload_sha256"]=collector.canonical_hash(report)
    with pytest.raises(ValueError,match="cross-field"): collector.validate_receipt(report,schema())


def test_validator_rejects_lock_hash_mismatch() -> None:
    report=mutated(("dependency_closure","lock_sha256"),"0"*64)
    with pytest.raises(ValueError,match="cross-field"): collector.validate_receipt(report,schema())


def test_validator_rejects_artifact_size_mismatch() -> None:
    report=mutated(("measurements","root_wheel_artifact_size_bytes"),1)
    with pytest.raises(ValueError,match="cross-field"): collector.validate_receipt(report,schema())


def test_validator_rejects_stale_canonical_hash() -> None:
    report=copy.deepcopy(baseline()); report["repeats"]=4
    with pytest.raises(ValueError,match="cross-field"): collector.validate_receipt(report,schema())


@pytest.mark.parametrize(("axis","os_label"),[("macos","macOS-26.4.1-arm64"),("linux","Linux-6.8.0-x86_64"),("windows","Windows-11-10.0.26100")])
def test_schema_supports_each_native_axis_without_fabricating_measurements(axis: str, os_label: str) -> None:
    report=copy.deepcopy(baseline()); report["measured_axis"]=axis; report["environment"]["system"]=axis; report["environment"]["os"]=os_label
    report["platform_axes"]={name:("measured_e0" if name==axis else "unknown") for name in ("macos","linux","windows")}; report["canonical_payload_sha256"]=collector.canonical_hash(report)
    collector.validate_receipt(report,schema())


def test_validator_rejects_environment_os_system_contradiction() -> None:
    report=mutated(("environment","os"),"Windows-11-10.0.26100")
    with pytest.raises(ValueError,match="cross-field"): collector.validate_receipt(report,schema())



def test_schema_rejects_cli_startup_definition_mutation() -> None:
    report=mutated(("measurements","cli_startup","definition"),"X"*20)
    with pytest.raises(ValidationError): collector.validate_receipt(report,schema())


def test_schema_rejects_mcp_startup_definition_mutation() -> None:
    report=mutated(("measurements","mcp_startup","definition"),"Y"*20)
    with pytest.raises(ValidationError): collector.validate_receipt(report,schema())


def test_schema_rejects_measured_axis_contradiction() -> None:
    report=mutated(("platform_axes","macos"),"unknown")
    with pytest.raises(ValidationError): collector.validate_receipt(report,schema())


def test_validator_rejects_build_python_mismatch() -> None:
    report=mutated(("environment","build_python","version"),"3.13.0")
    with pytest.raises(ValueError,match="cross-field"): collector.validate_receipt(report,schema())


def test_schema_rejects_unpinned_build_backend() -> None:
    report=mutated(("environment","build_backend","version"),"1.30.0")
    with pytest.raises(ValidationError): collector.validate_receipt(report,schema())


def test_schema_definitions_equal_collector_constants() -> None:
    properties=schema()["properties"]["measurements"]["properties"]
    assert [properties["cli_startup"]["properties"]["definition"]["const"],properties["mcp_startup"]["properties"]["definition"]["const"]] == [collector.CLI_STARTUP_DEFINITION,collector.MCP_STARTUP_DEFINITION]


def test_collect_routes_receipt_through_schema_finalizer() -> None:
    source=Path(collector.__file__).read_text()
    assert "finalize_receipt(report,output,repo); return report" in source


def test_finalize_receipt_loads_bound_schema_before_write(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    observed=[]
    monkeypatch.setattr(collector,"validate_receipt",lambda report,bound_schema: observed.append(bound_schema))
    monkeypatch.setattr(collector,"safe_write",lambda output,data,subject: observed.append(json.loads(data)))
    collector.finalize_receipt(baseline(),tmp_path/"receipt.json",REPO)
    assert observed == [schema(),baseline()]

def inventory_from_requirements(monkeypatch: pytest.MonkeyPatch, requirements: list[str], python_version: str="3.14") -> dict:
    marker_environment={"implementation_name":"cpython","implementation_version":python_version,"os_name":"posix","platform_machine":"arm64","platform_python_implementation":"CPython","platform_release":"test","platform_system":"Darwin","platform_version":"test","python_full_version":python_version,"python_version":python_version}
    payload={"versions":{"tree-sitter-analyzer":"1","Foo.Bar":"2"},"requires":requirements,"installed_size_bytes":1,"regular_file_count":1}
    def fake_run(command: list[str],**kwargs: object) -> object:
        output=marker_environment if command[-1] == collector.TARGET_MARKER_CODE else payload
        return __import__("subprocess").CompletedProcess([],0,json.dumps(output).encode(),b"")
    monkeypatch.setattr(collector,"run",fake_run)
    return collector.inventory(Path("python"),Path("."))


def test_inventory_evaluates_arbitrary_pep508_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    report=inventory_from_requirements(monkeypatch,["Foo.Bar; python_version > '3.0'"])
    assert report["distributions"][0] == {"name":"foo-bar","version":"2","role":"direct"}


def test_inventory_uses_target_interpreter_marker_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    report=inventory_from_requirements(monkeypatch,["Foo.Bar; python_version >= '3.10'"],python_version="2.7")
    assert report["distributions"][0] == {"name":"foo-bar","version":"2","role":"transitive"}


def test_inventory_excludes_unselected_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    report=inventory_from_requirements(monkeypatch,["Foo.Bar; extra == 'feature'"])
    assert report["distributions"][0] == {"name":"foo-bar","version":"2","role":"transitive"}


def test_safe_write_rejects_broken_output_symlink(tmp_path: Path) -> None:
    link=tmp_path/"receipt"; link.symlink_to(tmp_path/"missing")
    with pytest.raises(ValueError,match="symlink"): collector.safe_write(link,b"bad",REPO)

def test_safe_write_rejects_output_symlink(tmp_path: Path) -> None:
    target=tmp_path/"target"; target.write_text("safe"); link=tmp_path/"receipt"; link.symlink_to(target)
    with pytest.raises(ValueError,match="symlink"): collector.safe_write(link,b"bad",REPO)
    assert target.read_text() == "safe"


@pytest.mark.skipif(os.name == "nt", reason="tracked: NO1-006B collector currently emits macOS-only E0 receipts")
def test_bounded_reader_times_out_on_partial_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    read_fd,write_fd=__import__("os").pipe(); __import__("os").write(write_fd,b'{"id":')
    class Process: stdout=__import__("os").fdopen(read_fd,"rb",buffering=0)
    monkeypatch.setattr(collector,"MAX_FRAME_BYTES",64)
    with pytest.raises(TimeoutError,match="absolute deadline"): collector.read_json_frame(Process(),__import__("time").monotonic()+0.01)
    __import__("os").close(write_fd); Process.stdout.close()



def test_file_budget_rejects_oversized_artifact(tmp_path: Path) -> None:
    artifact=tmp_path/"artifact"; artifact.write_bytes(b"xx")
    with pytest.raises(RuntimeError,match="disk budget"): collector.require_file_budget(artifact,1,"test artifact")


def test_collector_rejects_unbounded_repeat_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collector.platform, "system", lambda: "Darwin")
    with pytest.raises(ValueError,match="between 3 and 20"): collector.collect(REPO,tmp_path/"receipt.json",21,collector.EXPECTED_SUBJECT_COMMIT)

def test_rfc_generated_summary_equals_checked_in_receipt() -> None:
    text=RFC.read_text()
    generated=text.split("<!-- BEGIN GENERATED RECEIPT SUMMARY -->\n",1)[1].split("\n<!-- END GENERATED RECEIPT SUMMARY -->",1)[0]
    assert generated == collector.render_receipt_summary(baseline())


def test_collector_commit_is_ancestor_of_reviewed_head() -> None:
    commit=baseline()["collector"]["commit"]
    result=subprocess.run(["git","merge-base","--is-ancestor",commit,"HEAD"],cwd=REPO)
    assert result.returncode == 0


def test_fresh_clone_can_resolve_and_checkout_collector_commit(tmp_path: Path) -> None:
    commit=baseline()["collector"]["commit"]
    bare=tmp_path/"reviewed.git"; clone=tmp_path/"clone"; worktree=tmp_path/"collector"
    subprocess.run(["git","init","--bare","-q",str(bare)],check=True)
    subprocess.run(["git","push","-q",str(bare),"HEAD:refs/heads/reviewed"],cwd=REPO,check=True)
    subprocess.run(["git","clone","-q","--no-local","--no-tags","--single-branch","--branch","reviewed",str(bare),str(clone)],check=True)
    subprocess.run(["git","worktree","add","-q","--detach",str(worktree),commit],cwd=clone,check=True)
    assert subprocess.run(["git","rev-parse","HEAD"],cwd=worktree,check=True,capture_output=True,text=True).stdout.strip() == commit


def test_rfc_requires_merge_commit_to_preserve_collector_ancestry() -> None:
    reproduction=RFC.read_text().split("## Reproduction of the descriptive receipt",1)[1].split("```bash",1)[0]
    assert [phrase in reproduction for phrase in ("merge-commit strategy","Squash","rebase merges are prohibited","gh pr merge 1250","--merge")] == [True,True,True,True,True]


def test_rfc_reproduction_command_uses_external_interpreter() -> None:
    # NO1-006B review 2026-08-10: a repo-local ignored venv made the clean gate reject the documented command.
    reproduction=RFC.read_text().split("## Reproduction of the descriptive receipt",1)[1].split("## Measured macOS E0 receipt",1)[0]
    assert ".venv/bin/python" not in reproduction
    assert 'TOOL_VENV="$RUN_ROOT/collector-tool-venv"' in reproduction
    assert "--only-group no1-006b-collector-tool --no-emit-project" in reproduction
    assert '--require-hashes -r "$TOOL_REQUIREMENTS"' in reproduction
    assert '"$TOOL_PYTHON" "$COLLECTOR/scripts/collect_no1_006b_baseline.py"' in reproduction


def test_collector_tool_group_has_exact_independent_pins() -> None:
    groups=tomllib.loads(PYPROJECT.read_text())["dependency-groups"]
    assert groups[collector.TOOL_GROUP] == ["hatchling==1.31.0","jsonschema==4.25.1","packaging==25.0"]



def active_tool_inventory(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str,str]]) -> bytes:
    export=b"packaging==25.0 "+bytes([92])+b"\n    --hash=sha256:"+b"a"*64+b"\n"
    payload={"executable":sys.executable,"python":"3.14","rows":rows}
    monkeypatch.setattr(collector,"run",lambda *args,**kwargs: subprocess.CompletedProcess([],0,json.dumps(payload).encode(),b""))
    return export


def test_active_collector_inventory_exactly_matches_selected_export(monkeypatch: pytest.MonkeyPatch) -> None:
    export=active_tool_inventory(monkeypatch,[{"name":"Packaging","version":"25.0"}])
    rows,digest=collector.validate_collector_environment(export)
    assert [rows,digest] == [[{"name":"packaging","version":"25.0"}],collector.canonical_inventory_rows([{"name":"packaging","version":"25.0"}])]


def test_active_collector_inventory_rejects_extra_bootstrap_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    export=active_tool_inventory(monkeypatch,[{"name":"packaging","version":"25.0"},{"name":"pip","version":"25.0"}])
    with pytest.raises(RuntimeError,match="extra=.*pip"): collector.validate_collector_environment(export)


def test_active_collector_inventory_rejects_project_root(monkeypatch: pytest.MonkeyPatch) -> None:
    export=active_tool_inventory(monkeypatch,[{"name":"packaging","version":"25.0"},{"name":"tree-sitter-analyzer","version":"1"}])
    with pytest.raises(RuntimeError,match="root must be absent"): collector.validate_collector_environment(export)


def test_clean_env_drops_hostile_uv_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UV_CONFIG_FILE","/hostile/uv.toml"); monkeypatch.setenv("UV_INDEX_URL","https://hostile.invalid")
    environment=collector.clean_env()
    assert {key:environment.get(key) for key in ("UV_CONFIG_FILE","UV_INDEX_URL","UV_NO_CONFIG","UV_OFFLINE")} == {"UV_CONFIG_FILE":None,"UV_INDEX_URL":None,"UV_NO_CONFIG":"1","UV_OFFLINE":"1"}


@pytest.mark.skipif(os.name == "nt", reason="tracked: NO1-006B collector currently emits macOS-only E0 receipts")
def test_uv_export_ignores_hostile_config_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    hostile=tmp_path/"uv.toml"; hostile.write_text("this is not valid toml = [")
    monkeypatch.setenv("UV_CONFIG_FILE",str(hostile))
    command=["uv","export","--no-config","--frozen","--offline","--only-group",collector.TOOL_GROUP,"--no-emit-project","--format","requirements-txt"]
    result=collector.run(command,cwd=REPO)
    assert b"packaging==25.0" in result.stdout


def test_source_archive_ignores_hostile_local_and_global_tar_umask(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # PR #1250: archive identity must be independent of ambient and repository Git configuration.
    source=tmp_path/"source"; source.mkdir(); (source/"file.txt").write_text("content\n")
    for command in (["git","init","-q"],["git","config","user.email","contract@example.invalid"],["git","config","user.name","Contract"],["git","add","."],["git","commit","-qm","source"]):
        subprocess.run(command,cwd=source,check=True)
    clean_digest=collector.source_archive_sha(source,tmp_path/"clean.tar")
    global_config=tmp_path/"hostile.gitconfig"; global_config.write_text("[tar]\n\tumask = 077\n")
    subprocess.run(["git","config","tar.umask","077"],cwd=source,check=True)
    original=collector.clean_env
    def hostile_env(overrides: dict[str,str] | None=None) -> dict[str,str]:
        environment=original(overrides); environment["GIT_CONFIG_GLOBAL"]=str(global_config); return environment
    monkeypatch.setattr(collector,"clean_env",hostile_env)
    hostile_digest=collector.source_archive_sha(source,tmp_path/"hostile.tar")
    assert hostile_digest == clean_digest


def test_bound_blob_hash_is_independent_of_crlf_checkout(tmp_path: Path) -> None:
    repo=tmp_path/"repo"; repo.mkdir(); tracked=repo/"uv.lock"; tracked.write_bytes(b"version = 1\n")
    for command in (["git","init","-q"],["git","config","user.email","contract@example.invalid"],["git","config","user.name","Contract"],["git","add","uv.lock"],["git","commit","-qm","blob"]): subprocess.run(command,cwd=repo,check=True)
    commit=subprocess.run(["git","rev-parse","HEAD"],cwd=repo,check=True,capture_output=True,text=True).stdout.strip()
    tracked.write_bytes(b"version = 1\r\n")
    assert collector.digest_bytes(collector.bound_blob(repo,commit,"uv.lock")) == collector.digest_bytes(b"version = 1\n")

def test_subject_closure_command_excludes_tool_group() -> None:
    command=baseline()["commands"]["export"]
    assert command == ["uv","export","--no-config","--frozen","--offline","--no-dev","--no-emit-project","--format","requirements-txt"]


@pytest.mark.skipif(os.name == "nt", reason="tracked: NO1-006B collector currently emits macOS-only E0 receipts")
def test_external_interpreter_probe_preserves_clean_ignored_gate(tmp_path: Path) -> None:
    # NO1-006B review 2026-08-10: probe the interpreter placement without weakening ignored-file rejection.
    root=tmp_path/"collector"; (root/"scripts").mkdir(parents=True); (root/"schemas").mkdir()
    shutil.copy2(Path(collector.__file__),root/"scripts/collect_no1_006b_baseline.py")
    shutil.copy2(SCHEMA,root/"schemas/no1-006b-baseline.schema.json")
    shutil.copy2(REPO/"uv.lock",root/"uv.lock")
    for command in (["git","init","-q"],["git","config","user.email","contract@example.invalid"],["git","config","user.name","Contract"],["git","add","."],["git","commit","-qm","probe"]):
        subprocess.run(command,cwd=root,check=True)
    interpreter=Path(sys.executable).resolve()
    assert root.resolve() not in interpreter.parents
    probe='import importlib.util,json; p="scripts/collect_no1_006b_baseline.py"; s=importlib.util.spec_from_file_location("probe_collector",p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(json.dumps(m.collector_identity("a"*64),sort_keys=True))'
    env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"}
    result=subprocess.run([str(interpreter),"-c",probe],cwd=root,env=env,check=True,capture_output=True,text=True)
    commit=subprocess.run(["git","rev-parse","HEAD"],cwd=root,check=True,capture_output=True,text=True).stdout.strip()
    expected={"commit":commit,"script_sha256":collector.digest_bytes(collector.git(root,"show",f"{commit}:scripts/collect_no1_006b_baseline.py")),"schema_sha256":collector.digest_bytes(collector.git(root,"show",f"{commit}:schemas/no1-006b-baseline.schema.json")),"tool_lock_sha256":collector.digest_bytes(collector.git(root,"show",f"{commit}:uv.lock")),"tool_export_sha256":"a"*64}
    status=subprocess.run(["git","status","--porcelain=v1","--untracked-files=all","--ignored"],cwd=root,check=True,capture_output=True,text=True).stdout
    assert json.loads(result.stdout) == expected
    assert status == ""


def test_verified_uv_resolves_and_attests_configured_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO1_006B_UV",str(Path(shutil.which("uv") or "missing")))
    path,version,digest=collector.verified_uv()
    assert [path,version,digest] == [Path(shutil.which("uv") or "missing").resolve(),collector.EXPECTED_UV_VERSION,collector.EXPECTED_UV_SHA256]


def test_verified_uv_rejects_digest_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake=tmp_path/("uv.exe" if os.name=="nt" else "uv"); fake.write_bytes(b"not uv")
    monkeypatch.setenv("NO1_006B_UV",str(fake))
    monkeypatch.setattr(collector,"run",lambda *args,**kwargs: subprocess.CompletedProcess([],0,(collector.EXPECTED_UV_VERSION+"\n").encode(),b""))
    with pytest.raises(RuntimeError,match="identity mismatch"): collector.verified_uv()

# fmt: on
