"""显式验证动作的参数与取消所有权。"""

import threading

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("repeated", [False, True])
async def test_tool_cancellation_waits_for_worker_cleanup(
    tmp_path, monkeypatch, repeated
):
    import asyncio

    from tree_sitter_analyzer.mcp.tools import verification_tool

    entered = threading.Event()
    cleaned = threading.Event()
    cancelled = threading.Event()
    release = threading.Event()

    def controlled(request, root, cancel):
        entered.set()
        assert cancel.wait(5) is True
        cancelled.set()
        assert release.wait(5) is True
        cleaned.set()
        return {"success": False}

    monkeypatch.setattr(verification_tool, "run_verification_request", controlled)
    task = asyncio.create_task(
        verification_tool.VerificationTool(str(tmp_path)).execute({"request": "token"})
    )
    assert await asyncio.to_thread(entered.wait, 5) is True
    try:
        task.cancel()
        assert await asyncio.to_thread(cancelled.wait, 5) is True
        if repeated:
            task.cancel()
            await asyncio.sleep(0)
        assert task.done() is False
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set() is True


@pytest.mark.asyncio
async def test_verification_tool_reports_invalid_descriptor_without_execution(tmp_path):
    from tree_sitter_analyzer.mcp.tools.verification_tool import VerificationTool

    tool = VerificationTool(str(tmp_path))
    with pytest.raises(ValueError, match="request must be"):
        await tool.execute({"request": 1})
    result = await tool.execute({"request": "invalid"})
    assert result["success"] is False
    assert result["error_code"] == "VERIFICATION_REQUEST_INVALID"
    assert result["executed_steps"] == []
