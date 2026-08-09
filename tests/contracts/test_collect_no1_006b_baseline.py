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

import pytest
from jsonschema.exceptions import ValidationError

from scripts import collect_no1_006b_baseline as collector

REPO = Path(__file__).parents[2]
BASELINE = REPO / "docs/baselines/no1-006b-macos-e0.json"
SCHEMA = REPO / "schemas/no1-006b-baseline.schema.json"
RFC = REPO / "rfcs/0024-default-dependency-split.md"


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


def test_receipt_binds_exact_collector_and_schema_bytes() -> None:
    report=baseline()
    assert [report["collector"]["script_sha256"],report["collector"]["schema_sha256"]] == [collector.sha256(Path(collector.__file__)),collector.sha256(SCHEMA)]


def test_schema_rejects_invalid_rfc3339_timestamp() -> None:
    report=mutated(("collection_started_at_utc",),"not-a-date")
    with pytest.raises(ValueError, match="Invalid isoformat"): collector.validate_receipt(report,schema())


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


def test_validator_rejects_lock_hash_mismatch() -> None:
    report=mutated(("dependency_closure","lock_sha256"),"0"*64)
    with pytest.raises(ValueError,match="cross-field"): collector.validate_receipt(report,schema())


def test_validator_rejects_artifact_size_mismatch() -> None:
    report=mutated(("measurements","root_wheel_artifact_size_bytes"),1)
    with pytest.raises(ValueError,match="cross-field"): collector.validate_receipt(report,schema())


def test_validator_rejects_stale_canonical_hash() -> None:
    report=copy.deepcopy(baseline()); report["repeats"]=4
    with pytest.raises(ValueError,match="cross-field"): collector.validate_receipt(report,schema())


def test_schema_supports_each_native_axis_without_fabricating_measurements() -> None:
    report=copy.deepcopy(baseline()); report["measured_axis"]="linux"; report["environment"]["system"]="linux"; report["platform_axes"]={"macos":"unknown","linux":"measured_e0","windows":"unknown"}; report["canonical_payload_sha256"]=collector.canonical_hash(report)
    collector.validate_receipt(report,schema())



def test_schema_rejects_cli_startup_definition_mutation() -> None:
    report=mutated(("measurements","cli_startup","definition"),"X"*20)
    with pytest.raises(ValidationError): collector.validate_receipt(report,schema())


def test_schema_rejects_mcp_startup_definition_mutation() -> None:
    report=mutated(("measurements","mcp_startup","definition"),"Y"*20)
    with pytest.raises(ValidationError): collector.validate_receipt(report,schema())


def test_schema_rejects_measured_axis_contradiction() -> None:
    report=mutated(("platform_axes","macos"),"unknown")
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


def test_bounded_reader_times_out_on_partial_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    read_fd,write_fd=__import__("os").pipe(); __import__("os").write(write_fd,b'{"id":')
    class Process: stdout=__import__("os").fdopen(read_fd,"rb",buffering=0)
    monkeypatch.setattr(collector,"MAX_FRAME_BYTES",64)
    with pytest.raises(TimeoutError,match="absolute deadline"): collector.read_json_frame(Process(),__import__("time").monotonic()+0.01)
    __import__("os").close(write_fd); Process.stdout.close()



def test_file_budget_rejects_oversized_artifact(tmp_path: Path) -> None:
    artifact=tmp_path/"artifact"; artifact.write_bytes(b"xx")
    with pytest.raises(RuntimeError,match="disk budget"): collector.require_file_budget(artifact,1,"test artifact")


def test_collector_rejects_unbounded_repeat_count(tmp_path: Path) -> None:
    with pytest.raises(ValueError,match="between 3 and 20"): collector.collect(REPO,tmp_path/"receipt.json",21,collector.EXPECTED_SUBJECT_COMMIT)

def test_rfc_reproduction_command_uses_external_interpreter() -> None:
    # NO1-006B review 2026-08-10: a repo-local ignored venv made the clean gate reject the documented command.
    reproduction=RFC.read_text().split("## Reproduction of the descriptive receipt",1)[1].split("## Measured macOS E0 receipt",1)[0]
    assert ".venv/bin/python" not in reproduction
    assert 'TOOL_VENV="$RUN_ROOT/collector-tool-venv"' in reproduction
    assert '"$TOOL_PYTHON" "$COLLECTOR/scripts/collect_no1_006b_baseline.py"' in reproduction


def test_external_interpreter_probe_preserves_clean_ignored_gate(tmp_path: Path) -> None:
    # NO1-006B review 2026-08-10: probe the interpreter placement without weakening ignored-file rejection.
    root=tmp_path/"collector"; (root/"scripts").mkdir(parents=True); (root/"schemas").mkdir()
    shutil.copy2(Path(collector.__file__),root/"scripts/collect_no1_006b_baseline.py")
    shutil.copy2(SCHEMA,root/"schemas/no1-006b-baseline.schema.json")
    for command in (["git","init","-q"],["git","config","user.email","contract@example.invalid"],["git","config","user.name","Contract"],["git","add","."],["git","commit","-qm","probe"]):
        subprocess.run(command,cwd=root,check=True)
    interpreter=Path(sys.executable).resolve()
    assert root.resolve() not in interpreter.parents
    probe='import importlib.util,json; p="scripts/collect_no1_006b_baseline.py"; s=importlib.util.spec_from_file_location("probe_collector",p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(json.dumps(m.collector_identity(),sort_keys=True))'
    env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"}
    result=subprocess.run([str(interpreter),"-c",probe],cwd=root,env=env,check=True,capture_output=True,text=True)
    commit=subprocess.run(["git","rev-parse","HEAD"],cwd=root,check=True,capture_output=True,text=True).stdout.strip()
    expected={"commit":commit,"script_sha256":collector.sha256(root/"scripts/collect_no1_006b_baseline.py"),"schema_sha256":collector.sha256(root/"schemas/no1-006b-baseline.schema.json")}
    status=subprocess.run(["git","status","--porcelain=v1","--untracked-files=all","--ignored"],cwd=root,check=True,capture_output=True,text=True).stdout
    assert json.loads(result.stdout) == expected
    assert status == ""

# fmt: on
