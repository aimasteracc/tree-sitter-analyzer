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


def canon(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


async def main() -> None:
    executable, project_arg, transcript_arg = sys.argv[1:]
    project, transcript = pathlib.Path(project_arg), pathlib.Path(transcript_arg)
    dist = importlib.metadata.distribution("tree-sitter-analyzer")
    module = __import__("tree_sitter_analyzer")
    events: list[dict[str, object]] = []
    params = StdioServerParameters(
        command=executable,
        args=[],
        cwd=str(project),
        env={**os.environ, "PYTHONPATH": "", "TREE_SITTER_PROJECT_ROOT": str(project)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            events.append(
                {
                    "sequence": 1,
                    "method": "initialize",
                    "response": initialized.model_dump(mode="json", by_alias=True),
                }
            )
            events.append({"sequence": 2, "method": "notifications/initialized"})
            listed = await session.list_tools()
            names = [tool.name for tool in listed.tools]
            events.append(
                {"sequence": 3, "method": "tools/list", "response": {"names": names}}
            )
            called = await session.call_tool("index", {"action": "status"})
            call_data = called.model_dump(mode="json", by_alias=True)
            events.append(
                {
                    "sequence": 4,
                    "method": "tools/call",
                    "request": {"name": "index", "arguments": {"action": "status"}},
                    "response": call_data,
                }
            )
    transcript.write_text(
        "".join(canon(event) + "\n" for event in events), encoding="utf-8"
    )
    assert names == TOOLS
    assert called.isError is False
    assert len(called.content) == 1 and called.content[0].type == "text"
    envelope = json.loads(called.content[0].text)
    assert (
        envelope["format"] == "toon"
        and isinstance(envelope["toon_content"], str)
        and envelope["toon_content"]
    )
    assert envelope["success"] is True and envelope["verdict"] in {
        "PASS",
        "WARN",
        "INFO",
    }
    assert initialized.serverInfo.name == "tree-sitter-analyzer-mcp"
    assert initialized.serverInfo.version.startswith(dist.version + " ")
    result = {
        "metadata": {
            "name": dist.metadata["Name"],
            "version": dist.version,
            "location": str(dist.locate_file("")),
            "module_file": module.__file__,
        },
        "runtime": {"python": sys.version, "executable": sys.executable},
        "mcp": {
            "executable": executable,
            "protocol_version": initialized.protocolVersion,
            "server_name": initialized.serverInfo.name,
            "server_version": initialized.serverInfo.version,
            "tools": names,
            "first_call": {
                "name": "index",
                "arguments": {"action": "status"},
                "is_error": False,
                "default_format": "toon",
                "verdict": envelope["verdict"],
            },
        },
    }
    print(canon(result))


asyncio.run(main())
