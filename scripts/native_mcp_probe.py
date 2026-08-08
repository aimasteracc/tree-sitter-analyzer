#!/usr/bin/env python3
"""Official MCP SDK probe copied into and executed from a qualification venv."""

import asyncio
import base64
import csv
import hashlib
import importlib.metadata
import json
import os
import pathlib
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

TOOLS = [
    "search",
    "nav",
    "structure",
    "health",
    "edit",
    "project",
    "index",
    "viz",
    "set_project_path",
]


def dump(value: object) -> object:
    method = getattr(value, "model_dump", None)
    return method(mode="json", by_alias=True) if method else value.dict(by_alias=True)


def canon(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def file_sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def installed_record(
    dist: importlib.metadata.Distribution, location: pathlib.Path
) -> dict[str, object]:
    record_paths = [
        item for item in (dist.files or []) if pathlib.Path(str(item)).name == "RECORD"
    ]
    if len(record_paths) != 1:
        raise AssertionError("installed distribution must contain exactly one RECORD")
    record_path = pathlib.Path(dist.locate_file(record_paths[0])).resolve(strict=True)
    rows = list(csv.reader(record_path.read_text("utf-8").splitlines()))
    names = [row[0] for row in rows if len(row) == 3]
    if not rows or len(names) != len(rows) or len(names) != len(set(names)):
        raise AssertionError("installed RECORD rows must be unique triples")
    files = []
    for name, declared_hash, declared_size in rows:
        lowered = pathlib.Path(name).name.lower()
        if lowered.endswith((".pth", ".egg-link")) or lowered in {
            "sitecustomize.py",
            "usercustomize.py",
        }:
            raise AssertionError("installed RECORD contains an injection hook")
        path = pathlib.Path(dist.locate_file(name)).resolve(strict=True)
        if (
            not path.is_file()
            or path.is_symlink()
            or not path.is_relative_to(pathlib.Path(sys.prefix).resolve())
        ):
            raise AssertionError("installed RECORD file escaped the fresh venv")
        data = path.read_bytes()
        actual = hashlib.sha256(data).digest()
        is_record = path == record_path
        generated_pyc = path.suffix.lower() == ".pyc"
        if is_record or generated_pyc:
            if declared_hash or declared_size:
                raise AssertionError(
                    "generated installed RECORD entry must be unhashed"
                )
        else:
            if (
                not declared_hash
                or not declared_size
                or int(declared_size) != len(data)
            ):
                raise AssertionError("installed RECORD file lacks exact size/hash")
            algorithm, encoded = declared_hash.split("=", 1)
            expected = base64.urlsafe_b64encode(actual).rstrip(b"=").decode()
            if algorithm != "sha256" or encoded != expected:
                raise AssertionError("installed RECORD file bytes mismatch")
        files.append({"path": name, "sha256": actual.hex(), "size": len(data)})
    return {
        "record_path": str(record_path),
        "record_sha256": file_sha256(record_path),
        "entry_count": len(files),
        "files": files,
    }


def installed_provenance() -> dict[str, object]:
    dist = importlib.metadata.distribution("tree-sitter-analyzer")
    module = __import__("tree_sitter_analyzer")
    location = pathlib.Path(dist.locate_file("")).resolve()
    direct_urls = list(
        location.glob("tree_sitter_analyzer-*.dist-info/direct_url.json")
    )
    if len(direct_urls) != 1:
        raise AssertionError("installed distribution must contain one direct_url.json")
    module_origin = pathlib.Path(module.__spec__.origin).resolve()
    module_relative = module_origin.relative_to(location).as_posix()
    record = installed_record(dist, location)
    return {
        "metadata": {
            "name": dist.metadata["Name"],
            "version": dist.version,
            "location": str(location),
            "module_file": str(pathlib.Path(module.__file__).resolve()),
            "module_origin": str(module_origin),
            "direct_url": json.loads(direct_urls[0].read_text("utf-8")),
            "direct_url_path": str(direct_urls[0].resolve()),
            "module_recorded": module_relative
            in {item["path"] for item in record["files"]},
            "installed_record": record,
        },
        "runtime": {
            "python": sys.version,
            "executable": str(
                pathlib.Path(sys.executable).absolute().parent.resolve()
                / pathlib.Path(sys.executable).name
            ),
            "prefix": str(pathlib.Path(sys.prefix).resolve()),
        },
    }


async def main() -> None:
    executable, project_arg, transcript_arg = sys.argv[1:]
    project, transcript = (
        pathlib.Path(project_arg).resolve(),
        pathlib.Path(transcript_arg),
    )
    provenance = installed_provenance()
    events = []
    params = StdioServerParameters(
        command=executable,
        args=[],
        cwd=str(project),
        env={**os.environ, "PYTHONPATH": "", "TREE_SITTER_PROJECT_ROOT": str(project)},
    )
    async with stdio_client(params) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            initialized = await session.initialize()
            events.append(
                {"sequence": 1, "method": "initialize", "response": dump(initialized)}
            )
            listed = await session.list_tools()
            names = [tool.name for tool in listed.tools]
            events.append(
                {"sequence": 2, "method": "tools/list", "response": {"names": names}}
            )
            called = await session.call_tool("index", {"action": "status"})
            events.append(
                {
                    "sequence": 3,
                    "method": "tools/call",
                    "request": {"name": "index", "arguments": {"action": "status"}},
                    "response": dump(called),
                }
            )
    transcript.write_text("".join(canon(event) + "\n" for event in events), "utf-8")
    assert names == TOOLS
    assert getattr(called, "isError", getattr(called, "is_error", None)) is False
    assert len(called.content) == 1 and called.content[0].type == "text"
    envelope = json.loads(called.content[0].text)
    toon = envelope.get("toon_content")
    assert envelope.get("format") == "toon" and isinstance(toon, str)
    assert project.name in toon
    assert "indexed: false" in toon and "total_files: 0" in toon
    assert "codegraph_status: index missing or empty" in toon
    assert envelope.get("success") is True and envelope.get("verdict") == "WARN"
    server_info = getattr(
        initialized, "serverInfo", getattr(initialized, "server_info", None)
    )
    protocol = getattr(
        initialized, "protocolVersion", getattr(initialized, "protocol_version", None)
    )
    assert server_info.name == "tree-sitter-analyzer-mcp"
    assert server_info.version.startswith(str(provenance["metadata"]["version"]) + " ")
    result = {
        **provenance,
        "mcp": {
            "executable": str(
                pathlib.Path(executable).absolute().parent.resolve()
                / pathlib.Path(executable).name
            ),
            "protocol_version": protocol,
            "server_name": server_info.name,
            "server_version": server_info.version,
            "tools": names,
            "first_call": {
                "name": "index",
                "arguments": {"action": "status"},
                "is_error": False,
                "default_format": "toon",
                "verdict": "WARN",
                "project_root": str(project),
                "indexed": False,
                "total_files": 0,
                "summary": "codegraph_status: index missing or empty",
            },
        },
    }
    print(canon(result))


if sys.argv[1:] == ["--metadata-only"]:
    print(canon(installed_provenance()))
else:
    asyncio.run(main())
