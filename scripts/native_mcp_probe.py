#!/usr/bin/env python3
"""Official MCP SDK probe copied into and executed from a qualification venv."""

import asyncio
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
    module_relative = str(module_origin.relative_to(location))
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
            in {str(item) for item in (dist.files or [])},
        },
        "runtime": {
            "python": sys.version,
            "executable": str(pathlib.Path(sys.executable).absolute()),
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
    assert str(project) in toon
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
            "executable": str(pathlib.Path(executable).absolute()),
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
